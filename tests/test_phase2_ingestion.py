from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.canonical.adapter import ExistingCatalogueAdapter
from backend.canonical.fingerprint import canonical_state_equal
from backend.catalogue_normalize import normalize_catalogue, normalize_labels, normalize_price_pair
from backend.catalogue_validate import validate_catalogue
from backend.main import app, get_swiggy_access, require_session
from backend.raw_capture import bind_raw_capture, bound_path, pending_dir, pending_path, read_capture, write_pending_raw
from backend.schemas import AuthUser, CatalogCreateRequest, CatalogCreateResponse
from backend.services.catalog_service import AccessResult, SwiggyAccess, create_catalog
from backend.store import CatalogueIdentityConflict, list_catalogues, save_catalogue
from scraper.swiggy.models import Catalogue, MenuCategory, MenuItem, RawSource, Restaurant
from scraper.swiggy.parser import parse_swiggy_catalogue

FIXTURE_JSON = Path(__file__).parent / "fixtures" / "swiggy_menu_payload.json"
SAMPLE = {
    "restaurant_name": "Harbor Spice House",
    "fssai_number": "12345678901234",
    "swiggy_url": "https://www.swiggy.com/city/mangaluru/harbor-spice-house-rest999001",
    "organization_id": "org_1",
}


class FakeAccess(SwiggyAccess):
    def __init__(self, result: AccessResult):
        self.result = result

    def load(self, swiggy_url: str) -> AccessResult:
        return self.result


def test_price_normalization_rules():
    selling, original, invalid = normalize_price_pair("₹1,249", "₹1,249")
    assert selling == 1249
    assert original is None
    assert invalid is False
    selling, original, invalid = normalize_price_pair(250, 200)
    assert selling == 200
    assert original == 250
    selling, original, invalid = normalize_price_pair("n/a", None)
    assert selling is None
    assert invalid is True
    selling, original, _invalid = normalize_price_pair(24900, None)
    assert selling == 24900


def test_swiggy_fixture_prices_are_not_divided_again():
    raw = RawSource(source_url=SAMPLE["swiggy_url"], next_data=json.loads(FIXTURE_JSON.read_text(encoding="utf-8")))
    parsed = parse_swiggy_catalogue(raw)
    before = [item.price for category in parsed.categories for item in category.items]
    normalize_catalogue(parsed)
    after = [item.price for category in parsed.categories for item in category.items]
    assert before
    assert before == after
    assert all(price is None or price < 10000 for price in after)


def test_category_tag_image_and_missing_normalization():
    catalogue = Catalogue(
        source="swiggy",
        source_url="https://www.swiggy.com/city/sample/norm-resta",
        extraction_status="ok",
        restaurant=Restaurant(name="  Harbor   Spice  "),
        categories=[
            MenuCategory(
                name="  Mains  ",
                item_count=9,
                items=[
                    MenuItem(
                        name="  Rice  Bowl ",
                        price="₹100",
                        original_price="₹100",
                        labels=["", " Bestseller ", "Bestseller"],
                        image_url="https://example.com/veg-icon.png",
                        additional_information={"id": "m1"},
                    ),
                    MenuItem(name="Dal", labels=["  "]),
                    MenuItem(
                        name="Rice Bowl",
                        price=100,
                        additional_information={"id": "m1"},
                    ),
                ],
            )
        ],
    )
    normalize_catalogue(catalogue)
    assert catalogue.restaurant.name == "Harbor Spice"
    assert catalogue.categories[0].name == "Mains"
    rice = catalogue.categories[0].items[0]
    assert rice.name == "Rice Bowl"
    assert rice.price == 100
    assert rice.original_price is None
    assert rice.labels == ["Bestseller"]
    assert rice.is_bestseller is True
    assert rice.image_url is None
    assert rice.source_image_url == "https://example.com/veg-icon.png"
    quality = validate_catalogue(catalogue)
    codes = {issue["code"] for issue in quality["issues"]}
    assert "missing_price" in codes
    assert "missing_image" in codes
    assert "missing_source_item_id" in codes
    assert "duplicate_source_item_id" in codes
    assert "duplicate_item_row" in codes
    assert "category_count_mismatch" in codes
    assert normalize_labels([" a ", "", "a", None]) == ["a"]


def test_quality_and_raw_capture_are_excluded_from_fingerprint():
    base = CatalogCreateResponse(
        extraction_status="ok",
        restaurant_name="Harbor Spice House",
        fssai_number="12345678901234",
        source_url="https://www.swiggy.com/city/sample/fp-resta",
        restaurant={"name": "Harbor", "restaurant_id": "1"},
        categories=[{"name": "Mains", "items": [{"name": "Rice", "price": 100, "additional_information": {"id": "m1"}}]}],
        item_count=1,
    )
    other = base.model_copy(update={"quality": {"issues": [{"code": "missing_image"}]}, "raw_capture_id": "token-1"})
    assert canonical_state_equal(base, other)


def test_raw_pending_bind_and_tenant_isolation(tmp_path, monkeypatch):
    monkeypatch.setenv("CATALOGFORGE_RAW_DIR", str(tmp_path / "raw"))
    raw = RawSource(source_url="https://www.swiggy.com/city/sample/raw-resta", html="<html>menu</html>")
    token = write_pending_raw(organization_id="org_1", raw=raw, platform="swiggy")
    assert token
    pending = pending_path("org_1", token)
    assert pending.is_file()
    payload = read_capture(pending)
    assert "menu" in payload["raw"]["html"]
    other = pending_path("org_a", token)
    assert other != pending
    assert not other.is_file()
    dest = bind_raw_capture(organization_id="org_1", scrape_token=token, catalogue_id="cat-1", user_id="user-1")
    assert dest is not None
    assert dest == bound_path("org_1", "cat-1", token).resolve()
    assert dest.is_file()
    assert not pending.is_file()
    bound = read_capture(dest)
    assert bound["catalogue_id"] == "cat-1"
    assert bound["user_id"] == "user-1"


def test_raw_pending_remains_when_bind_is_skipped(tmp_path, monkeypatch):
    monkeypatch.setenv("CATALOGFORGE_RAW_DIR", str(tmp_path / "raw"))
    raw = RawSource(source_url="https://www.swiggy.com/city/sample/pending-resta", html="<html>keep</html>")
    token = write_pending_raw(organization_id="org_1", raw=raw, platform="swiggy")
    assert pending_path("org_1", token).is_file()
    bind_raw_capture(organization_id="org_1", scrape_token=None, catalogue_id="cat-x")
    assert pending_path("org_1", token).is_file()


def test_create_catalog_normalizes_and_captures_raw(monkeypatch, tmp_path):
    monkeypatch.setenv("CATALOGFORGE_RAW_DIR", str(tmp_path / "raw"))
    raw = RawSource(
        source_url=SAMPLE["swiggy_url"],
        next_data=json.loads(FIXTURE_JSON.read_text(encoding="utf-8")),
        html="<html>source</html>",
    )
    request = CatalogCreateRequest.model_validate(SAMPLE)
    result = create_catalog(request, FakeAccess(AccessResult(method="local_fixture", raw=raw)))
    assert result.extraction_status == "ok"
    assert result.raw_capture_id
    assert pending_path("org_1", result.raw_capture_id).is_file()
    assert result.quality is not None
    assert result.canonical is not None
    assert result.canonical["provenance"]["platform"] == "swiggy"
    prices = [item["price"] for category in result.categories for item in category["items"]]
    assert prices
    stored = save_catalogue(user_id="user-1", organization_id="org_1", result=result)
    assert stored.result.canonical
    bind_raw_capture(
        organization_id="org_1",
        scrape_token=result.raw_capture_id,
        catalogue_id=stored.id,
        user_id="user-1",
    )
    assert bound_path("org_1", stored.id, result.raw_capture_id).is_file()
    assert not pending_path("org_1", result.raw_capture_id).is_file()
    again = create_catalog(request, FakeAccess(AccessResult(method="local_fixture", raw=raw)))
    second = save_catalogue(user_id="user-1", organization_id="org_1", result=again)
    assert second.id == stored.id
    bind_raw_capture(
        organization_id="org_1",
        scrape_token=again.raw_capture_id,
        catalogue_id=second.id,
        user_id="user-1",
    )
    assert again.raw_capture_id != result.raw_capture_id
    assert bound_path("org_1", stored.id, again.raw_capture_id).is_file()
    import sqlite3
    from backend.store import catalogue_db_path

    connection = sqlite3.connect(catalogue_db_path())
    try:
        count = connection.execute(
            "SELECT COUNT(*) FROM catalogue_revisions WHERE catalogue_id = ?", (stored.id,)
        ).fetchone()[0]
    finally:
        connection.close()
    assert count == 0


def test_identity_conflict_leaves_pending_raw(tmp_path, monkeypatch):
    monkeypatch.setenv("CATALOGFORGE_RAW_DIR", str(tmp_path / "raw"))
    url_x = "https://www.swiggy.com/city/sample/conflict-a-resta"
    url_y = "https://www.swiggy.com/city/sample/conflict-b-resta"
    save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=CatalogCreateResponse(
            extraction_status="ok",
            restaurant_name="A",
            fssai_number="12345678901234",
            source_url=url_x,
            restaurant={"name": "A", "restaurant_id": "123"},
            categories=[{"name": "Mains", "items": [{"name": "Rice", "price": 100, "additional_information": {"id": "m1"}}]}],
            item_count=1,
        ),
    )
    save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=CatalogCreateResponse(
            extraction_status="ok",
            restaurant_name="B",
            fssai_number="12345678901234",
            source_url=url_y,
            restaurant={"name": "B", "restaurant_id": "456"},
            categories=[{"name": "Mains", "items": [{"name": "Dal", "price": 110, "additional_information": {"id": "m2"}}]}],
            item_count=1,
        ),
    )
    raw = RawSource(source_url=url_x, html="<html>conflict</html>")
    token = write_pending_raw(organization_id="org_1", raw=raw, platform="swiggy")
    incoming = CatalogCreateResponse(
        extraction_status="ok",
        restaurant_name="C",
        fssai_number="12345678901234",
        source_url=url_x,
        restaurant={"name": "C", "restaurant_id": "456"},
        categories=[{"name": "Mains", "items": [{"name": "Tea", "price": 10, "additional_information": {"id": "m3"}}]}],
        item_count=1,
        raw_capture_id=token,
    )
    with pytest.raises(CatalogueIdentityConflict):
        save_catalogue(user_id="user-1", organization_id="org_1", result=incoming)
    assert pending_path("org_1", token).is_file()


def test_adapter_keeps_normalized_provenance():
    catalogue = Catalogue(
        source="zomato",
        source_url="https://www.zomato.com/city/alpha",
        extraction_status="ok",
        restaurant=Restaurant(name="Alpha", restaurant_id="z-1"),
        categories=[MenuCategory(name="Mains", items=[MenuItem(name="Rice", price="₹80", additional_information={"id": "z9"})])],
    )
    normalize_catalogue(catalogue)
    document = ExistingCatalogueAdapter().to_canonical(catalogue)
    assert document.provenance.platform == "zomato"
    assert document.venue.source_entity_id == "z-1"
    item = document.menus[0].categories[0].items[0]
    assert item.price == 80
    assert item.source_item_id == "z9"


def test_catalog_create_api_binds_raw(monkeypatch, tmp_path):
    monkeypatch.setenv("CATALOGFORGE_RAW_DIR", str(tmp_path / "raw"))
    raw = RawSource(
        source_url=SAMPLE["swiggy_url"],
        next_data=json.loads(FIXTURE_JSON.read_text(encoding="utf-8")),
        html="<html>api</html>",
    )

    class Fixture(SwiggyAccess):
        def load(self, swiggy_url: str) -> AccessResult:
            return AccessResult(method="local_fixture", raw=raw)

    app.dependency_overrides[require_session] = lambda: AuthUser(id="user-1", email="owner@example.com")
    app.dependency_overrides[get_swiggy_access] = lambda: Fixture()
    client = TestClient(app)
    try:
        response = client.post("/catalog/create", json=SAMPLE)
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    body = response.json()
    assert body["raw_capture_id"]
    assert body["canonical"]
    assert bound_path("org_1", body["id"], body["raw_capture_id"]).is_file()
    assert not pending_path("org_1", body["raw_capture_id"]).is_file()


def test_large_raw_html_and_next_data_are_preserved(tmp_path, monkeypatch):
    monkeypatch.setenv("CATALOGFORGE_RAW_DIR", str(tmp_path / "raw"))
    html = "H" * (8 * 1024 * 1024 + 2048)
    next_data = {"menu": "N" * (2 * 1024 * 1024 + 16), "id": "999"}
    token = write_pending_raw(
        organization_id="org_1",
        raw=RawSource(source_url=SAMPLE["swiggy_url"], html=html, next_data=next_data),
        platform="swiggy",
    )
    payload = read_capture(pending_path("org_1", token))
    assert payload.get("truncated") is not True
    assert payload["raw"]["html"] == html
    assert payload["raw"]["next_data"] == next_data


def test_prepersist_adapter_failure_still_projects_canonical(monkeypatch):
    raw = RawSource(
        source_url=SAMPLE["swiggy_url"],
        next_data=json.loads(FIXTURE_JSON.read_text(encoding="utf-8")),
        html="<html>adapter</html>",
    )

    def boom(self, *args, **kwargs):
        raise RuntimeError("adapter mapping failed")

    monkeypatch.setattr("backend.services.catalog_service.ExistingCatalogueAdapter.to_canonical", boom)
    result = create_catalog(CatalogCreateRequest.model_validate(SAMPLE), FakeAccess(AccessResult(method="local_fixture", raw=raw)))
    assert result.extraction_status == "ok"
    assert result.canonical is not None
    assert result.canonical["provenance"]["platform"] == "swiggy"
    stored = save_catalogue(user_id="user-1", organization_id="org_1", result=result)
    assert stored.result.canonical is not None


def test_both_canonical_mappings_fail_are_not_successful_ingest(monkeypatch):
    raw = RawSource(
        source_url=SAMPLE["swiggy_url"],
        next_data=json.loads(FIXTURE_JSON.read_text(encoding="utf-8")),
        html="<html>both-fail</html>",
    )

    def boom_adapter(self, *args, **kwargs):
        raise RuntimeError("adapter mapping failed")

    def boom_response(*args, **kwargs):
        raise RuntimeError("response mapping failed")

    monkeypatch.setattr("backend.services.catalog_service.ExistingCatalogueAdapter.to_canonical", boom_adapter)
    monkeypatch.setattr("backend.services.catalog_service.to_canonical_from_response", boom_response)
    with pytest.raises(RuntimeError, match="response mapping failed"):
        create_catalog(CatalogCreateRequest.model_validate(SAMPLE), FakeAccess(AccessResult(method="local_fixture", raw=raw)))
    assert list_catalogues("user-1", "org_1") == []
    assert list(pending_dir("org_1").glob("*.json.gz"))


def test_crash_between_persist_and_bind_keeps_catalogue_and_pending():
    raw = RawSource(
        source_url=SAMPLE["swiggy_url"],
        next_data=json.loads(FIXTURE_JSON.read_text(encoding="utf-8")),
        html="<html>crash-bind</html>",
    )
    result = create_catalog(CatalogCreateRequest.model_validate(SAMPLE), FakeAccess(AccessResult(method="local_fixture", raw=raw)))
    stored = save_catalogue(user_id="user-1", organization_id="org_1", result=result)
    assert stored.result.canonical is not None
    assert pending_path("org_1", result.raw_capture_id).is_file()
    assert not bound_path("org_1", stored.id, result.raw_capture_id).is_file()
    rows = list_catalogues("user-1", "org_1")
    assert len(rows) == 1
    assert rows[0].id == stored.id


def test_cancel_before_persist_retains_pending_and_does_not_create_catalogue():
    raw = RawSource(
        source_url=SAMPLE["swiggy_url"],
        next_data=json.loads(FIXTURE_JSON.read_text(encoding="utf-8")),
        html="<html>cancel</html>",
    )
    result = create_catalog(CatalogCreateRequest.model_validate(SAMPLE), FakeAccess(AccessResult(method="local_fixture", raw=raw)))
    assert result.raw_capture_id
    assert pending_path("org_1", result.raw_capture_id).is_file()
    assert list_catalogues("user-1", "org_1") == []


def test_retry_and_duplicate_bind_tokens():
    first = write_pending_raw(
        organization_id="org_1",
        raw=RawSource(source_url=SAMPLE["swiggy_url"], html="<html>one</html>"),
        platform="swiggy",
    )
    second = write_pending_raw(
        organization_id="org_1",
        raw=RawSource(source_url=SAMPLE["swiggy_url"], html="<html>two</html>"),
        platform="swiggy",
    )
    assert first != second
    assert pending_path("org_1", first).is_file()
    assert pending_path("org_1", second).is_file()
    dest = bind_raw_capture(organization_id="org_1", scrape_token=first, catalogue_id="cat-retry", user_id="user-1")
    assert dest is not None
    again = bind_raw_capture(organization_id="org_1", scrape_token=first, catalogue_id="cat-retry", user_id="user-1")
    assert again is None
    assert bound_path("org_1", "cat-retry", first).is_file()
    assert pending_path("org_1", second).is_file()

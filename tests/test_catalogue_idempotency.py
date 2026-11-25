from __future__ import annotations

import threading

from fastapi.testclient import TestClient

from backend.main import app, get_swiggy_access, require_session
from backend.schemas import AuthUser, CatalogCreateResponse
from backend.services.catalog_service import FixtureAccess
from backend.store import list_catalogues, matching_catalogue_id, save_catalogue
from tests.test_catalog_api import FIXTURE_JSON, SAMPLE


def _ok(
    *,
    source_url: str,
    platform: str = "swiggy",
    restaurant_id: str | None = None,
    restaurant_name: str = "Harbor Spice House",
    categories: list | None = None,
) -> CatalogCreateResponse:
    restaurant: dict = {"name": restaurant_name}
    if restaurant_id:
        restaurant["restaurant_id"] = restaurant_id
    return CatalogCreateResponse(
        extraction_status="ok",
        restaurant_name=restaurant_name,
        fssai_number="12345678901234",
        source_url=source_url,
        platform=platform,  # type: ignore[arg-type]
        catalogue_type="restaurant",
        restaurant=restaurant,
        categories=categories or [{"name": "Mains", "items": [{"name": "Rice"}]}],
        item_count=1,
    )


def _non_ok(status: str, source_url: str, platform: str = "swiggy") -> CatalogCreateResponse:
    return CatalogCreateResponse(
        extraction_status=status,  # type: ignore[arg-type]
        restaurant_name="Harbor Spice House",
        fssai_number="12345678901234",
        source_url=source_url,
        platform=platform,  # type: ignore[arg-type]
        error=status,
    )


def test_same_org_same_canonical_url_reuses_id():
    url = "https://www.swiggy.com/city/sample/alpha-resta"
    first = save_catalogue(user_id="user-1", organization_id="org_1", result=_ok(source_url=url))
    second = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_ok(source_url=url + "/", categories=[{"name": "Updated", "items": []}]),
    )
    rows = list_catalogues("user-1", "org_1")
    assert first.id == second.id
    assert first.created_at == second.created_at
    assert len(rows) == 1
    assert rows[0].result.categories[0]["name"] == "Updated"


def test_same_org_different_url_without_restaurant_id_inserts():
    first = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_ok(source_url="https://www.swiggy.com/city/sample/alpha-resta"),
    )
    second = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_ok(source_url="https://www.swiggy.com/city/sample/beta-restb"),
    )
    assert first.id != second.id
    assert len(list_catalogues("user-1", "org_1")) == 2


def test_same_url_different_organization_inserts():
    url = "https://www.swiggy.com/city/sample/alpha-resta"
    first = save_catalogue(user_id="user-1", organization_id="org_a", result=_ok(source_url=url))
    second = save_catalogue(user_id="user-1", organization_id="org_b", result=_ok(source_url=url))
    assert first.id != second.id
    assert len(list_catalogues("user-1", "org_a")) == 1
    assert len(list_catalogues("user-1", "org_b")) == 1


def test_same_url_incompatible_platform_inserts():
    url = "https://www.swiggy.com/city/sample/alpha-resta"
    first = save_catalogue(
        user_id="user-1", organization_id="org_1", result=_ok(source_url=url, platform="swiggy")
    )
    second = save_catalogue(
        user_id="user-1", organization_id="org_1", result=_ok(source_url=url, platform="zomato")
    )
    assert first.id != second.id
    assert len(list_catalogues("user-1", "org_1")) == 2


def test_same_restaurant_id_different_url_reuses_id():
    first = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_ok(source_url="https://www.swiggy.com/city/sample/alpha-resta", restaurant_id="111"),
    )
    second = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_ok(source_url="https://www.swiggy.com/city/sample/alpha-alt-resta", restaurant_id="111"),
    )
    assert first.id == second.id
    assert len(list_catalogues("user-1", "org_1")) == 1


def test_same_name_different_url_and_id_does_not_merge():
    first = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_ok(
            source_url="https://www.swiggy.com/city/sample/alpha-one-resta",
            restaurant_id="1",
            restaurant_name="Alpha",
        ),
    )
    second = save_catalogue(
        user_id="user-1",
        organization_id="org_1",
        result=_ok(
            source_url="https://www.swiggy.com/city/sample/alpha-two-restb",
            restaurant_id="2",
            restaurant_name="Alpha",
        ),
    )
    assert first.id != second.id
    assert len(list_catalogues("user-1", "org_1")) == 2


def test_failed_blocked_pending_do_not_downgrade_ok_catalogue():
    url = "https://www.swiggy.com/city/sample/alpha-resta"
    ok = save_catalogue(user_id="user-1", organization_id="org_1", result=_ok(source_url=url))
    for status in ("failed", "blocked", "pending"):
        saved = save_catalogue(user_id="user-1", organization_id="org_1", result=_non_ok(status, url))
        assert saved.id != ok.id
        assert saved.result.extraction_status == status
    rows = list_catalogues("user-1", "org_1")
    ok_rows = [row for row in rows if row.result.extraction_status == "ok"]
    assert len(ok_rows) == 1
    assert ok_rows[0].id == ok.id
    assert ok_rows[0].result.item_count == 1
    assert ok_rows[0].result.restaurant is not None


def test_non_ok_direct_create_still_persists_status_row():
    url = "https://www.swiggy.com/city/sample/missing-resta"
    saved = save_catalogue(user_id="user-1", organization_id="org_1", result=_non_ok("failed", url))
    rows = list_catalogues("user-1", "org_1")
    assert len(rows) == 1
    assert rows[0].id == saved.id
    assert rows[0].result.extraction_status == "failed"


def test_concurrent_ok_saves_one_catalogue_row():
    url = "https://www.swiggy.com/city/sample/concurrent-resta"
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []
    saved: list[str] = []

    def worker() -> None:
        try:
            barrier.wait(timeout=5)
            stored = save_catalogue(
                user_id="user-1",
                organization_id="org_1",
                result=_ok(source_url=url, restaurant_id="777"),
            )
            saved.append(stored.id)
        except BaseException as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert errors == []
    rows = list_catalogues("user-1", "org_1")
    assert len(rows) == 1
    assert set(saved) == {rows[0].id}


def test_persistence_matcher_ignores_name_and_place():
    catalogues = [
        {
            "id": "cat-wrong",
            "result": {
                "platform": "swiggy",
                "extraction_status": "ok",
                "source_url": "https://www.swiggy.com/city/sample/alpha-resta",
                "restaurant": {"name": "Alpha", "outlet": "Sample Area", "restaurant_id": "1"},
            },
        }
    ]
    assert (
        matching_catalogue_id(
            catalogues,
            platform="swiggy",
            source_url="https://www.swiggy.com/city/sample/other-rest9",
            restaurant_id="9",
        )
        is None
    )


def test_api_repeated_ok_create_returns_same_catalogue_id():
    app.dependency_overrides[get_swiggy_access] = lambda: FixtureAccess(json_path=FIXTURE_JSON)
    app.dependency_overrides[require_session] = lambda: AuthUser(id="user_1", email="owner@example.com")
    payload = {**SAMPLE, "organization_id": "org_idem"}
    try:
        client = TestClient(app)
        first = client.post("/catalog/create", json=payload)
        second = client.post("/catalog/create", json=payload)
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["id"] == second.json()["id"]
        listed = client.get("/catalogues", params={"organization_id": "org_idem"}).json()["catalogues"]
        assert len(listed) == 1
    finally:
        app.dependency_overrides.clear()

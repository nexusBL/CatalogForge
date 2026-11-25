from pathlib import Path
import json
import re

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.main import app, get_swiggy_access, require_session
from backend.schemas import AuthUser, CatalogCreateRequest
from backend.services.catalog_service import (
    FixtureAccess,
    OfficialApiAccess,
    SwiggyAccess,
    create_catalog,
)
from scraper.swiggy.models import RawSource

FIXTURE_JSON = Path(__file__).parent / "fixtures" / "swiggy_menu_payload.json"
SAMPLE = {
    "restaurant_name": "Harbor Spice House",
    "fssai_number": "12345678901234",
    "swiggy_url": "https://www.swiggy.com/city/mangaluru/harbor-spice-house-rest999001",
    "organization_id": "org_1",
}


class UrlIdFixtureAccess(FixtureAccess):
    """Same menu fixture, but restaurant id follows restNNNN from the URL."""

    def load(self, swiggy_url: str):
        obtained = super().load(swiggy_url)
        match = re.search(r"rest(\d+)", swiggy_url)
        if not match or obtained.raw is None:
            return obtained
        rest_id = match.group(1)
        raw = obtained.raw
        if raw.next_data is not None:
            raw.next_data = json.loads(json.dumps(raw.next_data).replace("999001", rest_id))
        if raw.api_payloads:
            raw.api_payloads = json.loads(json.dumps(raw.api_payloads).replace("999001", rest_id))
        return obtained


class FakeAccess(SwiggyAccess):
    def __init__(self, result=None, error: Exception | None = None):
        self._result = result
        self._error = error

    def load(self, swiggy_url: str):
        if self._error:
            raise self._error
        return self._result


def test_valid_request_schema():
    request = CatalogCreateRequest.model_validate(SAMPLE)
    assert request.restaurant_name == "Harbor Spice House"
    assert "swiggy.com" in request.swiggy_url


def test_missing_swiggy_url_rejected():
    with pytest.raises(ValidationError):
        CatalogCreateRequest.model_validate(
            {
                "restaurant_name": "Harbor Spice House",
                "fssai_number": "12345678901234",
                "swiggy_url": "",
            }
        )
    client = TestClient(app)
    app.dependency_overrides[require_session] = lambda: AuthUser(id="user_1", email="owner@example.com")
    try:
        response = client.post(
            "/catalog/create",
            json={"restaurant_name": "Harbor Spice House", "fssai_number": "12345678901234"},
        )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_service_error_handling():
    request = CatalogCreateRequest.model_validate(SAMPLE)
    result = create_catalog(request, FakeAccess(error=RuntimeError("collector crashed")))
    assert result.extraction_status == "failed"
    assert result.item_count == 0
    assert result.categories == []
    assert "collector crashed" in (result.error or "")


def test_blocked_extraction_is_not_success():
    from backend.services.catalog_service import AccessResult

    request = CatalogCreateRequest.model_validate(SAMPLE)
    raw = RawSource(
        source_url=SAMPLE["swiggy_url"],
        blocked=True,
        access_status="blocked",
        http_status=403,
        reason="Swiggy/CloudFront denied the restaurant page (HTTP 403).",
    )
    result = create_catalog(request, FakeAccess(AccessResult(method="stage1_browser", raw=raw)))
    assert result.extraction_status == "blocked"
    assert result.restaurant is None
    assert result.categories == []
    assert result.item_count == 0
    assert result.error


def test_failed_extraction_is_not_success():
    from backend.services.catalog_service import AccessResult

    request = CatalogCreateRequest.model_validate(SAMPLE)
    raw = RawSource(source_url=SAMPLE["swiggy_url"], access_status="failed", reason="no menu payload")
    result = create_catalog(request, FakeAccess(AccessResult(method="stage1_browser", raw=raw)))
    assert result.extraction_status == "failed"
    assert result.item_count == 0
    assert result.categories == []


def test_successful_fixture_catalogue_generation():
    request = CatalogCreateRequest.model_validate(SAMPLE)
    result = create_catalog(request, FixtureAccess(json_path=FIXTURE_JSON))
    assert result.extraction_status == "ok"
    assert result.source_type == "xhr_json"
    assert result.restaurant is not None
    assert result.restaurant["name"] == "Harbor Spice House"
    assert result.item_count == 2
    assert result.image_count >= 2
    assert result.error is None


def test_ok_status_without_menu_is_rejected():
    from backend.services.catalog_service import AccessResult

    request = CatalogCreateRequest.model_validate(SAMPLE)
    empty = RawSource(source_url=SAMPLE["swiggy_url"], access_status="ok", html="<html></html>")
    result = create_catalog(request, FakeAccess(AccessResult(method="catalogforge_chrome_cdp", raw=empty)))
    assert result.extraction_status == "failed"
    assert result.item_count == 0
    assert result.restaurant is None


def test_official_api_without_credentials_is_pending():
    request = CatalogCreateRequest.model_validate(SAMPLE)
    result = create_catalog(request, OfficialApiAccess())
    assert result.extraction_status == "pending"
    assert result.item_count == 0
    assert result.categories == []
    assert result.error


def test_api_fixture_success_via_dependency(tmp_path):
    app.dependency_overrides[get_swiggy_access] = lambda: FixtureAccess(json_path=FIXTURE_JSON)
    app.dependency_overrides[require_session] = lambda: AuthUser(id="user_1", email="owner@example.com")
    try:
        client = TestClient(app)
        response = client.post("/catalog/create", json=SAMPLE)
        assert response.status_code == 200
        body = response.json()
        assert body["extraction_status"] == "ok"
        assert body["item_count"] == 2
        assert body["restaurant"]["name"] == "Harbor Spice House"
    finally:
        app.dependency_overrides.clear()


def test_invalid_swiggy_url_is_rejected():
    app.dependency_overrides[require_session] = lambda: AuthUser(id="user_1", email="owner@example.com")
    try:
        client = TestClient(app)
        response = client.post(
            "/catalog/create",
            json={
                "restaurant_name": "Harbor Spice House",
                "fssai_number": "12345678901234",
                "swiggy_url": "https://example.com/not-swiggy",
                "organization_id": "org_1",
            },
        )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_authenticated_create_stores_and_retrieves_for_organization():
    app.dependency_overrides[get_swiggy_access] = lambda: FixtureAccess(json_path=FIXTURE_JSON)
    app.dependency_overrides[require_session] = lambda: AuthUser(id="user_1", email="owner@example.com")
    payload = {**SAMPLE, "organization_id": "org_harbor"}
    try:
        client = TestClient(app)
        created = client.post("/catalog/create", json=payload)
        assert created.status_code == 200
        body = created.json()
        assert body["extraction_status"] == "ok"
        assert body["id"]
        assert body["organization_id"] == "org_harbor"
        catalogue_id = body["id"]

        listed = client.get("/catalogues", params={"organization_id": "org_harbor"})
        assert listed.status_code == 200
        catalogues = listed.json()["catalogues"]
        assert len(catalogues) == 1
        assert catalogues[0]["id"] == catalogue_id
        assert catalogues[0]["organization_id"] == "org_harbor"
        assert catalogues[0]["result"]["restaurant"]["name"] == "Harbor Spice House"

        fetched = client.get(f"/catalogues/{catalogue_id}", params={"organization_id": "org_harbor"})
        assert fetched.status_code == 200
        assert fetched.json()["result"]["item_count"] == 2
        assert fetched.json()["result"]["categories"]
    finally:
        app.dependency_overrides.clear()


def test_delete_catalogue_removes_only_that_catalogue():
    app.dependency_overrides[get_swiggy_access] = lambda: UrlIdFixtureAccess(json_path=FIXTURE_JSON)
    app.dependency_overrides[require_session] = lambda: AuthUser(id="user_1", email="owner@example.com")
    try:
        client = TestClient(app)
        first = client.post("/catalog/create", json={**SAMPLE, "organization_id": "org_harbor"}).json()
        second = client.post(
            "/catalog/create",
            json={
                **SAMPLE,
                "organization_id": "org_harbor",
                "swiggy_url": "https://www.swiggy.com/city/mangaluru/other-harbor-house-rest999002",
            },
        ).json()
        deleted = client.delete(f"/catalogues/{first['id']}", params={"organization_id": "org_harbor"})
        assert deleted.status_code == 200
        assert deleted.json()["ok"] is True
        listed = client.get("/catalogues", params={"organization_id": "org_harbor"}).json()["catalogues"]
        ids = {item["id"] for item in listed}
        assert first["id"] not in ids
        assert second["id"] in ids
        missing = client.delete(f"/catalogues/{first['id']}", params={"organization_id": "org_harbor"})
        assert missing.status_code == 404
        wrong_org = client.delete(f"/catalogues/{second['id']}", params={"organization_id": "org_other"})
        assert wrong_org.status_code == 404
        still_there = client.get(f"/catalogues/{second['id']}", params={"organization_id": "org_harbor"})
        assert still_there.status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_catalogue_does_not_belong_to_another_organization():
    app.dependency_overrides[get_swiggy_access] = lambda: FixtureAccess(json_path=FIXTURE_JSON)
    app.dependency_overrides[require_session] = lambda: AuthUser(id="user_1", email="owner@example.com")
    try:
        client = TestClient(app)
        created = client.post("/catalog/create", json={**SAMPLE, "organization_id": "org_a"})
        catalogue_id = created.json()["id"]
        wrong_list = client.get("/catalogues", params={"organization_id": "org_b"})
        assert wrong_list.status_code == 200
        assert wrong_list.json()["catalogues"] == []
        wrong_get = client.get(f"/catalogues/{catalogue_id}", params={"organization_id": "org_b"})
        assert wrong_get.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_api_blocked_scraper_result_is_stored_as_blocked():
    from backend.services.catalog_service import AccessResult

    class BlockedAccess(SwiggyAccess):
        def load(self, swiggy_url: str):
            return AccessResult(
                method="stage1_browser",
                raw=RawSource(
                    source_url=swiggy_url,
                    blocked=True,
                    access_status="blocked",
                    http_status=403,
                    reason="Swiggy/CloudFront denied the restaurant page (HTTP 403).",
                ),
            )

    app.dependency_overrides[get_swiggy_access] = lambda: BlockedAccess()
    app.dependency_overrides[require_session] = lambda: AuthUser(id="user_1", email="owner@example.com")
    try:
        client = TestClient(app)
        response = client.post("/catalog/create", json={**SAMPLE, "organization_id": "org_1"})
        assert response.status_code == 200
        body = response.json()
        assert body["extraction_status"] == "blocked"
        assert body["restaurant"] is None
        assert body["categories"] == []
        assert body["item_count"] == 0
        fetched = client.get(f"/catalogues/{body['id']}", params={"organization_id": "org_1"})
        assert fetched.json()["result"]["extraction_status"] == "blocked"
        assert fetched.json()["result"]["categories"] == []
    finally:
        app.dependency_overrides.clear()


def test_api_failed_scraper_result_is_not_success():
    from backend.services.catalog_service import AccessResult

    class FailedAccess(SwiggyAccess):
        def load(self, swiggy_url: str):
            return AccessResult(
                method="stage1_browser",
                raw=RawSource(source_url=swiggy_url, access_status="failed", reason="no menu payload"),
            )

    app.dependency_overrides[get_swiggy_access] = lambda: FailedAccess()
    app.dependency_overrides[require_session] = lambda: AuthUser(id="user_1", email="owner@example.com")
    try:
        client = TestClient(app)
        response = client.post("/catalog/create", json={**SAMPLE, "organization_id": "org_1"})
        assert response.status_code == 200
        body = response.json()
        assert body["extraction_status"] == "failed"
        assert body["item_count"] == 0
        assert body["categories"] == []
        listed = client.get("/catalogues", params={"organization_id": "org_1"})
        assert listed.json()["catalogues"][0]["result"]["extraction_status"] == "failed"
    finally:
        app.dependency_overrides.clear()


def test_catalogue_list_requires_authentication():
    client = TestClient(app)
    response = client.get("/catalogues", params={"organization_id": "org_1"})
    assert response.status_code == 401


def test_dineout_request_does_not_require_fssai():
    request = CatalogCreateRequest.model_validate(
        {
            "restaurant_name": "Daffy's Brewgarden",
            "swiggy_url": "https://www.swiggy.com/restaurants/daffys/dineout",
            "catalogue_type": "dineout",
            "organization_id": "org_1",
        }
    )
    assert request.fssai_number == ""
    assert request.catalogue_type == "dineout"


def test_restaurant_request_still_requires_fssai():
    with pytest.raises(ValidationError):
        CatalogCreateRequest.model_validate(
            {
                "restaurant_name": "Harbor Spice House",
                "swiggy_url": SAMPLE["swiggy_url"],
                "catalogue_type": "restaurant",
            }
        )


def test_both_request_requires_dineout_url():
    with pytest.raises(ValidationError):
        CatalogCreateRequest.model_validate({**SAMPLE, "catalogue_type": "both"})


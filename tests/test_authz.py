from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.authz import _load_organization_ids as _REAL_LOAD_ORGANIZATION_IDS
from backend.authz import parse_organization_ids, require_organization_member
from backend.main import _assets, app, get_swiggy_access, require_session
from backend.schemas import AuthUser, CatalogCreateResponse
from backend.services.catalog_service import FixtureAccess
from backend.store import save_area_job, save_catalogue

FIXTURE_JSON = Path(__file__).parent / "fixtures" / "swiggy_menu_payload.json"
OWN = "org_a"
FOREIGN = "org_b"
SAMPLE = {
    "restaurant_name": "Harbor Spice House",
    "fssai_number": "12345678901234",
    "swiggy_url": "https://www.swiggy.com/city/mangaluru/harbor-spice-house-rest999001",
    "organization_id": OWN,
}


class FakeState:
    pass


class FakeRequest:
    def __init__(self, headers: dict[str, str] | None = None):
        self.headers = headers or {"cookie": "better-auth.session_token=test"}
        self.state = FakeState()


def _restrict(monkeypatch, org_ids: set[str]):
    calls = {"n": 0}

    def fake_load(request, user):
        calls["n"] += 1
        return set(org_ids)

    monkeypatch.setattr("backend.authz._load_organization_ids", fake_load)
    return calls


def _auth(user_id: str = "user_1"):
    app.dependency_overrides[require_session] = lambda: AuthUser(id=user_id, email="owner@example.com")
    app.dependency_overrides[get_swiggy_access] = lambda: FixtureAccess(json_path=FIXTURE_JSON)


def _ok_result(source_url: str) -> CatalogCreateResponse:
    return CatalogCreateResponse(
        extraction_status="ok",
        restaurant_name="Harbor Spice House",
        fssai_number="12345678901234",
        source_url=source_url,
        platform="swiggy",
        catalogue_type="restaurant",
        restaurant={"name": "Harbor Spice House", "restaurant_id": "rest999001"},
        categories=[],
        item_count=0,
        image_count=0,
    )


def test_parse_better_auth_organization_list_array():
    ids = parse_organization_ids(
        [
            {"id": "org_a", "name": "Harbor", "slug": "harbor"},
            {"id": "org_b", "role": "member"},
        ]
    )
    assert ids == {"org_a", "org_b"}


def test_parse_wrapped_organization_list():
    assert parse_organization_ids({"data": [{"organizationId": "org_x"}]}) == {"org_x"}


def test_malformed_organization_list_json_typeerror_is_401(monkeypatch):
    class FakeResponse:
        status_code = 200

        def json(self):
            raise TypeError("not json")

    monkeypatch.setattr("backend.authz.httpx.get", lambda *args, **kwargs: FakeResponse())
    monkeypatch.setattr("backend.authz._load_organization_ids", _REAL_LOAD_ORGANIZATION_IDS)
    try:
        _REAL_LOAD_ORGANIZATION_IDS(FakeRequest(), AuthUser(id="user_1", email="owner@example.com"))
        raise AssertionError("expected HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 401
        assert exc.detail == "Not authenticated"
        assert "not json" not in str(exc.detail)


def test_unauthenticated_protected_endpoint_is_401():
    client = TestClient(app)
    response = client.get("/catalogues", params={"organization_id": OWN})
    assert response.status_code == 401


def test_missing_organization_id_on_create_is_422():
    _auth()
    try:
        client = TestClient(app)
        response = client.post(
            "/catalog/create",
            json={
                "restaurant_name": "Harbor Spice House",
                "fssai_number": "12345678901234",
                "swiggy_url": SAMPLE["swiggy_url"],
            },
        )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_member_own_organization_succeeds(monkeypatch):
    _restrict(monkeypatch, {OWN})
    _auth()
    try:
        client = TestClient(app)
        created = client.post("/catalog/create", json=SAMPLE)
        assert created.status_code == 200, created.text
        listed = client.get("/catalogues", params={"organization_id": OWN})
        assert listed.status_code == 200
        assert len(listed.json()["catalogues"]) == 1
    finally:
        app.dependency_overrides.clear()


def test_non_member_organization_is_403(monkeypatch):
    _restrict(monkeypatch, {OWN})
    _auth()
    try:
        client = TestClient(app)
        listed = client.get("/catalogues", params={"organization_id": FOREIGN})
        assert listed.status_code == 403
        assert listed.json()["detail"] == "Not authorized for this organization."
    finally:
        app.dependency_overrides.clear()


def test_foreign_organization_cannot_create(monkeypatch):
    _restrict(monkeypatch, {OWN})
    _auth()
    try:
        client = TestClient(app)
        response = client.post("/catalog/create", json={**SAMPLE, "organization_id": FOREIGN})
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_foreign_organization_cannot_list_or_get_or_delete(monkeypatch):
    _restrict(monkeypatch, {OWN})
    _auth()
    try:
        client = TestClient(app)
        created = client.post("/catalog/create", json=SAMPLE)
        assert created.status_code == 200
        catalogue_id = created.json()["id"]
        assert client.get("/catalogues", params={"organization_id": FOREIGN}).status_code == 403
        assert client.get(f"/catalogues/{catalogue_id}", params={"organization_id": FOREIGN}).status_code == 403
        assert client.delete(f"/catalogues/{catalogue_id}", params={"organization_id": FOREIGN}).status_code == 403
        still = client.get(f"/catalogues/{catalogue_id}", params={"organization_id": OWN})
        assert still.status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_foreign_organization_cannot_create_or_mutate_area_jobs(monkeypatch):
    _restrict(monkeypatch, {OWN})
    _auth()
    job = save_area_job(
        user_id="user_1",
        organization_id=OWN,
        payload={
            "id": "job_own",
            "organization_id": OWN,
            "status": "awaiting_confirmation",
            "venues": [],
            "platforms": ["swiggy"],
            "catalogue_type": "restaurant",
        },
    )
    try:
        client = TestClient(app)
        created = client.post(
            "/area-jobs",
            json={
                "location": "Indiranagar, Bengaluru",
                "platforms": ["swiggy"],
                "catalogue_type": "restaurant",
                "organization_id": FOREIGN,
            },
        )
        assert created.status_code == 403
        job_id = job["id"]
        assert client.get("/area-jobs", params={"organization_id": FOREIGN}).status_code == 403
        assert client.get(f"/area-jobs/{job_id}", params={"organization_id": FOREIGN}).status_code == 403
        assert (
            client.post(f"/area-jobs/{job_id}/start", json={"organization_id": FOREIGN}).status_code == 403
        )
        assert (
            client.post(f"/area-jobs/{job_id}/scrape-batch", json={"organization_id": FOREIGN}).status_code == 403
        )
        assert client.post(f"/area-jobs/{job_id}/cancel", json={"organization_id": FOREIGN}).status_code == 403
        assert client.delete(f"/area-jobs/{job_id}", params={"organization_id": FOREIGN}).status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_member_cannot_access_another_users_catalogue(monkeypatch):
    _restrict(monkeypatch, {OWN})
    _auth("user_1")
    other = save_catalogue(
        user_id="user_other",
        organization_id=OWN,
        result=_ok_result("https://www.swiggy.com/city/mangaluru/other-rest1"),
    )
    try:
        client = TestClient(app)
        fetched = client.get(f"/catalogues/{other.id}", params={"organization_id": OWN})
        assert fetched.status_code == 404
        deleted = client.delete(f"/catalogues/{other.id}", params={"organization_id": OWN})
        assert deleted.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_member_cannot_access_another_users_job(monkeypatch):
    _restrict(monkeypatch, {OWN})
    _auth("user_1")
    save_area_job(
        user_id="user_other",
        organization_id=OWN,
        payload={
            "id": "job_other",
            "organization_id": OWN,
            "status": "queued",
            "venues": [],
            "platforms": ["swiggy"],
            "catalogue_type": "restaurant",
        },
    )
    try:
        client = TestClient(app)
        assert client.get("/area-jobs/job_other", params={"organization_id": OWN}).status_code == 404
        assert client.post("/area-jobs/job_other/start", json={"organization_id": OWN}).status_code == 404
        assert client.post("/area-jobs/job_other/scrape-batch", json={"organization_id": OWN}).status_code == 404
        assert client.post("/area-jobs/job_other/cancel", json={"organization_id": OWN}).status_code == 404
        assert client.delete("/area-jobs/job_other", params={"organization_id": OWN}).status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_membership_lookup_happens_once_per_request(monkeypatch):
    calls = _restrict(monkeypatch, {OWN})
    user = AuthUser(id="user_1", email="a@b.c")
    request = FakeRequest()
    require_organization_member(request, user, OWN)
    require_organization_member(request, user, OWN)
    assert calls["n"] == 1


def test_unauthenticated_catalogue_asset_is_public():
    dest = _assets / "pub-cat" / "hero.img"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"public-image")
    try:
        client = TestClient(app)
        response = client.get("/catalogue-assets/pub-cat/hero.img")
        assert response.status_code == 200
        assert response.content == b"public-image"
    finally:
        dest.unlink(missing_ok=True)

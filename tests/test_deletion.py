from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import app, get_swiggy_access, require_session
from backend.schemas import AuthUser
from backend.store import get_area_job, get_catalogue, list_area_jobs
from backend.services.catalog_service import FixtureAccess
from tests.test_catalog_api import UrlIdFixtureAccess
from scraper.discovery.locate import LocationSelectionError
from scraper.discovery.models import ListingPage
from scraper.discovery.runner import discover_location
from scraper.swiggy.assets import remove_owned_catalogue_assets

FIXTURE_JSON = Path(__file__).parent / "fixtures" / "swiggy_menu_payload.json"
SAMPLE = {
    "restaurant_name": "Harbor Spice House",
    "fssai_number": "12345678901234",
    "swiggy_url": "https://www.swiggy.com/city/mangaluru/harbor-spice-house-rest999001",
    "organization_id": "org_harbor",
}


def test_delete_failed_discovery_job_removes_job_not_catalogue(monkeypatch):
    app.dependency_overrides[require_session] = lambda: AuthUser(id="user_1", email="a@b.c")
    app.dependency_overrides[get_swiggy_access] = lambda: FixtureAccess(json_path=FIXTURE_JSON)
    client = TestClient(app)
    try:
        created = client.post("/catalog/create", json=SAMPLE).json()
        catalogue_id = created["id"]

        def boom(*_args, **_kwargs):
            raise LocationSelectionError("Location selection failed: header still Indiranagar")

        monkeypatch.setattr("backend.services.area_service.discover_location", boom)
        monkeypatch.setattr(
            "backend.services.area_service.resolve_location",
            lambda query, geocoder=None: __import__("scraper.discovery.location", fromlist=["parse_location"]).parse_location(query),
        )
        failed = client.post(
            "/area-jobs",
            json={
                "location": "JP Nagar, Bengaluru, Karnataka",
                "platforms": ["swiggy"],
                "catalogue_type": "restaurant",
                "organization_id": "org_harbor",
            },
        )
        assert failed.status_code == 200, failed.text
        job = failed.json()
        assert job["status"] == "failed"
        job_id = job["id"]

        other = client.post(
            "/area-jobs",
            json={
                "location": "Keep me",
                "platforms": ["swiggy"],
                "catalogue_type": "restaurant",
                "organization_id": "org_harbor",
            },
        ).json()

        deleted = client.delete(f"/area-jobs/{job_id}", params={"organization_id": "org_harbor"})
        assert deleted.status_code == 200
        assert deleted.json()["ok"] is True
        assert get_area_job("user_1", job_id, "org_harbor") is None
        remaining = {item["id"] for item in list_area_jobs("user_1", "org_harbor")}
        assert job_id not in remaining
        assert other["id"] in remaining
        listed = client.get("/area-jobs", params={"organization_id": "org_harbor"}).json()["jobs"]
        assert job_id not in {item["id"] for item in listed}
        still = client.get(f"/catalogues/{catalogue_id}", params={"organization_id": "org_harbor"})
        assert still.status_code == 200
        assert get_catalogue("user_1", catalogue_id, "org_harbor") is not None
        missing = client.delete(f"/area-jobs/{job_id}", params={"organization_id": "org_harbor"})
        assert missing.status_code == 404
        wrong = client.delete(f"/area-jobs/{other['id']}", params={"organization_id": "org_other"})
        assert wrong.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_permanent_catalogue_delete_removes_owned_assets_only(tmp_path, monkeypatch):
    monkeypatch.setenv("CATALOGFORGE_DOWNLOAD_IMAGES", "0")
    monkeypatch.setenv("CATALOGFORGE_ASSETS_DIR", str(tmp_path / "assets"))
    app.dependency_overrides[require_session] = lambda: AuthUser(id="user_1", email="a@b.c")
    app.dependency_overrides[get_swiggy_access] = lambda: UrlIdFixtureAccess(json_path=FIXTURE_JSON)
    client = TestClient(app)
    try:
        first = client.post("/catalog/create", json=SAMPLE).json()
        second = client.post(
            "/catalog/create",
            json={
                **SAMPLE,
                "swiggy_url": "https://www.swiggy.com/city/mangaluru/other-harbor-house-rest999002",
            },
        ).json()
        owned = tmp_path / "assets" / first["id"]
        other = tmp_path / "assets" / second["id"]
        owned.mkdir(parents=True, exist_ok=True)
        other.mkdir(parents=True, exist_ok=True)
        (owned / "hero.img").write_bytes(b"one")
        (other / "hero.img").write_bytes(b"two")
        deleted = client.delete(f"/catalogues/{first['id']}", params={"organization_id": "org_harbor"})
        assert deleted.status_code == 200
        assert not owned.exists()
        assert other.exists()
        assert get_catalogue("user_1", first["id"], "org_harbor") is None
        assert get_catalogue("user_1", second["id"], "org_harbor") is not None
        leftover = client.get("/area-jobs", params={"organization_id": "org_harbor"}).json()["jobs"]
        assert leftover == []
    finally:
        app.dependency_overrides.clear()


def test_remove_owned_assets_does_not_escape_root(tmp_path, monkeypatch):
    monkeypatch.setenv("CATALOGFORGE_ASSETS_DIR", str(tmp_path / "assets"))
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("keep", encoding="utf-8")
    remove_owned_catalogue_assets("../outside")
    assert (outside / "keep.txt").exists()


def test_unverified_location_does_not_discover_venues():
    html = '<a href="/city/bangalore/pizza-rest10584">Pizza</a>'

    def fetch(_url: str) -> ListingPage:
        return ListingPage(
            url="https://www.swiggy.com/restaurants",
            html=html,
            error="Location selection failed: requested JP Nagar, still showing Indiranagar",
        )

    try:
        discover_location("JP Nagar, Bengaluru, Karnataka", ["swiggy"], "restaurant", fetch)
        raise AssertionError("expected LocationSelectionError")
    except LocationSelectionError:
        pass

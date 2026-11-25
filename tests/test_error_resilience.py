from __future__ import annotations

from http.client import IncompleteRead
from pathlib import Path
from urllib.request import Request

import httpx
from fastapi.testclient import TestClient

from backend.main import app, get_swiggy_access, require_session
from backend.schemas import AuthUser, CatalogCreateRequest, CatalogCreateResponse
from backend.services.area_service import scrape_area_batch
from backend.services.catalog_service import AccessResult, SwiggyAccess, create_catalog
from backend.store import get_area_job, merge_area_job_venue
from scraper.discovery.locate import LocationSelectionError
from scraper.discovery.models import ListingPage
from scraper.discovery.runner import discover_location
from scraper.discovery.urls import SWIGGY_RESTAURANTS
from scraper.swiggy.assets import materialize_catalogue_images
from scraper.swiggy.models import RawSource
from scraper.swiggy.safe_fetch import fetch_public_http_bytes
from tests.test_area_job_crash_recovery import _simulate_restart
from tests.test_area_scrape_claim import _ok, _save_job, _venue
from tests.test_discovery import MapAccess, _page
from tests.test_ssrf import resolve_to

SAMPLE = {
    "restaurant_name": "Harbor Spice House",
    "fssai_number": "12345678901234",
    "swiggy_url": "https://www.swiggy.com/city/mangaluru/harbor-spice-house-rest999001",
    "organization_id": "org_1",
}


class FakeAccess(SwiggyAccess):
    def load(self, swiggy_url: str):
        return AccessResult(
            method="local_fixture",
            raw=RawSource(source_url=swiggy_url, access_status="ok", html="<html></html>"),
        )


def test_parser_exception_becomes_failed_result(monkeypatch):
    def boom(raw):
        raise TypeError("malformed menu node")

    monkeypatch.setattr("backend.services.catalog_service.parse_swiggy_catalogue", boom)
    request = CatalogCreateRequest.model_validate(SAMPLE)
    result = create_catalog(request, FakeAccess())
    assert result.extraction_status == "failed"
    assert result.item_count == 0
    assert "malformed menu node" in (result.error or "")


def test_parser_exception_does_not_500(monkeypatch):
    def boom(raw):
        raise TypeError("malformed menu node")

    monkeypatch.setattr("backend.services.catalog_service.parse_swiggy_catalogue", boom)
    app.dependency_overrides[require_session] = lambda: AuthUser(id="user_1", email="owner@example.com")
    app.dependency_overrides[get_swiggy_access] = lambda: FakeAccess()
    try:
        client = TestClient(app)
        response = client.post("/catalog/create", json=SAMPLE)
        assert response.status_code == 200
        body = response.json()
        assert body["extraction_status"] == "failed"
        assert body["item_count"] == 0
    finally:
        app.dependency_overrides.clear()


def test_persist_failure_is_generic_500_not_extraction_failed(monkeypatch):
    app.dependency_overrides[require_session] = lambda: AuthUser(id="user_1", email="owner@example.com")
    app.dependency_overrides[get_swiggy_access] = lambda: FakeAccess()

    def boom(*args, **kwargs):
        raise RuntimeError("sqlite disk I/O error at C:\\secret\\catalogues.sqlite")

    monkeypatch.setattr("backend.main.save_catalogue", boom)
    monkeypatch.setattr(
        "backend.main.create_catalog",
        lambda request, access: CatalogCreateResponse(
            extraction_status="ok",
            restaurant_name=request.restaurant_name,
            fssai_number=request.fssai_number or "",
            source_url=request.swiggy_url,
            platform="swiggy",
            catalogue_type="restaurant",
            restaurant={"name": request.restaurant_name},
        ),
    )
    try:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/catalog/create", json=SAMPLE)
        assert response.status_code == 500
        body = response.json()
        assert body == {"detail": "Internal server error"}
        assert "sqlite" not in response.text.lower()
        assert "secret" not in response.text
    finally:
        app.dependency_overrides.clear()


def test_claimed_venue_unexpected_exception_retries_then_fails(monkeypatch):
    monkeypatch.setattr(
        "backend.services.area_service.platform_url_error",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("unexpected claim work")),
    )
    job = _save_job(venues=[_venue("a")])
    payload = get_area_job("user-1", job["id"], "org_1")
    assert payload is not None
    payload["options"]["max_retries"] = 1
    from backend.store import update_area_job

    update_area_job(user_id="user-1", payload=payload)
    first = scrape_area_batch(user_id="user-1", organization_id="org_1", job_id=job["id"], access=MapAccess({}))
    assert first["venues"][0]["status"] == "queued"
    assert "unexpected claim work" in (first["venues"][0]["error"] or "")
    from datetime import datetime, timedelta, timezone

    monkeypatch.setattr(
        "scraper.discovery.queue.utcnow",
        lambda: (datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat(),
    )
    second = scrape_area_batch(user_id="user-1", organization_id="org_1", job_id=job["id"], access=MapAccess({}))
    assert second["venues"][0]["status"] == "failed"
    assert second["venues"][0]["status"] != "scraping"


def test_mkdir_failure_keeps_source_url(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CATALOGFORGE_DOWNLOAD_IMAGES", "1")
    monkeypatch.setenv("CATALOGFORGE_ASSETS_DIR", str(tmp_path))
    payload = {"dineout": {"hero_image": "https://cdn.example/hero.jpg"}}

    def boom(self, *args, **kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "mkdir", boom)
    materialize_catalogue_images(payload, "cat-mkdir", fetch=lambda _url: b"bytes")
    assert payload["dineout"]["hero_image"] == "https://cdn.example/hero.jpg"


def test_write_failure_keeps_source_url(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CATALOGFORGE_DOWNLOAD_IMAGES", "1")
    monkeypatch.setenv("CATALOGFORGE_ASSETS_DIR", str(tmp_path))
    payload = {"dineout": {"hero_image": "https://cdn.example/hero.jpg"}}

    def boom(self, data):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_bytes", boom)
    materialize_catalogue_images(payload, "cat-write", fetch=lambda _url: b"bytes")
    assert payload["dineout"]["hero_image"] == "https://cdn.example/hero.jpg"


def test_incomplete_read_returns_none():
    def open_url(request: Request, timeout: float):
        raise IncompleteRead(b"partial")

    assert (
        fetch_public_http_bytes(
            "https://cdn.example/hero.jpg",
            resolver=resolve_to("93.184.216.34"),
            open_url=open_url,
        )
        is None
    )


def test_auth_httpx_failure_is_generic_401(monkeypatch):
    def boom(*args, **kwargs):
        raise httpx.ConnectError("connection to host.internal:3001 failed")

    monkeypatch.setattr("backend.session.httpx.get", boom)
    client = TestClient(app)
    response = client.post("/catalog/create", json=SAMPLE, headers={"cookie": "better-auth.session_token=x"})
    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication service unavailable"}
    assert "host.internal" not in response.text
    assert "3001" not in response.text
    assert "ConnectError" not in response.text


def test_malformed_auth_json_is_401(monkeypatch):
    class FakeResponse:
        status_code = 200

        def json(self):
            raise ValueError("Expecting value")

    monkeypatch.setattr("backend.session.httpx.get", lambda *args, **kwargs: FakeResponse())
    client = TestClient(app)
    response = client.post("/catalog/create", json=SAMPLE, headers={"cookie": "better-auth.session_token=x"})
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


def test_http_exception_is_not_rewritten_to_500():
    client = TestClient(app)
    response = client.post("/catalog/create", json=SAMPLE)
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


def test_discovery_continues_when_one_platform_fetch_fails():
    def fetch(url: str) -> ListingPage:
        if "swiggy" in url:
            raise RuntimeError("swiggy listing crashed")
        if url.startswith("https://www.zomato.com"):
            return _page("discovery_zomato_page1.html", url)
        return ListingPage(url=url, html="", exhausted=True)

    _location, venues = discover_location("Sample Area", ["swiggy", "zomato"], "restaurant", fetch)
    assert any(item.platform == "zomato" for item in venues)
    assert not any(item.platform == "swiggy" for item in venues)


def test_discovery_continues_when_one_page_parse_fails(monkeypatch):
    from scraper.discovery.swiggy import SwiggyDiscovery

    original = SwiggyDiscovery.parse_page

    def parse_page(self, page, catalogue_type):
        if "page=2" in (page.url or ""):
            raise TypeError("bad listing cards")
        return original(self, page, catalogue_type)

    monkeypatch.setattr(SwiggyDiscovery, "parse_page", parse_page)

    def fetch(url: str) -> ListingPage:
        if url == SWIGGY_RESTAURANTS:
            return _page("discovery_swiggy_page1.html", url)
        if url == f"{SWIGGY_RESTAURANTS}?page=2":
            return _page("discovery_swiggy_page2.html", url)
        return ListingPage(url=url, html="", exhausted=True)

    _location, venues = discover_location("Sample Area", ["swiggy"], "restaurant", fetch)
    assert {item.venue_id for item in venues} >= {"111", "222"}
    assert "444" not in {item.venue_id for item in venues}


def test_location_selection_error_still_aborts_discovery():
    def fetch(url: str) -> ListingPage:
        return ListingPage(url=url, html="", error="Location selection failed: header still Indiranagar")

    try:
        discover_location("Sample Area", ["swiggy"], "restaurant", fetch)
        raise AssertionError("expected LocationSelectionError")
    except LocationSelectionError:
        pass


def test_merge_failure_leaves_recoverable_scraping_state(monkeypatch):
    monkeypatch.setattr("backend.services.area_service.create_catalog", lambda request, access: _ok(request))

    def boom(**kwargs):
        raise RuntimeError("merge boom")

    monkeypatch.setattr("backend.services.area_service.merge_area_job_venue", boom)
    job = _save_job(venues=[_venue("a")])
    result = scrape_area_batch(user_id="user-1", organization_id="org_1", job_id=job["id"], access=MapAccess({}))
    assert result["venues"][0]["status"] == "scraping"
    _simulate_restart(monkeypatch)
    monkeypatch.setattr(
        "backend.services.area_service.merge_area_job_venue",
        lambda **kwargs: merge_area_job_venue(**kwargs),
    )
    recovered = scrape_area_batch(user_id="user-1", organization_id="org_1", job_id=job["id"], access=MapAccess({}))
    assert recovered["venues"][0]["status"] == "completed"

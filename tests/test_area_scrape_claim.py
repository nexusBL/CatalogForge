from __future__ import annotations

import threading
import uuid
from datetime import datetime, timedelta, timezone

from backend.schemas import CatalogCreateRequest, CatalogCreateResponse
from backend.services.area_service import cancel_area_job, scrape_area_batch
from backend.store import claim_area_scrape_batch, get_area_job, save_area_job
from scraper.discovery.queue import (
    DEFAULT_STALE_SCRAPE_CLAIM_SECONDS,
    claim_next_batch,
    job_from_dict,
    stale_scrape_claim_seconds,
)
from tests.test_discovery import MapAccess


def _ok(request: CatalogCreateRequest) -> CatalogCreateResponse:
    return CatalogCreateResponse(
        extraction_status="ok",
        restaurant_name=request.restaurant_name,
        fssai_number="",
        source_url=request.swiggy_url,
        platform="swiggy",
        catalogue_type="restaurant",
        restaurant={"name": request.restaurant_name},
    )


def _venue(suffix: str, *, status: str = "queued", started: str | None = None) -> dict:
    return {
        "platform": "swiggy",
        "catalogue_type": "restaurant",
        "venue_url": f"https://www.swiggy.com/city/sample/{suffix}-rest{suffix}",
        "venue_id": suffix,
        "name": suffix,
        "identity_key": f"swiggy:restaurant:id:{suffix}",
        "selected": True,
        "status": status,
        "scraping_started_at": started,
    }


def _save_job(*, concurrency: int = 1, venues: list[dict], status: str = "scraping") -> dict:
    payload = {
        "id": str(uuid.uuid4()),
        "organization_id": "org_1",
        "location": {"original": "Sample Area", "normalized": "Sample Area"},
        "platforms": ["swiggy"],
        "catalogue_type": "restaurant",
        "status": status,
        "created_at": "2026-01-01T00:00:00+00:00",
        "started_at": "2026-01-01T00:00:00+00:00",
        "options": {"concurrency": concurrency, "max_retries": 0},
        "venues": venues,
    }
    return save_area_job(user_id="user-1", organization_id="org_1", payload=payload)


def test_stale_threshold_constant_defaults_to_300_seconds(monkeypatch):
    monkeypatch.delenv("CATALOGFORGE_STALE_SCRAPE_CLAIM_SECONDS", raising=False)
    assert DEFAULT_STALE_SCRAPE_CLAIM_SECONDS == 300.0
    assert stale_scrape_claim_seconds() == 300.0
    monkeypatch.setenv("CATALOGFORGE_STALE_SCRAPE_CLAIM_SECONDS", "15")
    assert stale_scrape_claim_seconds() == 15.0


def test_fresh_scraping_claim_is_not_reclaimed():
    now = datetime.now(timezone.utc).isoformat()
    job = job_from_dict(
        {
            "id": "job-fresh",
            "organization_id": "org_1",
            "location": {"original": "x", "normalized": "x"},
            "platforms": ["swiggy"],
            "catalogue_type": "restaurant",
            "status": "scraping",
            "options": {"concurrency": 1},
            "venues": [_venue("a", status="scraping", started=now), _venue("b")],
        }
    )
    claimed = claim_next_batch(job, now=now)
    assert claimed == []
    assert job.venues[0].status == "scraping"
    assert job.venues[1].status == "queued"


def test_stale_scraping_claim_is_reclaimed(monkeypatch):
    monkeypatch.setenv("CATALOGFORGE_STALE_SCRAPE_CLAIM_SECONDS", "300")
    now = datetime.now(timezone.utc)
    stale = (now - timedelta(seconds=301)).isoformat()
    job = job_from_dict(
        {
            "id": "job-stale",
            "organization_id": "org_1",
            "location": {"original": "x", "normalized": "x"},
            "platforms": ["swiggy"],
            "catalogue_type": "restaurant",
            "status": "scraping",
            "options": {"concurrency": 1},
            "venues": [_venue("a", status="scraping", started=stale)],
        }
    )
    claimed = claim_next_batch(job, now=now.isoformat())
    assert len(claimed) == 1
    assert claimed[0].identity_key == "swiggy:restaurant:id:a"
    assert claimed[0].status == "scraping"
    assert claimed[0].scraping_started_at == now.isoformat()


def test_missing_scraping_started_at_is_reclaimed():
    now = datetime.now(timezone.utc).isoformat()
    job = job_from_dict(
        {
            "id": "job-missing",
            "organization_id": "org_1",
            "location": {"original": "x", "normalized": "x"},
            "platforms": ["swiggy"],
            "catalogue_type": "restaurant",
            "status": "scraping",
            "options": {"concurrency": 1},
            "venues": [_venue("a", status="scraping", started=None)],
        }
    )
    claimed = claim_next_batch(job, now=now)
    assert len(claimed) == 1


def test_empty_claim_returns_current_job_without_create_catalog(monkeypatch):
    calls: list[str] = []

    def fake_create(request: CatalogCreateRequest, access):
        calls.append(request.swiggy_url)
        return _ok(request)

    monkeypatch.setattr("backend.services.area_service.create_catalog", fake_create)
    now = datetime.now(timezone.utc).isoformat()
    job = _save_job(venues=[_venue("a", status="scraping", started=now)])
    result = scrape_area_batch(user_id="user-1", organization_id="org_1", job_id=job["id"], access=MapAccess({}))
    assert calls == []
    assert result["id"] == job["id"]
    assert result["venues"][0]["status"] == "scraping"


def test_overlapping_scrape_batch_claims_same_venue_once(monkeypatch):
    started = threading.Event()
    release = threading.Event()
    calls: list[str] = []
    lock = threading.Lock()

    def fake_create(request: CatalogCreateRequest, access):
        with lock:
            calls.append(request.swiggy_url)
        started.set()
        assert release.wait(timeout=5)
        return _ok(request)

    monkeypatch.setattr("backend.services.area_service.create_catalog", fake_create)
    job = _save_job(concurrency=1, venues=[_venue("a"), _venue("b")])
    errors: list[BaseException] = []

    def run():
        try:
            scrape_area_batch(user_id="user-1", organization_id="org_1", job_id=job["id"], access=MapAccess({}))
        except BaseException as exc:  # pragma: no cover
            errors.append(exc)

    worker = threading.Thread(target=run)
    worker.start()
    assert started.wait(timeout=5)
    second = scrape_area_batch(user_id="user-1", organization_id="org_1", job_id=job["id"], access=MapAccess({}))
    with lock:
        assert calls == ["https://www.swiggy.com/city/sample/a-resta"]
    statuses = {item["identity_key"]: item["status"] for item in second["venues"]}
    assert statuses["swiggy:restaurant:id:a"] == "scraping"
    assert statuses["swiggy:restaurant:id:b"] == "queued"
    release.set()
    worker.join(timeout=5)
    assert errors == []
    final = get_area_job("user-1", job["id"], "org_1")
    assert final is not None
    done = {item["identity_key"]: item["status"] for item in final["venues"]}
    assert done["swiggy:restaurant:id:a"] == "completed"
    assert done["swiggy:restaurant:id:b"] == "queued"
    assert calls == ["https://www.swiggy.com/city/sample/a-resta"]


def test_concurrency_one_overlapping_does_not_take_second_venue(monkeypatch):
    started = threading.Event()
    release = threading.Event()
    calls: list[str] = []

    def fake_create(request: CatalogCreateRequest, access):
        calls.append(request.swiggy_url)
        started.set()
        assert release.wait(timeout=5)
        return _ok(request)

    monkeypatch.setattr("backend.services.area_service.create_catalog", fake_create)
    job = _save_job(concurrency=1, venues=[_venue("a"), _venue("b")])
    worker = threading.Thread(
        target=lambda: scrape_area_batch(
            user_id="user-1", organization_id="org_1", job_id=job["id"], access=MapAccess({})
        )
    )
    worker.start()
    assert started.wait(timeout=5)
    overlapping = scrape_area_batch(user_id="user-1", organization_id="org_1", job_id=job["id"], access=MapAccess({}))
    assert len(calls) == 1
    assert {item["status"] for item in overlapping["venues"]} == {"scraping", "queued"}
    release.set()
    worker.join(timeout=5)
    follow = scrape_area_batch(user_id="user-1", organization_id="org_1", job_id=job["id"], access=MapAccess({}))
    assert len(calls) == 2
    statuses = {item["identity_key"]: item["status"] for item in follow["venues"]}
    assert statuses["swiggy:restaurant:id:a"] == "completed"
    assert statuses["swiggy:restaurant:id:b"] == "completed"


def test_multiple_queued_venues_process_sequentially(monkeypatch):
    calls: list[str] = []

    def fake_create(request: CatalogCreateRequest, access):
        calls.append(request.swiggy_url)
        return _ok(request)

    monkeypatch.setattr("backend.services.area_service.create_catalog", fake_create)
    job = _save_job(concurrency=1, venues=[_venue("a"), _venue("b")])
    first = scrape_area_batch(user_id="user-1", organization_id="org_1", job_id=job["id"], access=MapAccess({}))
    second = scrape_area_batch(user_id="user-1", organization_id="org_1", job_id=job["id"], access=MapAccess({}))
    assert len(calls) == 2
    assert first["venues"][0]["status"] == "completed"
    assert second["venues"][1]["status"] == "completed"
    assert {item["status"] for item in second["venues"]} == {"completed"}


def test_cancel_between_venues_does_not_start_remaining_or_resurrect(monkeypatch):
    first_started = threading.Event()
    allow_first = threading.Event()
    calls: list[str] = []

    def fake_create(request: CatalogCreateRequest, access):
        calls.append(request.swiggy_url)
        if len(calls) == 1:
            first_started.set()
            assert allow_first.wait(timeout=5)
        return _ok(request)

    monkeypatch.setattr("backend.services.area_service.create_catalog", fake_create)
    job = _save_job(concurrency=2, venues=[_venue("a"), _venue("b")])
    result_holder: dict[str, dict] = {}

    def run():
        result_holder["job"] = scrape_area_batch(
            user_id="user-1", organization_id="org_1", job_id=job["id"], access=MapAccess({})
        )

    worker = threading.Thread(target=run)
    worker.start()
    assert first_started.wait(timeout=5)
    cancelled = cancel_area_job(user_id="user-1", organization_id="org_1", job_id=job["id"])
    assert cancelled["status"] == "cancelled"
    allow_first.set()
    worker.join(timeout=5)
    assert len(calls) == 1
    final = result_holder["job"]
    assert final["status"] == "cancelled"
    statuses = {item["identity_key"]: item["status"] for item in final["venues"]}
    assert statuses["swiggy:restaurant:id:a"] == "skipped"
    assert statuses["swiggy:restaurant:id:b"] == "skipped"
    stored = get_area_job("user-1", job["id"], "org_1")
    assert stored is not None
    assert stored["status"] == "cancelled"
    assert all(item["status"] == "skipped" for item in stored["venues"])


def test_cancel_does_not_overwrite_already_completed_venue():
    job = _save_job(venues=[_venue("a", status="completed"), _venue("b")])
    cancelled = cancel_area_job(user_id="user-1", organization_id="org_1", job_id=job["id"])
    statuses = {item["identity_key"]: item["status"] for item in cancelled["venues"]}
    assert cancelled["status"] == "cancelled"
    assert statuses["swiggy:restaurant:id:a"] == "completed"
    assert statuses["swiggy:restaurant:id:b"] == "skipped"


def test_sqlite_claim_is_exclusive():
    job = _save_job(concurrency=1, venues=[_venue("a"), _venue("b")])
    first, first_keys = claim_area_scrape_batch(user_id="user-1", organization_id="org_1", job_id=job["id"])
    second, second_keys = claim_area_scrape_batch(user_id="user-1", organization_id="org_1", job_id=job["id"])
    assert first_keys == ["swiggy:restaurant:id:a"]
    assert second_keys == []
    statuses = {item["identity_key"]: item["status"] for item in first["venues"]}
    assert statuses["swiggy:restaurant:id:a"] == "scraping"
    assert statuses["swiggy:restaurant:id:b"] == "queued"
    assert second["venues"][0]["status"] == "scraping"

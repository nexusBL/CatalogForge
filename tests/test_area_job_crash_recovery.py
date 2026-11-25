from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone

from backend.schemas import CatalogCreateRequest
from backend.services.area_service import (
    _MERGE_ATTEMPTS,
    cancel_area_job,
    recovery_catalogue_id,
    scrape_area_batch,
)
from backend.store import (
    claim_area_scrape_batch,
    get_area_job,
    list_catalogues,
    merge_area_job_venue,
    save_catalogue,
    update_area_job,
)
from scraper.discovery.models import DiscoveredVenue
from scraper.discovery.queue import claim_next_batch, job_from_dict, process_started_at
from tests.test_area_scrape_claim import _ok, _save_job, _venue
from tests.test_discovery import MapAccess


def _simulate_restart(monkeypatch) -> None:
    monkeypatch.setattr(
        "scraper.discovery.queue._PROCESS_STARTED_AT",
        datetime.now(timezone.utc) + timedelta(seconds=1),
    )


def test_multi_worker_uvicorn_is_not_supported_by_process_start_ownership():
    """Area scrape claims assume one Uvicorn process. `--workers N` is not supported."""
    job = job_from_dict(
        {
            "id": "job-workers",
            "organization_id": "org_1",
            "location": {"original": "x", "normalized": "x"},
            "platforms": ["swiggy"],
            "catalogue_type": "restaurant",
            "status": "scraping",
            "options": {"concurrency": 1},
            "venues": [_venue("a", status="scraping", started=process_started_at().isoformat())],
        }
    )
    assert claim_next_batch(job, now=datetime.now(timezone.utc).isoformat()) == []


def test_crash_before_claim_leaves_queued_work_eligible(monkeypatch):
    calls: list[str] = []

    def fake_create(request: CatalogCreateRequest, access):
        calls.append(request.swiggy_url)
        return _ok(request)

    monkeypatch.setattr("backend.services.area_service.create_catalog", fake_create)
    job = _save_job(venues=[_venue("a"), _venue("b")])
    stored = get_area_job("user-1", job["id"], "org_1")
    assert stored is not None
    assert stored["venues"][0]["status"] == "queued"
    result = scrape_area_batch(user_id="user-1", organization_id="org_1", job_id=job["id"], access=MapAccess({}))
    assert calls == ["https://www.swiggy.com/city/sample/a-resta"]
    assert result["venues"][0]["status"] == "completed"


def test_crash_after_claim_before_create_catalog_recovers_after_restart(monkeypatch):
    calls: list[str] = []

    def fake_create(request: CatalogCreateRequest, access):
        calls.append(request.swiggy_url)
        return _ok(request)

    monkeypatch.setattr("backend.services.area_service.create_catalog", fake_create)
    job = _save_job(venues=[_venue("a")])
    claimed, keys = claim_area_scrape_batch(user_id="user-1", organization_id="org_1", job_id=job["id"])
    assert keys == ["swiggy:restaurant:id:a"]
    assert claimed["venues"][0]["status"] == "scraping"
    t1 = claimed["venues"][0]["scraping_started_at"]
    _simulate_restart(monkeypatch)
    recovered = scrape_area_batch(user_id="user-1", organization_id="org_1", job_id=job["id"], access=MapAccess({}))
    assert calls == ["https://www.swiggy.com/city/sample/a-resta"]
    assert recovered["venues"][0]["status"] == "completed"
    assert recovered["venues"][0]["scraping_started_at"] is None
    assert t1 is not None


def test_fresh_claim_is_not_reclaimed_after_process_start():
    now = datetime.now(timezone.utc).isoformat()
    job = job_from_dict(
        {
            "id": "job-fresh-proc",
            "organization_id": "org_1",
            "location": {"original": "x", "normalized": "x"},
            "platforms": ["swiggy"],
            "catalogue_type": "restaurant",
            "status": "scraping",
            "options": {"concurrency": 1},
            "venues": [_venue("a", status="scraping", started=now), _venue("b")],
        }
    )
    assert claim_next_batch(job, now=now) == []
    assert job.venues[0].status == "scraping"
    assert job.venues[1].status == "queued"


def test_stale_claim_still_recovers_after_300s(monkeypatch):
    monkeypatch.setenv("CATALOGFORGE_STALE_SCRAPE_CLAIM_SECONDS", "300")
    now = datetime.now(timezone.utc)
    stale = (now - timedelta(seconds=301)).isoformat()
    job = job_from_dict(
        {
            "id": "job-stale-300",
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
    assert claimed[0].scraping_started_at == now.isoformat()


def test_recovery_after_restart_is_idempotent(monkeypatch):
    calls: list[str] = []

    def fake_create(request: CatalogCreateRequest, access):
        calls.append(request.swiggy_url)
        return _ok(request)

    monkeypatch.setattr("backend.services.area_service.create_catalog", fake_create)
    started = (process_started_at() - timedelta(seconds=5)).isoformat()
    job = _save_job(venues=[_venue("a", status="scraping", started=started)])
    first = scrape_area_batch(user_id="user-1", organization_id="org_1", job_id=job["id"], access=MapAccess({}))
    second = scrape_area_batch(user_id="user-1", organization_id="org_1", job_id=job["id"], access=MapAccess({}))
    assert calls == ["https://www.swiggy.com/city/sample/a-resta"]
    assert first["venues"][0]["status"] == "completed"
    assert second["venues"][0]["status"] == "completed"


def test_completed_venue_is_never_reclaimed_after_restart(monkeypatch):
    started = (process_started_at() - timedelta(seconds=5)).isoformat()
    job = _save_job(
        venues=[
            _venue("a", status="completed", started=started),
            _venue("b", status="scraping", started=started),
        ]
    )
    _simulate_restart(monkeypatch)
    stored, keys = claim_area_scrape_batch(user_id="user-1", organization_id="org_1", job_id=job["id"])
    statuses = {item["identity_key"]: item["status"] for item in stored["venues"]}
    assert statuses["swiggy:restaurant:id:a"] == "completed"
    assert keys == ["swiggy:restaurant:id:b"]


def test_failed_venue_is_not_reclaimed_but_queued_retry_is(monkeypatch):
    past = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    job = _save_job(
        venues=[
            {**_venue("a", status="failed"), "retry_count": 9},
            {**_venue("b", status="queued"), "next_attempt_at": past},
            {**_venue("c", status="blocked")},
        ]
    )
    _simulate_restart(monkeypatch)
    stored, keys = claim_area_scrape_batch(user_id="user-1", organization_id="org_1", job_id=job["id"])
    statuses = {item["identity_key"]: item["status"] for item in stored["venues"]}
    assert statuses["swiggy:restaurant:id:a"] == "failed"
    assert statuses["swiggy:restaurant:id:c"] == "blocked"
    assert keys == ["swiggy:restaurant:id:b"]


def test_cancelled_job_is_not_resurrected_after_restart(monkeypatch):
    calls: list[str] = []

    def fake_create(request: CatalogCreateRequest, access):
        calls.append(request.swiggy_url)
        return _ok(request)

    monkeypatch.setattr("backend.services.area_service.create_catalog", fake_create)
    job = _save_job(venues=[_venue("a", status="scraping", started=datetime.now(timezone.utc).isoformat())])
    cancel_area_job(user_id="user-1", organization_id="org_1", job_id=job["id"])
    _simulate_restart(monkeypatch)
    result = scrape_area_batch(user_id="user-1", organization_id="org_1", job_id=job["id"], access=MapAccess({}))
    assert result["status"] == "cancelled"
    assert result["venues"][0]["status"] == "skipped"
    assert calls == []


def test_late_worker_cas_cannot_overwrite_or_persist_duplicate(monkeypatch):
    started = threading.Event()
    release = threading.Event()
    creates: list[str] = []
    t1_holder: dict[str, str | None] = {"t1": None}

    def fake_create(request: CatalogCreateRequest, access):
        creates.append(request.swiggy_url)
        if len(creates) == 1:
            payload = get_area_job("user-1", job["id"], "org_1")
            assert payload is not None
            t1_holder["t1"] = payload["venues"][0]["scraping_started_at"]
            monkeypatch.setattr(
                "scraper.discovery.queue._PROCESS_STARTED_AT",
                datetime.now(timezone.utc) + timedelta(seconds=1),
            )
            started.set()
            assert release.wait(timeout=5)
        return _ok(request)

    monkeypatch.setattr("backend.services.area_service.create_catalog", fake_create)
    job = _save_job(venues=[_venue("a")])
    errors: list[BaseException] = []

    def run_a():
        try:
            scrape_area_batch(user_id="user-1", organization_id="org_1", job_id=job["id"], access=MapAccess({}))
        except BaseException as exc:  # pragma: no cover
            errors.append(exc)

    worker = threading.Thread(target=run_a)
    worker.start()
    assert started.wait(timeout=5)
    t1 = t1_holder["t1"]
    b = scrape_area_batch(user_id="user-1", organization_id="org_1", job_id=job["id"], access=MapAccess({}))
    assert b["venues"][0]["status"] == "completed"
    assert b["venues"][0]["catalogue_id"]
    release.set()
    worker.join(timeout=5)
    assert errors == []
    final = get_area_job("user-1", job["id"], "org_1")
    assert final is not None
    assert final["venues"][0]["status"] == "completed"
    assert len(list_catalogues("user-1", "org_1")) == 1
    late = DiscoveredVenue(
        platform="swiggy",
        catalogue_type="restaurant",
        venue_url="https://www.swiggy.com/city/sample/a-resta",
        identity_key="swiggy:restaurant:id:a",
        status="failed",
        error="late",
        selected=True,
    )
    stored = merge_area_job_venue(
        user_id="user-1",
        organization_id="org_1",
        job_id=job["id"],
        venue=late,
        claim_started_at=t1 or "",
    )
    assert stored["venues"][0]["status"] == "completed"
    assert stored["status"] != "failed"
    assert t1
    assert creates == [
        "https://www.swiggy.com/city/sample/a-resta",
        "https://www.swiggy.com/city/sample/a-resta",
    ]


def test_save_then_merge_crash_reuses_catalogue_by_source_url(monkeypatch):
    persist_calls = {"n": 0}
    original_save = save_catalogue

    def counting_save(**kwargs):
        persist_calls["n"] += 1
        return original_save(**kwargs)

    monkeypatch.setattr("backend.services.area_service.save_catalogue", counting_save)

    def fake_create(request: CatalogCreateRequest, access):
        return _ok(request)

    monkeypatch.setattr("backend.services.area_service.create_catalog", fake_create)

    job = _save_job(venues=[_venue("a")])
    real_merge = merge_area_job_venue
    crashes = {"n": 0}

    def crash_once(**kwargs):
        crashes["n"] += 1
        if crashes["n"] <= _MERGE_ATTEMPTS:
            raise RuntimeError("simulated merge crash after save_catalogue")
        return real_merge(**kwargs)

    monkeypatch.setattr("backend.services.area_service.merge_area_job_venue", crash_once)
    scrape_area_batch(user_id="user-1", organization_id="org_1", job_id=job["id"], access=MapAccess({}))
    stuck = get_area_job("user-1", job["id"], "org_1")
    assert stuck is not None
    assert stuck["venues"][0]["status"] == "scraping"
    assert persist_calls["n"] == 1
    assert len(list_catalogues("user-1", "org_1")) == 1
    _simulate_restart(monkeypatch)
    recovered = scrape_area_batch(user_id="user-1", organization_id="org_1", job_id=job["id"], access=MapAccess({}))
    assert recovered["venues"][0]["status"] == "completed"
    assert recovered["venues"][0]["catalogue_id"]
    assert persist_calls["n"] == 1
    assert len(list_catalogues("user-1", "org_1")) == 1


def test_recovery_matches_platform_and_source_url():
    venue = DiscoveredVenue(
        platform="swiggy",
        catalogue_type="restaurant",
        venue_url="https://www.swiggy.com/city/sample/alpha-rest1",
        venue_id="111",
        name="Other Name",
        identity_key="swiggy:restaurant:id:111",
    )
    catalogues = [
        {
            "id": "cat-url",
            "result": {
                "platform": "swiggy",
                "catalogue_type": "restaurant",
                "source_url": "https://www.swiggy.com/city/sample/alpha-rest1",
                "restaurant": {"name": "Alpha", "restaurant_id": "999"},
            },
        }
    ]
    assert recovery_catalogue_id("org_1", venue, catalogues) == "cat-url"


def test_recovery_does_not_match_on_name_and_place_only():
    venue = DiscoveredVenue(
        platform="swiggy",
        catalogue_type="restaurant",
        venue_url="https://www.swiggy.com/city/sample/other-rest9",
        venue_id="9",
        name="Alpha",
        location="Sample Area",
        identity_key="swiggy:restaurant:id:9",
    )
    catalogues = [
        {
            "id": "cat-wrong",
            "result": {
                "platform": "swiggy",
                "catalogue_type": "restaurant",
                "source_url": "https://www.swiggy.com/city/sample/alpha-rest1",
                "restaurant": {"name": "Alpha", "outlet": "Sample Area", "restaurant_id": "1"},
            },
        }
    ]
    assert recovery_catalogue_id("org_1", venue, catalogues) is None


def test_persist_failure_retries_then_fails(monkeypatch, caplog):
    caplog.set_level(logging.ERROR)
    creates = {"n": 0}

    def fake_create(request: CatalogCreateRequest, access):
        creates["n"] += 1
        return _ok(request)

    monkeypatch.setattr("backend.services.area_service.create_catalog", fake_create)
    monkeypatch.setattr(
        "backend.services.area_service._persist_result",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("disk full")),
    )
    job = _save_job(venues=[_venue("a")])
    payload = get_area_job("user-1", job["id"], "org_1")
    assert payload is not None
    payload["options"]["max_retries"] = 1
    update_area_job(user_id="user-1", payload=payload)

    first = scrape_area_batch(user_id="user-1", organization_id="org_1", job_id=job["id"], access=MapAccess({}))
    assert first["venues"][0]["status"] == "queued"
    assert "disk full" in (first["venues"][0]["error"] or "")
    monkeypatch.setattr(
        "scraper.discovery.queue.utcnow",
        lambda: (datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat(),
    )
    second = scrape_area_batch(user_id="user-1", organization_id="org_1", job_id=job["id"], access=MapAccess({}))
    assert second["venues"][0]["status"] == "failed"
    assert creates["n"] == 2
    assert any("Catalogue persist failed" in rec.message for rec in caplog.records)


def test_merge_failure_leaves_recoverable_scraping_state(monkeypatch):
    monkeypatch.setattr("backend.services.area_service.create_catalog", lambda request, access: _ok(request))

    def boom(**kwargs):
        raise RuntimeError("merge boom")

    monkeypatch.setattr("backend.services.area_service.merge_area_job_venue", boom)
    job = _save_job(venues=[_venue("a")])
    result = scrape_area_batch(user_id="user-1", organization_id="org_1", job_id=job["id"], access=MapAccess({}))
    assert result["venues"][0]["status"] == "scraping"
    assert result.get("status") != "cancelled"
    _simulate_restart(monkeypatch)
    monkeypatch.setattr(
        "backend.services.area_service.merge_area_job_venue",
        lambda **kwargs: merge_area_job_venue(**kwargs),
    )
    recovered = scrape_area_batch(user_id="user-1", organization_id="org_1", job_id=job["id"], access=MapAccess({}))
    assert recovered["venues"][0]["status"] == "completed"


def test_cancel_then_late_merge_cannot_resurrect():
    job = _save_job(venues=[_venue("a")])
    stored, keys = claim_area_scrape_batch(user_id="user-1", organization_id="org_1", job_id=job["id"])
    t1 = stored["venues"][0]["scraping_started_at"]
    assert keys == ["swiggy:restaurant:id:a"]
    cancelled = cancel_area_job(user_id="user-1", organization_id="org_1", job_id=job["id"])
    assert cancelled["status"] == "cancelled"
    assert cancelled["venues"][0]["status"] == "skipped"
    late = DiscoveredVenue(
        platform="swiggy",
        catalogue_type="restaurant",
        venue_url="https://www.swiggy.com/city/sample/a-resta",
        identity_key="swiggy:restaurant:id:a",
        status="completed",
        catalogue_id="should-not-apply",
        selected=True,
    )
    merged = merge_area_job_venue(
        user_id="user-1",
        organization_id="org_1",
        job_id=job["id"],
        venue=late,
        claim_started_at=t1,
    )
    assert merged["status"] == "cancelled"
    assert merged["venues"][0]["status"] == "skipped"
    assert merged["venues"][0].get("catalogue_id") is None

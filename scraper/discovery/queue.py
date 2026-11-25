from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from scraper.discovery.models import AreaJob, DiscoveredVenue, DiscoveryOptions, JobStatus, LocationQuery
from scraper.discovery.scope import job_discovery_scope

DEFAULT_STALE_SCRAPE_CLAIM_SECONDS = 300.0
STALE_SCRAPE_CLAIM_SECONDS_ENV = "CATALOGFORGE_STALE_SCRAPE_CLAIM_SECONDS"

# Claim ownership is valid for a single Uvicorn process only.
# Multi-worker Uvicorn (`--workers N`) is NOT supported: another worker would
# treat in-flight claims as pre-process (stale) and steal them.
# Do not introduce Redis/Celery to share ownership across processes.
_PROCESS_STARTED_AT = datetime.now(timezone.utc)


def process_started_at() -> datetime:
    return _PROCESS_STARTED_AT


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def stale_scrape_claim_seconds() -> float:
    raw = os.getenv(STALE_SCRAPE_CLAIM_SECONDS_ENV)
    if raw is None or not str(raw).strip():
        return DEFAULT_STALE_SCRAPE_CLAIM_SECONDS
    try:
        return max(0.0, float(raw))
    except ValueError:
        return DEFAULT_STALE_SCRAPE_CLAIM_SECONDS


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def venue_match_key(venue: DiscoveredVenue) -> str:
    return venue.identity_key or venue.venue_url


def is_stale_scrape_claim(venue: DiscoveredVenue, now: str | None = None, *, stale_after: float | None = None) -> bool:
    if venue.status != "scraping":
        return False
    started = parse_timestamp(venue.scraping_started_at)
    if started is None:
        return True
    # Claims written before this process started belong to a dead owner.
    if started < process_started_at():
        return True
    stamp = parse_timestamp(now) or datetime.now(timezone.utc)
    limit = stale_scrape_claim_seconds() if stale_after is None else stale_after
    return stamp - started >= timedelta(seconds=limit)


def job_from_dict(data: dict[str, Any]) -> AreaJob:
    location = data.get("location") or {}
    options = data.get("options") or {}
    venues = [venue_from_dict(item) for item in data.get("venues") or []]
    return AreaJob(
        id=data["id"],
        organization_id=data.get("organization_id") or "",
        location=LocationQuery(
            original=location.get("original") or "",
            normalized=location.get("normalized") or "",
            city=location.get("city"),
            state=location.get("state"),
            locality=location.get("locality"),
            slug=location.get("slug") or "",
            search_text=location.get("search_text") or "",
            country=location.get("country"),
            postal_code=location.get("postal_code"),
            latitude=location.get("latitude"),
            longitude=location.get("longitude"),
            display_name=location.get("display_name"),
            confidence=location.get("confidence"),
            platform_places=dict(location.get("platform_places") or location.get("platforms") or {}),
        ),
        platforms=list(data.get("platforms") or []),
        catalogue_type=data.get("catalogue_type") or "restaurant",
        status=data.get("status") or "created",
        created_at=data.get("created_at") or "",
        started_at=data.get("started_at"),
        completed_at=data.get("completed_at"),
        options=DiscoveryOptions(
            max_venues=options.get("max_venues"),
            max_pages=options.get("max_pages"),
            max_retries=int(2 if options.get("max_retries") is None else options.get("max_retries")),
            concurrency=int(options.get("concurrency") or 1),
            delay_seconds=float(options.get("delay_seconds") or 0),
            magicpin_dining=str(options.get("magicpin_dining") or "budget"),
        ),
        venues=venues,
        error=data.get("error"),
        discovery_scope=data.get("discovery_scope") or job_discovery_scope(list(data.get("platforms") or []), data.get("catalogue_type") or "restaurant"),
    )


def venue_from_dict(data: dict[str, Any]) -> DiscoveredVenue:
    return DiscoveredVenue(
        platform=data["platform"],
        catalogue_type=data["catalogue_type"],
        venue_url=data["venue_url"],
        canonical_url=data.get("canonical_url"),
        venue_id=data.get("venue_id"),
        name=data.get("name"),
        location=data.get("location"),
        address=data.get("address"),
        rating=data.get("rating"),
        source=data.get("source"),
        identity_key=data.get("identity_key"),
        status=data.get("status") or "discovered",
        retry_count=int(data.get("retry_count") or 0),
        error=data.get("error"),
        catalogue_id=data.get("catalogue_id"),
        existing_catalogue_id=data.get("existing_catalogue_id"),
        existing_action=data.get("existing_action"),
        image_url=data.get("image_url"),
        cuisine=data.get("cuisine"),
        selected=bool(data.get("selected", True)),
        next_attempt_at=data.get("next_attempt_at"),
        scraping_started_at=data.get("scraping_started_at"),
        discovery_scope=data.get("discovery_scope"),
        location_match=data.get("location_match"),
        sub_source=data.get("sub_source"),
    )


def job_to_dict(job: AreaJob) -> dict[str, Any]:
    counts = job.counts()
    return {
        "id": job.id,
        "organization_id": job.organization_id,
        "location": job.location.to_dict(),
        "location_input": job.location.original,
        "normalized_location": job.location.normalized,
        "platforms": job.platforms,
        "catalogue_type": job.catalogue_type,
        "status": job.status,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
        "options": {
            "max_venues": job.options.max_venues,
            "max_pages": job.options.max_pages,
            "max_retries": job.options.max_retries,
            "concurrency": job.options.concurrency,
            "delay_seconds": job.options.delay_seconds,
            "magicpin_dining": job.options.magicpin_dining,
        },
        "venues": [item.to_dict() for item in job.venues],
        "error": job.error,
        "discovery_scope": job.discovery_scope or job_discovery_scope(job.platforms, job.catalogue_type),
        **counts,
    }


def queue_selected(job: AreaJob, selected_keys: list[str] | None = None) -> AreaJob:
    keys = set(selected_keys) if selected_keys is not None else None
    for venue in job.venues:
        if keys is not None:
            venue.selected = (venue.identity_key or venue.venue_url) in keys
        if not venue.selected:
            if venue.status not in {"completed", "blocked", "failed"}:
                venue.status = "skipped"
            continue
        if venue.existing_catalogue_id and (venue.existing_action or "skip") == "skip":
            venue.status = "skipped"
            continue
        if venue.status in {"completed"}:
            continue
        venue.status = "queued"
    job.status = "queued"
    return job


def next_batch(job: AreaJob, now: str | None = None) -> list[DiscoveredVenue]:
    if job.status == "cancelled":
        return []
    limit = job.options.concurrency
    ready: list[DiscoveredVenue] = []
    stamp = now or utcnow()
    for venue in job.venues:
        if len(ready) >= limit:
            break
        if not venue.selected or venue.status != "queued":
            continue
        if venue.next_attempt_at and venue.next_attempt_at > stamp:
            continue
        ready.append(venue)
    return ready


def _is_due(venue: DiscoveredVenue, stamp: str) -> bool:
    return not (venue.next_attempt_at and venue.next_attempt_at > stamp)


def _is_claim_eligible(venue: DiscoveredVenue, stamp: str, stale_after: float) -> bool:
    if not venue.selected:
        return False
    if venue.status == "queued" and _is_due(venue, stamp):
        return True
    return is_stale_scrape_claim(venue, stamp, stale_after=stale_after)


def claim_next_batch(job: AreaJob, now: str | None = None) -> list[DiscoveredVenue]:
    if job.status == "cancelled":
        return []
    stamp = now or utcnow()
    stale_after = stale_scrape_claim_seconds()
    fresh_scraping = 0
    eligible: list[DiscoveredVenue] = []
    for venue in job.venues:
        if venue.selected and venue.status == "scraping" and not is_stale_scrape_claim(venue, stamp, stale_after=stale_after):
            fresh_scraping += 1
            continue
        if _is_claim_eligible(venue, stamp, stale_after):
            eligible.append(venue)
    slots = job.options.concurrency - fresh_scraping
    if slots <= 0:
        return []
    claimed = eligible[:slots]
    for venue in claimed:
        venue.status = "scraping"
        venue.scraping_started_at = stamp
    return claimed


def mark_retry_or_fail(venue: DiscoveredVenue, error: str, *, blocked: bool, max_retries: int) -> None:
    venue.error = error
    venue.scraping_started_at = None
    if blocked:
        venue.status = "blocked"
        return
    venue.retry_count += 1
    if venue.retry_count <= max_retries:
        venue.status = "queued"
        delay = min(60, 2 ** venue.retry_count)
        venue.next_attempt_at = (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()
        return
    venue.status = "failed"


def finalize_status(job: AreaJob) -> JobStatus:
    if job.status == "cancelled":
        return "cancelled"
    remaining = [
        item
        for item in job.venues
        if item.selected and item.status in {"queued", "scraping", "discovered", "selected"}
    ]
    if remaining:
        return "scraping"
    counts = job.counts()
    if counts["failed_count"] or counts["blocked_count"]:
        if counts["completed_count"]:
            return "partially_completed"
        return "failed"
    return "completed"

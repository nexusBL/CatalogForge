from __future__ import annotations

import logging
import uuid
from typing import Any, Literal

from backend.schemas import CatalogCreateRequest, CatalogCreateResponse
from backend.services.catalog_service import BrowserAccess, SwiggyAccess, create_catalog
from backend.raw_capture import bind_raw_capture
from backend.store import (
    catalogues_as_dicts,
    cancel_area_job_payload,
    claim_area_scrape_batch,
    delete_area_job,
    get_area_job,
    list_area_jobs,
    matching_catalogue_id,
    merge_area_job_venue,
    save_area_job,
    save_catalogue,
    update_area_job,
    update_catalogue,
)
from scraper.discovery.location import parse_location
from scraper.discovery.locate import LocationSelectionError, locate_script_args
from scraper.discovery.resolver import AmbiguousLocationError, default_geocoder, resolve_location
from scraper.discovery.models import AreaJob, DiscoveredVenue, DiscoveryOptions, ListingPage
from scraper.discovery.queue import (
    job_from_dict,
    job_to_dict,
    mark_retry_or_fail,
    queue_selected,
    utcnow,
    venue_match_key,
)
from scraper.discovery.runner import discover_location
from scraper.discovery.scope import job_discovery_scope
from scraper.discovery.urls import canonical_url
from scraper.platform import normalize_platform, platform_from_url, platform_url_error

ExistingVenueAction = Literal["skip", "rescrape", "update"]

logger = logging.getLogger(__name__)
_MERGE_ATTEMPTS = 3


def listing_fetcher(access: SwiggyAccess, location=None, options: DiscoveryOptions | None = None):
    def fetch(url: str) -> ListingPage:
        kind = getattr(options, "current_kind", "restaurant") if options else "restaurant"
        dining = getattr(options, "magicpin_dining", "budget") if options else "budget"
        platform = platform_from_url(url)
        if isinstance(access, BrowserAccess) and location is not None and platform:
            args = locate_script_args(platform, kind, location, dining)
            from scraper.discovery.collect import collect_listing_with_location

            located = collect_listing_with_location(
                url,
                platform=platform,
                query=args["query"],
                category=args["category"],
                expected_lat=getattr(location, "latitude", None),
                expected_lng=getattr(location, "longitude", None),
                city=args.get("city") or "",
                state=args.get("state") or "",
                locality=args.get("locality") or "",
                type_text=args.get("type") or "",
            )
            if located.html or located.error:
                return located
        obtained = access.load(url)
        raw = obtained.raw
        html = (raw.html if raw else "") or ""
        blocked = bool(raw and (raw.blocked or raw.access_status == "blocked"))
        payload = None
        if raw:
            payload = raw.next_data or raw.api_payloads or raw.json_ld
        return ListingPage(
            url=url,
            html=html,
            payload=payload,
            blocked=blocked,
            error=obtained.error,
            exhausted=blocked,
        )

    return fetch


def create_area_job(
    *,
    user_id: str,
    organization_id: str,
    location_input: str,
    platforms: list[str],
    catalogue_type: str,
    access: SwiggyAccess,
    max_venues: int | None = None,
    concurrency: int = 1,
    max_retries: int = 2,
    delay_seconds: float = 0.0,
    magicpin_dining: str = "budget",
) -> dict[str, Any]:
    if not platforms:
        raise ValueError("Select at least one platform.")
    names = [normalize_platform(item) for item in platforms]
    options = DiscoveryOptions(
        max_venues=max_venues,
        concurrency=concurrency,
        max_retries=max_retries,
        delay_seconds=delay_seconds,
        magicpin_dining=magicpin_dining or "budget",
    )
    existing = catalogues_as_dicts(user_id, organization_id)
    parsed = parse_location(location_input)
    try:
        parsed = resolve_location(location_input, geocoder=default_geocoder())
        location, venues = discover_location(
            location_input,
            names,
            catalogue_type,
            listing_fetcher(access, parsed, options),
            options,
            existing,
            resolved=parsed,
        )
        job_error = None
        status = "awaiting_confirmation"
    except (LocationSelectionError, AmbiguousLocationError) as exc:
        location = parsed
        venues = []
        job_error = str(exc)
        status = "failed"
    now = utcnow()
    payload = {
        "id": str(uuid.uuid4()),
        "organization_id": organization_id,
        "location": location.to_dict(),
        "platforms": names,
        "catalogue_type": catalogue_type,
        "status": status,
        "created_at": now,
        "started_at": None,
        "completed_at": now if status == "failed" else None,
        "options": {
            "max_venues": options.max_venues,
            "max_pages": options.max_pages,
            "max_retries": options.max_retries,
            "concurrency": options.concurrency,
            "delay_seconds": options.delay_seconds,
            "magicpin_dining": options.magicpin_dining,
        },
        "venues": [item.to_dict() for item in venues],
        "error": job_error,
    }
    job = job_from_dict(payload)
    job.discovery_scope = job_discovery_scope(names, catalogue_type)
    return save_area_job(user_id=user_id, organization_id=organization_id, payload=job_to_dict(job))


def start_area_scrape(
    *,
    user_id: str,
    organization_id: str,
    job_id: str,
    selected_keys: list[str] | None = None,
    existing_actions: dict[str, ExistingVenueAction] | None = None,
) -> dict[str, Any]:
    payload = get_area_job(user_id, job_id, organization_id)
    if payload is None:
        raise KeyError("Area job not found.")
    job = job_from_dict(payload)
    if job.status == "cancelled":
        return job_to_dict(job)
    actions = existing_actions or {}
    for venue in job.venues:
        key = venue.identity_key or venue.venue_url
        if key in actions:
            venue.existing_action = actions[key]
    queue_selected(job, selected_keys)
    job.status = "scraping"
    job.started_at = job.started_at or utcnow()
    stored = job_to_dict(job)
    return update_area_job(user_id=user_id, payload=stored)


def cancel_area_job(*, user_id: str, organization_id: str, job_id: str) -> dict[str, Any]:
    return cancel_area_job_payload(user_id=user_id, organization_id=organization_id, job_id=job_id)


def scrape_area_batch(*, user_id: str, organization_id: str, job_id: str, access: SwiggyAccess) -> dict[str, Any]:
    stored, claimed_keys = claim_area_scrape_batch(
        user_id=user_id,
        organization_id=organization_id,
        job_id=job_id,
    )
    latest = stored
    for key in claimed_keys:
        owned = _owned_claimed_venue(user_id, organization_id, job_id, key)
        if owned is None:
            payload = get_area_job(user_id, job_id, organization_id)
            if payload is None:
                raise KeyError("Area job not found.")
            if payload.get("status") == "cancelled":
                return payload
            latest = payload
            continue
        job, venue, claim_started_at = owned
        try:
            latest = _process_claimed_venue(
                user_id=user_id,
                organization_id=organization_id,
                job_id=job_id,
                job=job,
                venue=venue,
                claim_started_at=claim_started_at,
                access=access,
            )
        except KeyError:
            raise
        except Exception as exc:
            logger.exception("Area scrape failed for job %s venue %s", job_id, key)
            mark_retry_or_fail(
                venue, f"{type(exc).__name__}: {exc}", blocked=False, max_retries=job.options.max_retries
            )
            latest = _cas_merge(user_id, organization_id, job_id, venue, claim_started_at)
        if latest.get("status") == "cancelled":
            return latest
    return latest


def _process_claimed_venue(
    *,
    user_id: str,
    organization_id: str,
    job_id: str,
    job: AreaJob,
    venue: DiscoveredVenue,
    claim_started_at: str,
    access: SwiggyAccess,
) -> dict[str, Any]:
    key = venue_match_key(venue)
    mismatch = platform_url_error(venue.platform, venue.venue_url)
    if mismatch:
        venue.status = "failed"
        venue.error = mismatch
        return _cas_merge(user_id, organization_id, job_id, venue, claim_started_at)
    if venue.existing_catalogue_id and (venue.existing_action or "skip") == "skip":
        venue.status = "skipped"
        return _cas_merge(user_id, organization_id, job_id, venue, claim_started_at)
    request = CatalogCreateRequest.model_construct(
        restaurant_name=venue.name or "Venue",
        fssai_number="",
        swiggy_url=venue.venue_url,
        source_url=venue.venue_url,
        catalogue_type=venue.catalogue_type,
        platform=venue.platform,
        organization_id=organization_id,
    )
    try:
        result = create_catalog(request, access)
    except Exception as exc:
        mark_retry_or_fail(venue, f"{type(exc).__name__}: {exc}", blocked=False, max_retries=job.options.max_retries)
        return _cas_merge(user_id, organization_id, job_id, venue, claim_started_at)
    if result.extraction_status == "blocked":
        mark_retry_or_fail(venue, result.error or "blocked", blocked=True, max_retries=job.options.max_retries)
        return _cas_merge(user_id, organization_id, job_id, venue, claim_started_at)
    if result.extraction_status != "ok":
        mark_retry_or_fail(venue, result.error or "failed", blocked=False, max_retries=job.options.max_retries)
        return _cas_merge(user_id, organization_id, job_id, venue, claim_started_at)
    if not _still_owns_claim(user_id, organization_id, job_id, key, claim_started_at):
        payload = get_area_job(user_id, job_id, organization_id)
        if payload is None:
            raise KeyError("Area job not found.")
        return payload
    try:
        persisted = _persist_result(user_id, organization_id, venue, result)
    except Exception as exc:
        logger.exception("Catalogue persist failed for area job %s venue %s", job_id, key)
        mark_retry_or_fail(
            venue, f"{type(exc).__name__}: {exc}", blocked=False, max_retries=job.options.max_retries
        )
        return _cas_merge(user_id, organization_id, job_id, venue, claim_started_at)
    bind_raw_capture(
        organization_id=organization_id,
        scrape_token=result.raw_capture_id,
        catalogue_id=persisted.id,
        user_id=user_id,
    )
    venue.status = "completed"
    venue.catalogue_id = persisted.id
    venue.error = None
    return _cas_merge(user_id, organization_id, job_id, venue, claim_started_at)


def _owned_claimed_venue(
    user_id: str, organization_id: str, job_id: str, key: str
) -> tuple[AreaJob, DiscoveredVenue, str] | None:
    payload = get_area_job(user_id, job_id, organization_id)
    if payload is None:
        raise KeyError("Area job not found.")
    job = job_from_dict(payload)
    if job.status == "cancelled":
        return None
    venue = next((item for item in job.venues if venue_match_key(item) == key), None)
    if venue is None or venue.status != "scraping" or not venue.scraping_started_at:
        return None
    return job, venue, venue.scraping_started_at


def _still_owns_claim(user_id: str, organization_id: str, job_id: str, key: str, claim_started_at: str) -> bool:
    payload = get_area_job(user_id, job_id, organization_id)
    if payload is None or payload.get("status") == "cancelled":
        return False
    job = job_from_dict(payload)
    venue = next((item for item in job.venues if venue_match_key(item) == key), None)
    return bool(venue and venue.status == "scraping" and venue.scraping_started_at == claim_started_at)


def _cas_merge(
    user_id: str, organization_id: str, job_id: str, venue: DiscoveredVenue, claim_started_at: str
) -> dict[str, Any]:
    for attempt in range(_MERGE_ATTEMPTS):
        try:
            return merge_area_job_venue(
                user_id=user_id,
                organization_id=organization_id,
                job_id=job_id,
                venue=venue,
                claim_started_at=claim_started_at,
            )
        except Exception:
            logger.exception("Area job merge failed for job %s (attempt %s)", job_id, attempt + 1)
    payload = get_area_job(user_id, job_id, organization_id)
    if payload is None:
        raise KeyError("Area job not found.")
    return payload


def recovery_catalogue_id(
    organization_id: str, venue: DiscoveredVenue, catalogues: list[dict[str, Any]]
) -> str | None:
    """Reuse a catalogue only on stable identity: org (caller scope) + platform + source URL or venue id.

    Name/place matching is intentionally not used. If neither source URL nor venue id
    can be compared, recovery will not reuse a row (possible duplicate after a crash
    between save_catalogue and merge).
    """
    if not organization_id:
        return None
    venue_url = canonical_url(venue.canonical_url or venue.venue_url or "")
    venue_id = (venue.venue_id or "").strip().lower()
    if not venue_url and not venue_id:
        return None
    return matching_catalogue_id(
        catalogues,
        platform=venue.platform,
        source_url=venue_url,
        restaurant_id=venue_id,
    )


def _persist_result(user_id: str, organization_id: str, venue: DiscoveredVenue, result: CatalogCreateResponse):
    catalogues = catalogues_as_dicts(user_id, organization_id)
    recovered_id = recovery_catalogue_id(organization_id, venue, catalogues)
    reuse_id = recovered_id
    if not reuse_id and venue.existing_catalogue_id and venue.existing_action in {"rescrape", "update"}:
        reuse_id = venue.existing_catalogue_id
    if reuse_id:
        updated = update_catalogue(
            user_id=user_id,
            catalogue_id=reuse_id,
            organization_id=organization_id,
            result=result,
        )
        if updated:
            return updated
    return save_catalogue(user_id=user_id, organization_id=organization_id, result=result)


def area_jobs_for(user_id: str, organization_id: str) -> list[dict[str, Any]]:
    return list_area_jobs(user_id, organization_id)


def delete_area_discovery_job(*, user_id: str, organization_id: str, job_id: str) -> dict[str, Any]:
    payload = get_area_job(user_id, job_id, organization_id)
    if payload is None:
        raise KeyError("Area job not found.")
    if not delete_area_job(user_id, job_id, organization_id):
        raise KeyError("Area job not found.")
    return {"ok": True, "id": job_id}

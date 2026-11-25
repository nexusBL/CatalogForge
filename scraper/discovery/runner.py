from __future__ import annotations

import logging
from collections.abc import Callable

from scraper.discovery.locate import LocationSelectionError, category_follow_url
from scraper.discovery.dedupe import dedupe_venues
from scraper.discovery.district import DistrictDiscovery
from scraper.discovery.existing import mark_existing
from scraper.discovery.location import parse_location
from scraper.discovery.resolver import AmbiguousLocationError, PlatformLocationResolver, resolve_location
from scraper.discovery.magicpin import MagicpinDiscovery
from scraper.discovery.models import (
    CatalogueKind,
    DiscoveredVenue,
    DiscoveryOptions,
    ListingPage,
    LocationQuery,
)
from scraper.discovery.scope import classify_venues
from scraper.discovery.swiggy import SwiggyDiscovery
from scraper.discovery.urls import assert_platform_url
from scraper.discovery.zomato import ZomatoDiscovery
from scraper.swiggy.chrome_session import browser_job
from scraper.platform import normalize_platform

logger = logging.getLogger(__name__)
_DISCOVERY_ABORT = (LocationSelectionError, AmbiguousLocationError)

ADAPTERS = {
    "swiggy": SwiggyDiscovery(),
    "zomato": ZomatoDiscovery(),
    "magicpin": MagicpinDiscovery(),
}

ListingFetcher = Callable[[str], ListingPage]


def kinds_for(catalogue_type: str) -> list[CatalogueKind]:
    if catalogue_type == "both":
        return ["restaurant", "dineout"]
    if catalogue_type == "dineout":
        return ["dineout"]
    return ["restaurant"]


def discover_location(
    location_input: str,
    platforms: list[str],
    catalogue_type: str,
    fetcher: ListingFetcher,
    options: DiscoveryOptions | None = None,
    existing_catalogues: list[dict] | None = None,
    resolved: LocationQuery | None = None,
) -> tuple[LocationQuery, list[DiscoveredVenue]]:
    with browser_job():
        return _discover_location(
            location_input,
            platforms,
            catalogue_type,
            fetcher,
            options=options,
            existing_catalogues=existing_catalogues,
            resolved=resolved,
        )


def _discover_location(
    location_input: str,
    platforms: list[str],
    catalogue_type: str,
    fetcher: ListingFetcher,
    options: DiscoveryOptions | None = None,
    existing_catalogues: list[dict] | None = None,
    resolved: LocationQuery | None = None,
) -> tuple[LocationQuery, list[DiscoveredVenue]]:
    options = options or DiscoveryOptions()
    if resolved is not None:
        location = resolved
    elif options.geocoder is not None:
        location = resolve_location(location_input, geocoder=options.geocoder)
    else:
        location = parse_location(location_input)
    collected: list[DiscoveredVenue] = []
    selected = [normalize_platform(name) for name in platforms]
    if not selected:
        raise ValueError("Select at least one platform.")
    for platform in selected:
        adapter = ADAPTERS[platform]
        for kind in kinds_for(catalogue_type):
            options.current_kind = kind
            try:
                collected.extend(_discover_platform(adapter, location, kind, fetcher, options))
            except _DISCOVERY_ABORT:
                raise
            except Exception:
                logger.exception("Discovery failed for platform %s kind %s", platform, kind)
    if options.include_district and "zomato" in selected:
        try:
            collected.extend(_discover_platform(DistrictDiscovery(), location, "dineout", fetcher, options))
        except _DISCOVERY_ABORT:
            raise
        except Exception:
            logger.exception("Discovery failed for district dineout")
    unique = dedupe_venues(collected)
    if options.max_venues is not None:
        unique = unique[: options.max_venues]
    if existing_catalogues:
        mark_existing(unique, existing_catalogues)
    classify_venues(location, unique)
    for venue in unique:
        if venue.sub_source == "district":
            host = (venue.venue_url or "").lower()
            if "district.in" not in host:
                raise ValueError(f"District URL is not a District domain: {venue.venue_url}")
            continue
        assert_platform_url(venue.platform, venue.venue_url)
    return location, unique


def _discover_platform(adapter, location: LocationQuery, kind: CatalogueKind, fetcher: ListingFetcher, options: DiscoveryOptions) -> list[DiscoveredVenue]:
    seen_pages: set[str] = set()
    venues: list[DiscoveredVenue] = []
    queue = list(adapter.listing_urls(kind, location, options.magicpin_dining))
    pages = 0
    while queue:
        url = queue.pop(0)
        if url in seen_pages:
            continue
        seen_pages.add(url)
        pages += 1
        if options.max_pages is not None and pages > options.max_pages:
            break
        try:
            page = fetcher(url)
        except _DISCOVERY_ABORT:
            raise
        except Exception:
            logger.exception("Discovery fetch failed for %s %s %s", adapter.platform, kind, url)
            continue
        if page.error and "Location selection failed" in page.error:
            raise LocationSelectionError(page.error)
        try:
            if page.html or page.url:
                PlatformLocationResolver().bind(location, adapter.platform, html=page.html or "", page_url=page.url)
            if page.blocked:
                break
            dining_modes = (
                ["budget", "fine"]
                if adapter.platform == "magicpin" and kind == "dineout" and options.magicpin_dining == "all"
                else [options.magicpin_dining]
            )
            for mode in dining_modes:
                follow = category_follow_url(page.html, page.url, adapter.platform, kind, mode)
                if follow and follow not in seen_pages:
                    queue.append(follow)
            venues.extend(adapter.parse_page(page, kind))
            if adapter.exhausted(page):
                continue
            nxt = adapter.next_url(page)
            if nxt and nxt not in seen_pages:
                queue.append(nxt)
            if options.max_venues is not None and len(dedupe_venues(venues)) >= options.max_venues:
                break
        except _DISCOVERY_ABORT:
            raise
        except Exception:
            logger.exception("Discovery parse failed for %s %s %s", adapter.platform, kind, url)
            continue
    return venues

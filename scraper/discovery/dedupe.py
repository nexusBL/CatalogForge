from __future__ import annotations

from urllib.parse import urlparse

from scraper.discovery.models import DiscoveredVenue
from scraper.discovery.urls import canonical_url


def identity_key(venue: DiscoveredVenue) -> str:
    platform = venue.platform
    if venue.venue_id:
        return f"{platform}:{venue.catalogue_type}:id:{venue.venue_id.strip().lower()}"
    url = canonical_url(venue.canonical_url or venue.venue_url)
    if url and urlparse(url).netloc:
        return f"{platform}:{venue.catalogue_type}:url:{url}"
    name = (venue.name or "").strip().lower()
    place = (venue.location or venue.address or "").strip().lower()
    return f"{platform}:{venue.catalogue_type}:name-place:{name}|{place}"


def dedupe_venues(venues: list[DiscoveredVenue]) -> list[DiscoveredVenue]:
    seen: set[str] = set()
    unique: list[DiscoveredVenue] = []
    for venue in venues:
        key = identity_key(venue)
        venue.identity_key = key
        venue.canonical_url = canonical_url(venue.canonical_url or venue.venue_url)
        if key in seen:
            continue
        seen.add(key)
        unique.append(venue)
    return unique

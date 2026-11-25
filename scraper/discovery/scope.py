from __future__ import annotations

import re
from collections import Counter

from scraper.discovery.fields import is_distance_text
from scraper.discovery.locate import _fold_place
from scraper.discovery.models import DiscoveredVenue, LocationQuery

DiscoveryScope = str
LocationMatch = str

DELIVERY_TO_LOCATION = "delivery_to_location"
PHYSICAL_LOCATION = "physical_location"
LOCATED_HERE = "located_here"
DELIVERS_HERE = "delivers_here"
LOCATION_UNKNOWN = "unknown"

_CITY_SLUG_RE = re.compile(r"/city/([^/]+)/", re.I)
_WORD = re.compile(r"[a-z0-9]+")


def discovery_scope_for(platform: str, catalogue_type: str) -> str | None:
    if platform == "swiggy" and catalogue_type == "restaurant":
        return DELIVERY_TO_LOCATION
    return None


def job_discovery_scope(platforms: list[str], catalogue_type: str) -> str | None:
    kinds = ["restaurant", "dineout"] if catalogue_type == "both" else [catalogue_type]
    scopes = {discovery_scope_for(platform, kind) for platform in platforms for kind in kinds}
    scopes.discard(None)
    if DELIVERY_TO_LOCATION in scopes:
        return DELIVERY_TO_LOCATION
    if PHYSICAL_LOCATION in scopes:
        return PHYSICAL_LOCATION
    return None


def classify_venues(location: LocationQuery, venues: list[DiscoveredVenue]) -> list[DiscoveredVenue]:
    for venue in venues:
        venue.discovery_scope = discovery_scope_for(venue.platform, venue.catalogue_type)
        venue.location_match = classify_venue_location(location, venue)
    return venues


def classify_venue_location(location: LocationQuery, venue: DiscoveredVenue) -> str:
    parts = []
    for part in (venue.location, venue.address):
        if part and not is_distance_text(part):
            parts.append(part)
    hay = _fold_place(" ".join(parts))
    if location.locality:
        if not hay:
            return LOCATION_UNKNOWN
        if _place_token_in(hay, location.locality):
            return LOCATED_HERE
        return DELIVERS_HERE
    city = location.city
    if not city:
        return LOCATION_UNKNOWN if not hay else DELIVERS_HERE
    if hay and _place_token_in(hay, city):
        return LOCATED_HERE
    slug = _CITY_SLUG_RE.search(venue.venue_url or "")
    if slug and _place_token_in(_fold_place(slug.group(1).replace("-", " ")), city):
        return LOCATED_HERE
    if hay:
        return DELIVERS_HERE
    return LOCATION_UNKNOWN


def location_match_counts(venues: list[DiscoveredVenue]) -> dict[str, int]:
    tallies = Counter(item.location_match or LOCATION_UNKNOWN for item in venues)
    return {
        "located_here_count": tallies.get(LOCATED_HERE, 0),
        "delivers_here_count": tallies.get(DELIVERS_HERE, 0),
        "unknown_location_count": tallies.get(LOCATION_UNKNOWN, 0),
    }


def _place_token_in(hay: str, place: str) -> bool:
    token = _fold_place(place)
    if not token or not hay:
        return False
    if " " in token:
        return token in hay
    return token in _WORD.findall(hay)

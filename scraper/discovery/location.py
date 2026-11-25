from __future__ import annotations

import re

from scraper.discovery.models import LocationQuery

_WS = re.compile(r"\s+")
_SLUG = re.compile(r"[^a-z0-9]+")
_PREFIX = re.compile(
    r"^(?:find\s+)?(?:restaurants?|food|places?|cafes?)\s+(?:in|at|near)\s+",
    re.I,
)


def slugify(value: str) -> str:
    text = _SLUG.sub("-", (value or "").strip().lower()).strip("-")
    return text


def parse_location(value: str) -> LocationQuery:
    original = (value or "").strip()
    if not original:
        raise ValueError("Location is required.")
    normalized = _WS.sub(" ", original)
    normalized = _PREFIX.sub("", normalized).strip(" .") or normalized
    parts = [part.strip() for part in re.split(r"[,|/]", normalized) if part.strip()]
    city = None
    state = None
    locality = None
    if len(parts) == 1:
        city = parts[0]
    elif len(parts) == 2:
        city, state = parts[0], parts[1]
    else:
        locality, city, state = parts[0], parts[1], parts[-1]
    slug_source = city or normalized
    query = LocationQuery(
        original=original,
        normalized=normalized,
        city=city,
        state=state,
        locality=locality,
        slug=slugify(slug_source) or slugify(normalized),
    )
    query.search_text = location_search_text(query)
    return query


def location_search_text(location: LocationQuery) -> str:
    if location.city and location.state:
        return f"{location.city}, {location.state}"
    if location.city:
        return location.city
    return location.normalized

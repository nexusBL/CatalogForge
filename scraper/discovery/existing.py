from __future__ import annotations

from typing import Any

from scraper.discovery.models import DiscoveredVenue
from scraper.discovery.urls import canonical_url


def existing_catalogue_id(venue: DiscoveredVenue, catalogues: list[dict[str, Any]]) -> str | None:
    venue_url = canonical_url(venue.canonical_url or venue.venue_url)
    venue_id = (venue.venue_id or "").strip().lower()
    name = (venue.name or "").strip().lower()
    place = (venue.location or venue.address or "").strip().lower()
    for row in catalogues:
        result = row.get("result") if isinstance(row.get("result"), dict) else row
        if not isinstance(result, dict):
            continue
        platform = (result.get("platform") or "").strip().lower()
        if platform and platform != venue.platform:
            continue
        cat_type = (result.get("catalogue_type") or "restaurant").strip().lower()
        if cat_type not in {venue.catalogue_type, "both"}:
            continue
        restaurant = result.get("restaurant") if isinstance(result.get("restaurant"), dict) else {}
        dineout = result.get("dineout") if isinstance(result.get("dineout"), dict) else {}
        stored_id = str(restaurant.get("restaurant_id") or dineout.get("restaurant_id") or "").strip().lower()
        row_id = str(row.get("id") or result.get("id") or "")
        if venue_id and stored_id and venue_id == stored_id:
            return row_id or None
        stored_url = canonical_url(str(result.get("source_url") or dineout.get("source_url") or ""))
        if venue_url and stored_url and venue_url == stored_url:
            return row_id or None
        location = dineout.get("location") if isinstance(dineout.get("location"), dict) else {}
        stored_name = str(
            restaurant.get("name") or dineout.get("venue") or result.get("restaurant_name") or ""
        ).strip().lower()
        stored_place = str(
            restaurant.get("outlet") or location.get("locality") or restaurant.get("address") or ""
        ).strip().lower()
        if name and place and stored_name == name and stored_place == place:
            return row_id or None
    return None


def mark_existing(venues: list[DiscoveredVenue], catalogues: list[dict[str, Any]]) -> list[DiscoveredVenue]:
    for venue in venues:
        found = existing_catalogue_id(venue, catalogues)
        venue.existing_catalogue_id = found
        if found and venue.existing_action is None:
            venue.existing_action = "skip"
    return venues

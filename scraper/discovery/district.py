from __future__ import annotations

from urllib.parse import urlparse

from scraper.discovery.base import HREF_RE, PlatformDiscovery, card_name, make_venue
from scraper.discovery.models import CatalogueKind, DiscoveredVenue, ListingPage, LocationQuery
from scraper.discovery.urls import join_url
from scraper.html_common import venue_html


class DistrictDiscovery(PlatformDiscovery):
    """Zomato District as its own discovery source. Does not invent city slugs."""

    platform = "zomato"

    def listing_urls(self, catalogue_type: CatalogueKind, location: LocationQuery, magicpin_dining: str = "budget") -> list[str]:
        place = (location.platform_places or {}).get("district") or (location.platform_places or {}).get("zomato_district") or {}
        url = place.get("url")
        if place.get("location_verified") and isinstance(url, str) and "district.in" in url.lower():
            return [url]
        return []

    def parse_page(self, page: ListingPage, catalogue_type: CatalogueKind) -> list[DiscoveredVenue]:
        venues: list[DiscoveredVenue] = []
        html = venue_html(page.html or "")
        for href, inner in HREF_RE.findall(html):
            url = join_url(page.url, href).split("?")[0]
            host = (urlparse(url).hostname or "").replace("www.", "").lower()
            if host != "district.in" and not host.endswith(".district.in"):
                continue
            parts = [part for part in urlparse(url).path.split("/") if part]
            if len(parts) < 2:
                continue
            item = make_venue(
                platform="zomato",
                catalogue_type=catalogue_type,
                url=url,
                name=card_name(inner),
                source="district_listing",
                sub_source="district",
            )
            if item:
                venues.append(item)
        return venues

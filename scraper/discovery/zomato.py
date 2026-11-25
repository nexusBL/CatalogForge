from __future__ import annotations

import re

from scraper.discovery.base import HREF_RE, NOISE_RE, PlatformDiscovery, card_name, make_venue, parse_json_blobs, walk
from scraper.discovery.models import CatalogueKind, DiscoveredVenue, ListingPage
from scraper.discovery.urls import join_url
from scraper.html_common import venue_html

VENUE_RE = re.compile(r"^/[^/]+/[^/]+/?$", re.I)
SKIP_SLUGS = {
    "restaurants",
    "order",
    "dine-out",
    "nightlife",
    "drinks",
    "reviews",
    "photos",
    "info",
    "menu",
    "collections",
    "gold",
    "district",
    "cuisines",
    "cuisine",
    "india",
}


class ZomatoDiscovery(PlatformDiscovery):
    platform = "zomato"

    def parse_page(self, page: ListingPage, catalogue_type: CatalogueKind) -> list[DiscoveredVenue]:
        venues: list[DiscoveredVenue] = []
        html = venue_html(page.html or "")
        for blob in parse_json_blobs(html):
            for node in walk(blob):
                venues.extend(self._from_node(node, catalogue_type, page.url))
        if isinstance(page.payload, (dict, list)):
            for node in walk(page.payload):
                venues.extend(self._from_node(node, catalogue_type, page.url))
        for href, inner in HREF_RE.findall(html):
            if NOISE_RE.search(inner):
                continue
            url = join_url(page.url, href).split("?")[0]
            path = _path(url)
            if _skip_url(url, path):
                continue
            parts = [part for part in path.split("/") if part]
            if len(parts) != 2 or parts[1].lower() in SKIP_SLUGS:
                continue
            if catalogue_type == "dineout" and "order" in path.lower():
                continue
            item = make_venue(
                platform="zomato",
                catalogue_type=catalogue_type,
                url=url,
                venue_id=None,
                name=card_name(inner),
                source="zomato_listing",
                sub_source="dineout" if catalogue_type == "dineout" else "restaurant",
            )
            if item:
                venues.append(item)
        return venues

    def _from_node(self, node: dict, catalogue_type: CatalogueKind, base: str) -> list[DiscoveredVenue]:
        if not isinstance(node, dict):
            return []
        url = node.get("url") or node.get("resURL") or node.get("@id")
        name = node.get("name") if isinstance(node.get("name"), str) else None
        if not isinstance(url, str) or "zomato.com" not in url:
            return []
        path = _path(url)
        if _skip_url(url, path):
            return []
        parts = [part for part in path.split("/") if part]
        if len(parts) != 2 or parts[1].lower() in SKIP_SLUGS:
            return []
        res_id = str(node.get("resId") or node.get("id") or "").strip()
        locality = node.get("locality") if isinstance(node.get("locality"), str) else None
        item = make_venue(
            platform="zomato",
            catalogue_type=catalogue_type,
            url=url.split("?")[0],
            venue_id=res_id or None,
            name=name,
            location=locality,
            source="zomato_json",
            sub_source="dineout" if catalogue_type == "dineout" else "restaurant",
        )
        return [item] if item else []


def _path(url: str) -> str:
    from urllib.parse import urlparse

    return urlparse(url).path.rstrip("/")


def _skip_url(url: str, path: str) -> bool:
    lowered = f"{url} {path}".lower()
    if "district.in" in lowered or "/district" in lowered:
        return True
    if "/collections/" in lowered or lowered.endswith("/collections"):
        return True
    if "/cuisine/" in lowered or "/cuisines/" in lowered:
        return True
    return False

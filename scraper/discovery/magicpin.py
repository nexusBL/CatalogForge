from __future__ import annotations

import re

from scraper.discovery.base import HREF_RE, NOISE_RE, PlatformDiscovery, card_name, make_venue, parse_json_blobs, walk
from scraper.discovery.models import CatalogueKind, DiscoveredVenue, ListingPage
from scraper.discovery.urls import join_url
from scraper.html_common import venue_html

STORE_RE = re.compile(r"/Restaurant/[^/]+/store/([A-Za-z0-9]+)", re.I)


class MagicpinDiscovery(PlatformDiscovery):
    platform = "magicpin"

    def parse_page(self, page: ListingPage, catalogue_type: CatalogueKind) -> list[DiscoveredVenue]:
        venues: list[DiscoveredVenue] = []
        html = venue_html(page.html or "")
        for blob in parse_json_blobs(html):
            for node in walk(blob):
                venues.extend(self._from_node(node, catalogue_type, page.url))
        if page.payload is not None:
            for node in walk(page.payload):
                venues.extend(self._from_node(node, catalogue_type, page.url))
        for href, inner in HREF_RE.findall(html):
            if NOISE_RE.search(inner):
                continue
            url = join_url(page.url, href).split("?")[0]
            match = STORE_RE.search(url)
            if not match:
                continue
            if catalogue_type == "restaurant" and "/delivery" not in url.lower():
                url = url.rstrip("/") 
            if catalogue_type == "dineout" and "/delivery" in url.lower():
                url = re.sub(r"/delivery/?$", "", url, flags=re.I)
            item = make_venue(
                platform="magicpin",
                catalogue_type=catalogue_type,
                url=url,
                venue_id=match.group(1),
                name=card_name(inner),
                source="magicpin_listing",
            )
            if item:
                venues.append(item)
        return venues

    def _from_node(self, node: dict, catalogue_type: CatalogueKind, base: str) -> list[DiscoveredVenue]:
        if not isinstance(node, dict):
            return []
        url = node.get("url") or node.get("storeUrl")
        if not isinstance(url, str):
            return []
        match = STORE_RE.search(url)
        if not match:
            return []
        item = make_venue(
            platform="magicpin",
            catalogue_type=catalogue_type,
            url=join_url(base, url).split("?")[0],
            venue_id=match.group(1),
            name=node.get("name") if isinstance(node.get("name"), str) else None,
            location=node.get("locality") if isinstance(node.get("locality"), str) else None,
            source="magicpin_json",
        )
        return [item] if item else []

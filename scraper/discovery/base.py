from __future__ import annotations

import json
import re
from html import unescape
from typing import Any

from scraper.discovery.fields import is_distance_text
from scraper.discovery.models import CatalogueKind, DiscoveredVenue, ListingPage, PlatformName
from scraper.discovery.pagination import listing_exhausted, next_page_url
from scraper.discovery.urls import canonical_url, join_url
from scraper.html_common import venue_html
from scraper.platform import hostname, url_matches_platform

NOISE_RE = re.compile(
    r"similar restaurant|nearby restaurant|more restaurants|sponsored|recommended options|brands near|explore other",
    re.I,
)
HREF_RE = re.compile(r"""<a\b[^>]+href=["']([^"']+)["'][^>]*>(.*?)</a>""", re.I | re.S)
NAME_RE = re.compile(r"<h[1-3][^>]*>(.*?)</h[1-3]>", re.I | re.S)
RATING_RE = re.compile(r"\b([1-5](?:\.\d)?)\b")
TAG_RE = re.compile(r"<[^>]+>")


def visible_text(html: str) -> str:
    return unescape(re.sub(r"\s+", " ", TAG_RE.sub(" ", html or "")).strip())


def parse_json_blobs(html: str) -> list[Any]:
    blobs: list[Any] = []
    for match in re.finditer(
        r'<script[^>]+type=["\']application/(?:json|ld\+json)["\'][^>]*>(.*?)</script>',
        html or "",
        re.I | re.S,
    ):
        raw = match.group(1).strip()
        if not raw:
            continue
        try:
            blobs.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return blobs


def walk(node: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(node, dict):
        found.append(node)
        for value in node.values():
            found.extend(walk(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(walk(item))
    return found


class PlatformDiscovery:
    platform: PlatformName

    def listing_urls(self, catalogue_type: CatalogueKind, location, magicpin_dining: str = "budget") -> list[str]:
        from scraper.discovery.urls import search_urls

        return search_urls(self.platform, catalogue_type, location, magicpin_dining)

    def parse_page(self, page: ListingPage, catalogue_type: CatalogueKind) -> list[DiscoveredVenue]:
        raise NotImplementedError

    def next_url(self, page: ListingPage) -> str | None:
        return page.next_url or next_page_url(page.html, page.url)

    def exhausted(self, page: ListingPage) -> bool:
        if page.exhausted or page.blocked:
            return True
        return listing_exhausted(page.html, self.next_url(page))


def card_name(anchor_html: str, fallback: str | None = None) -> str | None:
    heading = NAME_RE.search(anchor_html)
    text = visible_text(heading.group(1) if heading else anchor_html)
    return text or fallback


def make_venue(
    *,
    platform: PlatformName,
    catalogue_type: CatalogueKind,
    url: str,
    venue_id: str | None = None,
    name: str | None = None,
    location: str | None = None,
    rating: str | None = None,
    address: str | None = None,
    image_url: str | None = None,
    cuisine: str | None = None,
    source: str,
    sub_source: str | None = None,
    distance_km: float | None = None,
) -> DiscoveredVenue | None:
    if sub_source == "district":
        host = hostname(url)
        if not (host == "district.in" or host.endswith(".district.in")):
            return None
    elif not url_matches_platform(platform, url):
        return None
    if re.search(r"best-restaurants|/instamart|/genie", url, re.I):
        return None
    place = None if is_distance_text(location) else location
    street = None if is_distance_text(address) else address
    return DiscoveredVenue(
        platform=platform,
        catalogue_type=catalogue_type,
        venue_url=url,
        canonical_url=canonical_url(url),
        venue_id=venue_id,
        name=name or None,
        location=place or None,
        address=street or None,
        rating=str(rating) if rating not in (None, "") else None,
        image_url=image_url or None,
        cuisine=cuisine or None,
        source=source,
        sub_source=sub_source,
        distance_km=distance_km,
    )

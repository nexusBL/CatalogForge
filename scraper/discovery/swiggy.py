from __future__ import annotations

import re
from typing import Any

from scraper.discovery.base import HREF_RE, NOISE_RE, PlatformDiscovery, card_name, make_venue, parse_json_blobs, walk
from scraper.discovery.fields import distance_km_from_text, is_distance_text
from scraper.discovery.models import CatalogueKind, DiscoveredVenue, ListingPage
from scraper.discovery.urls import join_url
from scraper.html_common import venue_html

REST_RE = re.compile(r"/city/[^/]+/.+-rest(\d+)", re.I)
DINEOUT_RE = re.compile(r"/restaurants/.+/dineout|/city/[^/]+/.+/dineout", re.I)
LISTING_RE = re.compile(
    r"/city/[^/]+/?$|/city/[^/]+/dineout/?$|/city/[^/]+/best-restaurants|/restaurants/?$|/restaurants/[^/]+/?$",
    re.I,
)
SEO_RE = re.compile(r"best-restaurants|/instamart|/genie|/offers-near-me|/food-offer-near-me", re.I)
EMBEDDED_REST_RE = re.compile(
    r"https://www\.swiggy\.com/city/[^\"'\\\s<>]+-rest\d+|\"(/city/[^\"'\\\s]+-rest\d+)\"",
    re.I,
)
CLOUDINARY = "https://media-assets.swiggy.com/swiggy/image/upload/fl_lossy,f_auto,q_auto,w_264/"


class SwiggyDiscovery(PlatformDiscovery):
    platform = "swiggy"

    def parse_page(self, page: ListingPage, catalogue_type: CatalogueKind) -> list[DiscoveredVenue]:
        venues: list[DiscoveredVenue] = []
        html = venue_html(page.html or "")
        payloads, dom_venues = _split_payload(page.payload)
        for blob in payloads:
            for node in walk(blob):
                venues.extend(self._from_node(node, catalogue_type, page.url))
        for blob in parse_json_blobs(html):
            for node in walk(blob):
                venues.extend(self._from_node(node, catalogue_type, page.url))
        for item in dom_venues:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "")
            if not _accept_url(url, catalogue_type):
                continue
            rest = REST_RE.search(url)
            found = make_venue(
                platform="swiggy",
                catalogue_type=catalogue_type,
                url=url.split("?")[0],
                venue_id=rest.group(1) if rest and catalogue_type != "dineout" else None,
                name=item.get("name") if isinstance(item.get("name"), str) else None,
                location=item.get("location") if isinstance(item.get("location"), str) else None,
                rating=item.get("rating"),
                image_url=item.get("image_url") if isinstance(item.get("image_url"), str) else None,
                source="swiggy_dom",
            )
            if found:
                venues.append(found)
        for href, inner in HREF_RE.findall(html):
            url = join_url(page.url, href)
            if LISTING_RE.search(urlparse_path(url)) or SEO_RE.search(url):
                continue
            if NOISE_RE.search(inner) or NOISE_RE.search(url):
                continue
            if not _accept_url(url, catalogue_type):
                continue
            match = REST_RE.search(url)
            item = make_venue(
                platform="swiggy",
                catalogue_type=catalogue_type,
                url=url.split("?")[0],
                venue_id=match.group(1) if match and catalogue_type != "dineout" else None,
                name=card_name(inner),
                source="swiggy_listing",
            )
            if item:
                venues.append(item)
        if catalogue_type == "restaurant":
            for match in EMBEDDED_REST_RE.finditer(html):
                path = match.group(1) or match.group(0)
                url = join_url("https://www.swiggy.com/", path)
                if SEO_RE.search(url) or not REST_RE.search(url):
                    continue
                rest = REST_RE.search(url)
                item = make_venue(
                    platform="swiggy",
                    catalogue_type="restaurant",
                    url=url.split("?")[0],
                    venue_id=rest.group(1) if rest else None,
                    source="swiggy_embedded",
                )
                if item:
                    venues.append(item)
        return _unique(venues)

    def _from_node(self, node: dict, catalogue_type: CatalogueKind, base: str) -> list[DiscoveredVenue]:
        if not isinstance(node, dict):
            return []
        info = node.get("info") if isinstance(node.get("info"), dict) else node
        rest_id = str(info.get("id") or info.get("resId") or node.get("restaurantId") or "").strip()
        name = info.get("name") if isinstance(info.get("name"), str) else None
        locality = _place_name(info.get("locality") or info.get("areaName"))
        address = _place_name(info.get("address") if isinstance(info.get("address"), str) else None)
        distance_km = _listing_distance_km(info)
        rating = info.get("avgRating") or info.get("rating")
        image = _image_url(info)
        if catalogue_type == "dineout":
            url = _dineout_url(info, node, base)
            if not url:
                return []
            item = make_venue(
                platform="swiggy",
                catalogue_type="dineout",
                url=url,
                venue_id=rest_id or None,
                name=name,
                location=locality,
                address=address,
                rating=rating,
                image_url=image,
                source="swiggy_json",
                distance_km=distance_km,
            )
            return [item] if item else []
        url = _restaurant_url(info, node, base)
        if not url:
            return []
        match = REST_RE.search(url)
        item = make_venue(
            platform="swiggy",
            catalogue_type="restaurant",
            url=url,
            venue_id=rest_id or (match.group(1) if match else None),
            name=name,
            location=locality,
            address=address,
            rating=rating,
            image_url=image,
            source="swiggy_json",
            distance_km=distance_km,
        )
        return [item] if item else []


def _split_payload(payload: Any) -> tuple[list[Any], list[dict[str, Any]]]:
    if payload is None:
        return [], []
    if isinstance(payload, dict) and ("api_payloads" in payload or "dom_venues" in payload):
        apis = payload.get("api_payloads") or []
        if not isinstance(apis, list):
            apis = [apis]
        dom = payload.get("dom_venues") or []
        return apis, [item for item in dom if isinstance(item, dict)]
    if isinstance(payload, list):
        return payload, []
    return [payload], []


def _accept_url(url: str, catalogue_type: CatalogueKind) -> bool:
    if SEO_RE.search(url) or LISTING_RE.search(urlparse_path(url)):
        return False
    if catalogue_type == "dineout":
        return bool(DINEOUT_RE.search(url))
    return bool(REST_RE.search(url))


def _link_candidate(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        link = value.get("link") or value.get("text")
        return link if isinstance(link, str) else None
    return None


def _restaurant_url(info: dict[str, Any], node: dict[str, Any], base: str) -> str | None:
    for raw in (
        _link_candidate(info.get("cta")),
        _link_candidate(node.get("cta")),
        info.get("ctaLink"),
        node.get("ctaLink"),
        info.get("slug"),
    ):
        if not isinstance(raw, str):
            continue
        url = join_url(base, raw)
        if REST_RE.search(url) and not SEO_RE.search(url):
            return url.split("?")[0]
    return None


def _dineout_url(info: dict[str, Any], node: dict[str, Any], base: str) -> str | None:
    for raw in (info.get("ctaLink"), node.get("dineoutUrl"), _link_candidate(info.get("cta")), _link_candidate(node.get("cta"))):
        if not isinstance(raw, str):
            continue
        url = join_url(base, raw)
        if DINEOUT_RE.search(url) and not SEO_RE.search(url):
            return url.split("?")[0]
    return None


def _place_name(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip() or is_distance_text(value):
        return None
    return value.strip()


def _listing_distance_km(info: dict[str, Any]) -> float | None:
    sla = info.get("sla") if isinstance(info.get("sla"), dict) else {}
    travel = sla.get("lastMileTravel") if sla.get("lastMileTravel") is not None else info.get("lastMileTravel")
    try:
        if travel not in (None, ""):
            return float(travel)
    except (TypeError, ValueError):
        pass
    text = sla.get("lastMileTravelString") or info.get("lastMileTravelString")
    if isinstance(text, str):
        return distance_km_from_text(text)
    return None


def _image_url(info: dict[str, Any]) -> str | None:
    image = info.get("image") or info.get("cloudinaryImageId")
    if isinstance(image, str) and image.startswith("http"):
        return image
    if isinstance(image, str) and image and " " not in image:
        return CLOUDINARY + image.lstrip("/")
    return None


def urlparse_path(url: str) -> str:
    from urllib.parse import urlparse

    return urlparse(url).path


def _unique(venues: list[DiscoveredVenue]) -> list[DiscoveredVenue]:
    seen: set[str] = set()
    out: list[DiscoveredVenue] = []
    for item in venues:
        key = (item.canonical_url or item.venue_url).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out

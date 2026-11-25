from __future__ import annotations

from urllib.parse import urljoin, urlparse, urlunparse

from scraper.discovery.location import location_search_text, slugify
from scraper.discovery.models import CatalogueKind, LocationQuery, PlatformName
from scraper.platform import platform_from_url, url_matches_platform

SWIGGY_HOME = "https://www.swiggy.com/"
SWIGGY_FOOD_NEAR_ME = "https://www.swiggy.com/food-offer-near-me"
SWIGGY_RESTAURANTS = "https://www.swiggy.com/restaurants"
SWIGGY_DINEOUT_NEAR_ME = "https://www.swiggy.com/offers-near-me"
SWIGGY_DINEOUT = "https://www.swiggy.com/dineout"
MAGICPIN_HOME = "https://magicpin.in/india/Bangalore/home/"
ZOMATO_HOME = "https://www.zomato.com/"
ZOMATO_RESTAURANTS = "https://www.zomato.com/mangalore/restaurants"


def canonical_url(url: str) -> str:
    parsed = urlparse((url or "").strip())
    path = (parsed.path or "/").rstrip("/") or "/"
    return urlunparse((parsed.scheme.lower() or "https", parsed.netloc.lower(), path, "", "", ""))


def city_slug(location: LocationQuery) -> str:
    return location.slug or slugify(location.city or location.normalized)


def search_urls(
    platform: PlatformName,
    catalogue_type: CatalogueKind,
    location: LocationQuery,
    magicpin_dining: str = "budget",
) -> list[str]:
    if platform == "swiggy":
        if catalogue_type == "dineout":
            return [SWIGGY_DINEOUT]
        return [SWIGGY_RESTAURANTS]
    if platform == "zomato":
        # Bare https://www.zomato.com/ does not load reliably. Open a real Zomato
        # listing page, then use the header location control. Do not rewrite mangalore.
        return [ZOMATO_RESTAURANTS]
    return [MAGICPIN_HOME]


def assert_platform_url(platform: PlatformName, url: str) -> None:
    if not url_matches_platform(platform, url):
        raise ValueError(f"URL is not a {platform} venue URL: {url}")
    found = platform_from_url(url)
    if found and found != platform:
        raise ValueError(f"URL platform {found} does not match selected platform {platform}.")


def join_url(base: str, href: str) -> str:
    return urljoin(base, href)


def picker_query(location: LocationQuery) -> str:
    if location.locality and location.city and location.state:
        return f"{location.locality}, {location.city}, {location.state}"
    return (location.normalized or location.search_text or location_search_text(location)).strip()


def type_query(location: LocationQuery) -> str:
    """What a human types into the website location box (area, else city)."""
    if location.locality and location.locality.strip():
        return location.locality.strip()
    if location.city and location.city.strip():
        return location.city.strip()
    return picker_query(location)

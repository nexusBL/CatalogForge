from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.error import URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from scraper.discovery.location import location_search_text, parse_location, slugify
from scraper.discovery.locate import _fold_place
from scraper.discovery.models import LocationQuery

_PREFIX = re.compile(
    r"^(?:find\s+)?(?:restaurants?|food|places?|cafes?)\s+(?:in|at|near)\s+",
    re.I,
)
_CACHE_PATH = Path("data/location-cache.json")


class AmbiguousLocationError(ValueError):
    pass


class LocationProvider(Protocol):
    """Geocoding/search backend. Results must be Nominatim-shaped dicts."""

    def search(self, query: str) -> list[dict[str, Any]]:
        ...


Geocoder = LocationProvider

_CANONICAL_CITIES = {
    "bangalore": "Bengaluru",
    "bengaluru": "Bengaluru",
    "mangalore": "Mangaluru",
    "mangaluru": "Mangaluru",
}
_CITY_ALIASES = {
    "bangalore": {"bangalore", "bengaluru"},
    "bengaluru": {"bangalore", "bengaluru"},
    "mangalore": {"mangalore", "mangaluru"},
    "mangaluru": {"mangalore", "mangaluru"},
}
_ZOMATO_SLUG_SKIP = {"india", "web", "offline", "restaurants", "order", "dine-out", "gold", "who-we-are"}


@dataclass
class NominatimProvider:
    endpoint: str = "https://nominatim.openstreetmap.org/search"
    user_agent: str = "CatalogForge/HectoBaba (location-resolver)"
    timeout: int = 12

    def search(self, query: str) -> list[dict[str, Any]]:
        params = urlencode(
            {
                "q": query,
                "format": "jsonv2",
                "addressdetails": 1,
                "limit": 8,
                "countrycodes": "in",
            }
        )
        request = Request(
            f"{self.endpoint}?{params}",
            headers={"User-Agent": self.user_agent, "Accept": "application/json"},
        )
        with urlopen(request, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return payload if isinstance(payload, list) else []


NominatimGeocoder = NominatimProvider


@dataclass
class GoogleProvider:
    api_key: str
    endpoint: str = "https://maps.googleapis.com/maps/api/geocode/json"
    timeout: int = 12

    def search(self, query: str) -> list[dict[str, Any]]:
        params = urlencode({"address": query, "key": self.api_key, "region": "in", "components": "country:IN"})
        request = Request(f"{self.endpoint}?{params}", headers={"Accept": "application/json"})
        with urlopen(request, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        rows = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            return []
        return [normalize_google_result(item) for item in rows if isinstance(item, dict)]

    def autocomplete(self, query: str) -> list[dict[str, Any]]:
        """Google Places Autocomplete (India). Does not replace search()/geocoding."""
        params = urlencode(
            {
                "input": query,
                "key": self.api_key,
                "components": "country:in",
                "types": "(regions)",
            }
        )
        request = Request(
            f"https://maps.googleapis.com/maps/api/place/autocomplete/json?{params}",
            headers={"Accept": "application/json"},
        )
        with urlopen(request, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        rows = payload.get("predictions") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            return []
        return [normalize_places_prediction(item) for item in rows if isinstance(item, dict)]


GoogleGeocoder = GoogleProvider


@dataclass
class MapboxProvider:
    access_token: str
    endpoint: str = "https://api.mapbox.com/geocoding/v5/mapbox.places"
    timeout: int = 12

    def search(self, query: str) -> list[dict[str, Any]]:
        from urllib.parse import quote

        encoded = quote(query)
        url = f"{self.endpoint}/{encoded}.json?{urlencode({'access_token': self.access_token, 'country': 'IN', 'limit': 8})}"
        request = Request(url, headers={"Accept": "application/json"})
        with urlopen(request, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        rows = payload.get("features") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            return []
        return [normalize_mapbox_result(item) for item in rows if isinstance(item, dict)]


MapboxGeocoder = MapboxProvider


class FileLocationCache:
    def __init__(self, path: Path | None = None):
        self.path = path or _CACHE_PATH
        self._data: dict[str, Any] = {}
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self._data = {}

    def get(self, key: str) -> dict[str, Any] | None:
        item = self._data.get(_fold_place(key))
        return item if isinstance(item, dict) else None

    def set(self, key: str, value: dict[str, Any]) -> None:
        self._data[_fold_place(key)] = value
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, ensure_ascii=True, indent=2), encoding="utf-8")


def clean_location_query(query: str) -> str:
    text = re.sub(r"\s+", " ", (query or "").strip())
    return _PREFIX.sub("", text).strip(" .")


def select_location_provider(*, pytest_guard: bool = True) -> LocationProvider | None:
    if pytest_guard and os.getenv("PYTEST_CURRENT_TEST"):
        return None
    mode = (os.getenv("CATALOGFORGE_GEOCODER") or "").strip().lower()
    if mode in {"off", "none", "parse"}:
        return None
    google_key = (os.getenv("GOOGLE_MAPS_API_KEY") or os.getenv("GOOGLE_GEOCODING_API_KEY") or "").strip()
    mapbox_token = (os.getenv("MAPBOX_ACCESS_TOKEN") or os.getenv("MAPBOX_TOKEN") or "").strip()
    if mode in {"google", "maps"}:
        return GoogleProvider(api_key=google_key) if google_key else NominatimProvider()
    if mode == "mapbox":
        return MapboxProvider(access_token=mapbox_token) if mapbox_token else NominatimProvider()
    if mode in {"", "auto"} and google_key:
        return GoogleProvider(api_key=google_key)
    if mode in {"", "auto"} and mapbox_token:
        return MapboxProvider(access_token=mapbox_token)
    return NominatimProvider()


def default_geocoder() -> LocationProvider | None:
    return select_location_provider()


class LocationResolver:
    def __init__(self, provider: LocationProvider | None = None, cache: FileLocationCache | None = None):
        self.provider = provider
        self.cache = cache

    def resolve(self, query: str) -> LocationQuery:
        return resolve_location(query, geocoder=self.provider, cache=self.cache)


def resolve_location(
    query: str,
    *,
    geocoder: Geocoder | None = None,
    cache: FileLocationCache | None = None,
) -> LocationQuery:
    cleaned = clean_location_query(query)
    parsed = parse_location(cleaned or query)
    engine = geocoder if geocoder is not None else default_geocoder()
    store = cache
    if engine is None:
        return parsed
    if store:
        hit = store.get(cleaned)
        if hit:
            return location_from_dict(hit, original=query)
    try:
        rows = engine.search(_search_text(parsed, cleaned))
    except (URLError, TimeoutError, json.JSONDecodeError, OSError):
        return parsed
    chosen = _choose_hit(rows, parsed)
    resolved = _from_geocode(query, cleaned, parsed, chosen)
    if store:
        store.set(cleaned, resolved.to_dict())
    return resolved


def apply_platform_place(
    location: LocationQuery,
    platform: str,
    *,
    city: str | None = None,
    slug: str | None = None,
    verified: bool = False,
    url: str | None = None,
    location_id: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
) -> LocationQuery:
    places = dict(location.platform_places or {})
    places[platform] = {
        "canonical_city": location.city,
        "city": city or location.city,
        "slug": slug,
        "location_verified": verified,
        "url": url,
        "location_id": location_id,
        "latitude": latitude,
        "longitude": longitude,
    }
    location.platform_places = places
    return location


def platform_place_matches_canonical(location: LocationQuery, inferred: dict[str, Any]) -> bool:
    slug = _fold_place(str(inferred.get("slug") or ""))
    city_name = _fold_place(str(inferred.get("city") or ""))
    wanted = {_fold_place(location.city or ""), _fold_place(location.locality or "")}
    wanted.update(_CITY_ALIASES.get(_fold_place(location.city or ""), set()))
    wanted.discard("")
    if slug and (slug in wanted or slug.replace("-", " ") in wanted or slug.replace("-", "") in {item.replace(" ", "") for item in wanted}):
        return True
    if city_name and city_name in wanted:
        return True
    return False


class PlatformLocationResolver:
    def bind(
        self,
        location: LocationQuery,
        platform: str,
        *,
        html: str = "",
        page_url: str = "",
        strict: bool = False,
    ) -> LocationQuery:
        inferred = infer_platform_place_from_html(html, page_url, platform) if html or page_url else None
        if not inferred:
            return location
        verified = platform_place_matches_canonical(location, inferred)
        key = "district" if "district.in" in str(inferred.get("url") or "").lower() else platform
        apply_platform_place(
            location,
            key,
            city=inferred.get("city"),
            slug=inferred.get("slug"),
            verified=verified,
            url=inferred.get("url"),
        )
        if strict and not verified:
            from scraper.discovery.locate import LocationSelectionError

            raise LocationSelectionError(
                f"Platform {key} selected {inferred.get('slug') or inferred.get('city')}, "
                f"which does not match requested {location.city or location.normalized}. "
                "Discovery stopped to avoid scraping a stale or wrong city."
            )
        return location


def platform_slug_from_url(url: str, platform: str) -> str | None:
    parsed = urlparse(url or "")
    parts = [part for part in (parsed.path or "").split("/") if part]
    host = (parsed.hostname or "").replace("www.", "").lower()
    if host.endswith("district.in") or platform in {"district", "zomato_district"}:
        return parts[0].lower() if parts else None
    if not parts:
        return None
    if platform == "zomato":
        if parts[0].lower() in _ZOMATO_SLUG_SKIP:
            return None
        return parts[0].lower()
    if platform == "magicpin":
        first = parts[0].lower()
        if first in {"category", "store"}:
            return None
        return first
    if platform == "swiggy" and len(parts) >= 2 and parts[0].lower() == "city":
        return parts[1].lower()
    return None


def infer_platform_place_from_html(html: str, base_url: str, platform: str) -> dict[str, Any] | None:
    match = re.search(r"""<link[^>]+rel=["']canonical["'][^>]+href=["']([^"']+)["']""", html or "", re.I)
    if not match:
        match = re.search(
            r"""href=["'](https://(?:www\.)?(?:zomato\.com|magicpin\.in|district\.in)/[^"'\s]+)["']""",
            html or "",
            re.I,
        )
    url = match.group(1) if match else base_url
    key = platform
    host = urlparse(url).hostname or ""
    if "district.in" in host.lower():
        key = "district"
    slug = platform_slug_from_url(url, key if key == "district" else platform)
    if not slug:
        return None
    return {"city": slug.replace("-", " "), "slug": slug, "location_verified": False, "url": url}


def coords_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * radius * math.asin(min(1.0, math.sqrt(a)))


def rewrite_city_token(text: str, old: str, new: str) -> str:
    """Forbidden helper — tests assert discovery does not use this for URLs."""
    return (text or "").replace(old, new)


def location_from_dict(data: dict[str, Any], original: str | None = None) -> LocationQuery:
    query = LocationQuery(
        original=original or data.get("original") or "",
        normalized=data.get("normalized") or "",
        city=data.get("city"),
        state=data.get("state"),
        locality=data.get("locality") or data.get("area"),
        slug=data.get("slug") or "",
        search_text=data.get("search_text") or "",
        country=data.get("country"),
        postal_code=data.get("postal_code"),
        latitude=data.get("latitude"),
        longitude=data.get("longitude"),
        display_name=data.get("display_name"),
        confidence=data.get("confidence"),
        place_id=data.get("place_id"),
        platform_places=dict(data.get("platform_places") or data.get("platforms") or {}),
    )
    return query


def _search_text(parsed: LocationQuery, cleaned: str) -> str:
    if parsed.city and parsed.state:
        return f"{parsed.locality + ', ' if parsed.locality else ''}{parsed.city}, {parsed.state}, India"
    if parsed.city:
        return f"{parsed.city}, India"
    return f"{cleaned}, India"


def _choose_hit(rows: list[dict[str, Any]], parsed: LocationQuery) -> dict[str, Any]:
    india = []
    for row in rows:
        address = row.get("address") if isinstance(row.get("address"), dict) else {}
        country = str(address.get("country") or row.get("display_name") or "")
        if _fold_place(country) and "india" not in _fold_place(country):
            continue
        india.append(row)
    pool = india or list(rows)
    if parsed.state:
        matched = [row for row in pool if _fold_place(parsed.state) in _fold_place(_state_of(row))]
        if matched:
            pool = matched
    if parsed.city:
        named = [row for row in pool if _fold_place(parsed.city) in _fold_place(_city_of(row) + " " + str(row.get("display_name") or ""))]
        if named:
            pool = named
    if parsed.locality:
        local = [row for row in pool if _fold_place(parsed.locality) in _fold_place(str(row.get("display_name") or "") + " " + _city_of(row))]
        if local:
            pool = local
    if len(pool) > 1:
        cities = {_fold_place(_city_of(row)) for row in pool}
        states = {_fold_place(_state_of(row)) for row in pool}
        if len(cities) > 1 or (len(states) > 1 and not parsed.state):
            names = ", ".join(str(row.get("display_name") or _city_of(row)) for row in pool[:4])
            raise AmbiguousLocationError(
                "Multiple locations match this query. Add city/state (for example: Puttur, Karnataka). "
                f"Candidates: {names}"
            )
    if not pool:
        raise AmbiguousLocationError("No location in India matched this query.")
    return pool[0]


def _city_of(row: dict[str, Any]) -> str:
    address = row.get("address") if isinstance(row.get("address"), dict) else {}
    for key in ("city", "town", "village", "county", "state_district"):
        value = address.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _state_of(row: dict[str, Any]) -> str:
    address = row.get("address") if isinstance(row.get("address"), dict) else {}
    value = address.get("state")
    return value.strip() if isinstance(value, str) else ""


def _from_geocode(original: str, cleaned: str, parsed: LocationQuery, row: dict[str, Any]) -> LocationQuery:
    address = row.get("address") if isinstance(row.get("address"), dict) else {}
    geo_city = _city_of(row) or parsed.city
    state = _state_of(row) or parsed.state
    locality = parsed.locality
    suburb = address.get("suburb") or address.get("neighbourhood") or address.get("city_district")
    suburb = suburb.strip() if isinstance(suburb, str) else ""
    if not locality and suburb and geo_city and _fold_place(suburb) != _fold_place(geo_city):
        if parsed.city and _fold_place(parsed.city) == _fold_place(suburb):
            locality = suburb
        elif not parsed.state and parsed.city and _fold_place(parsed.city) == _fold_place(suburb):
            locality = suburb
    if not locality and parsed.city and geo_city and _fold_place(parsed.city) != _fold_place(geo_city):
        locality = parsed.city
        # "Indiranagar" parsed as city, OSM city is Bengaluru
    city = canonical_city_name(geo_city)
    if parsed.locality:
        locality = parsed.locality
        if parsed.city:
            city = parsed.city if geo_city and _fold_place(parsed.city) != _fold_place(parsed.locality) else (geo_city or parsed.city)
            city = canonical_city_name(city)
    country = address.get("country") if isinstance(address.get("country"), str) else "India"
    lat = float(row["lat"]) if row.get("lat") not in (None, "") else None
    lng = float(row["lon"]) if row.get("lon") not in (None, "") else None
    query = LocationQuery(
        original=original,
        normalized=cleaned,
        city=city,
        state=state,
        locality=locality,
        slug=slugify(city or cleaned),
        country=country or "India",
        postal_code=str(address["postcode"]) if address.get("postcode") else None,
        latitude=lat,
        longitude=lng,
        display_name=str(row.get("display_name") or ""),
        confidence="high" if float(row.get("importance") or 1) >= 0.3 else "medium",
        place_id=str(row["place_id"]) if row.get("place_id") not in (None, "") else None,
        platform_places={},
    )
    query.search_text = location_search_text(query)
    return query


def canonical_city_name(name: str | None) -> str | None:
    if not name or not str(name).strip():
        return name
    mapped = _CANONICAL_CITIES.get(_fold_place(name))
    return mapped or str(name).strip()


def normalize_google_result(result: dict[str, Any]) -> dict[str, Any]:
    address: dict[str, str] = {}
    for component in result.get("address_components") or []:
        if not isinstance(component, dict):
            continue
        types = component.get("types") or []
        name = component.get("long_name")
        if not isinstance(name, str) or not name.strip():
            continue
        if "locality" in types:
            address["city"] = name
        elif "administrative_area_level_1" in types:
            address["state"] = name
        elif "country" in types:
            address["country"] = name
        elif "postal_code" in types:
            address["postcode"] = name
        elif "sublocality" in types or "sublocality_level_1" in types:
            address.setdefault("suburb", name)
        elif "neighborhood" in types:
            address.setdefault("neighbourhood", name)
    location = (result.get("geometry") or {}).get("location") if isinstance(result.get("geometry"), dict) else {}
    location = location if isinstance(location, dict) else {}
    return {
        "lat": location.get("lat"),
        "lon": location.get("lng"),
        "display_name": result.get("formatted_address"),
        "place_id": result.get("place_id"),
        "importance": 0.55,
        "address": address,
    }


def normalize_mapbox_result(feature: dict[str, Any]) -> dict[str, Any]:
    address: dict[str, str] = {}
    context = feature.get("context") if isinstance(feature.get("context"), list) else []
    for item in context:
        if not isinstance(item, dict):
            continue
        ident = str(item.get("id") or "")
        text = item.get("text")
        if not isinstance(text, str):
            continue
        if ident.startswith("place"):
            address["city"] = text
        elif ident.startswith("region"):
            address["state"] = text
        elif ident.startswith("country"):
            address["country"] = text
        elif ident.startswith("postcode"):
            address["postcode"] = text
        elif ident.startswith("neighborhood") or ident.startswith("locality"):
            address.setdefault("suburb", text)
    center = feature.get("center") if isinstance(feature.get("center"), list) else []
    lng = center[0] if len(center) >= 2 else None
    lat = center[1] if len(center) >= 2 else None
    text = feature.get("text") if isinstance(feature.get("text"), str) else None
    if text and "city" not in address:
        address["city"] = text
    return {
        "lat": lat,
        "lon": lng,
        "display_name": feature.get("place_name"),
        "place_id": feature.get("id"),
        "importance": 0.5,
        "address": address,
    }


def normalize_places_prediction(prediction: dict[str, Any]) -> dict[str, Any]:
    terms = prediction.get("terms") if isinstance(prediction.get("terms"), list) else []
    city = ""
    state = ""
    if terms:
        city = str(terms[0].get("value") or "") if isinstance(terms[0], dict) else ""
        if len(terms) > 1 and isinstance(terms[1], dict):
            state = str(terms[1].get("value") or "")
    return {
        "description": prediction.get("description"),
        "place_id": prediction.get("place_id"),
        "types": prediction.get("types") or [],
        "city": city,
        "state": state,
    }


def place_predictions(query: str, provider: LocationProvider | None = None) -> list[dict[str, Any]]:
    engine = provider if provider is not None else default_geocoder()
    autocomplete = getattr(engine, "autocomplete", None)
    if not callable(autocomplete):
        return []
    try:
        rows = autocomplete(query)
    except (URLError, TimeoutError, json.JSONDecodeError, OSError):
        return []
    return rows if isinstance(rows, list) else []

from pathlib import Path

import pytest

from scraper.discovery.location import parse_location
from scraper.discovery.place_meta import extract_zomato_place
from scraper.discovery.resolver import (
    AmbiguousLocationError,
    FileLocationCache,
    apply_platform_place,
    infer_platform_place_from_html,
    platform_slug_from_url,
    resolve_location,
    rewrite_city_token,
)
from scraper.discovery.urls import ZOMATO_HOME, ZOMATO_RESTAURANTS, search_urls

FIXTURES = Path(__file__).parent / "fixtures"


class FakeGeocoder:
    def __init__(self, rows):
        self.rows = rows
        self.queries: list[str] = []

    def search(self, query: str):
        self.queries.append(query)
        return list(self.rows)


def _puttur_row(**extra):
    row = {
        "lat": "12.7667",
        "lon": "75.2167",
        "importance": 0.6,
        "display_name": "Puttur, Dakshina Kannada, Karnataka, India",
        "address": {"town": "Puttur", "state": "Karnataka", "country": "India", "postcode": "574201"},
    }
    row.update(extra)
    return row


def test_puttur_resolves_to_karnataka_india():
    geo = FakeGeocoder([_puttur_row()])
    found = resolve_location("Puttur", geocoder=geo)
    assert found.city == "Puttur"
    assert found.state == "Karnataka"
    assert found.country == "India"
    assert found.locality is None
    assert found.latitude == pytest.approx(12.7667)
    assert found.longitude == pytest.approx(75.2167)
    assert "Karnataka" in (geo.queries[0] or "") or "Puttur" in geo.queries[0]


def test_puttur_karnataka_and_restaurants_in_prefix():
    geo = FakeGeocoder([_puttur_row()])
    found = resolve_location("restaurants in Puttur", geocoder=geo)
    assert found.city == "Puttur"
    assert found.state == "Karnataka"
    two = resolve_location("Puttur, Karnataka", geocoder=FakeGeocoder([_puttur_row()]))
    assert two.city == "Puttur"
    assert two.state == "Karnataka"


def test_indiranagar_resolves_area_under_bengaluru():
    geo = FakeGeocoder(
        [
            {
                "lat": "12.9784",
                "lon": "77.6408",
                "importance": 0.5,
                "display_name": "Indiranagar, Bengaluru, Karnataka, India",
                "address": {
                    "suburb": "Indiranagar",
                    "city": "Bengaluru",
                    "state": "Karnataka",
                    "country": "India",
                },
            }
        ]
    )
    found = resolve_location("restaurants in Indiranagar", geocoder=geo)
    assert found.locality == "Indiranagar"
    assert found.city == "Bengaluru"
    assert found.state == "Karnataka"
    three = resolve_location("Indiranagar, Bengaluru, Karnataka", geocoder=geo)
    assert three.locality == "Indiranagar"
    assert three.city == "Bengaluru"


def test_ambiguous_puttur_without_state_stops():
    geo = FakeGeocoder(
        [
            _puttur_row(),
            {
                "lat": "18.78",
                "lon": "82.97",
                "display_name": "Puttur, Andhra Pradesh, India",
                "address": {"town": "Puttur", "state": "Andhra Pradesh", "country": "India"},
            },
        ]
    )
    with pytest.raises(AmbiguousLocationError):
        resolve_location("Puttur", geocoder=geo)
    chosen = resolve_location("Puttur, Karnataka", geocoder=geo)
    assert chosen.state == "Karnataka"


def test_stale_city_is_not_string_replaced_into_urls():
    mangalore_url = "https://www.zomato.com/mangalore/dine-out"
    assert rewrite_city_token(mangalore_url, "mangalore", "puttur") == "https://www.zomato.com/puttur/dine-out"
    location = parse_location("Puttur, Karnataka")
    assert search_urls("zomato", "dineout", location) == [ZOMATO_RESTAURANTS]
    apply_platform_place(location, "zomato", city="Puttur", slug="puttur", verified=True)
    assert search_urls("zomato", "dineout", location) == [ZOMATO_RESTAURANTS]
    assert "puttur" not in search_urls("zomato", "dineout", location)[0]


def test_bengaluru_platform_slug_comes_from_canonical_not_slugify():
    html = '<link rel="canonical" href="https://www.zomato.com/bangalore/dine-out">'
    place = infer_platform_place_from_html(html, ZOMATO_HOME, "zomato")
    assert place and place["slug"] == "bangalore"
    location = parse_location("Bengaluru, Karnataka")
    assert location.city == "Bengaluru"
    apply_platform_place(location, "zomato", city="Bengaluru", slug=place["slug"], verified=True)
    assert location.city == "Bengaluru"
    assert location.platform_places["zomato"]["slug"] == "bangalore"
    assert platform_slug_from_url("https://www.swiggy.com/city/bangalore/x-rest1", "swiggy") == "bangalore"


def test_location_cache_avoids_repeat_geocode(tmp_path):
    cache = FileLocationCache(tmp_path / "cache.json")
    geo = FakeGeocoder([_puttur_row()])
    first = resolve_location("Puttur, Karnataka", geocoder=geo, cache=cache)
    second = resolve_location("Puttur, Karnataka", geocoder=geo, cache=cache)
    assert first.city == second.city == "Puttur"
    assert len(geo.queries) == 1


def test_zomato_json_ld_and_breadcrumbs_are_cheap_place_metadata():
    html = (FIXTURES / "discovery_zomato_jsonld.html").read_text(encoding="utf-8")
    place = extract_zomato_place(html)
    assert place["locality"] == "Balmatta, Mangalore"
    assert place["region"] == "Mangalore"
    assert place["country"] == "India"
    assert place["latitude"] == pytest.approx(12.8732)
    assert place["longitude"] == pytest.approx(74.8429)
    assert "Mangalore" in place["breadcrumbs"]
    from scraper.discovery.scope import DELIVERS_HERE, classify_venue_location
    from scraper.discovery.models import DiscoveredVenue

    requested = parse_location("Indiranagar, Bengaluru, Karnataka")
    venue = DiscoveredVenue(
        "zomato",
        "dineout",
        "https://www.zomato.com/mangalore/example",
        location=place["locality"],
        address=place["locality"],
    )
    assert classify_venue_location(requested, venue) == DELIVERS_HERE


def test_swiggy_listing_pin_must_be_near_resolved_coordinates():
    from scraper.discovery.resolver import coords_km

    puttur = (12.7667, 75.2167)
    bangalore = (12.9784, 77.6408)
    assert coords_km(*puttur, *puttur) < 1
    assert coords_km(*puttur, *bangalore) > 75


def test_bangalore_canonicalizes_to_bengaluru():
    geo = FakeGeocoder(
        [
            {
                "lat": "12.97",
                "lon": "77.59",
                "importance": 0.8,
                "display_name": "Bengaluru, Karnataka, India",
                "address": {"city": "Bengaluru", "state": "Karnataka", "country": "India"},
            }
        ]
    )
    found = resolve_location("Bangalore, Karnataka", geocoder=geo)
    assert found.city == "Bengaluru"
    assert found.state == "Karnataka"


def test_google_result_normalizes_to_nominatim_shape():
    from scraper.discovery.resolver import normalize_google_result

    row = normalize_google_result(
        {
            "place_id": "ChIJputtur",
            "formatted_address": "Puttur, Karnataka, India",
            "geometry": {"location": {"lat": 12.76, "lng": 75.21}},
            "address_components": [
                {"long_name": "Puttur", "types": ["locality"]},
                {"long_name": "Karnataka", "types": ["administrative_area_level_1"]},
                {"long_name": "India", "types": ["country"]},
            ],
        }
    )
    found = resolve_location("Puttur, Karnataka", geocoder=FakeGeocoder([row]))
    assert found.city == "Puttur"
    assert found.state == "Karnataka"
    assert found.place_id == "ChIJputtur"


def test_select_provider_prefers_google_when_key_present(monkeypatch):
    from scraper.discovery.resolver import GoogleProvider, NominatimProvider, select_location_provider

    monkeypatch.setenv("CATALOGFORGE_GEOCODER", "auto")
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "test-key")
    monkeypatch.delenv("MAPBOX_ACCESS_TOKEN", raising=False)
    chosen = select_location_provider(pytest_guard=False)
    assert isinstance(chosen, GoogleProvider)
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY")
    monkeypatch.setenv("CATALOGFORGE_GEOCODER", "nominatim")
    assert isinstance(select_location_provider(pytest_guard=False), NominatimProvider)


def test_stale_mangalore_platform_city_is_not_verified_for_puttur():
    from scraper.discovery.resolver import PlatformLocationResolver

    location = parse_location("Puttur, Karnataka")
    html = '<link rel="canonical" href="https://www.zomato.com/mangalore/dine-out">'
    bound = PlatformLocationResolver().bind(location, "zomato", html=html, page_url="https://www.zomato.com/")
    assert bound.platform_places["zomato"]["location_verified"] is False
    assert bound.platform_places["zomato"]["slug"] == "mangalore"
    assert search_urls("zomato", "dineout", bound) == [ZOMATO_RESTAURANTS]
    with pytest.raises(Exception):
        PlatformLocationResolver().bind(
            parse_location("Puttur, Karnataka"),
            "zomato",
            html=html,
            page_url="https://www.zomato.com/",
            strict=True,
        )


def test_distance_text_never_becomes_place_fields():
    from scraper.discovery.base import make_venue
    from scraper.discovery.fields import is_distance_text, platform_url_fields
    from scraper.discovery.scope import LOCATION_UNKNOWN, classify_venue_location

    assert is_distance_text("2.4 km")
    assert is_distance_text("1.8 km away")
    venue = make_venue(
        platform="swiggy",
        catalogue_type="restaurant",
        url="https://www.swiggy.com/city/bangalore/example-rest1",
        location="2.4 km",
        address="5 km",
        source="test",
        distance_km=2.4,
    )
    assert venue is not None
    assert venue.location is None
    assert venue.address is None
    assert venue.distance_km == 2.4
    requested = parse_location("Indiranagar, Bengaluru, Karnataka")
    assert classify_venue_location(requested, venue) == LOCATION_UNKNOWN
    slots = platform_url_fields("https://www.zomato.com/bangalore/example")
    assert slots["swiggy_url"] is None
    assert slots["zomato_url"] == "https://www.zomato.com/bangalore/example"
    wrong = platform_url_fields("https://www.zomato.com/bangalore/example", {"swiggy_url": "https://www.zomato.com/bangalore/example"})
    assert wrong["swiggy_url"] is None
    assert wrong["zomato_url"].endswith("/example")


def test_jp_nagar_geocode_keeps_area_and_bengaluru_city():
    geo = FakeGeocoder(
        [
            {
                "lat": "12.907",
                "lon": "77.585",
                "importance": 0.5,
                "display_name": "JP Nagar, Bengaluru, Karnataka, India",
                "address": {
                    "suburb": "JP Nagar",
                    "city": "Bengaluru",
                    "state": "Karnataka",
                    "country": "India",
                },
            }
        ]
    )
    found = resolve_location("JP Nagar, Bengaluru, Karnataka", geocoder=geo)
    assert found.locality == "JP Nagar"
    assert found.city == "Bengaluru"
    assert found.state == "Karnataka"
    assert found.country == "India"


def test_google_places_autocomplete_shape_is_separate_from_geocoding():
    from scraper.discovery.resolver import normalize_places_prediction, place_predictions

    row = normalize_places_prediction(
        {
            "description": "Puttur, Karnataka, India",
            "place_id": "ChIJ-puttur",
            "types": ["locality", "political"],
            "terms": [{"value": "Puttur"}, {"value": "Karnataka"}, {"value": "India"}],
        }
    )
    assert row["place_id"] == "ChIJ-puttur"
    assert row["city"] == "Puttur"
    assert row["state"] == "Karnataka"

    class FakePlaces:
        def search(self, query):
            return []

        def autocomplete(self, query):
            return [row]

    found = place_predictions("Puttur", provider=FakePlaces())
    assert found[0]["description"] == "Puttur, Karnataka, India"


def test_district_has_no_invented_url_and_keeps_own_domain():
    from scraper.discovery.district import DistrictDiscovery
    from scraper.discovery.models import ListingPage
    from scraper.discovery.resolver import apply_platform_place

    location = parse_location("Bengaluru, Karnataka")
    adapter = DistrictDiscovery()
    assert adapter.listing_urls("dineout", location) == []
    apply_platform_place(
        location,
        "district",
        city="Bengaluru",
        slug="bangalore",
        verified=True,
        url="https://www.district.in/bangalore",
    )
    assert adapter.listing_urls("dineout", location) == ["https://www.district.in/bangalore"]
    page = ListingPage(
        url="https://www.district.in/bangalore",
        html='<a href="https://www.district.in/bangalore/some-event">Event</a><a href="https://www.zomato.com/bangalore/place">Zomato</a>',
    )
    venues = adapter.parse_page(page, "dineout")
    assert venues
    assert all("district.in" in item.venue_url for item in venues)
    assert all(item.sub_source == "district" for item in venues)
    assert all("zomato.com" not in item.venue_url for item in venues)


from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app, get_swiggy_access, require_session
from backend.schemas import AuthUser, CatalogCreateRequest
from backend.services.area_service import create_area_job, scrape_area_batch, start_area_scrape
from backend.services.catalog_service import AccessResult, SwiggyAccess
from scraper.discovery.dedupe import dedupe_venues, identity_key
from scraper.discovery.existing import existing_catalogue_id
from scraper.discovery.location import parse_location
from scraper.discovery.models import DiscoveredVenue, DiscoveryOptions, ListingPage
from scraper.discovery.pagination import infinite_scroll_page_count, next_page_url
from scraper.discovery.queue import finalize_status, job_from_dict, mark_retry_or_fail, next_batch, queue_selected
from scraper.discovery.locate import (
    LOCATE_JS,
    category_follow_url,
    is_location_picker_page,
    locate_script_args,
    magicpin_category_label,
    match_location_suggestion,
)
from scraper.discovery.runner import discover_location, kinds_for
from scraper.discovery.urls import MAGICPIN_HOME, SWIGGY_DINEOUT, SWIGGY_HOME, SWIGGY_RESTAURANTS, ZOMATO_HOME, ZOMATO_RESTAURANTS, search_urls, type_query
from scraper.platform import platform_url_error
from scraper.swiggy.models import RawSource

FIXTURES = Path(__file__).parent / "fixtures"


def _page(name: str, url: str) -> ListingPage:
    html = (FIXTURES / name).read_text(encoding="utf-8")
    return ListingPage(url=url, html=html)


def map_fetcher(mapping: dict[str, str]):
    def fetch(url: str) -> ListingPage:
        name = mapping.get(url)
        if not name:
            return ListingPage(url=url, html="", exhausted=True)
        return _page(name, url)

    return fetch


def test_swiggy_delivery_feed_is_classified_not_treated_as_area_directory():
    from scraper.discovery.scope import (
        DELIVERY_TO_LOCATION,
        DELIVERS_HERE,
        LOCATED_HERE,
        LOCATION_UNKNOWN,
        classify_venues,
        job_discovery_scope,
    )

    location = parse_location("Indiranagar, Bengaluru, Karnataka")
    venues = classify_venues(
        location,
        [
            DiscoveredVenue("swiggy", "restaurant", "https://www.swiggy.com/city/bangalore/pizza-hut-indiranagar-rest10584", location="Indiranagar"),
            DiscoveredVenue("swiggy", "restaurant", "https://www.swiggy.com/city/bangalore/hayat-koramangala-rest1078550", location="Koramangala"),
            DiscoveredVenue("swiggy", "restaurant", "https://www.swiggy.com/city/bangalore/mystery-rest9"),
        ],
    )
    assert job_discovery_scope(["swiggy"], "restaurant") == DELIVERY_TO_LOCATION
    assert [item.location_match for item in venues] == [LOCATED_HERE, DELIVERS_HERE, LOCATION_UNKNOWN]
    assert all(item.discovery_scope == DELIVERY_TO_LOCATION for item in venues)
    city = parse_location("Bengaluru, Karnataka")
    city_venues = classify_venues(
        city,
        [DiscoveredVenue("swiggy", "restaurant", "https://www.swiggy.com/city/bangalore/hayat-koramangala-rest1078550", location="Koramangala")],
    )
    assert city_venues[0].location_match == LOCATED_HERE


def test_location_normalization_is_generic():
    one = parse_location("  Harbour Town ")
    assert one.original == "Harbour Town"
    assert one.city == "Harbour Town"
    assert one.locality is None
    assert one.slug == "harbour-town"
    city_state = parse_location("Bangalore, Karnataka")
    assert city_state.city == "Bangalore"
    assert city_state.state == "Karnataka"
    assert city_state.locality is None
    assert city_state.search_text == "Bangalore, Karnataka"
    assert city_state.slug == "bangalore"
    two = parse_location("Indiranagar, Bangalore, Karnataka")
    assert two.locality == "Indiranagar"
    assert two.city == "Bangalore"
    assert two.state == "Karnataka"
    with pytest.raises(ValueError):
        parse_location("   ")


def test_swiggy_header_reads_address_under_other():
    from scraper.discovery.locate import parse_swiggy_header_location

    assert parse_swiggy_header_location("Other\nIndiranagar, Bengaluru, Karnataka, India") == (
        "Indiranagar, Bengaluru, Karnataka, India"
    )
    assert parse_swiggy_header_location("Setup your precise location") == ""


def test_location_consistency_rejects_a_different_city():
    from scraper.discovery.locate import location_is_consistent, location_mismatch_message

    assert location_is_consistent("Indiranagar, Bengaluru, Karnataka", "Indiranagar")
    assert location_is_consistent("Indiranagar, Bengaluru, Karnataka", "Indiranagar Bengaluru, Karnataka, India")
    assert location_is_consistent("indiranagar", "Indiranagar, Bengaluru, Karnataka, India")
    assert not location_is_consistent("indiranagar", "Pandeshwar, Mangaluru, Karnataka, India")
    assert not location_is_consistent("Puttur, Karnataka", "Indiranagar, Bengaluru, Karnataka, India")
    assert not location_is_consistent("Puttur, Karnataka", "Mangalore, Karnataka, India")
    assert not location_is_consistent("Puttur", "Nandos Karnataka Restaurants, New Delhi")
    assert not location_is_consistent("JP Nagar, Bengaluru, Karnataka", "Indiranagar, Bengaluru, Karnataka, India")
    assert location_is_consistent("JP Nagar, Bengaluru, Karnataka", "J. P. Nagar, Bengaluru, Karnataka, India")
    assert "Location selection failed" in location_mismatch_message("indiranagar", "Mangaluru", "https://www.swiggy.com/restaurants")


def test_jp_nagar_suggestions_prefer_area_not_phase_road_or_restaurant():
    from scraper.discovery.locate import rank_location_suggestion

    query = "JP Nagar, Bengaluru, Karnataka"
    kwargs = {"locality": "JP Nagar", "city": "Bengaluru", "state": "Karnataka"}
    area = rank_location_suggestion("JP Nagar, Bengaluru, Karnataka, India", query, **kwargs)
    dotted = rank_location_suggestion("J. P. Nagar Bengaluru, Karnataka, India", query, **kwargs)
    phase = rank_location_suggestion("JP Nagar 7th Phase, Bengaluru", query, **kwargs)
    road = rank_location_suggestion("JP Nagar Road, Bengaluru", query, **kwargs)
    resto = rank_location_suggestion("JP Nagar Biryani House, Bengaluru", query, **kwargs)
    assert area is not None and area > 0
    assert dotted is not None and dotted > 0
    assert phase is None
    assert road is None
    assert resto is None
    parsed = parse_location(query)
    assert parsed.locality == "JP Nagar"
    assert parsed.city == "Bengaluru"
    assert parsed.state == "Karnataka"
    assert type_query(parsed) == "JP Nagar"


def test_first_top_level_jp_nagar_is_chosen_not_phase_or_restaurant():
    from scraper.discovery.locate import choose_location_suggestion, is_top_level_locality_match

    query = "JP Nagar, Bengaluru, Karnataka"
    kwargs = {"locality": "JP Nagar", "city": "Bengaluru", "state": "Karnataka"}
    first = "J. P. Nagar Bengaluru, Karnataka, India"
    rows = [
        first,
        "JP Nagar 7th Phase Bengaluru, Karnataka, India",
        "JP Nagar 8th Phase, J. P. Nagar Bengaluru, Karnataka, India",
        "JP Nagar 6th Phase Bengaluru, Karnataka, India",
        "JP Nagar Kuppaluru, Karnataka, India",
    ]
    assert is_top_level_locality_match(first, "JP Nagar", "Bengaluru")
    assert not is_top_level_locality_match(rows[1], "JP Nagar", "Bengaluru")
    assert choose_location_suggestion(rows, query, **kwargs) == first
    assert choose_location_suggestion(
        ["JP Nagar Restaurant Bengaluru", first], query, **kwargs
    ) == first
    assert not is_top_level_locality_match("JP Nagar Road, Bengaluru", "JP Nagar", "Bengaluru")
    assert not is_top_level_locality_match("JP Nagar, Delhi", "JP Nagar", "Bengaluru")
    phase_request = choose_location_suggestion(
        rows,
        "JP Nagar 7th Phase, Bengaluru, Karnataka",
        locality="JP Nagar 7th Phase",
        city="Bengaluru",
        state="Karnataka",
    )
    assert "7th Phase" in phase_request


def test_kinds_for_both_are_independent():
    assert kinds_for("restaurant") == ["restaurant"]
    assert kinds_for("dineout") == ["dineout"]
    assert kinds_for("both") == ["restaurant", "dineout"]


def test_entry_urls_use_platform_location_pages():
    location = parse_location("Bangalore, Karnataka")
    assert search_urls("swiggy", "restaurant", location) == [SWIGGY_RESTAURANTS]
    assert search_urls("swiggy", "dineout", location) == [SWIGGY_DINEOUT]
    swiggy_home = (FIXTURES / "discovery_swiggy_home.html").read_text(encoding="utf-8")
    assert is_location_picker_page(swiggy_home, "swiggy")
    assert category_follow_url(swiggy_home, SWIGGY_HOME, "swiggy", "restaurant") == SWIGGY_RESTAURANTS
    assert category_follow_url(swiggy_home, SWIGGY_HOME, "swiggy", "dineout") == "https://www.swiggy.com/dineout"
    assert search_urls("zomato", "dineout", location) == [ZOMATO_RESTAURANTS]
    zomato_located = parse_location("Bengaluru, Karnataka")
    from scraper.discovery.resolver import apply_platform_place

    apply_platform_place(zomato_located, "zomato", city="Bengaluru", slug="bangalore", verified=True)
    assert search_urls("zomato", "dineout", zomato_located) == [ZOMATO_RESTAURANTS]
    assert search_urls("zomato", "restaurant", location) == [ZOMATO_RESTAURANTS]
    assert "zomato.com/bangalore" not in "".join(search_urls("zomato", "restaurant", location))
    assert "zomato.com/bangalore" not in "".join(search_urls("zomato", "dineout", zomato_located))
    assert search_urls("magicpin", "restaurant", location) == [MAGICPIN_HOME]
    assert MAGICPIN_HOME == "https://magicpin.in/india/Bangalore/home/"
    home = (FIXTURES / "discovery_magicpin_home.html").read_text(encoding="utf-8")
    assert is_location_picker_page(home, "magicpin")
    assert magicpin_category_label("restaurant") == "Food Delivery"
    assert magicpin_category_label("dineout", "fine") == "Fine Dining"
    assert category_follow_url(home, MAGICPIN_HOME, "magicpin", "restaurant") == "https://magicpin.in/category?categoryName=food-delivery"
    assert category_follow_url(home, MAGICPIN_HOME, "magicpin", "dineout", "budget") == "https://magicpin.in/category?categoryName=budget-eats"
    assert category_follow_url(home, MAGICPIN_HOME, "magicpin", "dineout", "fine") == "https://magicpin.in/category?categoryName=fine-dining"
    zomato_home = (FIXTURES / "discovery_zomato_home.html").read_text(encoding="utf-8")
    assert match_location_suggestion(zomato_home, "pandeshwar mangaluru") == "Pandeshwar, Mangaluru, India"
    swiggy_suggest = '<div class="style__Location-sc-zdau5c-1 fwrdJJ">Mangaluru, Karnataka, India</div>'
    assert match_location_suggestion(swiggy_suggest, "mangaluru karnataka") == "Mangaluru, Karnataka, India"
    assert category_follow_url(zomato_home, ZOMATO_HOME, "zomato", "restaurant") == "https://www.zomato.com/sample-area/order"
    assert category_follow_url(zomato_home, ZOMATO_HOME, "zomato", "dineout") == "https://www.zomato.com/sample-area/dine-out"
    assert ".selectedLocation" in LOCATE_JS
    assert "role='option'" in LOCATE_JS or 'role="option"' in LOCATE_JS or "role='option'" in LOCATE_JS.replace('"', "'")
    assert "input.location" in LOCATE_JS
    assert "phase" in LOCATE_JS
    assert "area, street" in LOCATE_JS
    assert "setup your precise location" in LOCATE_JS
    assert "aria-label*='location'" in LOCATE_JS
    assert "Search Location" in LOCATE_JS
    assert "phase === \"read\"" in LOCATE_JS or "phase === 'read'" in LOCATE_JS
    assert "opts.type" in LOCATE_JS
    args = locate_script_args("magicpin", "restaurant", location)
    assert args["query"] == "Bangalore, Karnataka"
    assert args["city"] == "Bangalore"
    assert args["state"] == "Karnataka"
    typed = parse_location("pandeshwar mangaluru")
    assert locate_script_args("zomato", "restaurant", typed)["query"] == "pandeshwar mangaluru"
    assert args["type"] == "Bangalore"
    jp = parse_location("JP Nagar, Bengaluru, Karnataka")
    jp_args = locate_script_args("swiggy", "restaurant", jp)
    assert jp_args["query"] == "JP Nagar, Bengaluru, Karnataka"
    assert jp_args["type"] == "JP Nagar"
    assert jp_args["locality"] == "JP Nagar"
    assert args["category"] == "Food Delivery"
    assert locate_script_args("magicpin", "dineout", location, "fine")["category"] == "Fine Dining"
    assert locate_script_args("swiggy", "restaurant", location)["category"] == "Food Delivery"
    assert locate_script_args("swiggy", "dineout", location)["category"] == "Dineout"
    assert locate_script_args("zomato", "dineout", location)["category"] == "Dining Out"


def test_swiggy_restaurant_discovery_paginates_and_dedupes_branches():
    fetcher = map_fetcher(
        {
            SWIGGY_RESTAURANTS: "discovery_swiggy_page1.html",
            f"{SWIGGY_RESTAURANTS}?page=2": "discovery_swiggy_page2.html",
        }
    )
    location, venues = discover_location("Sample Area", ["swiggy"], "restaurant", fetcher)
    ids = [item.venue_id for item in venues]
    names = [item.name for item in venues]
    assert location.slug == "sample-area"
    assert ids == ["111", "222", "444", "555"]
    assert "Gamma Other Town" not in names
    assert all("best-restaurants" not in (item.venue_url or "") for item in venues)
    assert all(item.platform == "swiggy" for item in venues)
    assert all(item.catalogue_type == "restaurant" for item in venues)


def test_swiggy_listing_uses_api_cards_not_seo_links():
    from scraper.discovery.swiggy import SwiggyDiscovery

    page = ListingPage(
        url="https://www.swiggy.com/restaurants",
        html='<a href="https://www.swiggy.com/city/bangalore/best-restaurants">Best restaurants</a>',
        payload={
            "api_payloads": [
                {
                    "data": {
                        "cards": [
                            {
                                "card": {
                                    "card": {
                                        "gridElements": {
                                            "infoWithStyle": {
                                                "restaurants": [
                                                    {
                                                        "info": {
                                                            "id": "424558",
                                                            "name": "Live Kitchen",
                                                            "locality": "Indiranagar",
                                                            "avgRating": 4.3,
                                                            "cloudinaryImageId": "sample",
                                                            "sla": {
                                                                "lastMileTravel": 2.4,
                                                                "lastMileTravelString": "2.4 km",
                                                            },
                                                            "cta": {
                                                                "link": "https://www.swiggy.com/city/bangalore/live-kitchen-indiranagar-rest424558"
                                                            },
                                                        }
                                                    }
                                                ]
                                            }
                                        }
                                    }
                                }
                            }
                        ]
                    }
                }
            ],
            "dom_venues": [],
        },
    )
    venues = SwiggyDiscovery().parse_page(page, "restaurant")
    assert [item.venue_id for item in venues] == ["424558"]
    assert venues[0].name == "Live Kitchen"
    assert venues[0].location == "Indiranagar"
    assert venues[0].distance_km == 2.4
    assert "best-restaurants" not in venues[0].venue_url
    assert venues[0].image_url and "sample" in venues[0].image_url


def test_swiggy_listing_update_follows_next_offset_until_missing():
    from scraper.discovery.listing_update import listing_has_more, paginate_listing_payloads

    first = {"csrfToken": "a", "data": {"pageOffset": {"nextOffset": "token-1", "widgetOffset": {"k": "9"}}, "cards": [1]}}
    second = {"csrfToken": "b", "data": {"pageOffset": {"nextOffset": "token-1", "widgetOffset": {"k": "24"}}, "cards": [2]}}
    third = {"csrfToken": "c", "data": {"pageOffset": {"nextOffset": "", "widgetOffset": {"k": "40"}}, "cards": [3]}}
    calls: list[str] = []

    def fetch_update(lat, lng, csrf, offset):
        calls.append(str(offset.get("widgetOffset")))
        return second if offset.get("widgetOffset") == {"k": "9"} else third

    payloads, meta = paginate_listing_payloads([first], fetch_update, lat="1", lng="2")
    assert listing_has_more(first)
    assert not listing_has_more(third)
    assert calls == ["{'k': '9'}", "{'k': '24'}"]
    assert len(payloads) == 3
    assert meta["exhausted"] is True
    assert meta["reason"] == "missing nextOffset"
    assert meta["path"] == "/dapi/restaurants/list/update"
    assert meta["batches"] == 3
    assert "10" not in str(meta) and "25" not in str(meta) and "50" not in str(meta) and "100" not in str(meta)


def test_swiggy_listing_stops_when_offset_pair_does_not_advance():
    from scraper.discovery.listing_update import paginate_listing_payloads

    stuck = {"data": {"pageOffset": {"nextOffset": "same", "widgetOffset": {"k": "9"}}}}

    def fetch_update(lat, lng, csrf, offset):
        return stuck

    payloads, meta = paginate_listing_payloads([stuck], fetch_update, lat="1", lng="2")
    assert meta["exhausted"] is True
    assert meta["reason"] == "unchanged nextOffset and widgetOffset"
    assert meta["update_requests"] == 1


def test_swiggy_update_payload_uses_existing_url_parser():
    from scraper.discovery.swiggy import SwiggyDiscovery

    page = ListingPage(
        url="https://www.swiggy.com/restaurants",
        html="",
        payload={
            "api_payloads": [
                {
                    "data": {
                        "cards": [
                            {
                                "card": {
                                    "card": {
                                        "gridElements": {
                                            "infoWithStyle": {
                                                "restaurants": [
                                                    {
                                                        "info": {
                                                            "id": "1",
                                                            "name": "First",
                                                            "cta": {"link": "https://www.swiggy.com/city/bangalore/first-rest1"},
                                                        }
                                                    }
                                                ]
                                            }
                                        }
                                    }
                                }
                            }
                        ]
                    }
                },
                {
                    "data": {
                        "cards": [
                            {
                                "card": {
                                    "card": {
                                        "gridElements": {
                                            "infoWithStyle": {
                                                "restaurants": [
                                                    {
                                                        "info": {
                                                            "id": "1",
                                                            "name": "First dup",
                                                            "cta": {"link": "https://www.swiggy.com/city/bangalore/first-rest1"},
                                                        }
                                                    },
                                                    {
                                                        "info": {
                                                            "id": "2",
                                                            "name": "Second",
                                                            "cta": {"link": "https://www.swiggy.com/city/bangalore/second-rest2"},
                                                        }
                                                    },
                                                ]
                                            }
                                        }
                                    }
                                }
                            }
                        ]
                    }
                },
            ]
        },
    )
    venues = SwiggyDiscovery().parse_page(page, "restaurant")
    unique = dedupe_venues(venues)
    assert {item.venue_id for item in unique} == {"1", "2"}
    assert all("best-restaurants" not in (item.venue_url or "") for item in unique)


def test_all_available_collects_every_page():
    fetcher = map_fetcher(
        {
            SWIGGY_RESTAURANTS: "discovery_swiggy_page1.html",
            f"{SWIGGY_RESTAURANTS}?page=2": "discovery_swiggy_page2.html",
        }
    )
    _, unlimited = discover_location("Sample Area", ["swiggy"], "restaurant", fetcher, DiscoveryOptions())
    _, limited = discover_location(
        "Sample Area", ["swiggy"], "restaurant", fetcher, DiscoveryOptions(max_venues=2)
    )
    assert len(unlimited) == 4
    assert len(limited) == 2
    assert "10" not in str(DiscoveryOptions())


def test_swiggy_dineout_discovery_is_separate():
    fetcher = map_fetcher(
        {
            SWIGGY_DINEOUT: "discovery_swiggy_dineout.html",
        }
    )
    _, venues = discover_location("Sample Area", ["swiggy"], "dineout", fetcher)
    urls = [item.venue_url for item in venues]
    assert any("dineout" in url for url in urls)
    assert all(item.catalogue_type == "dineout" for item in venues)
    assert not any("noise-999" in url for url in urls)


def test_zomato_and_magicpin_load_more_and_store_ids():
    fetcher = map_fetcher(
        {
            ZOMATO_RESTAURANTS: "discovery_zomato_home.html",
            "https://www.zomato.com/sample-area/order": "discovery_zomato_page1.html",
            "https://www.zomato.com/sample-area/order?page=2": "discovery_zomato_page2.html",
            "https://www.zomato.com/sample-area/dine-out": "discovery_zomato_dineout.html",
            MAGICPIN_HOME: "discovery_magicpin_home.html",
            "https://magicpin.in/category?categoryName=food-delivery": "discovery_magicpin_page1.html",
            "https://magicpin.in/food-delivery": "discovery_magicpin_page1.html",
            "https://magicpin.in/food-delivery?page=2": "discovery_magicpin_page2.html",
            "https://magicpin.in/category?categoryName=budget-eats": "discovery_magicpin_page1.html",
            "https://magicpin.in/category?categoryName=fine-dining": "discovery_magicpin_page1.html",
            "https://magicpin.in/budget-dining": "discovery_magicpin_page1.html",
            "https://magicpin.in/fine-dining": "discovery_magicpin_page1.html",
        }
    )
    _, zomato = discover_location("Sample Area", ["zomato"], "restaurant", fetcher)
    assert {item.name for item in zomato} >= {"Street Storyss", "Bob's Bar", "Third Venue"}
    _, dine = discover_location("Sample Area", ["zomato"], "dineout", fetcher)
    assert any(item.name == "Street Storyss" for item in dine)
    assert not any("collections" in (item.venue_url or "") for item in dine)
    assert not any("district.in" in (item.venue_url or "") for item in dine)
    assert not any("cuisines" in (item.venue_url or "") for item in dine)
    _, magic = discover_location("Sample Area", ["magicpin"], "restaurant", fetcher)
    assert {item.venue_id for item in magic} >= {"19307c", "planb1", "5642c9"}
    assert all(item.platform == "magicpin" for item in magic)


def test_branch_identity_keeps_same_name_different_place():
    venues = dedupe_venues(
        [
            DiscoveredVenue("swiggy", "restaurant", "https://www.swiggy.com/city/a/chain-rest1", venue_id="1", name="Chain", location="Place A"),
            DiscoveredVenue("swiggy", "restaurant", "https://www.swiggy.com/city/b/chain-rest2", venue_id="2", name="Chain", location="Place B"),
        ]
    )
    assert len(venues) == 2
    assert identity_key(venues[0]) != identity_key(venues[1])


def test_name_alone_does_not_dedupe_without_id_or_url():
    venues = dedupe_venues(
        [
            DiscoveredVenue("zomato", "restaurant", "https://www.zomato.com/a/one", name="Cafe", location="North"),
            DiscoveredVenue("zomato", "restaurant", "https://www.zomato.com/a/two", name="Cafe", location="South"),
        ]
    )
    assert len(venues) == 2


def test_pagination_helpers():
    html = '<a rel="next" href="?page=2">Next</a>'
    assert "page=2" in (next_page_url(html, "https://www.swiggy.com/city/x") or "")
    scroll = '<div data-discovery-page="1"></div><div data-discovery-page="3" data-has-more="true"></div>'
    assert infinite_scroll_page_count(scroll) == 3


def test_platform_urls_are_not_silently_switched():
    assert platform_url_error("swiggy", "https://www.zomato.com/x/y")
    assert platform_url_error("zomato", "https://www.swiggy.com/city/x/y-rest1")
    assert platform_url_error("magicpin", "https://www.swiggy.com/city/x/y-rest1")


def test_existing_catalogue_match_and_skip():
    venue = DiscoveredVenue(
        "swiggy",
        "restaurant",
        "https://www.swiggy.com/city/sample-area/alpha-kitchen-rest111",
        venue_id="111",
        name="Alpha Kitchen",
        location="Sample Area",
    )
    catalogues = [
        {
            "id": "cat-existing",
            "result": {
                "platform": "swiggy",
                "catalogue_type": "restaurant",
                "source_url": "https://www.swiggy.com/city/sample-area/alpha-kitchen-rest111",
                "restaurant": {"name": "Alpha Kitchen", "restaurant_id": "111", "outlet": "Sample Area"},
            },
        }
    ]
    assert existing_catalogue_id(venue, catalogues) == "cat-existing"


def test_retries_cancel_and_resume_queue(monkeypatch):
    from scraper.discovery.queue import job_to_dict

    job = job_from_dict(
        {
            "id": "job-1",
            "organization_id": "org",
            "location": parse_location("Sample Area").to_dict(),
            "platforms": ["swiggy"],
            "catalogue_type": "restaurant",
            "status": "awaiting_confirmation",
            "created_at": "2026-01-01T00:00:00Z",
            "options": {"concurrency": 1, "max_retries": 1},
            "venues": [
                {
                    "platform": "swiggy",
                    "catalogue_type": "restaurant",
                    "venue_url": "https://www.swiggy.com/city/sample-area/alpha-kitchen-rest111",
                    "venue_id": "111",
                    "name": "Alpha",
                    "identity_key": "swiggy:restaurant:id:111",
                    "selected": True,
                    "status": "discovered",
                },
                {
                    "platform": "swiggy",
                    "catalogue_type": "restaurant",
                    "venue_url": "https://www.swiggy.com/city/sample-area/beta-bistro-rest222",
                    "venue_id": "222",
                    "name": "Beta",
                    "identity_key": "swiggy:restaurant:id:222",
                    "selected": True,
                    "status": "discovered",
                },
            ],
        }
    )
    queue_selected(job, None)
    first = next_batch(job)
    assert len(first) == 1
    mark_retry_or_fail(first[0], "network", blocked=False, max_retries=1)
    assert first[0].status == "queued"
    mark_retry_or_fail(first[0], "network", blocked=False, max_retries=1)
    assert first[0].status == "failed"
    first[0].status = "completed"
    job.venues[1].status = "queued"
    job.status = finalize_status(job)
    assert job.status == "scraping"
    job.venues[1].status = "skipped"
    job.status = finalize_status(job)
    assert job.status == "completed"


def test_blocked_is_not_retried_endlessly():
    venue = DiscoveredVenue("swiggy", "restaurant", "https://www.swiggy.com/city/x/y-rest1", venue_id="1")
    mark_retry_or_fail(venue, "blocked", blocked=True, max_retries=9)
    assert venue.status == "blocked"


class MapAccess(SwiggyAccess):
    def __init__(self, pages: dict[str, str], venue_html: str = "<h1>Alpha Kitchen</h1>"):
        self.pages = pages
        self.venue_html = venue_html
        self.loaded: list[str] = []

    def load(self, url: str):
        self.loaded.append(url)
        html = self.pages.get(url)
        if html is None and "rest" in url:
            html = self.venue_html
        raw = RawSource(source_url=url, access_status="ok", html=html or "", page_text=html or "")
        return AccessResult(method="local_fixture", raw=raw)


def test_area_job_uses_existing_venue_scraper_and_survives_one_failure(monkeypatch):
    client = TestClient(app)
    app.dependency_overrides[require_session] = lambda: AuthUser(id="user-1", email="a@b.c")
    pages = {
        SWIGGY_HOME: (FIXTURES / "discovery_swiggy_home.html").read_text(encoding="utf-8"),
        SWIGGY_RESTAURANTS: (FIXTURES / "discovery_swiggy_page1.html").read_text(encoding="utf-8"),
        f"{SWIGGY_RESTAURANTS}?page=2": (FIXTURES / "discovery_swiggy_page2.html").read_text(encoding="utf-8"),
    }

    def fake_create(request: CatalogCreateRequest, access):
        if "222" in request.swiggy_url:
            from backend.schemas import CatalogCreateResponse

            return CatalogCreateResponse(
                extraction_status="failed",
                restaurant_name=request.restaurant_name,
                fssai_number="",
                source_url=request.swiggy_url,
                platform="swiggy",
                error="temporary",
            )
        from backend.schemas import CatalogCreateResponse

        return CatalogCreateResponse(
            extraction_status="ok",
            restaurant_name=request.restaurant_name,
            fssai_number="",
            source_url=request.swiggy_url,
            platform="swiggy",
            catalogue_type="restaurant",
            restaurant={"name": request.restaurant_name, "restaurant_id": "111"},
        )

    monkeypatch.setattr("backend.services.area_service.create_catalog", fake_create)
    access = MapAccess(pages)
    app.dependency_overrides[get_swiggy_access] = lambda: access
    try:
        created = client.post(
            "/area-jobs",
            json={
                "location": "Sample Area",
                "platforms": ["swiggy"],
                "catalogue_type": "restaurant",
                "organization_id": "org_1",
                "concurrency": 1,
                "max_retries": 0,
            },
        )
        assert created.status_code == 200, created.text
        job = created.json()
        assert job["discovered_count"] == 4
        assert job["status"] == "awaiting_confirmation"
        start = client.post(
            f"/area-jobs/{job['id']}/start",
            json={"organization_id": "org_1", "selected_keys": [job["venues"][0]["identity_key"], job["venues"][1]["identity_key"]]},
        )
        assert start.status_code == 200
        first = client.post(f"/area-jobs/{job['id']}/scrape-batch", json={"organization_id": "org_1"})
        second = client.post(f"/area-jobs/{job['id']}/scrape-batch", json={"organization_id": "org_1"})
        body = second.json()
        statuses = {item["venue_id"]: item["status"] for item in body["venues"] if item.get("venue_id") in {"111", "222"}}
        assert statuses["111"] == "completed"
        assert statuses["222"] == "failed"
        assert body["completed_count"] >= 1
        listed = client.get("/area-jobs?organization_id=org_1").json()["jobs"]
        assert listed[0]["id"] == job["id"]
        cancel = client.post(f"/area-jobs/{job['id']}/cancel", json={"organization_id": "org_1"})
        assert cancel.json()["status"] == "cancelled"
    finally:
        app.dependency_overrides.clear()


def test_resume_skips_completed_venues(monkeypatch):
    app.dependency_overrides[require_session] = lambda: AuthUser(id="user-1", email="a@b.c")
    pages = {
        SWIGGY_HOME: (FIXTURES / "discovery_swiggy_home.html").read_text(encoding="utf-8"),
        SWIGGY_RESTAURANTS: (FIXTURES / "discovery_swiggy_page1.html").read_text(encoding="utf-8"),
        f"{SWIGGY_RESTAURANTS}?page=2": (FIXTURES / "discovery_swiggy_page2.html").read_text(encoding="utf-8"),
    }
    calls: list[str] = []

    def fake_create(request: CatalogCreateRequest, access):
        calls.append(request.swiggy_url)
        from backend.schemas import CatalogCreateResponse

        return CatalogCreateResponse(
            extraction_status="ok",
            restaurant_name=request.restaurant_name,
            fssai_number="",
            source_url=request.swiggy_url,
            platform="swiggy",
            catalogue_type="restaurant",
            restaurant={"name": request.restaurant_name},
        )

    monkeypatch.setattr("backend.services.area_service.create_catalog", fake_create)
    access = MapAccess(pages)
    job = create_area_job(
        user_id="user-1",
        organization_id="org_1",
        location_input="Sample Area",
        platforms=["swiggy"],
        catalogue_type="restaurant",
        access=access,
        concurrency=1,
    )
    start_area_scrape(
        user_id="user-1",
        organization_id="org_1",
        job_id=job["id"],
        selected_keys=[job["venues"][0]["identity_key"], job["venues"][2]["identity_key"]],
    )
    scrape_area_batch(user_id="user-1", organization_id="org_1", job_id=job["id"], access=access)
    scrape_area_batch(user_id="user-1", organization_id="org_1", job_id=job["id"], access=access)
    scrape_area_batch(user_id="user-1", organization_id="org_1", job_id=job["id"], access=access)
    assert len(calls) == 2
    app.dependency_overrides.clear()

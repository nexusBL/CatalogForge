import json
from pathlib import Path

from scraper.swiggy.models import RawSource
from scraper.swiggy.parser import parse_swiggy_catalogue
from scraper.swiggy.scraper import (
    _access_state,
    _has_menu_shape,
    _keep_json_payload,
    collect_local_source,
)

FIXTURES = Path(__file__).parent / "fixtures"
HARBOR = FIXTURES / "swiggy_menu_payload.json"
COASTAL = FIXTURES / "swiggy_menu_coastal_kitchen.json"
SPARSE = FIXTURES / "swiggy_menu_sparse.json"
HARBOR_URL = "https://www.swiggy.com/city/mangaluru/harbor-spice-house-rest999001"
COASTAL_URL = "https://www.swiggy.com/city/mangaluru/coastal-kitchen-rest888100"


def _from_json(path: Path, url: str):
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw = RawSource(source_url=url, api_payloads=[payload], access_status="ok")
    return parse_swiggy_catalogue(raw)


def test_restaurant_extraction_from_fixture():
    catalogue = _from_json(COASTAL, COASTAL_URL)
    restaurant = catalogue.restaurant
    assert catalogue.extraction_status == "ok"
    assert restaurant.name == "Coastal Kitchen"
    assert restaurant.rating == 4.2
    assert restaurant.cuisines == ["Seafood", "Mangalorean"]
    assert restaurant.price_for_two == "₹900 for two"
    assert restaurant.address == "12 Harbor Road, Panambur, Mangaluru"
    assert restaurant.image_url.endswith("test/coastal-kitchen")
    assert restaurant.outlet == "Harbor Road, Panambur"


def test_multiple_categories_discovered_from_source():
    catalogue = _from_json(COASTAL, COASTAL_URL)
    names = [category.name for category in catalogue.categories]
    assert names == ["Tandoor", "Seafood", "Rice"]
    assert "Bestseller" not in names
    assert "Recommended" not in names
    assert "Veg" not in names


def test_multiple_items_across_categories():
    catalogue = _from_json(COASTAL, COASTAL_URL)
    items = [item.name for category in catalogue.categories for item in category.items]
    assert items == ["Tandoori Pomfret", "Prawn Ghee Roast", "Neer Dosa"]
    assert catalogue.item_count == 3


def test_item_prices_descriptions_images():
    catalogue = _from_json(COASTAL, COASTAL_URL)
    pomfret = catalogue.categories[0].items[0]
    prawn = catalogue.categories[1].items[0]
    dosa = catalogue.categories[2].items[0]
    assert pomfret.price == 499
    assert pomfret.description == "Whole fish, charcoal grilled"
    assert pomfret.image_url.endswith("test/pomfret")
    assert prawn.price == 389
    assert prawn.description == "Coastal masala, ghee"
    assert prawn.image_url.endswith("test/prawn-ghee-roast")
    assert dosa.price == 80
    assert dosa.description is None
    assert dosa.image_url is None


def test_veg_nonveg_and_source_labels():
    catalogue = _from_json(COASTAL, COASTAL_URL)
    pomfret = catalogue.categories[0].items[0]
    dosa = catalogue.categories[2].items[0]
    assert pomfret.food_type == "NONVEG"
    assert dosa.food_type == "VEG"
    assert "Must Try" in pomfret.labels
    assert "Recommended" in pomfret.labels


def test_variants_and_customizations():
    catalogue = _from_json(COASTAL, COASTAL_URL)
    pomfret = catalogue.categories[0].items[0]
    assert pomfret.variants
    assert pomfret.variants[0]["group_name"] == "Spice"
    assert pomfret.customizations
    assert pomfret.customizations[0]["group_name"] == "Sides"
    assert pomfret.customizations[0]["choices"][0]["name"] == "Butter Naan"


def test_duplicate_items_with_same_source_id():
    catalogue = _from_json(COASTAL, COASTAL_URL)
    seafood = next(category for category in catalogue.categories if category.name == "Seafood")
    assert len(seafood.items) == 1
    assert seafood.items[0].name == "Prawn Ghee Roast"


def test_missing_fields_stay_null():
    catalogue = _from_json(SPARSE, "https://www.swiggy.com/city/x/plain-leaf-cafe-rest101")
    restaurant = catalogue.restaurant
    item = catalogue.categories[0].items[0]
    assert restaurant.name == "Plain Leaf Cafe"
    assert restaurant.rating is None
    assert restaurant.cuisines == []
    assert restaurant.price_for_two is None
    assert restaurant.address is None
    assert restaurant.image_url is None
    assert item.name == "Filter Coffee"
    assert item.description is None
    assert item.price is None
    assert item.image_url is None
    assert item.food_type is None
    assert item.variants == []
    assert item.customizations == []


def test_blocked_response_is_not_ok():
    catalogue = parse_swiggy_catalogue(
        RawSource(
            source_url=HARBOR_URL,
            blocked=True,
            access_status="blocked",
            http_status=403,
            waf_action="challenge",
            reason="Swiggy/CloudFront denied the restaurant page (HTTP 403).",
        )
    )
    assert catalogue.extraction_status == "blocked"
    assert catalogue.extraction.ok is False
    assert catalogue.restaurant.name is None
    assert catalogue.categories == []
    assert catalogue.item_count == 0
    assert catalogue.error


def test_failed_when_page_has_no_catalogue():
    catalogue = parse_swiggy_catalogue(
        RawSource(
            source_url=HARBOR_URL,
            access_status="ok",
            http_status=200,
            api_payloads=[{"data": {"cards": []}}],
        )
    )
    assert catalogue.extraction_status == "failed"
    assert catalogue.categories == []
    assert catalogue.restaurant.name is None
    assert catalogue.error


def test_dom_fallback_reads_item_fields(tmp_path):
    html = """
    <html><body>
    <section data-menu-category="Soups">
      <article data-menu-item="Tomato Soup" data-description="Classic" data-price="120"
               data-food-type="VEG" data-item-label="Chef special" data-image="https://cdn.example/soup.jpg"></article>
    </section>
    </body></html>
    """
    html_path = tmp_path / "menu.html"
    html_path.write_text(html, encoding="utf-8")
    raw = collect_local_source(HARBOR_URL, html_path=html_path)
    catalogue = parse_swiggy_catalogue(raw)
    assert catalogue.extraction_status == "ok"
    assert catalogue.source_type == "dom"
    soup = catalogue.categories[0].items[0]
    assert catalogue.categories[0].name == "Soups"
    assert soup.name == "Tomato Soup"
    assert soup.description == "Classic"
    assert soup.price == 120
    assert soup.food_type == "VEG"
    assert soup.labels == ["Chef special"]
    assert soup.image_url == "https://cdn.example/soup.jpg"


def test_untagged_item_cards_are_still_discovered():
    raw = RawSource(
        source_url=COASTAL_URL,
        api_payloads=[
            {
                "data": {
                    "cards": [
                        {
                            "title": "Street Snacks",
                            "itemCards": [
                                {"card": {"info": {"id": "s1", "name": "Bajji", "price": 5000}}}
                            ],
                        }
                    ]
                }
            }
        ],
    )
    catalogue = parse_swiggy_catalogue(raw)
    assert [category.name for category in catalogue.categories] == ["Street Snacks"]
    assert catalogue.categories[0].items[0].name == "Bajji"
    assert catalogue.categories[0].items[0].price == 50


def test_menu_shaped_json_is_kept_and_noise_is_dropped():
    menu = json.loads(HARBOR.read_text(encoding="utf-8"))
    assert _has_menu_shape(menu) is True
    assert _keep_json_payload("https://www.swiggy.com/dapi/menu/pl", menu) is True
    assert _keep_json_payload("https://www.swiggy.com/api/analytics", {"ok": True}) is False


def test_access_state_blocked_without_payload_is_blocked():
    status, reason = _access_state(
        url="https://www.swiggy.com/city/x/demo",
        http_status=403,
        waf_action="challenge",
        html="",
        payloads=[],
        next_data=None,
    )
    assert status == "blocked"
    assert reason


def test_access_state_challenge_with_menu_payload_is_ok():
    status, reason = _access_state(
        url="https://www.swiggy.com/city/x/demo",
        http_status=200,
        waf_action="challenge",
        html="<html></html>",
        payloads=[{"data": {"cards": [{"card": {"card": {"itemCards": [{}]}}}]}}],
        next_data=None,
    )
    assert status == "ok"
    assert reason is None

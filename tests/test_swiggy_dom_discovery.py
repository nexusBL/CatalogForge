from pathlib import Path

from scraper.swiggy.dom_discovery import discover_menu
from scraper.swiggy.models import RawSource
from scraper.swiggy.parser import parse_swiggy_catalogue
from scraper.swiggy.scraper import collect_local_source

FIXTURES = Path(__file__).parent / "fixtures"
URL = "https://www.swiggy.com/city/mangaluru/harbor-leaf-cafe-rest210000"


def _html(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_menu_items_and_dynamic_categories():
    result = discover_menu(_html("dom_menu_categories.html"), source_url=URL)
    names = {item.item_name for item in result.items}
    categories = {item.category for item in result.items if item.category}
    assert "Garden Margherita" in names
    assert "Garlic Bread" in names
    assert "Cola" in names
    assert categories == {"Wood Fired", "Sides", "Drinks"}
    assert "Bestseller" not in categories
    assert result.restaurant_name == "Harbor Leaf Cafe"
    assert result.selected is not None
    assert result.selected.repeat_count >= 8


def test_duplicate_items_are_removed():
    result = discover_menu(_html("dom_menu_categories.html"), source_url=URL)
    margheritas = [item for item in result.items if item.item_name == "Garden Margherita"]
    assert len(margheritas) == 1


def test_images_prices_and_descriptions():
    result = discover_menu(_html("dom_menu_rich_items.html"), source_url=URL)
    by_name = {item.item_name: item for item in result.items}
    chicken = by_name["Smoky Chicken Bake"]
    assert chicken.price == 449
    assert chicken.original_price == 499
    assert chicken.currency == "INR"
    assert chicken.description == "Charred chicken with pepper sauce"
    assert chicken.image_url.endswith("rich-one.jpg")
    assert chicken.veg_nonveg == "NONVEG"
    paneer = by_name["Paneer Tikka Pie"]
    assert paneer.veg_nonveg == "VEG"


def test_related_restaurant_cards_are_rejected():
    result = discover_menu(_html("dom_related_restaurants.html"), source_url=URL)
    names = {item.item_name for item in result.items}
    assert "Garden Margherita" in names
    assert "Bayview Kitchen" not in names
    assert "Coastal Grill House" not in names
    assert any(candidate.rejected == "related_restaurant_cards" for candidate in result.candidates)


def test_multiple_candidate_lists_prefer_menu():
    result = discover_menu(_html("dom_multiple_lists.html"), source_url=URL)
    names = {item.item_name for item in result.items}
    assert "Corn Cheese Melt" in names
    assert "Link A" not in names
    assert "About" not in names
    assert result.selected is not None
    assert result.selected.score >= 0.34


def test_missing_images_stay_null():
    result = discover_menu(_html("dom_missing_images.html"), source_url=URL)
    by_name = {item.item_name: item for item in result.items}
    assert by_name["Garden Margherita"].image_url
    assert by_name["Plain Cheese"].image_url is None
    assert by_name["Herb Tomato"].image_url is None


def test_missing_descriptions_stay_null():
    result = discover_menu(_html("dom_missing_descriptions.html"), source_url=URL)
    by_name = {item.item_name: item for item in result.items}
    assert by_name["Garden Margherita"].description
    assert by_name["Plain Cheese"].description is None
    assert by_name["Herb Tomato"].description is None


def test_customisable_items_are_flagged_from_source():
    result = discover_menu(_html("dom_customisable.html"), source_url=URL)
    by_name = {item.item_name: item for item in result.items}
    assert by_name["Garden Margherita"].customisable is True
    assert by_name["Farmhouse Slice"].customisable is True
    assert by_name["Garlic Bread"].customisable is None


def test_lazy_loaded_fixture_content_is_included():
    result = discover_menu(_html("dom_lazy_loaded.html"), source_url=URL)
    names = {item.item_name for item in result.items}
    assert "Garden Margherita" in names
    assert "Cheese Burst" in names
    assert "Chilli Paneer Pie" in names
    assert {item.category for item in result.items if item.category} >= {"Wood Fired", "Late Night"}


def test_no_reliable_menu_candidate():
    result = discover_menu(_html("dom_no_menu.html"), source_url=URL)
    assert result.items == []
    assert result.selected is None or result.selected.score < 0.34


def test_candidate_scoring_is_deterministic():
    html = _html("dom_menu_categories.html")
    first = discover_menu(html, source_url=URL)
    second = discover_menu(html, source_url=URL)
    assert first.selected is not None and second.selected is not None
    assert first.selected.score == second.selected.score
    assert first.selected.repeat_count == second.selected.repeat_count
    assert first.diagnostics["items_detected"] == second.diagnostics["items_detected"]
    assert first.diagnostics["method"] == "dom_discovery"


def test_parser_uses_dom_discovery_as_fallback():
    raw = collect_local_source(URL, html_path=FIXTURES / "dom_menu_categories.html")
    catalogue = parse_swiggy_catalogue(raw)
    assert catalogue.extraction_status == "ok"
    assert catalogue.source_type == "dom_discovery"
    assert catalogue.restaurant.name == "Harbor Leaf Cafe"
    names = [category.name for category in catalogue.categories]
    assert names == ["Wood Fired", "Sides", "Drinks"]
    items = [item.name for category in catalogue.categories for item in category.items]
    assert "Garden Margherita" in items
    assert catalogue.item_count == 8


def test_structured_json_is_preferred_over_dom_discovery():
    payload = {
        "data": {
            "cards": [
                {
                    "card": {
                        "card": {
                            "@type": "type.googleapis.com/swiggy.presentation.food.v2.Restaurant",
                            "info": {"name": "Harbor Spice House", "cuisines": ["Coastal"]},
                        }
                    }
                },
                {
                    "card": {
                        "card": {
                            "@type": "type.googleapis.com/swiggy.presentation.food.v2.ItemCategory",
                            "title": "Breads",
                            "itemCards": [{"card": {"info": {"id": "x", "name": "Butter Naan", "price": 7000}}}],
                        }
                    }
                },
            ]
        }
    }
    raw = RawSource(
        source_url=URL,
        api_payloads=[payload],
        html=_html("dom_menu_categories.html"),
    )
    catalogue = parse_swiggy_catalogue(raw)
    assert catalogue.source_type == "xhr_json"
    assert [category.name for category in catalogue.categories] == ["Breads"]
    assert catalogue.categories[0].items[0].name == "Butter Naan"

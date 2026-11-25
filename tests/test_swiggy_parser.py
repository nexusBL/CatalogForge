import json
from pathlib import Path

from scraper.swiggy.models import RawSource
from scraper.swiggy.parser import parse_swiggy_catalogue, restaurant_slug_from_url

FIXTURE = Path(__file__).parent / "fixtures" / "swiggy_menu_payload.json"


def _catalogue():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw = RawSource(
        source_url="https://www.swiggy.com/city/mangaluru/harbor-spice-house-rest999001",
        api_payloads=[payload],
    )
    return parse_swiggy_catalogue(raw)


def test_restaurant_fields_from_structured_payload():
    catalogue = _catalogue()
    restaurant = catalogue.restaurant
    assert catalogue.source == "swiggy"
    assert catalogue.source_url.endswith("rest999001")
    assert restaurant.name == "Harbor Spice House"
    assert restaurant.rating == 4.4
    assert restaurant.rating_count == "1K+"
    assert restaurant.price_for_two == "₹1200 for two"
    assert restaurant.cuisines == ["Coastal", "North Indian"]
    assert restaurant.outlet == "Sample Road, Sample Area"
    assert restaurant.address == "1 Sample Road, Sample Area, Mangaluru"
    assert restaurant.fssai_license == "12345678901234"
    assert restaurant.image_url.endswith("test/restaurant-image")
    assert restaurant.offers


def test_categories_are_discovered_dynamically():
    catalogue = _catalogue()
    names = [category.name for category in catalogue.categories]
    assert names == ["Veg Combos", "Breads"]
    assert "Starters" not in names


def test_items_preserve_category_relationship_and_images():
    catalogue = _catalogue()
    by_name = {category.name: category for category in catalogue.categories}
    thali = by_name["Veg Combos"].items[0]
    assert thali.name == "Coastal Thali"
    assert thali.description == "Rice, curry and sides"
    assert thali.price == 349
    assert thali.original_price == 399
    assert thali.food_type == "VEG"
    assert thali.rating == 4.5
    assert thali.rating_count == "80"
    assert "Bestseller" in thali.labels
    assert thali.variants
    assert thali.customizations
    assert thali.image_url.endswith("test/item-thali")
    assert thali.nutritional_information == {"calories": "720 kcal"}
    assert thali.additional_information.get("serving") == "Serves 1"


def test_duplicate_items_are_removed():
    catalogue = _catalogue()
    breads = next(category for category in catalogue.categories if category.name == "Breads")
    assert len(breads.items) == 1
    assert breads.items[0].name == "Butter Naan"


def test_missing_values_stay_null_and_nothing_is_invented():
    raw = RawSource(
        source_url="https://www.swiggy.com/city/x/demo-rest1",
        api_payloads=[{"data": {"cards": []}}],
        blocked=True,
        http_status=403,
        waf_action="challenge",
        reason="blocked",
    )
    catalogue = parse_swiggy_catalogue(raw)
    assert catalogue.restaurant.name is None
    assert catalogue.restaurant.cuisines == []
    assert catalogue.categories == []
    assert catalogue.extraction.blocked is True
    assert catalogue.extraction.http_status == 403
    assert catalogue.extraction_status == "blocked"
    assert catalogue.item_count == 0
    assert catalogue.image_count == 0
    assert catalogue.error
    assert catalogue.extraction.ok is False


def test_slug_from_url():
    slug = restaurant_slug_from_url(
        "https://www.swiggy.com/city/mangaluru/barbeque-nation-father-mullers-road-kankanady-rest302695"
    )
    assert slug == "barbeque-nation-father-mullers-road-kankanady-rest302695"


def test_bestseller_and_unavailable_items_are_preserved():
    payload = {
        "data": {
            "cards": [
                {
                    "card": {
                        "card": {
                            "@type": "type.googleapis.com/swiggy.presentation.food.v2.Restaurant",
                            "info": {"name": "Night Kitchen", "id": "1"},
                        }
                    }
                },
                {
                    "groupedCard": {
                        "cardGroupMap": {
                            "REGULAR": {
                                "cards": [
                                    {
                                        "card": {
                                            "card": {
                                                "@type": "type.googleapis.com/swiggy.presentation.food.v2.ItemCategory",
                                                "title": "Late Night",
                                                "itemCards": [
                                                    {
                                                        "card": {
                                                            "info": {
                                                                "id": "u1",
                                                                "name": "Unavailable Pizza",
                                                                "price": 28900,
                                                                "isVeg": 1,
                                                                "inStock": 0,
                                                                "nextAvailableAtMessage": "Next available at 11 pm, today",
                                                                "isBestseller": True,
                                                            }
                                                        }
                                                    }
                                                ],
                                            }
                                        }
                                    }
                                ]
                            }
                        }
                    }
                },
            ]
        }
    }
    raw = RawSource(source_url="https://www.swiggy.com/city/x/night-kitchen-rest1", api_payloads=[payload])
    catalogue = parse_swiggy_catalogue(raw)
    item = catalogue.categories[0].items[0]
    assert item.name == "Unavailable Pizza"
    assert item.available is False
    assert item.next_available == "Next available at 11 pm, today"
    assert item.is_bestseller is True
    assert "Bestseller" in item.labels


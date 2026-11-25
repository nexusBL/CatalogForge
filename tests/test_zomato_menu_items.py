from scraper.swiggy.models import RawSource
from scraper.zomato.parser import _menu_from_text, parse_zomato_catalogue

MENU_WITH_ITEMS = """
Brew 59
Belgaum
Recommended (2)
Starters (1)
Search within menu
Recommended
Fresh Lemonade
₹120
Chilled lemonade served here
Starters
Paneer Tikka
₹249
Tandoor starter from this kitchen
"""

SIDEBAR_ONLY = """
Brew 59
Recommended (12)
Mains (8)
Desserts (5)
Search within menu
Download the App
"""


def test_text_menu_keeps_dishes_prices_and_descriptions():
    categories = _menu_from_text(MENU_WITH_ITEMS)
    names = [item.name for category in categories for item in category.items]
    assert "Fresh Lemonade" in names
    assert "Paneer Tikka" in names
    lemonade = next(item for category in categories for item in category.items if item.name == "Fresh Lemonade")
    assert lemonade.price == 120
    assert lemonade.description
    assert all(category.items for category in categories)


def test_sidebar_counts_without_dishes_do_not_become_empty_categories():
    categories = _menu_from_text(SIDEBAR_ONLY)
    assert categories == []


def test_parse_zomato_catalogue_persists_menu_items():
    html = "<html><body><h1>Brew 59</h1><p>Belgaum</p></body></html>"
    raw = RawSource(
        source_url="https://www.zomato.com/belgaum/brew-59-belgaum",
        html=html,
        page_text=MENU_WITH_ITEMS,
        access_status="ok",
    )
    catalogue = parse_zomato_catalogue(raw)
    names = [item.name for category in catalogue.categories for item in category.items]
    assert "Fresh Lemonade" in names
    lemonade = next(item for category in catalogue.categories for item in category.items if item.name == "Fresh Lemonade")
    assert lemonade.price == 120
    assert catalogue.item_count >= 2

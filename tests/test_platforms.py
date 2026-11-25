from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.main import app, require_session
from backend.schemas import AuthUser, CatalogCreateRequest, CatalogCreateResponse
from backend.services.catalog_service import AccessResult, SwiggyAccess, create_catalog
from scraper.cli import main
from scraper.magicpin.parser import (
    delivery_menu_url,
    merge_magicpin_images,
    merge_magicpin_menu,
    parse_magicpin_catalogue,
    photos_gallery_url,
)
from scraper.platform import platform_url_error
from scraper.swiggy.models import RawSource
from scraper.zomato.parser import merge_zomato_images, order_menu_url, parse_zomato_catalogue, photos_gallery_url as zomato_photos_url

ZOMATO_HTML = Path(__file__).parent / "fixtures" / "zomato_venue.html"
ZOMATO_ORDER_HTML = Path(__file__).parent / "fixtures" / "zomato_order.html"
ZOMATO_PHOTOS_HTML = Path(__file__).parent / "fixtures" / "zomato_photos.html"
MAGICPIN_HTML = Path(__file__).parent / "fixtures" / "magicpin_store.html"
MAGICPIN_PHOTOS_HTML = Path(__file__).parent / "fixtures" / "magicpin_photos.html"
MAGICPIN_DELIVERY_HTML = Path(__file__).parent / "fixtures" / "magicpin_delivery.html"
ZOMATO_URL = "https://www.zomato.com/bangalore/daffys-brewgarden-indiranagar-bangalore"
MAGICPIN_URL = "https://magicpin.in/Bangalore/Defence-Colony/Restaurant/Daffys-Brewgarden/store/5642c9"
SWIGGY_URL = "https://www.swiggy.com/city/bangalore/daffys-brewgarden-rest1242667"


class HtmlAccess(SwiggyAccess):
    def __init__(self, html: str):
        self.html = html

    def load(self, url: str):
        return AccessResult(
            method="local_fixture",
            raw=RawSource(source_url=url, access_status="ok", html=self.html, page_text=""),
        )


def test_platform_url_mismatch_message():
    assert platform_url_error("zomato", SWIGGY_URL) == (
        "You selected Zomato, but the URL does not appear to be a Zomato URL."
    )
    assert platform_url_error("magicpin", ZOMATO_URL) == (
        "You selected Magicpin, but the URL does not appear to be a Magicpin URL."
    )


def test_explicit_platform_is_not_inferred_from_url():
    with pytest.raises(ValidationError) as exc:
        CatalogCreateRequest.model_validate(
            {
                "restaurant_name": "Daffy's Brewgarden",
                "fssai_number": "12345678901234",
                "swiggy_url": SWIGGY_URL,
                "organization_id": "org_1",
                "platform": "zomato",
            }
        )
    assert "You selected Zomato" in str(exc.value)


def test_zomato_fixture_extracts_identity_menu_and_excludes_recommendations():
    html = ZOMATO_HTML.read_text(encoding="utf-8")
    raw = RawSource(source_url=ZOMATO_URL, access_status="ok", html=html, page_text=html)
    catalogue = parse_zomato_catalogue(raw)
    assert catalogue.extraction_status == "ok"
    assert catalogue.restaurant.name == "Daffy's Brewgarden"
    assert catalogue.restaurant.dining_rating == 4.4
    assert catalogue.restaurant.delivery_rating == 4.0
    assert catalogue.restaurant.outlet == "Indiranagar, Bangalore"
    names = [item.name for category in catalogue.categories for item in category.items]
    assert "Chandni Mushroom" in names
    assert "The Balcony Bar" not in names
    gallery = " ".join(item.get("url", "") for item in (catalogue.dineout.gallery_images if catalogue.dineout else []))
    assert "nearby.jpg" not in gallery
    offer_titles = [offer["title"] for offer in (catalogue.dineout.offers if catalogue.dineout else [])]
    assert "Flat 20% OFF" in offer_titles
    assert "Flat 10% OFF" in offer_titles
    assert catalogue.dineout and "12.97" in (catalogue.dineout.location.get("maps_url") or "")
    assert catalogue.dineout.directions_url == catalogue.dineout.location.get("maps_url")


def test_magicpin_fixture_extracts_identity_and_keeps_menu_images_separate():
    raw = RawSource(
        source_url=MAGICPIN_URL,
        access_status="ok",
        html=MAGICPIN_HTML.read_text(encoding="utf-8"),
        page_text="Save 5%\nMore restaurants\nSave 63%\nSponsored deals\nSave 55%",
    )
    catalogue = parse_magicpin_catalogue(raw)
    assert catalogue.extraction_status == "ok"
    assert catalogue.restaurant.name == "Daffy's Brewgarden"
    assert catalogue.restaurant.restaurant_id == "5642c9"
    assert catalogue.restaurant.rating == 4.4
    titles = [offer["title"] for offer in catalogue.restaurant.offers]
    assert "Save 5%" in titles
    assert "Flat 15% OFF" in titles
    assert catalogue.dineout and catalogue.dineout.location.get("maps_url") == "https://www.google.com/maps?q=12.96710793,77.64128275"
    assert catalogue.dineout.directions_url == catalogue.dineout.location.get("maps_url")
    gallery = " ".join(item.get("url", "") for item in (catalogue.dineout.gallery_images if catalogue.dineout else []))
    assert "nearby.jpg" not in gallery
    menu_urls = " ".join(" ".join(page.get("images") or []) for page in (catalogue.dineout.menu_pages if catalogue.dineout else []))
    assert "menu.jpg" in menu_urls
    assert "menu.jpg" not in gallery


def test_magicpin_photos_url_is_the_plus_photos_gallery():
    assert photos_gallery_url(MAGICPIN_URL) == f"{MAGICPIN_URL}/photos?img=photos&id=1"
    assert photos_gallery_url(f"{MAGICPIN_URL}/photos?img=photos&id=1") is None


def test_magicpin_photos_page_keeps_venue_google_photos_and_drops_nearby():
    photos = parse_magicpin_catalogue(
        RawSource(
            source_url=f"{MAGICPIN_URL}/photos?img=photos&id=1",
            access_status="ok",
            html=MAGICPIN_PHOTOS_HTML.read_text(encoding="utf-8"),
        )
    )
    gallery = " ".join(item.get("url", "") for item in (photos.dineout.gallery_images if photos.dineout else []))
    assert "QZAcMtn1wbhj3DVLlfuQ6DcUKNs1gurPoUq7ODn1x43e6GjtETLI6n2BEpAubjOSD2KvUNy1Ah7FWKwp_2fR-Rin_9oXQDJh3GyGZg8N" in gallery
    assert "bobs-bar-h320-rw" in gallery
    assert "=w200-rw" not in gallery
    assert "=w400-rw" not in gallery
    assert "OTHERRESTAURANT" not in gallery
    assert "ELECTRONICSREPAIR" not in gallery
    assert "GENERALINSURANCE" not in gallery
    store = parse_magicpin_catalogue(
        RawSource(
            source_url=MAGICPIN_URL,
            access_status="ok",
            html=MAGICPIN_HTML.read_text(encoding="utf-8"),
        )
    )
    merged = merge_magicpin_images(store, photos)
    assert merged.image_count >= 3
    assert any("googleusercontent.com" in (item.get("url") or "") for item in merged.dineout.gallery_images)


def test_create_catalog_zomato_and_magicpin_types():
    html = ZOMATO_HTML.read_text(encoding="utf-8")
    access = HtmlAccess(html)
    restaurant = create_catalog(
        CatalogCreateRequest.model_validate(
            {
                "restaurant_name": "Daffy's Brewgarden",
                "fssai_number": "12345678901234",
                "swiggy_url": ZOMATO_URL,
                "organization_id": "org_1",
                "platform": "zomato",
                "catalogue_type": "restaurant",
            }
        ),
        access,
    )
    assert restaurant.extraction_status == "ok"
    assert restaurant.platform == "zomato"
    dineout = create_catalog(
        CatalogCreateRequest.model_validate(
            {
                "restaurant_name": "Daffy's Brewgarden",
                "swiggy_url": ZOMATO_URL,
                "organization_id": "org_1",
                "platform": "zomato",
                "catalogue_type": "dineout",
            }
        ),
        access,
    )
    assert dineout.catalogue_type == "dineout"
    assert dineout.dineout["venue"] == "Daffy's Brewgarden"
    both = create_catalog(
        CatalogCreateRequest.model_validate(
            {
                "restaurant_name": "Daffy's Brewgarden",
                "fssai_number": "12345678901234",
                "swiggy_url": MAGICPIN_URL,
                "dineout_url": MAGICPIN_URL,
                "organization_id": "org_1",
                "platform": "magicpin",
                "catalogue_type": "both",
            }
        ),
        HtmlAccess(MAGICPIN_HTML.read_text(encoding="utf-8")),
    )
    assert both.platform == "magicpin"
    assert both.restaurant["name"] == "Daffy's Brewgarden"
    assert both.dineout["venue"] == "Daffy's Brewgarden"


def test_cli_platform_and_catalogue_type(tmp_path):
    out_dir = tmp_path / "out"
    code = main(
        [
            ZOMATO_URL,
            "--platform",
            "zomato",
            "--catalogue-type",
            "dineout",
            "--from-html",
            str(ZOMATO_HTML),
            "--out-dir",
            str(out_dir),
        ]
    )
    assert code == 0
    saved = next(out_dir.glob("*.json"))
    payload = __import__("json").loads(saved.read_text(encoding="utf-8"))
    assert payload["platform"] == "zomato"
    assert payload["catalogue_type"] == "dineout"
    assert payload["restaurant"]["name"] == "Daffy's Brewgarden"


def test_cli_rejects_platform_url_mismatch():
    assert (
        main(
            [
                SWIGGY_URL,
                "--platform",
                "zomato",
            ]
        )
        == 2
    )


def test_legacy_payload_without_platform_defaults_from_url():
    swiggy = CatalogCreateResponse.model_validate(
        {
            "extraction_status": "ok",
            "restaurant_name": "Harbor Spice House",
            "fssai_number": "1",
            "source_url": SWIGGY_URL,
        }
    )
    assert swiggy.platform == "swiggy"
    zomato = CatalogCreateResponse.model_validate(
        {
            "extraction_status": "ok",
            "restaurant_name": "Daffy's Brewgarden",
            "fssai_number": "1",
            "source_url": ZOMATO_URL,
        }
    )
    assert zomato.platform == "zomato"


def test_api_rejects_mismatched_platform_url():
    app.dependency_overrides[require_session] = lambda: AuthUser(id="user_1", email="owner@example.com")
    try:
        client = TestClient(app)
        response = client.post(
            "/catalog/create",
            json={
                "restaurant_name": "Daffy's Brewgarden",
                "fssai_number": "12345678901234",
                "swiggy_url": SWIGGY_URL,
                "organization_id": "org_1",
                "platform": "zomato",
            },
        )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_zomato_blocked_is_not_success():
    class BlockedAccess(SwiggyAccess):
        def load(self, url: str):
            return AccessResult(
                method="local_fixture",
                raw=RawSource(source_url=url, blocked=True, access_status="blocked", reason="denied"),
            )

    result = create_catalog(
        CatalogCreateRequest.model_validate(
            {
                "restaurant_name": "Daffy's Brewgarden",
                "fssai_number": "12345678901234",
                "swiggy_url": ZOMATO_URL,
                "organization_id": "org_1",
                "platform": "zomato",
            }
        ),
        BlockedAccess(),
    )
    assert result.extraction_status == "blocked"
    assert result.restaurant is None
    assert result.item_count == 0


def test_zomato_order_online_uses_sidebar_and_dish_photos():
    raw = RawSource(
        source_url=f"{ZOMATO_URL}/order",
        access_status="ok",
        html=ZOMATO_ORDER_HTML.read_text(encoding="utf-8"),
    )
    catalogue = parse_zomato_catalogue(raw)
    names = [item.name for category in catalogue.categories for item in category.items]
    assert "Ambur Egg Biryani" in names
    assert "Ambur Biryani Rice (kushka)" in names
    assert "Open now" not in names
    assert "info-line" not in names
    assert "call" not in names
    assert "+918043747373" not in names
    assert "direction-line" not in names
    assert "Chinese" not in names
    egg = next(item for category in catalogue.categories for item in category.items if item.name == "Ambur Egg Biryani")
    assert egg.image_url and "dish_photos" in egg.image_url
    rice = next(item for category in catalogue.categories for item in category.items if "Biryani Rice" in item.name)
    assert rice.image_url and "dish_photos" in rice.image_url
    names = {category.name: category for category in catalogue.categories}
    assert list(names)[:3] == ["Our Traditional Briyani", "Starters", "Main Course"]
    assert names["Our Traditional Briyani"].item_count == 9
    assert names["Starters"].item_count == 55
    assert names["Dessert"].item_count == 2
    assert names["Sides / Extra"].item_count == 5
    assert {item.name for item in names["Our Traditional Briyani"].items} >= {"Ambur Egg Biryani", "Ambur Biryani Rice (kushka)"}
    assert any(item.name == "Ambur Chicken 65" for item in names["Starters"].items)
    chicken65 = next(item for item in names["Starters"].items if item.name == "Ambur Chicken 65")
    assert chicken65.image_url and "lazy-chicken65" in chicken65.image_url
    gravy = next(item for item in names["Main Course"].items if item.name == "Chicken Gravy")
    assert gravy.image_url and "chicken-gravy" in gravy.image_url
    assert any(item.name == "Gulab Jamun" for item in names["Dessert"].items)
    from scraper.platform_dom import debug_item_image

    trace = debug_item_image(catalogue.categories, "Ambur Egg Biryani")
    assert trace and trace["category"] == "Our Traditional Briyani" and "dish_photos" in (trace["image_url"] or "")
    gallery = " ".join(item.get("url", "") for item in (catalogue.dineout.gallery_images if catalogue.dineout else []))
    assert "hero.jpg" in gallery
    assert all("dish_photos" not in (item.get("url") or "") for item in (catalogue.dineout.gallery_images if catalogue.dineout else []))


def test_zomato_photos_tab_url_is_view_gallery():
    assert zomato_photos_url(ZOMATO_URL) == f"{ZOMATO_URL}/photos"
    assert order_menu_url(ZOMATO_URL) == f"{ZOMATO_URL}/order"
    assert zomato_photos_url(f"{ZOMATO_URL}/photos") is None
    photos = parse_zomato_catalogue(
        RawSource(
            source_url=f"{ZOMATO_URL}/photos",
            access_status="ok",
            html=ZOMATO_PHOTOS_HTML.read_text(encoding="utf-8"),
        )
    )
    overview = parse_zomato_catalogue(
        RawSource(source_url=ZOMATO_URL, access_status="ok", html=ZOMATO_HTML.read_text(encoding="utf-8"))
    )
    merged = merge_zomato_images(overview, photos)
    gallery = " ".join(item.get("url", "") for item in (merged.dineout.gallery_images if merged.dineout else []))
    assert "gallery-one.jpg" in gallery
    assert "gallery-three.jpg" in gallery
    assert "gallery-four.jpg" in gallery
    assert "nearby.jpg" not in gallery


def test_magicpin_delivery_tab_parses_priced_dishes():
    assert delivery_menu_url(MAGICPIN_URL) == f"{MAGICPIN_URL}/delivery"
    assert delivery_menu_url(f"{MAGICPIN_URL}/delivery") is None
    delivery = parse_magicpin_catalogue(
        RawSource(
            source_url=f"{MAGICPIN_URL}/delivery",
            access_status="ok",
            html=MAGICPIN_DELIVERY_HTML.read_text(encoding="utf-8"),
        )
    )
    names = [item.name for category in delivery.categories for item in category.items]
    assert "Dry Fruit Lassi" in names
    assert "Half Chicken Boneless Kebab" in names
    assert "Hara Bhara Kebab" in names
    assert not any("customFont" in name or "75%" in name for name in names)
    lassi = next(item for category in delivery.categories for item in category.items if item.name == "Dry Fruit Lassi")
    assert lassi.price == 36
    assert lassi.original_price == 91
    assert lassi.image_url and "googleusercontent.com" in lassi.image_url
    assert "veg-icon" not in (lassi.image_url or "")
    names_by_cat = {category.name: [item.name for item in category.items] for category in delivery.categories}
    assert "Recommended" in names_by_cat
    assert "Biryani Family Pack (Save Upto Rs 150/-)" in names_by_cat
    assert "Desserts" in names_by_cat
    assert "Beverages" in names_by_cat
    assert names_by_cat["Recommended"][0] == "Dry Fruit Lassi"
    assert "Hara Bhara Kebab" in names_by_cat["Starters"]
    assert "Paneer Makhni Biryani" in names_by_cat["Veg Biryanis"]
    assert "Hyderabadi Chicken Dum Biryani" in names_by_cat["Non Veg Biryanis"]
    assert "Gulab Jamun" in names_by_cat["Desserts"]
    assert "Sweet Lassi" in names_by_cat["Beverages"]
    paneer = next(item for category in delivery.categories for item in category.items if item.name == "Paneer Makhni Biryani")
    assert paneer.image_url and "paneerMakhniBiryaniPhoto" in paneer.image_url
    chicken = next(
        item for category in delivery.categories for item in category.items if item.name == "Hyderabadi Chicken Dum Biryani"
    )
    assert chicken.image_url and "hyderabadiChicken" in chicken.image_url
    from scraper.platform_dom import debug_item_image, is_dish_image

    trace = debug_item_image(delivery.categories, "Paneer Makhni Biryani")
    assert trace and trace["category"] == "Veg Biryanis"
    assert is_dish_image("https://lh3.googleusercontent.com/food=w400-rw")
    assert is_dish_image("https://lh3.googleusercontent.com/food=w512-rw")
    assert not is_dish_image("https://magicpin.in/images/merchant/veg-icon.svg")
    assert not is_dish_image("https://lh3.googleusercontent.com/thumb=w200-rw")
    recommended = next(category for category in delivery.categories if category.name == "Recommended")
    assert recommended.item_count == 12
    gallery = " ".join(item.get("url", "") for item in (delivery.dineout.gallery_images if delivery.dineout else []))
    assert "nearby restaurant" not in gallery
    assert all("veg-icon" not in (item.image_url or "") for category in delivery.categories for item in category.items)
    store = parse_magicpin_catalogue(
        RawSource(source_url=MAGICPIN_URL, access_status="ok", html=MAGICPIN_HTML.read_text(encoding="utf-8"))
    )
    merged = merge_magicpin_menu(store, delivery)
    assert merged.item_count >= 3


def test_live_dom_menu_attaches_item_images():
    zomato = parse_zomato_catalogue(
        RawSource(
            source_url=f"{ZOMATO_URL}/order",
            access_status="ok",
            html='<h1>Ambur Star Briyani Since 1890</h1>',
            dom_menu=[
                {
                    "name": "Our Traditional Briyani",
                    "items": [
                        {
                            "name": "Ambur Egg Biryani",
                            "image_url": "https://b.zmtcdn.com/data/dish_photos/0d8/egg.jpeg",
                        }
                    ],
                }
            ],
        )
    )
    egg = zomato.categories[0].items[0]
    assert egg.name == "Ambur Egg Biryani"
    assert "dish_photos" in (egg.image_url or "")
    magicpin = parse_magicpin_catalogue(
        RawSource(
            source_url=f"{MAGICPIN_URL}/delivery",
            access_status="ok",
            html="<h1>Biryani Trip</h1>",
            dom_menu=[
                {
                    "name": "Recommended",
                    "items": [
                        {
                            "name": "Dry Fruit Lassi",
                            "price": 36,
                            "original_price": 91,
                            "image_url": "https://lh3.googleusercontent.com/lassi=w512-rw",
                        }
                    ],
                }
            ],
        )
    )
    lassi = magicpin.categories[0].items[0]
    assert lassi.name == "Dry Fruit Lassi"
    assert lassi.price == 36
    assert "googleusercontent.com" in (lassi.image_url or "")


def test_empty_harvested_categories_take_items_from_delivery_html():
    catalogue = parse_magicpin_catalogue(
        RawSource(
            source_url=f"{MAGICPIN_URL}/delivery",
            access_status="ok",
            html=MAGICPIN_DELIVERY_HTML.read_text(encoding="utf-8"),
            dom_menu=[
                {"name": "Recommended", "item_count": 12, "items": [{"name": "Dry Fruit Lassi", "price": 36}]},
                {"name": "Desserts", "item_count": 3, "items": []},
                {"name": "Beverages", "item_count": 9, "items": []},
            ],
        )
    )
    by_name = {category.name: [item.name for item in category.items] for category in catalogue.categories}
    assert "Gulab Jamun" in by_name["Desserts"]
    assert "Sweet Lassi" in by_name["Beverages"]


def test_magicpin_does_not_assign_unmatched_or_nearby_images():
    delivery = parse_magicpin_catalogue(
        RawSource(
            source_url=f"{MAGICPIN_URL}/delivery",
            access_status="ok",
            html=MAGICPIN_DELIVERY_HTML.read_text(encoding="utf-8"),
        )
    )
    nearby_marker = "lKOn3sjFnX_V39VegMnYAATs8nvdd74i0RGIYNOVtc88vk47xavR2ovF8Pvob61ULAmtjrozFK751teKxTLpvQMvdZZtlk6rxIyylO87"
    items = [item for category in delivery.categories for item in category.items]
    assert items
    assert all(nearby_marker not in (item.image_url or "") for item in items)
    lassi = next(item for item in items if item.name == "Dry Fruit Lassi")
    assert lassi.image_url and "d0XzTeHvfnkSBdMkZ4GeiKbw0lg0v8kFMp8zaKmCvgtZ5ktJtTAmbbbdRB86Rm6p_WJ2ZRqjJH2iWz5CDczPMjOYK2pYDWZJ2wfVp1Ms" in lassi.image_url
    chicken = next(item for item in items if item.name == "Hyderabadi Chicken Dum Biryani")
    assert chicken.image_url and "hyderabadiChicken" in chicken.image_url
    assert chicken.image_url != lassi.image_url


def test_create_catalog_follows_zomato_order_and_magicpin_delivery():
    class MapAccess(SwiggyAccess):
        def __init__(self, mapping: dict[str, str]):
            self.mapping = mapping

        def load(self, url: str):
            html = self.mapping[url]
            return AccessResult(
                method="local_fixture",
                raw=RawSource(source_url=url, access_status="ok", html=html),
            )

    zomato = create_catalog(
        CatalogCreateRequest.model_validate(
            {
                "restaurant_name": "Ambur Star Briyani Since 1890",
                "fssai_number": "12345678901234",
                "swiggy_url": "https://www.zomato.com/bangalore/ambur-star-briyani-since-1890-indiranagar-bangalore",
                "organization_id": "org_1",
                "platform": "zomato",
                "catalogue_type": "restaurant",
            }
        ),
        MapAccess(
            {
                "https://www.zomato.com/bangalore/ambur-star-briyani-since-1890-indiranagar-bangalore": ZOMATO_ORDER_HTML.read_text(
                    encoding="utf-8"
                ),
                "https://www.zomato.com/bangalore/ambur-star-briyani-since-1890-indiranagar-bangalore/order": ZOMATO_ORDER_HTML.read_text(
                    encoding="utf-8"
                ),
                "https://www.zomato.com/bangalore/ambur-star-briyani-since-1890-indiranagar-bangalore/photos": ZOMATO_PHOTOS_HTML.read_text(
                    encoding="utf-8"
                ),
            }
        ),
    )
    names = [item["name"] for category in zomato.categories for item in category["items"]]
    assert "Ambur Egg Biryani" in names
    assert "Open now" not in names
    magicpin = create_catalog(
        CatalogCreateRequest.model_validate(
            {
                "restaurant_name": "Biryani Trip",
                "fssai_number": "12345678901234",
                "swiggy_url": MAGICPIN_URL,
                "organization_id": "org_1",
                "platform": "magicpin",
                "catalogue_type": "restaurant",
            }
        ),
        MapAccess(
            {
                MAGICPIN_URL: MAGICPIN_HTML.read_text(encoding="utf-8"),
                f"{MAGICPIN_URL}/delivery": MAGICPIN_DELIVERY_HTML.read_text(encoding="utf-8"),
                f"{MAGICPIN_URL}/photos?img=photos&id=1": MAGICPIN_PHOTOS_HTML.read_text(encoding="utf-8"),
            }
        ),
    )
    names = [item["name"] for category in magicpin.categories for item in category["items"]]
    assert "Dry Fruit Lassi" in names
    assert magicpin.item_count >= 3

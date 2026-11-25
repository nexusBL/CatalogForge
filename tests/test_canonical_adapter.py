from __future__ import annotations

import json
from pathlib import Path

from scraper.swiggy.models import Catalogue, MenuCategory, MenuItem, Restaurant
from scraper.swiggy.parser import parse_swiggy_catalogue
from scraper.swiggy.models import RawSource

from backend.canonical.adapter import ExistingCatalogueAdapter
from backend.canonical.project import apply_canonical_to_response
from backend.schemas import CatalogCreateRequest, CatalogCreateResponse

FIXTURE_JSON = Path(__file__).parent / "fixtures" / "swiggy_menu_payload.json"
SAMPLE = {
    "restaurant_name": "Harbor Spice House",
    "fssai_number": "12345678901234",
    "swiggy_url": "https://www.swiggy.com/city/mangaluru/harbor-spice-house-rest999001",
    "organization_id": "org_1",
}


def test_adapter_from_swiggy_fixture():
    raw = RawSource(source_url=SAMPLE["swiggy_url"], next_data=json.loads(FIXTURE_JSON.read_text(encoding="utf-8")))
    parsed = parse_swiggy_catalogue(raw)
    request = CatalogCreateRequest.model_validate(SAMPLE)
    document = ExistingCatalogueAdapter().to_canonical(parsed, request=request, access_method="local_fixture")
    assert document.provenance.platform == "swiggy"
    assert document.venue.source_entity_id == "999001"
    assert document.menus
    assert any(item.source_item_id == "m1" for category in document.menus[0].categories for item in category.items)
    result = CatalogCreateResponse(
        extraction_status="ok",
        restaurant_name=request.restaurant_name,
        fssai_number=request.fssai_number,
        source_url=request.swiggy_url,
        restaurant={"name": parsed.restaurant.name},
        categories=parsed.to_dict()["categories"],
        item_count=parsed.item_count,
    )
    projected = apply_canonical_to_response(result, document)
    assert projected.restaurant and projected.restaurant.get("restaurant_id") == "999001"


def test_adapter_keeps_platforms_as_separate_source_listings():
    adapter = ExistingCatalogueAdapter()
    swiggy = adapter.to_canonical(
        Catalogue(
            source="swiggy",
            source_url="https://www.swiggy.com/city/sample/alpha-resta",
            extraction_status="ok",
            restaurant=Restaurant(name="Alpha", restaurant_id="111"),
            categories=[MenuCategory(name="Mains", items=[MenuItem(name="Rice", additional_information={"id": "m1"})])],
            item_count=1,
        )
    )
    zomato = adapter.to_canonical(
        Catalogue(
            source="zomato",
            source_url="https://www.zomato.com/city/alpha",
            extraction_status="ok",
            restaurant=Restaurant(name="Alpha", restaurant_id="z-1", zomato_url="https://www.zomato.com/city/alpha"),
        )
    )
    assert swiggy.provenance.platform == "swiggy"
    assert zomato.provenance.platform == "zomato"
    assert swiggy.venue.source_entity_id == "111"
    assert zomato.venue.source_entity_id == "z-1"
    assert swiggy.venue.source_entity_id != zomato.venue.source_entity_id

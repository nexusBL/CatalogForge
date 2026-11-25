from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class MenuItem:
    name: str
    description: str | None = None
    price: float | int | None = None
    original_price: float | int | None = None
    food_type: str | None = None
    rating: float | None = None
    rating_count: int | str | None = None
    labels: list[str] = field(default_factory=list)
    variants: list[dict[str, Any]] = field(default_factory=list)
    customizations: list[dict[str, Any]] = field(default_factory=list)
    image_url: str | None = None
    source_image_url: str | None = None
    nutritional_information: dict[str, Any] | list[Any] | str | None = None
    additional_information: dict[str, Any] = field(default_factory=dict)
    is_bestseller: bool = False
    available: bool | None = None
    next_available: str | None = None


@dataclass
class MenuCategory:
    name: str
    items: list[MenuItem] = field(default_factory=list)
    item_count: int | None = None


@dataclass
class Restaurant:
    name: str | None = None
    rating: float | None = None
    rating_count: int | str | None = None
    price_for_two: str | int | float | None = None
    cuisines: list[str] = field(default_factory=list)
    outlet: str | None = None
    address: str | None = None
    fssai_license: str | None = None
    image_url: str | None = None
    offers: list[Any] = field(default_factory=list)
    additional_information: dict[str, Any] = field(default_factory=dict)
    zomato_rating: float | None = None
    zomato_url: str | None = None
    magicpin_rating: float | None = None
    magicpin_url: str | None = None
    dining_rating: float | None = None
    dining_rating_count: int | str | None = None
    delivery_rating: float | None = None
    delivery_rating_count: int | str | None = None
    phone: str | None = None
    opening_hours: str | None = None
    opening_status: str | None = None
    restaurant_id: str | None = None


@dataclass
class RawSource:
    source_url: str
    final_url: str | None = None
    http_status: int | None = None
    html: str | None = None
    next_data: dict[str, Any] | None = None
    json_ld: list[Any] = field(default_factory=list)
    api_payloads: list[Any] = field(default_factory=list)
    network_urls: list[str] = field(default_factory=list)
    blocked: bool = False
    access_status: str | None = None
    waf_action: str | None = None
    reason: str | None = None
    response_headers: dict[str, str] = field(default_factory=dict)
    page_title: str | None = None
    page_text: str | None = None
    screenshot_path: str | None = None
    window_state_keys: list[str] = field(default_factory=list)
    data_locations: list[str] = field(default_factory=list)
    dom_menu: list[dict[str, Any]] = field(default_factory=list)
    dom_images: list[dict[str, Any]] = field(default_factory=list)
    dom_discovery: dict[str, Any] | None = None
    browser_mode: str | None = None
    browser_path: str | None = None


@dataclass
class ExtractionMeta:
    ok: bool = False
    blocked: bool = False
    extraction_status: str = "failed"
    source_type: str | None = None
    http_status: int | None = None
    waf_action: str | None = None
    reason: str | None = None
    error: str | None = None
    source_kind: str | None = None
    data_locations: list[str] = field(default_factory=list)
    diagnostic_dir: str | None = None


@dataclass
class DineoutVenue:
    venue: str | None = None
    hero_image: str | None = None
    rating: float | None = None
    rating_count: int | str | None = None
    cuisines: list[str] = field(default_factory=list)
    price_for_two: str | int | float | None = None
    opening_hours: str | None = None
    opening_status: str | None = None
    actions: dict[str, str] = field(default_factory=dict)
    offers: list[dict[str, Any]] = field(default_factory=list)
    menu_pages: list[dict[str, Any]] = field(default_factory=list)
    popular_dishes: list[str] = field(default_factory=list)
    photos: list[str] = field(default_factory=list)
    gallery_images: list[dict[str, Any]] = field(default_factory=list)
    videos: list[dict[str, Any]] = field(default_factory=list)
    amenities: list[str] = field(default_factory=list)
    location: dict[str, Any] = field(default_factory=dict)
    location_map_image: str | None = None
    directions_url: str | None = None
    phone: str | None = None
    restaurant_id: str | None = None
    source_url: str | None = None


@dataclass
class Catalogue:
    source: str = "swiggy"
    source_url: str = ""
    catalogue_type: str = "restaurant"
    extraction_status: str = "failed"
    source_type: str | None = None
    restaurant: Restaurant = field(default_factory=Restaurant)
    dineout: DineoutVenue | None = None
    categories: list[MenuCategory] = field(default_factory=list)
    item_count: int = 0
    image_count: int = 0
    error: str | None = None
    extraction: ExtractionMeta = field(default_factory=ExtractionMeta)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def summary(self) -> dict[str, Any]:
        return {
            "extraction_status": self.extraction_status,
            "source_type": self.source_type,
            "restaurant": self.restaurant.name,
            "categories": len(self.categories),
            "items": self.item_count,
            "images": self.image_count,
            "error": self.error,
        }

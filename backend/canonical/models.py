from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

CatalogueKind = Literal["restaurant", "dineout", "both"]
MenuKind = Literal["delivery", "dineout_pages"]


class SourceLink(BaseModel):
    platform: str
    url: str | None = None
    source_entity_id: str | None = None
    role: str | None = None


class SourceRating(BaseModel):
    platform: str
    score: float | None = None
    count: int | str | None = None
    kind: str | None = None


class Provenance(BaseModel):
    platform: str
    source_url: str
    canonical_source_url: str
    source_entity_id: str | None = None
    scraped_at: str | None = None
    imported_at: str | None = None
    access_method: str | None = None
    source_type: str | None = None
    adapter_version: str = "canonical.v1"


class CanonicalMenuItem(BaseModel):
    item_id: str | None = None
    source_item_id: str | None = None
    name: str
    description: str | None = None
    price: float | int | None = None
    original_price: float | int | None = None
    food_type: str | None = None
    rating: float | None = None
    rating_count: int | str | None = None
    labels: list[str] = Field(default_factory=list)
    variants: list[dict[str, Any]] = Field(default_factory=list)
    customizations: list[dict[str, Any]] = Field(default_factory=list)
    image_url: str | None = None
    source_image_url: str | None = None
    nutritional_information: dict[str, Any] | list[Any] | str | None = None
    additional_information: dict[str, Any] = Field(default_factory=dict)
    is_bestseller: bool = False
    available: bool | None = None
    next_available: str | None = None


class CanonicalMenuCategory(BaseModel):
    name: str
    items: list[CanonicalMenuItem] = Field(default_factory=list)
    item_count: int | None = None


class CanonicalMenu(BaseModel):
    menu_kind: MenuKind = "delivery"
    categories: list[CanonicalMenuCategory] = Field(default_factory=list)


class CanonicalVenueData(BaseModel):
    """Current snapshot of a source listing. Not a cross-platform restaurant id."""

    name: str | None = None
    rating: float | None = None
    rating_count: int | str | None = None
    price_for_two: str | int | float | None = None
    cuisines: list[str] = Field(default_factory=list)
    outlet: str | None = None
    address: str | None = None
    fssai_license: str | None = None
    image_url: str | None = None
    offers: list[Any] = Field(default_factory=list)
    phone: str | None = None
    opening_hours: str | None = None
    opening_status: str | None = None
    dining_rating: float | None = None
    dining_rating_count: int | str | None = None
    delivery_rating: float | None = None
    delivery_rating_count: int | str | None = None
    source_links: list[SourceLink] = Field(default_factory=list)
    ratings: list[SourceRating] = Field(default_factory=list)
    additional_information: dict[str, Any] = Field(default_factory=dict)
    source_entity_id: str | None = None


class CanonicalDocument(BaseModel):
    schema_version: int = 1
    venue_id: str | None = None
    catalogue_type: CatalogueKind = "restaurant"
    extraction_status: str = "failed"
    restaurant_name: str = ""
    fssai_number: str = ""
    provenance: Provenance
    venue: CanonicalVenueData = Field(default_factory=CanonicalVenueData)
    menus: list[CanonicalMenu] = Field(default_factory=list)
    dineout: dict[str, Any] | None = None
    item_count: int = 0
    image_count: int = 0
    error: str | None = None
    source_type: str | None = None
    access_method: str | None = None

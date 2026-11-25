"""Canonical adapter boundary.

Approved flow: platform parser → platform-specific model → this adapter →
canonical model. Persistence (`backend.store`) writes only canonical /
legacy-response structures, not parser dataclasses.

`scraper.swiggy.models` (`Catalogue`, `Restaurant`, `MenuItem`) are the shared
post-parser dataclasses used as adapter *input* for every platform. They are
not imported by `backend.canonical.models` and are not a persistence dependency.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from scraper.discovery.urls import canonical_url
from scraper.swiggy.models import Catalogue, MenuItem, Restaurant

from backend.canonical.identity import (
    ADAPTER_VERSION,
    SCHEMA_VERSION,
    identity_tuple,
    normalize_platform,
    source_entity_id_from_result,
    source_item_id_from_item,
)
from backend.canonical.models import (
    CanonicalDocument,
    CanonicalMenu,
    CanonicalMenuCategory,
    CanonicalMenuItem,
    CanonicalVenueData,
    Provenance,
    SourceLink,
    SourceRating,
)
from backend.schemas import CatalogCreateRequest, CatalogCreateResponse


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _item_from_dict(raw: dict[str, Any]) -> CanonicalMenuItem:
    source_id = source_item_id_from_item(raw)
    return CanonicalMenuItem(
        item_id=str(raw["item_id"]).strip() if raw.get("item_id") else None,
        source_item_id=source_id,
        name=str(raw.get("name") or ""),
        description=raw.get("description"),
        price=raw.get("price"),
        original_price=raw.get("original_price"),
        food_type=raw.get("food_type"),
        rating=raw.get("rating"),
        rating_count=raw.get("rating_count"),
        labels=list(raw.get("labels") or []),
        variants=list(raw.get("variants") or []) if isinstance(raw.get("variants"), list) else [],
        customizations=list(raw.get("customizations") or []) if isinstance(raw.get("customizations"), list) else [],
        image_url=raw.get("image_url"),
        source_image_url=raw.get("source_image_url"),
        nutritional_information=raw.get("nutritional_information"),
        additional_information=dict(raw.get("additional_information") or {})
        if isinstance(raw.get("additional_information"), dict)
        else {},
        is_bestseller=bool(raw.get("is_bestseller")),
        available=raw.get("available") if isinstance(raw.get("available"), bool) else None,
        next_available=raw.get("next_available") if isinstance(raw.get("next_available"), str) else None,
    )


def _item_from_model(item: MenuItem) -> CanonicalMenuItem:
    return _item_from_dict(
        {
            "name": item.name,
            "description": item.description,
            "price": item.price,
            "original_price": item.original_price,
            "food_type": item.food_type,
            "rating": item.rating,
            "rating_count": item.rating_count,
            "labels": item.labels,
            "variants": item.variants,
            "customizations": item.customizations,
            "image_url": item.image_url,
            "source_image_url": item.source_image_url,
            "nutritional_information": item.nutritional_information,
            "additional_information": item.additional_information,
            "is_bestseller": item.is_bestseller,
            "available": item.available,
            "next_available": item.next_available,
        }
    )


def _links_and_ratings(restaurant: Restaurant, platform: str, source_url: str, source_id: str | None):
    links: list[SourceLink] = [
        SourceLink(platform=platform, url=source_url or None, source_entity_id=source_id, role="primary")
    ]
    ratings: list[SourceRating] = []
    if restaurant.rating is not None:
        ratings.append(SourceRating(platform=platform, score=restaurant.rating, count=restaurant.rating_count, kind="primary"))
    if restaurant.zomato_url:
        links.append(SourceLink(platform="zomato", url=restaurant.zomato_url, role="related"))
    if restaurant.zomato_rating is not None:
        ratings.append(SourceRating(platform="zomato", score=restaurant.zomato_rating, kind="listed"))
    if restaurant.magicpin_url:
        links.append(SourceLink(platform="magicpin", url=restaurant.magicpin_url, role="related"))
    if restaurant.magicpin_rating is not None:
        ratings.append(SourceRating(platform="magicpin", score=restaurant.magicpin_rating, kind="listed"))
    if restaurant.dining_rating is not None:
        ratings.append(
            SourceRating(platform=platform, score=restaurant.dining_rating, count=restaurant.dining_rating_count, kind="dining")
        )
    if restaurant.delivery_rating is not None:
        ratings.append(
            SourceRating(
                platform=platform, score=restaurant.delivery_rating, count=restaurant.delivery_rating_count, kind="delivery"
            )
        )
    return links, ratings


def _venue_from_restaurant(restaurant: Restaurant, platform: str, source_url: str, source_id: str | None) -> CanonicalVenueData:
    links, ratings = _links_and_ratings(restaurant, platform, source_url, source_id)
    extra = dict(restaurant.additional_information or {})
    extra.pop("parentId", None)
    return CanonicalVenueData(
        name=restaurant.name,
        rating=restaurant.rating,
        rating_count=restaurant.rating_count,
        price_for_two=restaurant.price_for_two,
        cuisines=list(restaurant.cuisines or []),
        outlet=restaurant.outlet,
        address=restaurant.address,
        fssai_license=restaurant.fssai_license,
        image_url=restaurant.image_url,
        offers=list(restaurant.offers or []),
        phone=restaurant.phone,
        opening_hours=restaurant.opening_hours,
        opening_status=restaurant.opening_status,
        dining_rating=restaurant.dining_rating,
        dining_rating_count=restaurant.dining_rating_count,
        delivery_rating=restaurant.delivery_rating,
        delivery_rating_count=restaurant.delivery_rating_count,
        source_links=links,
        ratings=ratings,
        additional_information=extra,
        source_entity_id=source_id,
    )


class ExistingCatalogueAdapter:
    """Map the shared parser Catalogue into a platform-neutral canonical document."""

    def to_canonical(
        self,
        parsed: Catalogue,
        *,
        request: CatalogCreateRequest | None = None,
        access_method: str | None = None,
        scraped_at: str | None = None,
    ) -> CanonicalDocument:
        platform = normalize_platform(parsed.source or (request.platform if request else None))
        source_url = parsed.source_url or (request.swiggy_url if request else "")
        payload = parsed.to_dict()
        restaurant_dict = payload.get("restaurant") if isinstance(payload.get("restaurant"), dict) else {}
        source_id = source_entity_id_from_result({"restaurant": restaurant_dict, "dineout": payload.get("dineout")})
        categories = [
            CanonicalMenuCategory(
                name=category.name,
                items=[_item_from_model(item) for item in category.items],
                item_count=category.item_count,
            )
            for category in parsed.categories
        ]
        dineout = payload.get("dineout") if isinstance(payload.get("dineout"), dict) else None
        menus: list[CanonicalMenu] = []
        if categories:
            menus.append(CanonicalMenu(menu_kind="delivery", categories=categories))
        restaurant_name = (request.restaurant_name if request else None) or parsed.restaurant.name or ""
        fssai = (request.fssai_number if request else None) or parsed.restaurant.fssai_license or ""
        catalogue_type = parsed.catalogue_type if parsed.catalogue_type in {"restaurant", "dineout", "both"} else "restaurant"
        if request is not None:
            catalogue_type = request.catalogue_type
        return CanonicalDocument(
            schema_version=SCHEMA_VERSION,
            catalogue_type=catalogue_type,  # type: ignore[arg-type]
            extraction_status=parsed.extraction_status,
            restaurant_name=restaurant_name,
            fssai_number=fssai,
            provenance=Provenance(
                platform=platform,
                source_url=source_url,
                canonical_source_url=canonical_url(source_url),
                source_entity_id=source_id,
                scraped_at=scraped_at or _now(),
                access_method=access_method,
                source_type=parsed.source_type,
                adapter_version=ADAPTER_VERSION,
            ),
            venue=_venue_from_restaurant(parsed.restaurant, platform, source_url, source_id),
            menus=menus,
            dineout=dineout if dineout and any(dineout.values()) else None,
            item_count=parsed.item_count,
            image_count=parsed.image_count,
            error=parsed.error,
            source_type=parsed.source_type,
            access_method=access_method,
        )


def to_canonical_from_response(result: CatalogCreateResponse, *, scraped_at: str | None = None) -> CanonicalDocument:
    payload = result.model_dump(mode="json")
    platform, url, source_id = identity_tuple(payload)
    restaurant = result.restaurant if isinstance(result.restaurant, dict) else {}
    rest_model = Restaurant(
        name=restaurant.get("name"),
        rating=restaurant.get("rating"),
        rating_count=restaurant.get("rating_count"),
        price_for_two=restaurant.get("price_for_two"),
        cuisines=list(restaurant.get("cuisines") or []) if isinstance(restaurant.get("cuisines"), list) else [],
        outlet=restaurant.get("outlet"),
        address=restaurant.get("address"),
        fssai_license=restaurant.get("fssai_license"),
        image_url=restaurant.get("image_url"),
        offers=list(restaurant.get("offers") or []) if isinstance(restaurant.get("offers"), list) else [],
        additional_information=dict(restaurant.get("additional_information") or {})
        if isinstance(restaurant.get("additional_information"), dict)
        else {},
        zomato_rating=restaurant.get("zomato_rating"),
        zomato_url=restaurant.get("zomato_url"),
        magicpin_rating=restaurant.get("magicpin_rating"),
        magicpin_url=restaurant.get("magicpin_url"),
        dining_rating=restaurant.get("dining_rating"),
        dining_rating_count=restaurant.get("dining_rating_count"),
        delivery_rating=restaurant.get("delivery_rating"),
        delivery_rating_count=restaurant.get("delivery_rating_count"),
        phone=restaurant.get("phone"),
        opening_hours=restaurant.get("opening_hours"),
        opening_status=restaurant.get("opening_status"),
        restaurant_id=restaurant.get("restaurant_id"),
    )
    categories = [
        CanonicalMenuCategory(
            name=str(category.get("name") or ""),
            items=[_item_from_dict(item) for item in (category.get("items") or []) if isinstance(item, dict)],
            item_count=category.get("item_count"),
        )
        for category in (result.categories or [])
        if isinstance(category, dict)
    ]
    dineout = result.dineout if isinstance(result.dineout, dict) else None
    menus = [CanonicalMenu(menu_kind="delivery", categories=categories)] if categories else []
    return CanonicalDocument(
        schema_version=SCHEMA_VERSION,
        venue_id=result.venue_id,
        catalogue_type=result.catalogue_type,
        extraction_status=result.extraction_status,
        restaurant_name=result.restaurant_name,
        fssai_number=result.fssai_number or "",
        provenance=Provenance(
            platform=platform,
            source_url=result.source_url,
            canonical_source_url=url,
            source_entity_id=source_id,
            scraped_at=scraped_at,
            access_method=result.access_method,
            source_type=result.source_type,
            adapter_version=ADAPTER_VERSION,
        ),
        venue=_venue_from_restaurant(rest_model, platform, result.source_url, source_id),
        menus=menus,
        dineout=dineout,
        item_count=result.item_count or 0,
        image_count=result.image_count or 0,
        error=result.error,
        source_type=result.source_type,
        access_method=result.access_method,
    )

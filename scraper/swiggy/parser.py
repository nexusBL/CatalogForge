from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

from scraper.swiggy.models import Catalogue, ExtractionMeta, MenuCategory, MenuItem, RawSource, Restaurant

IMAGE_CDN = "https://media-assets.swiggy.com/swiggy/image/upload/"

RESTAURANT_TYPE_HINTS = ("food.v2.Restaurant", "swiggy.presentation.food.v2.Restaurant")
ITEM_CATEGORY_HINTS = ("ItemCategory",)
NESTED_CATEGORY_HINTS = ("NestedItemCategory",)
MENU_COLLECTION_HINTS = ("MenuCarousel", "ItemCollection")
LICENSE_HINTS = ("RestaurantLicenseInfo", "LicenseInfo")
ADDRESS_HINTS = ("RestaurantAddress",)
OFFER_HINTS = ("GridWidget", "OfferInfo", "RestaurantOffer")


def parse_swiggy_catalogue(raw: RawSource) -> Catalogue:
    access_status = raw.access_status or ("blocked" if raw.blocked else None)
    if access_status == "blocked":
        return _result(
            raw,
            Restaurant(),
            [],
            status="blocked",
            source_type=None,
            error=raw.reason or "Swiggy blocked access to the restaurant page.",
        )

    payloads = list(raw.api_payloads)
    if raw.next_data:
        payloads.append(raw.next_data)
    payloads.extend(_json_ld_objects(raw.json_ld))

    restaurant_info: dict[str, Any] = {}
    license_info: dict[str, Any] = {}
    address_info: dict[str, Any] = {}
    offer_nodes: list[Any] = []
    category_nodes: list[dict[str, Any]] = []
    extra_schema_categories: list[MenuCategory] = []

    for payload in payloads:
        for node in _walk(payload):
            type_name = _type_name(node)
            if not isinstance(node, dict):
                continue
            if _is_restaurant_info(node, type_name):
                restaurant_info = _merge_info(restaurant_info, node.get("info") or node)
            if any(h in type_name for h in LICENSE_HINTS):
                license_info = _merge_info(license_info, node)
            if any(h in type_name for h in ADDRESS_HINTS):
                address_info = _merge_info(address_info, node)
            if any(h in type_name for h in OFFER_HINTS):
                offer_nodes.append(node)
            if any(h in type_name for h in NESTED_CATEGORY_HINTS):
                category_nodes.append(node)
            elif any(h in type_name for h in ITEM_CATEGORY_HINTS + MENU_COLLECTION_HINTS):
                category_nodes.append(node)
            elif _looks_like_category_node(node) and node not in category_nodes:
                category_nodes.append(node)

        # Some payloads nest menu under groupedCard without @type on every node.
        for grouped in _find_keys(payload, "cardGroupMap"):
            regular = (grouped.get("REGULAR") or grouped.get("regular") or {}) if isinstance(grouped, dict) else {}
            cards = regular.get("cards") if isinstance(regular, dict) else None
            if isinstance(cards, list):
                for card in cards:
                    inner = _unwrap_card(card)
                    type_name = _type_name(inner)
                    if any(h in type_name for h in NESTED_CATEGORY_HINTS + ITEM_CATEGORY_HINTS + MENU_COLLECTION_HINTS):
                        if inner not in category_nodes:
                            category_nodes.append(inner)
                    elif _looks_like_category_node(inner) and inner not in category_nodes:
                        category_nodes.append(inner)
                    if any(h in type_name for h in LICENSE_HINTS):
                        license_info = _merge_info(license_info, inner)
                    if any(h in type_name for h in ADDRESS_HINTS):
                        address_info = _merge_info(address_info, inner)

        schema_restaurant, schema_categories = _parse_schema_org(payload)
        if schema_restaurant and not restaurant_info.get("name"):
            restaurant_info = _merge_info(restaurant_info, schema_restaurant)
        if schema_categories and not extra_schema_categories:
            extra_schema_categories = schema_categories

    restaurant = _parse_restaurant(restaurant_info, license_info, address_info, offer_nodes)
    categories = _parse_categories(category_nodes)
    if not categories and extra_schema_categories:
        categories = extra_schema_categories
        source_type_hint = "json_ld"
    else:
        source_type_hint = None

    source_type = _source_type(raw) or source_type_hint
    if not categories and raw.dom_menu:
        categories = _categories_from_dom_menu(raw.dom_menu)
        source_type = source_type or "dom"
    if not categories and raw.html:
        dom_categories = _parse_dom_fallback(raw.html)
        if dom_categories:
            categories = dom_categories
            source_type = source_type or "dom"
    if not categories and raw.html:
        from scraper.swiggy.dom_discovery import discover_menu, discovery_to_dom_menu

        discovery = discover_menu(raw.html, source_url=raw.source_url)
        raw.dom_discovery = discovery.diagnostics
        if discovery.has_menu:
            raw.data_locations = list(dict.fromkeys([*raw.data_locations, "dom_discovery"]))
            categories = _categories_from_dom_menu(discovery_to_dom_menu(discovery))
            source_type = source_type or "dom_discovery"
            if not restaurant.name and discovery.restaurant_name:
                restaurant.name = discovery.restaurant_name

    has_data = bool(restaurant.name or any(category.items for category in categories))
    if has_data:
        status = "ok"
        error = None
    else:
        status = "failed"
        error = raw.reason or "Page was reachable but no restaurant/menu data was found."
        source_type = None

    catalogue = _result(raw, restaurant, categories, status=status, source_type=source_type, error=error)
    from scraper.swiggy.dineout import enrich_dineout, is_dineout_url

    if catalogue.extraction_status == "ok" or is_dineout_url(raw.source_url):
        catalogue = enrich_dineout(
            catalogue,
            payloads,
            html=raw.html,
            dom_images=raw.dom_images,
        )
    return catalogue


def _result(
    raw: RawSource,
    restaurant: Restaurant,
    categories: list[MenuCategory],
    status: str,
    source_type: str | None,
    error: str | None,
) -> Catalogue:
    items = [item for category in categories for item in category.items]
    image_count = (1 if restaurant.image_url else 0) + sum(1 for item in items if item.image_url)
    ok = status == "ok"
    extraction = ExtractionMeta(
        ok=ok,
        blocked=status == "blocked",
        extraction_status=status,
        source_type=source_type,
        http_status=raw.http_status,
        waf_action=raw.waf_action,
        reason=raw.reason,
        error=error,
        source_kind=source_type,
        data_locations=list(raw.data_locations),
    )
    return Catalogue(
        source="swiggy",
        source_url=raw.source_url,
        extraction_status=status,
        source_type=source_type,
        restaurant=restaurant if ok else Restaurant(),
        categories=categories if ok else [],
        item_count=len(items) if ok else 0,
        image_count=image_count if ok else 0,
        error=error,
        extraction=extraction,
    )


def _source_type(raw: RawSource) -> str | None:
    if raw.api_payloads:
        return "xhr_json"
    if raw.next_data:
        return "embedded_json"
    if raw.json_ld:
        return "json_ld"
    if raw.dom_menu:
        return "dom"
    return None


def _parse_schema_org(payload: Any) -> tuple[dict[str, Any], list[MenuCategory]]:
    restaurant: dict[str, Any] = {}
    categories: list[MenuCategory] = []
    for node in _walk(payload):
        if not isinstance(node, dict):
            continue
        type_name = str(node.get("@type") or "")
        if "Restaurant" in type_name and node.get("name"):
            cuisines = node.get("servesCuisine")
            restaurant = {
                "name": node.get("name"),
                "cuisines": cuisines if isinstance(cuisines, list) else ([cuisines] if isinstance(cuisines, str) else []),
                "avgRating": (node.get("aggregateRating") or {}).get("ratingValue")
                if isinstance(node.get("aggregateRating"), dict)
                else None,
                "address": node.get("address"),
                "imageId": node.get("image") if isinstance(node.get("image"), str) else None,
            }
            if isinstance(node.get("address"), dict):
                restaurant["address"] = node["address"].get("streetAddress") or node["address"].get("name")
        if "MenuSection" in type_name:
            items = []
            for item in node.get("hasMenuItem") or node.get("itemListElement") or []:
                parsed = _schema_item(item)
                if parsed:
                    items.append(parsed)
            title = node.get("name")
            if isinstance(title, str) and title.strip() and items:
                categories.append(MenuCategory(name=title.strip(), items=items))
    return restaurant, categories


def _schema_item(node: Any) -> MenuItem | None:
    if not isinstance(node, dict):
        return None
    if isinstance(node.get("item"), dict):
        node = node["item"]
    name = node.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    offers = node.get("offers") if isinstance(node.get("offers"), dict) else {}
    return MenuItem(
        name=name.strip(),
        description=node.get("description") if isinstance(node.get("description"), str) else None,
        price=_coerce_visible_price(offers.get("price") or node.get("price")),
        image_url=node.get("image") if isinstance(node.get("image"), str) else None,
    )


def _categories_from_dom_menu(dom_menu: list[dict[str, Any]]) -> list[MenuCategory]:
    categories: list[MenuCategory] = []
    for block in dom_menu:
        if not isinstance(block, dict):
            continue
        name = block.get("name")
        raw_items = block.get("items") if isinstance(block.get("items"), list) else []
        items = []
        for raw_item in raw_items:
            if not isinstance(raw_item, dict) or not raw_item.get("name"):
                continue
            labels = raw_item.get("labels") if isinstance(raw_item.get("labels"), list) else []
            extra = raw_item.get("additional_information") if isinstance(raw_item.get("additional_information"), dict) else {}
            items.append(
                MenuItem(
                    name=str(raw_item["name"]),
                    description=raw_item.get("description") or None,
                    price=_coerce_visible_price(raw_item.get("price")),
                    original_price=_coerce_visible_price(raw_item.get("original_price")),
                    image_url=raw_item.get("image_url") or None,
                    food_type=raw_item.get("food_type") or None,
                    rating=_to_float(raw_item.get("rating")) if raw_item.get("rating") is not None else None,
                    rating_count=raw_item.get("rating_count"),
                    labels=[str(label) for label in labels if label],
                    variants=raw_item.get("variants") if isinstance(raw_item.get("variants"), list) else [],
                    customizations=raw_item.get("customizations") if isinstance(raw_item.get("customizations"), list) else [],
                    additional_information=extra,
                    is_bestseller=bool(raw_item.get("is_bestseller") or extra.get("isBestseller")),
                    available=raw_item.get("available") if isinstance(raw_item.get("available"), bool) else None,
                    next_available=raw_item.get("next_available") if isinstance(raw_item.get("next_available"), str) else None,
                )
            )
        if items:
            title = name.strip() if isinstance(name, str) and name.strip() else ""
            categories.append(MenuCategory(name=title, items=items))
    return categories


def _parse_dom_fallback(html: str) -> list[MenuCategory]:
    # Conservative: only use explicit data attributes, never invented category names.
    sections = re.findall(
        r'data-menu-category="([^"]+)"[^>]*>([\s\S]*?)(?=data-menu-category="|$)',
        html,
        re.I,
    )
    categories: list[MenuCategory] = []
    for title, body in sections:
        items = _parse_dom_items(body)
        if items:
            categories.append(MenuCategory(name=_unescape(title), items=items))
    return categories


def _parse_dom_items(body: str) -> list[MenuItem]:
    items: list[MenuItem] = []
    for match in re.finditer(r"<[^>]*data-menu-item=\"([^\"]+)\"[^>]*>", body, re.I):
        tag = match.group(0)
        name = _unescape(match.group(1))
        if not name:
            continue
        desc = _attr(tag, "data-description")
        price = _coerce_visible_price(_attr(tag, "data-price"))
        food_type = _attr(tag, "data-food-type") or _attr(tag, "data-veg-classifier")
        label = _attr(tag, "data-item-label")
        image = _attr(tag, "data-image")
        items.append(
            MenuItem(
                name=name,
                description=desc,
                price=price,
                food_type=food_type,
                labels=[label] if label else [],
                image_url=image,
            )
        )
    return items


def _attr(tag: str, name: str) -> str | None:
    match = re.search(rf'{re.escape(name)}="([^"]*)"', tag, re.I)
    if not match:
        return None
    value = _unescape(match.group(1))
    return value or None


def _looks_like_category_node(node: dict[str, Any]) -> bool:
    title = node.get("title") or node.get("name")
    cards = node.get("itemCards") or node.get("carouselCards")
    return isinstance(title, str) and bool(title.strip()) and isinstance(cards, list) and bool(cards)


def _coerce_visible_price(value: Any) -> float | int | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        digits = re.sub(r"[^\d.]", "", value)
        if not digits:
            return None
        amount = float(digits) if "." in digits else int(digits)
        return int(amount) if isinstance(amount, float) and amount.is_integer() else amount
    return None


def _unescape(value: str) -> str:
    return re.sub(r"\s+", " ", value).replace("&amp;", "&").strip()


def _json_ld_objects(blocks: list[Any]) -> list[Any]:
    out = []
    for block in blocks:
        if isinstance(block, (dict, list)):
            out.append(block)
            continue
        if isinstance(block, str):
            try:
                out.append(json.loads(block))
            except json.JSONDecodeError:
                continue
    return out


def _walk(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from _walk(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk(item)


def _find_keys(obj: Any, key: str) -> list[Any]:
    found = []
    for node in _walk(obj):
        if isinstance(node, dict) and key in node:
            found.append(node[key])
    return found


def _type_name(node: Any) -> str:
    if not isinstance(node, dict):
        return ""
    return str(node.get("@type") or node.get("type") or "")


def _unwrap_card(card: Any) -> dict[str, Any]:
    if not isinstance(card, dict):
        return {}
    inner = card
    for _ in range(4):
        if isinstance(inner.get("card"), dict):
            inner = inner["card"]
        elif isinstance(inner.get("item"), dict):
            inner = inner["item"]
        else:
            break
    return inner if isinstance(inner, dict) else {}


def _is_restaurant_info(node: dict[str, Any], type_name: str) -> bool:
    if any(h in type_name for h in RESTAURANT_TYPE_HINTS):
        return True
    info = node.get("info")
    if isinstance(info, dict) and info.get("name") and info.get("cuisines") is not None:
        return True
    return False


def _merge_info(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in extra.items():
        if key in {"@type", "type", "card"}:
            continue
        if value in (None, "", [], {}):
            continue
        if key not in merged or merged[key] in (None, "", [], {}):
            merged[key] = value
    return merged


def _parse_restaurant(
    info: dict[str, Any],
    license_info: dict[str, Any],
    address_info: dict[str, Any],
    offer_nodes: list[Any],
) -> Restaurant:
    name = _first_str(info.get("name"), info.get("restaurantName"))
    rating = _to_float(info.get("avgRating") or info.get("avgRatingString"))
    rating_count = info.get("totalRatingsString") or info.get("totalRatings")
    price_for_two = info.get("costForTwoMessage")
    if price_for_two is None and info.get("costForTwo") is not None:
        price_for_two = _paise_to_amount(info.get("costForTwo"))

    cuisines = info.get("cuisines") if isinstance(info.get("cuisines"), list) else []
    cuisines = [c for c in cuisines if isinstance(c, str)]

    locality = _first_str(info.get("locality"), info.get("areaName"))
    area = _first_str(info.get("areaName"))
    outlet = None
    if locality and area and locality != area:
        outlet = f"{locality}, {area}"
    else:
        outlet = locality or area or _first_str(info.get("city"))

    address = _first_str(
        address_info.get("completeAddress"),
        address_info.get("address"),
        info.get("address"),
        info.get("slugs", {}).get("restaurant") if isinstance(info.get("slugs"), dict) else None,
    )
    if not address:
        parts = [info.get("locality"), info.get("areaName"), info.get("city")]
        parts = [p for p in parts if isinstance(p, str) and p]
        address = ", ".join(dict.fromkeys(parts)) or None

    fssai = _extract_fssai(license_info) or _extract_fssai(info)
    image_url = _image_url(info.get("cloudinaryImageId") or info.get("imageId"))
    offers = _extract_offers(info, offer_nodes)

    extra = {}
    for key in (
        "id",
        "city",
        "locality",
        "areaName",
        "isOpen",
        "veg",
        "availability",
        "sla",
        "aggregatedDiscountInfoV3",
        "aggregatedDiscountInfoV2",
        "labels",
        "badges",
        "badgesV2",
        "totalRatingsString",
        "costForTwo",
        "externalRatings",
        "uniqueId",
        "parentId",
    ):
        if info.get(key) not in (None, "", [], {}):
            extra[key] = info[key]
    if license_info:
        extra["license_raw"] = {k: v for k, v in license_info.items() if k not in {"@type", "type"}}
    if address_info:
        extra["address_raw"] = {k: v for k, v in address_info.items() if k not in {"@type", "type"}}

    return Restaurant(
        name=name,
        rating=rating,
        rating_count=rating_count,
        price_for_two=price_for_two,
        cuisines=cuisines,
        outlet=outlet,
        address=address,
        fssai_license=fssai,
        image_url=image_url,
        offers=offers,
        additional_information=extra,
        restaurant_id=str(extra["id"]) if extra.get("id") not in (None, "") else None,
    )


def _extract_fssai(node: dict[str, Any]) -> str | None:
    if not node:
        return None
    for key in ("licenseCode", "text", "fssaiLicense", "licenseNo", "license_number"):
        value = node.get(key)
        found = _find_fssai_value(value)
        if found:
            return found
    return _find_fssai_value(node)


def _find_fssai_value(value: Any) -> str | None:
    if isinstance(value, (int, float)) and len(str(int(value))) >= 12:
        return str(int(value))
    if isinstance(value, str):
        digits = re.sub(r"\D", "", value)
        if len(digits) >= 12:
            return digits
        return None
    if isinstance(value, list):
        for item in value:
            found = _find_fssai_value(item)
            if found:
                return found
    if isinstance(value, dict):
        for item in value.values():
            found = _find_fssai_value(item)
            if found:
                return found
    return None


def _extract_offers(info: dict[str, Any], offer_nodes: list[Any]) -> list[Any]:
    offers: list[Any] = []
    for key in (
        "aggregatedDiscountInfoV3",
        "aggregatedDiscountInfoV2",
        "aggregatedDiscountInfo",
        "offerDetails",
        "restaurantOfferPresentationInfo",
    ):
        value = info.get(key)
        if value not in (None, "", [], {}):
            offers.append(value)
    for node in offer_nodes:
        header = node.get("header") or node.get("title")
        if header:
            offers.append(node)
        info_with_style = node.get("infoWithStyle") or node.get("offers")
        if info_with_style:
            offers.append(info_with_style)
    # de-dupe by JSON
    unique = []
    seen = set()
    for offer in offers:
        marker = json.dumps(offer, sort_keys=True, default=str)
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(offer)
    return unique


def _parse_categories(nodes: list[dict[str, Any]]) -> list[MenuCategory]:
    categories: list[MenuCategory] = []
    for node in nodes:
        type_name = _type_name(node)
        title = _first_str(node.get("title"), node.get("name"), node.get("category"))
        nested = node.get("categories") if isinstance(node.get("categories"), list) else []
        if nested and any(h in type_name for h in NESTED_CATEGORY_HINTS):
            for child in nested:
                if not isinstance(child, dict):
                    continue
                child_title = _first_str(child.get("title"), child.get("name"), title)
                items = _parse_item_cards(child.get("itemCards") or child.get("carouselCards") or [])
                if child_title:
                    categories.append(MenuCategory(name=child_title, items=items))
            continue
        item_cards = node.get("itemCards") or node.get("carouselCards") or []
        if title and item_cards:
            categories.append(MenuCategory(name=title, items=_parse_item_cards(item_cards)))
        elif title and not item_cards and "ItemCategory" in type_name:
            categories.append(MenuCategory(name=title, items=[]))

    # Preserve source order; drop exact duplicate category blocks.
    unique: list[MenuCategory] = []
    seen_blocks = set()
    for category in categories:
        marker = (category.name, tuple(_item_key(i) for i in category.items))
        if marker in seen_blocks:
            continue
        seen_blocks.add(marker)
        unique.append(category)
    return unique


def _parse_item_cards(item_cards: Any) -> list[MenuItem]:
    items: list[MenuItem] = []
    seen = set()
    if not isinstance(item_cards, list):
        return items
    for card in item_cards:
        inner = _unwrap_card(card)
        info = inner.get("info") if isinstance(inner.get("info"), dict) else inner
        if not isinstance(info, dict):
            continue
        name = _first_str(info.get("name"), info.get("itemName"))
        if not name:
            continue
        item = _parse_item(info)
        key = _item_key(item)
        if key in seen:
            continue
        seen.add(key)
        items.append(item)
    return items


def _parse_item(info: dict[str, Any]) -> MenuItem:
    price = _paise_to_amount(info.get("price") if info.get("price") not in (None, 0) else info.get("defaultPrice"))
    original = None
    if info.get("price") not in (None, 0) and info.get("defaultPrice") not in (None, 0):
        if info.get("defaultPrice") != info.get("price"):
            original = _paise_to_amount(info.get("defaultPrice"))
    if info.get("finalPrice") not in (None, 0) and price is not None:
        maybe_original = price
        maybe_final = _paise_to_amount(info.get("finalPrice"))
        if maybe_final is not None and maybe_original != maybe_final:
            original = maybe_original
            price = maybe_final

    food_type = _food_type(info)
    rating_block = (info.get("ratings") or {}).get("aggregatedRating") if isinstance(info.get("ratings"), dict) else {}
    if not isinstance(rating_block, dict):
        rating_block = {}
    rating = _to_float(rating_block.get("rating") or info.get("rating"))
    rating_count = rating_block.get("ratingCountV2") or rating_block.get("ratingCount") or info.get("ratingCount")

    labels = _item_labels(info)
    variants = _item_variants(info)
    customizations = _item_customizations(info)
    image_url = _image_url(info.get("imageId") or info.get("cloudinaryImageId"))
    nutrition = info.get("nutrients") or info.get("nutrientInfo") or info.get("nutritionInfo") or info.get("nutritionalInfo")

    extra = {}
    for key in (
        "id",
        "category",
        "inStock",
        "isVeg",
        "itemAttribute",
        "ribbon",
        "offerTags",
        "addons",
        "variantsV2",
        "variants",
        "maxAddons",
        "showMC",
        "defaultPrice",
        "finalPrice",
        "price",
        "isBestseller",
        "isRecommended",
        "isHealthy",
        "nudgeText",
        "nextAvailableAt",
        "nextAvailableAtMessage",
        "nextAvailableMessage",
    ):
        if info.get(key) not in (None, "", [], {}):
            extra[key] = info[key]
    serving = None
    attr = info.get("itemAttribute")
    if isinstance(attr, dict):
        serving = attr.get("portionSize") or attr.get("servingInfo")
        if serving:
            extra["serving"] = serving
    available, next_available = _item_availability(info)
    is_bestseller = _is_bestseller(info, labels)

    return MenuItem(
        name=_first_str(info.get("name")) or "",
        description=_first_str(info.get("description")) or None,
        price=price,
        original_price=original,
        food_type=food_type,
        rating=rating,
        rating_count=rating_count,
        labels=labels,
        variants=variants,
        customizations=customizations,
        image_url=image_url,
        nutritional_information=nutrition if nutrition not in (None, "", [], {}) else None,
        additional_information=extra,
        is_bestseller=is_bestseller,
        available=available,
        next_available=next_available,
    )


def _item_availability(info: dict[str, Any]) -> tuple[bool | None, str | None]:
    in_stock = info.get("inStock")
    available: bool | None = None
    if in_stock in (0, False, "0"):
        available = False
    elif in_stock in (1, True, "1"):
        available = True
    nudge = info.get("nudgeText")
    next_available = _first_str(
        info.get("nextAvailableAtMessage"),
        info.get("nextAvailableMessage"),
        nudge if isinstance(nudge, str) and "available" in nudge.lower() else None,
    )
    nested = info.get("nextAvailableAt")
    if isinstance(nested, str) and nested.strip() and not nested.strip().isdigit():
        next_available = next_available or nested.strip()
    elif isinstance(nested, dict):
        next_available = next_available or _first_str(nested.get("message"), nested.get("time"), nested.get("text"))
    return available, next_available


def _is_bestseller(info: dict[str, Any], labels: list[str]) -> bool:
    if info.get("isBestseller") in (1, True, "1", "true", "True"):
        return True
    return any("bestseller" in str(label).lower().replace(" ", "") for label in labels)


def _item_labels(info: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    ribbon = info.get("ribbon")
    if isinstance(ribbon, dict) and ribbon.get("text"):
        labels.append(str(ribbon["text"]))
    elif isinstance(ribbon, str) and ribbon:
        labels.append(ribbon)
    for tag in info.get("offerTags") or []:
        if isinstance(tag, dict):
            text = tag.get("title") or tag.get("text") or tag.get("header")
            if text:
                labels.append(str(text))
        elif isinstance(tag, str):
            labels.append(tag)
    if info.get("isBestseller"):
        labels.append("Bestseller")
    if info.get("isRecommended"):
        labels.append("Recommended")
    nudge = info.get("nudgeText") or info.get("itemNudgeType")
    if isinstance(nudge, str) and nudge:
        labels.append(nudge)
    # unique, preserve order
    return list(dict.fromkeys(labels))


def _item_variants(info: dict[str, Any]) -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = []
    v2 = info.get("variantsV2")
    if isinstance(v2, dict):
        groups = v2.get("variantGroups") or []
        if isinstance(groups, list):
            for group in groups:
                if not isinstance(group, dict):
                    continue
                variants.append(
                    {
                        "group_name": group.get("name") or group.get("groupName"),
                        "variations": group.get("variations") or group.get("options") or [],
                    }
                )
        pricing = v2.get("pricingModels")
        if pricing:
            variants.append({"pricing_models": pricing})
    legacy = info.get("variants")
    if isinstance(legacy, dict) and legacy:
        variants.append({"variants": legacy})
    elif isinstance(legacy, list) and legacy:
        variants.append({"variants": legacy})
    return variants


def _item_customizations(info: dict[str, Any]) -> list[dict[str, Any]]:
    addons = info.get("addons")
    if not isinstance(addons, list):
        return []
    customizations = []
    for group in addons:
        if not isinstance(group, dict):
            continue
        customizations.append(
            {
                "group_id": group.get("groupId"),
                "group_name": group.get("groupName") or group.get("name"),
                "choices": group.get("choices") or group.get("addonItems") or [],
                "max_addons": group.get("maxAddons"),
                "max_free_addons": group.get("maxFreeAddons"),
            }
        )
    return customizations


def _food_type(info: dict[str, Any]) -> str | None:
    attr = info.get("itemAttribute")
    if isinstance(attr, dict):
        classifier = attr.get("vegClassifier") or attr.get("portionSizeClassifier")
        if isinstance(classifier, str) and classifier:
            return classifier
    if info.get("isVeg") in (1, True, "1", "VEG"):
        return "VEG"
    if info.get("isVeg") in (0, False, "0"):
        return "NONVEG"
    return None


def _image_url(image_id: Any) -> str | None:
    if not image_id or not isinstance(image_id, str):
        return None
    if image_id.startswith("http://") or image_id.startswith("https://"):
        return image_id
    return IMAGE_CDN + image_id.lstrip("/")


def _paise_to_amount(value: Any) -> float | int | None:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        digits = re.sub(r"[^\d.]", "", value)
        if not digits:
            return None
        try:
            value = float(digits) if "." in digits else int(digits)
        except ValueError:
            return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    amount = value / 100.0
    if amount.is_integer():
        return int(amount)
    return round(amount, 2)


def _to_float(value: Any) -> float | None:
    if value in (None, "", "--"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_str(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _item_key(item: MenuItem) -> tuple[Any, ...]:
    item_id = item.additional_information.get("id")
    if item_id:
        return ("id", item_id)
    return (item.name, item.description, item.price, item.image_url)


def restaurant_slug_from_url(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    slug = path.split("/")[-1] if path else "restaurant"
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", slug).strip("-")
    return slug or "restaurant"

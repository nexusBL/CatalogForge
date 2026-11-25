"""Deterministic catalogue normalization. Mutates parser Catalogue in place."""

from __future__ import annotations

import re
from typing import Any

from scraper.html_common import split_cuisines
from scraper.platform_dom import unwrap_image_url
from scraper.swiggy.models import Catalogue, DineoutVenue, MenuCategory, MenuItem, Restaurant

_JUNK_IMAGE_RE = re.compile(
    r"veg-icon|non-veg-icon|egg-icon|star-filled|star-empty|star-|web_assets|web/assets|placeholder|logo|favicon|=s120\b|=w120\b",
    re.I,
)
_WHITESPACE_RE = re.compile(r"\s+")


def collapse_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = _WHITESPACE_RE.sub(" ", str(value)).strip()
    return cleaned or None


def coerce_price(value: Any) -> float | int | None:
    if isinstance(value, bool) or value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        if value != value or value in {float("inf"), float("-inf")}:  # NaN/inf
            return None
        if value < 0:
            return None
        if isinstance(value, float) and value.is_integer():
            return int(value)
        return value
    if isinstance(value, dict):
        return coerce_price(value.get("amount") or value.get("display_text") or value.get("price"))
    if isinstance(value, str):
        digits = re.sub(r"[^\d.]", "", value.replace(",", ""))
        if not digits or digits == ".":
            return None
        try:
            amount = float(digits) if "." in digits else int(digits)
        except ValueError:
            return None
        if amount < 0:
            return None
        if isinstance(amount, float) and amount.is_integer():
            return int(amount)
        return amount
    return None


def normalize_price_pair(
    selling: Any, original: Any
) -> tuple[float | int | None, float | int | None, bool]:
    """Return (selling, original, invalid). Never divides by 100."""
    had_selling = selling not in (None, "")
    had_original = original not in (None, "")
    price = coerce_price(selling)
    mrp = coerce_price(original)
    invalid = (had_selling and price is None) or (had_original and mrp is None)
    if price is not None and mrp is not None:
        if mrp < price:
            price, mrp = mrp, price
        if mrp == price:
            mrp = None
    return price, mrp, invalid


def normalize_labels(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    labels: list[str] = []
    for item in values:
        text = collapse_text(str(item) if item is not None else "")
        if text:
            labels.append(text)
    return list(dict.fromkeys(labels))


def normalize_image_url(url: str | None) -> tuple[str | None, str | None, bool]:
    """Return (display_url, source_url, dropped_as_junk_or_invalid)."""
    if url is None or url == "":
        return None, None, False
    if not isinstance(url, str):
        return None, None, True
    unwrapped = unwrap_image_url(url.strip()) or url.strip()
    if unwrapped.startswith("/catalogue-assets/"):
        return unwrapped, None, False
    if not unwrapped.startswith(("http://", "https://")):
        return None, None, True
    lowered = unwrapped.lower()
    if _JUNK_IMAGE_RE.search(unwrapped) or re.search(r"=w200-rw", lowered):
        return None, unwrapped, True
    return unwrapped, unwrapped, False


def _normalize_item(item: MenuItem) -> None:
    item.name = collapse_text(item.name) or ""
    item.description = collapse_text(item.description)
    price, original, _invalid = normalize_price_pair(item.price, item.original_price)
    item.price = price
    item.original_price = original
    item.food_type = collapse_text(item.food_type)
    item.labels = normalize_labels(item.labels)
    if any("bestseller" in label.lower().replace(" ", "") for label in item.labels):
        item.is_bestseller = True
    display, source, _dropped = normalize_image_url(item.image_url)
    kept_source = collapse_text(item.source_image_url)
    if kept_source:
        _src_display, src_orig, src_dropped = normalize_image_url(kept_source)
        item.source_image_url = src_orig or (kept_source if kept_source.startswith("http") else None)
        if src_dropped and not src_orig:
            item.source_image_url = None
    else:
        item.source_image_url = source
    item.image_url = display
    if isinstance(item.additional_information, dict):
        extra = dict(item.additional_information)
        extra.pop("parentId", None)
        item.additional_information = extra
    else:
        item.additional_information = {}


def _normalize_category(category: MenuCategory) -> None:
    name = collapse_text(category.name)
    category.name = name or ("Menu" if category.items else "")
    for item in category.items:
        _normalize_item(item)


def _normalize_restaurant(restaurant: Restaurant) -> None:
    restaurant.name = collapse_text(restaurant.name)
    restaurant.outlet = collapse_text(restaurant.outlet)
    restaurant.address = collapse_text(restaurant.address)
    restaurant.cuisines = split_cuisines(restaurant.cuisines)
    display, _source, _dropped = normalize_image_url(restaurant.image_url)
    restaurant.image_url = display


def _normalize_dineout(dineout: DineoutVenue | None) -> None:
    if dineout is None:
        return
    dineout.venue = collapse_text(dineout.venue)
    hero, _, _ = normalize_image_url(dineout.hero_image)
    dineout.hero_image = hero
    photos: list[str] = []
    for url in dineout.photos or []:
        display, source, _dropped = normalize_image_url(url if isinstance(url, str) else None)
        kept = display or source
        if kept:
            photos.append(kept)
    dineout.photos = list(dict.fromkeys(photos))
    gallery: list[dict[str, Any]] = []
    for entry in dineout.gallery_images or []:
        if not isinstance(entry, dict):
            continue
        copied = dict(entry)
        display, source, _dropped = normalize_image_url(copied.get("url") if isinstance(copied.get("url"), str) else None)
        if display:
            if not copied.get("source_url") and source:
                copied["source_url"] = source
            copied["url"] = display
        elif source:
            copied["source_url"] = copied.get("source_url") or source
            copied["url"] = source
        gallery.append(copied)
    dineout.gallery_images = gallery


def normalize_catalogue(catalogue: Catalogue) -> Catalogue:
    _normalize_restaurant(catalogue.restaurant)
    _normalize_dineout(catalogue.dineout)
    for category in catalogue.categories:
        _normalize_category(category)
    catalogue.item_count = sum(len(category.items) for category in catalogue.categories)
    return catalogue

"""Apply allowlisted Phase 6 proposal lines onto a stored catalogue payload."""

from __future__ import annotations

import copy
import re
from typing import Any

from backend.catalogue_normalize import coerce_price
from backend.improvement.contract import ImprovementLine, ImprovementProposal
from backend.schemas import CatalogCreateResponse

_ITEM = re.compile(
    r"^menus\[(\d+)\]\.categories\[(\d+)\]\.items\[(\d+)\](?:\.(description|labels|image_url|price|name|video_url))?$"
)
_CATEGORY = re.compile(r"^menus\[(\d+)\]\.categories\[(\d+)\](?:\.name)?$")
_VENUE_IMAGE = re.compile(r"^(?:venue|restaurant)\.image_url$")


class ApplyRejected(ValueError):
    pass


def apply_proposal_lines(result: CatalogCreateResponse, proposal: ImprovementProposal) -> tuple[CatalogCreateResponse, list[str], list[str]]:
    payload = copy.deepcopy(result.model_dump(mode="json"))
    applied: list[str] = []
    skipped_media: list[str] = []
    for line in proposal.lines:
        if line.status != "READY":
            continue
        if line.kind == "media_handoff":
            skipped_media.append(line.path)
            continue
        _apply_line(payload, line)
        applied.append(line.path)
    if not applied and skipped_media:
        raise ApplyRejected("Image and video improvements must be applied from Generated Media after a candidate is ready.")
    if not applied:
        raise ApplyRejected("This proposal has no ready catalogue changes to apply.")
    updated = CatalogCreateResponse.model_validate(payload)
    count = 0
    for category in updated.categories or []:
        if isinstance(category, dict) and isinstance(category.get("items"), list):
            count += len(category["items"])
    return updated.model_copy(update={"item_count": count}), applied, skipped_media


def set_media_field(result: CatalogCreateResponse, path: str, url: str, *, video: bool = False) -> CatalogCreateResponse:
    payload = copy.deepcopy(result.model_dump(mode="json"))
    field = "video_url" if video else "image_url"
    item_match = _ITEM.match(path)
    if item_match:
        _set_item(payload, int(item_match.group(2)), int(item_match.group(3)), field, url)
        return CatalogCreateResponse.model_validate(payload)
    if _VENUE_IMAGE.match(path):
        restaurant = payload.get("restaurant") if isinstance(payload.get("restaurant"), dict) else {}
        restaurant = {**restaurant, "image_url": url}
        payload["restaurant"] = restaurant
        return CatalogCreateResponse.model_validate(payload)
    raise ApplyRejected("That media path cannot be applied to the live catalogue.")


def _apply_line(payload: dict[str, Any], line: ImprovementLine) -> None:
    if line.kind == "category_name":
        match = _CATEGORY.match(line.path)
        if match is None or not (line.proposed_value or "").strip():
            raise ApplyRejected("A valid category name is required.")
        _set_category_name(payload, int(match.group(2)), line.proposed_value.strip())
        return
    match = _ITEM.match(line.path)
    if match is None:
        raise ApplyRejected(f"Unsupported improvement path: {line.path}")
    category_index = int(match.group(2))
    item_index = int(match.group(3))
    if line.kind == "description":
        if not (line.proposed_value or "").strip():
            raise ApplyRejected("A valid description is required.")
        _set_item(payload, category_index, item_index, "description", line.proposed_value.strip())
        return
    if line.kind == "labels":
        labels = list(line.proposed_labels or [])
        if not labels and line.proposed_value:
            labels = [part.strip() for part in line.proposed_value.split(",") if part.strip()]
        if not labels:
            raise ApplyRejected("At least one tag is required.")
        _set_item(payload, category_index, item_index, "labels", labels)
        return
    if line.kind == "item_price":
        price = coerce_price(line.proposed_value)
        if price is None:
            raise ApplyRejected("A trusted price is required.")
        _set_item(payload, category_index, item_index, "price", price)
        return
    raise ApplyRejected(f"Unsupported improvement kind: {line.kind}")


def _categories(payload: dict[str, Any]) -> list[Any]:
    categories = payload.get("categories")
    if not isinstance(categories, list):
        raise ApplyRejected("Catalogue categories were not found.")
    return categories


def _set_category_name(payload: dict[str, Any], category_index: int, name: str) -> None:
    categories = _categories(payload)
    if category_index < 0 or category_index >= len(categories) or not isinstance(categories[category_index], dict):
        raise ApplyRejected("Category was not found.")
    categories[category_index] = {**categories[category_index], "name": name}


def _set_item(payload: dict[str, Any], category_index: int, item_index: int, field: str, value: Any) -> None:
    categories = _categories(payload)
    if category_index < 0 or category_index >= len(categories) or not isinstance(categories[category_index], dict):
        raise ApplyRejected("Category was not found.")
    items = list(categories[category_index].get("items") or [])
    if item_index < 0 or item_index >= len(items) or not isinstance(items[item_index], dict):
        raise ApplyRejected("Item was not found.")
    items[item_index] = {**items[item_index], field: value}
    categories[category_index] = {**categories[category_index], "items": items, "item_count": len(items)}


def value_at_path(result: CatalogCreateResponse, path: str) -> Any:
    payload = result.model_dump(mode="json")
    venue = _VENUE_IMAGE.match(path)
    if venue:
        restaurant = payload.get("restaurant") if isinstance(payload.get("restaurant"), dict) else {}
        return restaurant.get("image_url")
    category_match = _CATEGORY.match(path)
    if category_match:
        categories = _categories(payload)
        category_index = int(category_match.group(2))
        if category_index < 0 or category_index >= len(categories) or not isinstance(categories[category_index], dict):
            return None
        return categories[category_index].get("name")
    item_match = _ITEM.match(path)
    if item_match is None:
        return None
    categories = _categories(payload)
    category_index = int(item_match.group(2))
    item_index = int(item_match.group(3))
    field = item_match.group(4) or "name"
    if category_index < 0 or category_index >= len(categories) or not isinstance(categories[category_index], dict):
        return None
    items = list(categories[category_index].get("items") or [])
    if item_index < 0 or item_index >= len(items) or not isinstance(items[item_index], dict):
        return None
    return items[item_index].get(field)


def item_name_at_path(result: CatalogCreateResponse, path: str) -> str | None:
    payload = result.model_dump(mode="json")
    item_match = _ITEM.match(path)
    if item_match is None:
        return None
    categories = payload.get("categories") if isinstance(payload.get("categories"), list) else []
    category_index = int(item_match.group(2))
    item_index = int(item_match.group(3))
    if category_index < 0 or category_index >= len(categories) or not isinstance(categories[category_index], dict):
        return None
    items = list(categories[category_index].get("items") or [])
    if item_index < 0 or item_index >= len(items) or not isinstance(items[item_index], dict):
        return None
    name = items[item_index].get("name")
    return str(name) if name is not None else None


def set_path_value(result: CatalogCreateResponse, path: str, value: Any) -> CatalogCreateResponse:
    payload = copy.deepcopy(result.model_dump(mode="json"))
    venue = _VENUE_IMAGE.match(path)
    if venue:
        restaurant = payload.get("restaurant") if isinstance(payload.get("restaurant"), dict) else {}
        payload["restaurant"] = {**restaurant, "image_url": value}
        return CatalogCreateResponse.model_validate(payload)
    category_match = _CATEGORY.match(path)
    if category_match:
        _set_category_name(payload, int(category_match.group(2)), str(value or ""))
        return CatalogCreateResponse.model_validate(payload)
    item_match = _ITEM.match(path)
    if item_match is None:
        raise ApplyRejected(f"Unsupported catalogue path: {path}")
    field = item_match.group(4) or "name"
    _set_item(payload, int(item_match.group(2)), int(item_match.group(3)), field, value)
    return CatalogCreateResponse.model_validate(payload)

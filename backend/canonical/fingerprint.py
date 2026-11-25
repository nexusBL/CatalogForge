from __future__ import annotations

import json
from typing import Any

from backend.canonical.identity import source_item_id_from_item
from backend.schemas import CatalogCreateResponse


def _strip_item(item: dict[str, Any]) -> dict[str, Any]:
    kept = {key: value for key, value in item.items() if key not in {"item_id", "id"}}
    source_id = source_item_id_from_item(item)
    if source_id:
        kept["source_item_id"] = source_id
    return kept


def _strip_categories(categories: list[Any] | None) -> list[dict[str, Any]]:
    stripped: list[dict[str, Any]] = []
    for category in categories or []:
        if not isinstance(category, dict):
            continue
        items = [_strip_item(item) for item in (category.get("items") or []) if isinstance(item, dict)]
        stripped.append({"name": category.get("name"), "items": items, "item_count": category.get("item_count")})
    return stripped


def canonical_state_payload(result: CatalogCreateResponse) -> dict[str, Any]:
    """Comparable catalogue content. Timestamps, ids, quality, and raw capture ids are excluded."""
    return {
        "extraction_status": result.extraction_status,
        "platform": result.platform,
        "catalogue_type": result.catalogue_type,
        "restaurant_name": result.restaurant_name,
        "fssai_number": result.fssai_number,
        "restaurant": result.restaurant,
        "dineout": result.dineout,
        "categories": _strip_categories(result.categories),
        "item_count": result.item_count or 0,
        "image_count": result.image_count or 0,
        "error": result.error,
    }


def canonical_state_equal(left: CatalogCreateResponse, right: CatalogCreateResponse) -> bool:
    return json.dumps(canonical_state_payload(left), sort_keys=True, default=str) == json.dumps(
        canonical_state_payload(right), sort_keys=True, default=str
    )

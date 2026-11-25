from __future__ import annotations

from backend.canonical.identity import SCHEMA_VERSION
from backend.canonical.models import CanonicalDocument
from backend.schemas import CatalogCreateResponse


def apply_canonical_to_response(result: CatalogCreateResponse, document: CanonicalDocument) -> CatalogCreateResponse:
    merged = result.model_copy(
        update={
            "schema_version": document.schema_version or SCHEMA_VERSION,
            "venue_id": document.venue_id or result.venue_id,
            "canonical": document.model_dump(mode="json"),
        }
    )
    restaurant = merged.restaurant if isinstance(merged.restaurant, dict) else {}
    if document.venue.source_entity_id and not restaurant.get("restaurant_id"):
        restaurant = {**restaurant, "restaurant_id": document.venue.source_entity_id}
        merged = merged.model_copy(update={"restaurant": restaurant or None})
    categories = []
    for category in merged.categories or []:
        if not isinstance(category, dict):
            continue
        items = []
        for item in category.get("items") or []:
            if not isinstance(item, dict):
                continue
            copied = dict(item)
            if copied.get("item_id") and not copied.get("id"):
                copied["id"] = copied["item_id"]
            items.append(copied)
        categories.append({**category, "items": items})
    if categories:
        merged = merged.model_copy(update={"categories": categories})
    return merged

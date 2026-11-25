"""Load a CanonicalDocument from a stored catalogue response."""

from __future__ import annotations

import hashlib
import json

from backend.canonical.adapter import to_canonical_from_response
from backend.canonical.fingerprint import canonical_state_payload
from backend.canonical.models import CanonicalDocument
from backend.schemas import CatalogCreateResponse


def canonical_document_from_result(result: CatalogCreateResponse) -> CanonicalDocument:
    if result.canonical:
        return CanonicalDocument.model_validate(result.canonical)
    return to_canonical_from_response(result)


def graded_state_hash(result: CatalogCreateResponse) -> str:
    payload = canonical_state_payload(result)
    encoded = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def iter_menu_items(document: CanonicalDocument):
    for menu_index, menu in enumerate(document.menus):
        for category_index, category in enumerate(menu.categories):
            for item_index, item in enumerate(category.items):
                path = f"menus[{menu_index}].categories[{category_index}].items[{item_index}]"
                yield path, category, item

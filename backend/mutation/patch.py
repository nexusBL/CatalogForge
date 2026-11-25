"""Field-scoped catalogue patches. Never apply model JSON as a document replace."""

from __future__ import annotations

import copy
from typing import Any

from backend.catalogue_normalize import coerce_price, normalize_labels
from backend.improvement.contract import MAX_DESCRIPTION_CHARS, MAX_LABELS, GeneratorCandidate, TrustedItemContext
from backend.improvement.validate import CandidateRejected, validate_candidate, validate_labels
from backend.mutation.quality import description_needs_owner_facts, polish_description, suggest_labels
from backend.mutation.resolve import ResolvedItem
from backend.schemas import CatalogCreateResponse


class PatchRejected(ValueError):
    pass


def display_value(operation: str, item: dict[str, Any] | None, *, extra: str | None = None) -> str:
    if item is None:
        return extra or ""
    if operation == "change_price":
        return _price_text(item.get("price"))
    if operation == "rename_item":
        return str(item.get("name") or "")
    if operation == "update_description":
        return str(item.get("description") or "").strip() or "(empty)"
    if operation == "update_labels":
        labels = item.get("labels") if isinstance(item.get("labels"), list) else []
        return ", ".join(str(label) for label in labels) or "(none)"
    if operation == "move_item":
        return extra or ""
    if operation == "remove_item":
        return str(item.get("name") or "")
    return extra or str(item.get("name") or "")


def build_patch(
    result: CatalogCreateResponse,
    draft: MutationDraft,
    *,
    item: ResolvedItem | None,
    category_index: int | None,
    target_category_index: int | None,
) -> dict[str, Any]:
    if draft.operation == "change_price":
        if item is None:
            raise PatchRejected("Item is required.")
        price = coerce_price(draft.price)
        if price is None:
            raise PatchRejected("A valid price is required.")
        return {"op": "change_price", "item_id": item.item_id, "price": price}
    if draft.operation == "rename_item":
        if item is None or not draft.new_item_name:
            raise PatchRejected("Current and new item names are required.")
        return {"op": "rename_item", "item_id": item.item_id, "name": draft.new_item_name.strip()}
    if draft.operation == "update_description":
        if item is None:
            raise PatchRejected("Item is required.")
        text = (draft.description or "").strip()
        if not text:
            text = polish_description(
                name=item.name,
                category_name=item.category_name,
                description=str(item.item.get("description") or ""),
                labels=item.item.get("labels") if isinstance(item.item.get("labels"), list) else [],
            )
            if description_needs_owner_facts(str(item.item.get("description") or ""), text):
                raise PatchRejected(
                    "There is not enough verified information to improve this description without inventing details. Provide the exact new text in quotes."
                )
        return {"op": "update_description", "item_id": item.item_id, "description": _checked_description(result, item, text)}
    if draft.operation == "update_labels":
        if item is None:
            raise PatchRejected("Item is required.")
        labels = normalize_labels(draft.labels or [])
        if not labels:
            labels = suggest_labels(
                name=item.name,
                category_name=item.category_name,
                description=str(item.item.get("description") or ""),
                labels=item.item.get("labels") if isinstance(item.item.get("labels"), list) else [],
            )
        existing = item.item.get("labels") if isinstance(item.item.get("labels"), list) else []
        if not labels:
            raise PatchRejected("At least one tag is required.")
        if normalize_labels(existing) == labels:
            raise PatchRejected("Those tags already match the verified catalogue facts. Tell me the exact tags to set.")
        labels = _checked_labels(result, item, labels)
        return {"op": "update_labels", "item_id": item.item_id, "labels": labels}
    if draft.operation == "remove_item":
        if item is None:
            raise PatchRejected("Item is required.")
        return {"op": "remove_item", "item_id": item.item_id}
    if draft.operation == "move_item":
        if item is None or target_category_index is None:
            raise PatchRejected("Item and destination category are required.")
        return {
            "op": "move_item",
            "item_id": item.item_id,
            "from_index": item.category_index,
            "to_index": target_category_index,
        }
    if draft.operation == "add_item":
        if category_index is None or not draft.item_name:
            raise PatchRejected("Item name and category are required.")
        price = coerce_price(draft.price)
        if price is None:
            raise PatchRejected("A valid price is required.")
        return {
            "op": "add_item",
            "category_index": category_index,
            "name": draft.item_name.strip(),
            "price": price,
            "description": (draft.description or "").strip() or None,
        }
    if draft.operation in {"improve_image", "generate_video"}:
        if item is None:
            raise PatchRejected("Item is required.")
        return {"op": draft.operation, "item_id": item.item_id, "path": item.path, "writes_payload": False}
    raise PatchRejected("Unsupported operation.")


def apply_patch(result: CatalogCreateResponse, patch: dict[str, Any]) -> CatalogCreateResponse:
    op = patch.get("op")
    if op in {"improve_image", "generate_video"}:
        return result
    categories = copy.deepcopy(list(result.categories or []))
    if op == "add_item":
        index = int(patch["category_index"])
        if index < 0 or index >= len(categories) or not isinstance(categories[index], dict):
            raise PatchRejected("Category was not found.")
        items = list(categories[index].get("items") or [])
        items.append({"name": patch["name"], "price": patch["price"], "description": patch.get("description")})
        categories[index] = {**categories[index], "items": items, "item_count": len(items)}
        return _with_categories(result, categories)
    location = _find(categories, str(patch.get("item_id") or ""))
    if location is None:
        raise PatchRejected("Item was not found.")
    category_index, item_index, item = location
    if op == "change_price":
        categories[category_index]["items"][item_index] = {**item, "price": patch["price"]}
    elif op == "rename_item":
        categories[category_index]["items"][item_index] = {**item, "name": patch["name"]}
    elif op == "update_description":
        categories[category_index]["items"][item_index] = {**item, "description": patch["description"]}
    elif op == "update_labels":
        categories[category_index]["items"][item_index] = {**item, "labels": list(patch["labels"])}
    elif op == "remove_item":
        items = list(categories[category_index].get("items") or [])
        items.pop(item_index)
        categories[category_index] = {**categories[category_index], "items": items, "item_count": len(items)}
    elif op == "move_item":
        to_index = int(patch["to_index"])
        if to_index < 0 or to_index >= len(categories) or not isinstance(categories[to_index], dict):
            raise PatchRejected("Destination category was not found.")
        items = list(categories[category_index].get("items") or [])
        moved = items.pop(item_index)
        categories[category_index] = {**categories[category_index], "items": items, "item_count": len(items)}
        dest = list(categories[to_index].get("items") or [])
        dest.append(moved)
        categories[to_index] = {**categories[to_index], "items": dest, "item_count": len(dest)}
    else:
        raise PatchRejected("Unsupported operation.")
    return _with_categories(result, categories)


def _with_categories(result: CatalogCreateResponse, categories: list[dict[str, Any]]) -> CatalogCreateResponse:
    count = 0
    for category in categories:
        items = category.get("items") if isinstance(category, dict) else None
        if isinstance(items, list):
            count += len(items)
    return result.model_copy(update={"categories": categories, "item_count": count})


def _find(categories: list[Any], item_id: str) -> tuple[int, int, dict[str, Any]] | None:
    if not item_id:
        return None
    for category_index, category in enumerate(categories):
        if not isinstance(category, dict):
            continue
        items = category.get("items") if isinstance(category.get("items"), list) else []
        for item_index, item in enumerate(items):
            if isinstance(item, dict) and str(item.get("item_id") or item.get("id") or "") == item_id:
                return category_index, item_index, item
    return None


def _price_text(value: Any) -> str:
    price = coerce_price(value)
    if price is None:
        return "(none)"
    if isinstance(price, float) and price.is_integer():
        price = int(price)
    return f"₹{price}"


def _existing_description(item: ResolvedItem) -> str:
    current = str(item.item.get("description") or "").strip()
    if current:
        return current
    raise PatchRejected("There is not enough verified information to rewrite this description.")


def _checked_description(result: CatalogCreateResponse, item: ResolvedItem, text: str) -> str:
    if len(text) > MAX_DESCRIPTION_CHARS:
        raise PatchRejected("That description is too long.")
    if text.strip() == str(item.item.get("description") or "").strip():
        return text.strip()
    context = _context(result, item, kind="description", current=str(item.item.get("description") or ""))
    try:
        return validate_candidate(context, GeneratorCandidate(proposed_value=text))
    except CandidateRejected as exc:
        raise PatchRejected("That description is not allowed from verified catalogue facts.") from exc


def _checked_labels(result: CatalogCreateResponse, item: ResolvedItem, labels: list[str]) -> list[str]:
    if len(labels) > MAX_LABELS:
        raise PatchRejected("Too many tags.")
    existing = item.item.get("labels") if isinstance(item.item.get("labels"), list) else []
    context = _context(
        result,
        item,
        kind="labels",
        current=", ".join(str(label) for label in existing),
        labels=[str(label) for label in existing],
    )
    try:
        return validate_labels(context, labels)
    except CandidateRejected as exc:
        raise PatchRejected("Those tags are not allowed from verified catalogue facts.") from exc


def _context(
    result: CatalogCreateResponse,
    item: ResolvedItem,
    *,
    kind: str,
    current: str,
    labels: list[str] | None = None,
) -> TrustedItemContext:
    return TrustedItemContext(
        path=item.path,
        kind=kind,  # type: ignore[arg-type]
        item_id=item.item_id,
        name=item.name,
        category_name=item.category_name,
        labels=labels or [],
        current_value=current,
        restaurant_name=result.restaurant_name,
        needs_ollama=False,
        original_price=str(item.item.get("original_price") or item.item.get("price") or "") or None,
        image_url=item.item.get("image_url") if isinstance(item.item.get("image_url"), str) else None,
    )

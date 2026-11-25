"""Deterministic restore of a recorded previous canonical value."""

from __future__ import annotations

import copy
import json
from typing import Any

from backend.history.contract import HistoryRejected
from backend.improvement.apply import ApplyRejected, set_path_value, value_at_path
from backend.mutation.patch import PatchRejected, apply_patch
from backend.schemas import CatalogCreateResponse


def canonical_value(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, list):
        return [canonical_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): canonical_value(item) for key, item in value.items()}
    return value


def values_equal(left: Any, right: Any) -> bool:
    try:
        return json.dumps(canonical_value(left), sort_keys=True, ensure_ascii=False) == json.dumps(
            canonical_value(right), sort_keys=True, ensure_ascii=False
        )
    except TypeError:
        return left == right


def apply_restore_spec(result: CatalogCreateResponse, spec: dict[str, Any]) -> CatalogCreateResponse:
    kind = str(spec.get("op") or "")
    if kind == "set_path":
        path = str(spec.get("path") or "")
        if not path:
            raise HistoryRejected("Rollback is missing the field path.")
        try:
            return set_path_value(result, path, spec.get("value"))
        except ApplyRejected as exc:
            raise HistoryRejected(str(exc)) from exc
    if kind == "remove_item":
        try:
            return apply_patch(result, {"op": "remove_item", "item_id": spec.get("item_id")})
        except PatchRejected as exc:
            raise HistoryRejected(str(exc)) from exc
    if kind == "insert_item":
        return _insert_item(
            result,
            category_index=int(spec["category_index"]),
            item_index=int(spec.get("item_index") or 0),
            item=spec.get("item") if isinstance(spec.get("item"), dict) else {},
        )
    if kind == "move_item":
        try:
            return apply_patch(
                result,
                {
                    "op": "move_item",
                    "item_id": spec.get("item_id"),
                    "from_index": spec.get("from_index"),
                    "to_index": spec.get("to_index"),
                },
            )
        except PatchRejected as exc:
            raise HistoryRejected(str(exc)) from exc
    if kind == "patch":
        try:
            return apply_patch(result, spec.get("patch") if isinstance(spec.get("patch"), dict) else {})
        except PatchRejected as exc:
            raise HistoryRejected(str(exc)) from exc
    raise HistoryRejected(f"Unsupported rollback operation: {kind or 'unknown'}.")


def current_matches_new_value(result: CatalogCreateResponse, spec: dict[str, Any], new_value: Any) -> bool:
    kind = str(spec.get("op") or "")
    if kind == "set_path":
        return values_equal(value_at_path(result, str(spec.get("path") or "")), new_value)
    if kind == "remove_item":
        return _find_item(result, str(spec.get("item_id") or "")) is not None
    if kind == "insert_item":
        item = spec.get("item") if isinstance(spec.get("item"), dict) else {}
        name = str(item.get("name") or "")
        category_index = int(spec.get("category_index") or 0)
        categories = list(result.categories or [])
        if category_index < 0 or category_index >= len(categories) or not isinstance(categories[category_index], dict):
            return True
        items = list(categories[category_index].get("items") or [])
        return not any(isinstance(row, dict) and str(row.get("name") or "") == name for row in items)
    return True


def _insert_item(
    result: CatalogCreateResponse,
    *,
    category_index: int,
    item_index: int,
    item: dict[str, Any],
) -> CatalogCreateResponse:
    categories = copy.deepcopy(list(result.categories or []))
    if category_index < 0 or category_index >= len(categories) or not isinstance(categories[category_index], dict):
        raise HistoryRejected("Category was not found.")
    items = list(categories[category_index].get("items") or [])
    index = max(0, min(item_index, len(items)))
    items.insert(index, copy.deepcopy(item))
    categories[category_index] = {**categories[category_index], "items": items, "item_count": len(items)}
    payload = result.model_dump(mode="json")
    payload["categories"] = categories
    return CatalogCreateResponse.model_validate(payload)


def _find_item(result: CatalogCreateResponse, item_id: str) -> dict[str, Any] | None:
    if not item_id:
        return None
    for category in result.categories or []:
        if not isinstance(category, dict):
            continue
        for item in category.get("items") or []:
            if isinstance(item, dict) and str(item.get("item_id") or item.get("id") or "") == item_id:
                return item
    return None

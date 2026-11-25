from __future__ import annotations

import uuid
from typing import Any

from scraper.discovery.urls import canonical_url

ADAPTER_VERSION = "canonical.v1"
SCHEMA_VERSION = 1


def normalize_platform(value: str | None) -> str:
    text = (value or "").strip().lower()
    return text or "swiggy"


def normalize_source_entity_id(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    return text or None


def source_entity_id_from_result(result: dict[str, Any]) -> str | None:
    """Platform listing id only. Never chain parentId / name / place."""
    restaurant = result.get("restaurant") if isinstance(result.get("restaurant"), dict) else {}
    dineout = result.get("dineout") if isinstance(result.get("dineout"), dict) else {}
    extra = restaurant.get("additional_information") if isinstance(restaurant.get("additional_information"), dict) else {}
    raw = restaurant.get("restaurant_id") or dineout.get("restaurant_id") or extra.get("id")
    return normalize_source_entity_id(raw)


def source_item_id_from_item(item: dict[str, Any]) -> str | None:
    direct = item.get("source_item_id")
    if direct not in (None, ""):
        return normalize_source_entity_id(direct)
    extra = item.get("additional_information") if isinstance(item.get("additional_information"), dict) else {}
    if extra.get("id") not in (None, ""):
        return normalize_source_entity_id(extra.get("id"))
    return None


def identity_tuple(result: dict[str, Any]) -> tuple[str, str, str | None]:
    platform = normalize_platform(str(result.get("platform") or ""))
    url = canonical_url(str(result.get("source_url") or ""))
    return platform, url, source_entity_id_from_result(result)


def previous_item_id_map(categories: list[Any] | None) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for category in categories or []:
        if not isinstance(category, dict):
            continue
        for item in category.get("items") or []:
            if not isinstance(item, dict):
                continue
            source_id = source_item_id_from_item(item)
            item_id = str(item.get("item_id") or item.get("id") or "").strip()
            if source_id and item_id:
                mapping.setdefault(source_id, item_id)
    return mapping


def assign_item_ids(
    categories: list[Any] | None,
    *,
    previous: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Reuse item_id only when source_item_id matches. Never match by name/price."""
    prior = previous or {}
    assigned: list[dict[str, Any]] = []
    for category in categories or []:
        if not isinstance(category, dict):
            continue
        items: list[dict[str, Any]] = []
        for item in category.get("items") or []:
            if not isinstance(item, dict):
                continue
            copied = dict(item)
            source_id = source_item_id_from_item(copied)
            if source_id:
                copied["source_item_id"] = source_id
            existing = str(copied.get("item_id") or "").strip()
            if source_id and source_id in prior:
                copied["item_id"] = prior[source_id]
            elif existing:
                copied["item_id"] = existing
            else:
                copied["item_id"] = str(uuid.uuid4())
            items.append(copied)
        assigned.append({**category, "items": items})
    return assigned

"""Incoming catalogue validation and quality reporting. Does not merge identities."""

from __future__ import annotations

from typing import Any

from backend.canonical.identity import source_item_id_from_item
from backend.catalogue_normalize import coerce_price, normalize_image_url
from scraper.swiggy.models import Catalogue, MenuItem


def _issue(code: str, path: str, message: str, severity: str = "warning") -> dict[str, str]:
    return {"code": code, "path": path, "severity": severity, "message": message}


def validate_catalogue(catalogue: Catalogue) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    restaurant_name = (catalogue.restaurant.name or "").strip()
    if catalogue.catalogue_type in {"restaurant", "both"} and catalogue.extraction_status == "ok" and not restaurant_name:
        issues.append(_issue("missing_restaurant_name", "restaurant.name", "Restaurant name is missing."))
    if catalogue.extraction_status == "ok" and not (catalogue.source_url or "").strip():
        issues.append(_issue("missing_source_url", "source_url", "Source URL is missing."))

    seen_source_ids: dict[str, str] = {}
    for category_index, category in enumerate(catalogue.categories):
        category_path = f"categories[{category_index}]"
        if not (category.name or "").strip():
            issues.append(_issue("missing_category_name", f"{category_path}.name", "Category name is missing."))
        if category.item_count is not None and int(category.item_count) != len(category.items):
            issues.append(
                _issue(
                    "category_count_mismatch",
                    f"{category_path}.item_count",
                    "Declared item_count does not match collected items.",
                )
            )
        seen_rows: dict[tuple[str, str | int | float | None], str] = {}
        for item_index, item in enumerate(category.items):
            path = f"{category_path}.items[{item_index}]"
            _validate_item(item, path, issues, seen_source_ids, seen_rows, category.name)
    return {"issues": issues}


def _validate_item(
    item: MenuItem,
    path: str,
    issues: list[dict[str, str]],
    seen_source_ids: dict[str, str],
    seen_rows: dict[tuple[str, str | int | float | None], str],
    category_name: str,
) -> None:
    if not (item.name or "").strip():
        issues.append(_issue("missing_item_name", f"{path}.name", "Item name is missing."))
        return
    if item.price is None:
        issues.append(_issue("missing_price", f"{path}.price", "Selling price is missing."))
    elif coerce_price(item.price) is None:
        issues.append(_issue("invalid_price", f"{path}.price", "Selling price is invalid."))
    if item.original_price is not None and coerce_price(item.original_price) is None:
        issues.append(_issue("invalid_price", f"{path}.original_price", "MRP is invalid."))
    if not item.image_url:
        issues.append(_issue("missing_image", f"{path}.image_url", "Dish image is missing."))
    else:
        display, _source, dropped = normalize_image_url(item.image_url)
        if dropped and display is None:
            issues.append(_issue("invalid_image", f"{path}.image_url", "Image URL is invalid or is not a dish image."))
    payload = {
        "source_item_id": item.additional_information.get("id") if isinstance(item.additional_information, dict) else None,
        "additional_information": item.additional_information,
    }
    source_id = source_item_id_from_item(payload) or (
        str(item.additional_information.get("id")).strip().lower()
        if isinstance(item.additional_information, dict) and item.additional_information.get("id") not in (None, "")
        else None
    )
    if not source_id:
        issues.append(_issue("missing_source_item_id", f"{path}.source_item_id", "Source item id is missing."))
    else:
        previous = seen_source_ids.get(source_id)
        if previous:
            issues.append(
                _issue(
                    "duplicate_source_item_id",
                    path,
                    f"Duplicate source_item_id {source_id} (also at {previous}).",
                )
            )
        else:
            seen_source_ids[source_id] = path
    row_key = ((item.name or "").strip().lower(), item.price)
    previous_row = seen_rows.get(row_key)
    if previous_row:
        issues.append(
            _issue(
                "duplicate_item_row",
                path,
                f"Duplicate name and price in category {category_name!r} (also at {previous_row}).",
            )
        )
    else:
        seen_rows[row_key] = path

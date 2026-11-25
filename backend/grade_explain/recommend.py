"""Deterministic recommended actions and sort order for Phase 5."""

from __future__ import annotations

from typing import Any

from backend.grade_explain.contract import PRIORITY_RULE, SectionId
from backend.grading.contract import EvidenceItem, EvidenceSeverity
from backend.grading.formula import WEIGHTS

SEVERITY_RANK: dict[EvidenceSeverity, int] = {
    "hard": 0,
    "ordinary": 1,
    "info": 2,
}

ACTIONABLE_RESULTS = frozenset({"fail", "error"})


def is_actionable(item: EvidenceItem) -> bool:
    return item.result in ACTIONABLE_RESULTS


def recommendation_action(
    *,
    check_id: str,
    affected_count: int,
    details: dict[str, Any],
    explanation: str,
) -> str:
    """Concrete action from the finding. Not generic advice."""
    count = max(1, int(affected_count))
    described = details.get("described")
    item_total = details.get("item_total")
    coverage = details.get("coverage")
    repeated_count = details.get("repeated_count")
    templates = {
        "extraction_not_ok": "Fix catalogue extraction so extraction_status is ok, then re-grade.",
        "missing_restaurant_name": "Add a restaurant name.",
        "missing_source_url": "Add a source URL.",
        "empty_menu": "Add menu items to this restaurant catalogue.",
        "missing_fssai": "Add the FSSAI license number.",
        "missing_address": "Add the venue address.",
        "missing_category_name": f"Name the {count} unnamed menu categories.",
        "category_count_mismatch": (
            f"Correct declared item_count on {count} categories so it matches collected items."
        ),
        "missing_item_name": f"Add names for {count} menu items.",
        "missing_price": f"Add selling prices for {count} items.",
        "invalid_price": f"Correct invalid selling price or MRP on {count} fields.",
        "missing_item_image": f"Add dish images for {count} items.",
        "missing_description": f"Add descriptions for the {count} items that have none.",
        "description_coverage": _coverage_action(described, item_total, coverage),
        "placeholder_text": f"Replace placeholder text in {count} fields.",
        "malformed_text": f"Replace unusable text in {count} fields with letters or digits.",
        "repeated_description": _repeat_action(repeated_count),
        "no_images_present": "Add at least one catalogue image.",
        "image_missing": f"Provide image files or URLs for {count} empty image fields.",
        "image_invalid": f"Replace {count} invalid images with PNG, JPEG, GIF, or WebP files.",
        "image_unreadable": f"Replace {count} unreadable images with valid image files.",
        "image_low_quality": (
            f"Replace {count} undersized images with photos at least 64px on the short edge "
            "and 80×80 pixels."
        ),
        "no_item_text": "Add menu item names or descriptions so text quality can be graded.",
    }
    if check_id in templates:
        return templates[check_id]
    return f"Fix {count} failing {check_id} finding(s): {explanation}"


def _coverage_action(described: Any, item_total: Any, coverage: Any) -> str:
    if described is not None and item_total is not None:
        return (
            f"Add descriptions until at least 70% of items have one "
            f"({described} of {item_total} currently described)."
        )
    if coverage is not None:
        return f"Add item descriptions until coverage is at least 70% (currently {coverage})."
    return "Add item descriptions until coverage is at least 70%."


def _repeat_action(repeated_count: Any) -> str:
    if repeated_count is not None:
        return (
            f"Write unique descriptions for items that currently share identical text "
            f"({repeated_count} duplicated values)."
        )
    return "Write unique descriptions for items that currently share identical text."


def priority_sort_key(
    *,
    severity: EvidenceSeverity,
    section: SectionId,
    affected_count: int,
    check_id: str,
) -> tuple:
    weight = float(WEIGHTS.get(section, 0.0))
    return (
        SEVERITY_RANK.get(severity, 9),
        -weight,
        -int(affected_count),
        section,
        check_id,
    )


def priority_rule() -> str:
    return PRIORITY_RULE

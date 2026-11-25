"""Deterministic, reproducible catalogue quality rules. No fuzzy matching."""

from __future__ import annotations

from backend.canonical.models import CanonicalDocument
from backend.catalogue_normalize import coerce_price
from backend.grading.contract import StageSignals
from backend.grading.document import iter_menu_items
from backend.grading.evidence import evidence

DEDUCTION_CAPS = {
    "missing_item_name": (8.0, 40.0),
    "missing_price": (4.0, 30.0),
    "invalid_price": (6.0, 24.0),
    "missing_item_image": (3.0, 25.0),
    "missing_category_name": (5.0, 15.0),
    "missing_description": (1.0, 15.0),
    "category_count_mismatch": (3.0, 9.0),
    "missing_fssai": (10.0, 10.0),
    "missing_address": (5.0, 5.0),
}


def grade_deterministic(document: CanonicalDocument) -> StageSignals:
    findings = []
    deductions: dict[str, float] = {key: 0.0 for key in DEDUCTION_CAPS}
    hard_ids: list[str] = []

    status = (document.extraction_status or "").strip().lower()
    if status != "ok":
        hard_ids.append("extraction_not_ok")
        findings.append(
            evidence(
                category="deterministic",
                check_id="extraction_not_ok",
                severity="hard",
                result="fail",
                explanation="Catalogue extraction_status is not ok.",
                path="extraction_status",
                details={"extraction_status": document.extraction_status},
            )
        )
    else:
        findings.append(
            evidence(
                category="deterministic",
                check_id="extraction_not_ok",
                severity="hard",
                result="pass",
                explanation="Catalogue extraction_status is ok.",
                path="extraction_status",
            )
        )

    name = (document.restaurant_name or document.venue.name or "").strip()
    if status == "ok" and not name:
        hard_ids.append("missing_restaurant_name")
        findings.append(
            evidence(
                category="deterministic",
                check_id="missing_restaurant_name",
                severity="hard",
                result="fail",
                explanation="Restaurant name is missing.",
                path="restaurant_name",
            )
        )
    elif name:
        findings.append(
            evidence(
                category="deterministic",
                check_id="missing_restaurant_name",
                severity="hard",
                result="pass",
                explanation="Restaurant name is present.",
                path="restaurant_name",
            )
        )

    source_url = (document.provenance.source_url or document.provenance.canonical_source_url or "").strip()
    if status == "ok" and not source_url:
        hard_ids.append("missing_source_url")
        findings.append(
            evidence(
                category="deterministic",
                check_id="missing_source_url",
                severity="hard",
                result="fail",
                explanation="Source URL is missing.",
                path="provenance.source_url",
            )
        )

    item_rows = list(iter_menu_items(document))
    requires_menu = document.catalogue_type in {"restaurant", "both"}
    if requires_menu and status == "ok" and not item_rows:
        hard_ids.append("empty_menu")
        findings.append(
            evidence(
                category="deterministic",
                check_id="empty_menu",
                severity="hard",
                result="fail",
                explanation="Restaurant catalogue has no menu items.",
                path="menus",
                details={"item_count": document.item_count},
            )
        )

    fssai = (document.fssai_number or document.venue.fssai_license or "").strip()
    if requires_menu and not fssai:
        _add_deduction(deductions, "missing_fssai")
        findings.append(
            evidence(
                category="deterministic",
                check_id="missing_fssai",
                severity="ordinary",
                result="fail",
                explanation="FSSAI license number is missing.",
                path="fssai_number",
            )
        )

    address = (document.venue.address or "").strip()
    if requires_menu and not address:
        _add_deduction(deductions, "missing_address")
        findings.append(
            evidence(
                category="deterministic",
                check_id="missing_address",
                severity="ordinary",
                result="fail",
                explanation="Venue address is missing.",
                path="venue.address",
            )
        )

    for menu_index, menu in enumerate(document.menus):
        for category_index, category in enumerate(menu.categories):
            category_path = f"menus[{menu_index}].categories[{category_index}]"
            if not (category.name or "").strip():
                _add_deduction(deductions, "missing_category_name")
                findings.append(
                    evidence(
                        category="deterministic",
                        check_id="missing_category_name",
                        severity="ordinary",
                        result="fail",
                        explanation="Category name is missing.",
                        path=f"{category_path}.name",
                    )
                )
            if category.item_count is not None and int(category.item_count) != len(category.items):
                _add_deduction(deductions, "category_count_mismatch")
                findings.append(
                    evidence(
                        category="deterministic",
                        check_id="category_count_mismatch",
                        severity="ordinary",
                        result="fail",
                        explanation="Declared item_count does not match collected items.",
                        path=f"{category_path}.item_count",
                        details={"declared": category.item_count, "actual": len(category.items)},
                    )
                )

    for path, _category, item in item_rows:
        if not (item.name or "").strip():
            _add_deduction(deductions, "missing_item_name")
            findings.append(
                evidence(
                    category="deterministic",
                    check_id="missing_item_name",
                    severity="ordinary",
                    result="fail",
                    explanation="Item name is missing.",
                    path=f"{path}.name",
                )
            )
            continue
        if item.price is None:
            _add_deduction(deductions, "missing_price")
            findings.append(
                evidence(
                    category="deterministic",
                    check_id="missing_price",
                    severity="ordinary",
                    result="fail",
                    explanation="Selling price is missing.",
                    path=f"{path}.price",
                )
            )
        elif coerce_price(item.price) is None:
            _add_deduction(deductions, "invalid_price")
            findings.append(
                evidence(
                    category="deterministic",
                    check_id="invalid_price",
                    severity="ordinary",
                    result="fail",
                    explanation="Selling price is invalid.",
                    path=f"{path}.price",
                    details={"value": item.price},
                )
            )
        if item.original_price is not None and coerce_price(item.original_price) is None:
            _add_deduction(deductions, "invalid_price")
            findings.append(
                evidence(
                    category="deterministic",
                    check_id="invalid_price",
                    severity="ordinary",
                    result="fail",
                    explanation="MRP is invalid.",
                    path=f"{path}.original_price",
                    details={"value": item.original_price},
                )
            )
        if not (item.image_url or item.source_image_url):
            _add_deduction(deductions, "missing_item_image")
            findings.append(
                evidence(
                    category="deterministic",
                    check_id="missing_item_image",
                    severity="ordinary",
                    result="fail",
                    explanation="Dish image is missing.",
                    path=f"{path}.image_url",
                )
            )
        if not (item.description or "").strip():
            _add_deduction(deductions, "missing_description")
            findings.append(
                evidence(
                    category="deterministic",
                    check_id="missing_description",
                    severity="ordinary",
                    result="fail",
                    explanation="Item description is missing.",
                    path=f"{path}.description",
                )
            )

    score = max(0.0, 100.0 - sum(deductions.values()))
    if not findings:
        findings.append(
            evidence(
                category="deterministic",
                check_id="deterministic_clean",
                severity="info",
                result="pass",
                explanation="No deterministic rule failures.",
            )
        )
    return StageSignals(score=round(score, 4), evidence=findings, hard_failures=hard_ids)


def _add_deduction(deductions: dict[str, float], check_id: str) -> None:
    per, cap = DEDUCTION_CAPS[check_id]
    deductions[check_id] = min(cap, deductions[check_id] + per)

"""Grounded catalogue copy. Uses only verified item facts. Never invents ingredients or claims."""

from __future__ import annotations

import re
from typing import Any

from backend.catalogue_normalize import collapse_text, normalize_labels
from backend.improvement.contract import MAX_LABELS
from backend.improvement.validate import CLAIM_PHRASES

_SPACE = re.compile(r"\s+")
_UNSUPPORTED_TAG = re.compile(
    r"gluten|vegan|keto|halal|kosher|organic|award|michelin|certified|sugar-free|msg",
    re.IGNORECASE,
)


def polish_description(
    *,
    name: str,
    category_name: str | None,
    description: str | None,
    labels: list[str] | None = None,
) -> str:
    current = collapse_text(description) or ""
    if current:
        text = current[0].upper() + current[1:]
        if text[-1] not in ".!?":
            text += "."
        category = collapse_text(category_name) or ""
        if category and category.casefold() != "menu" and category.casefold() not in text.casefold():
            candidate = f"{text} in {category}."
            if not _contains_unsupported_claim(candidate, current, category, name, labels):
                return candidate
        return text
    category = collapse_text(category_name) or ""
    item = collapse_text(name) or "This item"
    if category and category.casefold() != "menu":
        return f"{item} in {category}."
    return f"{item}."


def description_needs_owner_facts(current: str | None, proposed: str) -> bool:
    now = collapse_text(current) or ""
    return _normalize_compare(now) == _normalize_compare(proposed) or len(proposed.split()) < 4


def suggest_labels(
    *,
    name: str,
    category_name: str | None,
    description: str | None,
    labels: list[str] | None,
) -> list[str]:
    existing = normalize_labels(labels or [])
    blob = " ".join(
        part
        for part in (name, category_name or "", description or "", " ".join(existing))
        if part
    ).casefold()
    suggested = list(existing)
    category = collapse_text(category_name)
    if category and not _has_label(suggested, category) and not _UNSUPPORTED_TAG.search(category):
        suggested.append(category)
    for token, label in (
        ("non-veg", "Non-veg"),
        ("non veg", "Non-veg"),
        ("vegetarian", "Vegetarian"),
        (" veg", "Vegetarian"),
        ("spicy", "Spicy"),
        ("chicken", "Chicken"),
        ("paneer", "Paneer"),
        ("rice", "Rice"),
        ("biryani", "Biryani"),
        ("lemonade", "Beverage"),
        ("lemon", "Lemon"),
    ):
        if token in f" {blob} " or blob.startswith(token) or token in blob:
            if token.strip() == "veg" and "non-veg" in blob:
                continue
            if not _has_label(suggested, label) and not _UNSUPPORTED_TAG.search(label):
                suggested.append(label)
    cleaned = [row for row in normalize_labels(suggested) if not _UNSUPPORTED_TAG.search(row)]
    return cleaned[:MAX_LABELS]


def _has_label(labels: list[str], candidate: str) -> bool:
    needle = candidate.casefold()
    return any(row.casefold() == needle for row in labels)


def _contains_unsupported_claim(text: str, *trusted: Any) -> bool:
    blob = " ".join(str(part or "") for part in trusted).casefold()
    lowered = text.casefold()
    for phrase in CLAIM_PHRASES:
        if phrase in lowered and phrase not in blob:
            return True
    return False


def _normalize_compare(text: str) -> str:
    return _SPACE.sub(" ", text).strip().casefold().rstrip(".!")

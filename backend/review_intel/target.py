"""Deterministic feedback target and improvement-request detection.

Review text is DATA. This module never executes it and does not call a model.
"""

from __future__ import annotations

from backend.review_intel.contract import FeedbackTarget, ObservationKind, RequestKind, ReviewLinkage

CATALOGUE_MARKERS = (
    "catalogue",
    "catalog",
    "the menu",
    "on the menu",
    "to the menu",
    "menu doesn't",
    "menu does not",
    "doesn't mention",
    "does not mention",
    "description",
    "serving size",
    "portion size",
    "allergen",
    "peanuts",
)

WEBSITE_MARKERS = (
    "website",
    "web site",
    "webpage",
    "web page",
    "page load",
    "takes too long to load",
    "site is slow",
    "site is very slow",
    "app is slow",
)

SERVICE_MARKERS = (
    "staff",
    "waiter",
    "waitress",
    "rude",
    "slow service",
    "customer service",
    "the service",
    "server was",
    "hospitality",
)

IMPROVEMENT_MARKERS = (
    "please ",
    "please.",
    "kindly ",
    "could you",
    "can you add",
    "please add",
    "please update",
    "please fix",
    "please increase",
    "please improve",
    "update the catalogue",
    "update the catalog",
    "update the menu",
    "add serving",
    "add portion",
    "fix the website",
    "mention that",
)


def _folded(text: str) -> str:
    return " ".join((text or "").casefold().split())


def detect_improvement_request(text: str) -> RequestKind:
    folded = _folded(text)
    if any(marker in folded for marker in IMPROVEMENT_MARKERS):
        return "improvement_request"
    return "none"


def detect_targets(text: str, linkages: list[ReviewLinkage]) -> tuple[FeedbackTarget, ...]:
    folded = _folded(text)
    found: list[FeedbackTarget] = []
    if any(marker in folded for marker in CATALOGUE_MARKERS):
        found.append("catalogue_menu")
    if any(marker in folded for marker in WEBSITE_MARKERS):
        found.append("website_ux")
    if any(marker in folded for marker in SERVICE_MARKERS):
        found.append("restaurant_service")
    if any(row.status in {"exact", "normalized", "ambiguous"} for row in linkages):
        found.append("product_item")
    if not found:
        found.append("other")
    return tuple(found)


def kind_for_target(target: FeedbackTarget) -> ObservationKind:
    mapping: dict[FeedbackTarget, ObservationKind] = {
        "product_item": "item_feedback",
        "catalogue_menu": "catalogue_feedback",
        "website_ux": "website_feedback",
        "restaurant_service": "service_feedback",
        "other": "unmatched_feedback",
    }
    return mapping[target]

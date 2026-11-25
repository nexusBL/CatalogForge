"""Deterministic intent routing. Runs before any LLM call."""

from __future__ import annotations

import re

from backend.assistant.contract import AssistantIntent

_COLLAPSE = re.compile(r"\s+")

_MUTATION = (
    "delete catalogue",
    "delete this catalogue",
    "apply improvement",
    "approve improvement",
    "apply the proposal",
    "apply improvement proposal",
    "publish",
    "re-grade",
    "regrade",
    "run grading",
    "modify the catalogue",
    "update the catalogue",
    "update catalogue",
    "write to sqlite",
    "patch json",
)

_INJECTION = (
    "ignore all previous",
    "ignore previous instructions",
    "ignore any previous",
    "you are now",
    "system prompt",
)

_CATALOGUE_GRADE = re.compile(
    r"why (did|does|is) (i|my catalogue|the catalogue|this catalogue).*(grade|score|[a-f]\b)",
    re.IGNORECASE,
)
_LETTER_GRADE = re.compile(r"why did (i|my catalogue).*\b[a-f]\b", re.IGNORECASE)


def normalize_message(message: str) -> str:
    return _COLLAPSE.sub(" ", (message or "").strip()).casefold()


def route_intent(message: str) -> AssistantIntent | None:
    """Return a frozen intent when the request is safe to handle without an LLM."""
    text = normalize_message(message)
    if not text:
        return None
    if any(token in text for token in _MUTATION) or any(token in text for token in _INJECTION):
        return "refuse_mutation"
    if text in {"why is it bad", "why is this bad", "why is it so bad"}:
        return "clarify"
    if "baba score" in text:
        return "show_baba_score"
    if _is_capabilities(text):
        return "explain_capabilities"
    if _is_catalogue_summary(text):
        return "explain_catalogue_summary"
    if _is_catalogue_problems(text):
        return "explain_problems"
    if _is_open_improvements(text):
        return "open_improvements"
    if _is_open_reviews(text):
        return "open_reviews"
    if _is_open_media(text):
        return "open_media"
    if _is_open_grade(text):
        return "open_grade"
    if _is_open_catalogue(text):
        return "open_catalogue"
    if _is_fix_first(text):
        return "explain_fix_first"
    if _is_review_complaints(text):
        return "explain_review_complaints"
    if _is_items_attention(text):
        return "explain_items_attention"
    if _is_org_grades(text):
        return "explain_org_grades"
    if _is_description_fix(text):
        return "open_improvements"
    if _is_photo_question(text):
        return "explain_items_attention"
    if _is_low_grade_reason(text):
        return "explain_catalogue_grade"
    if _CATALOGUE_GRADE.search(text) or _LETTER_GRADE.search(text) or "why did i get" in text:
        return "explain_catalogue_grade"
    return None


def looks_like_item_question(message: str) -> bool:
    text = normalize_message(message)
    return any(
        token in text
        for token in (
            "why is",
            "performing badly",
            "performing poorly",
            "this item",
            "this dish",
            "need attention",
            "what is wrong with",
            "tell me about",
            "price of",
            "how much is",
            "does my catalogue have",
            "do i have",
            "how is",
            "about",
            "check",
        )
    )


def _is_capabilities(text: str) -> bool:
    return any(
        token in text
        for token in (
            "what can you do",
            "what are your capabilities",
            "what do you do",
            "how can you help",
            "what can baba do",
        )
    )


def _is_catalogue_problems(text: str) -> bool:
    return any(
        token in text
        for token in (
            "what problems",
            "catalogue problems",
            "what is wrong with my catalogue",
            "what is hurting my grade",
            "what is lowering my grade",
            "catalogue issues",
            "what is wrong with the catalogue",
        )
    )


def _is_catalogue_summary(text: str) -> bool:
    return any(
        token in text
        for token in (
            "how many products",
            "how many items",
            "how many dishes",
            "total products",
            "product count",
            "item count",
            "show me my products",
            "show my products",
            "list my products",
            "show products",
            "list products",
            "what products do i have",
            "what categories",
            "list categories",
            "which categories",
            "show categories",
            "how many categories",
            "category has the most",
            "largest category",
            "biggest category",
            "don't have description",
            "don't have descriptions",
            "no description",
            "without description",
            "without descriptions",
            "don't have image",
            "don't have images",
            "no image",
            "no photo",
            "without image",
            "without images",
            "don't have tag",
            "don't have tags",
            "no tag",
            "no tags",
            "no label",
            "no labels",
            "without tag",
            "without tags",
            "most expensive",
            "cheapest",
            "expensive products",
            "expensive items",
        )
    )


def _is_open_improvements(text: str) -> bool:
    return any(
        token in text
        for token in (
            "show recommendations",
            "show my recommendations",
            "view recommendations",
            "open improvements",
            "ai improvements",
        )
    )


def _is_open_reviews(text: str) -> bool:
    return any(token in text for token in ("open reviews", "show reviews", "show my reviews", "view reviews"))


def _is_open_media(text: str) -> bool:
    if re.search(r"\b(improve|fix)\b", text) and re.search(r"\b(image|photo|picture)s?\b", text):
        return True
    return any(
        token in text
        for token in (
            "open image improvement",
            "show image improvement",
            "image improvement",
            "open media",
            "generated media",
        )
    )


def _is_open_grade(text: str) -> bool:
    if "recommendation" in text or "baba score" in text:
        return False
    return any(
        token in text
        for token in ("show my grade", "show the grade", "show grade", "open grade", "view grade", "grade details")
    )


def _is_open_catalogue(text: str) -> bool:
    return any(token in text for token in ("open catalogue", "show catalogue", "open the catalogue", "view catalogue"))


def _is_fix_first(text: str) -> bool:
    return any(
        token in text
        for token in ("what should i fix first", "what should i improve first", "fix first", "improve first")
    )


def _is_review_complaints(text: str) -> bool:
    return any(
        token in text
        for token in (
            "customers unhappy",
            "customers complaining",
            "customers complain",
            "complaining about",
            "what are customers",
            "recurring complaints",
            "recurring complaint",
        )
    )


def _is_items_attention(text: str) -> bool:
    return any(
        token in text
        for token in (
            "which dishes need",
            "which items need",
            "dishes need attention",
            "items need attention",
            "which dishes are missing",
            "which items are missing",
            "missing descriptions",
            "hurting the grade",
            "hurting my grade",
        )
    )


def _is_low_grade_reason(text: str) -> bool:
    return any(
        token in text
        for token in (
            "why is this grade",
            "why is my grade",
            "why is this restaurant",
            "why is this dineout",
            "why is the grade",
            "why is my restaurant graded",
            "why is my grade so low",
            "why is this grade so low",
        )
    )


def _is_photo_question(text: str) -> bool:
    if "which" in text and any(token in text for token in ("photo", "image", "picture")):
        return True
    return any(
        token in text
        for token in (
            "which photos need",
            "which images need",
            "photos need improvement",
            "images need improvement",
        )
    )


def _is_description_fix(text: str) -> bool:
    return any(
        token in text
        for token in (
            "improve those descriptions",
            "improve the descriptions",
            "fix the missing descriptions",
            "fix missing descriptions",
            "improve the missing descriptions",
            "improve this dish",
            "improve this item",
            "open ai improvements",
        )
    )


def _is_org_grades(text: str) -> bool:
    return any(
        token in text
        for token in (
            "restaurants with poor grades",
            "venues with poor grades",
            "poor grades",
            "low grades",
            "bad grades",
            "worst grades",
            "poorly graded",
            "which of my restaurants",
            "restaurants need the most",
            "venues need the most",
            "show me my restaurants with poor",
        )
    )

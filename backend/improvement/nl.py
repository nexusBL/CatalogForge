"""Natural-language quality improve to a Phase 6/11 proposal. Does not apply."""

from __future__ import annotations

import re

from backend.assistant.contract import AssistantTurnResponse
from backend.assistant.links import actions_for_intent
from backend.improvement.contract import ImprovementLineRequest
from backend.improvement.eligibility import ImprovementUnsupported
from backend.improvement.service import create_improvement
from backend.store import get_catalogue

_COLLAPSE = re.compile(r"\s+")
_IMAGE_OR_VIDEO = re.compile(r"\b(images?|photos?|pictures?|videos?|gifs?)\b", re.IGNORECASE)
_LABELS = re.compile(r"\b(tags?|labels)\b", re.IGNORECASE)
_DESCRIPTION = re.compile(r"\bdescriptions?\b", re.IGNORECASE)
_IMPROVE = re.compile(
    r"\b(improve|make\b.+\bbetter|fix the tags|improve the tags|improve this (?:dish|item))\b",
    re.IGNORECASE,
)


def maybe_handle_quality_improve(
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str | None,
    message: str,
) -> AssistantTurnResponse | None:
    check_id = _quality_check_id(message)
    if check_id is None:
        return None
    if not catalogue_id:
        return AssistantTurnResponse(
            message="Open a restaurant catalogue, then ask me to improve an item.",
            intent="clarify",
            used_llm=False,
            actions=[],
        )
    stored = get_catalogue(user_id, catalogue_id, organization_id)
    if stored is None:
        return None
    path = _item_field_path(stored.result, message, check_id)
    if path is None:
        return None
    try:
        proposal = create_improvement(
            user_id=user_id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
            request=ImprovementLineRequest(check_id=check_id, paths=[path]),
        )
    except (ImprovementUnsupported, LookupError, ValueError) as exc:
        return AssistantTurnResponse(
            message=(
                "I could not safely generate that improvement from verified catalogue facts. "
                f"{exc} Open AI Improvements to review supported findings."
            ),
            intent="open_improvements",
            used_llm=False,
            actions=actions_for_intent("open_improvements", catalogue_id, check_id=check_id),
        )
    lines = "\n".join(_line_summary(line) for line in proposal.lines) or "No ready suggestion."
    return AssistantTurnResponse(
        message=(
            f"I generated an AI improvement preview ({proposal.status}). "
            "It is not live until you apply it on AI Improvements.\n"
            f"{lines}"
        ),
        intent="open_improvements",
        used_llm=False,
        actions=actions_for_intent("open_improvements", catalogue_id, check_id=check_id),
    )


def _quality_check_id(message: str) -> str | None:
    text = _COLLAPSE.sub(" ", (message or "").strip())
    if not text or not _IMPROVE.search(text):
        return None
    if _IMAGE_OR_VIDEO.search(text):
        return None
    if _LABELS.search(text):
        return "empty_item_labels"
    if _DESCRIPTION.search(text):
        return "missing_description"
    return "missing_description"


def _item_field_path(result, message: str, check_id: str) -> str | None:
    text = _COLLAPSE.sub(" ", (message or "").strip()).casefold()
    field = "labels" if check_id == "empty_item_labels" else "description"
    categories = getattr(result, "categories", None) or []
    for category_index, category in enumerate(categories):
        if not isinstance(category, dict):
            continue
        items = category.get("items") or []
        if not isinstance(items, list):
            continue
        for item_index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if name and name.casefold() in text:
                return f"menus[0].categories[{category_index}].items[{item_index}].{field}"
    if re.search(r"\b(this dish|this item)\b", text) and categories:
        first = categories[0]
        items = first.get("items") if isinstance(first, dict) else None
        if isinstance(items, list) and items:
            return f"menus[0].categories[0].items[0].{field}"
    return None


def _line_summary(line) -> str:
    current = getattr(line, "current_value", None) or "(empty)"
    proposed = getattr(line, "proposed_value", None)
    labels = getattr(line, "proposed_labels", None)
    if labels:
        proposed = ", ".join(str(part) for part in labels)
    proposed = proposed or getattr(line, "failure_reason", None) or "(none)"
    return f"Current: {current}\nProposed: {proposed}"

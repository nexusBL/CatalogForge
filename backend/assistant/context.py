"""Page/entity context for Baba AI. Route text is a hint; authz still uses the request catalogue."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from backend.assistant.contract import AssistantIntent
from backend.assistant.router import normalize_message

PageSection = str


@dataclass(frozen=True)
class PageContext:
    current_route: str | None
    catalogue_id: str | None
    section: PageSection
    entity_type: str


def parse_page_context(current_route: str | None) -> PageContext:
    raw = (current_route or "").strip()
    if not raw:
        return PageContext(current_route=None, catalogue_id=None, section="unknown", entity_type="none")
    parsed = urlparse(raw if "://" in raw or raw.startswith("/") else f"/{raw.lstrip('/')}")
    path = parsed.path or "/"
    query = parse_qs(parsed.query)
    tab = (query.get("tab") or [None])[0]
    parts = [part for part in path.split("/") if part]
    if path == "/grading" or path == "/grading/":
        return PageContext(current_route=raw, catalogue_id=None, section="grading_list", entity_type="org")
    if len(parts) >= 2 and parts[0] == "grading":
        section = "quality"
        if tab == "photos":
            section = "photos"
        elif tab == "video":
            section = "video"
        return PageContext(current_route=raw, catalogue_id=parts[1], section=section, entity_type="venue")
    if len(parts) >= 1 and parts[0] == "baba-ai":
        catalogue_id = (query.get("catalogue") or [None])[0]
        return PageContext(
            current_route=raw,
            catalogue_id=catalogue_id,
            section="baba_ai",
            entity_type="venue" if catalogue_id else "org",
        )
    if len(parts) >= 2 and parts[0] == "catalogues" and parts[1] != "new":
        catalogue_id = parts[1]
        section = "catalogue"
        entity_type = "catalogue"
        if len(parts) >= 3:
            if parts[2] == "improvements":
                section = "improvements"
            elif parts[2] == "media":
                section = "photos"
            elif parts[2] == "reviews":
                section = "reviews"
        return PageContext(current_route=raw, catalogue_id=catalogue_id, section=section, entity_type=entity_type)
    if path.startswith("/reviews"):
        return PageContext(current_route=raw, catalogue_id=None, section="reviews", entity_type="org")
    return PageContext(current_route=raw, catalogue_id=None, section="unknown", entity_type="none")


def bind_request_catalogue(page: PageContext, request_catalogue_id: str | None) -> PageContext:
    """The authenticated catalogue path always wins over a client-supplied route id."""
    if request_catalogue_id:
        return PageContext(
            current_route=page.current_route,
            catalogue_id=request_catalogue_id,
            section=page.section,
            entity_type=page.entity_type if page.entity_type != "none" else "catalogue",
        )
    return page


def apply_page_context(
    intent: AssistantIntent | None,
    message: str,
    page: PageContext,
) -> AssistantIntent | None:
    text = normalize_message(message)
    deictic = any(
        token in text
        for token in ("this restaurant", "this dineout", "this venue", "this grade", "this catalogue", "this listing")
    )
    on_venue = bool(page.catalogue_id)
    low_hint = "why" in text and ("so low" in text or "so bad" in text or "this grade" in text)
    if intent == "clarify" and on_venue and (deictic or low_hint or text in {"why is it bad", "why is this bad", "why is it so bad", "why is this so low", "why is it so low"}):
        if page.section in {"photos", "video"} and ("photo" in text or "image" in text or "video" in text):
            return "explain_items_attention"
        return "explain_catalogue_grade"
    if intent is None and on_venue and (
        deictic
        or low_hint
        or text in {"why is it bad", "why is this bad", "why is it so bad", "why is this so low", "why is it so low"}
        or "these dishes" in text
        or "those dishes" in text
        or "this grade" in text
    ):
        if "dish" in text or "item" in text or "description" in text:
            return "explain_items_attention"
        return "explain_catalogue_grade"
    if intent is None and page.section == "grading_list" and any(
        token in text for token in ("poor grade", "low grade", "bad grade", "worst grade")
    ):
        return "explain_org_grades"
    return intent

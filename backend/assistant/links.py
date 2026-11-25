"""Server-built allowlisted catalogue workspace links. Never accept model hrefs."""

from __future__ import annotations

from urllib.parse import parse_qs, urlencode, urlparse

from backend.assistant.contract import AssistantAction, AssistantIntent

_LABELS = {
    "open_catalogue": ("Open Catalogue", "catalogue"),
    "open_grade": ("View Grade", "grade"),
    "open_improvements": ("Open AI Improvements", "improvements"),
    "open_reviews": ("View Reviews", "reviews"),
    "open_media": ("Open Generated Media", "media"),
    "show_baba_score": ("View Grade", "grade"),
    "explain_catalogue_grade": ("View Grade", "grade"),
    "explain_fix_first": ("Open AI Improvements", "improvements"),
    "explain_review_complaints": ("View Reviews", "reviews"),
    "explain_items_attention": ("View Grade", "grade"),
    "explain_item_findings": ("View Grade", "grade"),
    "explain_org_grades": ("Open Grading", "grading_list"),
    "explain_catalogue_summary": ("Open Catalogue", "catalogue"),
    "explain_capabilities": ("Open Catalogue", "catalogue"),
    "explain_problems": ("View Grade", "grade"),
    "refuse_mutation": ("Open Catalogue", "catalogue"),
    "propose_mutation": ("Open Catalogue", "catalogue"),
    "clarify": ("View Grade", "grade"),
    "unsupported": ("Open Catalogue", "catalogue"),
}


def catalogue_path(catalogue_id: str) -> str:
    return f"/catalogues/{catalogue_id}"


def grading_path(catalogue_id: str | None = None) -> str:
    if catalogue_id:
        return f"/grading/{catalogue_id}"
    return "/grading"


def improvements_path(catalogue_id: str, *, check_id: str | None = None) -> str:
    base = f"/catalogues/{catalogue_id}/improvements"
    if check_id:
        return f"{base}?{urlencode({'check_id': check_id})}"
    return base


def reviews_path(catalogue_id: str) -> str:
    return f"/catalogues/{catalogue_id}/reviews"


def media_path(catalogue_id: str, *, path: str | None = None) -> str:
    base = f"/catalogues/{catalogue_id}/media"
    if path:
        return f"{base}?{urlencode({'path': path})}"
    return base


def actions_for_intent(
    intent: AssistantIntent,
    catalogue_id: str,
    *,
    item_path: str | None = None,
    check_id: str | None = None,
    venues: list[dict] | None = None,
) -> list[AssistantAction]:
    rows: list[AssistantAction] = []
    if intent == "explain_org_grades":
        list_href = grading_path()
        if href_allowed(list_href, catalogue_id or ""):
            rows.append(_action("Open Grading", list_href))
        for venue in (venues or [])[:6]:
            venue_id = venue.get("catalogue_id")
            name = venue.get("name") or "Venue"
            if not venue_id:
                continue
            href = grading_path(str(venue_id))
            if href_allowed(href, str(venue_id)):
                rows.append(_action(f"View Grade — {name}", href))
        return rows
    if intent == "explain_item_findings":
        rows.append(_action("View Grade", grading_path(catalogue_id)))
        rows.append(_action("Open AI Improvements", improvements_path(catalogue_id, check_id=check_id)))
        if item_path:
            rows.append(_action("Open Generated Media", media_path(catalogue_id, path=item_path)))
        return [row for row in rows if href_allowed(row.href, catalogue_id)]
    if intent == "explain_catalogue_grade":
        rows.append(_action("View Grade", grading_path(catalogue_id)))
        rows.append(_action("Open AI Improvements", improvements_path(catalogue_id, check_id=check_id)))
        return [row for row in rows if href_allowed(row.href, catalogue_id)]
    if intent == "explain_fix_first":
        rows.append(_action("Open AI Improvements", improvements_path(catalogue_id, check_id=check_id)))
        rows.append(_action("View Grade", grading_path(catalogue_id)))
        return [row for row in rows if href_allowed(row.href, catalogue_id)]
    if intent == "explain_items_attention":
        rows.append(_action("View Grade", grading_path(catalogue_id)))
        rows.append(_action("Open AI Improvements", improvements_path(catalogue_id, check_id=check_id)))
        rows.append(_action("Open Generated Media", media_path(catalogue_id, path=item_path)))
        return [row for row in rows if href_allowed(row.href, catalogue_id)]
    if intent == "open_media":
        href = media_path(catalogue_id, path=item_path)
        return [_action("Open Generated Media", href)] if href_allowed(href, catalogue_id) else []
    if intent == "clarify":
        if catalogue_id:
            rows.append(_action("View Grade", grading_path(catalogue_id)))
            rows.append(_action("View Reviews", reviews_path(catalogue_id)))
            return [row for row in rows if href_allowed(row.href, catalogue_id)]
        href = grading_path()
        return [_action("Open Grading", href)] if href_allowed(href, "") else []
    label, kind = _LABELS[intent]
    href = {
        "catalogue": catalogue_path(catalogue_id),
        "grade": grading_path(catalogue_id),
        "improvements": improvements_path(catalogue_id, check_id=check_id),
        "reviews": reviews_path(catalogue_id),
        "media": media_path(catalogue_id, path=item_path),
        "grading_list": grading_path(),
    }[kind]
    allowed_id = catalogue_id if kind != "grading_list" else catalogue_id or ""
    if not href_allowed(href, allowed_id):
        return []
    return [_action(label, href)]


def href_allowed(href: str, catalogue_id: str) -> bool:
    if not href or href.startswith("//") or "://" in href or "\\" in href:
        return False
    parsed = urlparse(href)
    if parsed.scheme or parsed.netloc:
        return False
    prefix = f"/catalogues/{catalogue_id}"
    if parsed.path == "/grading":
        return not parsed.query
    if catalogue_id and parsed.path == f"/grading/{catalogue_id}":
        query = parse_qs(parsed.query, keep_blank_values=True)
        return all(key in {"tab"} for key in query)
    if not catalogue_id:
        return False
    if parsed.path != prefix and not parsed.path.startswith(prefix + "/"):
        return False
    rest = parsed.path[len(prefix) :]
    if rest not in {"", "/improvements", "/reviews", "/media", "/assistant"}:
        return False
    query = parse_qs(parsed.query, keep_blank_values=True)
    allowed_keys = {"path", "proposal_id", "check_id"}
    if any(key not in allowed_keys for key in query):
        return False
    if "path" in query and rest != "/media":
        return False
    return True


def _action(label: str, href: str) -> AssistantAction:
    return AssistantAction(label=label, href=href)

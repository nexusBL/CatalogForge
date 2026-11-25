"""Single-turn Baba AI orchestration. Read-only. Authz happens before this is called."""

from __future__ import annotations

from backend.assistant.context import apply_page_context, bind_request_catalogue, parse_page_context
from backend.assistant.contract import (
    AssistantIntent,
    AssistantTurnRequest,
    AssistantTurnResponse,
    PlannerOutput,
)
from backend.assistant.explain import explain_turn
from backend.assistant.links import actions_for_intent
from backend.assistant.planner import PLANNER_UNAVAILABLE, PlannerRejected, intent_default_tool, plan_message
from backend.assistant.router import looks_like_item_question, route_intent
from backend.assistant.tools import (
    ToolLimitExceeded,
    ToolRejected,
    TurnCache,
    execute_tool,
    resolve_item,
    resolve_item_in_message,
)
from backend.store import get_catalogue
from backend.improvement.nl import maybe_handle_quality_improve
from backend.mutation.service import maybe_handle_turn

NOT_FOUND = "Catalogue not found for this restaurant organization."

_ORG_INTENTS = frozenset({"explain_org_grades", "refuse_mutation", "clarify", "unsupported"})


class AssistantCatalogueMissing(LookupError):
    pass


def run_turn(
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str | None,
    request: AssistantTurnRequest,
) -> AssistantTurnResponse:
    route = request.context.current_route if request.context is not None else None
    page = bind_request_catalogue(parse_page_context(route), catalogue_id)
    stored = None
    if catalogue_id:
        stored = get_catalogue(user_id, catalogue_id, organization_id)
        if stored is None:
            raise AssistantCatalogueMissing(NOT_FOUND)
    cache = TurnCache(
        user_id=user_id,
        organization_id=organization_id,
        catalogue_id=catalogue_id or "",
        stored=stored,
    )
    handled = maybe_handle_turn(
        user_id=user_id,
        organization_id=organization_id,
        catalogue_id=catalogue_id,
        message=request.message,
    )
    if handled is not None:
        return handled
    quality = maybe_handle_quality_improve(
        user_id=user_id,
        organization_id=organization_id,
        catalogue_id=catalogue_id,
        message=request.message,
    )
    if quality is not None:
        return quality
    used_llm = False
    item_name: str | None = None
    intent = apply_page_context(route_intent(request.message), request.message, page)
    if stored is not None and intent is None:
        linkage = resolve_item_in_message(cache, request.message)
        if linkage is not None and linkage.status == "ambiguous" and looks_like_item_question(request.message):
            intent = "clarify"
            item_name = linkage.item_name
        elif (
            linkage is not None
            and linkage.status in {"exact", "normalized"}
            and looks_like_item_question(request.message)
        ):
            intent = "explain_item_findings"
            item_name = linkage.item_name
    if stored is not None and intent == "open_media" and item_name is None:
        linkage = resolve_item_in_message(cache, request.message)
        if linkage is not None and linkage.status == "ambiguous":
            intent = "clarify"
            item_name = linkage.item_name
        elif linkage is not None and linkage.status in {"exact", "normalized"}:
            item_name = linkage.item_name
    if intent is None:
        used_llm = True
        try:
            planned = plan_message(request.message)
        except PlannerRejected:
            return AssistantTurnResponse(
                message=PLANNER_UNAVAILABLE,
                intent="unsupported",
                used_llm=True,
                actions=actions_for_intent("unsupported", cache.catalogue_id),
                unavailable=PLANNER_UNAVAILABLE,
            )
        intent, item_name = _from_planner(planned, cache)
        if intent == "propose_mutation":
            intent = "clarify"
            item_name = None
        if intent is None:
            return AssistantTurnResponse(
                message=PLANNER_UNAVAILABLE,
                intent="unsupported",
                used_llm=True,
                actions=actions_for_intent("unsupported", cache.catalogue_id),
                unavailable=PLANNER_UNAVAILABLE,
            )
    if not cache.catalogue_id and intent not in _ORG_INTENTS:
        intent = "clarify"
        item_name = None
    return _respond(
        cache,
        intent=intent,
        item_name=item_name,
        used_llm=used_llm,
        message=request.message,
    )


def _from_planner(planned: PlannerOutput, cache: TurnCache) -> tuple[AssistantIntent | None, str | None]:
    expected = intent_default_tool(planned.intent)
    if planned.tool is not None and expected is not None and planned.tool != expected:
        return None, None
    item_name = planned.item_name
    if planned.intent == "explain_item_findings":
        if not item_name:
            return "clarify", None
        if cache.stored is None:
            return "clarify", None
        linkage = resolve_item(cache, item_name)
        if linkage is not None and linkage.status == "ambiguous":
            return "clarify", item_name
    return planned.intent, item_name


def _respond(
    cache: TurnCache,
    *,
    intent: AssistantIntent,
    item_name: str | None,
    used_llm: bool,
    message: str,
) -> AssistantTurnResponse:
    if intent in {"refuse_mutation", "clarify", "unsupported", "open_catalogue"}:
        facts: dict = {"needs_venue": not cache.catalogue_id}
        text, unavailable = explain_turn(intent, facts, item_name=item_name)
        return AssistantTurnResponse(
            message=text,
            intent=intent,
            used_llm=used_llm,
            actions=actions_for_intent(intent, cache.catalogue_id),
            unavailable=unavailable,
        )
    try:
        facts, resolved_path, check_id, item_name = _run_tools(cache, intent, item_name, message)
    except ToolRejected:
        return AssistantTurnResponse(
            message=PLANNER_UNAVAILABLE,
            intent="unsupported",
            used_llm=used_llm,
            actions=actions_for_intent("unsupported", cache.catalogue_id),
            unavailable=PLANNER_UNAVAILABLE,
        )
    except ToolLimitExceeded:
        return AssistantTurnResponse(
            message=PLANNER_UNAVAILABLE,
            intent=intent,
            used_llm=used_llm,
            actions=actions_for_intent(intent, cache.catalogue_id),
            unavailable=PLANNER_UNAVAILABLE,
        )
    text, unavailable = explain_turn(intent, facts, item_name=item_name)
    action_intent: AssistantIntent = intent
    if intent == "explain_item_findings" and facts.get("linkage") == "ambiguous":
        action_intent = "clarify"
        resolved_path = None
    media_path = resolved_path if facts.get("linkage") in {None, "exact", "normalized"} else None
    if action_intent == "open_media" and facts.get("linkage") not in {None, "exact", "normalized"}:
        media_path = None
    venues = facts.get("venues") if intent == "explain_org_grades" else None
    actions = actions_for_intent(
        action_intent,
        cache.catalogue_id,
        item_path=media_path,
        check_id=check_id,
        venues=venues,
    )
    return AssistantTurnResponse(
        message=text,
        intent=action_intent,
        used_llm=used_llm,
        actions=actions,
        unavailable=unavailable,
    )


def _run_tools(
    cache: TurnCache,
    intent: AssistantIntent,
    item_name: str | None,
    message: str,
) -> tuple[dict, str | None, str | None, str | None]:
    path = None
    if intent == "open_media":
        linkage = resolve_item(cache, item_name) if item_name else resolve_item_in_message(cache, message)
        if linkage is None:
            return {}, None, None, item_name
        facts = {"linkage": linkage.status, "item_name": linkage.item_name or item_name}
        if linkage.status in {"exact", "normalized"}:
            path = linkage.path
            item_name = linkage.item_name or item_name
        return facts, path, None, item_name
    tool = intent_default_tool(intent)
    if tool is None:
        return {}, None, None, item_name
    payload = execute_tool(tool, cache, item_name=item_name)
    check_id = payload.get("fix_first_check_id")
    if payload.get("path") and payload.get("linkage") in {"exact", "normalized"}:
        path = payload.get("path")
        item_name = payload.get("item_name") or item_name
    if intent == "explain_items_attention" and cache.tool_count < 3:
        intel = execute_tool("get_review_intelligence", cache)
        payload = {**payload, "intel": intel}
    return payload, path, check_id, item_name

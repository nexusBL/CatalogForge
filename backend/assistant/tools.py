"""Read-only allowlisted tools. Map to existing services. No new engines."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.assistant.contract import (
    ALLOWED_TOOLS,
    MAX_FINDINGS,
    MAX_OBSERVATIONS,
    MAX_TEXT_CHARS,
    MAX_TOOLS_PER_TURN,
    AssistantToolName,
)
from backend.canonical.adapter import to_canonical_from_response
from backend.grade_explain.contract import GradeExplanation
from backend.improvement.contract import ImprovementProposal
from backend.improvement.service import list_improvements
from backend.platform_eval.baba_score import load_baba_score
from backend.platform_eval.contract import BabaScore
from backend.review_intel.contract import CatalogueItemRef, ReviewIntelligence, ReviewLinkage
from backend.review_intel.link import catalogue_item_refs, link_review_text, normalize_item_name
from backend.schemas import StoredCatalogue
from backend.services.grade_explain_service import IncompleteGradePayload, get_grade_explanation


class ToolLimitExceeded(RuntimeError):
    pass


class ToolRejected(ValueError):
    pass


@dataclass
class TurnCache:
    user_id: str
    organization_id: str
    catalogue_id: str
    stored: StoredCatalogue | None
    tool_count: int = 0
    _explanation: GradeExplanation | None = None
    _explanation_loaded: bool = False
    _explanation_error: str | None = None
    _score: BabaScore | None = None
    _score_loaded: bool = False
    _intel: ReviewIntelligence | None = None
    _intel_loaded: bool = False
    _proposals: list[ImprovementProposal] | None = None
    _item_refs: list[CatalogueItemRef] | None = None


def clip(value: str | None, limit: int = MAX_TEXT_CHARS) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if len(text) <= limit:
        return text
    return text[: limit].rstrip() + "…"


def item_refs(cache: TurnCache) -> list[CatalogueItemRef]:
    if cache.stored is None:
        return []
    if cache._item_refs is None:
        document = to_canonical_from_response(cache.stored.result)
        cache._item_refs = catalogue_item_refs(document)
    return cache._item_refs


def resolve_item(cache: TurnCache, item_name: str | None) -> ReviewLinkage | None:
    if not item_name or not item_name.strip():
        return None
    hits = link_review_text(item_name.strip(), item_refs(cache))
    if not hits:
        return ReviewLinkage(status="no_match")
    ambiguous = [row for row in hits if row.status == "ambiguous"]
    if ambiguous:
        return ambiguous[0]
    matched = [row for row in hits if row.status in {"exact", "normalized"}]
    if len(matched) > 1:
        ids = {row.item_id for row in matched}
        if len(ids) > 1:
            return ReviewLinkage(
                status="ambiguous",
                item_name=matched[0].item_name,
                candidate_item_ids=[row.item_id or "" for row in matched if row.item_id],
            )
    if matched:
        return matched[0]
    return hits[0]


def resolve_item_in_message(cache: TurnCache, message: str) -> ReviewLinkage | None:
    hits = link_review_text(message, item_refs(cache))
    matched = [row for row in hits if row.status in {"exact", "normalized", "ambiguous"}]
    if not matched:
        return None
    if any(row.status == "ambiguous" for row in matched):
        return next(row for row in matched if row.status == "ambiguous")
    names = {normalize_item_name(row.item_name) for row in matched}
    ids = {row.item_id for row in matched if row.item_id}
    if len(names) > 1 or len(ids) > 1:
        return ReviewLinkage(status="ambiguous")
    return matched[0]


def execute_tool(name: str, cache: TurnCache, *, item_name: str | None = None) -> dict[str, Any]:
    if name not in ALLOWED_TOOLS:
        raise ToolRejected("unknown tool")
    if cache.tool_count >= MAX_TOOLS_PER_TURN:
        raise ToolLimitExceeded("tool limit")
    cache.tool_count += 1
    tool: AssistantToolName = name  # type: ignore[assignment]
    if tool == "get_catalogue_summary":
        return _catalogue_summary(cache)
    if tool == "get_grade_explanation":
        return _explanation_payload(cache)
    if tool == "get_baba_score":
        return _score_payload(cache)
    if tool == "get_review_intelligence":
        return _intel_payload(cache)
    if tool == "list_improvement_proposals":
        return _proposals_payload(cache)
    if tool == "list_org_grade_summaries":
        return _org_grade_summaries(cache)
    return _item_context_payload(cache, item_name)


def explanation(cache: TurnCache) -> GradeExplanation | None:
    _load_explanation(cache)
    return cache._explanation if isinstance(cache._explanation, GradeExplanation) else None


def intelligence(cache: TurnCache) -> ReviewIntelligence | None:
    _load_intel(cache)
    return cache._intel


def _load_explanation(cache: TurnCache) -> None:
    if cache._explanation_loaded:
        return
    cache._explanation_loaded = True
    try:
        cache._explanation = get_grade_explanation(
            user_id=cache.user_id,
            organization_id=cache.organization_id,
            catalogue_id=cache.catalogue_id,
        )
    except IncompleteGradePayload:
        cache._explanation = None
        cache._explanation_error = "Grade explanation could not be completed."
    except KeyError:
        raise


def _load_score(cache: TurnCache) -> None:
    if cache._score_loaded:
        return
    cache._score_loaded = True
    cache._score = load_baba_score(
        user_id=cache.user_id,
        organization_id=cache.organization_id,
        catalogue_id=cache.catalogue_id,
    )


def _load_intel(cache: TurnCache) -> None:
    if cache._intel_loaded:
        return
    cache._intel_loaded = True
    from backend.review_intel.service import get_review_intelligence

    cache._intel = get_review_intelligence(
        user_id=cache.user_id,
        organization_id=cache.organization_id,
        catalogue_id=cache.catalogue_id,
    )


def _load_proposals(cache: TurnCache) -> None:
    if cache._proposals is not None:
        return
    cache._proposals = list_improvements(
        user_id=cache.user_id,
        organization_id=cache.organization_id,
        catalogue_id=cache.catalogue_id,
    )


def _catalogue_summary(cache: TurnCache) -> dict[str, Any]:
    if cache.stored is None:
        return {"kind": "catalogue_summary", "missing": True}
    result = cache.stored.result
    categories = getattr(result, "categories", None) or []

    cat_summaries = []
    items_list = []
    missing_desc = []
    missing_img = []
    missing_tags = []

    for category in categories:
        if isinstance(category, dict):
            c_name = str(category.get("name") or "")
            c_items = category.get("items") or []
        else:
            c_name = str(getattr(category, "name", ""))
            c_items = getattr(category, "items", []) or []

        if callable(c_items):
            c_items = []

        cat_summaries.append({"name": c_name, "count": len(c_items)})
        for item in c_items:
            if isinstance(item, dict):
                i_name = str(item.get("name") or "")
                i_price = item.get("price")
                i_desc = item.get("description")
                i_img = item.get("image_url")
                i_labels = item.get("labels") or []
            else:
                i_name = str(getattr(item, "name", ""))
                i_price = getattr(item, "price", None)
                i_desc = getattr(item, "description", None)
                i_img = getattr(item, "image_url", None)
                i_labels = getattr(item, "labels", []) or []

            has_desc = bool(i_desc and str(i_desc).strip())
            has_img = bool(i_img and str(i_img).strip())
            has_tags = bool(i_labels and len(i_labels) > 0)

            items_list.append(
                {
                    "name": i_name,
                    "category": c_name,
                    "price": i_price,
                    "has_desc": has_desc,
                    "has_img": has_img,
                    "has_tags": has_tags,
                    "labels": i_labels,
                }
            )
            if not has_desc and i_name:
                missing_desc.append(i_name)
            if not has_img and i_name:
                missing_img.append(i_name)
            if not has_tags and i_name:
                missing_tags.append(i_name)

    cat_summaries.sort(key=lambda x: x["count"], reverse=True)
    largest_category = cat_summaries[0] if cat_summaries else None

    priced_items = [i for i in items_list if isinstance(i["price"], (int, float))]
    most_expensive = max(priced_items, key=lambda x: x["price"]) if priced_items else None
    cheapest = min(priced_items, key=lambda x: x["price"]) if priced_items else None

    return {
        "kind": "catalogue_summary",
        "restaurant_name": result.restaurant_name,
        "platform": result.platform,
        "catalogue_type": result.catalogue_type,
        "item_count": result.item_count or len(items_list),
        "extraction_status": result.extraction_status,
        "categories": cat_summaries,
        "category_count": len(cat_summaries),
        "largest_category": largest_category,
        "missing_descriptions": missing_desc,
        "missing_images": missing_img,
        "missing_tags": missing_tags,
        "most_expensive": most_expensive,
        "cheapest": cheapest,
        "items": items_list,
    }


def _find_item_data(cache: TurnCache, path: str | None, name: str | None) -> dict[str, Any]:
    if cache.stored is None:
        return {}
    result = cache.stored.result
    categories = getattr(result, "categories", None) or []
    for c in categories:
        if isinstance(c, dict):
            c_name = str(c.get("name") or "")
            c_items = c.get("items") or []
        else:
            c_name = str(getattr(c, "name", ""))
            c_items = getattr(c, "items", []) or []

        if callable(c_items):
            c_items = []

        for item in c_items:
            if isinstance(item, dict):
                i_name = str(item.get("name") or "")
                i_price = item.get("price")
                i_desc = item.get("description")
                i_img = item.get("image_url")
                i_labels = item.get("labels") or []
                i_food = item.get("food_type")
            else:
                i_name = str(getattr(item, "name", ""))
                i_price = getattr(item, "price", None)
                i_desc = getattr(item, "description", None)
                i_img = getattr(item, "image_url", None)
                i_labels = getattr(item, "labels", []) or []
                i_food = getattr(item, "food_type", None)

            if name and i_name.casefold() == name.casefold():
                return {
                    "price": i_price,
                    "category": c_name,
                    "description": i_desc,
                    "image_url": i_img,
                    "labels": i_labels,
                    "food_type": i_food,
                }
    return {}


def _explanation_payload(cache: TurnCache) -> dict[str, Any]:
    _load_explanation(cache)
    if cache._explanation_error:
        return {"kind": "grade_explanation", "unavailable": cache._explanation_error}
    row = cache._explanation
    if not isinstance(row, GradeExplanation):
        return {"kind": "grade_explanation", "missing": True}
    findings = []
    for finding in row.findings[:MAX_FINDINGS]:
        names = _item_names_for_paths(cache, finding.evidence.paths)
        findings.append(
            {
                "check_id": finding.check_id,
                "why": clip(finding.why),
                "affected_count": finding.evidence.affected_count,
                "paths": finding.evidence.paths[:8],
                "item_names": names,
                "measured_value": finding.evidence.measured_value,
            }
        )
    fix = row.fix_first
    return {
        "kind": "grade_explanation",
        "overall_grade": row.overall_grade,
        "overall_score": row.overall_score,
        "overall_why": clip(row.overall_why),
        "fix_first": clip(fix.action) if fix else None,
        "fix_first_check_id": fix.check_id if fix else None,
        "section_grades": [
            {"section": section.section, "label": section.label, "letter": section.letter, "score": section.score}
            for section in row.section_grades
        ],
        "findings": findings,
        "venue_name": cache.stored.result.restaurant_name if cache.stored is not None else None,
        "catalogue_type": cache.stored.result.catalogue_type if cache.stored is not None else None,
    }


def _score_payload(cache: TurnCache) -> dict[str, Any]:
    _load_score(cache)
    if cache._score is None:
        return {"kind": "baba_score", "missing": True}
    return {
        "kind": "baba_score",
        "letter": cache._score.letter,
        "score": cache._score.score,
        "independent_of_platform": True,
    }


def _intel_payload(cache: TurnCache) -> dict[str, Any]:
    _load_intel(cache)
    row = cache._intel
    if row is None:
        return {"kind": "review_intelligence", "missing": True}
    stale = row.status == "STALE"
    observations = sorted(
        row.observations,
        key=lambda obs: (0 if obs.recurrence_status == "recurring_complaint" else 1, -obs.review_count),
    )[:MAX_OBSERVATIONS]
    bounded = []
    for obs in observations:
        bounded.append(
            {
                "item_name": obs.item_name,
                "target": obs.target,
                "polarity": obs.polarity,
                "recurrence_status": obs.recurrence_status,
                "review_count": obs.review_count,
                "aspect": obs.aspect,
                "intent": obs.intent,
            }
        )
    recs = [clip(item.action) for item in row.recommendations[:MAX_OBSERVATIONS] if item.action]
    return {
        "kind": "review_intelligence",
        "status": row.status,
        "stale": stale,
        "review_count": row.review_count,
        "observations": bounded,
        "recommendation_actions": recs,
    }


def _proposals_payload(cache: TurnCache) -> dict[str, Any]:
    _load_proposals(cache)
    proposals = cache._proposals or []
    return {
        "kind": "improvement_proposals",
        "count": len(proposals),
        "statuses": [row.status for row in proposals[:MAX_FINDINGS]],
    }


def _find_item_data(cache: TurnCache, path: str | None, name: str | None) -> dict[str, Any]:
    if cache.stored is None:
        return {}
    result = cache.stored.result
    categories = getattr(result, "categories", None) or []
    for c in categories:
        if isinstance(c, dict):
            c_name = str(c.get("name") or "")
            c_items = c.get("items") or []
        else:
            c_name = str(getattr(c, "name", ""))
            c_items = getattr(c, "items", []) or []

        if callable(c_items):
            c_items = []

        for item in c_items:
            if isinstance(item, dict):
                i_name = str(item.get("name") or "")
                i_price = item.get("price")
                i_desc = item.get("description")
                i_img = item.get("image_url")
                i_labels = item.get("labels") or []
                i_food = item.get("food_type")
            else:
                i_name = str(getattr(item, "name", ""))
                i_price = getattr(item, "price", None)
                i_desc = getattr(item, "description", None)
                i_img = getattr(item, "image_url", None)
                i_labels = getattr(item, "labels", []) or []
                i_food = getattr(item, "food_type", None)

            if name and i_name.casefold() == name.casefold():
                return {
                    "price": i_price,
                    "category": c_name,
                    "description": i_desc,
                    "image_url": i_img,
                    "labels": i_labels,
                    "food_type": i_food,
                }
    return {}


def _item_context_payload(cache: TurnCache, item_name: str | None) -> dict[str, Any]:
    linkage = resolve_item(cache, item_name)
    if linkage is None or linkage.status == "no_match":
        return {"kind": "item_context", "linkage": "no_match", "item_name": item_name}
    if linkage.status == "ambiguous":
        return {"kind": "item_context", "linkage": "ambiguous", "item_name": linkage.item_name or item_name}
    path = linkage.path
    explanation_row = _explanation_payload(cache)
    intel_row = _intel_payload(cache)
    item_findings = []
    if explanation_row.get("findings") and path:
        for finding in explanation_row["findings"]:
            paths = finding.get("paths") or []
            if any(path in entry for entry in paths):
                item_findings.append({"check_id": finding["check_id"], "why": finding["why"]})
    item_obs = []
    if intel_row.get("observations"):
        for obs in intel_row["observations"]:
            if obs.get("item_name") and normalize_item_name(obs["item_name"]) == normalize_item_name(
                linkage.item_name or item_name or ""
            ):
                item_obs.append(obs)

    matched_name = linkage.item_name or item_name
    item_data = _find_item_data(cache, path, matched_name)

    return {
        "kind": "item_context",
        "linkage": linkage.status,
        "item_name": matched_name,
        "path": path,
        "item_id": linkage.item_id,
        "price": item_data.get("price"),
        "category": item_data.get("category"),
        "description": item_data.get("description"),
        "has_description": bool(item_data.get("description") and str(item_data.get("description")).strip()),
        "image_url": item_data.get("image_url"),
        "has_image": bool(item_data.get("image_url") and str(item_data.get("image_url")).strip()),
        "labels": item_data.get("labels") or [],
        "has_tags": bool(item_data.get("labels") and len(item_data.get("labels")) > 0),
        "catalogue_grade": explanation_row.get("overall_grade"),
        "catalogue_why": explanation_row.get("overall_why"),
        "grade_missing": bool(explanation_row.get("missing")),
        "findings": item_findings[:MAX_FINDINGS],
        "review_observations": item_obs[:MAX_OBSERVATIONS],
        "intel_stale": bool(intel_row.get("stale")),
        "intel_missing": bool(intel_row.get("missing")),
    }


def _item_names_for_paths(cache: TurnCache, paths: list[str]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    refs = item_refs(cache)
    for path in paths:
        match = next((row.name for row in refs if row.path and (path == row.path or path.startswith(row.path + ".") or row.path in path)), None)
        if match and match not in seen:
            seen.add(match)
            names.append(match)
        if len(names) >= 8:
            break
    return names


def _org_grade_summaries(cache: TurnCache) -> dict[str, Any]:
    from backend.store import list_catalogues

    venues: list[dict[str, Any]] = []
    for stored in list_catalogues(cache.user_id, cache.organization_id)[:20]:
        name = stored.result.restaurant_name
        kind = stored.result.catalogue_type
        try:
            explanation = get_grade_explanation(
                user_id=cache.user_id,
                organization_id=cache.organization_id,
                catalogue_id=stored.id,
            )
        except IncompleteGradePayload:
            venues.append(
                {
                    "catalogue_id": stored.id,
                    "name": name,
                    "catalogue_type": kind,
                    "graded": False,
                }
            )
            continue
        if explanation is None:
            venues.append(
                {
                    "catalogue_id": stored.id,
                    "name": name,
                    "catalogue_type": kind,
                    "graded": False,
                }
            )
            continue
        venues.append(
            {
                "catalogue_id": stored.id,
                "name": name,
                "catalogue_type": kind,
                "graded": True,
                "overall_grade": explanation.overall_grade,
                "overall_score": explanation.overall_score,
            }
        )
    return {"kind": "org_grade_summaries", "venues": venues}

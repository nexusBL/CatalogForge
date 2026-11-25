"""Build a Phase 5 explanation from a persisted grading.v1 result.

Read-time projection only. Overall letter and score are copied from the
grade row. Section letters use ``letter_for_score`` on the stored stage
scores (same frozen floors as grading.v1). Findings come from stored
evidence items. No new grading engine.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from backend.grade_explain.contract import (
    EXPLANATION_VERSION,
    SECTION_LABELS,
    SECTION_ORDER,
    Finding,
    FindingEvidence,
    GradeExplanation,
    Recommendation,
    SectionGrade,
    SectionId,
)
from backend.grade_explain.recommend import (
    is_actionable,
    priority_rule,
    priority_sort_key,
    recommendation_action,
)
from backend.grading.contract import ENGINE_VERSION, EvidenceItem, GradingResult
from backend.grading.formula import letter_for_score, stage_score_is_unit


class IncompleteGradePayload(ValueError):
    """Stored grade is missing section scores required for an honest explanation."""


def explain_grade(result: GradingResult) -> GradeExplanation:
    engine = str(result.grading_metadata.get("engine_version") or ENGINE_VERSION)
    sections = _section_grades(result)
    grouped = _group_actionable(result)
    findings = [_finding_from_group(section, check_id, items) for section, check_id, items in grouped]
    ordered = sorted(
        findings,
        key=lambda finding: priority_sort_key(
            severity=finding.severity,
            section=finding.section,
            affected_count=finding.evidence.affected_count,
            check_id=finding.check_id,
        ),
    )
    recommendations: list[Recommendation] = []
    numbered: list[Finding] = []
    for index, finding in enumerate(ordered, start=1):
        rec = finding.recommendation
        if rec is None:
            numbered.append(finding)
            continue
        rec = rec.model_copy(update={"priority": index})
        numbered.append(finding.model_copy(update={"recommendation": rec}))
        recommendations.append(rec)
    return GradeExplanation(
        catalogue_id=result.catalogue_id,
        graded_head_revision=result.graded_head_revision,
        graded_state_hash=result.graded_state_hash,
        engine_version=engine,
        explanation_version=EXPLANATION_VERSION,
        overall_grade=result.grade,
        overall_score=result.score,
        overall_why=_overall_why(result, recommendations),
        section_grades=sections,
        findings=numbered,
        recommendations=recommendations,
        fix_first=recommendations[0] if recommendations else None,
        priority_rule=priority_rule(),
        derived=True,
    )


def _section_grades(result: GradingResult) -> list[SectionGrade]:
    missing = [section for section in SECTION_ORDER if section not in result.signals]
    if missing:
        raise IncompleteGradePayload(f"Grade payload is missing section scores: {', '.join(missing)}")
    grades: list[SectionGrade] = []
    for section in SECTION_ORDER:
        raw = result.signals[section]
        try:
            score = float(raw)
        except (TypeError, ValueError) as exc:
            raise IncompleteGradePayload(f"Grade payload has a non-numeric {section} score.") from exc
        if not stage_score_is_unit(score):
            raise IncompleteGradePayload(
                f"Grade payload has an out-of-range {section} score; grading.v1 stage scores are 0–100."
            )
        grades.append(
            SectionGrade(
                section=section,
                label=SECTION_LABELS[section],
                letter=letter_for_score(score),
                score=score,
            )
        )
    return grades


def _iter_section_evidence(result: GradingResult) -> list[tuple[SectionId, EvidenceItem]]:
    rows: list[tuple[SectionId, EvidenceItem]] = []
    for item in result.deterministic_evidence:
        rows.append(("deterministic", item))
    for item in result.nlp_evidence:
        rows.append(("nlp", item))
    for item in result.vision_evidence:
        rows.append(("vision", item))
    return rows


def _group_actionable(result: GradingResult) -> list[tuple[SectionId, str, list[EvidenceItem]]]:
    buckets: dict[tuple[SectionId, str], list[EvidenceItem]] = defaultdict(list)
    for section, item in _iter_section_evidence(result):
        if not is_actionable(item):
            continue
        buckets[(section, item.check_id)].append(item)
    grouped = [(section, check_id, items) for (section, check_id), items in buckets.items()]
    grouped.sort(key=lambda row: (row[0], row[1]))
    return grouped


def _finding_from_group(section: SectionId, check_id: str, items: list[EvidenceItem]) -> Finding:
    finding_id = f"{section}:{check_id}"
    paths = sorted({item.path for item in items if item.path})
    details = _merge_details(items)
    affected = _affected_count(items, details, paths)
    why = _why(check_id, items, affected, details)
    evidence = FindingEvidence(
        failed_criterion=check_id,
        affected_count=affected,
        affected_field=_affected_field(paths, items),
        measured_value=_measured_value(details),
        paths=paths,
        details=details,
    )
    severity = _worst_severity(items)
    result_value = _worst_result(items)
    action = recommendation_action(
        check_id=check_id,
        affected_count=affected,
        details=details,
        explanation=why,
    )
    recommendation = Recommendation(
        finding_id=finding_id,
        priority=0,
        action=action,
        section=section,
        check_id=check_id,
        severity=severity,
    )
    return Finding(
        finding_id=finding_id,
        section=section,
        check_id=check_id,
        severity=severity,
        result=result_value,
        why=why,
        evidence=evidence,
        recommendation=recommendation,
    )


def _affected_count(items: list[EvidenceItem], details: dict[str, Any], paths: list[str]) -> int:
    if "item_total" in details and "described" in details:
        try:
            missing = int(details["item_total"]) - int(details["described"])
            return max(missing, 1)
        except (TypeError, ValueError):
            pass
    if paths:
        return len(paths)
    return max(1, len(items))


def _affected_field(paths: list[str], items: list[EvidenceItem]) -> str | None:
    if paths:
        suffixes = sorted({path.rsplit(".", 1)[-1] for path in paths})
        if len(suffixes) == 1:
            return suffixes[0]
        return ", ".join(suffixes)
    first = items[0].path
    return first.rsplit(".", 1)[-1] if first else None


def _measured_value(details: dict[str, Any]) -> Any | None:
    for key in ("coverage", "extraction_status", "declared", "actual", "value", "repeated_count"):
        if key in details:
            return details[key]
    return None


def _merge_details(items: list[EvidenceItem]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for item in items:
        for key, value in item.details.items():
            if key not in merged:
                merged[key] = value
                continue
            if merged[key] == value:
                continue
            existing = merged[key]
            if isinstance(existing, list):
                if value not in existing:
                    existing.append(value)
            else:
                merged[key] = [existing, value]
    return merged


def _why(check_id: str, items: list[EvidenceItem], affected: int, details: dict[str, Any]) -> str:
    texts = []
    seen: set[str] = set()
    for item in items:
        text = (item.explanation or "").strip()
        if text and text not in seen:
            seen.add(text)
            texts.append(text)
    if not texts:
        base = f"Check {check_id} failed."
    else:
        base = " ".join(texts)
    if check_id == "description_coverage" and "described" in details and "item_total" in details:
        return (
            f"{base} {details['described']} of {details['item_total']} items have a description "
            f"(coverage {details.get('coverage')})."
        )
    if check_id == "repeated_description" and details.get("repeated_count") is not None:
        return f"{base} Repeated values: {details['repeated_count']}."
    if affected > 1:
        return f"{base} Affected count: {affected}."
    return base


def _worst_severity(items: list[EvidenceItem]):
    rank = {"hard": 0, "ordinary": 1, "info": 2}
    return min((item.severity for item in items), key=lambda value: rank.get(value, 9))


def _worst_result(items: list[EvidenceItem]):
    rank = {"error": 0, "fail": 1, "skip": 2, "pass": 3}
    return min((item.result for item in items), key=lambda value: rank.get(value, 9))


def _overall_why(result: GradingResult, recommendations: list[Recommendation]) -> str:
    hard_ids = [
        item.check_id
        for item in result.hard_failures
        if item.check_id != "hard_failure_forces_f"
    ]
    forced = next((item for item in result.hard_failures if item.check_id == "hard_failure_forces_f"), None)
    prefix = (
        f"Overall grade {result.grade} (score {result.score}) from persisted grading.v1. "
        "The letter is not recalculated by Phase 5."
    )
    if forced is not None:
        ids = ", ".join(hard_ids) if hard_ids else "recorded hard failure"
        return f"{prefix} {forced.explanation} Originating checks: {ids}."
    if result.hard_failures:
        ids = ", ".join(item.check_id for item in result.hard_failures)
        return f"{prefix} Hard failures force F. Originating checks: {ids}."
    if recommendations:
        first = recommendations[0]
        return (
            f"{prefix} Highest-priority fix is {first.check_id} "
            f"({first.section}, severity {first.severity})."
        )
    return f"{prefix} No failing evidence was recorded for this revision."

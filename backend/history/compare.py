"""Before/after grade comparison from stored grading.v1 / grade_explain.v1."""

from __future__ import annotations

from backend.grade_explain.contract import GradeExplanation
from backend.grading.contract import GradingResult
from backend.history.contract import GradeSnapshot
from backend.services.grade_explain_service import IncompleteGradePayload, get_grade_explanation
from backend.services.grading_service import get_catalogue_grade, grade_catalogue


def _letter(grade: GradingResult | None, explanation: GradeExplanation | None) -> str | None:
    if explanation is not None:
        return explanation.overall_grade
    if grade is None:
        return None
    value = getattr(grade, "grade", None) or getattr(grade, "letter", None)
    return str(value) if value is not None else None


def _score(grade: GradingResult | None, explanation: GradeExplanation | None) -> float | None:
    if explanation is not None:
        return float(explanation.overall_score)
    if grade is None:
        return None
    value = getattr(grade, "score", None)
    return float(value) if isinstance(value, (int, float)) else None


def snapshot_from(grade: GradingResult | None, explanation: GradeExplanation | None) -> GradeSnapshot:
    finding_ids: list[str] = []
    check_ids: list[str] = []
    section_scores: dict[str, float] = {}
    if explanation is not None:
        section_scores = {row.section: float(row.score) for row in explanation.section_grades}
        for finding in explanation.findings:
            if finding.result not in {"fail", "error"}:
                continue
            finding_ids.append(finding.finding_id)
            check_ids.append(finding.check_id)
    return GradeSnapshot(
        letter=_letter(grade, explanation),
        score=_score(grade, explanation),
        section_scores=section_scores,
        finding_ids=finding_ids,
        check_ids=check_ids,
    )


def load_snapshot(*, user_id: str, organization_id: str, catalogue_id: str) -> GradeSnapshot:
    grade = None
    explanation = None
    try:
        grade = get_catalogue_grade(user_id=user_id, organization_id=organization_id, catalogue_id=catalogue_id)
    except Exception:
        grade = None
    if grade is not None:
        try:
            explanation = get_grade_explanation(
                user_id=user_id,
                organization_id=organization_id,
                catalogue_id=catalogue_id,
            )
        except (IncompleteGradePayload, Exception):
            explanation = None
    return snapshot_from(grade, explanation)


def regrade_snapshot(*, user_id: str, organization_id: str, catalogue_id: str) -> tuple[GradingResult | None, GradeSnapshot]:
    graded = None
    try:
        graded = grade_catalogue(user_id=user_id, organization_id=organization_id, catalogue_id=catalogue_id)
    except Exception:
        graded = None
    return graded, load_snapshot(user_id=user_id, organization_id=organization_id, catalogue_id=catalogue_id)


def resolved_issue_ids(before: GradeSnapshot, after: GradeSnapshot) -> list[str]:
    after_findings = set(after.finding_ids)
    after_checks = set(after.check_ids)
    resolved: list[str] = []
    for finding_id in before.finding_ids:
        if finding_id not in after_findings:
            resolved.append(finding_id)
    for check_id in before.check_ids:
        if check_id not in after_checks and check_id not in resolved:
            resolved.append(check_id)
    return resolved


def overall_delta(before: GradeSnapshot, after: GradeSnapshot) -> float | None:
    if before.score is None or after.score is None:
        return None
    return round(float(after.score) - float(before.score), 4)

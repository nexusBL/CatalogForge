"""Phase 5 explanation contract. Downstream of frozen grading.v1."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.grading.contract import EvidenceResult, EvidenceSeverity, GradeLetter

EXPLANATION_VERSION = "grade_explain.v1"

SectionId = Literal["deterministic", "nlp", "vision"]

SECTION_ORDER: tuple[SectionId, ...] = ("deterministic", "nlp", "vision")
SECTION_LABELS: dict[SectionId, str] = {
    "deterministic": "Deterministic",
    "nlp": "Text",
    "vision": "Images",
}

# Reuses Phase 3 EvidenceSeverity. Do not invent a parallel severity scale.
PRIORITY_RULE = (
    "Actionable findings are result=fail or result=error. "
    "Order: severity hard, then ordinary, then info; "
    "then higher grading.v1 stage weight "
    "(deterministic 0.50, nlp 0.25, vision 0.25); "
    "then higher affected_count; "
    "then section id ascending; "
    "then check_id ascending."
)


class SectionGrade(BaseModel):
    section: SectionId
    label: str
    letter: GradeLetter
    score: float


class FindingEvidence(BaseModel):
    failed_criterion: str
    affected_count: int
    affected_field: str | None = None
    measured_value: Any | None = None
    paths: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class Recommendation(BaseModel):
    finding_id: str
    priority: int
    action: str
    section: SectionId
    check_id: str
    severity: EvidenceSeverity


class Finding(BaseModel):
    finding_id: str
    section: SectionId
    check_id: str
    severity: EvidenceSeverity
    result: EvidenceResult
    why: str
    evidence: FindingEvidence
    recommendation: Recommendation | None = None


class GradeExplanation(BaseModel):
    catalogue_id: str
    graded_head_revision: int
    graded_state_hash: str
    engine_version: str
    explanation_version: str = EXPLANATION_VERSION
    overall_grade: GradeLetter
    overall_score: float
    overall_why: str
    section_grades: list[SectionGrade]
    findings: list[Finding]
    recommendations: list[Recommendation]
    fix_first: Recommendation | None = None
    priority_rule: str = PRIORITY_RULE
    derived: Literal[True] = True

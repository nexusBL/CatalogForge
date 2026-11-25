"""Phase 5 grade explanation and recommendations.

Derived at read time from a persisted ``grading.v1`` result. Does not
recompute grades or write new tables.
"""

from backend.grade_explain.contract import (
    EXPLANATION_VERSION,
    Finding,
    FindingEvidence,
    GradeExplanation,
    Recommendation,
    SectionGrade,
)
from backend.grade_explain.explain import IncompleteGradePayload, explain_grade

__all__ = [
    "EXPLANATION_VERSION",
    "Finding",
    "FindingEvidence",
    "GradeExplanation",
    "IncompleteGradePayload",
    "Recommendation",
    "SectionGrade",
    "explain_grade",
]

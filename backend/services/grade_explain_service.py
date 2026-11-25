"""Read-time Phase 5 explanation. Reuses Phase 3 grade load; no extra persist."""

from __future__ import annotations

import json

from pydantic import ValidationError

from backend.grade_explain.contract import GradeExplanation
from backend.grade_explain.explain import IncompleteGradePayload, explain_grade
from backend.services.grading_service import get_catalogue_grade


def get_grade_explanation(
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
) -> GradeExplanation | None:
    try:
        grade = get_catalogue_grade(user_id=user_id, organization_id=organization_id, catalogue_id=catalogue_id)
    except (json.JSONDecodeError, ValidationError, UnicodeDecodeError) as exc:
        raise IncompleteGradePayload("Stored grade payload is not a valid grading.v1 result.") from exc
    if grade is None:
        return None
    try:
        return explain_grade(grade)
    except IncompleteGradePayload:
        raise
    except (ValidationError, TypeError, ValueError) as exc:
        raise IncompleteGradePayload("Grade explanation could not be built from the stored result.") from exc


__all__ = ["IncompleteGradePayload", "get_grade_explanation"]

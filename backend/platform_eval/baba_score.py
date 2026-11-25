"""Baba Score is a labeled projection of grading.v1. Platform scores never enter here."""

from __future__ import annotations

from backend.grading.contract import ENGINE_VERSION, GradingResult
from backend.platform_eval.contract import BabaScore
from backend.services.grading_service import get_catalogue_grade


def baba_score_from_grade(result: GradingResult) -> BabaScore:
    if (result.grading_metadata.get("engine_version") or ENGINE_VERSION) != ENGINE_VERSION:
        raise ValueError("Baba Score projection requires grading.v1")
    return BabaScore(
        catalogue_id=result.catalogue_id,
        graded_head_revision=result.graded_head_revision,
        graded_state_hash=result.graded_state_hash,
        letter=result.grade,
        score=result.score,
    )


def load_baba_score(*, user_id: str, organization_id: str, catalogue_id: str) -> BabaScore | None:
    grade = get_catalogue_grade(user_id=user_id, organization_id=organization_id, catalogue_id=catalogue_id)
    if grade is None:
        return None
    return baba_score_from_grade(grade)

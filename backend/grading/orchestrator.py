"""Coordinate graders, collect evidence, and produce a GradingResult."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from backend.canonical.models import CanonicalDocument
from backend.grading.contract import ENGINE_VERSION, GradingResult
from backend.grading.deterministic import grade_deterministic
from backend.grading.formula import WEIGHTS, aggregate_grade
from backend.grading.nlp import NLPGrader
from backend.grading.vision import VisionGrader

CancelCheck = Callable[[], bool]


class GradingCancelled(RuntimeError):
    pass


class GradingStageFailure(RuntimeError):
    def __init__(self, stage: str, message: str):
        self.stage = stage
        super().__init__(message)


def grade_canonical_document(
    document: CanonicalDocument,
    *,
    catalogue_id: str,
    graded_head_revision: int,
    graded_state_hash: str,
    nlp_grader: NLPGrader | None = None,
    vision_grader: VisionGrader | None = None,
    cancel_check: CancelCheck | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> GradingResult:
    nlp = nlp_grader or NLPGrader()
    vision = vision_grader or VisionGrader()

    def _cancelled() -> None:
        if cancel_check and cancel_check():
            raise GradingCancelled("grading cancelled")

    _cancelled()
    try:
        deterministic = grade_deterministic(document)
    except GradingCancelled:
        raise
    except Exception as exc:
        raise GradingStageFailure("deterministic", str(exc)) from exc

    _cancelled()
    try:
        nlp_signals = nlp.grade(document)
    except GradingCancelled:
        raise
    except Exception as exc:
        raise GradingStageFailure("nlp", str(exc)) from exc

    _cancelled()
    try:
        vision_signals = vision.grade(document, catalogue_id=catalogue_id)
    except GradingCancelled:
        raise
    except Exception as exc:
        raise GradingStageFailure("vision", str(exc)) from exc

    _cancelled()
    if nlp_signals.status != "completed":
        raise GradingStageFailure("nlp", nlp_signals.error or "NLP grading did not complete")
    if vision_signals.status != "completed":
        raise GradingStageFailure("vision", vision_signals.error or "Vision grading did not complete")

    letter, score, hard = aggregate_grade(
        deterministic=deterministic,
        nlp=nlp_signals,
        vision=vision_signals,
    )
    metadata = {
        "engine_version": ENGINE_VERSION,
        "weights": WEIGHTS,
        "graded_at": datetime.now(timezone.utc).isoformat(),
        "formula": "grading.v1 approved product formula; see backend/grading/formula.py",
        **(extra_metadata or {}),
    }
    return GradingResult(
        catalogue_id=catalogue_id,
        graded_head_revision=graded_head_revision,
        graded_state_hash=graded_state_hash,
        grade=letter,
        score=score,
        signals={
            "deterministic": deterministic.score,
            "nlp": nlp_signals.score,
            "vision": vision_signals.score,
            "combined": score,
        },
        hard_failures=hard,
        deterministic_evidence=deterministic.evidence,
        nlp_evidence=nlp_signals.evidence,
        vision_evidence=vision_signals.evidence,
        grading_metadata=metadata,
    )

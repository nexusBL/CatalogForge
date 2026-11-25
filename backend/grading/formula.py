"""A–F aggregation formula.

APPROVED Phase 3 product decision (`grading.v1`). Do not change these numbers
in place. A new ENGINE_VERSION and explicit product approval are required to
change weights or thresholds.

Weights:
    deterministic 0.50
    nlp           0.25
    vision        0.25

Letters (inclusive lower bounds on the combined 0–100 score):
    A >= 90
    B >= 75
    C >= 60
    D >= 40
    F < 40

A hard failure always yields F, regardless of the combined score.
Ordinary quality failures only reduce scores; they never by themselves force F
unless the resulting score is below 40.
"""

from __future__ import annotations

from backend.grading.contract import ENGINE_VERSION, EvidenceItem, GradeLetter, StageSignals

WEIGHTS = {
    "deterministic": 0.50,
    "nlp": 0.25,
    "vision": 0.25,
}

THRESHOLDS: tuple[tuple[float, GradeLetter], ...] = (
    (90.0, "A"),
    (75.0, "B"),
    (60.0, "C"),
    (40.0, "D"),
    (0.0, "F"),
)


def clamp_stage_score(score: float) -> float:
    """grading.v1 stage scores are 0–100. Out-of-range inputs are not extra credit."""
    return max(0.0, min(100.0, float(score)))


def stage_score_is_unit(score: object) -> bool:
    try:
        value = float(score)
    except (TypeError, ValueError):
        return False
    return 0.0 <= value <= 100.0


def letter_for_score(score: float) -> GradeLetter:
    value = clamp_stage_score(score)
    for floor, letter in THRESHOLDS:
        if value >= floor:
            return letter
    return "F"


def combine_scores(deterministic: float, nlp: float, vision: float) -> float:
    combined = (
        WEIGHTS["deterministic"] * clamp_stage_score(deterministic)
        + WEIGHTS["nlp"] * clamp_stage_score(nlp)
        + WEIGHTS["vision"] * clamp_stage_score(vision)
    )
    return round(max(0.0, min(100.0, combined)), 4)


def aggregate_grade(
    *,
    deterministic: StageSignals,
    nlp: StageSignals,
    vision: StageSignals,
) -> tuple[GradeLetter, float, list[EvidenceItem]]:
    """Return (letter, combined_score, hard_failure_evidence). Hard failures win."""
    hard: list[EvidenceItem] = []
    for stage in (deterministic, nlp, vision):
        for item in stage.evidence:
            if item.severity == "hard" and item.result == "fail":
                hard.append(item)
    score = combine_scores(deterministic.score, nlp.score, vision.score)
    if hard:
        forced = EvidenceItem(
            category="aggregation",
            check_id="hard_failure_forces_f",
            severity="hard",
            result="fail",
            explanation="A hard failure forces grade F and cannot be overridden by score aggregation.",
            details={
                "combined_score": score,
                "engine_version": ENGINE_VERSION,
                "hard_failure_check_ids": [item.check_id for item in hard],
            },
        )
        return "F", score, [*hard, forced]
    return letter_for_score(score), score, []

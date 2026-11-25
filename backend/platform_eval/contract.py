"""Phase 4 contracts. Baba Score and platform evidence are distinct types."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.grading.contract import GradeLetter

EVALUATION_VERSION = "platform_eval.v1"

EvidenceResult = Literal["pass", "fail", "skip"]
EvidenceSeverity = Literal["info", "ordinary"]

# Common food-app native scale observed in ingested data. This is NOT a Baba Score mapping.
DECLARED_NATIVE_SCALE_MIN = 0.0
DECLARED_NATIVE_SCALE_MAX = 5.0


class PlatformNativeSignal(BaseModel):
    """A platform-native observation. Never a Baba Score."""

    kind: str
    score: float | None = None
    count: int | str | None = None
    path: str
    parseable: bool = False
    in_declared_scale: bool | None = None
    raw: Any = None


class PlatformEvidenceItem(BaseModel):
    platform: str
    check_id: str
    severity: EvidenceSeverity
    result: EvidenceResult
    explanation: str
    path: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class PlatformEvaluation(BaseModel):
    kind: Literal["platform_evidence"] = "platform_evidence"
    platform: str
    evaluation_version: str = EVALUATION_VERSION
    adapter_id: str
    catalogue_id: str
    evaluated_head_revision: int
    evaluated_state_hash: str
    source_listing: bool
    native_signals: list[PlatformNativeSignal] = Field(default_factory=list)
    evidence: list[PlatformEvidenceItem] = Field(default_factory=list)
    baba_score: None = None


class BabaScore(BaseModel):
    """Projection of Phase 3 grading.v1. Independent of platform-native scores."""

    kind: Literal["baba_score"] = "baba_score"
    source: Literal["grading.v1"] = "grading.v1"
    independent_of_platform: Literal[True] = True
    catalogue_id: str
    graded_head_revision: int
    graded_state_hash: str
    letter: GradeLetter
    score: float


class CatalogueEvaluationResponse(BaseModel):
    catalogue_id: str
    evaluated_head_revision: int
    evaluated_state_hash: str
    evaluation_version: str = EVALUATION_VERSION
    baba_score: BabaScore | None = None
    platform_evaluations: list[PlatformEvaluation] = Field(default_factory=list)


class EvaluationContext(BaseModel):
    catalogue_id: str
    evaluated_head_revision: int
    evaluated_state_hash: str
    source_platform: str
    native_signals: list[PlatformNativeSignal] = Field(default_factory=list)

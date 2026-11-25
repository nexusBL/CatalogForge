"""Structured Phase 3 grading contract.

Field names follow repository snake_case conventions (see `backend/catalogue_validate.py`).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ENGINE_VERSION = "grading.v1"

GradeLetter = Literal["A", "B", "C", "D", "F"]
EvidenceCategory = Literal["deterministic", "nlp", "vision", "aggregation"]
EvidenceSeverity = Literal["info", "ordinary", "hard"]
EvidenceResult = Literal["pass", "fail", "skip", "error"]
JobStatus = Literal["NOT_STARTED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"]
StageStatus = Literal["completed", "failed", "cancelled"]


class EvidenceItem(BaseModel):
    category: EvidenceCategory
    check_id: str
    severity: EvidenceSeverity
    result: EvidenceResult
    explanation: str
    path: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class StageSignals(BaseModel):
    score: float
    evidence: list[EvidenceItem] = Field(default_factory=list)
    hard_failures: list[str] = Field(default_factory=list)
    status: StageStatus = "completed"
    error: str | None = None


class GradingResult(BaseModel):
    catalogue_id: str
    graded_head_revision: int
    graded_state_hash: str
    grade: GradeLetter
    score: float
    signals: dict[str, float] = Field(default_factory=dict)
    hard_failures: list[EvidenceItem] = Field(default_factory=list)
    deterministic_evidence: list[EvidenceItem] = Field(default_factory=list)
    nlp_evidence: list[EvidenceItem] = Field(default_factory=list)
    vision_evidence: list[EvidenceItem] = Field(default_factory=list)
    grading_metadata: dict[str, Any] = Field(default_factory=dict)

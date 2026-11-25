"""Phase 3 Baba grading engine. Consumes canonical catalogues only."""

from backend.grading.contract import (
    ENGINE_VERSION,
    EvidenceItem,
    GradeLetter,
    GradingResult,
    StageSignals,
)
from backend.grading.orchestrator import grade_canonical_document

__all__ = [
    "ENGINE_VERSION",
    "EvidenceItem",
    "GradeLetter",
    "GradingResult",
    "StageSignals",
    "grade_canonical_document",
]

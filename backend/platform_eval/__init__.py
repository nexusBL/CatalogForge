"""Phase 4 Baba Score + platform evaluation. Downstream of canonical persist; separate from grading.v1."""

from backend.platform_eval.adapters import UnsupportedPlatform, supported_platforms
from backend.platform_eval.contract import (
    EVALUATION_VERSION,
    BabaScore,
    CatalogueEvaluationResponse,
    PlatformEvaluation,
)
from backend.platform_eval.evaluate import evaluate_platforms

__all__ = [
    "EVALUATION_VERSION",
    "BabaScore",
    "CatalogueEvaluationResponse",
    "PlatformEvaluation",
    "UnsupportedPlatform",
    "evaluate_platforms",
    "supported_platforms",
]

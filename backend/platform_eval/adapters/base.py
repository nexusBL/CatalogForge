"""Platform evaluation adapter contract."""

from __future__ import annotations

from abc import ABC, abstractmethod

from backend.canonical.models import CanonicalDocument
from backend.platform_eval.contract import (
    EVALUATION_VERSION,
    EvaluationContext,
    PlatformEvaluation,
    PlatformEvidenceItem,
    PlatformNativeSignal,
)


class PlatformEvaluationAdapter(ABC):
    platform: str
    adapter_id: str

    def evaluate(self, document: CanonicalDocument, context: EvaluationContext) -> PlatformEvaluation:
        evidence = self.apply_rules(document, context)
        return PlatformEvaluation(
            platform=self.platform,
            evaluation_version=EVALUATION_VERSION,
            adapter_id=self.adapter_id,
            catalogue_id=context.catalogue_id,
            evaluated_head_revision=context.evaluated_head_revision,
            evaluated_state_hash=context.evaluated_state_hash,
            source_listing=context.source_platform == self.platform,
            native_signals=list(context.native_signals),
            evidence=evidence,
            baba_score=None,
        )

    @abstractmethod
    def apply_rules(self, document: CanonicalDocument, context: EvaluationContext) -> list[PlatformEvidenceItem]:
        raise NotImplementedError

    def evidence(
        self,
        *,
        check_id: str,
        result: str,
        explanation: str,
        severity: str = "ordinary",
        path: str | None = None,
        details: dict | None = None,
    ) -> PlatformEvidenceItem:
        return PlatformEvidenceItem(
            platform=self.platform,
            check_id=check_id,
            severity=severity,  # type: ignore[arg-type]
            result=result,  # type: ignore[arg-type]
            explanation=explanation,
            path=path,
            details=details or {},
        )

    @staticmethod
    def venue_signals(signals: list[PlatformNativeSignal]) -> list[PlatformNativeSignal]:
        return [item for item in signals if item.kind != "item"]

    @staticmethod
    def parseable_venue_scores(signals: list[PlatformNativeSignal]) -> list[PlatformNativeSignal]:
        return [item for item in signals if item.kind != "item" and item.parseable and item.score is not None]

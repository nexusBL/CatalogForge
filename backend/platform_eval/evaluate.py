"""Run registered platform adapters. Does not compute or mutate Baba Score."""

from __future__ import annotations

from backend.canonical.models import CanonicalDocument
from backend.platform_eval.adapters import require_adapter, supported_platforms
from backend.platform_eval.contract import EvaluationContext, PlatformEvaluation
from backend.platform_eval.signals import applicable_platforms, native_signals_for_platform


class PlatformEvalStageFailure(RuntimeError):
    def __init__(self, platform: str, detail: str):
        self.platform = platform
        super().__init__(f"{platform}: {detail}")


def resolve_platforms(document: CanonicalDocument, requested: list[str] | None) -> list[str]:
    if requested is None or not any((platform or "").strip() for platform in requested):
        return applicable_platforms(document, supported_platforms())
    resolved: list[str] = []
    seen: set[str] = set()
    for platform in requested:
        key = platform.strip().lower()
        if not key or key in seen:
            continue
        require_adapter(key)
        seen.add(key)
        resolved.append(key)
    return resolved


def evaluate_platforms(
    document: CanonicalDocument,
    *,
    catalogue_id: str,
    evaluated_head_revision: int,
    evaluated_state_hash: str,
    platforms: list[str],
) -> list[PlatformEvaluation]:
    source_platform = (document.provenance.platform or "").strip().lower()
    results: list[PlatformEvaluation] = []
    for platform in platforms:
        adapter = require_adapter(platform)
        context = EvaluationContext(
            catalogue_id=catalogue_id,
            evaluated_head_revision=evaluated_head_revision,
            evaluated_state_hash=evaluated_state_hash,
            source_platform=source_platform,
            native_signals=native_signals_for_platform(document, platform),
        )
        try:
            results.append(adapter.evaluate(document, context))
        except PlatformEvalStageFailure:
            raise
        except Exception as exc:
            raise PlatformEvalStageFailure(platform, str(exc)) from exc
    return results

"""Normalize stage findings into the structured EvidenceItem contract."""

from __future__ import annotations

from typing import Any

from backend.grading.contract import EvidenceCategory, EvidenceItem, EvidenceResult, EvidenceSeverity


def evidence(
    *,
    category: EvidenceCategory,
    check_id: str,
    severity: EvidenceSeverity,
    result: EvidenceResult,
    explanation: str,
    path: str | None = None,
    details: dict[str, Any] | None = None,
) -> EvidenceItem:
    return EvidenceItem(
        category=category,
        check_id=check_id,
        severity=severity,
        result=result,
        explanation=explanation,
        path=path,
        details=details or {},
    )

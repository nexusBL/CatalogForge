"""Evaluate stored catalogues for platform evidence. Does not run grading.v1 or ingest."""

from __future__ import annotations

from backend.grading.document import graded_state_hash
from backend.grading.persist import head_revision
from backend.migrate_catalogues import connect_catalogue_db
from backend.platform_eval.baba_score import load_baba_score
from backend.platform_eval.contract import CatalogueEvaluationResponse
from backend.platform_eval.evaluate import PlatformEvalStageFailure, evaluate_platforms, resolve_platforms
from backend.platform_eval.persist import (
    PlatformEvalPersistenceError,
    StaleCatalogueState,
    document_from_snapshot,
    load_evaluations_for_state,
    persist_evaluations,
    snapshot_catalogue,
)
from backend.store import get_catalogue


def evaluate_catalogue_platforms(
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
    platforms: list[str] | None = None,
) -> CatalogueEvaluationResponse:
    stored_result, revision, state_hash = snapshot_catalogue(
        user_id=user_id,
        organization_id=organization_id,
        catalogue_id=catalogue_id,
    )
    document = document_from_snapshot(stored_result)
    wanted = resolve_platforms(document, platforms)
    existing = load_evaluations_for_state(
        user_id=user_id,
        organization_id=organization_id,
        catalogue_id=catalogue_id,
        evaluated_head_revision=revision,
        evaluated_state_hash=state_hash,
    )
    have = {item.platform for item in existing}
    missing = [platform for platform in wanted if platform not in have]
    if missing:
        computed = evaluate_platforms(
            document,
            catalogue_id=catalogue_id,
            evaluated_head_revision=revision,
            evaluated_state_hash=state_hash,
            platforms=missing,
        )
        persisted = persist_evaluations(
            user_id=user_id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
            expected_head_revision=revision,
            expected_state_hash=state_hash,
            evaluations=computed,
        )
        by_platform = {item.platform: item for item in existing}
        for item in persisted:
            by_platform[item.platform] = item
        existing = [by_platform[platform] for platform in sorted(by_platform)]
    selected = [item for item in existing if item.platform in wanted]
    selected.sort(key=lambda item: item.platform)
    baba_score = load_baba_score(user_id=user_id, organization_id=organization_id, catalogue_id=catalogue_id)
    return CatalogueEvaluationResponse(
        catalogue_id=catalogue_id,
        evaluated_head_revision=revision,
        evaluated_state_hash=state_hash,
        baba_score=baba_score,
        platform_evaluations=selected,
    )


def get_catalogue_platform_evaluation(
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
) -> CatalogueEvaluationResponse:
    stored = get_catalogue(user_id, catalogue_id, organization_id)
    if stored is None:
        raise KeyError("Catalogue not found for this restaurant organization.")
    connection = connect_catalogue_db()
    try:
        revision = head_revision(connection, catalogue_id)
    finally:
        connection.close()
    state_hash = graded_state_hash(stored.result)
    evaluations = load_evaluations_for_state(
        user_id=user_id,
        organization_id=organization_id,
        catalogue_id=catalogue_id,
        evaluated_head_revision=revision,
        evaluated_state_hash=state_hash,
    )
    baba_score = load_baba_score(user_id=user_id, organization_id=organization_id, catalogue_id=catalogue_id)
    return CatalogueEvaluationResponse(
        catalogue_id=catalogue_id,
        evaluated_head_revision=revision,
        evaluated_state_hash=state_hash,
        baba_score=baba_score,
        platform_evaluations=evaluations,
    )


__all__ = [
    "PlatformEvalPersistenceError",
    "PlatformEvalStageFailure",
    "StaleCatalogueState",
    "evaluate_catalogue_platforms",
    "get_catalogue_platform_evaluation",
]

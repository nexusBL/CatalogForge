"""Grade a stored canonical catalogue. Downstream of Phase 1/2 persistence."""

from __future__ import annotations

from backend.grading.contract import GradingResult
from backend.grading.document import canonical_document_from_result, graded_state_hash
from backend.grading.nlp import NLPGrader
from backend.grading.orchestrator import GradingCancelled, GradingStageFailure, grade_canonical_document
from backend.grading.persist import (
    GradeCancelled,
    GradeInProgress,
    GradePersistenceError,
    StaleClaim,
    claim_grade_job,
    finish_grade_job,
    head_revision,
    job_is_cancelled,
    latest_grade_for_state,
    request_cancel_grade_job,
)
from backend.grading.vision import VisionGrader
from backend.migrate_catalogues import connect_catalogue_db
from backend.store import get_catalogue


def grade_catalogue(
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
    nlp_grader: NLPGrader | None = None,
    vision_grader: VisionGrader | None = None,
) -> GradingResult:
    job_id, existing, snapshot, revision, state_hash, claim_token = claim_grade_job(
        user_id=user_id,
        organization_id=organization_id,
        catalogue_id=catalogue_id,
    )
    if existing is not None:
        return existing
    document = canonical_document_from_result(snapshot)
    try:
        result = grade_canonical_document(
            document,
            catalogue_id=catalogue_id,
            graded_head_revision=revision,
            graded_state_hash=state_hash,
            nlp_grader=nlp_grader,
            vision_grader=vision_grader,
            cancel_check=lambda: job_is_cancelled(job_id),
        )
    except GradingCancelled as exc:
        try:
            finish_grade_job(
                job_id=job_id,
                user_id=user_id,
                organization_id=organization_id,
                catalogue_id=catalogue_id,
                expected_head_revision=revision,
                expected_state_hash=state_hash,
                claim_token=claim_token,
                result=None,
                status="CANCELLED",
                error=str(exc),
            )
        except (GradeCancelled, StaleClaim):
            pass
        raise GradeCancelled(str(exc)) from exc
    except GradingStageFailure as exc:
        try:
            finish_grade_job(
                job_id=job_id,
                user_id=user_id,
                organization_id=organization_id,
                catalogue_id=catalogue_id,
                expected_head_revision=revision,
                expected_state_hash=state_hash,
                claim_token=claim_token,
                result=None,
                status="FAILED",
                error=f"{exc.stage}: {exc}",
            )
        except GradeCancelled as cancel_exc:
            raise cancel_exc from exc
        except StaleClaim as stale_exc:
            raise stale_exc from exc
        raise
    persisted = finish_grade_job(
        job_id=job_id,
        user_id=user_id,
        organization_id=organization_id,
        catalogue_id=catalogue_id,
        expected_head_revision=revision,
        expected_state_hash=state_hash,
        claim_token=claim_token,
        result=result,
        status="COMPLETED",
    )
    if persisted is None:
        raise GradePersistenceError("completed grading did not persist a grade")
    return persisted


def get_catalogue_grade(*, user_id: str, organization_id: str, catalogue_id: str) -> GradingResult | None:
    stored = get_catalogue(user_id, catalogue_id, organization_id)
    if stored is None:
        raise KeyError("Catalogue not found for this restaurant organization.")
    connection = connect_catalogue_db()
    try:
        revision = head_revision(connection, catalogue_id)
    finally:
        connection.close()
    return latest_grade_for_state(
        user_id=user_id,
        organization_id=organization_id,
        catalogue_id=catalogue_id,
        graded_head_revision=revision,
        graded_state_hash=graded_state_hash(stored.result),
    )


def cancel_catalogue_grade(
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
    job_id: str,
    claim_token: str | None = None,
) -> dict:
    return request_cancel_grade_job(
        user_id=user_id,
        organization_id=organization_id,
        catalogue_id=catalogue_id,
        job_id=job_id,
        claim_token=claim_token,
    )


__all__ = [
    "GradeInProgress",
    "GradeCancelled",
    "GradePersistenceError",
    "StaleClaim",
    "cancel_catalogue_grade",
    "get_catalogue_grade",
    "grade_catalogue",
]

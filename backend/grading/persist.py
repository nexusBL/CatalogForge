"""Additive Phase 3 grading persistence. Does not alter catalogue identity."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from backend.grading.contract import ENGINE_VERSION, GradingResult, JobStatus
from backend.grading.document import graded_state_hash
from backend.grading.formula import stage_score_is_unit
from backend.migrate_catalogues import connect_catalogue_db, ensure_phase3_ddl
from backend.schemas import CatalogCreateResponse

STALE_CLAIM_SECONDS = float(os.getenv("CATALOGFORGE_GRADE_CLAIM_TTL", "900"))


class GradeInProgress(RuntimeError):
    pass


class GradeCancelled(RuntimeError):
    pass


class StaleCatalogueState(RuntimeError):
    pass


class StaleClaim(RuntimeError):
    """This worker no longer owns the RUNNING claim."""


class GradePersistenceError(RuntimeError):
    pass


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _stale(claimed_at: str | None) -> bool:
    started = _parse_time(claimed_at)
    if started is None:
        return True
    now = datetime.now(timezone.utc)
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    return (now - started).total_seconds() > STALE_CLAIM_SECONDS


def _begin_immediate(connection: sqlite3.Connection) -> None:
    connection.isolation_level = None
    connection.execute("BEGIN IMMEDIATE")


def head_revision(connection: sqlite3.Connection, catalogue_id: str) -> int:
    row = connection.execute(
        "SELECT COALESCE(MAX(revision), 0) AS n FROM catalogue_revisions WHERE catalogue_id = ?",
        (catalogue_id,),
    ).fetchone()
    return int(row["n"] if row else 0)


def _catalogue_snapshot(
    connection: sqlite3.Connection,
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
) -> tuple[CatalogCreateResponse, int, str]:
    row = connection.execute(
        """
        SELECT payload FROM catalogues
        WHERE id = ? AND user_id = ? AND organization_id = ?
        """,
        (catalogue_id, user_id, organization_id),
    ).fetchone()
    if row is None:
        raise KeyError("Catalogue not found for this restaurant organization.")
    result = CatalogCreateResponse.model_validate(json.loads(row["payload"]))
    return result, head_revision(connection, catalogue_id), graded_state_hash(result)


def get_completed_grade(
    connection: sqlite3.Connection,
    *,
    catalogue_id: str,
    graded_head_revision: int,
    graded_state_hash: str,
    engine_version: str = ENGINE_VERSION,
) -> GradingResult | None:
    row = connection.execute(
        """
        SELECT payload FROM catalogue_grades
        WHERE catalogue_id = ? AND graded_head_revision = ? AND graded_state_hash = ?
          AND engine_version = ? AND status = 'COMPLETED'
        """,
        (catalogue_id, graded_head_revision, graded_state_hash, engine_version),
    ).fetchone()
    if row is None:
        return None
    result = GradingResult.model_validate(json.loads(row["payload"]))
    if not _stage_scores_are_unit(result):
        return None
    return result


def _stage_scores_are_unit(result: GradingResult) -> bool:
    return all(stage_score_is_unit(result.signals.get(key)) for key in ("deterministic", "nlp", "vision"))


def _purge_invalid_completed_grade(
    connection: sqlite3.Connection,
    *,
    catalogue_id: str,
    graded_head_revision: int,
    graded_state_hash: str,
    engine_version: str,
) -> None:
    """Remove a COMPLETED row whose payload is not a valid grading.v1 0–100 stage result."""
    row = connection.execute(
        """
        SELECT payload FROM catalogue_grades
        WHERE catalogue_id = ? AND graded_head_revision = ? AND graded_state_hash = ?
          AND engine_version = ? AND status = 'COMPLETED'
        """,
        (catalogue_id, graded_head_revision, graded_state_hash, engine_version),
    ).fetchone()
    if row is None:
        return
    try:
        result = GradingResult.model_validate(json.loads(row["payload"]))
    except (TypeError, ValueError, json.JSONDecodeError):
        result = None
    if result is not None and _stage_scores_are_unit(result):
        return
    connection.execute(
        """
        DELETE FROM catalogue_grades
        WHERE catalogue_id = ? AND graded_head_revision = ? AND graded_state_hash = ?
          AND engine_version = ? AND status = 'COMPLETED'
        """,
        (catalogue_id, graded_head_revision, graded_state_hash, engine_version),
    )
    connection.execute(
        """
        DELETE FROM catalogue_grade_jobs
        WHERE catalogue_id = ? AND graded_head_revision = ? AND graded_state_hash = ?
          AND engine_version = ?
        """,
        (catalogue_id, graded_head_revision, graded_state_hash, engine_version),
    )


def claim_grade_job(
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
    engine_version: str = ENGINE_VERSION,
) -> tuple[str, GradingResult | None, CatalogCreateResponse, int, str, str]:
    """Lock, snapshot catalogue identity, then claim or return an existing completed grade."""
    connection = connect_catalogue_db()
    ensure_phase3_ddl(connection)
    try:
        _begin_immediate(connection)
        stored_result, graded_head_revision, graded_state_hash = _catalogue_snapshot(
            connection,
            user_id=user_id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
        )
        existing = get_completed_grade(
            connection,
            catalogue_id=catalogue_id,
            graded_head_revision=graded_head_revision,
            graded_state_hash=graded_state_hash,
            engine_version=engine_version,
        )
        if existing is not None:
            connection.execute("COMMIT")
            return (
                str(existing.grading_metadata.get("job_id") or ""),
                existing,
                stored_result,
                graded_head_revision,
                graded_state_hash,
                "",
            )
        _purge_invalid_completed_grade(
            connection,
            catalogue_id=catalogue_id,
            graded_head_revision=graded_head_revision,
            graded_state_hash=graded_state_hash,
            engine_version=engine_version,
        )

        row = connection.execute(
            """
            SELECT id, status, claim_token, claimed_at, cancel_requested
            FROM catalogue_grade_jobs
            WHERE catalogue_id = ? AND graded_head_revision = ? AND graded_state_hash = ?
              AND engine_version = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (catalogue_id, graded_head_revision, graded_state_hash, engine_version),
        ).fetchone()
        now = _utcnow()
        token = str(uuid.uuid4())
        if row is not None and row["status"] == "RUNNING" and not _stale(row["claimed_at"]) and not row["cancel_requested"]:
            connection.execute("COMMIT")
            raise GradeInProgress("Grading is already running for this catalogue revision.")
        if row is not None and row["status"] == "RUNNING" and row["cancel_requested"]:
            connection.execute(
                """
                UPDATE catalogue_grade_jobs
                SET status = 'CANCELLED', updated_at = ?, error = ?
                WHERE id = ? AND status = 'RUNNING' AND claim_token = ?
                """,
                (now, "Cancelled", row["id"], row["claim_token"]),
            )
            return _insert_running_job(
                connection,
                job_id=str(uuid.uuid4()),
                user_id=user_id,
                organization_id=organization_id,
                catalogue_id=catalogue_id,
                graded_head_revision=graded_head_revision,
                graded_state_hash=graded_state_hash,
                engine_version=engine_version,
                token=token,
                now=now,
                stored_result=stored_result,
            )
        if row is not None and row["status"] in {"RUNNING", "FAILED"}:
            previous_token = row["claim_token"]
            previous_status = row["status"]
            updated = connection.execute(
                """
                UPDATE catalogue_grade_jobs
                SET status = 'RUNNING', claim_token = ?, claimed_at = ?, updated_at = ?,
                    cancel_requested = 0, error = NULL, user_id = ?, organization_id = ?
                WHERE id = ? AND status = ? AND IFNULL(claim_token, '') = ?
                """,
                (
                    token,
                    now,
                    now,
                    user_id,
                    organization_id,
                    row["id"],
                    previous_status,
                    previous_token or "",
                ),
            )
            if int(updated.rowcount) != 1:
                connection.execute("ROLLBACK")
                raise GradeInProgress("Grading is already running for this catalogue revision.")
            connection.execute("COMMIT")
            return str(row["id"]), None, stored_result, graded_head_revision, graded_state_hash, token
        return _insert_running_job(
            connection,
            job_id=str(uuid.uuid4()),
            user_id=user_id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
            graded_head_revision=graded_head_revision,
            graded_state_hash=graded_state_hash,
            engine_version=engine_version,
            token=token,
            now=now,
            stored_result=stored_result,
        )
    except GradeInProgress:
        raise
    except KeyError:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    except Exception:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        connection.close()


def _insert_running_job(
    connection: sqlite3.Connection,
    *,
    job_id: str,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
    graded_head_revision: int,
    graded_state_hash: str,
    engine_version: str,
    token: str,
    now: str,
    stored_result: CatalogCreateResponse,
) -> tuple[str, None, CatalogCreateResponse, int, str, str]:
    try:
        connection.execute(
            """
            INSERT INTO catalogue_grade_jobs (
                id, catalogue_id, user_id, organization_id, graded_head_revision,
                graded_state_hash, engine_version, status, claim_token, claimed_at,
                cancel_requested, error, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'RUNNING', ?, ?, 0, NULL, ?, ?)
            """,
            (
                job_id,
                catalogue_id,
                user_id,
                organization_id,
                graded_head_revision,
                graded_state_hash,
                engine_version,
                token,
                now,
                now,
                now,
            ),
        )
    except sqlite3.IntegrityError:
        connection.execute("ROLLBACK")
        raise GradeInProgress("Grading is already running for this catalogue revision.") from None
    connection.execute("COMMIT")
    return job_id, None, stored_result, graded_head_revision, graded_state_hash, token


def job_is_cancelled(job_id: str) -> bool:
    connection = connect_catalogue_db()
    ensure_phase3_ddl(connection)
    try:
        row = connection.execute(
            "SELECT status, cancel_requested FROM catalogue_grade_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return False
    return row["status"] == "CANCELLED" or bool(row["cancel_requested"])


def request_cancel_grade_job(
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
    job_id: str,
    claim_token: str | None = None,
) -> dict[str, Any]:
    connection = connect_catalogue_db()
    ensure_phase3_ddl(connection)
    try:
        _begin_immediate(connection)
        row = connection.execute(
            """
            SELECT id, status, claim_token FROM catalogue_grade_jobs
            WHERE id = ? AND catalogue_id = ? AND user_id = ? AND organization_id = ?
            """,
            (job_id, catalogue_id, user_id, organization_id),
        ).fetchone()
        if row is None:
            connection.execute("ROLLBACK")
            raise KeyError("Grade job not found.")
        now = _utcnow()
        if row["status"] in {"COMPLETED", "FAILED", "CANCELLED"}:
            status = row["status"]
            connection.execute("COMMIT")
            return {"id": job_id, "status": status}
        if claim_token is not None:
            updated = connection.execute(
                """
                UPDATE catalogue_grade_jobs
                SET cancel_requested = 1, status = 'CANCELLED', updated_at = ?, error = ?
                WHERE id = ? AND status = 'RUNNING' AND claim_token = ?
                """,
                (now, "Cancelled", job_id, claim_token),
            )
            if int(updated.rowcount) != 1:
                connection.execute("ROLLBACK")
                raise StaleClaim("job claim is no longer owned by this worker")
        else:
            connection.execute(
                """
                UPDATE catalogue_grade_jobs
                SET cancel_requested = 1, status = 'CANCELLED', updated_at = ?, error = ?
                WHERE id = ? AND status = 'RUNNING'
                """,
                (now, "Cancelled", job_id),
            )
        connection.execute("COMMIT")
        return {"id": job_id, "status": "CANCELLED"}
    except (KeyError, StaleClaim):
        raise
    except Exception:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        connection.close()


def finish_grade_job(
    *,
    job_id: str,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
    expected_head_revision: int,
    expected_state_hash: str,
    claim_token: str,
    result: GradingResult | None,
    status: JobStatus,
    error: str | None = None,
) -> GradingResult | None:
    connection = connect_catalogue_db()
    ensure_phase3_ddl(connection)
    try:
        _begin_immediate(connection)
        job = connection.execute(
            """
            SELECT status, cancel_requested, graded_head_revision, graded_state_hash, claim_token
            FROM catalogue_grade_jobs
            WHERE id = ? AND catalogue_id = ? AND user_id = ? AND organization_id = ?
            """,
            (job_id, catalogue_id, user_id, organization_id),
        ).fetchone()
        if job is None:
            connection.execute("ROLLBACK")
            raise KeyError("Grade job not found.")
        if str(job["claim_token"] or "") != str(claim_token or ""):
            connection.execute("ROLLBACK")
            raise StaleClaim("job claim is no longer owned by this worker")
        if job["status"] != "RUNNING":
            if job["status"] == "CANCELLED" or job["cancel_requested"]:
                connection.execute("COMMIT")
                raise GradeCancelled("grading cancelled")
            if job["status"] == "COMPLETED":
                existing = get_completed_grade(
                    connection,
                    catalogue_id=catalogue_id,
                    graded_head_revision=expected_head_revision,
                    graded_state_hash=expected_state_hash,
                )
                connection.execute("COMMIT")
                if existing is not None:
                    return existing
                raise GradePersistenceError("job marked completed without a persisted grade")
            connection.execute("ROLLBACK")
            raise StaleClaim("job claim is no longer owned by this worker")
        if job["cancel_requested"]:
            cancelled = connection.execute(
                """
                UPDATE catalogue_grade_jobs
                SET status = 'CANCELLED', updated_at = ?, error = ?
                WHERE id = ? AND status = 'RUNNING' AND claim_token = ?
                """,
                (_utcnow(), "Cancelled", job_id, claim_token),
            )
            if int(cancelled.rowcount) != 1:
                connection.execute("ROLLBACK")
                raise StaleClaim("job claim is no longer owned by this worker")
            connection.execute("COMMIT")
            raise GradeCancelled("grading cancelled")
        if int(job["graded_head_revision"]) != expected_head_revision or str(job["graded_state_hash"]) != expected_state_hash:
            failed = connection.execute(
                """
                UPDATE catalogue_grade_jobs
                SET status = 'FAILED', updated_at = ?, error = ?
                WHERE id = ? AND status = 'RUNNING' AND claim_token = ?
                """,
                (_utcnow(), "Stale catalogue state", job_id, claim_token),
            )
            if int(failed.rowcount) != 1:
                connection.execute("ROLLBACK")
                raise StaleClaim("job claim is no longer owned by this worker")
            connection.execute("COMMIT")
            raise StaleCatalogueState("grade job identity does not match the claimed catalogue state")

        now = _utcnow()
        if status == "CANCELLED":
            updated = connection.execute(
                """
                UPDATE catalogue_grade_jobs
                SET status = 'CANCELLED', updated_at = ?, error = ?
                WHERE id = ? AND status = 'RUNNING' AND claim_token = ?
                """,
                (now, error or "Cancelled", job_id, claim_token),
            )
            if int(updated.rowcount) != 1:
                connection.execute("ROLLBACK")
                raise StaleClaim("job claim is no longer owned by this worker")
            connection.execute("COMMIT")
            raise GradeCancelled(error or "grading cancelled")

        if status == "FAILED":
            updated = connection.execute(
                """
                UPDATE catalogue_grade_jobs
                SET status = 'FAILED', updated_at = ?, error = ?, result_id = NULL
                WHERE id = ? AND status = 'RUNNING' AND claim_token = ?
                """,
                (now, error, job_id, claim_token),
            )
            if int(updated.rowcount) != 1:
                connection.execute("ROLLBACK")
                raise StaleClaim("job claim is no longer owned by this worker")
            connection.execute("COMMIT")
            return None

        if status != "COMPLETED" or result is None:
            connection.execute("ROLLBACK")
            raise GradePersistenceError("completed grading requires a result payload")

        existing = get_completed_grade(
            connection,
            catalogue_id=catalogue_id,
            graded_head_revision=expected_head_revision,
            graded_state_hash=expected_state_hash,
            engine_version=result.grading_metadata.get("engine_version") or ENGINE_VERSION,
        )
        if existing is not None:
            updated = connection.execute(
                """
                UPDATE catalogue_grade_jobs
                SET status = 'COMPLETED', updated_at = ?, error = NULL
                WHERE id = ? AND status = 'RUNNING' AND claim_token = ?
                """,
                (now, job_id, claim_token),
            )
            if int(updated.rowcount) != 1:
                connection.execute("ROLLBACK")
                raise StaleClaim("job claim is no longer owned by this worker")
            connection.execute("COMMIT")
            return existing

        grade_id = str(uuid.uuid4())
        payload = result.model_copy(
            update={"grading_metadata": {**result.grading_metadata, "job_id": job_id, "grade_id": grade_id}}
        )
        try:
            connection.execute(
                """
                INSERT INTO catalogue_grades (
                    id, catalogue_id, user_id, organization_id, graded_head_revision,
                    graded_state_hash, engine_version, grade, status, payload, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'COMPLETED', ?, ?)
                """,
                (
                    grade_id,
                    catalogue_id,
                    user_id,
                    organization_id,
                    expected_head_revision,
                    expected_state_hash,
                    ENGINE_VERSION,
                    payload.grade,
                    json.dumps(payload.model_dump(mode="json"), ensure_ascii=False),
                    now,
                ),
            )
        except sqlite3.IntegrityError as exc:
            duplicate = get_completed_grade(
                connection,
                catalogue_id=catalogue_id,
                graded_head_revision=expected_head_revision,
                graded_state_hash=expected_state_hash,
            )
            if duplicate is None:
                failed = connection.execute(
                    """
                    UPDATE catalogue_grade_jobs
                    SET status = 'FAILED', updated_at = ?, error = ?, result_id = NULL
                    WHERE id = ? AND status = 'RUNNING' AND claim_token = ?
                    """,
                    (now, "Grade persistence failed", job_id, claim_token),
                )
                if int(failed.rowcount) != 1:
                    connection.execute("ROLLBACK")
                    raise StaleClaim("job claim is no longer owned by this worker") from exc
                connection.execute("COMMIT")
                raise GradePersistenceError("grade could not be persisted") from exc
            updated = connection.execute(
                """
                UPDATE catalogue_grade_jobs
                SET status = 'COMPLETED', updated_at = ?, error = NULL
                WHERE id = ? AND status = 'RUNNING' AND claim_token = ?
                """,
                (now, job_id, claim_token),
            )
            if int(updated.rowcount) != 1:
                connection.execute("ROLLBACK")
                raise StaleClaim("job claim is no longer owned by this worker") from exc
            connection.execute("COMMIT")
            return duplicate

        confirmed = get_completed_grade(
            connection,
            catalogue_id=catalogue_id,
            graded_head_revision=expected_head_revision,
            graded_state_hash=expected_state_hash,
        )
        if confirmed is None:
            failed = connection.execute(
                """
                UPDATE catalogue_grade_jobs
                SET status = 'FAILED', updated_at = ?, error = ?, result_id = NULL
                WHERE id = ? AND status = 'RUNNING' AND claim_token = ?
                """,
                (now, "Grade persistence failed", job_id, claim_token),
            )
            if int(failed.rowcount) != 1:
                connection.execute("ROLLBACK")
                raise StaleClaim("job claim is no longer owned by this worker")
            connection.execute("COMMIT")
            raise GradePersistenceError("completed job is missing a persisted grade")

        updated = connection.execute(
            """
            UPDATE catalogue_grade_jobs
            SET status = 'COMPLETED', updated_at = ?, error = NULL, result_id = ?
            WHERE id = ? AND status = 'RUNNING' AND claim_token = ?
            """,
            (now, grade_id, job_id, claim_token),
        )
        if int(updated.rowcount) != 1:
            connection.execute("ROLLBACK")
            raise StaleClaim("job claim is no longer owned by this worker")
        connection.execute("COMMIT")
        return confirmed
    except (GradeCancelled, StaleCatalogueState, StaleClaim, GradePersistenceError, KeyError):
        raise
    except Exception:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        connection.close()


def latest_grade_for_state(
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
    graded_head_revision: int,
    graded_state_hash: str,
) -> GradingResult | None:
    connection = connect_catalogue_db()
    ensure_phase3_ddl(connection)
    try:
        row = connection.execute(
            """
            SELECT payload FROM catalogue_grades
            WHERE catalogue_id = ? AND user_id = ? AND organization_id = ?
              AND graded_head_revision = ? AND graded_state_hash = ?
              AND engine_version = ? AND status = 'COMPLETED'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (
                catalogue_id,
                user_id,
                organization_id,
                graded_head_revision,
                graded_state_hash,
                ENGINE_VERSION,
            ),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    result = GradingResult.model_validate(json.loads(row["payload"]))
    if not _stage_scores_are_unit(result):
        return None
    return result

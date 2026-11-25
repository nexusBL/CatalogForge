"""Additive Phase 4 platform-evaluation persistence. Does not alter catalogue identity or grading.v1.

``status`` is always written as COMPLETED. Phase 4 has no FAILED/RUNNING job
lifecycle; the column is retained for a possible later lifecycle, not used as
a second grading-job state machine.

Hashing: ``snapshot_catalogue`` reads payload+revision under ``BEGIN IMMEDIATE``
then hashes after COMMIT (the copied payload is the snapshot). ``persist_evaluations``
re-reads and hashes under the write lock so stale-state detection and INSERT share
one transaction. Moving persist hashing outside that lock would reopen a TOCTOU
before INSERT.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone

from pydantic import ValidationError

from backend.canonical.models import CanonicalDocument
from backend.grading.document import canonical_document_from_result, graded_state_hash
from backend.grading.persist import head_revision
from backend.migrate_catalogues import connect_catalogue_db, ensure_phase4_ddl
from backend.platform_eval.contract import EVALUATION_VERSION, PlatformEvaluation
from backend.schemas import CatalogCreateResponse

_SQLITE_CONSTRAINT_FOREIGNKEY = 787
_SQLITE_CONSTRAINT_UNIQUE = 2067
_SQLITE_CONSTRAINT_PRIMARYKEY = 1555


class StaleCatalogueState(RuntimeError):
    pass


class PlatformEvalPersistenceError(RuntimeError):
    pass


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _begin_immediate(connection: sqlite3.Connection) -> None:
    connection.isolation_level = None
    connection.execute("BEGIN IMMEDIATE")


def _rollback(connection: sqlite3.Connection, original: BaseException) -> None:
    try:
        connection.execute("ROLLBACK")
    except sqlite3.Error as rollback_exc:
        if hasattr(original, "add_note"):
            original.add_note(f"ROLLBACK failed: {rollback_exc}")


def _integrity_kind(exc: sqlite3.IntegrityError) -> str:
    code = int(getattr(exc, "sqlite_errorcode", 0) or 0)
    name = str(getattr(exc, "sqlite_errorname", "") or "").upper()
    text = str(exc).upper()
    if code == _SQLITE_CONSTRAINT_FOREIGNKEY or "FOREIGNKEY" in name or "FOREIGN KEY" in text:
        return "fk"
    if (
        code in {_SQLITE_CONSTRAINT_UNIQUE, _SQLITE_CONSTRAINT_PRIMARYKEY}
        or "UNIQUE" in name
        or "PRIMARYKEY" in name
        or "UNIQUE CONSTRAINT" in text
    ):
        return "unique"
    return "other"


def _read_catalogue_payload(
    connection: sqlite3.Connection,
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
) -> tuple[str, int]:
    row = connection.execute(
        """
        SELECT payload FROM catalogues
        WHERE id = ? AND user_id = ? AND organization_id = ?
        """,
        (catalogue_id, user_id, organization_id),
    ).fetchone()
    if row is None:
        raise KeyError("Catalogue not found for this restaurant organization.")
    return str(row["payload"]), head_revision(connection, catalogue_id)


def _parse_catalogue_payload(raw: str) -> CatalogCreateResponse:
    try:
        return CatalogCreateResponse.model_validate(json.loads(raw))
    except (json.JSONDecodeError, TypeError, ValidationError) as exc:
        raise PlatformEvalPersistenceError("stored catalogue payload is unreadable") from exc


def snapshot_catalogue(
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
) -> tuple[CatalogCreateResponse, int, str]:
    connection = connect_catalogue_db()
    ensure_phase4_ddl(connection)
    in_tx = False
    try:
        _begin_immediate(connection)
        in_tx = True
        raw, revision = _read_catalogue_payload(
            connection,
            user_id=user_id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
        )
        connection.execute("COMMIT")
        in_tx = False
        result = _parse_catalogue_payload(raw)
        return result, revision, graded_state_hash(result)
    except Exception as exc:
        if in_tx:
            _rollback(connection, exc)
        raise
    finally:
        connection.close()


def get_completed_evaluations(
    connection: sqlite3.Connection,
    *,
    catalogue_id: str,
    evaluated_head_revision: int,
    evaluated_state_hash: str,
    platforms: list[str] | None = None,
    evaluation_version: str = EVALUATION_VERSION,
) -> list[PlatformEvaluation]:
    params: list[object] = [catalogue_id, evaluated_head_revision, evaluated_state_hash, evaluation_version]
    platform_sql = ""
    if platforms:
        placeholders = ",".join("?" for _ in platforms)
        platform_sql = f" AND platform IN ({placeholders})"
        params.extend(platforms)
    rows = connection.execute(
        f"""
        SELECT platform, payload FROM catalogue_platform_evaluations
        WHERE catalogue_id = ? AND evaluated_head_revision = ? AND evaluated_state_hash = ?
          AND evaluation_version = ? AND status = 'COMPLETED'{platform_sql}
        ORDER BY platform ASC
        """,
        params,
    ).fetchall()
    try:
        return [PlatformEvaluation.model_validate(json.loads(row["payload"])) for row in rows]
    except (json.JSONDecodeError, TypeError, ValidationError) as exc:
        raise PlatformEvalPersistenceError("stored platform evaluation payload is unreadable") from exc


def _insert_completed_evaluation(connection: sqlite3.Connection, params: tuple) -> None:
    connection.execute(
        """
        INSERT INTO catalogue_platform_evaluations (
            id, catalogue_id, user_id, organization_id, evaluated_head_revision,
            evaluated_state_hash, platform, evaluation_version, status, payload, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'COMPLETED', ?, ?)
        """,
        params,
    )


def persist_evaluations(
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
    expected_head_revision: int,
    expected_state_hash: str,
    evaluations: list[PlatformEvaluation],
) -> list[PlatformEvaluation]:
    connection = connect_catalogue_db()
    ensure_phase4_ddl(connection)
    in_tx = False
    try:
        _begin_immediate(connection)
        in_tx = True
        raw, head = _read_catalogue_payload(
            connection,
            user_id=user_id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
        )
        if head != expected_head_revision:
            raise StaleCatalogueState("platform evaluation identity does not match current catalogue state")
        stored_result = _parse_catalogue_payload(raw)
        state_hash = graded_state_hash(stored_result)
        if state_hash != expected_state_hash:
            raise StaleCatalogueState("platform evaluation identity does not match current catalogue state")
        now = _utcnow()
        existing_all = get_completed_evaluations(
            connection,
            catalogue_id=catalogue_id,
            evaluated_head_revision=expected_head_revision,
            evaluated_state_hash=expected_state_hash,
        )
        persisted: dict[str, PlatformEvaluation] = {item.platform: item for item in existing_all}
        for evaluation in evaluations:
            if evaluation.baba_score is not None:
                raise PlatformEvalPersistenceError("platform evaluation must not carry a Baba Score")
            if evaluation.evaluated_head_revision != expected_head_revision or evaluation.evaluated_state_hash != expected_state_hash:
                raise StaleCatalogueState("platform evaluation identity does not match claimed catalogue state")
            if evaluation.platform in persisted:
                continue
            eval_id = str(uuid.uuid4())
            try:
                _insert_completed_evaluation(
                    connection,
                    (
                        eval_id,
                        catalogue_id,
                        user_id,
                        organization_id,
                        expected_head_revision,
                        expected_state_hash,
                        evaluation.platform,
                        evaluation.evaluation_version,
                        json.dumps(evaluation.model_dump(mode="json"), ensure_ascii=False),
                        now,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                kind = _integrity_kind(exc)
                if kind == "fk":
                    raise KeyError("Catalogue not found for this restaurant organization.") from exc
                if kind != "unique":
                    raise PlatformEvalPersistenceError("platform evaluation could not be persisted") from exc
                duplicate = get_completed_evaluations(
                    connection,
                    catalogue_id=catalogue_id,
                    evaluated_head_revision=expected_head_revision,
                    evaluated_state_hash=expected_state_hash,
                    platforms=[evaluation.platform],
                    evaluation_version=evaluation.evaluation_version,
                )
                if not duplicate:
                    raise PlatformEvalPersistenceError("platform evaluation could not be persisted") from exc
                persisted[evaluation.platform] = duplicate[0]
                continue
            persisted[evaluation.platform] = evaluation
        connection.execute("COMMIT")
        in_tx = False
        return [persisted[item.platform] for item in evaluations]
    except Exception as exc:
        if in_tx:
            _rollback(connection, exc)
        raise
    finally:
        connection.close()


def load_evaluations_for_state(
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
    evaluated_head_revision: int,
    evaluated_state_hash: str,
) -> list[PlatformEvaluation]:
    connection = connect_catalogue_db()
    ensure_phase4_ddl(connection)
    try:
        owned = connection.execute(
            """
            SELECT 1 FROM catalogues
            WHERE id = ? AND user_id = ? AND organization_id = ?
            """,
            (catalogue_id, user_id, organization_id),
        ).fetchone()
        if owned is None:
            raise KeyError("Catalogue not found for this restaurant organization.")
        return get_completed_evaluations(
            connection,
            catalogue_id=catalogue_id,
            evaluated_head_revision=evaluated_head_revision,
            evaluated_state_hash=evaluated_state_hash,
        )
    finally:
        connection.close()


def document_from_snapshot(result: CatalogCreateResponse) -> CanonicalDocument:
    return canonical_document_from_result(result)

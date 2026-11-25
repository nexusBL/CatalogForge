"""Persist Phase 7 media jobs and artifacts. Never writes catalogues.payload."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.media.contract import MediaJob
from backend.media.source import confined_generated_path
from backend.migrate_catalogues import connect_catalogue_db, ensure_phase7_ddl

RESERVATION_STATUS = "GENERATING"


def generated_root() -> Path:
    return Path(os.getenv("CATALOGFORGE_GENERATED_MEDIA_DIR", "data/generated-media"))


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


def connect() -> sqlite3.Connection:
    connection = connect_catalogue_db()
    ensure_phase7_ddl(connection)
    connection.commit()
    return connection


def begin_immediate(connection: sqlite3.Connection) -> None:
    connection.isolation_level = None
    connection.execute("BEGIN IMMEDIATE")


def request_key(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def get_job_by_key(connection: sqlite3.Connection, request_key_value: str) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT * FROM catalogue_media_jobs WHERE request_key = ?",
        (request_key_value,),
    ).fetchone()


def insert_job(
    connection: sqlite3.Connection,
    *,
    job_id: str,
    request_key_value: str,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
    source_head_revision: int,
    source_state_hash: str,
    path: str,
    operation: str,
    claim_token: str,
    payload: dict[str, Any],
) -> None:
    now = utcnow()
    connection.execute(
        """
        INSERT INTO catalogue_media_jobs (
            id, request_key, catalogue_id, user_id, organization_id,
            source_head_revision, source_state_hash, path, operation, status,
            claim_token, cancel_requested, payload, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
        """,
        (
            job_id,
            request_key_value,
            catalogue_id,
            user_id,
            organization_id,
            source_head_revision,
            source_state_hash,
            path,
            operation,
            RESERVATION_STATUS,
            claim_token,
            json.dumps(payload, ensure_ascii=False),
            now,
            now,
        ),
    )


def cas_apply(
    connection: sqlite3.Connection,
    *,
    job_id: str,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
) -> bool:
    cursor = connection.execute(
        """
        UPDATE catalogue_media_jobs
        SET status = ?, updated_at = ?
        WHERE id = ? AND catalogue_id = ? AND user_id = ? AND organization_id = ? AND status = ?
        """,
        ("APPLIED", utcnow(), job_id, catalogue_id, user_id, organization_id, "READY"),
    )
    return cursor.rowcount == 1


def cas_finish(
    connection: sqlite3.Connection,
    *,
    job_id: str,
    claim_token: str,
    status: str,
    payload: dict[str, Any],
) -> bool:
    cursor = connection.execute(
        """
        UPDATE catalogue_media_jobs
        SET status = ?, payload = ?, updated_at = ?, claim_token = claim_token
        WHERE id = ? AND status = ? AND claim_token = ? AND cancel_requested = 0
        """,
        (status, json.dumps(payload, ensure_ascii=False), utcnow(), job_id, RESERVATION_STATUS, claim_token),
    )
    return cursor.rowcount == 1


def cas_fail_or_cancel(
    connection: sqlite3.Connection,
    *,
    job_id: str,
    claim_token: str,
    status: str,
    payload: dict[str, Any],
) -> bool:
    cursor = connection.execute(
        """
        UPDATE catalogue_media_jobs
        SET status = ?, payload = ?, updated_at = ?
        WHERE id = ? AND status = ? AND claim_token = ?
        """,
        (status, json.dumps(payload, ensure_ascii=False), utcnow(), job_id, RESERVATION_STATUS, claim_token),
    )
    return cursor.rowcount == 1


def request_cancel(
    connection: sqlite3.Connection,
    *,
    job_id: str,
    user_id: str,
    organization_id: str,
    catalogue_id: str | None = None,
) -> sqlite3.Row | None:
    if catalogue_id is None:
        row = connection.execute(
            """
            SELECT * FROM catalogue_media_jobs
            WHERE id = ? AND user_id = ? AND organization_id = ?
            """,
            (job_id, user_id, organization_id),
        ).fetchone()
    else:
        row = connection.execute(
            """
            SELECT * FROM catalogue_media_jobs
            WHERE id = ? AND catalogue_id = ? AND user_id = ? AND organization_id = ?
            """,
            (job_id, catalogue_id, user_id, organization_id),
        ).fetchone()
    if row is None:
        return None
    connection.execute(
        """
        UPDATE catalogue_media_jobs
        SET cancel_requested = 1,
            status = CASE WHEN status = ? THEN 'CANCELLED' ELSE status END,
            updated_at = ?
        WHERE id = ? AND user_id = ? AND organization_id = ? AND catalogue_id = ?
        """,
        (RESERVATION_STATUS, utcnow(), job_id, user_id, organization_id, row["catalogue_id"]),
    )
    return connection.execute("SELECT * FROM catalogue_media_jobs WHERE id = ?", (job_id,)).fetchone()


def cancel_generating_for_path(
    connection: sqlite3.Connection,
    *,
    catalogue_id: str,
    user_id: str,
    organization_id: str,
    path: str,
) -> None:
    connection.execute(
        """
        UPDATE catalogue_media_jobs
        SET cancel_requested = 1,
            status = CASE WHEN status = ? THEN 'CANCELLED' ELSE status END,
            updated_at = ?
        WHERE catalogue_id = ? AND user_id = ? AND organization_id = ? AND path = ? AND status = ?
        """,
        (RESERVATION_STATUS, utcnow(), catalogue_id, user_id, organization_id, path, RESERVATION_STATUS),
    )


def list_job_rows(
    connection: sqlite3.Connection,
    *,
    catalogue_id: str,
    organization_id: str,
    user_id: str,
) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT * FROM catalogue_media_jobs
        WHERE catalogue_id = ? AND organization_id = ? AND user_id = ?
        ORDER BY created_at DESC
        """,
        (catalogue_id, organization_id, user_id),
    ).fetchall()


def get_owned_job(
    connection: sqlite3.Connection,
    *,
    job_id: str,
    catalogue_id: str,
    organization_id: str,
    user_id: str,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT * FROM catalogue_media_jobs
        WHERE id = ? AND catalogue_id = ? AND organization_id = ? AND user_id = ?
        """,
        (job_id, catalogue_id, organization_id, user_id),
    ).fetchone()


def upsert_workspace(
    connection: sqlite3.Connection,
    *,
    catalogue_id: str,
    user_id: str,
    organization_id: str,
    path: str,
    active_job_id: str | None,
    active_candidate_id: str | None,
    original_artifact_id: str | None,
    running_job_id: str | None,
) -> None:
    connection.execute(
        """
        INSERT INTO catalogue_media_workspaces (
            catalogue_id, user_id, organization_id, path,
            active_job_id, active_candidate_id, original_artifact_id, running_job_id, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(catalogue_id, user_id, organization_id, path) DO UPDATE SET
            active_job_id = excluded.active_job_id,
            active_candidate_id = excluded.active_candidate_id,
            original_artifact_id = COALESCE(excluded.original_artifact_id, catalogue_media_workspaces.original_artifact_id),
            running_job_id = excluded.running_job_id,
            updated_at = excluded.updated_at
        """,
        (
            catalogue_id,
            user_id,
            organization_id,
            path,
            active_job_id,
            active_candidate_id,
            original_artifact_id,
            running_job_id,
            utcnow(),
        ),
    )


def get_workspace(
    connection: sqlite3.Connection,
    *,
    catalogue_id: str,
    user_id: str,
    organization_id: str,
    path: str,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT * FROM catalogue_media_workspaces
        WHERE catalogue_id = ? AND user_id = ? AND organization_id = ? AND path = ?
        """,
        (catalogue_id, user_id, organization_id, path),
    ).fetchone()


def list_workspaces(
    connection: sqlite3.Connection,
    *,
    catalogue_id: str,
    user_id: str,
    organization_id: str,
) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT * FROM catalogue_media_workspaces
        WHERE catalogue_id = ? AND user_id = ? AND organization_id = ?
        """,
        (catalogue_id, user_id, organization_id),
    ).fetchall()


def store_artifact_bytes(
    *,
    artefact_id: str,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
    data: bytes,
    suffix: str,
) -> str:
    root = generated_root()
    rel_parts = [user_id, organization_id, catalogue_id, f"{artefact_id}{suffix}"]
    dest = confined_generated_path(root, rel_parts)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return "/".join(rel_parts)


def insert_artifact(
    connection: sqlite3.Connection,
    *,
    artefact_id: str,
    catalogue_id: str,
    user_id: str,
    organization_id: str,
    job_id: str | None,
    kind: str,
    content_type: str,
    rel_path: str,
    byte_size: int,
) -> None:
    connection.execute(
        """
        INSERT INTO catalogue_media_artifacts (
            id, catalogue_id, user_id, organization_id, job_id, kind, content_type, rel_path, byte_size, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            artefact_id,
            catalogue_id,
            user_id,
            organization_id,
            job_id,
            kind,
            content_type,
            rel_path,
            byte_size,
            utcnow(),
        ),
    )


def get_artifact(
    connection: sqlite3.Connection,
    *,
    artefact_id: str,
    catalogue_id: str,
    user_id: str,
    organization_id: str,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT * FROM catalogue_media_artifacts
        WHERE id = ? AND catalogue_id = ? AND user_id = ? AND organization_id = ?
        """,
        (artefact_id, catalogue_id, user_id, organization_id),
    ).fetchone()


def read_artifact_file(rel_path: str) -> bytes:
    parts = [part for part in rel_path.split("/") if part]
    dest = confined_generated_path(generated_root(), parts)
    if not dest.is_file():
        raise FileNotFoundError(rel_path)
    return dest.read_bytes()


def row_to_job(row: sqlite3.Row, *, current_revision: int, current_hash: str, replay: bool = False) -> MediaJob:
    payload = json.loads(row["payload"])
    job = MediaJob.model_validate(
        {
            "id": row["id"],
            "catalogue_id": row["catalogue_id"],
            "organization_id": row["organization_id"],
            "path": row["path"],
            "operation": row["operation"],
            "status": row["status"],
            "prompt": payload.get("prompt"),
            "proposal_id": payload.get("proposal_id"),
            "source_head_revision": row["source_head_revision"],
            "source_state_hash": row["source_state_hash"],
            "source_ref": payload.get("source_ref"),
            "source_snapshot_hash": payload.get("source_snapshot_hash"),
            "original_artifact_id": payload.get("original_artifact_id"),
            "active_candidate_id": payload.get("active_candidate_id"),
            "candidates": payload.get("candidates") or [],
            "reference_paths": payload.get("reference_paths") or [],
            "error": payload.get("error"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
    )
    stale = int(row["source_head_revision"]) != current_revision or str(row["source_state_hash"]) != current_hash
    if stale and job.status in {"READY", "GENERATING"}:
        job = job.model_copy(update={"status": "STALE"})
    if replay:
        job = job.model_copy(update={"idempotent_replay": True})
    return job

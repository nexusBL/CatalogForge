"""Persist Phase 10 mutation proposals. CAS + single-use confirmation."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

from backend.migrate_catalogues import connect_catalogue_db, ensure_phase10_ddl
from backend.mutation.contract import PROPOSAL_TTL_SECONDS, MutationRecord, MutationStatus

TERMINAL = frozenset({"APPLIED", "CANCELLED", "STALE", "EXPIRED"})


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect() -> sqlite3.Connection:
    connection = connect_catalogue_db()
    ensure_phase10_ddl(connection)
    connection.commit()
    return connection


def begin_immediate(connection: sqlite3.Connection) -> None:
    connection.isolation_level = None
    connection.execute("BEGIN IMMEDIATE")


def new_id() -> str:
    return str(uuid.uuid4())


def new_token() -> str:
    return uuid.uuid4().hex + uuid.uuid4().hex[:16]


def expiry_timestamp() -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=PROPOSAL_TTL_SECONDS)).isoformat()


def insert_proposal(connection: sqlite3.Connection, record: MutationRecord) -> None:
    payload = record.model_dump(mode="json")
    connection.execute(
        """
        INSERT INTO catalogue_mutation_proposals (
            id, confirm_token, catalogue_id, user_id, organization_id,
            source_head_revision, source_state_hash, operation, status,
            expires_at, payload, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.id,
            record.confirm_token,
            record.catalogue_id,
            record.user_id,
            record.organization_id,
            record.source_head_revision,
            record.source_state_hash,
            record.operation,
            record.status,
            record.expires_at,
            json.dumps(payload, ensure_ascii=False),
            record.created_at,
            record.updated_at,
        ),
    )


def get_owned_proposal(
    connection: sqlite3.Connection,
    *,
    proposal_id: str,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
) -> MutationRecord | None:
    row = connection.execute(
        """
        SELECT payload FROM catalogue_mutation_proposals
        WHERE id = ? AND user_id = ? AND organization_id = ? AND catalogue_id = ?
        """,
        (proposal_id, user_id, organization_id, catalogue_id),
    ).fetchone()
    if row is None:
        return None
    return MutationRecord.model_validate(json.loads(row["payload"]))


def get_latest_pending(
    connection: sqlite3.Connection,
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
) -> MutationRecord | None:
    row = connection.execute(
        """
        SELECT payload FROM catalogue_mutation_proposals
        WHERE user_id = ? AND organization_id = ? AND catalogue_id = ? AND status = 'PENDING'
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (user_id, organization_id, catalogue_id),
    ).fetchone()
    if row is None:
        return None
    return MutationRecord.model_validate(json.loads(row["payload"]))


def save_proposal(connection: sqlite3.Connection, record: MutationRecord) -> None:
    connection.execute(
        """
        UPDATE catalogue_mutation_proposals
        SET status = ?, payload = ?, updated_at = ?
        WHERE id = ? AND user_id = ? AND organization_id = ? AND catalogue_id = ?
        """,
        (
            record.status,
            json.dumps(record.model_dump(mode="json"), ensure_ascii=False),
            record.updated_at,
            record.id,
            record.user_id,
            record.organization_id,
            record.catalogue_id,
        ),
    )


def cas_status(
    connection: sqlite3.Connection,
    *,
    proposal_id: str,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
    expected: MutationStatus,
    record: MutationRecord,
) -> bool:
    cursor = connection.execute(
        """
        UPDATE catalogue_mutation_proposals
        SET status = ?, payload = ?, updated_at = ?
        WHERE id = ? AND user_id = ? AND organization_id = ? AND catalogue_id = ? AND status = ?
        """,
        (
            record.status,
            json.dumps(record.model_dump(mode="json"), ensure_ascii=False),
            record.updated_at,
            proposal_id,
            user_id,
            organization_id,
            catalogue_id,
            expected,
        ),
    )
    return cursor.rowcount == 1

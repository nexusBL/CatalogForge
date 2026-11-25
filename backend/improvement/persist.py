"""Persist Phase 6 proposals. Never writes catalogues.payload."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone

from backend.improvement.contract import ImprovementProposal
from backend.migrate_catalogues import connect_catalogue_db


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _begin_immediate(connection: sqlite3.Connection) -> None:
    connection.isolation_level = None
    connection.execute("BEGIN IMMEDIATE")


def request_key(
    *,
    catalogue_id: str,
    source_head_revision: int,
    source_state_hash: str,
    check_id: str,
    paths: list[str],
    instruction: str | None = None,
) -> str:
    payload = {
        "catalogue_id": catalogue_id,
        "source_head_revision": source_head_revision,
        "source_state_hash": source_state_hash,
        "check_id": check_id,
        "paths": paths,
        "instruction": instruction.strip() if instruction else None,
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _row_to_proposal(row: sqlite3.Row, *, current_revision: int, current_hash: str, replay: bool = False) -> ImprovementProposal:
    proposal = ImprovementProposal.model_validate(json.loads(row["payload"]))
    stale = (
        int(row["source_head_revision"]) != current_revision or str(row["source_state_hash"]) != current_hash
    )
    if stale and proposal.status not in {"APPLIED", "CANCELLED"}:
        proposal = proposal.model_copy(update={"status": "STALE"})
    if replay:
        proposal = proposal.model_copy(update={"idempotent_replay": True})
    return proposal


RESERVATION_STATUS = "GENERATING"


def get_request_row(connection: sqlite3.Connection, request_key_value: str) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT id, request_key, status, payload, source_head_revision, source_state_hash,
               organization_id, user_id, created_at
        FROM catalogue_improvement_proposals
        WHERE request_key = ?
        """,
        (request_key_value,),
    ).fetchone()


def insert_reservation(
    connection: sqlite3.Connection,
    *,
    request_key_value: str,
    user_id: str,
    proposal: ImprovementProposal,
) -> None:
    payload = proposal.model_dump(mode="json")
    connection.execute(
        """
        INSERT INTO catalogue_improvement_proposals (
            id, request_key, catalogue_id, user_id, organization_id,
            source_head_revision, source_state_hash, check_id, finding_id,
            status, payload, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            proposal.id,
            request_key_value,
            proposal.catalogue_id,
            user_id,
            proposal.organization_id,
            proposal.source_head_revision,
            proposal.source_state_hash,
            proposal.check_id,
            proposal.finding_id,
            RESERVATION_STATUS,
            json.dumps(payload, ensure_ascii=False),
            proposal.created_at,
        ),
    )


def finalize_proposal(
    connection: sqlite3.Connection,
    *,
    request_key_value: str,
    proposal: ImprovementProposal,
) -> None:
    payload = proposal.model_dump(mode="json")
    connection.execute(
        """
        UPDATE catalogue_improvement_proposals
        SET status = ?, payload = ?
        WHERE request_key = ?
        """,
        (proposal.status, json.dumps(payload, ensure_ascii=False), request_key_value),
    )


def touch_reservation(connection: sqlite3.Connection, request_key_value: str) -> None:
    connection.execute(
        """
        UPDATE catalogue_improvement_proposals
        SET created_at = ?
        WHERE request_key = ? AND status = ?
        """,
        (_utcnow(), request_key_value, RESERVATION_STATUS),
    )


def reservation_age_seconds(created_at: str) -> float:
    started = datetime.fromisoformat(created_at)
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - started).total_seconds()


def get_proposal_by_key(
    connection: sqlite3.Connection,
    *,
    request_key_value: str,
    organization_id: str,
    current_revision: int,
    current_hash: str,
) -> ImprovementProposal | None:
    row = get_request_row(connection, request_key_value)
    if row is None:
        return None
    if row["organization_id"] != organization_id:
        return None
    if row["status"] == RESERVATION_STATUS:
        return None
    return _row_to_proposal(row, current_revision=current_revision, current_hash=current_hash, replay=True)


def get_proposal_by_id(
    connection: sqlite3.Connection,
    *,
    proposal_id: str,
    catalogue_id: str,
    organization_id: str,
    user_id: str,
    current_revision: int,
    current_hash: str,
) -> ImprovementProposal | None:
    row = connection.execute(
        """
        SELECT payload, source_head_revision, source_state_hash
        FROM catalogue_improvement_proposals
        WHERE id = ? AND catalogue_id = ? AND organization_id = ? AND user_id = ?
          AND status != ?
        """,
        (proposal_id, catalogue_id, organization_id, user_id, RESERVATION_STATUS),
    ).fetchone()
    if row is None:
        return None
    return _row_to_proposal(row, current_revision=current_revision, current_hash=current_hash)


def list_proposals(
    connection: sqlite3.Connection,
    *,
    catalogue_id: str,
    organization_id: str,
    user_id: str,
    current_revision: int,
    current_hash: str,
) -> list[ImprovementProposal]:
    rows = connection.execute(
        """
        SELECT payload, source_head_revision, source_state_hash
        FROM catalogue_improvement_proposals
        WHERE catalogue_id = ? AND organization_id = ? AND user_id = ?
          AND status != ?
        ORDER BY created_at DESC
        """,
        (catalogue_id, organization_id, user_id, RESERVATION_STATUS),
    ).fetchall()
    return [
        _row_to_proposal(row, current_revision=current_revision, current_hash=current_hash)
        for row in rows
    ]


def cas_proposal_status(
    connection: sqlite3.Connection,
    *,
    proposal_id: str,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
    expected: tuple[str, ...],
    proposal: ImprovementProposal,
) -> bool:
    payload = proposal.model_dump(mode="json")
    placeholders = ",".join("?" for _ in expected)
    cursor = connection.execute(
        f"""
        UPDATE catalogue_improvement_proposals
        SET status = ?, payload = ?
        WHERE id = ? AND catalogue_id = ? AND organization_id = ? AND user_id = ?
          AND status IN ({placeholders})
        """,
        (
            proposal.status,
            json.dumps(payload, ensure_ascii=False),
            proposal_id,
            catalogue_id,
            organization_id,
            user_id,
            *expected,
        ),
    )
    return cursor.rowcount == 1


def new_proposal_id() -> str:
    return str(uuid.uuid4())


def connect() -> sqlite3.Connection:
    return connect_catalogue_db()


def utcnow() -> str:
    return _utcnow()


def begin_immediate(connection: sqlite3.Connection) -> None:
    _begin_immediate(connection)

"""Append-only catalogue_edit_history. Existing rows are never updated."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from backend.history.contract import EditHistoryRecord
from backend.migrate_catalogues import connect_catalogue_db, ensure_phase11_history_ddl


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


def connect() -> sqlite3.Connection:
    connection = connect_catalogue_db()
    ensure_phase11_history_ddl(connection)
    connection.commit()
    return connection


def begin_immediate(connection: sqlite3.Connection) -> None:
    connection.isolation_level = None
    connection.execute("BEGIN IMMEDIATE")


def insert_record(connection: sqlite3.Connection, record: EditHistoryRecord) -> None:
    connection.execute(
        """
        INSERT INTO catalogue_edit_history (
            id, catalogue_id, user_id, organization_id, source, operation, path,
            item_name, previous_value, new_value, restore_spec, proposal_id, media_job_id,
            rolled_back_history_id, actor, provenance, approval_state,
            before_grade_letter, before_grade_score, after_grade_letter, after_grade_score,
            before_section_scores, after_section_scores, resolved_issue_ids, overall_score_delta,
            source_head_revision, result_head_revision, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.id,
            record.catalogue_id,
            record.user_id,
            record.organization_id,
            record.source,
            record.operation,
            record.path,
            record.item_name,
            json.dumps(record.previous_value, ensure_ascii=False),
            json.dumps(record.new_value, ensure_ascii=False),
            json.dumps(record.restore_spec, ensure_ascii=False),
            record.proposal_id,
            record.media_job_id,
            record.rolled_back_history_id,
            record.actor,
            json.dumps(record.provenance, ensure_ascii=False),
            record.approval_state,
            record.before_grade_letter,
            record.before_grade_score,
            record.after_grade_letter,
            record.after_grade_score,
            json.dumps(record.before_section_scores, ensure_ascii=False),
            json.dumps(record.after_section_scores, ensure_ascii=False),
            json.dumps(record.resolved_issue_ids, ensure_ascii=False),
            record.overall_score_delta,
            record.source_head_revision,
            record.result_head_revision,
            record.created_at,
        ),
    )


def _parse(raw: str | None, default: Any) -> Any:
    if raw is None or raw == "":
        return default
    return json.loads(raw)


def _row_to_record(row: sqlite3.Row) -> EditHistoryRecord:
    return EditHistoryRecord(
        id=row["id"],
        catalogue_id=row["catalogue_id"],
        user_id=row["user_id"],
        organization_id=row["organization_id"],
        source=row["source"],
        operation=row["operation"],
        path=row["path"],
        item_name=row["item_name"],
        previous_value=_parse(row["previous_value"], None),
        new_value=_parse(row["new_value"], None),
        restore_spec=_parse(row["restore_spec"], {}) or {},
        proposal_id=row["proposal_id"],
        media_job_id=row["media_job_id"],
        rolled_back_history_id=row["rolled_back_history_id"],
        actor=row["actor"],
        provenance=_parse(row["provenance"], {}) or {},
        approval_state=row["approval_state"],
        before_grade_letter=row["before_grade_letter"],
        before_grade_score=row["before_grade_score"],
        after_grade_letter=row["after_grade_letter"],
        after_grade_score=row["after_grade_score"],
        before_section_scores=_parse(row["before_section_scores"], {}) or {},
        after_section_scores=_parse(row["after_section_scores"], {}) or {},
        resolved_issue_ids=_parse(row["resolved_issue_ids"], []) or [],
        overall_score_delta=row["overall_score_delta"],
        source_head_revision=row["source_head_revision"],
        result_head_revision=row["result_head_revision"],
        created_at=row["created_at"],
    )


def get_record(
    connection: sqlite3.Connection,
    *,
    history_id: str,
    catalogue_id: str,
    organization_id: str,
) -> EditHistoryRecord | None:
    row = connection.execute(
        """
        SELECT * FROM catalogue_edit_history
        WHERE id = ? AND catalogue_id = ? AND organization_id = ?
        """,
        (history_id, catalogue_id, organization_id),
    ).fetchone()
    if row is None:
        return None
    return _row_to_record(row)


def list_records(
    connection: sqlite3.Connection,
    *,
    catalogue_id: str,
    organization_id: str,
) -> list[EditHistoryRecord]:
    rows = connection.execute(
        """
        SELECT * FROM catalogue_edit_history
        WHERE catalogue_id = ? AND organization_id = ?
        ORDER BY created_at DESC, id DESC
        """,
        (catalogue_id, organization_id),
    ).fetchall()
    return [_row_to_record(row) for row in rows]

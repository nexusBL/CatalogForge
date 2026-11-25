from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.canonical.identity import identity_tuple

DEFAULT_DB = "data/catalogues.sqlite"


def catalogue_db_path() -> Path:
    return Path(os.getenv("CATALOGFORGE_CATALOGUE_DB", DEFAULT_DB))

logger = logging.getLogger(__name__)

MIGRATION_ID = "phase1_canonical_v1"

CATALOGUE_COLUMNS = (
    ("updated_at", "TEXT"),
    ("schema_version", "INTEGER"),
    ("platform", "TEXT"),
    ("canonical_source_url", "TEXT"),
    ("source_entity_id", "TEXT"),
    ("venue_id", "TEXT"),
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _enable_foreign_keys(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys = ON")


def connect_catalogue_db(path: Path | None = None) -> sqlite3.Connection:
    """Open a catalogue SQLite connection with foreign-key enforcement enabled."""
    db_path = Path(path) if path is not None else catalogue_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, timeout=30)
    connection.row_factory = sqlite3.Row
    _enable_foreign_keys(connection)
    return connection


def _add_column(connection: sqlite3.Connection, table: str, name: str, decl: str) -> None:
    existing = {row[1] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
    if name in existing:
        return
    connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


def ensure_phase1_ddl(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS catalogues (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            organization_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            extraction_status TEXT NOT NULL,
            payload TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS area_jobs (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            organization_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL,
            payload TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL,
            status TEXT NOT NULL,
            detail TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS venues (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            organization_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            name TEXT
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS venue_sources (
            id TEXT PRIMARY KEY,
            venue_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            organization_id TEXT NOT NULL,
            platform TEXT NOT NULL,
            source_entity_id TEXT,
            canonical_source_url TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (venue_id) REFERENCES venues(id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS catalogue_revisions (
            id TEXT PRIMARY KEY,
            catalogue_id TEXT NOT NULL,
            revision INTEGER NOT NULL,
            captured_at TEXT NOT NULL,
            payload TEXT NOT NULL,
            FOREIGN KEY (catalogue_id) REFERENCES catalogues(id)
        )
        """
    )
    for name, decl in CATALOGUE_COLUMNS:
        _add_column(connection, "catalogues", name, decl)


def ensure_phase3_ddl(connection: sqlite3.Connection) -> None:
    """Additive grading tables. No catalogue backfill. Safe to rerun."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS catalogue_grades (
            id TEXT PRIMARY KEY,
            catalogue_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            organization_id TEXT NOT NULL,
            graded_head_revision INTEGER NOT NULL,
            graded_state_hash TEXT NOT NULL,
            engine_version TEXT NOT NULL,
            grade TEXT NOT NULL,
            status TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (catalogue_id) REFERENCES catalogues(id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS catalogue_grade_jobs (
            id TEXT PRIMARY KEY,
            catalogue_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            organization_id TEXT NOT NULL,
            graded_head_revision INTEGER NOT NULL,
            graded_state_hash TEXT NOT NULL,
            engine_version TEXT NOT NULL,
            status TEXT NOT NULL,
            claim_token TEXT,
            claimed_at TEXT,
            cancel_requested INTEGER NOT NULL DEFAULT 0,
            error TEXT,
            result_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (catalogue_id) REFERENCES catalogues(id)
        )
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS catalogue_grades_identity
        ON catalogue_grades(catalogue_id, graded_head_revision, graded_state_hash, engine_version)
        WHERE status = 'COMPLETED'
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS catalogue_grade_jobs_running
        ON catalogue_grade_jobs(catalogue_id, graded_head_revision, graded_state_hash, engine_version)
        WHERE status = 'RUNNING'
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS catalogue_grades_lookup
        ON catalogue_grades(catalogue_id, organization_id, user_id)
        """
    )


def ensure_phase4_ddl(connection: sqlite3.Connection) -> None:
    """Additive platform-evaluation tables. No catalogue backfill. Safe to rerun."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS catalogue_platform_evaluations (
            id TEXT PRIMARY KEY,
            catalogue_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            organization_id TEXT NOT NULL,
            evaluated_head_revision INTEGER NOT NULL,
            evaluated_state_hash TEXT NOT NULL,
            platform TEXT NOT NULL,
            evaluation_version TEXT NOT NULL,
            status TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (catalogue_id) REFERENCES catalogues(id)
        )
        """
    )
    # status is always COMPLETED in Phase 4; no FAILED/RUNNING job table.
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS catalogue_platform_evaluations_identity
        ON catalogue_platform_evaluations(
            catalogue_id, evaluated_head_revision, evaluated_state_hash, platform, evaluation_version
        )
        WHERE status = 'COMPLETED'
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS catalogue_platform_evaluations_lookup
        ON catalogue_platform_evaluations(catalogue_id, organization_id, user_id)
        """
    )


def ensure_phase6_ddl(connection: sqlite3.Connection) -> None:
    """Additive improvement-proposal tables. No catalogue backfill. Safe to rerun."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS catalogue_improvement_proposals (
            id TEXT PRIMARY KEY,
            request_key TEXT NOT NULL,
            catalogue_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            organization_id TEXT NOT NULL,
            source_head_revision INTEGER NOT NULL,
            source_state_hash TEXT NOT NULL,
            check_id TEXT NOT NULL,
            finding_id TEXT NOT NULL,
            status TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (catalogue_id) REFERENCES catalogues(id)
        )
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS catalogue_improvement_proposals_request_key
        ON catalogue_improvement_proposals(request_key)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS catalogue_improvement_proposals_lookup
        ON catalogue_improvement_proposals(catalogue_id, organization_id, user_id)
        """
    )


def ensure_phase7_ddl(connection: sqlite3.Connection) -> None:
    """Additive Phase 7 media-job tables. Never writes catalogues.payload."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS catalogue_media_jobs (
            id TEXT PRIMARY KEY,
            request_key TEXT NOT NULL,
            catalogue_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            organization_id TEXT NOT NULL,
            source_head_revision INTEGER NOT NULL,
            source_state_hash TEXT NOT NULL,
            path TEXT NOT NULL,
            operation TEXT NOT NULL,
            status TEXT NOT NULL,
            claim_token TEXT,
            cancel_requested INTEGER NOT NULL DEFAULT 0,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (catalogue_id) REFERENCES catalogues(id)
        )
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS catalogue_media_jobs_request_key
        ON catalogue_media_jobs(request_key)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS catalogue_media_jobs_lookup
        ON catalogue_media_jobs(catalogue_id, organization_id, user_id, created_at)
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS catalogue_media_artifacts (
            id TEXT PRIMARY KEY,
            catalogue_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            organization_id TEXT NOT NULL,
            job_id TEXT,
            kind TEXT NOT NULL,
            content_type TEXT NOT NULL,
            rel_path TEXT NOT NULL,
            byte_size INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (catalogue_id) REFERENCES catalogues(id)
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS catalogue_media_artifacts_lookup
        ON catalogue_media_artifacts(catalogue_id, organization_id, user_id)
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS catalogue_media_workspaces (
            catalogue_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            organization_id TEXT NOT NULL,
            path TEXT NOT NULL,
            active_job_id TEXT,
            active_candidate_id TEXT,
            original_artifact_id TEXT,
            running_job_id TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (catalogue_id, user_id, organization_id, path)
        )
        """
    )


def ensure_phase8_ddl(connection: sqlite3.Connection) -> None:
    """Additive Phase 8 review tables. Never writes catalogues.payload."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS catalogue_reviews (
            id TEXT PRIMARY KEY,
            catalogue_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            organization_id TEXT NOT NULL,
            source TEXT NOT NULL,
            external_id TEXT NOT NULL,
            body TEXT NOT NULL,
            posted_at TEXT,
            author_key TEXT,
            observed_rating REAL,
            photo_id TEXT,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (catalogue_id) REFERENCES catalogues(id)
        )
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS catalogue_reviews_identity
        ON catalogue_reviews(catalogue_id, organization_id, source, external_id)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS catalogue_reviews_lookup
        ON catalogue_reviews(catalogue_id, organization_id, user_id, created_at)
        """
    )
    _add_column(connection, "catalogue_reviews", "photo_id", "TEXT")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS catalogue_review_analyses (
            id TEXT PRIMARY KEY,
            request_key TEXT NOT NULL,
            catalogue_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            organization_id TEXT NOT NULL,
            source_head_revision INTEGER NOT NULL,
            source_state_hash TEXT NOT NULL,
            reviews_fingerprint TEXT NOT NULL,
            status TEXT NOT NULL,
            claim_token TEXT,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (catalogue_id) REFERENCES catalogues(id)
        )
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS catalogue_review_analyses_request_key
        ON catalogue_review_analyses(request_key)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS catalogue_review_analyses_lookup
        ON catalogue_review_analyses(catalogue_id, organization_id, user_id, created_at)
        """
    )


def ensure_phase10_ddl(connection: sqlite3.Connection) -> None:
    """Additive Phase 10 mutation-proposal table. Payload writes happen only after confirm."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS catalogue_mutation_proposals (
            id TEXT PRIMARY KEY,
            confirm_token TEXT NOT NULL,
            catalogue_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            organization_id TEXT NOT NULL,
            source_head_revision INTEGER NOT NULL,
            source_state_hash TEXT NOT NULL,
            operation TEXT NOT NULL,
            status TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (catalogue_id) REFERENCES catalogues(id)
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS catalogue_mutation_proposals_lookup
        ON catalogue_mutation_proposals(catalogue_id, organization_id, user_id, status, created_at)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS catalogue_mutation_proposals_token
        ON catalogue_mutation_proposals(confirm_token)
        """
    )


def ensure_phase11_history_ddl(connection: sqlite3.Connection) -> None:
    """Append-only edit history. Never overwrites previous history rows."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS catalogue_edit_history (
            id TEXT PRIMARY KEY,
            catalogue_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            organization_id TEXT NOT NULL,
            source TEXT NOT NULL,
            operation TEXT NOT NULL,
            path TEXT,
            item_name TEXT,
            previous_value TEXT,
            new_value TEXT,
            restore_spec TEXT NOT NULL,
            proposal_id TEXT,
            media_job_id TEXT,
            rolled_back_history_id TEXT,
            actor TEXT NOT NULL,
            provenance TEXT,
            approval_state TEXT NOT NULL,
            before_grade_letter TEXT,
            before_grade_score REAL,
            after_grade_letter TEXT,
            after_grade_score REAL,
            before_section_scores TEXT,
            after_section_scores TEXT,
            resolved_issue_ids TEXT,
            overall_score_delta REAL,
            source_head_revision INTEGER,
            result_head_revision INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY (catalogue_id) REFERENCES catalogues(id)
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS catalogue_edit_history_lookup
        ON catalogue_edit_history(catalogue_id, organization_id, created_at)
        """
    )


def _payload_dict(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _duplicate_groups(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    entity_rows = connection.execute(
        """
        SELECT user_id, organization_id, platform, source_entity_id, GROUP_CONCAT(id) AS ids, COUNT(*) AS n
        FROM catalogues
        WHERE extraction_status = 'ok' AND source_entity_id IS NOT NULL
        GROUP BY user_id, organization_id, platform, source_entity_id
        HAVING n > 1
        """
    ).fetchall()
    url_rows = connection.execute(
        """
        SELECT user_id, organization_id, platform, canonical_source_url, GROUP_CONCAT(id) AS ids, COUNT(*) AS n
        FROM catalogues
        WHERE extraction_status = 'ok' AND canonical_source_url IS NOT NULL
        GROUP BY user_id, organization_id, platform, canonical_source_url
        HAVING n > 1
        """
    ).fetchall()
    for row in entity_rows:
        groups.append(
            {
                "kind": "source_entity_id",
                "user_id": row["user_id"],
                "organization_id": row["organization_id"],
                "platform": row["platform"],
                "key": row["source_entity_id"],
                "ids": str(row["ids"]).split(","),
                "count": row["n"],
            }
        )
    for row in url_rows:
        groups.append(
            {
                "kind": "canonical_source_url",
                "user_id": row["user_id"],
                "organization_id": row["organization_id"],
                "platform": row["platform"],
                "key": row["canonical_source_url"],
                "ids": str(row["ids"]).split(","),
                "count": row["n"],
            }
        )
    return groups


def _create_unique_indexes(connection: sqlite3.Connection) -> list[str]:
    created: list[str] = []
    statements = {
        "catalogues_ok_entity": """
            CREATE UNIQUE INDEX IF NOT EXISTS catalogues_ok_entity
            ON catalogues(user_id, organization_id, platform, source_entity_id)
            WHERE extraction_status = 'ok' AND source_entity_id IS NOT NULL
        """,
        "catalogues_ok_url": """
            CREATE UNIQUE INDEX IF NOT EXISTS catalogues_ok_url
            ON catalogues(user_id, organization_id, platform, canonical_source_url)
            WHERE extraction_status = 'ok' AND canonical_source_url IS NOT NULL
        """,
        "venue_sources_entity": """
            CREATE UNIQUE INDEX IF NOT EXISTS venue_sources_entity
            ON venue_sources(user_id, organization_id, platform, source_entity_id)
            WHERE source_entity_id IS NOT NULL
        """,
        "venue_sources_url": """
            CREATE UNIQUE INDEX IF NOT EXISTS venue_sources_url
            ON venue_sources(user_id, organization_id, platform, canonical_source_url)
            WHERE canonical_source_url IS NOT NULL
        """,
    }
    for name, sql in statements.items():
        connection.execute(sql)
        created.append(name)
    return created


def _backfill(connection: sqlite3.Connection) -> dict[str, int]:
    rows = connection.execute(
        "SELECT id, user_id, organization_id, created_at, extraction_status, payload, venue_id FROM catalogues"
    ).fetchall()
    venues_created = 0
    catalogues_updated = 0
    venue_by_entity: dict[tuple[str, str, str, str], str] = {}
    venue_by_url: dict[tuple[str, str, str, str], str] = {}

    existing_sources = connection.execute(
        "SELECT venue_id, user_id, organization_id, platform, source_entity_id, canonical_source_url FROM venue_sources"
    ).fetchall()
    for row in existing_sources:
        if row["source_entity_id"]:
            venue_by_entity[(row["user_id"], row["organization_id"], row["platform"], row["source_entity_id"])] = row["venue_id"]
        if row["canonical_source_url"]:
            venue_by_url[(row["user_id"], row["organization_id"], row["platform"], row["canonical_source_url"])] = row["venue_id"]

    for row in rows:
        payload = _payload_dict(row["payload"])
        platform, source_url, source_id = identity_tuple(payload)
        url = source_url or None
        venue_id = row["venue_id"]
        key_entity = (row["user_id"], row["organization_id"], platform, source_id) if source_id else None
        key_url = (row["user_id"], row["organization_id"], platform, url) if url else None
        if not venue_id:
            if key_entity and key_entity in venue_by_entity:
                venue_id = venue_by_entity[key_entity]
            elif key_url and key_url in venue_by_url:
                venue_id = venue_by_url[key_url]
            else:
                venue_id = str(uuid.uuid4())
                connection.execute(
                    """
                    INSERT INTO venues (id, user_id, organization_id, created_at, updated_at, name)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        venue_id,
                        row["user_id"],
                        row["organization_id"],
                        row["created_at"],
                        row["created_at"],
                        str(payload.get("restaurant_name") or "") or None,
                    ),
                )
                venues_created += 1
                connection.execute(
                    """
                    INSERT INTO venue_sources (
                        id, venue_id, user_id, organization_id, platform, source_entity_id, canonical_source_url, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        venue_id,
                        row["user_id"],
                        row["organization_id"],
                        platform,
                        source_id,
                        url,
                        row["created_at"],
                    ),
                )
            if key_entity:
                venue_by_entity[key_entity] = venue_id
            if key_url:
                venue_by_url[key_url] = venue_id
        connection.execute(
            """
            UPDATE catalogues
            SET platform = ?, canonical_source_url = ?, source_entity_id = ?, venue_id = ?, schema_version = COALESCE(schema_version, 1),
                updated_at = COALESCE(updated_at, created_at)
            WHERE id = ?
            """,
            (platform, url, source_id, venue_id, row["id"]),
        )
        catalogues_updated += 1
    return {"catalogues_updated": catalogues_updated, "venues_created": venues_created, "rows": len(rows)}


def _record_migration(connection: sqlite3.Connection, status: str, detail: dict[str, Any]) -> None:
    connection.execute(
        """
        INSERT INTO schema_migrations (id, applied_at, status, detail)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET applied_at = excluded.applied_at, status = excluded.status, detail = excluded.detail
        """,
        (MIGRATION_ID, _utcnow(), status, json.dumps(detail, ensure_ascii=False)),
    )


def _finish_migration(connection: sqlite3.Connection, detail: dict[str, Any]) -> str:
    duplicates = _duplicate_groups(connection)
    detail["duplicate_groups"] = duplicates
    if duplicates:
        detail["indexes_skipped"] = True
        detail["indexes_created"] = []
        logger.warning(
            "Phase 1 migration %s is partial: %s duplicate ok-catalogue group(s). Unique indexes were not created. Data was preserved.",
            MIGRATION_ID,
            len(duplicates),
        )
        return "partial"
    detail["indexes_skipped"] = False
    detail["indexes_created"] = _create_unique_indexes(connection)
    return "applied"


def migrate_catalogue_db(path: Path | None = None) -> dict[str, Any]:
    """Explicit, idempotent, non-destructive Phase 1 schema migration.

    A completed ``applied`` migration is recorded in ``schema_migrations``. Later
    calls (including API startup) skip the catalogue backfill. A ``partial``
    migration also skips backfill and only retries unique-index creation.
    Re-run ``python -m backend.migrate_catalogues`` at any time; it is a no-op
    when already applied.
    """
    db_path = path or catalogue_db_path()
    connection = connect_catalogue_db(db_path)
    detail: dict[str, Any] = {"indexes_created": [], "indexes_skipped": False, "duplicate_groups": []}
    status = "applied"
    skipped = False
    backfilled = False
    try:
        connection.execute("BEGIN IMMEDIATE")
        ensure_phase1_ddl(connection)
        ensure_phase3_ddl(connection)
        ensure_phase4_ddl(connection)
        ensure_phase6_ddl(connection)
        ensure_phase7_ddl(connection)
        ensure_phase8_ddl(connection)
        ensure_phase10_ddl(connection)
        ensure_phase11_history_ddl(connection)
        existing = connection.execute(
            "SELECT status, detail FROM schema_migrations WHERE id = ?",
            (MIGRATION_ID,),
        ).fetchone()
        if existing is not None and existing["status"] == "applied":
            skipped = True
            prior = json.loads(existing["detail"]) if existing["detail"] else {}
            if isinstance(prior, dict):
                detail = prior
            connection.execute("COMMIT")
        elif existing is not None:
            skipped = True
            prior = json.loads(existing["detail"]) if existing["detail"] else {}
            if isinstance(prior, dict):
                detail = {**prior, **detail}
            status = _finish_migration(connection, detail)
            _record_migration(connection, status, detail)
            connection.execute("COMMIT")
        else:
            backfilled = True
            detail.update(_backfill(connection))
            status = _finish_migration(connection, detail)
            _record_migration(connection, status, detail)
            connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()
    logger.info(
        "Phase 1 migration %s status=%s skipped=%s backfilled=%s detail=%s",
        MIGRATION_ID,
        status,
        skipped,
        backfilled,
        detail,
    )
    return {
        "id": MIGRATION_ID,
        "status": status,
        "skipped": skipped,
        "backfilled": backfilled,
        "detail": detail,
        "path": str(db_path),
    }


def migration_status(path: Path | None = None) -> dict[str, Any] | None:
    db_path = path or catalogue_db_path()
    if not db_path.exists():
        return None
    connection = connect_catalogue_db(db_path)
    try:
        ensure_phase1_ddl(connection)
        ensure_phase3_ddl(connection)
        ensure_phase4_ddl(connection)
        ensure_phase6_ddl(connection)
        ensure_phase7_ddl(connection)
        ensure_phase8_ddl(connection)
        ensure_phase10_ddl(connection)
        ensure_phase11_history_ddl(connection)
        connection.commit()
        row = connection.execute("SELECT id, applied_at, status, detail FROM schema_migrations WHERE id = ?", (MIGRATION_ID,)).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    return {
        "id": row["id"],
        "applied_at": row["applied_at"],
        "status": row["status"],
        "detail": json.loads(row["detail"]),
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    result = migrate_catalogue_db()
    print(json.dumps(result, indent=2))
    if result["status"] != "applied":
        raise SystemExit(2)


if __name__ == "__main__":
    main()

"""Persist Phase 8 reviews and analyses. Never writes catalogues.payload."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone

from backend.migrate_catalogues import connect_catalogue_db, ensure_phase8_ddl
from backend.review_intel.contract import (
    ANALYSIS_CONTRACT,
    ENGINE_VERSION,
    ReviewIntelligence,
    StoredReview,
)
from backend.schemas import CatalogCreateResponse


RESERVATION_STATUS = "GENERATING"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def reservation_age_seconds(created_at: str) -> float:
    started = datetime.fromisoformat(created_at)
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - started).total_seconds()


def connect() -> sqlite3.Connection:
    connection = connect_catalogue_db()
    ensure_phase8_ddl(connection)
    return connection


def begin_immediate(connection: sqlite3.Connection) -> None:
    connection.isolation_level = None
    connection.execute("BEGIN IMMEDIATE")


def new_id() -> str:
    return str(uuid.uuid4())


def derived_external_id(*, body: str, posted_at: str | None, author_key: str | None) -> str:
    payload = {"body": body, "posted_at": posted_at or "", "author_key": author_key or ""}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return f"derived:{digest}"


def customer_author_key(user_id: str) -> str:
    digest = hashlib.sha256(f"customer:{user_id}".encode("utf-8")).hexdigest()
    return digest[:32]


def get_review_by_photo(
    connection: sqlite3.Connection,
    *,
    catalogue_id: str,
    user_id: str,
    organization_id: str,
    photo_id: str,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT * FROM catalogue_reviews
        WHERE catalogue_id = ? AND user_id = ? AND organization_id = ? AND photo_id = ?
        """,
        (catalogue_id, user_id, organization_id, photo_id),
    ).fetchone()


def analysis_request_key(
    *,
    catalogue_id: str,
    source_head_revision: int,
    source_state_hash: str,
    reviews_fingerprint: str,
) -> str:
    payload = {
        "catalogue_id": catalogue_id,
        "source_head_revision": source_head_revision,
        "source_state_hash": source_state_hash,
        "reviews_fingerprint": reviews_fingerprint,
        "engine_version": ENGINE_VERSION,
        "analysis_contract": ANALYSIS_CONTRACT,
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def insert_review(connection: sqlite3.Connection, *, user_id: str, review: StoredReview) -> None:
    connection.execute(
        """
        INSERT INTO catalogue_reviews (
            id, catalogue_id, user_id, organization_id, source, external_id,
            body, posted_at, author_key, observed_rating, photo_id, payload, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            review.id,
            review.catalogue_id,
            user_id,
            review.organization_id,
            review.source,
            review.external_id,
            review.body,
            review.posted_at,
            review.author_key,
            review.observed_rating,
            review.photo_id,
            json.dumps(review.model_dump(mode="json"), ensure_ascii=False),
            review.created_at,
        ),
    )


def get_review_by_external(
    connection: sqlite3.Connection,
    *,
    catalogue_id: str,
    organization_id: str,
    source: str,
    external_id: str,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT * FROM catalogue_reviews
        WHERE catalogue_id = ? AND organization_id = ? AND source = ? AND external_id = ?
        """,
        (catalogue_id, organization_id, source, external_id),
    ).fetchone()


def load_catalogue_result(
    connection: sqlite3.Connection,
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
) -> CatalogCreateResponse:
    row = connection.execute(
        """
        SELECT payload FROM catalogues
        WHERE id = ? AND user_id = ? AND organization_id = ?
        """,
        (catalogue_id, user_id, organization_id),
    ).fetchone()
    if row is None:
        raise KeyError("Catalogue not found for this restaurant organization.")
    return CatalogCreateResponse.model_validate(json.loads(row["payload"]))


def count_reviews(
    connection: sqlite3.Connection,
    *,
    catalogue_id: str,
    user_id: str,
    organization_id: str,
) -> int:
    row = connection.execute(
        """
        SELECT COUNT(*) AS n FROM catalogue_reviews
        WHERE catalogue_id = ? AND user_id = ? AND organization_id = ?
        """,
        (catalogue_id, user_id, organization_id),
    ).fetchone()
    return int(row["n"] if row else 0)


def list_review_rows(
    connection: sqlite3.Connection,
    *,
    catalogue_id: str,
    user_id: str,
    organization_id: str,
    limit: int,
    offset: int,
) -> tuple[int, list[sqlite3.Row]]:
    total_row = connection.execute(
        """
        SELECT COUNT(*) AS n FROM catalogue_reviews
        WHERE catalogue_id = ? AND user_id = ? AND organization_id = ?
        """,
        (catalogue_id, user_id, organization_id),
    ).fetchone()
    rows = connection.execute(
        """
        SELECT * FROM catalogue_reviews
        WHERE catalogue_id = ? AND user_id = ? AND organization_id = ?
        ORDER BY created_at ASC, id ASC
        LIMIT ? OFFSET ?
        """,
        (catalogue_id, user_id, organization_id, limit, offset),
    ).fetchall()
    return int(total_row["n"] if total_row else 0), list(rows)


def list_all_reviews(
    connection: sqlite3.Connection,
    *,
    catalogue_id: str,
    user_id: str,
    organization_id: str,
) -> list[StoredReview]:
    rows = connection.execute(
        """
        SELECT payload FROM catalogue_reviews
        WHERE catalogue_id = ? AND user_id = ? AND organization_id = ?
        ORDER BY created_at ASC, id ASC
        """,
        (catalogue_id, user_id, organization_id),
    ).fetchall()
    return [StoredReview.model_validate(json.loads(row["payload"])) for row in rows]


def row_to_review(row: sqlite3.Row) -> StoredReview:
    return StoredReview.model_validate(json.loads(row["payload"]))


def get_analysis_by_key(connection: sqlite3.Connection, request_key_value: str) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT * FROM catalogue_review_analyses WHERE request_key = ?",
        (request_key_value,),
    ).fetchone()


def latest_analysis_row(
    connection: sqlite3.Connection,
    *,
    catalogue_id: str,
    user_id: str,
    organization_id: str,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT * FROM catalogue_review_analyses
        WHERE catalogue_id = ? AND user_id = ? AND organization_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (catalogue_id, user_id, organization_id),
    ).fetchone()


def insert_analysis_reservation(
    connection: sqlite3.Connection,
    *,
    request_key_value: str,
    user_id: str,
    claim_token: str,
    analysis: ReviewIntelligence,
) -> None:
    payload = analysis.model_dump(mode="json")
    connection.execute(
        """
        INSERT INTO catalogue_review_analyses (
            id, request_key, catalogue_id, user_id, organization_id,
            source_head_revision, source_state_hash, reviews_fingerprint,
            status, claim_token, payload, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            analysis.id,
            request_key_value,
            analysis.catalogue_id,
            user_id,
            analysis.organization_id,
            analysis.source_head_revision,
            analysis.source_state_hash,
            analysis.reviews_fingerprint,
            RESERVATION_STATUS,
            claim_token,
            json.dumps(payload, ensure_ascii=False),
            analysis.created_at,
            analysis.updated_at,
        ),
    )


def reclaim_analysis(
    connection: sqlite3.Connection,
    *,
    analysis_id: str,
    from_status: str,
    claim_token: str,
    analysis: ReviewIntelligence,
) -> int:
    payload = analysis.model_dump(mode="json")
    cursor = connection.execute(
        """
        UPDATE catalogue_review_analyses
        SET status = ?, claim_token = ?, payload = ?, updated_at = ?
        WHERE id = ? AND status = ?
        """,
        (
            RESERVATION_STATUS,
            claim_token,
            json.dumps(payload, ensure_ascii=False),
            analysis.updated_at,
            analysis_id,
            from_status,
        ),
    )
    return int(cursor.rowcount)


def cas_finish_analysis(
    connection: sqlite3.Connection,
    *,
    analysis_id: str,
    claim_token: str,
    analysis: ReviewIntelligence,
) -> int:
    payload = analysis.model_dump(mode="json")
    cursor = connection.execute(
        """
        UPDATE catalogue_review_analyses
        SET status = ?, payload = ?, updated_at = ?, claim_token = claim_token
        WHERE id = ? AND status = ? AND claim_token = ?
        """,
        (
            analysis.status,
            json.dumps(payload, ensure_ascii=False),
            analysis.updated_at,
            analysis_id,
            RESERVATION_STATUS,
            claim_token,
        ),
    )
    return int(cursor.rowcount)


def analysis_from_row(
    row: sqlite3.Row,
    *,
    current_revision: int,
    current_hash: str,
    current_fingerprint: str,
    replay: bool = False,
) -> ReviewIntelligence:
    analysis = ReviewIntelligence.model_validate(json.loads(row["payload"]))
    stale = (
        int(row["source_head_revision"]) != current_revision
        or str(row["source_state_hash"]) != current_hash
        or str(row["reviews_fingerprint"]) != current_fingerprint
        or str(analysis.engine_version) != ENGINE_VERSION
    )
    updates: dict = {}
    if stale:
        updates["status"] = "STALE"
    if replay:
        updates["idempotent_replay"] = True
    if updates:
        analysis = analysis.model_copy(update=updates)
    return analysis

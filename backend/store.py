from __future__ import annotations

import json
import os
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scraper.swiggy.assets import materialize_catalogue_images, remove_owned_catalogue_assets
from backend.canonical.adapter import to_canonical_from_response
from backend.canonical.fingerprint import canonical_state_equal
from backend.canonical.identity import (
    SCHEMA_VERSION,
    assign_item_ids,
    identity_tuple,
    previous_item_id_map,
    source_entity_id_from_result,
)
from backend.canonical.project import apply_canonical_to_response
from backend.migrate_catalogues import connect_catalogue_db, ensure_phase1_ddl, ensure_phase3_ddl, ensure_phase4_ddl
from backend.schemas import CatalogCreateResponse, StoredCatalogue
from scraper.discovery.models import DiscoveredVenue
from scraper.discovery.queue import claim_next_batch, finalize_status, job_from_dict, job_to_dict, utcnow, venue_match_key
from scraper.discovery.urls import canonical_url

DEFAULT_DB = "data/catalogues.sqlite"


class CatalogueIdentityConflict(ValueError):
    """URL identity and source-entity identity point at different catalogues."""

    def __init__(self, *, url_catalogue_id: str, entity_catalogue_id: str):
        self.url_catalogue_id = url_catalogue_id
        self.entity_catalogue_id = entity_catalogue_id
        super().__init__(
            "Catalogue identity conflict: canonical URL resolves to catalogue "
            f"{url_catalogue_id} while source entity ID resolves to catalogue {entity_catalogue_id}."
        )


def catalogue_db_path() -> Path:
    return Path(os.getenv("CATALOGFORGE_CATALOGUE_DB", DEFAULT_DB))


def _connect() -> sqlite3.Connection:
    connection = connect_catalogue_db()
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
    ensure_phase1_ddl(connection)
    ensure_phase3_ddl(connection)
    ensure_phase4_ddl(connection)
    connection.commit()
    return connection


def _result_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict) and isinstance(value.get("result"), dict):
        return value["result"]
    return value if isinstance(value, dict) else {}


def _stored_restaurant_id(result: dict[str, Any]) -> str:
    return source_entity_id_from_result(result) or ""


def identity_from_result(result: CatalogCreateResponse) -> tuple[str, str, str]:
    platform, source_url, source_id = identity_tuple(result.model_dump(mode="json"))
    return platform, source_url, source_id or ""


def catalogues_match_identity(
    stored: dict[str, Any],
    *,
    platform: str,
    source_url: str,
    restaurant_id: str = "",
) -> bool:
    result = _result_dict(stored)
    stored_platform = (result.get("platform") or "").strip().lower()
    incoming_platform = (platform or "").strip().lower()
    if stored_platform and incoming_platform and stored_platform != incoming_platform:
        return False
    stored_url = canonical_url(str(result.get("source_url") or ""))
    incoming_url = canonical_url(source_url)
    if incoming_url and stored_url and incoming_url == stored_url:
        return True
    stored_id = _stored_restaurant_id(result)
    incoming_id = (restaurant_id or "").strip().lower()
    return bool(incoming_id and stored_id and incoming_id == stored_id)


def catalogues_match_url(
    stored: dict[str, Any],
    *,
    platform: str,
    source_url: str,
) -> bool:
    result = _result_dict(stored)
    stored_platform = (result.get("platform") or "").strip().lower()
    incoming_platform = (platform or "").strip().lower()
    if stored_platform and incoming_platform and stored_platform != incoming_platform:
        return False
    stored_url = canonical_url(str(result.get("source_url") or ""))
    incoming_url = canonical_url(source_url)
    return bool(incoming_url and stored_url and incoming_url == stored_url)


def catalogues_match_entity(
    stored: dict[str, Any],
    *,
    platform: str,
    restaurant_id: str,
) -> bool:
    result = _result_dict(stored)
    stored_platform = (result.get("platform") or "").strip().lower()
    incoming_platform = (platform or "").strip().lower()
    if stored_platform and incoming_platform and stored_platform != incoming_platform:
        return False
    stored_id = _stored_restaurant_id(result)
    incoming_id = (restaurant_id or "").strip().lower()
    return bool(incoming_id and stored_id and incoming_id == stored_id)


def _row_id(row: sqlite3.Row | dict[str, Any]) -> str:
    if isinstance(row, dict):
        result = _result_dict(row)
        return str(row.get("id") or result.get("id") or "").strip()
    return str(row["id"]).strip()


def _row_status(row: sqlite3.Row | dict[str, Any]) -> str:
    if isinstance(row, dict):
        result = _result_dict(row)
        return str(row.get("extraction_status") or result.get("extraction_status") or "")
    return str(row["extraction_status"] or "")


def _prefer_ok_match(rows: list[Any]) -> Any | None:
    if not rows:
        return None
    for row in rows:
        if _row_status(row) == "ok":
            return row
    return rows[0]


def _raise_if_identity_conflict(url_match: Any | None, entity_match: Any | None) -> None:
    if url_match is None or entity_match is None:
        return
    url_id = _row_id(url_match)
    entity_id = _row_id(entity_match)
    if url_id and entity_id and url_id != entity_id:
        raise CatalogueIdentityConflict(url_catalogue_id=url_id, entity_catalogue_id=entity_id)


def _lift_source_identity(result: CatalogCreateResponse) -> CatalogCreateResponse:
    payload = result.model_dump(mode="json")
    source_id = source_entity_id_from_result(payload)
    restaurant = payload.get("restaurant") if isinstance(payload.get("restaurant"), dict) else {}
    if source_id and restaurant.get("restaurant_id") != source_id:
        restaurant = {**restaurant, "restaurant_id": source_id}
        result = result.model_copy(update={"restaurant": restaurant})
    return result


def _with_item_ids(result: CatalogCreateResponse, previous: CatalogCreateResponse | None = None) -> CatalogCreateResponse:
    mapping = previous_item_id_map(previous.categories if previous else None)
    categories = assign_item_ids(result.categories, previous=mapping)
    return result.model_copy(update={"categories": categories})


def _stamp_canonical(
    result: CatalogCreateResponse,
    *,
    venue_id: str | None,
    imported_at: str,
) -> CatalogCreateResponse:
    document = to_canonical_from_response(result)
    document.venue_id = venue_id
    document.provenance.imported_at = imported_at
    stamped = apply_canonical_to_response(result, document)
    return stamped.model_copy(
        update={
            "venue_id": venue_id,
            "schema_version": SCHEMA_VERSION,
            "updated_at": imported_at,
        }
    )


def matching_catalogue_id(
    catalogues: list[dict[str, Any]],
    *,
    platform: str,
    source_url: str,
    restaurant_id: str = "",
) -> str | None:
    url_match = None
    entity_match = None
    if canonical_url(source_url):
        url_match = _prefer_ok_match(
            [row for row in catalogues if catalogues_match_url(row, platform=platform, source_url=source_url)]
        )
    if (restaurant_id or "").strip():
        entity_match = _prefer_ok_match(
            [row for row in catalogues if catalogues_match_entity(row, platform=platform, restaurant_id=restaurant_id)]
        )
    _raise_if_identity_conflict(url_match, entity_match)
    chosen = url_match or entity_match
    if chosen is None:
        return None
    row_id = _row_id(chosen)
    return row_id or None


def save_catalogue(
    *,
    user_id: str,
    organization_id: str,
    result: CatalogCreateResponse,
) -> StoredCatalogue:
    organization_id = (organization_id or result.organization_id or "").strip()
    result = _lift_source_identity(result)
    platform, source_url, restaurant_id = identity_from_result(result)
    peek = None
    if result.extraction_status == "ok":
        peek = _peek_matching_catalogue(user_id, organization_id, platform, source_url, restaurant_id)
    if peek is not None:
        catalogue_id = peek[0]
        created_at = peek[1]
    else:
        catalogue_id = result.id or str(uuid.uuid4())
        created_at = result.created_at or datetime.now(timezone.utc).isoformat()
    result.id = catalogue_id
    result.organization_id = organization_id or None
    result.created_at = created_at
    payload = result.model_dump(mode="json")
    materialize_catalogue_images(payload, catalogue_id)
    result = CatalogCreateResponse.model_validate(payload)
    result = _lift_source_identity(result)
    result.id = catalogue_id
    result.organization_id = organization_id or None
    result.created_at = created_at
    connection = _connect()
    try:
        _begin_immediate(connection)
        try:
            stored = _persist_catalogue_locked(
                connection,
                user_id=user_id,
                organization_id=organization_id,
                result=result,
                catalogue_id=catalogue_id,
                created_at=created_at,
                platform=platform,
                source_url=source_url,
                restaurant_id=restaurant_id,
            )
        except sqlite3.IntegrityError:
            connection.execute("ROLLBACK")
            _begin_immediate(connection)
            stored = _persist_catalogue_locked(
                connection,
                user_id=user_id,
                organization_id=organization_id,
                result=result,
                catalogue_id=catalogue_id,
                created_at=created_at,
                platform=platform,
                source_url=source_url,
                restaurant_id=restaurant_id,
            )
        connection.execute("COMMIT")
        return stored
    except Exception:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        connection.close()


def _empty_to_null(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


def _row_venue_id(row: sqlite3.Row | None) -> str | None:
    if row is None:
        return None
    try:
        value = row["venue_id"]
    except (KeyError, IndexError):
        return None
    return _empty_to_null(str(value) if value is not None else None)


def _persist_catalogue_locked(
    connection: sqlite3.Connection,
    *,
    user_id: str,
    organization_id: str,
    result: CatalogCreateResponse,
    catalogue_id: str,
    created_at: str,
    platform: str,
    source_url: str,
    restaurant_id: str,
) -> StoredCatalogue:
    match = _matching_catalogue_row(connection, user_id, organization_id, platform, source_url, restaurant_id)
    imported_at = datetime.now(timezone.utc).isoformat()
    if result.extraction_status == "ok" and match is not None:
        catalogue_id = match["id"]
        created_at = match["created_at"]
        existing = CatalogCreateResponse.model_validate(json.loads(match["payload"]))
        result.id = catalogue_id
        result.organization_id = organization_id or None
        result.created_at = created_at
        result = _with_item_ids(result, existing if existing.extraction_status == "ok" else None)
        venue_id = _upsert_venue(
            connection,
            user_id=user_id,
            organization_id=organization_id,
            platform=platform,
            source_url=source_url,
            restaurant_id=restaurant_id,
            name=result.restaurant_name,
            existing_venue_id=_row_venue_id(match),
            created_at=created_at,
            imported_at=imported_at,
        )
        result = _stamp_canonical(result, venue_id=venue_id, imported_at=imported_at)
        if str(match["extraction_status"]) == "ok" and canonical_state_equal(result, existing):
            return StoredCatalogue(id=catalogue_id, organization_id=organization_id, created_at=created_at, result=existing)
        if str(match["extraction_status"]) == "ok":
            _insert_revision(connection, catalogue_id, match["payload"], imported_at)
        _write_catalogue_update(
            connection,
            user_id=user_id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
            result=result,
            platform=platform,
            source_url=source_url or None,
            restaurant_id=restaurant_id or None,
            venue_id=venue_id,
            imported_at=imported_at,
        )
        return StoredCatalogue(id=catalogue_id, organization_id=organization_id, created_at=created_at, result=result)

    if match is not None and str(match["extraction_status"]) == "ok" and catalogue_id == match["id"]:
        catalogue_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        result.id = catalogue_id
        result.organization_id = organization_id or None
        result.created_at = created_at
    result = _with_item_ids(result)
    venue_id = _upsert_venue(
        connection,
        user_id=user_id,
        organization_id=organization_id,
        platform=platform,
        source_url=source_url,
        restaurant_id=restaurant_id,
        name=result.restaurant_name,
        existing_venue_id=_row_venue_id(match),
        created_at=created_at,
        imported_at=imported_at,
    )
    result = _stamp_canonical(result, venue_id=venue_id, imported_at=imported_at)
    _insert_catalogue(
        connection,
        user_id=user_id,
        organization_id=organization_id,
        catalogue_id=catalogue_id,
        created_at=created_at,
        result=result,
        platform=platform,
        source_url=source_url or None,
        restaurant_id=restaurant_id or None,
        venue_id=venue_id,
        imported_at=imported_at,
    )
    return StoredCatalogue(id=catalogue_id, organization_id=organization_id, created_at=created_at, result=result)


def _write_catalogue_update(
    connection: sqlite3.Connection,
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
    result: CatalogCreateResponse,
    platform: str,
    source_url: str | None,
    restaurant_id: str | None,
    venue_id: str | None,
    imported_at: str,
) -> None:
    payload = json.dumps(result.model_dump(mode="json"), ensure_ascii=False)
    connection.execute(
        """
        UPDATE catalogues
        SET extraction_status = ?, payload = ?, platform = ?, canonical_source_url = ?,
            source_entity_id = ?, venue_id = ?, schema_version = ?, updated_at = ?
        WHERE id = ? AND user_id = ? AND organization_id = ?
        """,
        (
            result.extraction_status,
            payload,
            platform,
            _empty_to_null(source_url),
            _empty_to_null(restaurant_id),
            venue_id,
            SCHEMA_VERSION,
            imported_at,
            catalogue_id,
            user_id,
            organization_id,
        ),
    )


def _insert_catalogue(
    connection: sqlite3.Connection,
    *,
    user_id: str,
    organization_id: str,
    catalogue_id: str,
    created_at: str,
    result: CatalogCreateResponse,
    platform: str,
    source_url: str | None,
    restaurant_id: str | None,
    venue_id: str | None,
    imported_at: str,
) -> None:
    payload = json.dumps(result.model_dump(mode="json"), ensure_ascii=False)
    connection.execute(
        """
        INSERT INTO catalogues (
            id, user_id, organization_id, created_at, extraction_status, payload,
            platform, canonical_source_url, source_entity_id, venue_id, schema_version, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            catalogue_id,
            user_id,
            organization_id,
            created_at,
            result.extraction_status,
            payload,
            platform,
            _empty_to_null(source_url),
            _empty_to_null(restaurant_id),
            venue_id,
            SCHEMA_VERSION,
            imported_at,
        ),
    )


def _insert_revision(connection: sqlite3.Connection, catalogue_id: str, previous_payload: str, captured_at: str) -> None:
    row = connection.execute(
        "SELECT COALESCE(MAX(revision), 0) AS n FROM catalogue_revisions WHERE catalogue_id = ?",
        (catalogue_id,),
    ).fetchone()
    revision = int(row["n"] if row else 0) + 1
    connection.execute(
        """
        INSERT INTO catalogue_revisions (id, catalogue_id, revision, captured_at, payload)
        VALUES (?, ?, ?, ?, ?)
        """,
        (str(uuid.uuid4()), catalogue_id, revision, captured_at, previous_payload),
    )


def _upsert_venue(
    connection: sqlite3.Connection,
    *,
    user_id: str,
    organization_id: str,
    platform: str,
    source_url: str,
    restaurant_id: str,
    name: str,
    existing_venue_id: str | None,
    created_at: str,
    imported_at: str,
) -> str:
    entity = _empty_to_null(restaurant_id)
    url = _empty_to_null(source_url)
    found = None
    if entity:
        found = connection.execute(
            """
            SELECT venue_id FROM venue_sources
            WHERE user_id = ? AND organization_id = ? AND platform = ? AND source_entity_id = ?
            """,
            (user_id, organization_id, platform, entity),
        ).fetchone()
    if found is None and url:
        found = connection.execute(
            """
            SELECT venue_id FROM venue_sources
            WHERE user_id = ? AND organization_id = ? AND platform = ? AND canonical_source_url = ?
            """,
            (user_id, organization_id, platform, url),
        ).fetchone()
    venue_id = (found["venue_id"] if found else None) or existing_venue_id
    if venue_id:
        updated = connection.execute(
            "UPDATE venues SET updated_at = ?, name = COALESCE(?, name) WHERE id = ? AND user_id = ? AND organization_id = ?",
            (imported_at, name or None, venue_id, user_id, organization_id),
        )
        if updated.rowcount == 0:
            connection.execute(
                """
                INSERT INTO venues (id, user_id, organization_id, created_at, updated_at, name)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (venue_id, user_id, organization_id, created_at, imported_at, name or None),
            )
        source = connection.execute(
            "SELECT id FROM venue_sources WHERE venue_id = ? AND user_id = ? AND organization_id = ? AND platform = ?",
            (venue_id, user_id, organization_id, platform),
        ).fetchone()
        if source is None:
            connection.execute(
                """
                INSERT INTO venue_sources (
                    id, venue_id, user_id, organization_id, platform, source_entity_id, canonical_source_url, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), venue_id, user_id, organization_id, platform, entity, url, created_at),
            )
        else:
            connection.execute(
                """
                UPDATE venue_sources
                SET source_entity_id = COALESCE(source_entity_id, ?), canonical_source_url = COALESCE(canonical_source_url, ?)
                WHERE id = ?
                """,
                (entity, url, source["id"]),
            )
        return venue_id
    venue_id = str(uuid.uuid4())
    connection.execute(
        """
        INSERT INTO venues (id, user_id, organization_id, created_at, updated_at, name)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (venue_id, user_id, organization_id, created_at, imported_at, name or None),
    )
    connection.execute(
        """
        INSERT INTO venue_sources (
            id, venue_id, user_id, organization_id, platform, source_entity_id, canonical_source_url, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (str(uuid.uuid4()), venue_id, user_id, organization_id, platform, entity, url, created_at),
    )
    return venue_id


def _catalogue_scope_rows(
    connection: sqlite3.Connection, user_id: str, organization_id: str
) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT id, created_at, extraction_status, payload, venue_id
        FROM catalogues
        WHERE user_id = ? AND organization_id = ?
        ORDER BY created_at DESC
        """,
        (user_id, organization_id),
    ).fetchall()


def _row_as_match_dict(row: sqlite3.Row) -> dict[str, Any]:
    payload = json.loads(row["payload"])
    return {
        "id": row["id"],
        "extraction_status": row["extraction_status"],
        "result": payload if isinstance(payload, dict) else {},
    }


def _select_url_row(
    rows: list[sqlite3.Row],
    *,
    platform: str,
    source_url: str,
) -> sqlite3.Row | None:
    return _prefer_ok_match(
        [row for row in rows if catalogues_match_url(_row_as_match_dict(row), platform=platform, source_url=source_url)]
    )


def _select_entity_row(
    rows: list[sqlite3.Row],
    *,
    platform: str,
    restaurant_id: str,
) -> sqlite3.Row | None:
    return _prefer_ok_match(
        [
            row
            for row in rows
            if catalogues_match_entity(_row_as_match_dict(row), platform=platform, restaurant_id=restaurant_id)
        ]
    )


def _matching_catalogue_row(
    connection: sqlite3.Connection,
    user_id: str,
    organization_id: str,
    platform: str,
    source_url: str,
    restaurant_id: str,
) -> sqlite3.Row | None:
    url = (source_url or "").strip()
    entity = (restaurant_id or "").strip()
    url_match: sqlite3.Row | None = None
    entity_match: sqlite3.Row | None = None
    if url:
        url_match = _select_url_row(
            connection.execute(
                """
                SELECT id, created_at, extraction_status, payload, venue_id
                FROM catalogues
                WHERE user_id = ? AND organization_id = ? AND platform = ? AND canonical_source_url = ?
                """,
                (user_id, organization_id, platform, url),
            ).fetchall(),
            platform=platform,
            source_url=source_url,
        )
    if entity:
        entity_match = _select_entity_row(
            connection.execute(
                """
                SELECT id, created_at, extraction_status, payload, venue_id
                FROM catalogues
                WHERE user_id = ? AND organization_id = ? AND platform = ? AND source_entity_id = ?
                """,
                (user_id, organization_id, platform, entity),
            ).fetchall(),
            platform=platform,
            restaurant_id=restaurant_id,
        )
    if (url and url_match is None) or (entity and entity_match is None):
        scope = _catalogue_scope_rows(connection, user_id, organization_id)
        if url and url_match is None:
            url_match = _select_url_row(scope, platform=platform, source_url=source_url)
        if entity and entity_match is None:
            entity_match = _select_entity_row(scope, platform=platform, restaurant_id=restaurant_id)
    _raise_if_identity_conflict(url_match, entity_match)
    return url_match or entity_match


def _peek_matching_catalogue(
    user_id: str,
    organization_id: str,
    platform: str,
    source_url: str,
    restaurant_id: str,
) -> tuple[str, str] | None:
    connection = _connect()
    try:
        row = _matching_catalogue_row(connection, user_id, organization_id, platform, source_url, restaurant_id)
        if row is None:
            return None
        return row["id"], row["created_at"]
    finally:
        connection.close()


def _compact_stored(row: StoredCatalogue) -> StoredCatalogue:
    payload = row.result.model_dump()
    payload["categories"] = []
    dineout = payload.get("dineout")
    if isinstance(dineout, dict):
        for key in ("photos", "gallery_images", "menu_pages", "videos"):
            dineout.pop(key, None)
        payload["dineout"] = dineout
    return StoredCatalogue(
        id=row.id,
        organization_id=row.organization_id,
        created_at=row.created_at,
        result=CatalogCreateResponse.model_validate(payload),
    )


def list_catalogues(user_id: str, organization_id: str, *, compact: bool = False) -> list[StoredCatalogue]:
    connection = _connect()
    try:
        rows = connection.execute(
            """
            SELECT id, organization_id, created_at, payload
            FROM catalogues
            WHERE user_id = ? AND organization_id = ?
            ORDER BY created_at DESC
            """,
            (user_id, organization_id),
        ).fetchall()
    finally:
        connection.close()
    stored = [_row_to_stored(row) for row in rows]
    if compact:
        return [_compact_stored(row) for row in stored]
    return stored


def delete_catalogue(user_id: str, catalogue_id: str, organization_id: str) -> bool:
    deleted = False
    connection = _connect()
    try:
        row = connection.execute(
            """
            SELECT venue_id FROM catalogues
            WHERE id = ? AND user_id = ? AND organization_id = ?
            """,
            (catalogue_id, user_id, organization_id),
        ).fetchone()
        connection.execute("DELETE FROM catalogue_grade_jobs WHERE catalogue_id = ?", (catalogue_id,))
        connection.execute("DELETE FROM catalogue_grades WHERE catalogue_id = ?", (catalogue_id,))
        connection.execute("DELETE FROM catalogue_platform_evaluations WHERE catalogue_id = ?", (catalogue_id,))
        connection.execute("DELETE FROM catalogue_media_artifacts WHERE catalogue_id = ?", (catalogue_id,))
        connection.execute("DELETE FROM catalogue_media_jobs WHERE catalogue_id = ?", (catalogue_id,))
        connection.execute("DELETE FROM catalogue_review_analyses WHERE catalogue_id = ?", (catalogue_id,))
        connection.execute("DELETE FROM catalogue_reviews WHERE catalogue_id = ?", (catalogue_id,))
        connection.execute(
            "DELETE FROM catalogue_media_workspaces WHERE catalogue_id = ? AND user_id = ? AND organization_id = ?",
            (catalogue_id, user_id, organization_id),
        )
        connection.execute("DELETE FROM catalogue_revisions WHERE catalogue_id = ?", (catalogue_id,))
        cursor = connection.execute(
            """
            DELETE FROM catalogues
            WHERE id = ? AND user_id = ? AND organization_id = ?
            """,
            (catalogue_id, user_id, organization_id),
        )
        venue_id = _row_venue_id(row)
        if venue_id:
            remaining = connection.execute(
                "SELECT 1 FROM catalogues WHERE venue_id = ? AND user_id = ? AND organization_id = ? LIMIT 1",
                (venue_id, user_id, organization_id),
            ).fetchone()
            if remaining is None:
                connection.execute(
                    "DELETE FROM venue_sources WHERE venue_id = ? AND user_id = ? AND organization_id = ?",
                    (venue_id, user_id, organization_id),
                )
                connection.execute(
                    "DELETE FROM venues WHERE id = ? AND user_id = ? AND organization_id = ?",
                    (venue_id, user_id, organization_id),
                )
        connection.commit()
        deleted = cursor.rowcount > 0
    finally:
        connection.close()
    if deleted:
        remove_owned_catalogue_assets(catalogue_id)
        try:
            from backend.media.persist import generated_root
            from backend.media.source import MediaSourceError, confined_generated_path

            dest = confined_generated_path(generated_root(), [user_id, organization_id, catalogue_id])
            if dest.is_dir():
                shutil.rmtree(dest, ignore_errors=True)
        except (MediaSourceError, OSError):
            pass
        try:
            from backend.review_intel.evidence import remove_catalogue_evidence

            remove_catalogue_evidence(user_id=user_id, organization_id=organization_id, catalogue_id=catalogue_id)
        except OSError:
            pass
    return deleted


def get_catalogue(user_id: str, catalogue_id: str, organization_id: str) -> StoredCatalogue | None:
    connection = _connect()
    try:
        row = connection.execute(
            """
            SELECT id, organization_id, created_at, payload
            FROM catalogues
            WHERE id = ? AND user_id = ? AND organization_id = ?
            """,
            (catalogue_id, user_id, organization_id),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    return _row_to_stored(row)


def update_catalogue(
    *,
    user_id: str,
    catalogue_id: str,
    organization_id: str,
    result: CatalogCreateResponse,
) -> StoredCatalogue | None:
    existing = get_catalogue(user_id, catalogue_id, organization_id)
    if existing is None:
        return None
    result = _lift_source_identity(result)
    result.id = catalogue_id
    result.organization_id = organization_id
    result.created_at = existing.created_at
    payload = result.model_dump(mode="json")
    materialize_catalogue_images(payload, catalogue_id)
    result = CatalogCreateResponse.model_validate(payload)
    result = _lift_source_identity(result)
    result.id = catalogue_id
    result.organization_id = organization_id
    result.created_at = existing.created_at
    platform, source_url, restaurant_id = identity_from_result(result)
    imported_at = datetime.now(timezone.utc).isoformat()
    connection = _connect()
    try:
        _begin_immediate(connection)
        result = _with_item_ids(result, existing.result if existing.result.extraction_status == "ok" else None)
        venue_id = _upsert_venue(
            connection,
            user_id=user_id,
            organization_id=organization_id,
            platform=platform,
            source_url=source_url,
            restaurant_id=restaurant_id,
            name=result.restaurant_name,
            existing_venue_id=existing.result.venue_id,
            created_at=existing.created_at,
            imported_at=imported_at,
        )
        result = _stamp_canonical(result, venue_id=venue_id, imported_at=imported_at)
        if existing.result.extraction_status == "ok" and result.extraction_status == "ok" and canonical_state_equal(result, existing.result):
            connection.execute("ROLLBACK")
            return existing
        if existing.result.extraction_status == "ok" and result.extraction_status == "ok":
            _insert_revision(connection, catalogue_id, json.dumps(existing.result.model_dump(mode="json"), ensure_ascii=False), imported_at)
        _write_catalogue_update(
            connection,
            user_id=user_id,
            organization_id=organization_id,
            catalogue_id=catalogue_id,
            result=result,
            platform=platform,
            source_url=source_url or None,
            restaurant_id=restaurant_id or None,
            venue_id=venue_id,
            imported_at=imported_at,
        )
        connection.execute("COMMIT")
    except Exception:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        connection.close()
    return StoredCatalogue(
        id=catalogue_id,
        organization_id=organization_id,
        created_at=existing.created_at,
        result=result,
    )


def catalogues_as_dicts(user_id: str, organization_id: str) -> list[dict[str, Any]]:
    return [
        {"id": item.id, "result": item.result.model_dump(mode="json")}
        for item in list_catalogues(user_id, organization_id)
    ]


def save_area_job(*, user_id: str, organization_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    connection = _connect()
    try:
        connection.execute(
            """
            INSERT INTO area_jobs (id, user_id, organization_id, created_at, status, payload)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                payload["id"],
                user_id,
                organization_id,
                payload.get("created_at") or "",
                payload.get("status") or "created",
                json.dumps(payload, ensure_ascii=False),
            ),
        )
        connection.commit()
    finally:
        connection.close()
    return payload


def _area_job_row(
    connection: sqlite3.Connection, user_id: str, job_id: str, organization_id: str
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT payload FROM area_jobs
        WHERE id = ? AND user_id = ? AND organization_id = ?
        """,
        (job_id, user_id, organization_id),
    ).fetchone()


def _write_area_job(connection: sqlite3.Connection, user_id: str, payload: dict[str, Any]) -> None:
    connection.execute(
        """
        UPDATE area_jobs
        SET status = ?, payload = ?
        WHERE id = ? AND user_id = ?
        """,
        (payload.get("status") or "created", json.dumps(payload, ensure_ascii=False), payload["id"], user_id),
    )


def _begin_immediate(connection: sqlite3.Connection) -> None:
    connection.isolation_level = None
    connection.execute("BEGIN IMMEDIATE")


def claim_area_scrape_batch(*, user_id: str, organization_id: str, job_id: str) -> tuple[dict[str, Any], list[str]]:
    connection = _connect()
    try:
        _begin_immediate(connection)
        row = _area_job_row(connection, user_id, job_id, organization_id)
        if row is None:
            connection.execute("ROLLBACK")
            raise KeyError("Area job not found.")
        job = job_from_dict(json.loads(row["payload"]))
        if job.status == "cancelled":
            stored = job_to_dict(job)
            connection.execute("ROLLBACK")
            return stored, []
        claimed = claim_next_batch(job)
        previous_status = job.status
        previous_completed = job.completed_at
        job.status = finalize_status(job)
        if job.status in {"completed", "partially_completed", "failed"}:
            job.completed_at = job.completed_at or utcnow()
        stored = job_to_dict(job)
        if claimed or job.status != previous_status or job.completed_at != previous_completed:
            _write_area_job(connection, user_id, stored)
            connection.execute("COMMIT")
        else:
            connection.execute("ROLLBACK")
        return stored, [venue_match_key(item) for item in claimed]
    except Exception:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        connection.close()


def cancel_area_job_payload(*, user_id: str, organization_id: str, job_id: str) -> dict[str, Any]:
    connection = _connect()
    try:
        _begin_immediate(connection)
        row = _area_job_row(connection, user_id, job_id, organization_id)
        if row is None:
            connection.execute("ROLLBACK")
            raise KeyError("Area job not found.")
        job = job_from_dict(json.loads(row["payload"]))
        job.status = "cancelled"
        for venue in job.venues:
            if venue.status in {"queued", "discovered", "selected", "scraping"}:
                venue.status = "skipped"
                venue.error = "Cancelled"
                venue.scraping_started_at = None
        job.completed_at = job.completed_at or utcnow()
        stored = job_to_dict(job)
        _write_area_job(connection, user_id, stored)
        connection.execute("COMMIT")
        return stored
    except Exception:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        connection.close()


def merge_area_job_venue(
    *,
    user_id: str,
    organization_id: str,
    job_id: str,
    venue: DiscoveredVenue,
    claim_started_at: str,
) -> dict[str, Any]:
    connection = _connect()
    try:
        _begin_immediate(connection)
        row = _area_job_row(connection, user_id, job_id, organization_id)
        if row is None:
            connection.execute("ROLLBACK")
            raise KeyError("Area job not found.")
        job = job_from_dict(json.loads(row["payload"]))
        if job.status == "cancelled":
            stored = job_to_dict(job)
            connection.execute("ROLLBACK")
            return stored
        key = venue_match_key(venue)
        target = next((item for item in job.venues if venue_match_key(item) == key), None)
        if (
            target is None
            or target.status != "scraping"
            or target.scraping_started_at != claim_started_at
        ):
            stored = job_to_dict(job)
            connection.execute("ROLLBACK")
            return stored
        target.status = venue.status
        target.error = venue.error
        target.retry_count = venue.retry_count
        target.next_attempt_at = venue.next_attempt_at
        target.catalogue_id = venue.catalogue_id
        target.scraping_started_at = None if venue.status != "scraping" else venue.scraping_started_at
        job.status = finalize_status(job)
        if job.status in {"completed", "partially_completed", "failed"}:
            job.completed_at = job.completed_at or utcnow()
        stored = job_to_dict(job)
        _write_area_job(connection, user_id, stored)
        connection.execute("COMMIT")
        return stored
    except Exception:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        connection.close()


def update_area_job(*, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    connection = _connect()
    try:
        connection.execute(
            """
            UPDATE area_jobs
            SET status = ?, payload = ?
            WHERE id = ? AND user_id = ?
            """,
            (payload.get("status") or "created", json.dumps(payload, ensure_ascii=False), payload["id"], user_id),
        )
        connection.commit()
    finally:
        connection.close()
    return payload


def get_area_job(user_id: str, job_id: str, organization_id: str) -> dict[str, Any] | None:
    connection = _connect()
    try:
        row = connection.execute(
            """
            SELECT payload FROM area_jobs
            WHERE id = ? AND user_id = ? AND organization_id = ?
            """,
            (job_id, user_id, organization_id),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    return json.loads(row["payload"])


def list_area_jobs(user_id: str, organization_id: str) -> list[dict[str, Any]]:
    connection = _connect()
    try:
        rows = connection.execute(
            """
            SELECT payload FROM area_jobs
            WHERE user_id = ? AND organization_id = ?
            ORDER BY created_at DESC
            """,
            (user_id, organization_id),
        ).fetchall()
    finally:
        connection.close()
    return [json.loads(row["payload"]) for row in rows]


def delete_area_job(user_id: str, job_id: str, organization_id: str) -> bool:
    """Permanently remove a discovery-job row. Does not delete catalogues."""
    connection = _connect()
    try:
        cursor = connection.execute(
            """
            DELETE FROM area_jobs
            WHERE id = ? AND user_id = ? AND organization_id = ?
            """,
            (job_id, user_id, organization_id),
        )
        connection.commit()
        return cursor.rowcount > 0
    finally:
        connection.close()


def _row_to_stored(row: sqlite3.Row) -> StoredCatalogue:
    payload: dict[str, Any] = json.loads(row["payload"])
    result = CatalogCreateResponse.model_validate(payload)
    return StoredCatalogue(
        id=row["id"],
        organization_id=row["organization_id"],
        created_at=row["created_at"],
        result=result,
    )

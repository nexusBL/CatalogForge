from __future__ import annotations

import sqlite3

import pytest

from backend.migrate_catalogues import connect_catalogue_db
from backend.store import _connect


def test_store_and_migrator_connections_enable_foreign_keys():
    store_conn = _connect()
    try:
        assert store_conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        store_conn.close()
    migrate_conn = connect_catalogue_db()
    try:
        assert migrate_conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        migrate_conn.close()


def test_invalid_venue_source_foreign_key_is_rejected():
    connection = _connect()
    try:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO venue_sources (
                    id, venue_id, user_id, organization_id, platform,
                    source_entity_id, canonical_source_url, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "vs-orphan",
                    "missing-venue-id",
                    "user-1",
                    "org_1",
                    "swiggy",
                    "entity-1",
                    "https://www.swiggy.com/city/sample/fk-resta",
                    "2026-01-01T00:00:00+00:00",
                ),
            )
            connection.commit()
    finally:
        connection.close()


def test_valid_venue_source_foreign_key_is_accepted():
    connection = _connect()
    try:
        connection.execute(
            """
            INSERT INTO venues (id, user_id, organization_id, created_at, updated_at, name)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("venue-ok", "user-1", "org_1", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00", "Ok"),
        )
        connection.execute(
            """
            INSERT INTO venue_sources (
                id, venue_id, user_id, organization_id, platform,
                source_entity_id, canonical_source_url, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "vs-ok",
                "venue-ok",
                "user-1",
                "org_1",
                "swiggy",
                "entity-ok",
                "https://www.swiggy.com/city/sample/fk-ok-resta",
                "2026-01-01T00:00:00+00:00",
            ),
        )
        connection.commit()
        row = connection.execute("SELECT venue_id FROM venue_sources WHERE id = ?", ("vs-ok",)).fetchone()
        assert row["venue_id"] == "venue-ok"
    finally:
        connection.close()

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from backend.migrate_catalogues import MIGRATION_ID, migrate_catalogue_db, migration_status


def _legacy_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """
            CREATE TABLE catalogues (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                organization_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                extraction_status TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        payload = {
            "extraction_status": "ok",
            "restaurant_name": "Alpha",
            "fssai_number": "1",
            "source_url": "https://www.swiggy.com/city/sample/dup-resta",
            "platform": "swiggy",
            "restaurant": {"name": "Alpha", "restaurant_id": "dup-1"},
            "categories": [],
        }
        for catalogue_id in ("cat-a", "cat-b"):
            connection.execute(
                "INSERT INTO catalogues (id, user_id, organization_id, created_at, extraction_status, payload) VALUES (?, ?, ?, ?, ?, ?)",
                (catalogue_id, "user-1", "org_1", "2026-01-01T00:00:00+00:00", "ok", json.dumps(payload)),
            )
        connection.commit()
    finally:
        connection.close()


def test_migrate_empty_db_creates_unique_indexes(tmp_path: Path, monkeypatch):
    db = tmp_path / "fresh.sqlite"
    monkeypatch.setenv("CATALOGFORGE_CATALOGUE_DB", str(db))
    first = migrate_catalogue_db(db)
    assert first["status"] == "applied"
    assert first["backfilled"] is True
    assert first["skipped"] is False
    assert first["detail"]["indexes_skipped"] is False
    again = migrate_catalogue_db(db)
    assert again["status"] == "applied"
    assert again["backfilled"] is False
    assert again["skipped"] is True
    status = migration_status(db)
    assert status is not None
    assert status["id"] == MIGRATION_ID
    connection = sqlite3.connect(db)
    try:
        names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
    finally:
        connection.close()
    assert "catalogues_ok_url" in names
    assert "catalogues_ok_entity" in names


def test_migrate_preserves_duplicate_ok_rows_and_skips_unique_indexes(tmp_path: Path, monkeypatch):
    db = tmp_path / "dirty.sqlite"
    monkeypatch.setenv("CATALOGFORGE_CATALOGUE_DB", str(db))
    _legacy_db(db)
    result = migrate_catalogue_db(db)
    assert result["status"] == "partial"
    assert result["detail"]["indexes_skipped"] is True
    assert result["detail"]["duplicate_groups"]
    connection = sqlite3.connect(db)
    try:
        count = connection.execute("SELECT COUNT(*) FROM catalogues").fetchone()[0]
        names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
        ids = [row[0] for row in connection.execute("SELECT id FROM catalogues ORDER BY id")]
    finally:
        connection.close()
    assert count == 2
    assert ids == ["cat-a", "cat-b"]
    assert "catalogues_ok_url" not in names
    assert "catalogues_ok_entity" not in names


def test_completed_migration_is_not_rebackfilled(tmp_path: Path, monkeypatch):
    db = tmp_path / "once.sqlite"
    monkeypatch.setenv("CATALOGFORGE_CATALOGUE_DB", str(db))
    import backend.migrate_catalogues as migrate_mod

    calls = {"n": 0}
    real = migrate_mod._backfill

    def wrapped(connection):
        calls["n"] += 1
        return real(connection)

    monkeypatch.setattr(migrate_mod, "_backfill", wrapped)
    first = migrate_mod.migrate_catalogue_db(db)
    assert first["backfilled"] is True
    assert calls["n"] == 1
    second = migrate_mod.migrate_catalogue_db(db)
    assert second["skipped"] is True
    assert second["backfilled"] is False
    assert second["status"] == "applied"
    assert calls["n"] == 1


def test_partial_migration_does_not_rebackfill(tmp_path: Path, monkeypatch):
    db = tmp_path / "partial-once.sqlite"
    monkeypatch.setenv("CATALOGFORGE_CATALOGUE_DB", str(db))
    _legacy_db(db)
    import backend.migrate_catalogues as migrate_mod

    calls = {"n": 0}
    real = migrate_mod._backfill

    def wrapped(connection):
        calls["n"] += 1
        return real(connection)

    monkeypatch.setattr(migrate_mod, "_backfill", wrapped)
    first = migrate_mod.migrate_catalogue_db(db)
    assert first["status"] == "partial"
    assert first["backfilled"] is True
    assert calls["n"] == 1
    second = migrate_mod.migrate_catalogue_db(db)
    assert second["status"] == "partial"
    assert second["backfilled"] is False
    assert calls["n"] == 1


def test_api_startup_uses_migrate_catalogue_db():
    import backend.main as main
    from backend.migrate_catalogues import migrate_catalogue_db

    assert main.migrate_catalogue_db is migrate_catalogue_db


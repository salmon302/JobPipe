from __future__ import annotations

import sqlite3

from jobpipe.storage.db import initialize_database, schema_version
from jobpipe.storage.migrations import latest_schema_version


def _table_exists(db_path, table_name: str) -> bool:
    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
    return row is not None


def _column_exists(db_path, table_name: str, column_name: str) -> bool:
    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(row[1] == column_name for row in rows)


def test_initialize_database_applies_latest_schema_version(tmp_path) -> None:
    db_path = tmp_path / "jobpipe.db"

    initialize_database(db_path)

    assert schema_version(db_path) == latest_schema_version()
    assert _table_exists(db_path, "jobs") is True
    assert _table_exists(db_path, "scrape_runs") is True
    assert _table_exists(db_path, "notifications_audit") is True
    assert _column_exists(db_path, "jobs", "score_relevance") is True
    assert _column_exists(db_path, "jobs", "score_attainability") is True
    assert _column_exists(db_path, "jobs", "score_recency") is True


def test_initialize_database_upgrades_legacy_schema(tmp_path) -> None:
    db_path = tmp_path / "legacy.db"

    with sqlite3.connect(str(db_path)) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                company TEXT NOT NULL,
                url TEXT NOT NULL,
                description TEXT NOT NULL,
                date_posted TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Queued'
            );
            PRAGMA user_version = 1;
            """
        )
        conn.commit()

    initialize_database(db_path)

    assert schema_version(db_path) == latest_schema_version()
    assert _table_exists(db_path, "jobs") is True
    assert _table_exists(db_path, "scrape_runs") is True
    assert _table_exists(db_path, "notifications_audit") is True
    assert _column_exists(db_path, "jobs", "score_relevance") is True
    assert _column_exists(db_path, "jobs", "score_attainability") is True
    assert _column_exists(db_path, "jobs", "score_recency") is True

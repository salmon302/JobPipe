from __future__ import annotations

import sqlite3

_MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            platform TEXT NOT NULL,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            url TEXT NOT NULL,
            description TEXT NOT NULL,
            date_posted TEXT NOT NULL,
            match_score REAL,
            status TEXT NOT NULL DEFAULT 'Queued',
            years_required INTEGER,
            is_remote INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(platform, url)
        );

        CREATE INDEX IF NOT EXISTS idx_jobs_status_score ON jobs(status, match_score DESC);
        CREATE INDEX IF NOT EXISTS idx_jobs_posted ON jobs(date_posted DESC);
        """,
    ),
    (
        2,
        """
        CREATE TABLE IF NOT EXISTS scrape_runs (
            run_id TEXT PRIMARY KEY,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT NOT NULL,
            scraped INTEGER NOT NULL DEFAULT 0,
            inserted INTEGER NOT NULL DEFAULT 0,
            updated INTEGER NOT NULL DEFAULT 0,
            scored INTEGER NOT NULL DEFAULT 0,
            above_threshold INTEGER NOT NULL DEFAULT 0,
            notified INTEGER NOT NULL DEFAULT 0,
            error_message TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_scrape_runs_started ON scrape_runs(started_at DESC);
        """,
    ),
    (
        3,
        """
        CREATE TABLE IF NOT EXISTS notifications_audit (
            notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT,
            job_id TEXT NOT NULL,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            score REAL,
            url TEXT NOT NULL,
            delivery_status TEXT NOT NULL,
            error_message TEXT,
            notified_at TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_notifications_notified_at ON notifications_audit(notified_at DESC);
        CREATE INDEX IF NOT EXISTS idx_notifications_run ON notifications_audit(run_id);
        CREATE INDEX IF NOT EXISTS idx_notifications_job ON notifications_audit(job_id);
        """,
    ),
    (
        4,
        """
        ALTER TABLE jobs ADD COLUMN score_relevance REAL;
        ALTER TABLE jobs ADD COLUMN score_attainability REAL;
        ALTER TABLE jobs ADD COLUMN score_recency REAL;
        """,
    ),
]


def latest_schema_version() -> int:
    if not _MIGRATIONS:
        return 0
    return _MIGRATIONS[-1][0]


def get_schema_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("PRAGMA user_version;").fetchone()
    if row is None:
        return 0
    return int(row[0])


def _set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute(f"PRAGMA user_version = {int(version)};")


def apply_migrations(conn: sqlite3.Connection) -> int:
    current = get_schema_version(conn)

    for version, sql in _MIGRATIONS:
        if version <= current:
            continue

        conn.executescript(sql)
        _set_schema_version(conn, version)
        current = version

    return current

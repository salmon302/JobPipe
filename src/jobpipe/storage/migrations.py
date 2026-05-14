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
    (
        5,
        """
        ALTER TABLE jobs ADD COLUMN summary TEXT;
        ALTER TABLE jobs ADD COLUMN requirements TEXT;
        ALTER TABLE jobs ADD COLUMN location TEXT;
        ALTER TABLE jobs ADD COLUMN county TEXT;
        ALTER TABLE jobs ADD COLUMN compensation TEXT;
        ALTER TABLE jobs ADD COLUMN workplace_type TEXT;
        ALTER TABLE jobs ADD COLUMN employment_type TEXT;
        ALTER TABLE jobs ADD COLUMN department TEXT;
        ALTER TABLE jobs ADD COLUMN team TEXT;
        ALTER TABLE jobs ADD COLUMN views INTEGER;
        ALTER TABLE jobs ADD COLUMN saves INTEGER;
        ALTER TABLE jobs ADD COLUMN applications INTEGER;
        ALTER TABLE jobs ADD COLUMN posted_at TEXT;
        ALTER TABLE jobs ADD COLUMN posted_ago TEXT;
        """,
    ),
    (
        6,
        """
        CREATE TABLE IF NOT EXISTS master_cv_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cv_hash TEXT NOT NULL UNIQUE,
            file_path TEXT NOT NULL,
            version_number INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(cv_hash)
        );

        CREATE INDEX IF NOT EXISTS idx_cv_versions_hash ON master_cv_versions(cv_hash);
        CREATE INDEX IF NOT EXISTS idx_cv_versions_created ON master_cv_versions(created_at DESC);

        CREATE TABLE IF NOT EXISTS resume_variants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT,
            variant_name TEXT NOT NULL,
            page_length INTEGER NOT NULL DEFAULT 1 CHECK(page_length IN (1, 2)),
            job_type TEXT,
            target_company TEXT,
            skills TEXT,
            master_cv_hash TEXT NOT NULL,
            generation_number INTEGER NOT NULL DEFAULT 1,
            parent_variant_id INTEGER,
            tex_path TEXT NOT NULL,
            pdf_path TEXT,
            ats_optimized INTEGER NOT NULL DEFAULT 0,
            ats_score REAL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE SET NULL,
            FOREIGN KEY (master_cv_hash) REFERENCES master_cv_versions(cv_hash) ON DELETE CASCADE,
            FOREIGN KEY (parent_variant_id) REFERENCES resume_variants(id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_variants_job ON resume_variants(job_id);
        CREATE INDEX IF NOT EXISTS idx_variants_company ON resume_variants(target_company);
        CREATE INDEX IF NOT EXISTS idx_variants_type ON resume_variants(job_type);
        CREATE INDEX IF NOT EXISTS idx_variants_page ON resume_variants(page_length);
        CREATE INDEX IF NOT EXISTS idx_variants_cv_hash ON resume_variants(master_cv_hash);
        CREATE INDEX IF NOT EXISTS idx_variants_parent ON resume_variants(parent_variant_id);
        CREATE INDEX IF NOT EXISTS idx_variants_created ON resume_variants(created_at DESC);
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

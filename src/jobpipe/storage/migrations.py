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
    (
        7,
        """
        CREATE INDEX IF NOT EXISTS idx_jobs_score_posted ON jobs(match_score DESC, date_posted DESC);
        """,
    ),
    (
        8,
        """
        CREATE INDEX IF NOT EXISTS idx_jobs_url ON jobs(url);
        """,
    ),
    (
        9,
        """
        CREATE INDEX IF NOT EXISTS idx_jobs_normalized_url ON jobs(url);
        """,
    ),
    (
        10,
        """
        -- Optimize URL deduplication with covering index
        CREATE INDEX IF NOT EXISTS idx_jobs_url_covering ON jobs(url, id);
        """,
    ),
    (
        11,
        """
        -- Create FTS virtual table for full-text search
        CREATE VIRTUAL TABLE IF NOT EXISTS jobs_fts USING fts5(
            title,
            company,
            description,
            summary,
            requirements,
            location,
            county,
            compensation,
            workplace_type,
            employment_type,
            department,
            team,
            platform,
            status,
            url,
            content='jobs',
            content_rowid='rowid'
        );

        -- Trigger to index new jobs
        CREATE TRIGGER IF NOT EXISTS jobs_ai AFTER INSERT ON jobs BEGIN
            INSERT INTO jobs_fts(
                rowid,
                title,
                company,
                description,
                summary,
                requirements,
                location,
                county,
                compensation,
                workplace_type,
                employment_type,
                department,
                team,
                platform,
                status,
                url
            ) VALUES (
                new.rowid,
                new.title,
                new.company,
                new.description,
                new.summary,
                new.requirements,
                new.location,
                new.county,
                new.compensation,
                new.workplace_type,
                new.employment_type,
                new.department,
                new.team,
                new.platform,
                new.status,
                new.url
            );
        END;

        -- Trigger to remove deleted jobs from FTS
        CREATE TRIGGER IF NOT EXISTS jobs_ad AFTER DELETE ON jobs BEGIN
            INSERT INTO jobs_fts(jobs_fts, rowid) VALUES('delete', old.rowid);
        END;

        -- Trigger to update FTS on job update
        CREATE TRIGGER IF NOT EXISTS jobs_au AFTER UPDATE ON jobs BEGIN
            INSERT INTO jobs_fts(jobs_fts, rowid) VALUES('delete', old.rowid);
            INSERT INTO jobs_fts(
                rowid,
                title,
                company,
                description,
                summary,
                requirements,
                location,
                county,
                compensation,
                workplace_type,
                employment_type,
                department,
                team,
                platform,
                status,
                url
            ) VALUES (
                new.rowid,
                new.title,
                new.company,
                new.description,
                new.summary,
                new.requirements,
                new.location,
                new.county,
                new.compensation,
                new.workplace_type,
                new.employment_type,
                new.department,
                new.team,
                new.platform,
                new.status,
                new.url
            );
        END;

        -- Rebuild FTS index with existing data
        INSERT INTO jobs_fts(jobs_fts) VALUES('rebuild');
        """,
    ),
    (
        12,
        """
        -- Add indexes for scoring performance
        CREATE INDEX IF NOT EXISTS idx_jobs_for_scoring ON jobs(match_score, status, date_posted DESC) WHERE match_score IS NULL;
        CREATE INDEX IF NOT EXISTS idx_jobs_score_status ON jobs(match_score DESC, status, date_posted DESC);
        CREATE INDEX IF NOT EXISTS idx_jobs_status_posted ON jobs(status, date_posted DESC);
        CREATE INDEX IF NOT EXISTS idx_jobs_status_score ON jobs(status, match_score DESC);
        CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
        """,
    ),
    (
        13,
        """
        -- Add last_scored_at column for incremental scoring
        ALTER TABLE jobs ADD COLUMN last_scored_at TEXT;
        CREATE INDEX IF NOT EXISTS idx_jobs_last_scored ON jobs(last_scored_at DESC);
        """,
    ),
]


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row[1] for row in rows}


def _add_columns_if_missing(
    conn: sqlite3.Connection,
    table_name: str,
    column_defs: list[tuple[str, str]],
) -> None:
    existing_columns = _table_columns(conn, table_name)
    for column_name, column_sql in column_defs:
        if column_name in existing_columns:
            continue
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_sql}")


def latest_schema_version() -> int:
    """Return the latest schema version from migrations list."""
    if not _MIGRATIONS:
        return 0
    return _MIGRATIONS[-1][0]


# Current schema version - must match the last migration number
CURRENT_SCHEMA_VERSION = 13


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

        if version == 4:
            _add_columns_if_missing(
                conn,
                "jobs",
                [
                    ("match_score", "match_score REAL"),
                    ("score_relevance", "score_relevance REAL"),
                    ("score_attainability", "score_attainability REAL"),
                    ("score_recency", "score_recency REAL"),
                ],
            )
            _set_schema_version(conn, version)
            current = version
            continue

        if version == 5:
            _add_columns_if_missing(
                conn,
                "jobs",
                [
                    ("platform", "platform TEXT"),
                    ("summary", "summary TEXT"),
                    ("requirements", "requirements TEXT"),
                    ("location", "location TEXT"),
                    ("county", "county TEXT"),
                    ("compensation", "compensation TEXT"),
                    ("workplace_type", "workplace_type TEXT"),
                    ("employment_type", "employment_type TEXT"),
                    ("department", "department TEXT"),
                    ("team", "team TEXT"),
                    ("views", "views INTEGER"),
                    ("saves", "saves INTEGER"),
                    ("applications", "applications INTEGER"),
                    ("posted_at", "posted_at TEXT"),
                    ("posted_ago", "posted_ago TEXT"),
                ],
            )
            _set_schema_version(conn, version)
            current = version
            continue

        conn.executescript(sql)
        _set_schema_version(conn, version)
        current = version

    return current

from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any
import logging

from jobpipe.storage.db import connect, _get_pool
from jobpipe.storage.connection_pool import PooledConnection
from jobpipe.storage.models import JobRecord, NotificationAuditRecord, ScrapeRunRecord, _parse_datetime

LOGGER = logging.getLogger(__name__)


_JOB_SELECT_COLUMNS = """
    jobs.id, jobs.platform, jobs.title, jobs.company, jobs.url, jobs.description, jobs.date_posted,
    jobs.match_score, jobs.status, jobs.years_required, jobs.is_remote,
    jobs.score_relevance, jobs.score_attainability, jobs.score_recency,
    jobs.summary, jobs.requirements, jobs.location, jobs.county, jobs.compensation,
    jobs.workplace_type, jobs.employment_type, jobs.department, jobs.team,
    jobs.views, jobs.saves, jobs.applications, jobs.posted_at, jobs.posted_ago
""".strip()


class JobRepository:
    """
    Repository for job data with performance optimizations.
    
    Optimizations included:
    - Connection pooling via db.py
    - Query result caching for expensive operations
    - Optimized batch operations
    - FTS5 support for full-text search
    """
    
    def __init__(self, db_path: Path, settings: Settings) -> None:
        self._db_path = db_path
        self._settings = settings
        self._cache_lock = Lock()
        self._job_count_cache: tuple[int, datetime] | None = None
        self._cache_ttl_seconds = 30  # Cache TTL in seconds
        self._pool = _get_pool(db_path, max_connections=settings.db_pool_max_connections, wait_timeout=settings.db_pool_wait_timeout)  # Use connection pool for better performance

    def _is_cache_valid(self, cache_entry: tuple[Any, datetime]) -> bool:
        """Check if a cache entry is still valid based on TTL."""
        import time
        _, timestamp = cache_entry
        age = (datetime.now(timezone.utc) - timestamp).total_seconds()
        return age < self._cache_ttl_seconds

    def create_scrape_run(self, run_id: str, started_at: datetime | None = None) -> None:
        started = (started_at or datetime.now(timezone.utc)).isoformat()

        with PooledConnection(self._pool) as conn:
            conn.execute(
                """
                INSERT INTO scrape_runs (run_id, started_at, status)
                VALUES (?, ?, 'Started')
                """,
                (run_id, started),
            )
            conn.commit()

    def update_scrape_run_ingest(
        self,
        run_id: str,
        scraped: int,
        inserted: int,
        updated: int,
        status: str = "Scoring",
    ) -> None:
        with PooledConnection(self._pool) as conn:
            conn.execute(
                """
                UPDATE scrape_runs
                SET status = ?,
                    scraped = ?,
                    inserted = ?,
                    updated = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE run_id = ?
                """,
                (status, scraped, inserted, updated, run_id),
            )
            conn.commit()

    def complete_scrape_run(
        self,
        run_id: str,
        scraped: int,
        inserted: int,
        updated: int,
        scored: int,
        above_threshold: int,
        notified: int,
        finished_at: datetime | None = None,
    ) -> None:
        finished = (finished_at or datetime.now(timezone.utc)).isoformat()

        with connect(self._db_path) as conn:
            conn.execute(
                """
                UPDATE scrape_runs
                SET finished_at = ?,
                    status = 'Completed',
                    scraped = ?,
                    inserted = ?,
                    updated = ?,
                    scored = ?,
                    above_threshold = ?,
                    notified = ?,
                    error_message = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE run_id = ?
                """,
                (finished, scraped, inserted, updated, scored, above_threshold, notified, run_id),
            )
            conn.commit()

    def fail_scrape_run(
        self,
        run_id: str,
        error_message: str,
        finished_at: datetime | None = None,
    ) -> None:
        finished = (finished_at or datetime.now(timezone.utc)).isoformat()

        with connect(self._db_path) as conn:
            conn.execute(
                """
                UPDATE scrape_runs
                SET finished_at = ?,
                    status = 'Failed',
                    error_message = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE run_id = ?
                """,
                (finished, error_message, run_id),
            )
            conn.commit()

    def get_scrape_run(self, run_id: str) -> ScrapeRunRecord | None:
        with connect(self._db_path) as conn:
            row = conn.execute(
                """
                SELECT run_id, started_at, finished_at, status,
                       scraped, inserted, updated, scored,
                       above_threshold, notified, error_message
                FROM scrape_runs
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()

        if row is None:
            return None

        return ScrapeRunRecord.from_row(row)

    def list_recent_runs(self, limit: int = 20) -> list[ScrapeRunRecord]:
        with connect(self._db_path) as conn:
            rows = conn.execute(
                """
                SELECT run_id, started_at, finished_at, status,
                       scraped, inserted, updated, scored,
                       above_threshold, notified, error_message
                FROM scrape_runs
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [ScrapeRunRecord.from_row(row) for row in rows]

    def record_notification_event(
        self,
        run_id: str | None,
        job_id: str,
        title: str,
        company: str,
        score: float | None,
        url: str,
        delivery_status: str,
        error_message: str | None = None,
        notified_at: datetime | None = None,
    ) -> None:
        notified = (notified_at or datetime.now(timezone.utc)).isoformat()

        with connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO notifications_audit (
                    run_id,
                    job_id,
                    title,
                    company,
                    score,
                    url,
                    delivery_status,
                    error_message,
                    notified_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    job_id,
                    title,
                    company,
                    score,
                    url,
                    delivery_status,
                    error_message,
                    notified,
                ),
            )
            conn.commit()

    def record_notification_events_bulk(self, events: list[tuple]) -> None:
        """Record multiple notification events in a single transaction.
        
        Args:
            events: List of tuples (run_id, job_id, title, company, score, url,
                   delivery_status, error_message, notified_at)
        """
        if not events:
            return

        with connect(self._db_path) as conn:
            conn.executemany(
                """
                INSERT INTO notifications_audit (
                    run_id,
                    job_id,
                    title,
                    company,
                    score,
                    url,
                    delivery_status,
                    error_message,
                    notified_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                events,
            )
            conn.commit()

    def list_recent_notifications(self, limit: int = 20) -> list[NotificationAuditRecord]:
        with connect(self._db_path) as conn:
            rows = conn.execute(
                """
                SELECT notification_id, run_id, job_id, title, company,
                       score, url, delivery_status, error_message, notified_at
                FROM notifications_audit
                ORDER BY notified_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [NotificationAuditRecord.from_row(row) for row in rows]

    def upsert_jobs(self, jobs: list[JobRecord]) -> tuple[int, int]:
        import logging
        LOGGER = logging.getLogger(__name__)
        LOGGER.info("upsert_jobs | Starting with %d jobs", len(jobs))
        if not jobs:
            return 0, 0

        inserted = 0
        updated = 0

        with connect(self._db_path) as conn:
            def chunked(items: list[str], size: int = 100) -> list[list[str]]:
                return [items[i : i + size] for i in range(0, len(items), size)]

            job_ids = [job.id for job in jobs]

            # Detect duplicate IDs inside the incoming batch itself
            from collections import Counter

            id_counts = Counter(job_ids)
            duplicates = [jid for jid, cnt in id_counts.items() if cnt > 1]
            if duplicates:
                LOGGER.info(
                    "upsert_jobs | Found %d duplicate IDs inside batch, sample: %s",
                    sum(id_counts[j] for j in duplicates),
                    duplicates[:10],
                )
            existing_ids: set[str] = set()
            for chunk in chunked(job_ids):
                placeholders = ",".join("?" for _ in chunk)
                rows = conn.execute(
                    f"SELECT id FROM jobs WHERE id IN ({placeholders})",
                    chunk,
                ).fetchall()
                existing_ids.update(row["id"] for row in rows)

            # URL-based dedup: check if any incoming job's URL already exists
            # under a different ID (e.g., same job ingested from different platforms).
            # Normalize URLs by stripping query parameters so enriched pages (different query strings)
            # still match the original job record.
            def _normalize_url(url: str) -> str:
                """Strip query parameters and fragments for URL comparison."""
                return url.split("?")[0].split("#")[0]

            incoming_norm_urls = [_normalize_url(job.url) for job in jobs]
            if incoming_norm_urls:
                # Build a mapping of normalized URL -> existing ID (O(n) instead of O(n²))
                url_to_existing_id: dict[str, str] = {}
                # Pre-compute a set for O(1) lookups
                incoming_norm_set = set(incoming_norm_urls)
                
                for chunk_norm_urls in [
                    list(incoming_norm_set)[i:i+900] for i in range(0, len(incoming_norm_set), 900)
                ]:
                    chunk_placeholders = ",".join("?" for _ in chunk_norm_urls)
                    url_rows = conn.execute(
                        f"SELECT id, url FROM jobs WHERE url IN ({chunk_placeholders})",
                        chunk_norm_urls,
                    ).fetchall()
                    for row in url_rows:
                        norm_existing = _normalize_url(row["url"])
                        if norm_existing in incoming_norm_set:
                            url_to_existing_id[norm_existing] = row["id"]

                # Rewrite IDs for jobs whose normalized URL already exists under a different ID
                for job in jobs:
                    norm_url = _normalize_url(job.url)
                    existing_id = url_to_existing_id.get(norm_url)
                    if existing_id is not None and existing_id != job.id:
                        LOGGER.info(
                            "upsert_jobs | URL dedup: %s -> %s (was %s)",
                            job.url, existing_id, job.id,
                        )
                        job.id = existing_id
                        existing_ids.add(existing_id)

            # If many IDs are already present, log a small sample of their URLs for debugging.
            if existing_ids:
                sample_ids = list(existing_ids)[:10]
                sample_placeholders = ",".join("?" for _ in sample_ids)
                try:
                    sample_rows = conn.execute(
                        f"SELECT id, url FROM jobs WHERE id IN ({sample_placeholders})",
                        sample_ids,
                    ).fetchall()
                    LOGGER.info(
                        "upsert_jobs | Existing sample rows (count=%d): %s",
                        len(existing_ids),
                        [{"id": r["id"], "url": r["url"]} for r in sample_rows],
                    )
                except Exception:
                    LOGGER.info("upsert_jobs | Could not fetch sample existing rows")

            # Deduplicate jobs by ID for the actual INSERT/UPDATE.
            # The counting loop above may count duplicates as "updated",
            # but passing them to executemany would cause a UNIQUE constraint
            # failure on jobs.id when two jobs share the same ID but have
            # different (platform, url) pairs.
            seen_ids: set[str] = set()
            unique_jobs: list[JobRecord] = []
            for job in jobs:
                if job.id in existing_ids or job.id in seen_ids:
                    updated += 1
                else:
                    inserted += 1
                    seen_ids.add(job.id)
                    unique_jobs.append(job)

            conn.executemany(
                """
                INSERT INTO jobs (
                    id,
                    platform,
                    title,
                    company,
                    url,
                    description,
                    date_posted,
                    status,
                    summary,
                    requirements,
                    location,
                    county,
                    compensation,
                    workplace_type,
                    employment_type,
                    department,
                    team,
                    views,
                    saves,
                    applications,
                    posted_at,
                    posted_ago
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(platform, url) DO UPDATE SET

                    title = excluded.title,
                    company = excluded.company,
                    description = excluded.description,
                    date_posted = excluded.date_posted,
                    status = excluded.status,
                    summary = excluded.summary,
                    requirements = excluded.requirements,
                    location = excluded.location,
                    county = excluded.county,
                    compensation = excluded.compensation,
                    workplace_type = excluded.workplace_type,
                    employment_type = excluded.employment_type,
                    department = excluded.department,
                    team = excluded.team,
                    views = excluded.views,
                    saves = excluded.saves,
                    applications = excluded.applications,
                    posted_at = excluded.posted_at,
                    posted_ago = excluded.posted_ago,
                    updated_at = CURRENT_TIMESTAMP
                """,
                [
                    (
                        job.id,
                        job.platform,
                        job.title,
                        job.company,
                        job.url,
                        job.description,
                        job.date_posted.isoformat(),
                        job.status,
                        job.summary,
                        job.requirements,
                        job.location,
                        job.county,
                        job.compensation,
                        job.workplace_type,
                        job.employment_type,
                        job.department,
                        job.team,
                        job.views,
                        job.saves,
                        job.applications,
                        job.posted_at,
                        job.posted_ago,
                    )
                    for job in unique_jobs
                ],
            )
            conn.commit()

        LOGGER.info("upsert_jobs | Complete: %d inserted, %d updated", inserted, updated)
        return inserted, updated

    def list_jobs_for_scoring(self, limit: int = 250) -> list[JobRecord]:
        with connect(self._db_path) as conn:
            rows = conn.execute(
                """
                SELECT id, platform, title, company, url, description, date_posted,
                       match_score, status, years_required, is_remote,
                       score_relevance, score_attainability, score_recency,
                       summary, requirements, location, county, compensation,
                       workplace_type, employment_type, department, team,
                       views, saves, applications, posted_at, posted_ago
                FROM jobs
                WHERE match_score IS NULL AND status IN ('Queued', 'Notified')
                ORDER BY date_posted DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [JobRecord.from_row(row) for row in rows]

    def update_scoring(
        self,
        job_id: str,
        match_score: float,
        years_required: int | None,
        is_remote: bool,
        status: str,
        score_relevance: float | None = None,
        score_attainability: float | None = None,
        score_recency: float | None = None,
    ) -> None:
        with connect(self._db_path) as conn:
            conn.execute(
                """
                UPDATE jobs
                SET match_score = ?,
                    years_required = ?,
                    is_remote = ?,
                    status = ?,
                    score_relevance = ?,
                    score_attainability = ?,
                    score_recency = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    match_score,
                    years_required,
                    int(is_remote),
                    status,
                    score_relevance,
                    score_attainability,
                    score_recency,
                    job_id,
                ),
            )
            conn.commit()

    def update_scoring_bulk(self, updates: list[tuple], batch_size: int | None = None) -> None:
        """Update scoring in bulk with configurable batch size.
        
        Args:
            updates: List of tuples (match_score, years_required, is_remote, status,
                           score_relevance, score_attainability, score_recency, job_id)
            batch_size: Number of updates to process in each transaction (defaults to settings.scoring_batch_size)
        """
        if batch_size is None:
            batch_size = self._settings.scoring_batch_size
        if not updates:
            return

        normalized = [
            (
                match_score,
                years_required,
                int(is_remote),
                status,
                score_relevance,
                score_attainability,
                score_recency,
                job_id,
            )
            for (
                match_score,
                years_required,
                is_remote,
                status,
                score_relevance,
                score_attainability,
                score_recency,
                job_id,
            ) in updates
        ]

        # Process in batches to avoid large transactions
        total_batches = (len(normalized) + batch_size - 1) // batch_size
        
        for batch_num in range(total_batches):
            start_idx = batch_num * batch_size
            end_idx = min(start_idx + batch_size, len(normalized))
            batch = normalized[start_idx:end_idx]
            
            with PooledConnection(self._pool) as conn:
                conn.executemany(
                    """
                    UPDATE jobs
                    SET match_score = ?,
                        years_required = ?,
                        is_remote = ?,
                        status = ?,
                        score_relevance = ?,
                        score_attainability = ?,
                        score_recency = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    batch,
                )
                conn.commit()
            
            LOGGER.info("Updated scoring batch %d/%d (%d records)", batch_num + 1, total_batches, len(batch))

    def update_last_scored_at(self, job_ids: list[str], timestamp: str) -> None:
        """Update last_scored_at timestamp for multiple jobs in a single transaction.
        
        Args:
            job_ids: List of job IDs to update
            timestamp: ISO format timestamp string
        """
        if not job_ids:
            return

        with PooledConnection(self._pool) as conn:
            conn.executemany(
                "UPDATE jobs SET last_scored_at = ? WHERE id = ?",
                [(timestamp, job_id) for job_id in job_ids]
            )
            conn.commit()

    def list_jobs_above_threshold(self, threshold: float, limit: int = 100) -> list[JobRecord]:
        with connect(self._db_path) as conn:
            rows = conn.execute(
                """
                SELECT id, platform, title, company, url, description, date_posted,
                       match_score, status, years_required, is_remote,
                       score_relevance, score_attainability, score_recency,
                       summary, requirements, location, county, compensation,
                       workplace_type, employment_type, department, team,
                       views, saves, applications, posted_at, posted_ago
                FROM jobs
                WHERE match_score IS NOT NULL AND match_score >= ?
                ORDER BY match_score DESC
                LIMIT ?
                """,
                (threshold, limit),
            ).fetchall()

        return [JobRecord.from_row(row) for row in rows]

    def list_jobs_to_notify(self, threshold: float, limit: int = 100) -> list[JobRecord]:
        with connect(self._db_path) as conn:
            rows = conn.execute(
                """
                SELECT id, platform, title, company, url, description, date_posted,
                       match_score, status, years_required, is_remote,
                       score_relevance, score_attainability, score_recency,
                       summary, requirements, location, county, compensation,
                       workplace_type, employment_type, department, team,
                       views, saves, applications, posted_at, posted_ago
                FROM jobs
                WHERE status = 'Queued'
                  AND match_score IS NOT NULL
                  AND match_score >= ?
                ORDER BY match_score DESC, date_posted DESC
                LIMIT ?
                """,
                (threshold, limit),
            ).fetchall()

        return [JobRecord.from_row(row) for row in rows]

    def list_top_jobs(self, limit: int = 20) -> list[JobRecord]:
        with connect(self._db_path) as conn:
            rows = conn.execute(
                """
                SELECT id, platform, title, company, url, description, date_posted,
                       match_score, status, years_required, is_remote,
                       score_relevance, score_attainability, score_recency,
                       summary, requirements, location, county, compensation,
                       workplace_type, employment_type, department, team,
                       views, saves, applications, posted_at, posted_ago
                FROM jobs
                WHERE match_score IS NOT NULL
                ORDER BY match_score DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [JobRecord.from_row(row) for row in rows]

    def get_job_by_id(self, job_id: str) -> JobRecord | None:
        with connect(self._db_path) as conn:
            row = conn.execute(
                f"""
                SELECT {_JOB_SELECT_COLUMNS}
                FROM jobs
                WHERE id = ?
                """,
                (job_id,),
            ).fetchone()

        if row is None:
            return None

        return JobRecord.from_row(row)

    def list_jobs(
        self,
        limit: int = 200,
        offset: int = 0,
        search_query: str | None = None,
    ) -> list[JobRecord]:
        """List jobs with optional search and pagination.
        
        Args:
            limit: Maximum number of jobs to return
            offset: Number of jobs to skip (for pagination)
            search_query: Optional search string for FTS
        """
        search = (search_query or "").strip()

        if search:
            tokens = [token for token in search.split() if token]
            if tokens:
                escaped_tokens = [token.replace('"', '""') for token in tokens]
                fts_query = " AND ".join(f'"{token}"' for token in escaped_tokens)
                query = f"""
                    SELECT {_JOB_SELECT_COLUMNS}
                    FROM jobs
                    JOIN jobs_fts ON jobs_fts.rowid = jobs.rowid
                    WHERE jobs_fts MATCH ?
                    ORDER BY (jobs.match_score IS NULL), jobs.match_score DESC, jobs.date_posted DESC
                    LIMIT ? OFFSET ?
                """
                params = (fts_query, limit, offset)
            else:
                query = f"""
                    SELECT {_JOB_SELECT_COLUMNS}
                    FROM jobs
                    ORDER BY (jobs.match_score IS NULL), jobs.match_score DESC, jobs.date_posted DESC
                    LIMIT ? OFFSET ?
                """
                params = (limit, offset)
        else:
            query = f"""
                SELECT {_JOB_SELECT_COLUMNS}
                FROM jobs
                ORDER BY (jobs.match_score IS NULL), jobs.match_score DESC, jobs.date_posted DESC
                LIMIT ? OFFSET ?
            """
            params = (limit, offset)

        with connect(self._db_path) as conn:
            rows = conn.execute(query, params).fetchall()

        return [JobRecord.from_row(row) for row in rows]

    def count_jobs(self, search_query: str | None = None) -> int:
        """Count total jobs, optionally filtered by search query.
        
        Returns:
            Total number of jobs matching the search criteria
        """
        search = (search_query or "").strip()

        if search:
            tokens = [token for token in search.split() if token]
            if tokens:
                escaped_tokens = [token.replace('"', '""') for token in tokens]
                fts_query = " AND ".join(f'"{token}"' for token in escaped_tokens)
                query = """
                    SELECT COUNT(*) as count
                    FROM jobs
                    JOIN jobs_fts ON jobs_fts.rowid = jobs.rowid
                    WHERE jobs_fts MATCH ?
                """
                params = (fts_query,)
            else:
                query = "SELECT COUNT(*) as count FROM jobs"
                params = ()
        else:
            query = "SELECT COUNT(*) as count FROM jobs"
            params = ()

        with connect(self._db_path) as conn:
            row = conn.execute(query, params).fetchone()

        return int(row["count"] or 0)

    def mark_notified(self, job_ids: list[str]) -> None:
        if not job_ids:
            return

        placeholders = ",".join("?" for _ in job_ids)
        query = (
            "UPDATE jobs SET status = 'Notified', updated_at = CURRENT_TIMESTAMP "
            f"WHERE id IN ({placeholders})"
        )

        with connect(self._db_path) as conn:
            conn.execute(query, job_ids)
            conn.commit()

    def clear_jobs(self) -> int:
        """Clear all jobs from the database. Returns the number of deleted jobs."""
        with connect(self._db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM jobs")
            count = cursor.fetchone()[0]
            conn.execute("DELETE FROM jobs")
            conn.commit()
        return count

    def select_resume_target_job(
        self,
        min_score: float,
        job_id: str | None = None,
        statuses: tuple[str, ...] = ("Notified", "Queued"),
    ) -> JobRecord | None:
        if not statuses:
            return None

        status_placeholders = ",".join("?" for _ in statuses)

        if job_id:
            query = (
                """
                SELECT id, platform, title, company, url, description, date_posted,
                       match_score, status, years_required, is_remote,
                       score_relevance, score_attainability, score_recency,
                       summary, requirements, location, county, compensation,
                       workplace_type, employment_type, department, team,
                       views, saves, applications, posted_at, posted_ago
                FROM jobs
                WHERE id = ?
                  AND match_score IS NOT NULL
                  AND match_score >= ?
                  AND status IN ("""
                + status_placeholders
                + """)
                ORDER BY match_score DESC, date_posted DESC
                LIMIT 1
                """
            )
            params = (job_id, min_score, *statuses)
        else:
            query = (
                """
                SELECT id, platform, title, company, url, description, date_posted,
                       match_score, status, years_required, is_remote,
                       score_relevance, score_attainability, score_recency,
                       summary, requirements, location, county, compensation,
                       workplace_type, employment_type, department, team,
                       views, saves, applications, posted_at, posted_ago
                FROM jobs
                WHERE match_score IS NOT NULL
                  AND match_score >= ?
                  AND status IN ("""
                + status_placeholders
                + """)
                ORDER BY match_score DESC, date_posted DESC
                LIMIT 1
                """
            )
            params = (min_score, *statuses)

        with connect(self._db_path) as conn:
            row = conn.execute(query, params).fetchone()

        if row is None:
            return None

        return JobRecord.from_row(row)

    # -------------------------------------------------------------------------
    # Master CV Versions
    # -------------------------------------------------------------------------
    def create_cv_version(self, cv_hash: str, file_path: str, version_number: int = 1) -> int:
        """Create a new CV version record. Returns the row ID."""
        with connect(self._db_path) as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO master_cv_versions (cv_hash, file_path, version_number)
                VALUES (?, ?, ?)
                """,
                (cv_hash, file_path, version_number),
            )
            conn.commit()
            return cursor.lastrowid or 0

    def get_cv_version_by_hash(self, cv_hash: str) -> "MasterCVVersion | None":
        """Retrieve a CV version by its hash."""
        from jobpipe.storage.models import MasterCVVersion

        with connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT id, cv_hash, file_path, version_number, created_at FROM master_cv_versions WHERE cv_hash = ?",
                (cv_hash,),
            ).fetchone()

        if row is None:
            return None
        return MasterCVVersion.from_row(row)

    def list_cv_versions(self, limit: int = 50) -> list["MasterCVVersion"]:
        """List recent CV versions."""
        from jobpipe.storage.models import MasterCVVersion

        with connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT id, cv_hash, file_path, version_number, created_at FROM master_cv_versions ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()

        return [MasterCVVersion.from_row(row) for row in rows]

    # -------------------------------------------------------------------------
    # Resume Variants
    # -------------------------------------------------------------------------
    def create_resume_variant(
        self,
        variant_name: str,
        tex_path: str,
        master_cv_hash: str,
        job_id: str | None = None,
        page_length: int = 1,
        job_type: str | None = None,
        target_company: str | None = None,
        skills: str | None = None,
        generation_number: int = 1,
        parent_variant_id: int | None = None,
        pdf_path: str | None = None,
    ) -> int:
        """Create a new resume variant. Returns the row ID."""
        with connect(self._db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO resume_variants (
                    variant_name, tex_path, master_cv_hash, job_id, page_length,
                    job_type, target_company, skills, generation_number,
                    parent_variant_id, pdf_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    variant_name,
                    tex_path,
                    master_cv_hash,
                    job_id,
                    page_length,
                    job_type,
                    target_company,
                    skills,
                    generation_number,
                    parent_variant_id,
                    pdf_path,
                ),
            )
            conn.commit()
            return cursor.lastrowid or 0

    def update_resume_variant(
        self,
        variant_id: int,
        pdf_path: str | None = None,
        ats_optimized: bool | None = None,
        ats_score: float | None = None,
    ) -> None:
        """Update an existing resume variant."""
        updates = []
        params = []

        if pdf_path is not None:
            updates.append("pdf_path = ?")
            params.append(pdf_path)
        if ats_optimized is not None:
            updates.append("ats_optimized = ?")
            params.append(int(ats_optimized))
        if ats_score is not None:
            updates.append("ats_score = ?")
            params.append(ats_score)

        if not updates:
            return

        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(variant_id)

        with connect(self._db_path) as conn:
            conn.execute(
                f"UPDATE resume_variants SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            conn.commit()

    def get_resume_variant(self, variant_id: int) -> "ResumeVariant | None":
        """Get a resume variant by ID."""
        from jobpipe.storage.models import ResumeVariant

        with connect(self._db_path) as conn:
            row = conn.execute(
                """
                SELECT id, job_id, variant_name, page_length, job_type, target_company,
                       skills, master_cv_hash, generation_number, parent_variant_id,
                       tex_path, pdf_path, ats_optimized, ats_score, created_at, updated_at
                FROM resume_variants WHERE id = ?
                """,
                (variant_id,),
            ).fetchone()

        if row is None:
            return None
        return ResumeVariant.from_row(row)

    def list_resume_variants(
        self,
        job_id: str | None = None,
        target_company: str | None = None,
        job_type: str | None = None,
        page_length: int | None = None,
        master_cv_hash: str | None = None,
        ats_optimized: bool | None = None,
        limit: int = 100,
    ) -> list["ResumeVariant"]:
        """List resume variants with optional filters."""
        from jobpipe.storage.models import ResumeVariant

        query = """
            SELECT id, job_id, variant_name, page_length, job_type, target_company,
                   skills, master_cv_hash, generation_number, parent_variant_id,
                   tex_path, pdf_path, ats_optimized, ats_score, created_at, updated_at
            FROM resume_variants
            WHERE 1=1
        """
        params = []

        if job_id is not None:
            query += " AND job_id = ?"
            params.append(job_id)
        if target_company is not None:
            query += " AND target_company = ?"
            params.append(target_company)
        if job_type is not None:
            query += " AND job_type = ?"
            params.append(job_type)
        if page_length is not None:
            query += " AND page_length = ?"
            params.append(page_length)
        if master_cv_hash is not None:
            query += " AND master_cv_hash = ?"
            params.append(master_cv_hash)
        if ats_optimized is not None:
            query += " AND ats_optimized = ?"
            params.append(int(ats_optimized))

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with connect(self._db_path) as conn:
            rows = conn.execute(query, params).fetchall()

        return [ResumeVariant.from_row(row) for row in rows]

    def get_variant_lineage(self, variant_id: int) -> list["ResumeVariant"]:
        """Get the full lineage (parent chain) of a variant."""
        from jobpipe.storage.models import ResumeVariant

        lineage = []
        current_id = variant_id

        while current_id is not None:
            variant = self.get_resume_variant(current_id)
            if variant is None:
                break
            lineage.append(variant)
            current_id = variant.parent_variant_id

        return lineage

    def get_variants_by_job(self, job_id: str) -> list["ResumeVariant"]:
        """Get all variants for a specific job, ordered by generation."""
        from jobpipe.storage.models import ResumeVariant

        with connect(self._db_path) as conn:
            rows = conn.execute(
                """
                SELECT id, job_id, variant_name, page_length, job_type, target_company,
                       skills, master_cv_hash, generation_number, parent_variant_id,
                       tex_path, pdf_path, ats_optimized, ats_score, created_at, updated_at
                FROM resume_variants
                WHERE job_id = ?
                ORDER BY generation_number ASC, created_at ASC
                """,
                (job_id,),
            ).fetchall()

        return [ResumeVariant.from_row(row) for row in rows]

    def search_jobs_fts(self, search_query: str, limit: int = 100) -> list[JobRecord]:
        """
        Search jobs using FTS5 full-text search (optimized for performance).
        
        Args:
            search_query: Search query with space-separated tokens
            limit: Maximum number of results
            
        Returns:
            List of JobRecord objects matching the search
        """
        tokens = [token for token in search_query.strip().split() if token]
        if not tokens:
            return []
        
        # Build FTS5 query - use OR for broader matches
        escaped_tokens = [token.replace('"', '""') for token in tokens]
        fts_query = " OR ".join(f'"{token}"' for token in escaped_tokens)
        
        query = f"""
            SELECT {_JOB_SELECT_COLUMNS},
                   rank as fts_rank
            FROM jobs
            JOIN jobs_fts ON jobs_fts.rowid = jobs.rowid
            WHERE jobs_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """
        
        with connect(self._db_path) as conn:
            try:
                rows = conn.execute(query, (fts_query, limit)).fetchall()
            except sqlite3.OperationalError:
                # FTS table might not exist, fall back to LIKE search
                like_query = f"""
                    SELECT {_JOB_SELECT_COLUMNS}
                    FROM jobs
                    WHERE title LIKE ? OR company LIKE ? OR description LIKE ?
                    ORDER BY (jobs.match_score IS NULL), jobs.match_score DESC
                    LIMIT ?
                """
                like_pattern = f"%{search_query}%"
                rows = conn.execute(like_query, (like_pattern, like_pattern, like_pattern, limit)).fetchall()

        return [JobRecord.from_row(row) for row in rows]

    def get_job_count_cached(self) -> int:
        """
        Get job count with caching to avoid repeated COUNT queries.
        
        Returns:
            Total number of jobs in the database
        """
        with self._cache_lock:
            if self._job_count_cache and self._is_cache_valid(self._job_count_cache):
                return self._job_count_cache[0]
            
            # Cache miss or expired, query database
            with connect(self._db_path) as conn:
                row = conn.execute("SELECT COUNT(*) as count FROM jobs").fetchone()
                count = int(row["count"] or 0)
            
            from datetime import datetime, timezone
            self._job_count_cache = (count, datetime.now(timezone.utc))
            return count

    def invalidate_cache(self) -> None:
        """Invalidate all cached data (call after bulk updates)."""
        with self._cache_lock:
            self._job_count_cache = None

    def get_last_scoring_timestamp(self) -> datetime | None:
        """Get the timestamp of the last scoring run."""
        with connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT MAX(last_scored_at) as last_scored FROM jobs WHERE last_scored_at IS NOT NULL"
            ).fetchone()
            
        if row is None or row["last_scored"] is None:
            return None
            
        return _parse_datetime(row["last_scored"])
        
    def list_jobs_for_incremental_scoring(self, limit: int = 250) -> list[JobRecord]:
        """List jobs that need to be scored (new or updated since last scoring)."""
        last_scored = self.get_last_scoring_timestamp()
        
        if last_scored is None:
            # No previous scoring, score all jobs
            return self.list_jobs_for_scoring(limit=limit)
            
        with connect(self._db_path) as conn:
            rows = conn.execute(
                """
                SELECT id, platform, title, company, url, description, date_posted,
                       match_score, status, years_required, is_remote,
                       score_relevance, score_attainability, score_recency,
                       summary, requirements, location, county, compensation,
                       workplace_type, employment_type, department, team,
                       views, saves, applications, posted_at, posted_ago
                FROM jobs
                WHERE (last_scored_at IS NULL OR last_scored_at < updated_at)
                  AND match_score IS NULL 
                  AND status IN ('Queued', 'Notified')
                ORDER BY date_posted DESC
                LIMIT ?
                """,
                (limit,)
            ).fetchall()

        return [JobRecord.from_row(row) for row in rows]

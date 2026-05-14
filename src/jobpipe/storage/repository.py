from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from jobpipe.storage.db import connect
from jobpipe.storage.models import JobRecord, NotificationAuditRecord, ScrapeRunRecord


class JobRepository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def create_scrape_run(self, run_id: str, started_at: datetime | None = None) -> None:
        started = (started_at or datetime.now(timezone.utc)).isoformat()

        with connect(self._db_path) as conn:
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
        with connect(self._db_path) as conn:
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
            def chunked(items: list[str], size: int = 900) -> list[list[str]]:
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

            seen_ids: set[str] = set()
            for job in jobs:
                if job.id in existing_ids or job.id in seen_ids:
                    updated += 1
                else:
                    inserted += 1
                    seen_ids.add(job.id)

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
                ON CONFLICT(id) DO UPDATE SET
                    platform = excluded.platform,
                    title = excluded.title,
                    company = excluded.company,
                    url = excluded.url,
                    description = excluded.description,
                    date_posted = excluded.date_posted,
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
                    for job in jobs
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

    def update_scoring_bulk(self, updates: list[tuple]) -> None:
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

        with connect(self._db_path) as conn:
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
                normalized,
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

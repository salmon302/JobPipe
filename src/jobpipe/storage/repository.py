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
        inserted = 0
        updated = 0

        with connect(self._db_path) as conn:
            for job in jobs:
                existing = conn.execute("SELECT 1 FROM jobs WHERE id = ?", (job.id,)).fetchone()

                conn.execute(
                    """
                    INSERT INTO jobs (
                        id,
                        platform,
                        title,
                        company,
                        url,
                        description,
                        date_posted,
                        status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        platform = excluded.platform,
                        title = excluded.title,
                        company = excluded.company,
                        url = excluded.url,
                        description = excluded.description,
                        date_posted = excluded.date_posted,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        job.id,
                        job.platform,
                        job.title,
                        job.company,
                        job.url,
                        job.description,
                        job.date_posted.isoformat(),
                        job.status,
                    ),
                )

                if existing:
                    updated += 1
                else:
                    inserted += 1

            conn.commit()

        return inserted, updated

    def list_jobs_for_scoring(self, limit: int = 250) -> list[JobRecord]:
        with connect(self._db_path) as conn:
            rows = conn.execute(
                """
                SELECT id, platform, title, company, url, description, date_posted,
                       match_score, status, years_required, is_remote,
                       score_relevance, score_attainability, score_recency
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

    def list_jobs_above_threshold(self, threshold: float, limit: int = 100) -> list[JobRecord]:
        with connect(self._db_path) as conn:
            rows = conn.execute(
                """
                SELECT id, platform, title, company, url, description, date_posted,
                       match_score, status, years_required, is_remote,
                       score_relevance, score_attainability, score_recency
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
                                             score_relevance, score_attainability, score_recency
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
                       score_relevance, score_attainability, score_recency
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
                       score_relevance, score_attainability, score_recency
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
                       score_relevance, score_attainability, score_recency
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

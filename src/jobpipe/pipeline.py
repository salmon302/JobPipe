# Purpose: Process ingested jobs, score matches, notify, and stage resumes.
# Author: Seth Nenninger (GPT-5.2-Codex Agent)
# Timestamp: 2026-05-12T00:00:00Z
# Changelog: Replace scraper pipeline with ingest batch processing.

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import threading
from uuid import uuid4

from jobpipe.config import Settings
from jobpipe.notifications.windows_toast import notify_job_match
from jobpipe.resume.staging import ResumeTargetNotFoundError, stage_job_description
from jobpipe.scoring.attainability import attainability_score, should_discard_for_senior_role
from jobpipe.scoring.calculator import compute_total_match_score
from jobpipe.scoring.embeddings import LocalEmbedder, relevance_scores
from jobpipe.scoring.extractors import extract_years_required, infer_remote
from jobpipe.scoring.recency import recency_score
from jobpipe.storage.db import initialize_database
from jobpipe.storage.models import JobRecord
from jobpipe.storage.repository import JobRepository

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class RunSummary:
    ingested: int
    inserted: int
    updated: int
    scored: int
    above_threshold: int
    notified: int


@dataclass(slots=True)
class ScoreSummary:
    scored: int
    above_threshold: int
    notified: int


@dataclass(slots=True)
class IngestBatchResult:
    run_id: str
    summary: RunSummary
    scoring_in_progress: bool = False


class RunAlreadyInProgressError(RuntimeError):
    pass


class MissingMasterCVError(RuntimeError):
    pass


def _load_master_cv(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _is_stale_lock(lock_path: Path, stale_after_seconds: int) -> bool:
    if stale_after_seconds <= 0:
        return False

    try:
        age_seconds = datetime.now(timezone.utc).timestamp() - lock_path.stat().st_mtime
    except FileNotFoundError:
        return False

    return age_seconds > stale_after_seconds


def _acquire_run_lock(lock_path: Path, stale_after_seconds: int) -> None:
    if lock_path.exists() and _is_stale_lock(lock_path, stale_after_seconds):
        try:
            lock_path.unlink()
            LOGGER.warning("Removed stale run lock at %s", lock_path)
        except OSError:
            LOGGER.warning("Found stale run lock but could not remove %s", lock_path)

    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RunAlreadyInProgressError(
            f"Another run appears active. Existing lock: {lock_path}"
        ) from exc

    started_at = datetime.now(timezone.utc).isoformat()
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(f"pid={os.getpid()}\nstarted_at={started_at}\n")


def _release_run_lock(lock_path: Path) -> None:
    try:
        lock_path.unlink()
    except FileNotFoundError:
        pass


def score_pending_jobs(
    settings: Settings,
    repository: JobRepository,
    run_id: str | None = None,
    limit: int = 500,
) -> ScoreSummary:
    cv_text = _load_master_cv(settings.master_cv_path)
    if not cv_text.strip():
        raise MissingMasterCVError(
            f"Master CV is missing or empty at {settings.master_cv_path}. "
            "Create it or set JOBPIPE_MASTER_CV_PATH."
        )

    scored = 0
    updates: list[tuple] = []
    to_score_jobs: list[JobRecord] = []
    to_score_meta: list[tuple[JobRecord, int | None, bool]] = []

    for job in repository.list_jobs_for_scoring(limit=limit):
        years_required = extract_years_required(job.description)
        is_remote = bool(infer_remote(f"{job.title} {job.description}"))

        if should_discard_for_senior_role(
            required_years=years_required,
            user_years_experience=settings.user_years_experience,
        ):
            LOGGER.info(
                "Job rejected: senior role requires %s years, user has %s",
                years_required,
                settings.user_years_experience,
            )
            updates.append(
                (
                    0.0,
                    years_required,
                    is_remote,
                    "Rejected",
                    0.0,
                    0.0,
                    0.0,
                    job.id,
                )
            )
            scored += 1
            continue

        to_score_jobs.append(job)
        to_score_meta.append((job, years_required, is_remote))

    if to_score_jobs:
        embedder = LocalEmbedder(
            settings.embed_model,
            batch_size=settings.embed_batch_size,
        )
        cv_vector = embedder.embed_text(cv_text)
        relevance_values = relevance_scores(
            [job.description for job in to_score_jobs],
            cv_vector,
            embedder,
        )

        for (job, years_required, is_remote), relevance in zip(
            to_score_meta, relevance_values
        ):
            attainability_score_value, attainability_details = attainability_score(
                required_years=years_required,
                user_years_experience=settings.user_years_experience,
            )
            recency = recency_score(job.date_posted, is_remote)
            breakdown = compute_total_match_score(
                relevance=relevance,
                attainability=attainability_score_value,
                recency=recency,
            )

            updates.append(
                (
                    breakdown.total,
                    years_required,
                    is_remote,
                    "Queued",
                    breakdown.relevance,
                    breakdown.attainability,
                    breakdown.recency,
                    job.id,
                )
            )
            scored += 1

    repository.update_scoring_bulk(updates)

    above_threshold_jobs = repository.list_jobs_above_threshold(
        settings.notification_threshold
    )
    jobs_to_notify = repository.list_jobs_to_notify(settings.notification_threshold)

    notified_ids: list[str] = []
    for job in jobs_to_notify:
        if job.match_score is None:
            continue

        try:
            delivery = notify_job_match(
                title=job.title,
                company=job.company,
                score=job.match_score,
                url=job.url,
            )
            if not delivery.clickable and not delivery.url_opened:
                LOGGER.warning(
                    "Notification fallback used for job %s (backend=%s)",
                    job.id,
                    delivery.backend,
                )
            elif not delivery.clickable and delivery.url_opened:
                LOGGER.info(
                    "Notification used URL-open fallback for job %s (backend=%s)",
                    job.id,
                    delivery.backend,
                )
            repository.record_notification_event(
                run_id=run_id,
                job_id=job.id,
                title=job.title,
                company=job.company,
                score=job.match_score,
                url=job.url,
                delivery_status=f"{delivery.delivery_status}:{delivery.backend}",
            )
            notified_ids.append(job.id)
        except Exception as exc:
            repository.record_notification_event(
                run_id=run_id,
                job_id=job.id,
                title=job.title,
                company=job.company,
                score=job.match_score,
                url=job.url,
                delivery_status="Failed",
                error_message=str(exc),
            )
            LOGGER.exception("Failed notification audit write for job %s", job.id)

    repository.mark_notified(notified_ids)

    if settings.auto_stage_job_description:
        try:
            staged = stage_job_description(
                repository=repository,
                output_path=settings.job_description_path,
                minimum_score=settings.notification_threshold,
            )
            LOGGER.info(
                "Auto-staged job description | job=%s title=%s company=%s path=%s",
                staged.job_id,
                staged.title,
                staged.company,
                staged.output_path,
            )
        except ResumeTargetNotFoundError:
            LOGGER.info(
                "Auto-stage enabled but no resume target met threshold %.3f",
                settings.notification_threshold,
            )
        except Exception:
            LOGGER.exception("Auto-stage failed unexpectedly")

    return ScoreSummary(
        scored=scored,
        above_threshold=len(above_threshold_jobs),
        notified=len(notified_ids),
    )


def process_ingest_batch(settings: Settings, jobs: list[JobRecord]) -> IngestBatchResult:
    settings.validate_runtime()
    settings.ensure_runtime_dirs()
    lock_acquired = False
    release_lock = True
    repository: JobRepository | None = None
    run_id: str | None = None

    try:
        LOGGER.info("process_ingest_batch | Starting with %d jobs", len(jobs))
        _acquire_run_lock(settings.run_lock_path, settings.run_lock_stale_seconds)
        lock_acquired = True

        initialize_database(settings.db_path)

        repository = JobRepository(settings.db_path)
        run_id = f"ingest-{uuid4().hex[:12]}"
        repository.create_scrape_run(run_id)

        inserted, updated = repository.upsert_jobs(jobs)
        LOGGER.info(
            "process_ingest_batch | Upsert complete: %d inserted, %d updated",
            inserted,
            updated,
        )

        if settings.score_async:
            repository.update_scrape_run_ingest(
                run_id=run_id,
                scraped=len(jobs),
                inserted=inserted,
                updated=updated,
            )

            def _score_and_finalize() -> None:
                try:
                    score_summary = score_pending_jobs(
                        settings,
                        JobRepository(settings.db_path),
                        run_id=run_id,
                    )
                    summary = RunSummary(
                        ingested=len(jobs),
                        inserted=inserted,
                        updated=updated,
                        scored=score_summary.scored,
                        above_threshold=score_summary.above_threshold,
                        notified=score_summary.notified,
                    )
                    JobRepository(settings.db_path).complete_scrape_run(
                        run_id=run_id,
                        scraped=summary.ingested,
                        inserted=summary.inserted,
                        updated=summary.updated,
                        scored=summary.scored,
                        above_threshold=summary.above_threshold,
                        notified=summary.notified,
                    )
                except Exception as exc:  # pragma: no cover - background safety net
                    LOGGER.exception("Async scoring failed for %s", run_id)
                    try:
                        JobRepository(settings.db_path).fail_scrape_run(
                            run_id=run_id,
                            error_message=str(exc),
                        )
                    except Exception:
                        LOGGER.exception("Failed to persist async run failure for %s", run_id)
                finally:
                    _release_run_lock(settings.run_lock_path)

            thread = threading.Thread(
                target=_score_and_finalize,
                name=f"JobPipeScoreRun-{run_id}",
                daemon=True,
            )
            thread.start()
            # Release the ingest lock immediately so new batches can arrive while
            # scoring continues in the background.
            _release_run_lock(settings.run_lock_path)
            release_lock = False

            summary = RunSummary(
                ingested=len(jobs),
                inserted=inserted,
                updated=updated,
                scored=0,
                above_threshold=0,
                notified=0,
            )
            return IngestBatchResult(run_id=run_id, summary=summary, scoring_in_progress=True)

        score_summary = score_pending_jobs(settings, repository, run_id=run_id)

        summary = RunSummary(
            ingested=len(jobs),
            inserted=inserted,
            updated=updated,
            scored=score_summary.scored,
            above_threshold=score_summary.above_threshold,
            notified=score_summary.notified,
        )
        repository.complete_scrape_run(
            run_id=run_id,
            scraped=summary.ingested,
            inserted=summary.inserted,
            updated=summary.updated,
            scored=summary.scored,
            above_threshold=summary.above_threshold,
            notified=summary.notified,
        )
        return IngestBatchResult(run_id=run_id, summary=summary)
    except Exception as exc:
        if repository is not None and run_id is not None:
            try:
                repository.fail_scrape_run(run_id=run_id, error_message=str(exc))
            except Exception:  # pragma: no cover - defensive telemetry path
                LOGGER.exception("Failed to persist run failure for %s", run_id)
        raise
    finally:
        if lock_acquired and release_lock:
            _release_run_lock(settings.run_lock_path)

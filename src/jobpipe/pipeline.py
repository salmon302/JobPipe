from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
from uuid import uuid4

from jobpipe.config import Settings
from jobpipe.notifications.windows_toast import notify_job_match
from jobpipe.resume.staging import ResumeTargetNotFoundError, stage_job_description
from jobpipe.scoring.attainability import attainability_score, should_discard_for_senior_role
from jobpipe.scoring.calculator import compute_total_match_score
from jobpipe.scoring.embeddings import LocalEmbedder, relevance_score
from jobpipe.scoring.extractors import extract_years_required, infer_remote
from jobpipe.scoring.prefilter import passes_prefilter
from jobpipe.scoring.recency import recency_score
from jobpipe.scrapers.auth_state import UnusableStorageStateError
from jobpipe.scrapers.base import JobScraper
from jobpipe.scrapers.builtin import BuiltInScraper, BuiltInScraperConfig
from jobpipe.scrapers.hiringcafe import HiringCafeScraper, HiringCafeScraperConfig
from jobpipe.scrapers.wellfound import WellfoundScraper, WellfoundScraperConfig
from jobpipe.storage.db import initialize_database
from jobpipe.storage.repository import JobRepository

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class RunSummary:
    scraped: int
    inserted: int
    updated: int
    scored: int
    above_threshold: int
    notified: int


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


def _build_scrapers(settings: Settings) -> list[tuple[str, JobScraper]]:
    scrapers: list[tuple[str, JobScraper]] = [
        (
            "hiringcafe",
            HiringCafeScraper(
                HiringCafeScraperConfig(
                    base_url=settings.hiringcafe_base_url,
                    search_urls=tuple(settings.platform_search_urls("hiringcafe")),
                    storage_state=settings.hiringcafe_storage_state,
                    headless=settings.hiringcafe_headless,
                    jitter_min=settings.hiringcafe_jitter_min,
                    jitter_max=settings.hiringcafe_jitter_max,
                    fetch_detail_descriptions=settings.hiringcafe_fetch_detail_descriptions,
                    user_agents=tuple(settings.platform_user_agents("hiringcafe")),
                    require_usable_auth_state=settings.require_usable_auth_state,
                )
            ),
        )
    ]

    if settings.wellfound_enabled:
        scrapers.append(
            (
                "wellfound",
                WellfoundScraper(
                    WellfoundScraperConfig(
                        base_url=settings.wellfound_base_url,
                        search_urls=tuple(settings.platform_search_urls("wellfound")),
                        storage_state=settings.wellfound_storage_state,
                        headless=settings.wellfound_headless,
                        jitter_min=settings.wellfound_jitter_min,
                        jitter_max=settings.wellfound_jitter_max,
                        fetch_detail_descriptions=settings.wellfound_fetch_detail_descriptions,
                        user_agents=tuple(settings.platform_user_agents("wellfound")),
                        require_usable_auth_state=settings.require_usable_auth_state,
                    )
                ),
            )
        )

    if settings.builtin_enabled:
        scrapers.append(
            (
                "builtin",
                BuiltInScraper(
                    BuiltInScraperConfig(
                        base_url=settings.builtin_base_url,
                        search_urls=tuple(settings.platform_search_urls("builtin")),
                        storage_state=settings.builtin_storage_state,
                        headless=settings.builtin_headless,
                        jitter_min=settings.builtin_jitter_min,
                        jitter_max=settings.builtin_jitter_max,
                        fetch_detail_descriptions=settings.builtin_fetch_detail_descriptions,
                        user_agents=tuple(settings.platform_user_agents("builtin")),
                        require_usable_auth_state=settings.require_usable_auth_state,
                    )
                ),
            )
        )

    return scrapers


async def run_once(settings: Settings, max_pages: int = 1) -> RunSummary:
    settings.validate_scraping_runtime()
    settings.ensure_runtime_dirs()
    lock_acquired = False

    try:
        _acquire_run_lock(settings.run_lock_path, settings.run_lock_stale_seconds)
        lock_acquired = True

        initialize_database(settings.db_path)

        repository = JobRepository(settings.db_path)
        run_id = f"run-{uuid4().hex[:12]}"
        repository.create_scrape_run(run_id)

        try:
            scraped_jobs = []
            for platform_name, scraper in _build_scrapers(settings):
                try:
                    platform_jobs = await scraper.scrape(max_pages=max_pages)
                except UnusableStorageStateError:
                    LOGGER.exception(
                        "Strict auth-state failure for platform %s",
                        platform_name,
                    )
                    raise
                except Exception:
                    LOGGER.exception("Scraper failure for platform %s", platform_name)
                    continue

                LOGGER.info(
                    "Scraped %s jobs from %s",
                    len(platform_jobs),
                    platform_name,
                )
                scraped_jobs.extend(platform_jobs)

            inserted, updated = repository.upsert_jobs(scraped_jobs)

            cv_text = _load_master_cv(settings.master_cv_path)
            if not cv_text.strip():
                raise MissingMasterCVError(
                    f"Master CV is missing or empty at {settings.master_cv_path}. "
                    "Create it or set JOBPIPE_MASTER_CV_PATH."
                )
            scored = 0

            embedder = LocalEmbedder(settings.embed_model)

            for job in repository.list_jobs_for_scoring(limit=500):
                if not passes_prefilter(
                    title=job.title,
                    description=job.description,
                    critical_skills=settings.critical_skills,
                    reject_terms=settings.reject_terms,
                ):
                    repository.update_scoring(
                        job_id=job.id,
                        match_score=0.0,
                        years_required=extract_years_required(job.description),
                        is_remote=infer_remote(f"{job.title} {job.description}"),
                        status="Rejected",
                        score_relevance=0.0,
                        score_attainability=0.0,
                        score_recency=0.0,
                    )
                    scored += 1
                    continue

                years_required = extract_years_required(job.description)
                is_remote = infer_remote(f"{job.title} {job.description}")

                if should_discard_for_senior_role(
                    required_years=years_required,
                    user_years_experience=settings.user_years_experience,
                ):
                    repository.update_scoring(
                        job_id=job.id,
                        match_score=0.0,
                        years_required=years_required,
                        is_remote=is_remote,
                        status="Rejected",
                        score_relevance=0.0,
                        score_attainability=0.0,
                        score_recency=0.0,
                    )
                    scored += 1
                    continue

                relevance = relevance_score(job.description, cv_text, embedder)
                attainability = attainability_score(
                    required_years=years_required,
                    user_years_experience=settings.user_years_experience,
                )

                recency = recency_score(job.date_posted, is_remote)
                breakdown = compute_total_match_score(
                    relevance=relevance,
                    attainability=attainability,
                    recency=recency,
                )

                repository.update_scoring(
                    job_id=job.id,
                    match_score=breakdown.total,
                    years_required=years_required,
                    is_remote=is_remote,
                    status="Queued",
                    score_relevance=breakdown.relevance,
                    score_attainability=breakdown.attainability,
                    score_recency=breakdown.recency,
                )
                scored += 1

            above_threshold_jobs = repository.list_jobs_above_threshold(settings.notification_threshold)
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

            summary = RunSummary(
                scraped=len(scraped_jobs),
                inserted=inserted,
                updated=updated,
                scored=scored,
                above_threshold=len(above_threshold_jobs),
                notified=len(notified_ids),
            )
            repository.complete_scrape_run(
                run_id=run_id,
                scraped=summary.scraped,
                inserted=summary.inserted,
                updated=summary.updated,
                scored=summary.scored,
                above_threshold=summary.above_threshold,
                notified=summary.notified,
            )
            return summary
        except Exception as exc:
            try:
                repository.fail_scrape_run(run_id=run_id, error_message=str(exc))
            except Exception:  # pragma: no cover - defensive telemetry path
                LOGGER.exception("Failed to persist scrape run failure for %s", run_id)
            raise
    finally:
        if lock_acquired:
            _release_run_lock(settings.run_lock_path)

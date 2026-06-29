# Purpose: Process ingested jobs, score matches, notify, and stage resumes.
# Author: Seth Nenninger (GPT-5.2-Codex Agent)
# Timestamp: 2026-05-12T00:00:00Z
# Changelog: Replace scraper pipeline with ingest batch processing.

from __future__ import annotations

import sqlite3

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import threading
from uuid import uuid4

import numpy as np

from jobpipe.config import Settings
from jobpipe.notifications.windows_toast import notify_job_match
from jobpipe.resume.staging import ResumeTargetNotFoundError, stage_job_description
from jobpipe.scoring.attainability import attainability_score, should_discard_for_senior_role
from jobpipe.scoring.calculator import (
    ScoreWeights,
    SectionWeights,
    compute_blended_relevance,
    compute_confidence,
    compute_total_match_score,
    cosine_similarity,
    _detect_job_type,
    select_weights_for_job_type,
)
from jobpipe.scoring.cv_parser import ParsedCV, parse_cv_text
from jobpipe.scoring.domain_matcher import domain_alignment_score
from jobpipe.scoring.embeddings import LocalEmbedder, relevance_scores
from jobpipe.scoring.extractors import extract_years_required, infer_remote
from jobpipe.scoring.keyword_scorer import build_keyword_lexicon, keyword_density_score
from jobpipe.scoring.recency import recency_score
from jobpipe.storage.db import initialize_database
from jobpipe.storage.models import JobRecord
from jobpipe.storage.repository import JobRepository

LOGGER = logging.getLogger(__name__)

# Limit concurrent scoring threads to prevent connection pool exhaustion
_scoring_semaphore = threading.Semaphore(2)


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

    # Check if lock is old enough to be stale
    if age_seconds > stale_after_seconds:
        return True

    # Check if the process that created the lock is still alive
    try:
        with open(lock_path, "r", encoding="utf-8") as f:
            content = f.read()
            for line in content.splitlines():
                if line.startswith("pid="):
                    pid = int(line.split("=", 1)[1])
                    # Check if process is still running
                    try:
                        os.kill(pid, 0)  # Signal 0 just checks if process exists
                        return False  # Process is alive, lock is not stale
                    except (OSError, ProcessLookupError):
                        # Process doesn't exist, lock is stale
                        LOGGER.info("Lock file PID %d is not running, treating as stale", pid)
                        return True
    except (FileNotFoundError, ValueError, OSError):
        # Can't read lock file or parse PID, treat as stale if old enough
        pass

    return False


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


def _parse_master_cv(settings: Settings) -> tuple[str, object | None]:
    """Load and parse the Master CV, returning (raw_text, parsed_cv_or_None)."""
    cv_text = _load_master_cv(settings.master_cv_path)
    if not cv_text.strip():
        raise MissingMasterCVError(
            f"Master CV is missing or empty at {settings.master_cv_path}. "
            "Create it or set JOBPIPE_MASTER_CV_PATH."
        )
    try:
        parsed = parse_cv_text(cv_text)
        LOGGER.info(
            "Parsed CV: %d skills, %d education entries, %d experience entries, %d projects",
            len(parsed.skills.all_skills()),
            len(parsed.education),
            len(parsed.experience),
            len(parsed.projects),
        )
        return cv_text, parsed
    except Exception:
        LOGGER.exception("CV parsing failed, falling back to flat text")
        return cv_text, None


def score_pending_jobs(
    settings: Settings,
    repository: JobRepository,
    run_id: str | None = None,
    limit: int = 500,
) -> ScoreSummary:
    import time
    pipeline_start = time.time()
    
    cv_text, parsed_cv = _parse_master_cv(settings)
    cv_parsed = parsed_cv is not None
    
    embed_start = time.time()
    # We still compute full-CV embedding for the legacy flat similarity
    # (used as a fallback dimension)
    embedder = LocalEmbedder(
        settings.embed_model,
        batch_size=settings.embed_batch_size,
        quantize=settings.embed_quantize,
    )
    flat_cv_vector = embedder.embed_text(cv_text)
    embed_time = time.time() - embed_start
    LOGGER.info("CV embedding completed in %.2fs", embed_time)

    # Build keyword lexicon from parsed CV (if available)
    keyword_lexicon: dict[str, float] = {}
    if parsed_cv is not None:
        keyword_lexicon = build_keyword_lexicon(parsed_cv)  # type: ignore[arg-type]

    # Build section weights from settings
    section_weights = SectionWeights(
        skills=settings.skills_section_weight,
        experience=settings.experience_section_weight,
        education=settings.education_section_weight,
        projects=settings.projects_section_weight,
    )

    scored = 0
    updates: list[tuple] = []
    to_score_jobs: list[JobRecord] = []
    to_score_meta: list[tuple[JobRecord, int | None, bool]] = []

    # Use incremental scoring to only score jobs that need it
    for job in repository.list_jobs_for_incremental_scoring(limit=limit):
        years_required = extract_years_required(job.description)
        is_remote = bool(infer_remote(f"{job.title} {job.description}"))

        # ---- Early recency filter: reject old jobs immediately ----
        rec = recency_score(job.date_posted, is_remote)
        if rec < 0.1:  # Skip jobs older than ~7 days
            repository.update_scoring(
                job.id,
                0.0,              # match_score
                years_required,   # years_required
                is_remote,        # is_remote
                "Rejected",       # status
                score_relevance=0.0,
                score_attainability=0.0,
                score_recency=0.0,
            )
            scored += 1
            continue

        # Experience-based filtering removed - users filter by years in UI
        # The attainability score already penalizes experience mismatches
        # without hard-rejecting jobs that users might want to see

        to_score_jobs.append(job)
        to_score_meta.append((job, years_required, is_remote))

    if to_score_jobs:
        cv_sections = parsed_cv.to_section_dict() if parsed_cv is not None else {}
        job_descriptions = [job.description for job in to_score_jobs]

        # Pre-compute section vectors once if CV is parsed
        section_vectors: dict[str, object] = {}
        sec_map = {}
        if cv_sections:
            sec_map = {
                "skills": section_weights.skills,
                "experience": section_weights.experience,
                "education": section_weights.education,
                "projects": section_weights.projects,
                "summary": getattr(section_weights, 'summary', 0.05),
            }
            for sec_name in sec_map:
                sec_text = cv_sections.get(sec_name, "").strip()
                if sec_text:
                    section_vectors[sec_name] = embedder.embed_text(sec_text)

        # Embed job descriptions ONCE (avoids double-embedding)
        # This single embedding is used for both flat relevance and section scoring
        LOGGER.info("Embedding %d job descriptions (single pass)", len(job_descriptions))
        job_vectors = embedder.embed_texts(job_descriptions)

        # Compute flat relevance from the already-embedded vectors
        cv_vec = np.asarray(flat_cv_vector, dtype=float).reshape(-1)
        similarities = np.dot(job_vectors, cv_vec)
        similarities = np.clip(similarities, -1.0, 1.0)
        flat_relevance_values = ((similarities + 1.0) / 2.0).tolist()

        # Vectorized section-weighted relevance computation
        if section_vectors and job_vectors is not None:
            # Pre-compute section weights array
            sec_names = list(section_vectors.keys())
            sec_weights = np.array([sec_map[name] for name in sec_names])
            sec_weights_sum = sec_weights.sum()
            
            # Stack section vectors into matrix: shape (num_sections, embedding_dim)
            sec_matrix = np.stack([section_vectors[name] for name in sec_names])
            
            # Compute cosine similarities in batch: job_vectors @ sec_matrix.T
            # job_vectors: (num_jobs, embedding_dim)
            # sec_matrix: (num_sections, embedding_dim)
            # similarities: (num_jobs, num_sections)
            similarities = np.dot(job_vectors, sec_matrix.T)
            
            # Normalize to [0, 1] range
            sec_scores = (np.clip(similarities, -1.0, 1.0) + 1.0) / 2.0
            
            # Weighted average across sections
            weighted_scores = np.dot(sec_scores, sec_weights) / sec_weights_sum
            
            # Build detail strings (only for logging/debugging)
            section_emb_scores = weighted_scores.tolist()
            section_details = []
            for idx in range(len(to_score_meta)):
                parts = [f"{sec_names[i]}:{sec_scores[idx, i]:.3f}(w={sec_weights[i]:.2f})" 
                         for i in range(len(sec_names))]
                section_details.append(", ".join(parts))
        else:
            section_emb_scores = flat_relevance_values
            section_details = ["flat_only"] * len(to_score_meta)

        for idx, (job, years_required, is_remote) in enumerate(to_score_meta):
            # ---- Blended relevance ----
            section_emb_score = section_emb_scores[idx]
            section_detail = section_details[idx]

            # Keyword density score
            kw_score, kw_detail = keyword_density_score(job.description, keyword_lexicon) if keyword_lexicon else (0.5, "no_lexicon")

            # Domain alignment
            dom_score, dom_detail = domain_alignment_score(job.title, job.description, parsed_cv) if parsed_cv else (0.5, "no_cv")

            # Boost relevance for strong keyword/domain matches
            blended_relevance, rel_detail = compute_blended_relevance(
                embedding_score=section_emb_score,
                keyword_score=kw_score,
                domain_score=dom_score,
            )
            
            # Apply relevance boost: if keyword + domain both strong, boost by 10%
            if kw_score > 0.6 and dom_score > 0.8:
                blended_relevance = min(1.0, blended_relevance * 1.1)
                rel_detail += " [boosted]"

            # ---- Attainability ----
            att_score, att_detail = attainability_score(
                required_years=years_required,
                user_years_experience=settings.user_years_experience,
                cv=parsed_cv,
                job_description=job.description,
                job_title=job.title,
                is_remote_job=is_remote,
            )
            
            # Penalize attainability for domain mismatches
            if dom_score < 0.3:  # Complete domain mismatch
                att_score = att_score * 0.7  # Additional 30% penalty
                att_detail += " [domain_penalty]"

            # ---- Recency (recomputed above) ----
            # rec is already computed above

            # ---- Dynamic weights by job type ----
            job_type = _detect_job_type(job.title, job.description)
            weights = select_weights_for_job_type(job_type)

            confidence_level, confidence_reason = compute_confidence(rel_detail, att_detail, cv_parsed=cv_parsed)

            breakdown = compute_total_match_score(
                relevance=blended_relevance,
                attainability=att_score,
                recency=rec,
                weights=weights,
                confidence=confidence_level,
                confidence_reason=confidence_reason,
            )

            full_details = (
                f"type={job_type}, embed({section_detail}), "
                f"kw({kw_detail}), domain({dom_detail}), "
                f"attain({att_detail}), conf={confidence_level}: {confidence_reason}"
            )

            updates.append((
                breakdown.total, years_required, is_remote, "Queued",
                breakdown.relevance, breakdown.attainability, breakdown.recency,
                job.id,
            ))
            scored += 1

    # Update last_scored_at timestamp for scored jobs
    now = datetime.now(timezone.utc).isoformat()
    scored_ids = [job.id for job in to_score_jobs]
    
    if scored_ids:
        LOGGER.debug("Updating last_scored_at for %d jobs", len(scored_ids))
        try:
            repository.update_last_scored_at(scored_ids, now)
            LOGGER.debug("last_scored_at updated")
        except Exception as exc:
            LOGGER.warning("Failed to update last_scored_at: %s", exc)
    
    if updates:
        LOGGER.debug("Updating scoring for %d jobs", len(updates))
        try:
            repository.update_scoring_bulk(updates)
            LOGGER.debug("Scoring updates applied")
        except Exception as exc:
            LOGGER.warning("Failed to update scoring: %s", exc)
    else:
        LOGGER.debug("No scoring updates to apply")
    
    pipeline_time = time.time() - pipeline_start
    LOGGER.info(
        "Scoring pipeline completed: %d jobs scored in %.2fs (%.0f jobs/sec)",
        scored, pipeline_time, scored / pipeline_time if pipeline_time > 0 else 0
    )

    # Early exit if no jobs were scored - skip notification and staging
    if scored == 0:
        LOGGER.info("No jobs scored, skipping notifications and staging")
        LOGGER.debug("Creating ScoreSummary object")
        result = ScoreSummary(
            scored=0,
            above_threshold=0,
            notified=0,
        )
        LOGGER.debug("ScoreSummary created, returning from score_pending_jobs")
        return result

    LOGGER.debug("Querying jobs above threshold (%.3f)", settings.notification_threshold)
    try:
        above_threshold_jobs = repository.list_jobs_above_threshold(
            settings.notification_threshold
        )
        LOGGER.debug("Found %d jobs above threshold", len(above_threshold_jobs))
    except Exception as exc:
        LOGGER.warning("Failed to query jobs above threshold: %s", exc)
        above_threshold_jobs = []
    
    LOGGER.debug("Querying jobs to notify")
    try:
        jobs_to_notify = repository.list_jobs_to_notify(settings.notification_threshold)
        LOGGER.debug("Found %d jobs to notify", len(jobs_to_notify))
    except Exception as exc:
        LOGGER.warning("Failed to query jobs to notify: %s", exc)
        jobs_to_notify = []

    # Cap notifications per batch to prevent blocking the pipeline
    # (each notification may open a browser tab or show a toast)
    max_notifications_per_batch = 3
    if len(jobs_to_notify) > max_notifications_per_batch:
        LOGGER.info(
            "Limiting notifications from %d to %d jobs (highest scoring only)",
            len(jobs_to_notify),
            max_notifications_per_batch,
        )
        jobs_to_notify = jobs_to_notify[:max_notifications_per_batch]

    notified_ids: list[str] = []
    notification_events: list[tuple] = []
    now_iso = datetime.now(timezone.utc).isoformat()
    
    # Timeout for each notification (seconds) - prevents hanging on browser operations
    notification_timeout_seconds = 5.0
    
    for job in jobs_to_notify:
        if job.match_score is None:
            continue

        # Run notification in a thread with timeout to prevent blocking
        result_container: list[object] = []
        exception_container: list[Exception] = []
        
        def _send_notification():
            try:
                delivery = notify_job_match(
                    title=job.title,
                    company=job.company,
                    score=job.match_score,
                    url=job.url,
                )
                result_container.append(delivery)
            except Exception as exc:
                exception_container.append(exc)
        
        notification_thread = threading.Thread(target=_send_notification, daemon=True)
        notification_thread.start()
        notification_thread.join(timeout=notification_timeout_seconds)
        
        # Check if notification completed or timed out
        if notification_thread.is_alive():
            # Thread is still running - timeout occurred
            LOGGER.warning(
                "Notification timed out after %.1fs for job %s (title=%s)",
                notification_timeout_seconds,
                job.id,
                job.title,
            )
            notification_events.append((
                run_id,
                job.id,
                job.title,
                job.company,
                job.match_score,
                job.url,
                "Timeout",
                f"Notification exceeded {notification_timeout_seconds}s timeout",
                now_iso,
            ))
            continue
        
        # Check if exception occurred
        if exception_container:
            exc = exception_container[0]
            notification_events.append((
                run_id,
                job.id,
                job.title,
                job.company,
                job.match_score,
                job.url,
                "Failed",
                str(exc),
                now_iso,
            ))
            LOGGER.exception("Failed notification for job %s", job.id)
            continue
        
        # Success path
        if result_container:
            delivery = result_container[0]
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
            notification_events.append((
                run_id,
                job.id,
                job.title,
                job.company,
                job.match_score,
                job.url,
                f"{delivery.delivery_status}:{delivery.backend}",
                None,
                now_iso,
            ))
            notified_ids.append(job.id)

    # Batch write all notification events in a single transaction
    if notification_events:
        try:
            repository.record_notification_events_bulk(notification_events)
            LOGGER.debug("Recorded %d notification events", len(notification_events))
        except Exception:
            LOGGER.exception("Failed to record notification events")
    
    if notified_ids:
        try:
            repository.mark_notified(notified_ids)
            LOGGER.debug("Marked %d jobs as notified", len(notified_ids))
        except Exception:
            LOGGER.exception("Failed to mark jobs as notified")

    if settings.auto_stage_job_description:
        # Run auto-staging with timeout to prevent blocking
        staging_timeout = 10.0
        staging_result: list[object] = []
        staging_exception: list[Exception] = []
        
        def _run_staging():
            try:
                staged = stage_job_description(
                    repository=repository,
                    output_path=settings.job_description_path,
                    minimum_score=settings.notification_threshold,
                )
                staging_result.append(staged)
            except Exception as exc:
                staging_exception.append(exc)
        
        staging_thread = threading.Thread(target=_run_staging, daemon=True)
        staging_thread.start()
        staging_thread.join(timeout=staging_timeout)
        
        if staging_thread.is_alive():
            LOGGER.warning(
                "Auto-staging timed out after %.1fs",
                staging_timeout,
            )
        elif staging_exception:
            exc = staging_exception[0]
            if isinstance(exc, ResumeTargetNotFoundError):
                LOGGER.info(
                    "Auto-stage enabled but no resume target met threshold %.3f",
                    settings.notification_threshold,
                )
            else:
                LOGGER.exception("Auto-stage failed unexpectedly: %s", exc)
        elif staging_result:
            staged = staging_result[0]
            LOGGER.info(
                "Auto-staged job description | job=%s title=%s company=%s path=%s",
                staged.job_id,
                staged.title,
                staged.company,
                staged.output_path,
            )

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

        repository = JobRepository(settings.db_path, settings)
        run_id = f"ingest-{uuid4().hex[:12]}"
        repository.create_scrape_run(run_id)

        inserted, updated = repository.upsert_jobs(jobs)
        LOGGER.info(
            "process_ingest_batch | Upsert complete: %d inserted, %d updated",
            inserted,
            updated,
        )

        if not settings.auto_scoring_enabled:
            LOGGER.info("Auto scoring is disabled. Skipping scoring for run %s", run_id)
            repository.update_scrape_run_ingest(
                run_id=run_id,
                scraped=len(jobs),
                inserted=inserted,
                updated=updated,
            )
            _release_run_lock(settings.run_lock_path)
            summary = RunSummary(
                ingested=len(jobs),
                inserted=inserted,
                updated=updated,
                scored=0,
                above_threshold=0,
                notified=0,
            )
            return IngestBatchResult(run_id=run_id, summary=summary)

        if settings.score_async:
            repository.update_scrape_run_ingest(
                run_id=run_id,
                scraped=len(jobs),
                inserted=inserted,
                updated=updated,
            )

            def _score_and_finalize() -> None:
                # Acquire semaphore to limit concurrent scoring threads
                _scoring_semaphore.acquire()
                try:
                    score_summary = score_pending_jobs(
                        settings,
                        repository,
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
                    repository.complete_scrape_run(
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
                        repository.fail_scrape_run(
                            run_id=run_id,
                            error_message=str(exc),
                        )
                    except Exception:
                        LOGGER.exception("Failed to persist async run failure for %s", run_id)
                finally:
                    _scoring_semaphore.release()
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

        if settings.auto_scoring_enabled:
            LOGGER.info("Starting scoring pipeline for run %s", run_id)
            score_summary = score_pending_jobs(settings, repository, run_id=run_id)
            LOGGER.info("Scoring pipeline returned for run %s", run_id)

            summary = RunSummary(
                ingested=len(jobs),
                inserted=inserted,
                updated=updated,
                scored=score_summary.scored,
                above_threshold=score_summary.above_threshold,
                notified=score_summary.notified,
            )
            LOGGER.info("Created RunSummary for run %s", run_id)
        else:
            summary = RunSummary(
                ingested=len(jobs),
                inserted=inserted,
                updated=updated,
                scored=0,
                above_threshold=0,
                notified=0,
            )
        
        LOGGER.info("Completing scrape run %s", run_id)
        repository.complete_scrape_run(
            run_id=run_id,
            scraped=summary.ingested,
            inserted=summary.inserted,
            updated=summary.updated,
            scored=summary.scored,
            above_threshold=summary.above_threshold,
            notified=summary.notified,
        )
        LOGGER.info("Scrape run %s completed, returning result", run_id)
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

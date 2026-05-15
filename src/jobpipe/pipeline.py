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
    cv_text, parsed_cv = _parse_master_cv(settings)
    cv_parsed = parsed_cv is not None
    # We still compute full-CV embedding for the legacy flat similarity
    # (used as a fallback dimension)
    embedder = LocalEmbedder(
        settings.embed_model,
        batch_size=settings.embed_batch_size,
    )
    flat_cv_vector = embedder.embed_text(cv_text)

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

    for job in repository.list_jobs_for_scoring(limit=limit):
        years_required = extract_years_required(job.description)
        is_remote = bool(infer_remote(f"{job.title} {job.description}"))

        # ---- Early recency filter: reject old jobs immediately ----
        rec = recency_score(job.date_posted, is_remote)
        if rec < 0.1:  # Skip jobs older than ~7 days
            repository.update_scoring(
                job.id,
                0.0,  # total
                0.0,  # relevance
                0.0,  # attainability
                0.0,  # recency
                "Rejected",
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

        # Compute flat relevance as baseline
        flat_relevance_values = relevance_scores(
            job_descriptions,
            flat_cv_vector,
            embedder,
        )

        # Pre-compute section vectors once if CV is parsed
        section_vectors: dict[str, object] = {}
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

        # Batch-embed job descriptions for section scoring
        job_vectors = embedder.embed_texts(job_descriptions) if section_vectors else None

        for idx, (job, years_required, is_remote) in enumerate(to_score_meta):
            # ---- Blended relevance ----
            # Section-weighted embedding score
            if section_vectors and job_vectors is not None:
                job_vec = job_vectors[idx]
                weighted_sum = 0.0
                weight_sum = 0.0
                sec_parts = []
                for sec_name, sec_vec in section_vectors.items():
                    weight = sec_map[sec_name]
                    sim = max(-1.0, min(1.0, cosine_similarity(sec_vec, job_vec)))
                    sec_score = (sim + 1.0) / 2.0
                    weighted_sum += sec_score * weight
                    weight_sum += weight
                    sec_parts.append(f"{sec_name}:{sec_score:.3f}(w={weight})")
                section_emb_score = weighted_sum / weight_sum if weight_sum > 0 else flat_relevance_values[idx]
                section_detail = ", ".join(sec_parts) if sec_parts else "flat_fallback"
            else:
                section_emb_score = flat_relevance_values[idx]
                section_detail = "flat_only"

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

            confidence = compute_confidence(rel_detail, att_detail, cv_parsed=cv_parsed)

            breakdown = compute_total_match_score(
                relevance=blended_relevance,
                attainability=att_score,
                recency=rec,
                weights=weights,
                confidence=confidence,
            )

            full_details = (
                f"type={job_type}, embed({section_detail}), "
                f"kw({kw_detail}), domain({dom_detail}), "
                f"attain({att_detail}), conf={confidence}"
            )

            updates.append((
                breakdown.total, years_required, is_remote, "Queued",
                breakdown.relevance, breakdown.attainability, breakdown.recency,
                job.id,
            ))
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

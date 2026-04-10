from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import pytest

from jobpipe.config import Settings
from jobpipe.notifications.windows_toast import NotificationDeliveryResult
from jobpipe.pipeline import run_once
from jobpipe.scrapers.auth_state import UnusableStorageStateError
from jobpipe.resume.staging import stage_job_description
from jobpipe.storage.models import JobRecord
from jobpipe.storage.repository import JobRepository


class _FakeScraper:
    def __init__(self, jobs: list[JobRecord]) -> None:
        self._jobs = jobs

    async def scrape(self, max_pages: int = 1) -> list[JobRecord]:
        _ = max_pages
        return list(self._jobs)


class _FailingStrictAuthScraper:
    async def scrape(self, max_pages: int = 1) -> list[JobRecord]:
        _ = max_pages
        raise UnusableStorageStateError("strict auth-state unavailable")


def test_run_once_orchestrates_scrape_score_notify_and_stage(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "jobpipe.db"
    cv_path = tmp_path / "Master_CV.md"
    jd_path = tmp_path / "Job_Description.md"
    lock_path = tmp_path / "runtime" / "aggregator.lock"

    cv_path.write_text("Python backend engineer with API and SQL experience", encoding="utf-8")

    monkeypatch.setenv("JOBPIPE_DB_PATH", str(db_path))
    monkeypatch.setenv("JOBPIPE_MASTER_CV_PATH", str(cv_path))
    monkeypatch.setenv("JOBPIPE_JOB_DESCRIPTION_PATH", str(jd_path))
    monkeypatch.setenv("JOBPIPE_RUN_LOCK_PATH", str(lock_path))
    settings = Settings.from_env()

    jobs = [
        JobRecord(
            id="hiringcafe-901",
            platform="HiringCafe",
            title="Backend Engineer",
            company="Acme",
            url="https://hiring.cafe/jobs/901",
            description="Python API role, 2+ years experience, remote",
            date_posted=datetime.now(timezone.utc),
        ),
        JobRecord(
            id="hiringcafe-902",
            platform="HiringCafe",
            title="Platform Engineer",
            company="Beta",
            url="https://hiring.cafe/jobs/902",
            description="Python platform role requiring 7+ years experience",
            date_posted=datetime.now(timezone.utc),
        ),
    ]

    monkeypatch.setattr(
        "jobpipe.pipeline._build_scrapers",
        lambda cfg: [("fake", _FakeScraper(jobs))],
    )
    monkeypatch.setattr("jobpipe.pipeline.LocalEmbedder", lambda model_name: object())
    monkeypatch.setattr(
        "jobpipe.pipeline.relevance_score",
        lambda job_text, cv_text, embedder: 0.95,
    )
    monkeypatch.setattr(
        "jobpipe.pipeline.notify_job_match",
        lambda title, company, score, url: NotificationDeliveryResult(
            delivery_status="ToastClickable",
            backend="test-backend",
            clickable=True,
        ),
    )

    summary = asyncio.run(run_once(settings, max_pages=1))

    assert summary.scraped == 2
    assert summary.inserted == 2
    assert summary.updated == 0
    assert summary.scored == 2
    assert summary.above_threshold == 1
    assert summary.notified == 1

    repo = JobRepository(db_path)
    top = repo.list_top_jobs(limit=10)
    assert len(top) == 2

    best = top[0]
    assert best.id == "hiringcafe-901"
    assert best.status == "Notified"
    assert best.match_score is not None
    assert best.match_score >= settings.notification_threshold

    rejected = next(record for record in top if record.id == "hiringcafe-902")
    assert rejected.status == "Rejected"
    assert rejected.match_score == 0.0

    events = repo.list_recent_notifications(limit=5)
    assert len(events) == 1
    assert events[0].job_id == "hiringcafe-901"
    assert events[0].delivery_status == "ToastClickable:test-backend"

    staged = stage_job_description(
        repository=repo,
        output_path=jd_path,
        minimum_score=settings.notification_threshold,
    )
    assert staged.job_id == "hiringcafe-901"
    assert Path(staged.output_path).exists() is True


def test_run_once_auto_stages_job_description_when_enabled(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "jobpipe.db"
    cv_path = tmp_path / "Master_CV.md"
    jd_path = tmp_path / "Job_Description.md"
    lock_path = tmp_path / "runtime" / "aggregator.lock"

    cv_path.write_text("Python backend engineer with API and SQL experience", encoding="utf-8")

    monkeypatch.setenv("JOBPIPE_DB_PATH", str(db_path))
    monkeypatch.setenv("JOBPIPE_MASTER_CV_PATH", str(cv_path))
    monkeypatch.setenv("JOBPIPE_JOB_DESCRIPTION_PATH", str(jd_path))
    monkeypatch.setenv("JOBPIPE_RUN_LOCK_PATH", str(lock_path))
    monkeypatch.setenv("JOBPIPE_AUTO_STAGE_JOB_DESCRIPTION", "true")
    settings = Settings.from_env()

    jobs = [
        JobRecord(
            id="hiringcafe-901",
            platform="HiringCafe",
            title="Backend Engineer",
            company="Acme",
            url="https://hiring.cafe/jobs/901",
            description="Python API role, 2+ years experience, remote",
            date_posted=datetime.now(timezone.utc),
        ),
        JobRecord(
            id="hiringcafe-902",
            platform="HiringCafe",
            title="Platform Engineer",
            company="Beta",
            url="https://hiring.cafe/jobs/902",
            description="Python platform role requiring 7+ years experience",
            date_posted=datetime.now(timezone.utc),
        ),
    ]

    monkeypatch.setattr(
        "jobpipe.pipeline._build_scrapers",
        lambda cfg: [("fake", _FakeScraper(jobs))],
    )
    monkeypatch.setattr("jobpipe.pipeline.LocalEmbedder", lambda model_name: object())
    monkeypatch.setattr(
        "jobpipe.pipeline.relevance_score",
        lambda job_text, cv_text, embedder: 0.95,
    )
    monkeypatch.setattr(
        "jobpipe.pipeline.notify_job_match",
        lambda title, company, score, url: NotificationDeliveryResult(
            delivery_status="ToastClickable",
            backend="test-backend",
            clickable=True,
        ),
    )

    summary = asyncio.run(run_once(settings, max_pages=1))

    assert summary.notified == 1
    assert jd_path.exists() is True
    content = jd_path.read_text(encoding="utf-8")
    assert "hiringcafe-901" in content
    assert "Backend Engineer" in content


def test_run_once_fails_fast_when_strict_auth_state_is_unusable(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "jobpipe.db"
    cv_path = tmp_path / "Master_CV.md"
    lock_path = tmp_path / "runtime" / "aggregator.lock"

    cv_path.write_text("Python backend engineer", encoding="utf-8")

    monkeypatch.setenv("JOBPIPE_DB_PATH", str(db_path))
    monkeypatch.setenv("JOBPIPE_MASTER_CV_PATH", str(cv_path))
    monkeypatch.setenv("JOBPIPE_RUN_LOCK_PATH", str(lock_path))
    monkeypatch.setenv("JOBPIPE_REQUIRE_USABLE_AUTH_STATE", "true")

    settings = Settings.from_env()

    monkeypatch.setattr(
        "jobpipe.pipeline._build_scrapers",
        lambda cfg: [("hiringcafe", _FailingStrictAuthScraper())],
    )

    with pytest.raises(UnusableStorageStateError):
        asyncio.run(run_once(settings, max_pages=1))

    repo = JobRepository(db_path)
    runs = repo.list_recent_runs(limit=1)
    assert len(runs) == 1
    assert runs[0].status == "Failed"
    assert runs[0].error_message is not None
    assert "strict auth-state unavailable" in runs[0].error_message

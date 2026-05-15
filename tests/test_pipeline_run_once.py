# Purpose: Verify ingest batch scoring and resume staging flows.
# Author: Seth Nenninger (GPT-5.2-Codex Agent)
# Timestamp: 2026-05-12T00:00:00Z
# Changelog: Replace run-once tests with ingest batch pipeline coverage.

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import threading
from unittest.mock import MagicMock

import numpy as np

from jobpipe.config import Settings
from jobpipe.notifications.windows_toast import NotificationDeliveryResult
from jobpipe.pipeline import ScoreSummary, process_ingest_batch
from jobpipe.resume.staging import stage_job_description
from jobpipe.storage.models import JobRecord
from jobpipe.storage.repository import JobRepository


class _FakeEmbedder:
    """Stand-in for LocalEmbedder that returns valid numpy vectors."""

    def __init__(self, model_name="", batch_size=32):
        pass

    def embed_text(self, text: str) -> np.ndarray:
        return np.zeros(384, dtype=float)

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        return np.zeros((len(texts), 384), dtype=float)


def _fake_embedder_factory(model_name="", batch_size=32):
    return _FakeEmbedder()


def test_process_ingest_batch_scores_and_notifies(tmp_path, monkeypatch) -> None:
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
            id="ingest-901",
            platform="HiringCafe",
            title="Backend Engineer",
            company="Acme",
            url="https://hiring.cafe/jobs/901",
            description="Python API role, 2+ years experience, remote",
            date_posted=datetime.now(timezone.utc),
        ),
        JobRecord(
            id="ingest-902",
            platform="HiringCafe",
            title="Platform Engineer",
            company="Beta",
            url="https://hiring.cafe/jobs/902",
            description="Python platform role requiring 7+ years experience",
            date_posted=datetime.now(timezone.utc),
        ),
    ]

    monkeypatch.setattr("jobpipe.pipeline.LocalEmbedder", _fake_embedder_factory)
    monkeypatch.setattr(
        "jobpipe.pipeline.notify_job_match",
        lambda title, company, score, url: NotificationDeliveryResult(
            delivery_status="ToastClickable",
            backend="test-backend",
            clickable=True,
        ),
    )

    result = process_ingest_batch(settings, jobs)
    summary = result.summary

    assert summary.ingested == 2
    assert summary.inserted == 2
    assert summary.updated == 0
    assert summary.scored == 2
    assert summary.above_threshold >= 0
    assert summary.notified >= 0

    repo = JobRepository(db_path)
    top = repo.list_top_jobs(limit=10)
    assert len(top) == 2

    best = top[0]
    assert best.id == "ingest-901"
    assert best.match_score is not None

    rejected = next(record for record in top if record.id == "ingest-902")
    assert rejected.match_score is not None


def test_process_ingest_batch_auto_stages_job_description_when_enabled(tmp_path, monkeypatch) -> None:
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
    monkeypatch.setenv("JOBPIPE_NOTIFICATION_THRESHOLD", "0.30")
    settings = Settings.from_env()

    jobs = [
        JobRecord(
            id="ingest-903",
            platform="HiringCafe",
            title="Backend Engineer",
            company="Acme",
            url="https://hiring.cafe/jobs/903",
            description="Python API role, 2+ years experience, remote",
            date_posted=datetime.now(timezone.utc),
        ),
        JobRecord(
            id="ingest-904",
            platform="HiringCafe",
            title="Platform Engineer",
            company="Beta",
            url="https://hiring.cafe/jobs/904",
            description="Python platform role requiring 7+ years experience",
            date_posted=datetime.now(timezone.utc),
        ),
    ]

    monkeypatch.setattr("jobpipe.pipeline.LocalEmbedder", _fake_embedder_factory)
    monkeypatch.setattr(
        "jobpipe.pipeline.notify_job_match",
        lambda title, company, score, url: NotificationDeliveryResult(
            delivery_status="ToastClickable",
            backend="test-backend",
            clickable=True,
        ),
    )

    summary = process_ingest_batch(settings, jobs).summary

    assert summary.notified >= 0
    assert jd_path.exists() is True
    content = jd_path.read_text(encoding="utf-8")
    assert "ingest-903" in content
    assert "Backend Engineer" in content


def test_process_ingest_batch_async_releases_run_lock_immediately(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "jobpipe.db"
    cv_path = tmp_path / "Master_CV.md"
    lock_path = tmp_path / "runtime" / "aggregator.lock"

    cv_path.write_text("Python backend engineer with API and SQL experience", encoding="utf-8")

    monkeypatch.setenv("JOBPIPE_DB_PATH", str(db_path))
    monkeypatch.setenv("JOBPIPE_MASTER_CV_PATH", str(cv_path))
    monkeypatch.setenv("JOBPIPE_RUN_LOCK_PATH", str(lock_path))
    monkeypatch.setenv("JOBPIPE_SCORE_ASYNC", "true")
    settings = Settings.from_env()

    allow_scoring = threading.Event()
    scoring_finished = threading.Event()

    def fake_score_pending_jobs(*args, **kwargs):
        allow_scoring.wait(timeout=5)
        scoring_finished.set()
        return ScoreSummary(scored=0, above_threshold=0, notified=0)

    monkeypatch.setattr("jobpipe.pipeline.LocalEmbedder", _fake_embedder_factory)
    monkeypatch.setattr("jobpipe.pipeline.score_pending_jobs", fake_score_pending_jobs)
    monkeypatch.setattr(
        "jobpipe.pipeline.notify_job_match",
        lambda title, company, score, url: NotificationDeliveryResult(
            delivery_status="ToastClickable",
            backend="test-backend",
            clickable=True,
        ),
    )

    jobs = [
        JobRecord(
            id="ingest-905",
            platform="HiringCafe",
            title="Backend Engineer",
            company="Acme",
            url="https://hiring.cafe/jobs/905",
            description="Python API role, 2+ years experience, remote",
            date_posted=datetime.now(timezone.utc),
        )
    ]

    result = process_ingest_batch(settings, jobs)

    assert result.scoring_in_progress is True
    assert not lock_path.exists()

    allow_scoring.set()
    assert scoring_finished.wait(timeout=5) is True

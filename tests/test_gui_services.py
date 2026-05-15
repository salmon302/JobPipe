# Purpose: Validate GUI service helpers for ingest and resume flows.
# Author: Seth Nenninger (GPT-5.2-Codex Agent)
# Timestamp: 2026-05-12T00:00:00Z
# Changelog: Remove scheduler tests and add ingest settings coverage.

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from jobpipe.config import InvalidSettingsError, Settings
from jobpipe.storage.db import initialize_database
from jobpipe.gui.services import JobPipeGuiService
from jobpipe.storage.models import JobRecord
from jobpipe.storage.repository import JobRepository


def _settings(tmp_path, monkeypatch) -> Settings:
    monkeypatch.setenv("JOBPIPE_DB_PATH", str(tmp_path / "jobpipe.db"))
    monkeypatch.setenv("JOBPIPE_MASTER_CV_PATH", str(tmp_path / "Master_CV.md"))
    monkeypatch.setenv("JOBPIPE_JOB_DESCRIPTION_PATH", str(tmp_path / "Job_Description.md"))
    monkeypatch.setenv("JOBPIPE_RESUME_OUTPUT_DIR", str(tmp_path / "resume"))
    monkeypatch.setenv("JOBPIPE_RUN_LOCK_PATH", str(tmp_path / "aggregator.lock"))
    monkeypatch.setenv("JOBPIPE_INGEST_HOST", "127.0.0.1")
    monkeypatch.setenv("JOBPIPE_INGEST_PORT", "3838")
    monkeypatch.setenv("JOBPIPE_INGEST_MAX_PAYLOAD_BYTES", "1000000")
    return Settings.from_env()


def test_ingest_endpoint_uses_settings(monkeypatch, tmp_path) -> None:
    service = JobPipeGuiService(_settings(tmp_path, monkeypatch))

    assert service.ingest_endpoint() == "http://127.0.0.1:3838"


def test_load_editable_env_values_prefers_env_file(monkeypatch, tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "JOBPIPE_NOTIFICATION_THRESHOLD=0.92",
                "JOBPIPE_INGEST_HOST=0.0.0.0",
                "JOBPIPE_CRITICAL_SKILLS=python,sql,aws",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    service = JobPipeGuiService(_settings(tmp_path, monkeypatch))
    monkeypatch.setattr(service, "_project_root", lambda: tmp_path)

    values = service.load_editable_env_values()

    assert values["JOBPIPE_NOTIFICATION_THRESHOLD"] == "0.92"
    assert values["JOBPIPE_INGEST_HOST"] == "0.0.0.0"
    assert values["JOBPIPE_CRITICAL_SKILLS"] == "python,sql,aws"


def test_validate_editable_env_values_rejects_invalid_threshold(monkeypatch, tmp_path) -> None:
    service = JobPipeGuiService(_settings(tmp_path, monkeypatch))
    values = service.load_editable_env_values()
    values["JOBPIPE_NOTIFICATION_THRESHOLD"] = "1.7"

    with pytest.raises(InvalidSettingsError):
        service.validate_editable_env_values(values)


def test_save_editable_env_values_persists_and_updates_runtime(monkeypatch, tmp_path) -> None:
    service = JobPipeGuiService(_settings(tmp_path, monkeypatch))
    monkeypatch.setattr(service, "_project_root", lambda: tmp_path)

    values = service.load_editable_env_values()
    values["JOBPIPE_NOTIFICATION_THRESHOLD"] = "0.77"
    values["JOBPIPE_INGEST_PORT"] = "3839"
    values["JOBPIPE_AUTO_STAGE_JOB_DESCRIPTION"] = "true"

    saved_path = service.save_editable_env_values(values)

    assert saved_path == tmp_path / ".env"
    content = saved_path.read_text(encoding="utf-8")
    assert "JOBPIPE_NOTIFICATION_THRESHOLD=0.77" in content
    assert "JOBPIPE_INGEST_PORT=3839" in content
    assert "JOBPIPE_AUTO_STAGE_JOB_DESCRIPTION=true" in content
    assert service.settings.notification_threshold == 0.77
    assert service.settings.ingest_port == 3839
    assert service.settings.auto_stage_job_description is True


def test_default_resume_tex_path_uses_configured_basename(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("JOBPIPE_RESUME_TARGET_BASENAME", "FocusedResume")
    service = JobPipeGuiService(_settings(tmp_path, monkeypatch))

    path = service.default_resume_tex_path()

    assert path.name == "FocusedResume.tex"


def test_stage_resume_target_delegates_to_staging_module(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}
    expected = SimpleNamespace(
        job_id="job-1",
        title="Backend Engineer",
        company="Acme",
        score=0.91,
        output_path=tmp_path / "Job_Description.md",
    )

    def _fake_stage_job_description(repository, output_path, minimum_score, job_id=None):
        captured["repository"] = repository
        captured["output_path"] = output_path
        captured["minimum_score"] = minimum_score
        captured["job_id"] = job_id
        return expected

    monkeypatch.setattr("jobpipe.gui.services.stage_job_description", _fake_stage_job_description)

    service = JobPipeGuiService(_settings(tmp_path, monkeypatch))
    result = service.stage_resume_target(minimum_score=0.88, job_id="job-1")

    assert result is expected
    assert captured["output_path"] == service.settings.job_description_path
    assert captured["minimum_score"] == 0.88
    assert captured["job_id"] == "job-1"


def test_compile_resume_delegates_with_config(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}
    expected = SimpleNamespace(
        tex_path=tmp_path / "resume" / "FocusedResume.tex",
        pdf_path=tmp_path / "resume" / "FocusedResume.pdf",
        attempts=1,
    )

    def _fake_compile_latex(tex_path, output_pdf_path=None, config=None):
        captured["tex_path"] = tex_path
        captured["output_pdf_path"] = output_pdf_path
        captured["config"] = config
        return expected

    monkeypatch.setenv("JOBPIPE_RESUME_TARGET_BASENAME", "FocusedResume")
    monkeypatch.setattr("jobpipe.gui.services.compile_latex", _fake_compile_latex)

    service = JobPipeGuiService(_settings(tmp_path, monkeypatch))
    result = service.compile_resume()

    assert result is expected
    assert captured["tex_path"].name == "FocusedResume.tex"
    assert captured["output_pdf_path"].name == "FocusedResume.pdf"
    assert captured["config"].pdflatex_command == service.settings.resume_pdflatex_command


def test_generate_ai_recommendations_success(monkeypatch, tmp_path) -> None:
    """Test successful AI recommendation generation."""
    # Create a fake Master CV
    master_cv_path = tmp_path / "Master_CV.md"
    master_cv_path.write_text("# John Doe\n## Skills\nPython, SQL\n## Experience\n3 years", encoding="utf-8")
    
    monkeypatch.setenv("JOBPIPE_MASTER_CV_PATH", str(master_cv_path))
    monkeypatch.setenv("JOBPIPE_GEMINI_API_KEY", "fake-api-key")
    monkeypatch.setenv("JOBPIPE_GEMINI_MODEL", "gemini-flash-latest")
    
    # Create fake top jobs
    from jobpipe.storage.models import JobRecord
    from datetime import datetime, timezone
    
    top_jobs = [
        JobRecord(
            id="job-1",
            platform="HiringCafe",
            title="Python Developer",
            company="Tech Corp",
            url="https://example.com/job1",
            description="Looking for Python developer with SQL skills",
            match_score=0.95,
            score_relevance=0.90,
            score_attainability=0.95,
            date_posted=datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc),
        ),
        JobRecord(
            id="job-2",
            platform="HiringCafe",
            title="Backend Engineer",
            company="Data Inc",
            url="https://example.com/job2",
            description="Backend work with Python and databases",
            match_score=0.88,
            score_relevance=0.85,
            score_attainability=0.90,
            date_posted=datetime(2026, 5, 11, 12, 0, tzinfo=timezone.utc),
        ),
    ]
    
    # Mock the Gemini client - need to mock where it's imported in the method
    def _fake_create_gemini_client(settings):
        class FakeClient:
            def generate_text(self, prompt, temperature=0.3, max_output_tokens=1024):
                return "1. Apply to Python Developer at Tech Corp first (score 0.95)\n2. Consider Backend Engineer at Data Inc (score 0.88)"
        return FakeClient()
    
    monkeypatch.setattr("jobpipe.resume.gemini_client.create_gemini_client_from_settings", _fake_create_gemini_client)
    
    service = JobPipeGuiService(_settings(tmp_path, monkeypatch))
    result = service.generate_ai_recommendations(top_jobs)
    
    assert "Python Developer" in result
    assert "Tech Corp" in result
    assert "Backend Engineer" in result


def test_generate_ai_recommendations_no_api_key(monkeypatch, tmp_path) -> None:
    """Test that missing API key raises RuntimeError."""
    # Create a fake Master CV so it passes that check
    master_cv_path = tmp_path / "Master_CV.md"
    master_cv_path.write_text("# John Doe\n## Skills\nPython", encoding="utf-8")
    
    monkeypatch.setenv("JOBPIPE_MASTER_CV_PATH", str(master_cv_path))
    monkeypatch.setenv("JOBPIPE_GEMINI_API_KEY", "")  # Empty API key
    
    service = JobPipeGuiService(_settings(tmp_path, monkeypatch))
    top_jobs = []  # Empty list, should fail at API key check
    
    with pytest.raises(RuntimeError, match="Gemini API key not configured"):
        service.generate_ai_recommendations(top_jobs)


def test_generate_ai_recommendations_missing_cv(monkeypatch, tmp_path) -> None:
    """Test that missing Master CV raises RuntimeError."""
    monkeypatch.setenv("JOBPIPE_GEMINI_API_KEY", "fake-key")
    monkeypatch.setenv("JOBPIPE_MASTER_CV_PATH", str(tmp_path / "non_existent.md"))
    
    service = JobPipeGuiService(_settings(tmp_path, monkeypatch))
    top_jobs = []
    
    with pytest.raises(RuntimeError, match="Master CV not found"):
        service.generate_ai_recommendations(top_jobs)


def test_list_jobs_searches_and_returns_unscored_rows(monkeypatch, tmp_path) -> None:
    service = JobPipeGuiService(_settings(tmp_path, monkeypatch))
    initialize_database(service.settings.db_path)
    repo = JobRepository(service.settings.db_path)

    scored = JobRecord(
        id="job-scored",
        platform="HiringCafe",
        title="Senior Python Engineer",
        company="Acme",
        url="https://example.com/scored",
        description="Build APIs with Python and SQL",
        date_posted=datetime(2026, 4, 10, 12, 0, tzinfo=timezone.utc),
    )
    unscored = JobRecord(
        id="job-unscored",
        platform="HiringCafe",
        title="Data Platform Engineer",
        company="Beta Labs",
        url="https://example.com/unscored",
        description="Python data pipelines and warehouse work",
        date_posted=datetime(2026, 4, 11, 12, 0, tzinfo=timezone.utc),
    )

    repo.upsert_jobs([scored, unscored])
    repo.update_scoring(
        job_id=scored.id,
        match_score=0.95,
        years_required=3,
        is_remote=True,
        status="Queued",
    )

    results = service.list_jobs(limit=10, search_query="python")

    assert [job.id for job in results] == ["job-scored", "job-unscored"]
    assert service.get_job_by_id("job-unscored").title == "Data Platform Engineer"

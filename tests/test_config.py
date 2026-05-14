# Purpose: Validate Settings defaults and runtime validation for ingest workflow.
# Author: Seth Nenninger (GPT-5.2-Codex Agent)
# Timestamp: 2026-05-12T00:00:00Z
# Changelog: Replace scraper configuration tests with ingest settings coverage.

from pathlib import Path

import pytest

from jobpipe.config import InvalidSettingsError, Settings


def test_space_delimited_reject_terms_are_supported(monkeypatch) -> None:
    monkeypatch.setenv("JOBPIPE_REJECT_TERMS", "senior staff principal")

    settings = Settings.from_env()

    assert settings.reject_terms == ["senior", "staff", "principal"]


def test_resume_settings_defaults(monkeypatch) -> None:
    monkeypatch.delenv("JOBPIPE_JOB_DESCRIPTION_PATH", raising=False)
    monkeypatch.delenv("JOBPIPE_RESUME_OUTPUT_DIR", raising=False)
    monkeypatch.delenv("JOBPIPE_RESUME_TARGET_BASENAME", raising=False)

    settings = Settings.from_env()

    assert settings.job_description_path == Path("Job_Description.md")
    assert settings.resume_output_dir == Path("data/resume")
    assert settings.resume_target_basename == "Targeted_Resume"


def test_ingest_settings_defaults(monkeypatch) -> None:
    monkeypatch.delenv("JOBPIPE_INGEST_HOST", raising=False)
    monkeypatch.delenv("JOBPIPE_INGEST_PORT", raising=False)
    monkeypatch.delenv("JOBPIPE_INGEST_MAX_PAYLOAD_BYTES", raising=False)

    settings = Settings.from_env()

    assert settings.ingest_host == "127.0.0.1"
    assert settings.ingest_port == 3838
    assert settings.ingest_max_payload_bytes == 1_000_000


def test_validate_runtime_rejects_invalid_threshold(monkeypatch) -> None:
    monkeypatch.setenv("JOBPIPE_NOTIFICATION_THRESHOLD", "1.5")

    settings = Settings.from_env()

    with pytest.raises(InvalidSettingsError):
        settings.validate_runtime()


def test_validate_runtime_rejects_invalid_port(monkeypatch) -> None:
    monkeypatch.setenv("JOBPIPE_INGEST_PORT", "70000")

    settings = Settings.from_env()

    with pytest.raises(InvalidSettingsError):
        settings.validate_runtime()

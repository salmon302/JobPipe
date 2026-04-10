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


def test_platform_settings_defaults(monkeypatch) -> None:
    monkeypatch.delenv("JOBPIPE_WELLFOUND_ENABLED", raising=False)
    monkeypatch.delenv("JOBPIPE_BUILTIN_ENABLED", raising=False)
    monkeypatch.delenv("JOBPIPE_AUTO_STAGE_JOB_DESCRIPTION", raising=False)
    monkeypatch.delenv("JOBPIPE_WELLFOUND_HEADLESS", raising=False)
    monkeypatch.delenv("JOBPIPE_WELLFOUND_JITTER_MIN", raising=False)
    monkeypatch.delenv("JOBPIPE_WELLFOUND_JITTER_MAX", raising=False)
    monkeypatch.delenv("JOBPIPE_WELLFOUND_FETCH_DETAILS", raising=False)
    monkeypatch.delenv("JOBPIPE_BUILTIN_HEADLESS", raising=False)
    monkeypatch.delenv("JOBPIPE_BUILTIN_JITTER_MIN", raising=False)
    monkeypatch.delenv("JOBPIPE_BUILTIN_JITTER_MAX", raising=False)
    monkeypatch.delenv("JOBPIPE_BUILTIN_FETCH_DETAILS", raising=False)
    monkeypatch.delenv("JOBPIPE_USER_AGENTS", raising=False)
    monkeypatch.delenv("JOBPIPE_HIRINGCAFE_USER_AGENTS", raising=False)
    monkeypatch.delenv("JOBPIPE_WELLFOUND_USER_AGENTS", raising=False)
    monkeypatch.delenv("JOBPIPE_BUILTIN_USER_AGENTS", raising=False)
    monkeypatch.delenv("JOBPIPE_REQUIRE_USABLE_AUTH_STATE", raising=False)

    settings = Settings.from_env()

    assert settings.wellfound_enabled is False
    assert settings.builtin_enabled is False
    assert settings.wellfound_headless is True
    assert settings.wellfound_jitter_min == 1.5
    assert settings.wellfound_jitter_max == 3.5
    assert settings.wellfound_fetch_detail_descriptions is True
    assert settings.builtin_headless is True
    assert settings.builtin_jitter_min == 1.5
    assert settings.builtin_jitter_max == 3.5
    assert settings.builtin_fetch_detail_descriptions is True
    assert settings.auto_stage_job_description is False
    assert settings.require_usable_auth_state is False
    assert len(settings.user_agents) == 2
    assert settings.platform_user_agents("hiringcafe") == settings.user_agents
    assert settings.platform_user_agents("wellfound") == settings.user_agents
    assert settings.platform_user_agents("builtin") == settings.user_agents
    assert settings.platform_base_url("hiringcafe") == settings.hiringcafe_base_url
    assert settings.platform_base_url("wellfound") == settings.wellfound_base_url
    assert settings.platform_base_url("builtin") == settings.builtin_base_url
    assert settings.platform_storage_state("wellfound") == settings.wellfound_storage_state


def test_platform_runtime_overrides(monkeypatch) -> None:
    monkeypatch.setenv("JOBPIPE_WELLFOUND_HEADLESS", "false")
    monkeypatch.setenv("JOBPIPE_WELLFOUND_JITTER_MIN", "0.2")
    monkeypatch.setenv("JOBPIPE_WELLFOUND_JITTER_MAX", "0.6")
    monkeypatch.setenv("JOBPIPE_WELLFOUND_FETCH_DETAILS", "false")
    monkeypatch.setenv("JOBPIPE_BUILTIN_HEADLESS", "false")
    monkeypatch.setenv("JOBPIPE_BUILTIN_JITTER_MIN", "0.3")
    monkeypatch.setenv("JOBPIPE_BUILTIN_JITTER_MAX", "0.7")
    monkeypatch.setenv("JOBPIPE_BUILTIN_FETCH_DETAILS", "false")
    monkeypatch.setenv("JOBPIPE_USER_AGENTS", "Global Agent 1||Global Agent 2")
    monkeypatch.setenv("JOBPIPE_WELLFOUND_USER_AGENTS", "Wellfound Agent 1||Wellfound Agent 2")
    monkeypatch.setenv("JOBPIPE_BUILTIN_USER_AGENTS", "BuiltIn Agent 1")
    monkeypatch.setenv("JOBPIPE_REQUIRE_USABLE_AUTH_STATE", "true")

    settings = Settings.from_env()

    assert settings.wellfound_headless is False
    assert settings.wellfound_jitter_min == 0.2
    assert settings.wellfound_jitter_max == 0.6
    assert settings.wellfound_fetch_detail_descriptions is False
    assert settings.builtin_headless is False
    assert settings.builtin_jitter_min == 0.3
    assert settings.builtin_jitter_max == 0.7
    assert settings.builtin_fetch_detail_descriptions is False
    assert settings.require_usable_auth_state is True
    assert settings.user_agents == ["Global Agent 1", "Global Agent 2"]
    assert settings.platform_user_agents("hiringcafe") == ["Global Agent 1", "Global Agent 2"]
    assert settings.platform_user_agents("wellfound") == [
        "Wellfound Agent 1",
        "Wellfound Agent 2",
    ]
    assert settings.platform_user_agents("builtin") == ["BuiltIn Agent 1"]


def test_validate_scraping_runtime_rejects_invalid_threshold(monkeypatch) -> None:
    monkeypatch.setenv("JOBPIPE_NOTIFICATION_THRESHOLD", "1.5")

    settings = Settings.from_env()

    with pytest.raises(InvalidSettingsError):
        settings.validate_scraping_runtime()


def test_validate_scraping_runtime_rejects_invalid_jitter_range(monkeypatch) -> None:
    monkeypatch.setenv("JOBPIPE_WELLFOUND_ENABLED", "true")
    monkeypatch.setenv("JOBPIPE_WELLFOUND_JITTER_MIN", "2.0")
    monkeypatch.setenv("JOBPIPE_WELLFOUND_JITTER_MAX", "1.0")

    settings = Settings.from_env()

    with pytest.raises(InvalidSettingsError):
        settings.validate_scraping_runtime()

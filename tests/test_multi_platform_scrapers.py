from pathlib import Path

from jobpipe.config import Settings
from jobpipe.pipeline import _build_scrapers
from jobpipe.scrapers.builtin import BuiltInScraper, BuiltInScraperConfig
from jobpipe.scrapers.wellfound import WellfoundScraper, WellfoundScraperConfig


def test_wellfound_job_id_generation() -> None:
    scraper = WellfoundScraper(
        WellfoundScraperConfig(
            base_url="https://wellfound.com",
            storage_state=Path("state.json"),
            headless=True,
            jitter_min=0.0,
            jitter_max=0.0,
            fetch_detail_descriptions=False,
        )
    )

    assert scraper._build_job_id(node_id="123", url="https://wellfound.com/jobs/123") == "wellfound-123"
    generated = scraper._build_job_id(node_id=None, url="https://wellfound.com/jobs/abc")
    assert generated.startswith("wellfound-")
    assert generated != "wellfound-123"


def test_builtin_job_id_generation() -> None:
    scraper = BuiltInScraper(
        BuiltInScraperConfig(
            base_url="https://builtin.com",
            storage_state=Path("state.json"),
            headless=True,
            jitter_min=0.0,
            jitter_max=0.0,
            fetch_detail_descriptions=False,
        )
    )

    assert scraper._build_job_id(node_id="123", url="https://builtin.com/jobs/123") == "builtin-123"
    generated = scraper._build_job_id(node_id=None, url="https://builtin.com/jobs/abc")
    assert generated.startswith("builtin-")
    assert generated != "builtin-123"


def test_build_scrapers_uses_platform_specific_runtime_settings(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("JOBPIPE_WELLFOUND_ENABLED", "true")
    monkeypatch.setenv("JOBPIPE_BUILTIN_ENABLED", "true")
    monkeypatch.setenv("JOBPIPE_WELLFOUND_HEADLESS", "false")
    monkeypatch.setenv("JOBPIPE_WELLFOUND_JITTER_MIN", "0.2")
    monkeypatch.setenv("JOBPIPE_WELLFOUND_JITTER_MAX", "0.6")
    monkeypatch.setenv("JOBPIPE_WELLFOUND_FETCH_DETAILS", "false")
    monkeypatch.setenv("JOBPIPE_WELLFOUND_STORAGE_STATE", str(tmp_path / "wellfound.json"))
    monkeypatch.setenv("JOBPIPE_BUILTIN_HEADLESS", "false")
    monkeypatch.setenv("JOBPIPE_BUILTIN_JITTER_MIN", "0.3")
    monkeypatch.setenv("JOBPIPE_BUILTIN_JITTER_MAX", "0.7")
    monkeypatch.setenv("JOBPIPE_BUILTIN_FETCH_DETAILS", "false")
    monkeypatch.setenv("JOBPIPE_BUILTIN_STORAGE_STATE", str(tmp_path / "builtin.json"))
    monkeypatch.setenv("JOBPIPE_USER_AGENTS", "Global Agent 1||Global Agent 2")
    monkeypatch.setenv("JOBPIPE_WELLFOUND_USER_AGENTS", "Wellfound Agent 1||Wellfound Agent 2")
    monkeypatch.setenv("JOBPIPE_BUILTIN_USER_AGENTS", "BuiltIn Agent 1")
    monkeypatch.setenv("JOBPIPE_REQUIRE_USABLE_AUTH_STATE", "true")

    settings = Settings.from_env()
    scraper_map = dict(_build_scrapers(settings))

    hiringcafe = scraper_map["hiringcafe"]
    wellfound = scraper_map["wellfound"]
    builtin = scraper_map["builtin"]

    assert hiringcafe._config.user_agents == ("Global Agent 1", "Global Agent 2")

    assert wellfound._config.headless is False
    assert wellfound._config.jitter_min == 0.2
    assert wellfound._config.jitter_max == 0.6
    assert wellfound._config.fetch_detail_descriptions is False
    assert wellfound._config.user_agents == ("Wellfound Agent 1", "Wellfound Agent 2")
    assert wellfound._config.require_usable_auth_state is True

    assert builtin._config.headless is False
    assert builtin._config.jitter_min == 0.3
    assert builtin._config.jitter_max == 0.7
    assert builtin._config.fetch_detail_descriptions is False
    assert builtin._config.user_agents == ("BuiltIn Agent 1",)
    assert builtin._config.require_usable_auth_state is True

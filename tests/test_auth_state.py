from __future__ import annotations

from datetime import datetime, timezone
import json

from jobpipe.scrapers.auth_state import (
    evaluate_platform_storage_state,
    evaluate_storage_state,
    expected_cookie_domains,
)


NOW_UTC = datetime(2026, 4, 9, tzinfo=timezone.utc)


def test_evaluate_storage_state_missing_file(tmp_path) -> None:
    storage_state = tmp_path / "missing.json"

    status = evaluate_storage_state(storage_state, now_utc=NOW_UTC)

    assert status.exists is False
    assert status.valid_json is False
    assert status.usable is False
    assert any("does not exist" in issue for issue in status.errors)


def test_evaluate_storage_state_invalid_json(tmp_path) -> None:
    storage_state = tmp_path / "state.json"
    storage_state.write_text("{invalid json", encoding="utf-8")

    status = evaluate_storage_state(storage_state, now_utc=NOW_UTC)

    assert status.exists is True
    assert status.valid_json is False
    assert status.usable is False
    assert any("failed to read storage state JSON" in issue for issue in status.errors)


def test_evaluate_storage_state_unusable_when_all_cookies_expired(tmp_path) -> None:
    storage_state = tmp_path / "state.json"
    payload = {
        "cookies": [
            {
                "name": "hf_session",
                "value": "abc",
                "domain": "hiring.cafe",
                "expires": NOW_UTC.timestamp() - 3600,
            }
        ]
    }
    storage_state.write_text(json.dumps(payload), encoding="utf-8")

    status = evaluate_storage_state(storage_state, now_utc=NOW_UTC)

    assert status.valid_json is True
    assert status.cookie_count == 1
    assert status.unexpired_cookie_count == 0
    assert status.session_cookie_count == 0
    assert status.usable is False
    assert any("appear expired" in issue for issue in status.errors)


def test_evaluate_storage_state_usable_with_unexpired_cookie(tmp_path) -> None:
    storage_state = tmp_path / "state.json"
    payload = {
        "cookies": [
            {
                "name": "hf_session",
                "value": "abc",
                "domain": "hiring.cafe",
                "expires": NOW_UTC.timestamp() + 3600,
            }
        ]
    }
    storage_state.write_text(json.dumps(payload), encoding="utf-8")

    status = evaluate_storage_state(storage_state, now_utc=NOW_UTC)

    assert status.cookie_count == 1
    assert status.unexpired_cookie_count == 1
    assert status.session_cookie_count == 0
    assert status.usable is True
    assert status.errors == ()


def test_evaluate_storage_state_usable_with_session_cookie(tmp_path) -> None:
    storage_state = tmp_path / "state.json"
    payload = {
        "cookies": [
            {
                "name": "hf_session",
                "value": "abc",
                "domain": "hiring.cafe",
                "expires": -1,
            }
        ]
    }
    storage_state.write_text(json.dumps(payload), encoding="utf-8")

    status = evaluate_storage_state(storage_state, now_utc=NOW_UTC)

    assert status.cookie_count == 1
    assert status.unexpired_cookie_count == 0
    assert status.session_cookie_count == 1
    assert status.usable is True


def test_expected_cookie_domains_normalizes_www_hostnames() -> None:
    assert expected_cookie_domains("https://www.wellfound.com/jobs") == (
        "www.wellfound.com",
        "wellfound.com",
    )


def test_expected_cookie_domains_accepts_scheme_less_values() -> None:
    assert expected_cookie_domains("hiring.cafe") == ("hiring.cafe",)


def test_evaluate_storage_state_rejects_cookies_for_unexpected_domains(tmp_path) -> None:
    storage_state = tmp_path / "state.json"
    payload = {
        "cookies": [
            {
                "name": "session",
                "value": "abc",
                "domain": "example.com",
                "expires": NOW_UTC.timestamp() + 3600,
            }
        ]
    }
    storage_state.write_text(json.dumps(payload), encoding="utf-8")

    status = evaluate_storage_state(
        storage_state,
        now_utc=NOW_UTC,
        expected_domains=("hiring.cafe",),
    )

    assert status.cookie_count == 1
    assert status.usable is False
    assert any("matched expected domains" in issue for issue in status.errors)


def test_evaluate_storage_state_accepts_matching_subdomains(tmp_path) -> None:
    storage_state = tmp_path / "state.json"
    payload = {
        "cookies": [
            {
                "name": "session",
                "value": "abc",
                "domain": ".jobs.hiring.cafe",
                "expires": NOW_UTC.timestamp() + 3600,
            }
        ]
    }
    storage_state.write_text(json.dumps(payload), encoding="utf-8")

    status = evaluate_storage_state(
        storage_state,
        now_utc=NOW_UTC,
        expected_domains=("hiring.cafe",),
    )

    assert status.cookie_count == 1
    assert status.unexpired_cookie_count == 1
    assert status.usable is True


def test_evaluate_platform_storage_state_uses_base_url_for_domain_filter(tmp_path) -> None:
    storage_state = tmp_path / "state.json"
    payload = {
        "cookies": [
            {
                "name": "session",
                "value": "abc",
                "domain": ".jobs.wellfound.com",
                "expires": NOW_UTC.timestamp() + 3600,
            }
        ]
    }
    storage_state.write_text(json.dumps(payload), encoding="utf-8")

    status = evaluate_platform_storage_state(
        storage_state=storage_state,
        base_url="https://wellfound.com/jobs",
        now_utc=NOW_UTC,
    )

    assert status.cookie_count == 1
    assert status.unexpired_cookie_count == 1
    assert status.usable is True

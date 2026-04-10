from __future__ import annotations

from pathlib import Path
import sys
import types

import pytest

from jobpipe.cli import main
from jobpipe.scrapers.auth_state import StorageStateStatus
from jobpipe.scrapers.auth_state import UnusableStorageStateError


def _storage_status(path: Path, usable: bool) -> StorageStateStatus:
    errors = () if usable else ("invalid session",)
    return StorageStateStatus(
        path=path,
        exists=True,
        valid_json=True,
        cookie_count=1,
        unexpired_cookie_count=1 if usable else 0,
        session_cookie_count=0,
        usable=usable,
        errors=errors,
    )


def test_main_with_explicit_empty_args_prints_help_and_returns_zero(capsys) -> None:
    exit_code = main([])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "usage: jobpipe" in captured.out.lower()


def test_main_with_no_sys_argv_args_prints_help_and_returns_zero(capsys, monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["jobpipe"])

    exit_code = main(None)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "usage: jobpipe" in captured.out.lower()


def test_main_with_invalid_args_keeps_argparse_error_behavior() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--definitely-not-a-real-flag"])

    assert exc.value.code == 2


def test_auth_preflight_strict_mode_returns_error_for_unusable_state(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("JOBPIPE_REQUIRE_USABLE_AUTH_STATE", "true")
    monkeypatch.setenv("JOBPIPE_HIRINGCAFE_STORAGE_STATE", str(tmp_path / "hiringcafe.json"))
    monkeypatch.setattr(
        "jobpipe.cli.evaluate_storage_state",
        lambda storage_state, expected_domains=(): _storage_status(storage_state, usable=False),
    )

    exit_code = main(["auth-preflight", "--platform", "hiringcafe"])

    assert exit_code == 2


def test_auth_preflight_non_strict_mode_allows_unusable_state(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("JOBPIPE_REQUIRE_USABLE_AUTH_STATE", "false")
    monkeypatch.setenv("JOBPIPE_HIRINGCAFE_STORAGE_STATE", str(tmp_path / "hiringcafe.json"))
    monkeypatch.setattr(
        "jobpipe.cli.evaluate_storage_state",
        lambda storage_state, expected_domains=(): _storage_status(storage_state, usable=False),
    )

    exit_code = main(["auth-preflight", "--platform", "hiringcafe"])

    assert exit_code == 0


def test_auth_preflight_defaults_to_enabled_platforms(monkeypatch, tmp_path) -> None:
    hiringcafe_path = tmp_path / "hiringcafe.json"
    wellfound_path = tmp_path / "wellfound.json"
    builtin_path = tmp_path / "builtin.json"

    monkeypatch.setenv("JOBPIPE_WELLFOUND_ENABLED", "true")
    monkeypatch.setenv("JOBPIPE_BUILTIN_ENABLED", "false")
    monkeypatch.setenv("JOBPIPE_HIRINGCAFE_STORAGE_STATE", str(hiringcafe_path))
    monkeypatch.setenv("JOBPIPE_WELLFOUND_STORAGE_STATE", str(wellfound_path))
    monkeypatch.setenv("JOBPIPE_BUILTIN_STORAGE_STATE", str(builtin_path))

    checked_paths: list[Path] = []

    def _capture(storage_state: Path, expected_domains=()) -> StorageStateStatus:
        _ = expected_domains
        checked_paths.append(storage_state)
        return _storage_status(storage_state, usable=True)

    monkeypatch.setattr("jobpipe.cli.evaluate_storage_state", _capture)

    exit_code = main(["auth-preflight"])

    assert exit_code == 0
    assert checked_paths == [hiringcafe_path, wellfound_path]


def test_auth_preflight_include_disabled_checks_all_platforms(monkeypatch, tmp_path) -> None:
    hiringcafe_path = tmp_path / "hiringcafe.json"
    wellfound_path = tmp_path / "wellfound.json"
    builtin_path = tmp_path / "builtin.json"

    monkeypatch.setenv("JOBPIPE_WELLFOUND_ENABLED", "false")
    monkeypatch.setenv("JOBPIPE_BUILTIN_ENABLED", "false")
    monkeypatch.setenv("JOBPIPE_HIRINGCAFE_STORAGE_STATE", str(hiringcafe_path))
    monkeypatch.setenv("JOBPIPE_WELLFOUND_STORAGE_STATE", str(wellfound_path))
    monkeypatch.setenv("JOBPIPE_BUILTIN_STORAGE_STATE", str(builtin_path))

    checked_paths: list[Path] = []

    def _capture(storage_state: Path, expected_domains=()) -> StorageStateStatus:
        _ = expected_domains
        checked_paths.append(storage_state)
        return _storage_status(storage_state, usable=True)

    monkeypatch.setattr("jobpipe.cli.evaluate_storage_state", _capture)

    exit_code = main(["auth-preflight", "--include-disabled"])

    assert exit_code == 0
    assert checked_paths == [hiringcafe_path, wellfound_path, builtin_path]


def test_run_once_returns_error_for_strict_auth_state_failure(monkeypatch) -> None:
    async def _raise_auth_error(*_args, **_kwargs):
        raise UnusableStorageStateError("strict auth failed")

    monkeypatch.setattr("jobpipe.cli.run_once", _raise_auth_error)

    exit_code = main(["run-once"])

    assert exit_code == 2


def test_run_once_returns_error_for_invalid_runtime_settings(monkeypatch) -> None:
    monkeypatch.setenv("JOBPIPE_NOTIFICATION_THRESHOLD", "1.2")

    async def _should_not_run(*_args, **_kwargs):
        raise AssertionError("run_once should not execute when settings are invalid")

    monkeypatch.setattr("jobpipe.cli.run_once", _should_not_run)

    exit_code = main(["run-once"])

    assert exit_code == 2


def test_gui_command_delegates_to_gui_launcher(monkeypatch) -> None:
    launch_calls: list[int] = []

    def _fake_launch_gui(settings, default_max_pages):
        assert settings.db_path
        launch_calls.append(default_max_pages)
        return 0

    fake_module = types.SimpleNamespace(launch_gui=_fake_launch_gui)
    monkeypatch.setitem(sys.modules, "jobpipe.gui.app", fake_module)

    exit_code = main(["gui", "--max-pages", "3"])

    assert exit_code == 0
    assert launch_calls == [3]

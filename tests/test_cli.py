# Purpose: Verify CLI command routing for ingest-focused workflow.
# Author: Seth Nenninger (GPT-5.2-Codex Agent)
# Timestamp: 2026-05-12T00:00:00Z
# Changelog: Remove auth/scheduler tests and cover ingest-server command.

from __future__ import annotations

import sys
import types

from jobpipe.cli import main


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
    try:
        main(["--definitely-not-a-real-flag"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("Expected SystemExit for invalid arguments")


def test_ingest_server_command_delegates(monkeypatch) -> None:
    calls: list[tuple[str | None, int | None]] = []

    def _fake_run_ingest_server(settings, host=None, port=None):
        assert settings.db_path
        calls.append((host, port))

    monkeypatch.setattr("jobpipe.cli.run_ingest_server", _fake_run_ingest_server)

    exit_code = main(["ingest-server", "--host", "127.0.0.1", "--port", "3839"])

    assert exit_code == 0
    assert calls == [("127.0.0.1", 3839)]


def test_gui_command_delegates_to_gui_launcher(monkeypatch) -> None:
    launch_calls: list[bool] = []

    def _fake_launch_gui(settings):
        assert settings.db_path
        launch_calls.append(True)
        return 0

    fake_module = types.SimpleNamespace(launch_gui=_fake_launch_gui)
    monkeypatch.setitem(sys.modules, "jobpipe.gui.app", fake_module)

    exit_code = main(["gui"])

    assert exit_code == 0
    assert launch_calls == [True]

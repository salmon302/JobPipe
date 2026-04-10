from pathlib import Path

from jobpipe.scheduler.windows_task import (
    build_hourly_task_command,
    build_task_delete_command,
    build_task_run_command,
    build_task_run_now_command,
    build_task_status_command,
)


def test_build_task_run_command_contains_required_segments() -> None:
    command = build_task_run_command(
        python_executable=Path("C:/repo/.venv/Scripts/python.exe"),
        project_root=Path("C:/repo"),
        env_file=Path("C:/repo/.env"),
        max_pages=2,
    )

    assert "cd /d" in command
    assert "PYTHONPATH=src" in command
    assert "-m jobpipe" in command
    assert "--env-file" in command
    assert "--max-pages 2" in command


def test_build_hourly_task_command_includes_schedule_fields() -> None:
    command = build_hourly_task_command(
        task_name="JobPipeAggregator",
        run_command="cmd /c \"echo ok\"",
        interval_hours=2,
        start_time="09:00",
    )

    assert command[0] == "schtasks"
    assert "/Create" in command
    assert "JobPipeAggregator" in command
    assert "/MO" in command
    assert "2" in command
    assert "/ST" in command
    assert "09:00" in command


def test_build_task_status_command_contains_query_flags() -> None:
    command = build_task_status_command(task_name="JobPipeAggregator")

    assert command[0] == "schtasks"
    assert "/Query" in command
    assert "/TN" in command
    assert "JobPipeAggregator" in command
    assert "/V" in command


def test_build_task_run_now_command_contains_run_flags() -> None:
    command = build_task_run_now_command(task_name="JobPipeAggregator")

    assert command[0] == "schtasks"
    assert "/Run" in command
    assert "/TN" in command
    assert "JobPipeAggregator" in command


def test_build_task_delete_command_contains_delete_flags() -> None:
    command = build_task_delete_command(task_name="JobPipeAggregator")

    assert command[0] == "schtasks"
    assert "/Delete" in command
    assert "/TN" in command
    assert "JobPipeAggregator" in command
    assert "/F" in command

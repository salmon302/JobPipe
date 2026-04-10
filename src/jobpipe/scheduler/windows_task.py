from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import platform
import subprocess


def _quote_for_cmd(value: str) -> str:
    return f'""{value}""'


def _ensure_windows_host() -> None:
    if platform.system() != "Windows":
        raise RuntimeError("Windows Task Scheduler integration only supports Windows hosts")


def _is_task_not_found_message(message: str) -> bool:
    lowered = message.lower()
    return (
        "cannot find the file specified" in lowered
        or "cannot find the task" in lowered
        or "the system cannot find" in lowered
        or "does not exist" in lowered
    )


def build_task_run_command(
    python_executable: Path,
    project_root: Path,
    env_file: Path,
    max_pages: int,
) -> str:
    py = _quote_for_cmd(str(python_executable.resolve()))
    root = _quote_for_cmd(str(project_root.resolve()))
    env = _quote_for_cmd(str(env_file.resolve()))

    return (
        'cmd /c "'
        f"cd /d {root} && "
        "set PYTHONPATH=src && "
        f"{py} -m jobpipe --env-file {env} run-once --max-pages {max_pages}"
        '"'
    )


def build_hourly_task_command(
    task_name: str,
    run_command: str,
    interval_hours: int,
    start_time: str | None = None,
) -> list[str]:
    if interval_hours < 1:
        raise ValueError("interval_hours must be >= 1")

    command = [
        "schtasks",
        "/Create",
        "/TN",
        task_name,
        "/TR",
        run_command,
        "/SC",
        "HOURLY",
        "/MO",
        str(interval_hours),
        "/F",
    ]

    if start_time:
        command.extend(["/ST", start_time])

    return command


def build_task_status_command(task_name: str) -> list[str]:
    return ["schtasks", "/Query", "/TN", task_name, "/FO", "LIST", "/V"]


def build_task_run_now_command(task_name: str) -> list[str]:
    return ["schtasks", "/Run", "/TN", task_name]


def build_task_delete_command(task_name: str) -> list[str]:
    return ["schtasks", "/Delete", "/TN", task_name, "/F"]


@dataclass(frozen=True)
class ScheduledTaskResult:
    task_name: str
    interval_hours: int
    run_command: str
    stdout: str


@dataclass(frozen=True)
class TaskStatusResult:
    task_name: str
    exists: bool
    stdout: str


@dataclass(frozen=True)
class TaskActionResult:
    task_name: str
    stdout: str


@dataclass(frozen=True)
class TaskDeleteResult:
    task_name: str
    deleted: bool
    stdout: str


def create_or_update_hourly_task(
    task_name: str,
    python_executable: Path,
    project_root: Path,
    env_file: Path,
    interval_hours: int,
    max_pages: int,
    start_time: str | None = None,
) -> ScheduledTaskResult:
    _ensure_windows_host()

    run_command = build_task_run_command(
        python_executable=python_executable,
        project_root=project_root,
        env_file=env_file,
        max_pages=max_pages,
    )
    command = build_hourly_task_command(
        task_name=task_name,
        run_command=run_command,
        interval_hours=interval_hours,
        start_time=start_time,
    )

    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Failed to configure Windows task '{task_name}': {message}")

    return ScheduledTaskResult(
        task_name=task_name,
        interval_hours=interval_hours,
        run_command=run_command,
        stdout=result.stdout.strip(),
    )


def get_task_status(task_name: str) -> TaskStatusResult:
    _ensure_windows_host()

    command = build_task_status_command(task_name)
    result = subprocess.run(command, capture_output=True, text=True, check=False)

    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip()
        if _is_task_not_found_message(message):
            return TaskStatusResult(task_name=task_name, exists=False, stdout=message)
        raise RuntimeError(f"Failed to query Windows task '{task_name}': {message}")

    return TaskStatusResult(task_name=task_name, exists=True, stdout=result.stdout.strip())


def run_task_now(task_name: str) -> TaskActionResult:
    _ensure_windows_host()

    command = build_task_run_now_command(task_name)
    result = subprocess.run(command, capture_output=True, text=True, check=False)

    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip()
        if _is_task_not_found_message(message):
            raise RuntimeError(f"Windows task '{task_name}' does not exist")
        raise RuntimeError(f"Failed to run Windows task '{task_name}': {message}")

    return TaskActionResult(task_name=task_name, stdout=result.stdout.strip())


def remove_task(task_name: str) -> TaskDeleteResult:
    _ensure_windows_host()

    command = build_task_delete_command(task_name)
    result = subprocess.run(command, capture_output=True, text=True, check=False)

    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip()
        if _is_task_not_found_message(message):
            return TaskDeleteResult(task_name=task_name, deleted=False, stdout=message)
        raise RuntimeError(f"Failed to delete Windows task '{task_name}': {message}")

    return TaskDeleteResult(task_name=task_name, deleted=True, stdout=result.stdout.strip())

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path
import sys

from jobpipe.config import InvalidSettingsError, Settings, load_dotenv
from jobpipe.logging_config import configure_logging
from jobpipe.pipeline import MissingMasterCVError, RunAlreadyInProgressError, run_once
from jobpipe.resume.compiler import LatexCompileConfig, LatexCompilationError, compile_latex
from jobpipe.resume.mcp_server import run_resume_mcp_server
from jobpipe.resume.service import ApprovalRequiredError, write_targeted_resume
from jobpipe.resume.staging import ResumeTargetNotFoundError, stage_job_description
from jobpipe.scrapers.auth_state import (
    StorageStateStatus,
    UnusableStorageStateError,
    bootstrap_storage_state,
    expected_cookie_domains,
    evaluate_storage_state,
)
from jobpipe.scheduler.windows_task import (
    create_or_update_hourly_task,
    get_task_status,
    remove_task,
    run_task_now,
)
from jobpipe.storage.db import initialize_database
from jobpipe.storage.repository import JobRepository

LOGGER = logging.getLogger(__name__)
_AUTH_PLATFORM_CHOICES = ("hiringcafe", "wellfound", "builtin")
_SCRAPING_RUNTIME_COMMANDS = {
    "run-once",
    "install-schedule",
    "auth-bootstrap",
    "auth-status",
    "auth-preflight",
}


def _log_storage_state_status(status: StorageStateStatus) -> None:
    LOGGER.info(
        (
            "Storage state | path=%s exists=%s valid_json=%s cookies=%s "
            "unexpired=%s session=%s usable=%s"
        ),
        status.path,
        status.exists,
        status.valid_json,
        status.cookie_count,
        status.unexpired_cookie_count,
        status.session_cookie_count,
        status.usable,
    )
    for issue in status.errors:
        LOGGER.warning("Storage state issue: %s", issue)


def _default_auth_platforms(settings: Settings, include_disabled: bool) -> list[str]:
    if include_disabled:
        return list(_AUTH_PLATFORM_CHOICES)

    platforms = ["hiringcafe"]
    if settings.wellfound_enabled:
        platforms.append("wellfound")
    if settings.builtin_enabled:
        platforms.append("builtin")

    return platforms


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jobpipe", description="JobPipe CLI")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="Path to dotenv file",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init-db", help="Initialize SQLite schema")
    init_parser.add_argument("--db-path", type=Path, help="Override database path")

    run_parser = subparsers.add_parser("run-once", help="Run one scrape + score cycle")
    run_parser.add_argument("--max-pages", type=int, default=1, help="Max number of pages to scrape")

    top_parser = subparsers.add_parser("top", help="Print top scored jobs")
    top_parser.add_argument("--limit", type=int, default=10, help="Rows to print")

    runs_parser = subparsers.add_parser("runs", help="Print recent run telemetry")
    runs_parser.add_argument("--limit", type=int, default=10, help="Rows to print")

    notifications_parser = subparsers.add_parser(
        "notifications",
        help="Print recent notification audit entries",
    )
    notifications_parser.add_argument("--limit", type=int, default=10, help="Rows to print")

    schedule_parser = subparsers.add_parser(
        "install-schedule",
        help="Create or update a Windows Task Scheduler job",
    )
    schedule_parser.add_argument("--task-name", default="JobPipeAggregator")
    schedule_parser.add_argument("--interval-hours", type=int, help="Run frequency in hours")
    schedule_parser.add_argument("--start-time", help="Optional daily start time in HH:MM")
    schedule_parser.add_argument("--max-pages", type=int, default=1)

    status_parser = subparsers.add_parser(
        "schedule-status",
        help="Show current Windows Task Scheduler status for JobPipe",
    )
    status_parser.add_argument("--task-name", default="JobPipeAggregator")

    run_now_parser = subparsers.add_parser(
        "run-now",
        help="Trigger a configured Windows Task Scheduler job immediately",
    )
    run_now_parser.add_argument("--task-name", default="JobPipeAggregator")

    uninstall_parser = subparsers.add_parser(
        "uninstall-schedule",
        help="Delete a Windows Task Scheduler job",
    )
    uninstall_parser.add_argument("--task-name", default="JobPipeAggregator")

    auth_bootstrap_parser = subparsers.add_parser(
        "auth-bootstrap",
        help="Interactively capture platform browser session state",
    )
    auth_bootstrap_parser.add_argument(
        "--platform",
        choices=_AUTH_PLATFORM_CHOICES,
        default="hiringcafe",
        help="Platform auth profile to capture",
    )
    auth_bootstrap_parser.add_argument("--base-url", help="Override platform base URL")
    auth_bootstrap_parser.add_argument(
        "--storage-state",
        type=Path,
        help="Override platform storage state file path",
    )
    auth_bootstrap_parser.add_argument(
        "--headless",
        action="store_true",
        help="Launch browser headless during auth bootstrap",
    )

    auth_status_parser = subparsers.add_parser(
        "auth-status",
        help="Validate current platform storage state cookies",
    )
    auth_status_parser.add_argument(
        "--platform",
        choices=_AUTH_PLATFORM_CHOICES,
        default="hiringcafe",
        help="Platform auth profile to validate",
    )
    auth_status_parser.add_argument(
        "--storage-state",
        type=Path,
        help="Override platform storage state file path",
    )
    auth_status_parser.add_argument(
        "--base-url",
        help="Override platform base URL for cookie domain validation",
    )

    auth_preflight_parser = subparsers.add_parser(
        "auth-preflight",
        help="Validate auth storage state for one or more platforms",
    )
    auth_preflight_parser.add_argument(
        "--platform",
        action="append",
        choices=_AUTH_PLATFORM_CHOICES,
        help="Platform auth profile(s) to validate (repeatable)",
    )
    auth_preflight_parser.add_argument(
        "--include-disabled",
        action="store_true",
        help="When no --platform is provided, include disabled platforms in checks",
    )
    auth_preflight_parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Return non-zero when any selected platform is unusable. "
            "Defaults to JOBPIPE_REQUIRE_USABLE_AUTH_STATE when omitted."
        ),
    )

    resume_stage_parser = subparsers.add_parser(
        "resume-stage",
        help="Write top eligible job into Job_Description.md for resume generation",
    )
    resume_stage_parser.add_argument("--job-id", help="Optional specific job id to stage")
    resume_stage_parser.add_argument(
        "--min-score",
        type=float,
        help="Minimum score required for staging (defaults to notification threshold)",
    )
    resume_stage_parser.add_argument(
        "--output",
        type=Path,
        help="Override Job_Description markdown path",
    )

    resume_write_parser = subparsers.add_parser(
        "resume-write",
        help="Write approved targeted LaTeX and compile PDF",
    )
    resume_write_parser.add_argument("--input-tex", type=Path, required=True)
    resume_write_parser.add_argument(
        "--output-name",
        help="Output file name (without extension defaults to configured basename)",
    )
    resume_write_parser.add_argument(
        "--approved",
        action="store_true",
        help="Must be supplied after manual review to allow file writes",
    )

    resume_compile_parser = subparsers.add_parser(
        "resume-compile",
        help="Compile a LaTeX resume file into PDF",
    )
    resume_compile_parser.add_argument(
        "--tex-path",
        type=Path,
        help="Path to .tex file (defaults to configured basename in resume output dir)",
    )

    subparsers.add_parser(
        "resume-server",
        help="Run local MCP resume server for Claude Desktop",
    )

    gui_parser = subparsers.add_parser(
        "gui",
        help="Launch the local JobPipe desktop GUI",
    )
    gui_parser.add_argument(
        "--max-pages",
        type=int,
        default=1,
        help="Default max pages value for the Run Once action",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = _build_parser()
    provided_args = sys.argv[1:] if argv is None else list(argv)
    if not provided_args:
        parser.print_help()
        return 0

    args = parser.parse_args(provided_args)
    load_dotenv(args.env_file)
    settings = Settings.from_env()

    if args.command in _SCRAPING_RUNTIME_COMMANDS:
        try:
            settings.validate_scraping_runtime()
        except InvalidSettingsError as exc:
            LOGGER.error("%s", exc)
            return 2

    if args.command == "init-db":
        db_path = args.db_path or settings.db_path
        initialize_database(db_path)
        LOGGER.info("Database initialized at %s", db_path)
        return 0

    if args.command == "run-once":
        try:
            summary = asyncio.run(run_once(settings, max_pages=args.max_pages))
        except (
            InvalidSettingsError,
            RunAlreadyInProgressError,
            MissingMasterCVError,
            UnusableStorageStateError,
        ) as exc:
            LOGGER.error("%s", exc)
            return 2

        LOGGER.info(
            "Run complete | scraped=%s inserted=%s updated=%s scored=%s above_threshold=%s notified=%s",
            summary.scraped,
            summary.inserted,
            summary.updated,
            summary.scored,
            summary.above_threshold,
            summary.notified,
        )
        return 0

    if args.command == "top":
        repository = JobRepository(settings.db_path)
        jobs = repository.list_top_jobs(limit=args.limit)
        for job in jobs:
            score = "n/a" if job.match_score is None else f"{job.match_score:.3f}"
            print(f"[{score}] {job.title} | {job.company} | {job.url}")
        return 0

    if args.command == "runs":
        repository = JobRepository(settings.db_path)
        runs = repository.list_recent_runs(limit=args.limit)
        for run in runs:
            finished = "in-progress" if run.finished_at is None else run.finished_at.isoformat()
            error = "" if not run.error_message else f" | error={run.error_message}"
            print(
                (
                    f"[{run.status}] {run.run_id} | started={run.started_at.isoformat()} "
                    f"| finished={finished} | scraped={run.scraped} inserted={run.inserted} "
                    f"updated={run.updated} scored={run.scored} "
                    f"above={run.above_threshold} notified={run.notified}{error}"
                )
            )
        return 0

    if args.command == "notifications":
        repository = JobRepository(settings.db_path)
        events = repository.list_recent_notifications(limit=args.limit)
        for event in events:
            score = "n/a" if event.score is None else f"{event.score:.3f}"
            run_ref = "n/a" if not event.run_id else event.run_id
            error = "" if not event.error_message else f" | error={event.error_message}"
            print(
                (
                    f"[{event.delivery_status}] {event.notification_id} | run={run_ref} "
                    f"| job={event.job_id} | score={score} | title={event.title} "
                    f"| company={event.company} | at={event.notified_at.isoformat()} "
                    f"| {event.url}{error}"
                )
            )
        return 0

    if args.command == "auth-bootstrap":
        platform = args.platform
        base_url = args.base_url or settings.platform_base_url(platform)
        storage_state = args.storage_state or settings.platform_storage_state(platform)
        platform_label = "Built In" if platform == "builtin" else platform.title()
        LOGGER.info(
            "Starting auth bootstrap | platform=%s base_url=%s storage_state=%s headless=%s",
            platform,
            base_url,
            storage_state,
            args.headless,
        )
        try:
            result = asyncio.run(
                bootstrap_storage_state(
                    base_url=base_url,
                    storage_state=storage_state,
                    headless=args.headless,
                    prompt_label=platform_label,
                )
            )
        except KeyboardInterrupt:
            LOGGER.warning("Auth bootstrap cancelled by user")
            return 130
        except RuntimeError as exc:
            LOGGER.error("%s", exc)
            return 2

        _log_storage_state_status(result.status)
        if not result.status.usable:
            LOGGER.error(
                "Captured storage state is not usable. Re-run auth-bootstrap and ensure login succeeds."
            )
            return 2

        LOGGER.info("Auth bootstrap complete for %s", platform_label)
        return 0

    if args.command == "auth-status":
        platform = args.platform
        storage_state = args.storage_state or settings.platform_storage_state(platform)
        base_url = args.base_url or settings.platform_base_url(platform)
        status = evaluate_storage_state(
            storage_state,
            expected_domains=expected_cookie_domains(base_url),
        )
        _log_storage_state_status(status)
        return 0 if status.usable else 1

    if args.command == "auth-preflight":
        selected_platforms = args.platform or _default_auth_platforms(
            settings,
            include_disabled=args.include_disabled,
        )
        strict = args.strict or settings.require_usable_auth_state

        failing_platforms: list[str] = []
        for platform in selected_platforms:
            base_url = settings.platform_base_url(platform)
            storage_state = settings.platform_storage_state(platform)
            expected_domains = expected_cookie_domains(base_url)

            LOGGER.info(
                "Auth preflight | platform=%s storage_state=%s expected_domains=%s",
                platform,
                storage_state,
                ",".join(expected_domains) if expected_domains else "n/a",
            )

            status = evaluate_storage_state(
                storage_state,
                expected_domains=expected_domains,
            )
            _log_storage_state_status(status)
            if not status.usable:
                failing_platforms.append(platform)

        if failing_platforms:
            LOGGER.warning(
                "Auth preflight found unusable platform(s): %s",
                ", ".join(failing_platforms),
            )
            if strict:
                LOGGER.error(
                    "Strict auth preflight failed. Run auth-bootstrap for each failing platform."
                )
                return 2

        LOGGER.info(
            "Auth preflight complete | checked=%s failing=%s strict=%s",
            len(selected_platforms),
            len(failing_platforms),
            strict,
        )
        return 0

    if args.command == "resume-stage":
        repository = JobRepository(settings.db_path)
        minimum_score = (
            settings.notification_threshold if args.min_score is None else args.min_score
        )
        output_path = args.output or settings.job_description_path

        try:
            staged = stage_job_description(
                repository=repository,
                output_path=output_path,
                minimum_score=minimum_score,
                job_id=args.job_id,
            )
        except ResumeTargetNotFoundError as exc:
            LOGGER.error("%s", exc)
            return 1

        score = "n/a" if staged.score is None else f"{staged.score:.3f}"
        LOGGER.info(
            "Staged job description | job=%s title=%s company=%s score=%s path=%s",
            staged.job_id,
            staged.title,
            staged.company,
            score,
            staged.output_path,
        )
        return 0

    if args.command == "resume-write":
        try:
            tex_content = args.input_tex.read_text(encoding="utf-8")
        except OSError as exc:
            LOGGER.error("Unable to read input TeX file %s: %s", args.input_tex, exc)
            return 1

        compile_config = LatexCompileConfig(
            pdflatex_command=settings.resume_pdflatex_command,
            retries=settings.resume_compile_retries,
            timeout_seconds=settings.resume_compile_timeout_seconds,
        )

        try:
            result = write_targeted_resume(
                tex_content=tex_content,
                output_name=args.output_name or settings.resume_target_basename,
                output_dir=settings.resume_output_dir,
                compile_config=compile_config,
                approved=args.approved,
                write_retries=settings.resume_write_retries,
                default_base_name=settings.resume_target_basename,
            )
        except ApprovalRequiredError as exc:
            LOGGER.error("%s", exc)
            return 2
        except LatexCompilationError as exc:
            LOGGER.error("%s", exc)
            return 2
        except RuntimeError as exc:
            LOGGER.error("%s", exc)
            return 2

        LOGGER.info(
            "Resume write+compile complete | tex=%s pdf=%s attempts=%s",
            result.tex_path,
            result.pdf_path,
            result.compile_attempts,
        )
        return 0

    if args.command == "resume-compile":
        tex_path = args.tex_path
        if tex_path is None:
            default_name = settings.resume_target_basename
            if not default_name.lower().endswith(".tex"):
                default_name = f"{default_name}.tex"
            tex_path = settings.resume_output_dir / default_name

        compile_config = LatexCompileConfig(
            pdflatex_command=settings.resume_pdflatex_command,
            retries=settings.resume_compile_retries,
            timeout_seconds=settings.resume_compile_timeout_seconds,
        )

        try:
            result = compile_latex(
                tex_path=tex_path,
                output_pdf_path=tex_path.with_suffix(".pdf"),
                config=compile_config,
            )
        except LatexCompilationError as exc:
            LOGGER.error("%s", exc)
            return 2

        LOGGER.info(
            "Resume compile complete | tex=%s pdf=%s attempts=%s",
            result.tex_path,
            result.pdf_path,
            result.attempts,
        )
        return 0

    if args.command == "resume-server":
        try:
            run_resume_mcp_server(settings)
        except RuntimeError as exc:
            LOGGER.error("%s", exc)
            return 2
        return 0

    if args.command == "gui":
        try:
            from jobpipe.gui.app import launch_gui

            return launch_gui(settings=settings, default_max_pages=args.max_pages)
        except (ImportError, RuntimeError) as exc:
            LOGGER.error("%s", exc)
            return 2

    if args.command == "install-schedule":
        interval_hours = args.interval_hours or settings.schedule_interval_hours
        result = create_or_update_hourly_task(
            task_name=args.task_name,
            python_executable=Path(sys.executable),
            project_root=Path.cwd(),
            env_file=args.env_file.resolve(),
            interval_hours=interval_hours,
            max_pages=args.max_pages,
            start_time=args.start_time,
        )
        LOGGER.info(
            "Scheduled task configured | task=%s interval_hours=%s",
            result.task_name,
            result.interval_hours,
        )
        LOGGER.info("Task run command: %s", result.run_command)
        return 0

    if args.command == "schedule-status":
        result = get_task_status(args.task_name)
        if not result.exists:
            LOGGER.warning("Scheduled task not found | task=%s", args.task_name)
            if result.stdout:
                LOGGER.info(result.stdout)
            return 1

        LOGGER.info("Scheduled task found | task=%s", args.task_name)
        if result.stdout:
            print(result.stdout)
        return 0

    if args.command == "run-now":
        result = run_task_now(args.task_name)
        LOGGER.info("Scheduled task triggered | task=%s", args.task_name)
        if result.stdout:
            LOGGER.info(result.stdout)
        return 0

    if args.command == "uninstall-schedule":
        result = remove_task(args.task_name)
        if result.deleted:
            LOGGER.info("Scheduled task removed | task=%s", args.task_name)
        else:
            LOGGER.info("Scheduled task already absent | task=%s", args.task_name)
        if result.stdout:
            LOGGER.info(result.stdout)
        return 0

    parser.print_help()
    return 1

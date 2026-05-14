# Purpose: Provide CLI entry points for ingest and resume workflows.
# Author: Seth Nenninger (GPT-5.2-Codex Agent)
# Timestamp: 2026-05-12T00:00:00Z
# Changelog: Replace scraper/scheduler commands with ingest server command.

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys

from jobpipe.config import InvalidSettingsError, Settings, load_dotenv
from jobpipe.ingest.server import run_ingest_server
from jobpipe.logging_config import configure_logging
from jobpipe.resume.compiler import LatexCompileConfig, LatexCompilationError, compile_latex
from jobpipe.resume.mcp_server import run_resume_mcp_server
from jobpipe.resume.service import ApprovalRequiredError, write_targeted_resume
from jobpipe.resume.staging import ResumeTargetNotFoundError, stage_job_description
from jobpipe.storage.db import initialize_database
from jobpipe.storage.repository import JobRepository

LOGGER = logging.getLogger(__name__)
_RUNTIME_COMMANDS = {"ingest-server", "gui"}


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

    clear_parser = subparsers.add_parser("clear-db", help="Clear all jobs and runs data")
    clear_parser.add_argument("--db-path", type=Path, help="Override database path")
    clear_parser.add_argument(
        "--confirm",
        action="store_true",
        help="Must be supplied to confirm deletion",
    )

    ingest_parser = subparsers.add_parser(
        "ingest-server",
        help="Run the local ingest HTTP server",
    )
    ingest_parser.add_argument("--host", help="Override ingest host")
    ingest_parser.add_argument("--port", type=int, help="Override ingest port")

    top_parser = subparsers.add_parser("top", help="Print top scored jobs")
    top_parser.add_argument("--limit", type=int, default=10, help="Rows to print")

    runs_parser = subparsers.add_parser("runs", help="Print recent run telemetry")
    runs_parser.add_argument("--limit", type=int, default=10, help="Rows to print")

    notifications_parser = subparsers.add_parser(
        "notifications",
        help="Print recent notification audit entries",
    )
    notifications_parser.add_argument("--limit", type=int, default=10, help="Rows to print")

    db_stats_parser = subparsers.add_parser(
        "db-stats",
        help="Show database statistics (job counts, statuses)",
    )
    db_stats_parser.add_argument("--db-path", type=Path, help="Override database path")

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

    resume_generate_parser = subparsers.add_parser(
        "resume-generate",
        help="Generate targeted LaTeX resume using Gemini API",
    )
    resume_generate_parser.add_argument(
        "--output-name",
        help="Output file name (without extension, defaults to configured basename)",
    )
    resume_generate_parser.add_argument(
        "--template",
        type=Path,
        help="Optional LaTeX template file to guide generation",
    )

    subparsers.add_parser(
        "resume-server",
        help="Run local MCP resume server for Claude Desktop",
    )

    subparsers.add_parser(
        "gui",
        help="Launch the local JobPipe desktop GUI",
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

    if args.command in _RUNTIME_COMMANDS:
        try:
            settings.validate_runtime()
        except InvalidSettingsError as exc:
            LOGGER.error("%s", exc)
            return 2

    if args.command == "init-db":
        db_path = args.db_path or settings.db_path
        initialize_database(db_path)
        LOGGER.info("Database initialized at %s", db_path)
        return 0

    if args.command == "clear-db":
        if not args.confirm:
            LOGGER.error("Must supply --confirm to clear database")
            return 1
        db_path = args.db_path or settings.db_path
        from jobpipe.storage.db import connect
        with connect(db_path) as conn:
            conn.execute("DELETE FROM notifications_audit")
            conn.execute("DELETE FROM jobs")
            conn.execute("DELETE FROM scrape_runs")
            conn.commit()
        LOGGER.info("Cleared all jobs and runs data from %s", db_path)
        return 0

    if args.command == "ingest-server":
        try:
            run_ingest_server(settings, host=args.host, port=args.port)
        except OSError as exc:
            LOGGER.error("Ingest server failed: %s", exc)
            return 2
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
                    f"| finished={finished} | ingested={run.scraped} inserted={run.inserted} "
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

    if args.command == "resume-generate":
        # Generate resume using Gemini API
        from jobpipe.resume.gemini_client import (
            GeminiAPIError,
            create_gemini_client_from_settings,
        )
        from jobpipe.resume.service import write_targeted_resume as write_resume

        if not settings.gemini_api_key:
            LOGGER.error(
                "Gemini API key not configured. Set JOBPIPE_GEMINI_API_KEY in .env file."
            )
            return 2

        # Read Master CV
        if not settings.master_cv_path.exists():
            LOGGER.error("Master CV not found at: %s", settings.master_cv_path)
            return 1

        master_cv = settings.master_cv_path.read_text(encoding="utf-8")
        if not master_cv.strip():
            LOGGER.error("Master CV is empty at: %s", settings.master_cv_path)
            return 1

        # Read Job Description
        if not settings.job_description_path.exists():
            LOGGER.error("Job description not found at: %s", settings.job_description_path)
            return 1

        job_description = settings.job_description_path.read_text(encoding="utf-8")
        if not job_description.strip():
            LOGGER.error("Job description is empty at: %s", settings.job_description_path)
            return 1

        # Optional LaTeX template
        latex_template = None
        if args.template and args.template.exists():
            latex_template = args.template.read_text(encoding="utf-8")

        try:
            # Create Gemini client
            client = create_gemini_client_from_settings(settings)

            # Check API health
            if not client.health_check():
                LOGGER.warning("Gemini API health check failed. Proceeding anyway...")

            # Generate resume
            LOGGER.info("Generating resume with Gemini API (%s)...", settings.gemini_model)
            response = client.generate_resume(
                master_cv=master_cv,
                job_description=job_description,
                latex_template=latex_template,
            )

            # Output path
            output_name = args.output_name or settings.resume_target_basename
            if not output_name.lower().endswith(".tex"):
                output_name = f"{output_name}.tex"

            output_path = settings.resume_output_dir / output_name

            # Write LaTeX to file (not approved yet - user must review)
            settings.resume_output_dir.mkdir(parents=True, exist_ok=True)
            output_path.write_text(response.text, encoding="utf-8")

            LOGGER.info("Resume generated successfully!")
            LOGGER.info("TeX file: %s", output_path)
            LOGGER.info("")
            LOGGER.info("Next steps:")
            LOGGER.info("  1. Review the generated LaTeX: %s", output_path)
            LOGGER.info("  2. Edit if needed")
            LOGGER.info("  3. Compile with: jobpipe resume-write --input-tex %s --approved", output_path)

            return 0

        except GeminiAPIError as exc:
            LOGGER.error("Gemini API error: %s", exc)
            return 2
        except Exception as exc:
            LOGGER.error("Unexpected error: %s", exc)
            return 2

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

            return launch_gui(settings=settings)
        except (ImportError, RuntimeError) as exc:
            LOGGER.error("%s", exc)
            return 2

    if args.command == "db-stats":
        db_path = args.db_path or settings.db_path
        from jobpipe.storage.db import connect

        with connect(db_path) as conn:
            # Total jobs
            total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]

            # By status
            status_rows = conn.execute(
                "SELECT status, COUNT(*) as cnt FROM jobs GROUP BY status ORDER BY cnt DESC"
            ).fetchall()

            # By platform
            platform_rows = conn.execute(
                "SELECT platform, COUNT(*) as cnt FROM jobs GROUP BY platform ORDER BY cnt DESC"
            ).fetchall()

            # Recent runs
            run_count = conn.execute("SELECT COUNT(*) FROM scrape_runs").fetchone()[0]

            # Average score
            avg_score = conn.execute(
                "SELECT AVG(match_score) FROM jobs WHERE match_score IS NOT NULL"
            ).fetchone()[0]

        print(f"\n=== JobPipe Database Statistics ===")
        print(f"Database: {db_path}")
        print(f"\nTotal jobs: {total}")
        print(f"Total runs: {run_count}")
        print(f"Average match score: {avg_score:.3f}" if avg_score else "Average match score: n/a")

        print(f"\n--- Jobs by Status ---")
        for row in status_rows:
            print(f"  {row['status']}: {row['cnt']}")

        print(f"\n--- Jobs by Platform ---")
        for row in platform_rows:
            print(f"  {row['platform']}: {row['cnt']}")

        print()
        return 0

    parser.print_help()
    return 1

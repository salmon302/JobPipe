from __future__ import annotations

import asyncio
from dataclasses import dataclass
from os import environ
from pathlib import Path
import sys

from jobpipe.config import InvalidSettingsError, Settings
from jobpipe.pipeline import RunSummary, run_once
from jobpipe.resume.compiler import LatexCompileConfig, LatexCompileResult, compile_latex
from jobpipe.resume.staging import StagedJobDescription, stage_job_description
from jobpipe.scrapers.auth_state import evaluate_storage_state, StorageStateStatus
from jobpipe.storage.db import connect, initialize_database
from jobpipe.storage.models import JobRecord, NotificationAuditRecord, ScrapeRunRecord
from jobpipe.storage.repository import JobRepository


_EDITABLE_ENV_KEYS = (
    "JOBPIPE_NOTIFICATION_THRESHOLD",
    "JOBPIPE_USER_YEARS_EXPERIENCE",
    "JOBPIPE_SCHEDULE_INTERVAL_HOURS",
    "JOBPIPE_AUTO_STAGE_JOB_DESCRIPTION",
    "JOBPIPE_REQUIRE_USABLE_AUTH_STATE",
    "JOBPIPE_WELLFOUND_ENABLED",
    "JOBPIPE_BUILTIN_ENABLED",
    "JOBPIPE_CRITICAL_SKILLS",
    "JOBPIPE_REJECT_TERMS",
)


@dataclass(frozen=True)
class DashboardSnapshot:
    total_jobs: int
    queued_jobs: int
    notified_jobs: int
    above_threshold_jobs: int
    last_run: ScrapeRunRecord | None
    auth_states: dict[str, StorageStateStatus]


class JobPipeGuiService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def editable_env_keys(self) -> tuple[str, ...]:
        return _EDITABLE_ENV_KEYS

    def editable_env_file_path(self, env_file: Path | None = None) -> Path:
        return self._env_file_path(env_file)

    def _prepare(self) -> None:
        self._settings.ensure_runtime_dirs()
        initialize_database(self._settings.db_path)

    def _repository(self) -> JobRepository:
        return JobRepository(self._settings.db_path)

    def dashboard_snapshot(self) -> DashboardSnapshot:
        self._prepare()
        repository = self._repository()

        with connect(self._settings.db_path) as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_jobs,
                    SUM(CASE WHEN status = 'Queued' THEN 1 ELSE 0 END) AS queued_jobs,
                    SUM(CASE WHEN status = 'Notified' THEN 1 ELSE 0 END) AS notified_jobs,
                    SUM(
                        CASE
                            WHEN match_score IS NOT NULL AND match_score >= ?
                            THEN 1
                            ELSE 0
                        END
                    ) AS above_threshold_jobs
                FROM jobs
                """,
                (self._settings.notification_threshold,),
            ).fetchone()

        recent_runs = repository.list_recent_runs(limit=1)

        auth_states = {
            "HiringCafe": evaluate_storage_state(self._settings.hiringcafe_storage_state),
            "Wellfound": evaluate_storage_state(self._settings.wellfound_storage_state),
            "BuiltIn": evaluate_storage_state(self._settings.builtin_storage_state),
        }

        return DashboardSnapshot(
            total_jobs=int(row["total_jobs"] or 0),
            queued_jobs=int(row["queued_jobs"] or 0),
            notified_jobs=int(row["notified_jobs"] or 0),
            above_threshold_jobs=int(row["above_threshold_jobs"] or 0),
            last_run=recent_runs[0] if recent_runs else None,
            auth_states=auth_states,
        )

    def list_top_jobs(self, limit: int = 100) -> list[JobRecord]:
        self._prepare()
        repository = self._repository()
        return repository.list_top_jobs(limit=limit)

    def list_recent_runs(self, limit: int = 100) -> list[ScrapeRunRecord]:
        self._prepare()
        repository = self._repository()
        return repository.list_recent_runs(limit=limit)

    def list_recent_notifications(self, limit: int = 100) -> list[NotificationAuditRecord]:
        self._prepare()
        repository = self._repository()
        return repository.list_recent_notifications(limit=limit)

    def run_pipeline_once(self, max_pages: int = 1) -> RunSummary:
        self._prepare()
        return asyncio.run(run_once(self._settings, max_pages=max_pages))

    def default_resume_tex_path(self) -> Path:
        name = self._settings.resume_target_basename
        if not name.lower().endswith(".tex"):
            name = f"{name}.tex"
        return self._settings.resume_output_dir / name

    def stage_resume_target(
        self,
        minimum_score: float | None = None,
        job_id: str | None = None,
        output_path: Path | None = None,
    ) -> StagedJobDescription:
        self._prepare()
        repository = self._repository()

        threshold = self._settings.notification_threshold if minimum_score is None else minimum_score
        target_path = output_path or self._settings.job_description_path
        return stage_job_description(
            repository=repository,
            output_path=target_path,
            minimum_score=threshold,
            job_id=job_id,
        )

    def compile_resume(self, tex_path: Path | None = None) -> LatexCompileResult:
        self._prepare()
        target_tex = tex_path or self.default_resume_tex_path()
        config = LatexCompileConfig(
            pdflatex_command=self._settings.resume_pdflatex_command,
            retries=self._settings.resume_compile_retries,
            timeout_seconds=self._settings.resume_compile_timeout_seconds,
        )
        return compile_latex(
            tex_path=target_tex,
            output_pdf_path=target_tex.with_suffix(".pdf"),
            config=config,
        )

    def load_editable_env_values(self, env_file: Path | None = None) -> dict[str, str]:
        path = self._env_file_path(env_file)
        values = self._default_editable_env_values()
        values.update(
            {
                key: value
                for key, value in self._read_env_file(path).items()
                if key in _EDITABLE_ENV_KEYS
            }
        )
        return values

    def validate_editable_env_values(self, values: dict[str, str]) -> None:
        normalized = {
            key: values.get(key, "").strip()
            for key in _EDITABLE_ENV_KEYS
        }

        snapshot = {
            key: environ.get(key)
            for key in _EDITABLE_ENV_KEYS
        }

        try:
            for key, value in normalized.items():
                environ[key] = value

            candidate = Settings.from_env()
            candidate.validate_scraping_runtime()
        except (InvalidSettingsError, ValueError) as exc:
            raise InvalidSettingsError(str(exc)) from exc
        finally:
            for key, original in snapshot.items():
                if original is None:
                    environ.pop(key, None)
                else:
                    environ[key] = original

    def save_editable_env_values(
        self,
        values: dict[str, str],
        env_file: Path | None = None,
    ) -> Path:
        path = self._env_file_path(env_file)
        normalized = {
            key: values.get(key, "").strip()
            for key in _EDITABLE_ENV_KEYS
        }

        self.validate_editable_env_values(normalized)
        self._upsert_env_values(path, normalized)

        for key, value in normalized.items():
            environ[key] = value

        self._settings = Settings.from_env()
        return path

    def scheduler_status(self, task_name: str = "JobPipeAggregator") -> TaskStatusResult:
        return get_task_status(task_name)

    def install_or_update_scheduler(
        self,
        task_name: str = "JobPipeAggregator",
        interval_hours: int | None = None,
        max_pages: int = 1,
        start_time: str | None = None,
        env_file: Path | None = None,
    ):
        interval = interval_hours or self._settings.schedule_interval_hours
        root = self._project_root()
        env_path = env_file or root / ".env"

        return create_or_update_hourly_task(
            task_name=task_name,
            python_executable=Path(sys.executable),
            project_root=root,
            env_file=env_path,
            interval_hours=interval,
            max_pages=max_pages,
            start_time=start_time,
        )

    def run_scheduler_now(self, task_name: str = "JobPipeAggregator") -> TaskActionResult:
        return run_task_now(task_name)

    def uninstall_scheduler(self, task_name: str = "JobPipeAggregator") -> TaskDeleteResult:
        return remove_task(task_name)

    def _project_root(self) -> Path:
        cwd = Path.cwd()
        if (cwd / "src" / "jobpipe").exists():
            return cwd

        # Fallback when the GUI is launched from a different working directory.
        return Path(__file__).resolve().parents[3]

    def _env_file_path(self, env_file: Path | None = None) -> Path:
        if env_file is not None:
            return env_file
        return self._project_root() / ".env"

    def _default_editable_env_values(self) -> dict[str, str]:
        return {
            "JOBPIPE_NOTIFICATION_THRESHOLD": str(self._settings.notification_threshold),
            "JOBPIPE_USER_YEARS_EXPERIENCE": str(self._settings.user_years_experience),
            "JOBPIPE_SCHEDULE_INTERVAL_HOURS": str(self._settings.schedule_interval_hours),
            "JOBPIPE_AUTO_STAGE_JOB_DESCRIPTION": str(
                self._settings.auto_stage_job_description
            ).lower(),
            "JOBPIPE_REQUIRE_USABLE_AUTH_STATE": str(
                self._settings.require_usable_auth_state
            ).lower(),
            "JOBPIPE_WELLFOUND_ENABLED": str(self._settings.wellfound_enabled).lower(),
            "JOBPIPE_BUILTIN_ENABLED": str(self._settings.builtin_enabled).lower(),
            "JOBPIPE_CRITICAL_SKILLS": ",".join(self._settings.critical_skills),
            "JOBPIPE_REJECT_TERMS": ",".join(self._settings.reject_terms),
        }

    def _read_env_file(self, path: Path) -> dict[str, str]:
        if not path.exists():
            return {}

        result: dict[str, str] = {}
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            normalized_key = key.strip()
            normalized_value = value.strip().strip('"').strip("'")
            if normalized_key:
                result[normalized_key] = normalized_value

        return result

    def _upsert_env_values(self, path: Path, updates: dict[str, str]) -> None:
        existing_lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        updated_lines: list[str] = []
        seen: set[str] = set()

        for raw_line in existing_lines:
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#") or "=" not in raw_line:
                updated_lines.append(raw_line)
                continue

            key, _ = raw_line.split("=", 1)
            normalized_key = key.strip()
            if normalized_key in updates:
                updated_lines.append(f"{normalized_key}={updates[normalized_key]}")
                seen.add(normalized_key)
                continue

            updated_lines.append(raw_line)

        for key in _EDITABLE_ENV_KEYS:
            if key in updates and key not in seen:
                updated_lines.append(f"{key}={updates[key]}")

        path.parent.mkdir(parents=True, exist_ok=True)
        content = "\n".join(updated_lines).strip()
        path.write_text(f"{content}\n" if content else "", encoding="utf-8")
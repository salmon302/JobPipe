from __future__ import annotations

from dataclasses import dataclass
from os import environ, getenv
from pathlib import Path
from urllib.parse import urlparse


_DEFAULT_ROTATING_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:137.0) Gecko/20100101 Firefox/137.0",
]


class InvalidSettingsError(RuntimeError):
    pass


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_float(value: str | None, default: float) -> float:
    if value is None:
        return default
    return float(value)


def _as_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    return int(value)


def _split_csv(value: str | None, default: list[str]) -> list[str]:
    if value is None:
        return default

    normalized = value.strip()
    if not normalized:
        return []

    # Support both CSV values and legacy space-delimited values from older .env examples.
    if "," in normalized:
        return [chunk.strip() for chunk in normalized.split(",") if chunk.strip()]

    return [chunk.strip() for chunk in normalized.split() if chunk.strip()]


def _split_multi_value(value: str | None, default: list[str]) -> list[str]:
    if value is None:
        return list(default)

    normalized = value.strip()
    if not normalized:
        return []

    if "||" in normalized:
        chunks = normalized.split("||")
    elif "\n" in normalized:
        chunks = normalized.splitlines()
    else:
        chunks = normalized.split(",")

    return [chunk.strip() for chunk in chunks if chunk.strip()]


def _is_valid_http_url(value: str) -> bool:
    candidate = value.strip()
    if not candidate:
        return False

    if "://" not in candidate:
        candidate = f"https://{candidate}"

    parsed = urlparse(candidate)
    return parsed.scheme in {"http", "https"} and bool(parsed.hostname)


def load_dotenv(dotenv_path: Path) -> None:
    if not dotenv_path.exists():
        return

    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"").strip("'")

        if key and key not in environ:
            environ[key] = value


@dataclass(frozen=True)
class Settings:
    db_path: Path
    master_cv_path: Path
    job_description_path: Path
    resume_output_dir: Path
    resume_target_basename: str
    resume_pdflatex_command: str
    resume_compile_retries: int
    resume_compile_timeout_seconds: int
    resume_write_retries: int
    hiringcafe_base_url: str
    hiringcafe_search_urls: list[str]
    hiringcafe_storage_state: Path
    hiringcafe_headless: bool
    hiringcafe_jitter_min: float
    hiringcafe_jitter_max: float
    hiringcafe_fetch_detail_descriptions: bool
    wellfound_enabled: bool
    wellfound_base_url: str
    wellfound_search_urls: list[str]
    wellfound_storage_state: Path
    wellfound_headless: bool
    wellfound_jitter_min: float
    wellfound_jitter_max: float
    wellfound_fetch_detail_descriptions: bool
    builtin_enabled: bool
    builtin_base_url: str
    builtin_search_urls: list[str]
    builtin_storage_state: Path
    builtin_headless: bool
    builtin_jitter_min: float
    builtin_jitter_max: float
    builtin_fetch_detail_descriptions: bool
    user_agents: list[str]
    hiringcafe_user_agents: list[str]
    wellfound_user_agents: list[str]
    builtin_user_agents: list[str]
    critical_skills: list[str]
    reject_terms: list[str]
    user_years_experience: int
    notification_threshold: float
    auto_stage_job_description: bool
    embed_model: str
    require_usable_auth_state: bool
    schedule_interval_hours: int
    run_lock_path: Path
    run_lock_stale_seconds: int

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            db_path=Path(getenv("JOBPIPE_DB_PATH", "data/jobpipe.db")),
            master_cv_path=Path(getenv("JOBPIPE_MASTER_CV_PATH", "Master_CV.md")),
            job_description_path=Path(getenv("JOBPIPE_JOB_DESCRIPTION_PATH", "Job_Description.md")),
            resume_output_dir=Path(getenv("JOBPIPE_RESUME_OUTPUT_DIR", "data/resume")),
            resume_target_basename=getenv("JOBPIPE_RESUME_TARGET_BASENAME", "Targeted_Resume"),
            resume_pdflatex_command=getenv("JOBPIPE_PDFLATEX_COMMAND", "pdflatex"),
            resume_compile_retries=_as_int(getenv("JOBPIPE_RESUME_COMPILE_RETRIES"), 2),
            resume_compile_timeout_seconds=_as_int(
                getenv("JOBPIPE_RESUME_COMPILE_TIMEOUT_SECONDS"),
                120,
            ),
            resume_write_retries=_as_int(getenv("JOBPIPE_RESUME_WRITE_RETRIES"), 2),
            hiringcafe_base_url=getenv("JOBPIPE_HIRINGCAFE_BASE_URL", "https://hiring.cafe"),
            hiringcafe_search_urls=_split_multi_value(
                getenv("JOBPIPE_HIRINGCAFE_SEARCH_URLS"),
                [],
            ),
            hiringcafe_storage_state=Path(
                getenv(
                    "JOBPIPE_HIRINGCAFE_STORAGE_STATE",
                    "data/session/hiringcafe_storage_state.json",
                )
            ),
            hiringcafe_headless=_as_bool(getenv("JOBPIPE_HIRINGCAFE_HEADLESS"), True),
            hiringcafe_jitter_min=_as_float(getenv("JOBPIPE_HIRINGCAFE_JITTER_MIN"), 1.5),
            hiringcafe_jitter_max=_as_float(getenv("JOBPIPE_HIRINGCAFE_JITTER_MAX"), 3.5),
            hiringcafe_fetch_detail_descriptions=_as_bool(
                getenv("JOBPIPE_HIRINGCAFE_FETCH_DETAILS"),
                True,
            ),
            wellfound_enabled=_as_bool(getenv("JOBPIPE_WELLFOUND_ENABLED"), False),
            wellfound_base_url=getenv("JOBPIPE_WELLFOUND_BASE_URL", "https://wellfound.com"),
            wellfound_search_urls=_split_multi_value(
                getenv("JOBPIPE_WELLFOUND_SEARCH_URLS"),
                [],
            ),
            wellfound_storage_state=Path(
                getenv(
                    "JOBPIPE_WELLFOUND_STORAGE_STATE",
                    "data/session/wellfound_storage_state.json",
                )
            ),
            wellfound_headless=_as_bool(getenv("JOBPIPE_WELLFOUND_HEADLESS"), True),
            wellfound_jitter_min=_as_float(getenv("JOBPIPE_WELLFOUND_JITTER_MIN"), 1.5),
            wellfound_jitter_max=_as_float(getenv("JOBPIPE_WELLFOUND_JITTER_MAX"), 3.5),
            wellfound_fetch_detail_descriptions=_as_bool(
                getenv("JOBPIPE_WELLFOUND_FETCH_DETAILS"),
                True,
            ),
            builtin_enabled=_as_bool(getenv("JOBPIPE_BUILTIN_ENABLED"), False),
            builtin_base_url=getenv("JOBPIPE_BUILTIN_BASE_URL", "https://builtin.com"),
            builtin_search_urls=_split_multi_value(
                getenv("JOBPIPE_BUILTIN_SEARCH_URLS"),
                [],
            ),
            builtin_storage_state=Path(
                getenv(
                    "JOBPIPE_BUILTIN_STORAGE_STATE",
                    "data/session/builtin_storage_state.json",
                )
            ),
            builtin_headless=_as_bool(getenv("JOBPIPE_BUILTIN_HEADLESS"), True),
            builtin_jitter_min=_as_float(getenv("JOBPIPE_BUILTIN_JITTER_MIN"), 1.5),
            builtin_jitter_max=_as_float(getenv("JOBPIPE_BUILTIN_JITTER_MAX"), 3.5),
            builtin_fetch_detail_descriptions=_as_bool(
                getenv("JOBPIPE_BUILTIN_FETCH_DETAILS"),
                True,
            ),
            user_agents=_split_multi_value(
                getenv("JOBPIPE_USER_AGENTS"),
                _DEFAULT_ROTATING_USER_AGENTS,
            ),
            hiringcafe_user_agents=_split_multi_value(
                getenv("JOBPIPE_HIRINGCAFE_USER_AGENTS"),
                [],
            ),
            wellfound_user_agents=_split_multi_value(
                getenv("JOBPIPE_WELLFOUND_USER_AGENTS"),
                [],
            ),
            builtin_user_agents=_split_multi_value(
                getenv("JOBPIPE_BUILTIN_USER_AGENTS"),
                [],
            ),
            critical_skills=_split_csv(getenv("JOBPIPE_CRITICAL_SKILLS"), ["python"]),
            reject_terms=_split_csv(
                getenv("JOBPIPE_REJECT_TERMS"), ["senior", "staff", "principal"]
            ),
            user_years_experience=_as_int(getenv("JOBPIPE_USER_YEARS_EXPERIENCE"), 1),
            notification_threshold=_as_float(getenv("JOBPIPE_NOTIFICATION_THRESHOLD"), 0.80),
            auto_stage_job_description=_as_bool(
                getenv("JOBPIPE_AUTO_STAGE_JOB_DESCRIPTION"),
                False,
            ),
            embed_model=getenv("JOBPIPE_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2"),
            require_usable_auth_state=_as_bool(
                getenv("JOBPIPE_REQUIRE_USABLE_AUTH_STATE"),
                False,
            ),
            schedule_interval_hours=_as_int(getenv("JOBPIPE_SCHEDULE_INTERVAL_HOURS"), 2),
            run_lock_path=Path(getenv("JOBPIPE_RUN_LOCK_PATH", "data/runtime/aggregator.lock")),
            run_lock_stale_seconds=_as_int(getenv("JOBPIPE_RUN_LOCK_STALE_SECONDS"), 21600),
        )

    def ensure_runtime_dirs(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.job_description_path.parent.mkdir(parents=True, exist_ok=True)
        self.resume_output_dir.mkdir(parents=True, exist_ok=True)
        self.hiringcafe_storage_state.parent.mkdir(parents=True, exist_ok=True)
        self.wellfound_storage_state.parent.mkdir(parents=True, exist_ok=True)
        self.builtin_storage_state.parent.mkdir(parents=True, exist_ok=True)
        self.run_lock_path.parent.mkdir(parents=True, exist_ok=True)

    def platform_base_url(self, platform: str) -> str:
        normalized = platform.strip().lower()
        if normalized == "hiringcafe":
            return self.hiringcafe_base_url
        if normalized == "wellfound":
            return self.wellfound_base_url
        if normalized == "builtin":
            return self.builtin_base_url

        raise ValueError(f"Unsupported platform: {platform}")

    def platform_storage_state(self, platform: str) -> Path:
        normalized = platform.strip().lower()
        if normalized == "hiringcafe":
            return self.hiringcafe_storage_state
        if normalized == "wellfound":
            return self.wellfound_storage_state
        if normalized == "builtin":
            return self.builtin_storage_state

        raise ValueError(f"Unsupported platform: {platform}")

    def platform_user_agents(self, platform: str) -> list[str]:
        normalized = platform.strip().lower()
        default_pool = self.user_agents or list(_DEFAULT_ROTATING_USER_AGENTS)

        if normalized == "hiringcafe":
            return list(self.hiringcafe_user_agents or default_pool)
        if normalized == "wellfound":
            return list(self.wellfound_user_agents or default_pool)
        if normalized == "builtin":
            return list(self.builtin_user_agents or default_pool)

        raise ValueError(f"Unsupported platform: {platform}")

    def platform_search_urls(self, platform: str) -> list[str]:
        normalized = platform.strip().lower()
        if normalized == "hiringcafe":
            return self.hiringcafe_search_urls
        if normalized == "wellfound":
            return self.wellfound_search_urls
        if normalized == "builtin":
            return self.builtin_search_urls

        raise ValueError(f"Unsupported platform: {platform}")

    def validate_scraping_runtime(self) -> None:
        errors: list[str] = []

        if not 0.0 <= self.notification_threshold <= 1.0:
            errors.append(
                (
                    "JOBPIPE_NOTIFICATION_THRESHOLD must be within [0, 1] "
                    f"(received: {self.notification_threshold})"
                )
            )

        if self.user_years_experience < 0:
            errors.append(
                (
                    "JOBPIPE_USER_YEARS_EXPERIENCE must be >= 0 "
                    f"(received: {self.user_years_experience})"
                )
            )

        if self.schedule_interval_hours < 1:
            errors.append(
                (
                    "JOBPIPE_SCHEDULE_INTERVAL_HOURS must be >= 1 "
                    f"(received: {self.schedule_interval_hours})"
                )
            )

        if self.run_lock_stale_seconds < 0:
            errors.append(
                (
                    "JOBPIPE_RUN_LOCK_STALE_SECONDS must be >= 0 "
                    f"(received: {self.run_lock_stale_seconds})"
                )
            )

        platform_runtime = [
            (
                "hiringcafe",
                True,
                self.hiringcafe_base_url,
                self.hiringcafe_jitter_min,
                self.hiringcafe_jitter_max,
            ),
            (
                "wellfound",
                self.wellfound_enabled,
                self.wellfound_base_url,
                self.wellfound_jitter_min,
                self.wellfound_jitter_max,
            ),
            (
                "builtin",
                self.builtin_enabled,
                self.builtin_base_url,
                self.builtin_jitter_min,
                self.builtin_jitter_max,
            ),
        ]

        for platform, enabled, base_url, jitter_min, jitter_max in platform_runtime:
            if not enabled:
                continue

            if not _is_valid_http_url(base_url):
                errors.append(
                    f"{platform} base URL must be a valid HTTP/HTTPS URL (received: {base_url})"
                )

            if jitter_min < 0 or jitter_max < 0:
                errors.append(
                    (
                        f"{platform} jitter bounds must be >= 0 "
                        f"(received min={jitter_min}, max={jitter_max})"
                    )
                )
            elif jitter_min > jitter_max:
                errors.append(
                    (
                        f"{platform} jitter min must be <= max "
                        f"(received min={jitter_min}, max={jitter_max})"
                    )
                )

            if not self.platform_user_agents(platform):
                errors.append(f"{platform} user-agent pool must not be empty")

        if errors:
            detail = "\n".join(f"- {item}" for item in errors)
            raise InvalidSettingsError(
                "Invalid JobPipe scraping runtime configuration:\n"
                f"{detail}"
            )

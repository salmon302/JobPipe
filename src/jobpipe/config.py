# Purpose: Load and validate JobPipe runtime settings.
# Author: Seth Nenninger (GPT-5.2-Codex Agent)
# Timestamp: 2026-05-12T00:00:00Z
# Changelog: Replace scraper settings with ingest server configuration.

from __future__ import annotations

from dataclasses import dataclass
from os import environ, getenv
from pathlib import Path


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


def _as_port(value: str | None, default: int) -> int:
    if value is None:
        return default
    return int(value)


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
    ingest_host: str
    ingest_port: int
    ingest_max_payload_bytes: int
    critical_skills: list[str]
    reject_terms: list[str]
    user_years_experience: int
    notification_threshold: float
    auto_stage_job_description: bool
    embed_model: str
    embed_batch_size: int
    score_async: bool
    run_lock_path: Path
    run_lock_stale_seconds: int
    # Scoring weights (Phase 2)
    relevance_weight: float = 0.5
    attainability_weight: float = 0.3
    recency_weight: float = 0.2
    # Section weights for relevance
    skills_section_weight: float = 0.4
    experience_section_weight: float = 0.3
    education_section_weight: float = 0.2
    projects_section_weight: float = 0.1
    # Attainability factors
    user_education: str | None = None
    user_skills: list[str] = None
    remote_preference: bool | None = None
    # Gemini API settings
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-1.5-flash"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_timeout_seconds: int = 60
    gemini_max_retries: int = 3
    gemini_retry_delay_seconds: float = 1.0
    # Resume variant system settings
    resume_variants_dir: Path = Path("data/resume_variants")
    ats_optimization_model: str = "gemini-1.5-flash"
    master_cv_hash_algorithm: str = "sha256"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            db_path=Path(getenv("JOBPIPE_DB_PATH", "data/jobpipe.db")),
            master_cv_path=Path(getenv("JOBPIPE_MASTER_CV_PATH", "Master_CV.md")),
            job_description_path=Path(
                getenv("JOBPIPE_JOB_DESCRIPTION_PATH", "Job_Description.md")
            ),
            resume_output_dir=Path(getenv("JOBPIPE_RESUME_OUTPUT_DIR", "data/resume")),
            resume_target_basename=getenv(
                "JOBPIPE_RESUME_TARGET_BASENAME",
                "Targeted_Resume",
            ),
            resume_pdflatex_command=getenv("JOBPIPE_PDFLATEX_COMMAND", "pdflatex"),
            resume_compile_retries=_as_int(getenv("JOBPIPE_RESUME_COMPILE_RETRIES"), 2),
            resume_compile_timeout_seconds=_as_int(
                getenv("JOBPIPE_RESUME_COMPILE_TIMEOUT_SECONDS"),
                120,
            ),
            resume_write_retries=_as_int(getenv("JOBPIPE_RESUME_WRITE_RETRIES"), 2),
            ingest_host=getenv("JOBPIPE_INGEST_HOST", "127.0.0.1"),
            ingest_port=_as_port(getenv("JOBPIPE_INGEST_PORT"), 3838),
            ingest_max_payload_bytes=_as_int(
                getenv("JOBPIPE_INGEST_MAX_PAYLOAD_BYTES"),
                1_000_000,
            ),
            critical_skills=_split_csv(getenv("JOBPIPE_CRITICAL_SKILLS"), []),
            reject_terms=_split_csv(
                getenv("JOBPIPE_REJECT_TERMS"), ["senior", "staff", "principal"]
            ),
            user_years_experience=_as_int(getenv("JOBPIPE_USER_YEARS_EXPERIENCE"), 1),
            notification_threshold=_as_float(
                getenv("JOBPIPE_NOTIFICATION_THRESHOLD"),
                0.80,
            ),
            auto_stage_job_description=_as_bool(
                getenv("JOBPIPE_AUTO_STAGE_JOB_DESCRIPTION"),
                False,
            ),
            embed_model=getenv(
                "JOBPIPE_EMBED_MODEL",
                "sentence-transformers/all-MiniLM-L6-v2",
            ),
            embed_batch_size=_as_int(getenv("JOBPIPE_EMBED_BATCH_SIZE"), 32),
            score_async=_as_bool(getenv("JOBPIPE_SCORE_ASYNC"), False),
            relevance_weight=_as_float(getenv("JOBPIPE_RELEVANCE_WEIGHT"), 0.5),
            attainability_weight=_as_float(getenv("JOBPIPE_ATTAINABILITY_WEIGHT"), 0.3),
            recency_weight=_as_float(getenv("JOBPIPE_RECENCY_WEIGHT"), 0.2),
            skills_section_weight=_as_float(getenv("JOBPIPE_SKILLS_SECTION_WEIGHT"), 0.4),
            experience_section_weight=_as_float(getenv("JOBPIPE_EXPERIENCE_SECTION_WEIGHT"), 0.3),
            education_section_weight=_as_float(getenv("JOBPIPE_EDUCATION_SECTION_WEIGHT"), 0.2),
            projects_section_weight=_as_float(getenv("JOBPIPE_PROJECTS_SECTION_WEIGHT"), 0.1),
            user_education=getenv("JOBPIPE_USER_EDUCATION", None),
            user_skills=_split_csv(getenv("JOBPIPE_USER_SKILLS"), []),
            remote_preference=_as_bool(getenv("JOBPIPE_REMOTE_PREFERENCE"), None),
            run_lock_path=Path(
                getenv("JOBPIPE_RUN_LOCK_PATH", "data/runtime/aggregator.lock")
            ),
            run_lock_stale_seconds=_as_int(
                getenv("JOBPIPE_RUN_LOCK_STALE_SECONDS"),
                21600,
            ),
            # Gemini API settings
            gemini_api_key=getenv("JOBPIPE_GEMINI_API_KEY") or None,
            gemini_model=getenv("JOBPIPE_GEMINI_MODEL", "gemini-1.5-flash"),
            gemini_base_url=getenv(
                "JOBPIPE_GEMINI_BASE_URL",
                "https://generativelanguage.googleapis.com/v1beta",
            ),
            gemini_timeout_seconds=_as_int(
                getenv("JOBPIPE_GEMINI_TIMEOUT_SECONDS"),
                60,
            ),
            gemini_max_retries=_as_int(
                getenv("JOBPIPE_GEMINI_MAX_RETRIES"),
                3,
            ),
            gemini_retry_delay_seconds=_as_float(
                getenv("JOBPIPE_GEMINI_RETRY_DELAY_SECONDS"),
                1.0,
            ),
        )

    def ensure_runtime_dirs(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.job_description_path.parent.mkdir(parents=True, exist_ok=True)
        self.resume_output_dir.mkdir(parents=True, exist_ok=True)
        self.run_lock_path.parent.mkdir(parents=True, exist_ok=True)

    def validate_runtime(self) -> None:
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

        if self.run_lock_stale_seconds < 0:
            errors.append(
                (
                    "JOBPIPE_RUN_LOCK_STALE_SECONDS must be >= 0 "
                    f"(received: {self.run_lock_stale_seconds})"
                )
            )

        if self.embed_batch_size <= 0:
            errors.append(
                (
                    "JOBPIPE_EMBED_BATCH_SIZE must be > 0 "
                    f"(received: {self.embed_batch_size})"
                )
            )

        if not self.ingest_host.strip():
            errors.append("JOBPIPE_INGEST_HOST must not be empty")

        if not 1 <= self.ingest_port <= 65535:
            errors.append(
                (
                    "JOBPIPE_INGEST_PORT must be within [1, 65535] "
                    f"(received: {self.ingest_port})"
                )
            )

        if self.ingest_max_payload_bytes <= 0:
            errors.append(
                (
                    "JOBPIPE_INGEST_MAX_PAYLOAD_BYTES must be > 0 "
                    f"(received: {self.ingest_max_payload_bytes})"
                )
            )

        if errors:
            detail = "\n".join(f"- {item}" for item in errors)
            raise InvalidSettingsError(
                "Invalid JobPipe runtime configuration:\n"
                f"{detail}"
            )

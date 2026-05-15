# Purpose: Provide GUI-facing services for ingest, dashboard, and resume actions.
# Author: Seth Nenninger (GPT-5.2-Codex Agent)
# Timestamp: 2026-05-12T00:00:00Z
# Changelog: Remove scheduler/auth services and add ingest server helpers.

from __future__ import annotations

from dataclasses import dataclass
from os import environ
from pathlib import Path

from jobpipe.config import InvalidSettingsError, Settings
from jobpipe.ingest.server import IngestServer, IngestServerConfig
from jobpipe.ingest.service import JobIngestService
from jobpipe.resume.compiler import LatexCompileConfig, LatexCompileResult, compile_latex
from jobpipe.resume.staging import ResumeTargetNotFoundError, StagedJobDescription, stage_job_description
from jobpipe.storage.db import connect, initialize_database
from jobpipe.storage.models import JobRecord, NotificationAuditRecord, ScrapeRunRecord
from jobpipe.storage.repository import JobRepository


_EDITABLE_ENV_KEYS = (
    "JOBPIPE_NOTIFICATION_THRESHOLD",
    "JOBPIPE_USER_YEARS_EXPERIENCE",
    "JOBPIPE_AUTO_STAGE_JOB_DESCRIPTION",
    "JOBPIPE_INGEST_HOST",
    "JOBPIPE_INGEST_PORT",
    "JOBPIPE_INGEST_MAX_PAYLOAD_BYTES",
    "JOBPIPE_CRITICAL_SKILLS",
    "JOBPIPE_REJECT_TERMS",
    "JOBPIPE_EMBED_BATCH_SIZE",
    "JOBPIPE_SCORE_ASYNC",
)


@dataclass(frozen=True)
class DashboardSnapshot:
    total_jobs: int
    queued_jobs: int
    notified_jobs: int
    above_threshold_jobs: int
    last_run: ScrapeRunRecord | None


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

    def ingest_endpoint(self) -> str:
        return f"http://{self._settings.ingest_host}:{self._settings.ingest_port}"

    def create_ingest_server(
        self,
        host: str | None = None,
        port: int | None = None,
    ) -> IngestServer:
        config = IngestServerConfig(
            host=host or self._settings.ingest_host,
            port=port or self._settings.ingest_port,
            max_payload_bytes=self._settings.ingest_max_payload_bytes,
        )
        service = JobIngestService(self._settings)
        return IngestServer(config=config, service=service)

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

        return DashboardSnapshot(
            total_jobs=int(row["total_jobs"] or 0),
            queued_jobs=int(row["queued_jobs"] or 0),
            notified_jobs=int(row["notified_jobs"] or 0),
            above_threshold_jobs=int(row["above_threshold_jobs"] or 0),
            last_run=recent_runs[0] if recent_runs else None,
        )

    def list_top_jobs(self, limit: int = 100) -> list[JobRecord]:
        self._prepare()
        repository = self._repository()
        return repository.list_top_jobs(limit=limit)

    def list_jobs(
        self,
        limit: int = 200,
        search_query: str | None = None,
    ) -> list[JobRecord]:
        self._prepare()
        repository = self._repository()
        return repository.list_jobs(limit=limit, search_query=search_query)

    def get_job_by_id(self, job_id: str) -> JobRecord | None:
        self._prepare()
        repository = self._repository()
        return repository.get_job_by_id(job_id)

    def get_jobs_and_companies_count(self) -> tuple[int, int]:
        """Return (unique_job_count, unique_company_count)."""
        self._prepare()
        with connect(self._settings.db_path) as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS job_count,
                    COUNT(DISTINCT company) AS company_count
                FROM jobs
                """
            ).fetchone()
            return int(row["job_count"] or 0), int(row["company_count"] or 0)

    def clear_jobs(self) -> int:
        """Clear all jobs from the database. Returns the number of deleted jobs."""
        self._prepare()
        repository = self._repository()
        return repository.clear_jobs()

    def list_recent_runs(self, limit: int = 100) -> list[ScrapeRunRecord]:
        self._prepare()
        repository = self._repository()
        return repository.list_recent_runs(limit=limit)

    def list_recent_notifications(
        self,
        limit: int = 100,
    ) -> list[NotificationAuditRecord]:
        self._prepare()
        repository = self._repository()
        return repository.list_recent_notifications(limit=limit)

    def rescore_all_jobs(self) -> int:
        """Re-score all jobs using current Master CV. Returns number of jobs scored."""
        from jobpipe.pipeline import score_pending_jobs
        from jobpipe.storage.models import ScrapeRunRecord

        self._prepare()
        repository = self._repository()

        # Create a dummy run_id for scoring
        run_id = "gui-rescore"

        # Reset scores to None so they get re-scored
        with connect(self._settings.db_path) as conn:
            conn.execute("UPDATE jobs SET match_score = NULL WHERE match_score IS NOT NULL")
            conn.commit()

        # Run scoring
        summary = score_pending_jobs(
            settings=self._settings,
            repository=repository,
            run_id=run_id,
            limit=1000,
        )

        return summary.scored

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

        threshold = (
            self._settings.notification_threshold
            if minimum_score is None
            else minimum_score
        )
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

    def approve_and_compile_resume(
        self,
        tex_path: Path | None = None,
    ) -> LatexCompileResult:
        """Approve the LaTeX content and compile to PDF (REQ-3.4).

        This method is called after the user reviews and approves the LaTeX
        in the GUI editor. It writes the approved content and compiles.

        Args:
            tex_path: Path to the .tex file (defaults to configured basename)

        Returns:
            LatexCompileResult with paths and attempt count
        """
        from jobpipe.resume.service import (
            ApprovalRequiredError,
            write_targeted_resume,
        )

        self._prepare()
        target_tex = tex_path or self.default_resume_tex_path()

        # Read the LaTeX content (already saved by the GUI before calling this)
        if not target_tex.exists():
            raise FileNotFoundError(f"TeX file not found: {target_tex}")

        latex_content = target_tex.read_text(encoding="utf-8")

        # Use write_targeted_resume with approved=True
        # This will compile the PDF
        output_dir = target_tex.parent
        base_name = target_tex.stem  # filename without extension

        config = LatexCompileConfig(
            pdflatex_command=self._settings.resume_pdflatex_command,
            retries=self._settings.resume_compile_retries,
            timeout_seconds=self._settings.resume_compile_timeout_seconds,
        )

        result = write_targeted_resume(
            tex_content=latex_content,
            output_name=base_name,
            output_dir=output_dir,
            compile_config=config,
            approved=True,  # User has approved
            write_retries=self._settings.resume_write_retries,
            default_base_name=self._settings.resume_target_basename,
        )

        return LatexCompileResult(
            tex_path=result.tex_path,
            pdf_path=result.pdf_path,
            attempts=result.compile_attempts,
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
            candidate.validate_runtime()
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
            "JOBPIPE_AUTO_STAGE_JOB_DESCRIPTION": str(
                self._settings.auto_stage_job_description
            ).lower(),
            "JOBPIPE_INGEST_HOST": self._settings.ingest_host,
            "JOBPIPE_INGEST_PORT": str(self._settings.ingest_port),
            "JOBPIPE_INGEST_MAX_PAYLOAD_BYTES": str(self._settings.ingest_max_payload_bytes),
            "JOBPIPE_CRITICAL_SKILLS": ",".join(self._settings.critical_skills),
            "JOBPIPE_REJECT_TERMS": ",".join(self._settings.reject_terms),
            "JOBPIPE_EMBED_BATCH_SIZE": str(self._settings.embed_batch_size),
            "JOBPIPE_SCORE_ASYNC": str(self._settings.score_async).lower(),
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

    # -------------------------------------------------------------------------
    # Resume Variants Management
    # -------------------------------------------------------------------------
    def list_resume_variants(
        self,
        job_id: str | None = None,
        target_company: str | None = None,
        job_type: str | None = None,
        page_length: int | None = None,
        master_cv_hash: str | None = None,
        ats_optimized: bool | None = None,
        limit: int = 100,
    ) -> list:
        """List resume variants with optional filters."""
        self._prepare()
        repository = self._repository()
        return repository.list_resume_variants(
            job_id=job_id,
            target_company=target_company,
            job_type=job_type,
            page_length=page_length,
            master_cv_hash=master_cv_hash,
            ats_optimized=ats_optimized,
            limit=limit,
        )

    def get_variant_lineage(self, variant_id: int) -> list:
        """Get the full lineage (parent chain) of a variant."""
        self._prepare()
        repository = self._repository()
        return repository.get_variant_lineage(variant_id)

    def get_variants_by_job(self, job_id: str) -> list:
        """Get all variants for a specific job."""
        self._prepare()
        repository = self._repository()
        return repository.get_variants_by_job(job_id)

    def get_variant_by_id(self, variant_id: int):
        """Get a specific variant by ID."""
        self._prepare()
        repository = self._repository()
        return repository.get_resume_variant(variant_id)

    def ats_optimize_variant(
        self,
        variant_id: int,
        job_description: str | None = None,
    ) -> dict:
        """Optimize a resume variant for ATS compatibility."""
        from jobpipe.resume.service import ats_optimize_resume

        self._prepare()
        repository = self._repository()

        variant = repository.get_resume_variant(variant_id)
        if variant is None:
            raise ValueError(f"Variant {variant_id} not found")

        # Read the LaTeX content
        tex_path = Path(variant.tex_path)
        if not tex_path.exists():
            raise FileNotFoundError(f"TeX file not found: {tex_path}")

        tex_content = tex_path.read_text(encoding="utf-8")

        # Get job description if not provided
        if job_description is None and variant.job_id:
            job = repository.select_resume_target_job(0.0, variant.job_id)
            if job:
                job_description = job.description

        if job_description is None:
            raise ValueError("Job description is required for ATS optimization")

        # Run ATS optimization
        result = ats_optimize_resume(
            tex_content=tex_content,
            job_description=job_description,
            gemini_api_key=self._settings.gemini_api_key,
            gemini_model=self._settings.ats_optimization_model,
            gemini_base_url=self._settings.gemini_base_url,
        )

        # Update variant with ATS results
        pdf_path = None
        if "optimized_content" in result and result["optimized_content"] != tex_content:
            # Write optimized content
            optimized_path = tex_path.with_stem(tex_path.stem + "_ats_optimized")
            optimized_path.write_text(result["optimized_content"], encoding="utf-8")

            # Compile optimized version
            config = LatexCompileConfig(
                pdflatex_command=self._settings.resume_pdflatex_command,
                retries=self._settings.resume_compile_retries,
                timeout_seconds=self._settings.resume_compile_timeout_seconds,
            )
            compile_result = compile_latex(
                tex_path=optimized_path,
                output_pdf_path=optimized_path.with_suffix(".pdf"),
                config=config,
            )
            pdf_path = str(compile_result.pdf_path)

        # Update variant record
        repository.update_resume_variant(
            variant_id=variant_id,
            pdf_path=pdf_path,
            ats_optimized=True,
            ats_score=result.get("ats_score"),
        )

        return result

    def ats_optimize_all_for_role(
        self,
        job_id: str | None = None,
        target_company: str | None = None,
    ) -> dict:
        """Optimize all resume variants for a specific role/company."""
        self._prepare()
        repository = self._repository()

        # Get all variants for this role/company
        variants = repository.list_resume_variants(
            job_id=job_id,
            target_company=target_company,
            limit=1000,
        )

        results = {
            "total": len(variants),
            "optimized": 0,
            "failed": 0,
            "details": [],
        }

        for variant in variants:
            try:
                result = self.ats_optimize_variant(
                    variant_id=variant.id,
                    job_description=None,  # Will be fetched from job_id
                )
                results["optimized"] += 1
                results["details"].append({
                    "variant_id": variant.id,
                    "variant_name": variant.variant_name,
                    "ats_score": result.get("ats_score"),
                    "status": "success",
                })
            except Exception as exc:
                results["failed"] += 1
                results["details"].append({
                    "variant_id": variant.id,
                    "variant_name": variant.variant_name,
                    "error": str(exc),
                    "status": "failed",
                })

        return results

    def list_master_cv_versions(self, limit: int = 50) -> list:
        """List all Master CV versions."""
        self._prepare()
        repository = self._repository()
        return repository.list_cv_versions(limit=limit)

    def compute_current_cv_hash(self) -> str:
        """Compute hash of current Master CV file."""
        from jobpipe.resume.service import compute_master_cv_hash

        return compute_master_cv_hash(self._settings.master_cv_path)

    # -------------------------------------------------------------------------
    # Job Enrichment Polling
    # -------------------------------------------------------------------------
    def poll_job_enrichment(self, job_id: str) -> bool:
        """Check if a job has been enriched with a substantive description.

        After opening a job URL in the browser, the extension auto-scrapes
        and enriches the detail page. This method checks if the description
        is now >200 characters (indicating enrichment succeeded).

        Args:
            job_id: The job ID to check.

        Returns:
            True if the job has a substantive description, False otherwise.
        """
        self._prepare()
        repository = self._repository()
        job = repository.get_job_by_id(job_id)
        if job is None:
            return False
        return bool(job.description and len(job.description.strip()) > 200)

    # -------------------------------------------------------------------------
    # AI Recommendations
    # -------------------------------------------------------------------------

    def generate_ai_recommendations(self, top_jobs: list[JobRecord]) -> str:
        """Generate AI recommendations for job application priorities.

        Uses Gemini API to analyze top-scoring jobs against the Master CV
        and provide concise application priorities.

        Args:
            top_jobs: List of top-scoring JobRecord objects (top 20%).

        Returns:
            AI-generated recommendation text.

        Raises:
            RuntimeError: If Gemini key is not configured or generation fails.
        """
        from jobpipe.resume.gemini_client import (
            GeminiAPIError,
            GeminiClient,
            create_gemini_client_from_settings,
        )

        # Read Master CV
        if not self._settings.master_cv_path.exists():
            raise RuntimeError(f"Master CV not found at: {self._settings.master_cv_path}")

        master_cv = self._settings.master_cv_path.read_text(encoding="utf-8")

        # Build job summaries for the prompt (keep it concise)
        job_summaries = []
        for i, job in enumerate(top_jobs[:15], 1):  # Limit to 15 jobs max for prompt size
            summary = f"""
Job {i}:
- Title: {job.title}
- Company: {job.company}
- Score: {job.match_score:.3f} (Rel: {job.score_relevance or 'n/a'}, Att: {job.score_attainability or 'n/a'})
- Description: {job.description[:200]}...""" if job.description else "- Description: N/A"
            job_summaries.append(summary)

        jobs_text = "\n".join(job_summaries)

        # Build the prompt
        prompt = f"""You are an expert career advisor and job search strategist.

## Task
Analyze the following top-scoring jobs (top 20% by match score) against the candidate's Master CV.
Provide CONCISE, ACTIONABLE application priorities in 200-300 words.

## Guidelines
- List 3-5 prioritized action items (bullet points)
- Focus on: which jobs to apply first, why, and any gaps to address
- Be specific about job titles and companies
- Consider: match score, skills alignment, experience fit
- Keep it under 300 words total

## Master CV:
{master_cv[:2000]}  # Truncate to stay within token limits

## Top Jobs to Prioritize:
{jobs_text}

## Output Format
Provide a brief intro (1 sentence), then bullet points with priorities. Be concise and specific."""

        # Create Gemini client and generate text
        try:
            client = create_gemini_client_from_settings(self._settings)
            return client.generate_text(prompt, temperature=0.3, max_output_tokens=1024)
        except GeminiAPIError as exc:
            raise RuntimeError(f"AI recommendation failed: {exc}") from exc

    # -------------------------------------------------------------------------
    # AI Resume Generation (direct from GUI)
    # -------------------------------------------------------------------------
    def generate_resume_content(
        self,
        job_id: str,
        max_pages: str = "1",
    ) -> dict:
        """Generate a targeted LaTeX resume for a specific job via Gemini API.

        This is the full pipeline:
        1. Stage the job description for the given job_id
        2. Read Master CV
        3. Call Gemini API to generate LaTeX
        4. Save to output directory
        5. Return paths to the generated files

        Args:
            job_id: The job ID to generate a resume for.
            max_pages: "1" for one page, "half" for a compact half-page resume.

        Returns:
            Dict with 'tex_path', 'pdf_path', 'title', 'company', 'status'.

        Raises:
            RuntimeError: If Gemini key is not configured or generation fails.
            ResumeTargetNotFoundError: If job is not found or not eligible.
        """
        from jobpipe.resume.gemini_client import (
            GeminiAPIError,
            create_gemini_client_from_settings,
        )
        from jobpipe.resume.service import (
            ApprovalRequiredError,
            write_targeted_resume,
        )

        self._prepare()
        repository = self._repository()

        # 1. Get the job record
        job = repository.get_job_by_id(job_id)
        if job is None:
            raise ResumeTargetNotFoundError(f"Job not found: {job_id}")

        # 2. Stage the job description to a markdown file
        staged = stage_job_description(
            repository=repository,
            output_path=self._settings.job_description_path,
            minimum_score=0.0,  # No score threshold for explicit job_id
            job_id=job_id,
        )

        # 3. Read Master CV
        if not self._settings.master_cv_path.exists():
            raise FileNotFoundError(
                f"Master CV not found at: {self._settings.master_cv_path}"
            )
        master_cv = self._settings.master_cv_path.read_text(encoding="utf-8")
        if not master_cv.strip():
            raise RuntimeError(f"Master CV is empty at: {self._settings.master_cv_path}")

        # 4. Read the staged job description
        job_description = staged.output_path.read_text(encoding="utf-8")

        # 5. Call Gemini API
        if not self._settings.gemini_api_key:
            raise RuntimeError(
                "Gemini API key not configured. Set JOBPIPE_GEMINI_API_KEY in .env"
            )

        client = create_gemini_client_from_settings(self._settings)
        try:
            response = client.generate_resume(
                master_cv=master_cv,
                job_description=job_description,
                max_pages=max_pages,
            )
        except GeminiAPIError as exc:
            raise RuntimeError(f"Gemini API error: {exc}") from exc

        # 6. Determine output path with company/title directory structure
        safe_company = "".join(c if c.isalnum() or c in " _-" else "_" for c in job.company).strip()
        safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in job.title).strip()
        page_suffix = "_half" if max_pages == "half" else ""
        output_dir = self._settings.resume_output_dir / f"{safe_company}_{safe_title[:40]}"
        output_dir.mkdir(parents=True, exist_ok=True)

        tex_filename = f"resume{page_suffix}.tex"
        tex_path = output_dir / tex_filename

        # 7. Save LaTeX to file
        tex_path.write_text(response.text, encoding="utf-8")

        # Update the resume tex_path input in settings
        self._settings.resume_target_basename = tex_filename.replace(".tex", "")

        return {
            "tex_path": str(tex_path),
            "title": job.title,
            "company": job.company,
            "job_id": job.id,
            "status": "generated",
            "message": f"Resume generated for {job.title} at {job.company}. Review and compile.",
        }

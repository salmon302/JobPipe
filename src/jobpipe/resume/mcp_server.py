from __future__ import annotations

import importlib
from pathlib import Path

from jobpipe.config import Settings
from jobpipe.resume.compiler import LatexCompileConfig, compile_latex
from jobpipe.resume.service import (
    ApprovalRequiredError,
    write_targeted_resume as write_targeted_resume_document,
)
from jobpipe.resume.staging import ResumeTargetNotFoundError, stage_job_description
from jobpipe.storage.repository import JobRepository

try:
    _fastmcp_module = importlib.import_module("mcp.server.fastmcp")
    FastMCP = getattr(_fastmcp_module, "FastMCP")
except (ImportError, ModuleNotFoundError, AttributeError):
    FastMCP = None


RESUME_SKILL_TEMPLATE = """# JobPipe Resume Skill Template

Goal:
- Produce a targeted, one-page resume in LaTeX tailored to Job_Description.md.

Constraints:
- Keep claims factual and traceable to Master_CV.md.
- Do not invent projects, metrics, employers, or responsibilities.
- Preserve a concise one-page layout and prioritize impact bullets.
- Emphasize role-relevant skills and recent, matching experience.

Workflow:
1. Read resources: jobpipe://master-cv and jobpipe://job-description.
2. Draft LaTeX output that maps role needs to proven experience.
3. Ask for human diff review before writing.
4. Call write_targeted_resume with approved=true only after review.
"""


def _read_resource(path: Path) -> str:
    if not path.exists():
        return f"Resource is missing at: {path}"

    content = path.read_text(encoding="utf-8")
    if not content.strip():
        return f"Resource exists but is empty at: {path}"

    return content


def create_resume_mcp_server(settings: Settings):
    if FastMCP is None:
        raise RuntimeError(
            "MCP server dependency is missing. Install the `mcp` package to run resume-server."
        )

    settings.ensure_runtime_dirs()

    repository = JobRepository(settings.db_path)
    compile_config = LatexCompileConfig(
        pdflatex_command=settings.resume_pdflatex_command,
        retries=settings.resume_compile_retries,
        timeout_seconds=settings.resume_compile_timeout_seconds,
    )

    server = FastMCP("JobPipe Resume Generator")

    @server.resource("jobpipe://master-cv")
    def read_master_cv() -> str:
        return _read_resource(settings.master_cv_path)

    @server.resource("jobpipe://job-description")
    def read_job_description() -> str:
        return _read_resource(settings.job_description_path)

    @server.resource("jobpipe://resume-skill")
    def read_resume_skill() -> str:
        return RESUME_SKILL_TEMPLATE

    @server.tool()
    def stage_job_description_for_resume(
        job_id: str | None = None,
        minimum_score: float | None = None,
    ) -> dict[str, str]:
        threshold = settings.notification_threshold if minimum_score is None else minimum_score
        staged = stage_job_description(
            repository=repository,
            output_path=settings.job_description_path,
            minimum_score=threshold,
            job_id=job_id,
        )
        return {
            "job_id": staged.job_id,
            "title": staged.title,
            "company": staged.company,
            "score": "n/a" if staged.score is None else f"{staged.score:.3f}",
            "output_path": str(staged.output_path),
        }

    @server.tool()
    def write_targeted_resume(
        tex_content: str,
        output_name: str | None = None,
        approved: bool = False,
    ) -> dict[str, str]:
        name = output_name or settings.resume_target_basename
        result = write_targeted_resume_document(
            tex_content=tex_content,
            output_name=name,
            output_dir=settings.resume_output_dir,
            compile_config=compile_config,
            approved=approved,
            write_retries=settings.resume_write_retries,
            default_base_name=settings.resume_target_basename,
        )
        return {
            "tex_path": str(result.tex_path),
            "pdf_path": str(result.pdf_path),
            "compile_attempts": str(result.compile_attempts),
        }

    @server.tool()
    def compile_existing_resume(output_name: str | None = None) -> dict[str, str]:
        name = output_name or settings.resume_target_basename
        if not name.lower().endswith(".tex"):
            name = f"{name}.tex"

        tex_path = settings.resume_output_dir / name
        result = compile_latex(
            tex_path,
            output_pdf_path=tex_path.with_suffix(".pdf"),
            config=compile_config,
        )
        return {
            "tex_path": str(result.tex_path),
            "pdf_path": str(result.pdf_path),
            "attempts": str(result.attempts),
        }

    @server.tool()
    def healthcheck() -> dict[str, str]:
        return {
            "db_path": str(settings.db_path),
            "master_cv_path": str(settings.master_cv_path),
            "job_description_path": str(settings.job_description_path),
            "resume_output_dir": str(settings.resume_output_dir),
            "notification_threshold": str(settings.notification_threshold),
        }

    # Keep explicit references to custom exceptions so MCP wrappers keep friendly messages.
    _ = (ApprovalRequiredError, ResumeTargetNotFoundError)

    return server


def run_resume_mcp_server(settings: Settings) -> None:
    server = create_resume_mcp_server(settings)
    server.run()

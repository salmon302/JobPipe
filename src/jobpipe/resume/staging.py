from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from jobpipe.storage.models import JobRecord
from jobpipe.storage.repository import JobRepository


class ResumeTargetNotFoundError(RuntimeError):
    pass


@dataclass(frozen=True)
class StagedJobDescription:
    job_id: str
    title: str
    company: str
    score: float | None
    output_path: Path


def _job_to_markdown(job: JobRecord) -> str:
    score_text = "n/a" if job.match_score is None else f"{job.match_score:.3f}"
    remote_text = "n/a" if job.is_remote is None else ("remote" if job.is_remote else "on-site/hybrid")

    lines = [
        "# Job Description",
        "",
        f"- Job ID: {job.id}",
        f"- Platform: {job.platform}",
        f"- Title: {job.title}",
        f"- Company: {job.company}",
        f"- URL: {job.url}",
        f"- Date Posted (UTC): {job.date_posted.isoformat()}",
        f"- Match Score: {score_text}",
        f"- Status: {job.status}",
        f"- Years Required: {job.years_required if job.years_required is not None else 'n/a'}",
        f"- Remote: {remote_text}",
        "",
        "## Raw Description",
        "",
        job.description.strip() or "(No description captured)",
        "",
    ]

    return "\n".join(lines)


def stage_job_description(
    repository: JobRepository,
    output_path: Path,
    minimum_score: float,
    job_id: str | None = None,
) -> StagedJobDescription:
    target = repository.select_resume_target_job(min_score=minimum_score, job_id=job_id)
    if target is None:
        raise ResumeTargetNotFoundError(
            "No eligible job found for resume staging. "
            f"minimum_score={minimum_score:.3f}"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_job_to_markdown(target), encoding="utf-8")

    return StagedJobDescription(
        job_id=target.id,
        title=target.title,
        company=target.company,
        score=target.match_score,
        output_path=output_path,
    )

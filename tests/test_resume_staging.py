from datetime import datetime, timezone

import pytest

from jobpipe.resume.staging import ResumeTargetNotFoundError, stage_job_description
from jobpipe.storage.db import initialize_database
from jobpipe.storage.models import JobRecord
from jobpipe.storage.repository import JobRepository


def test_stage_job_description_selects_top_eligible_job(tmp_path) -> None:
    db_path = tmp_path / "jobpipe.db"
    initialize_database(db_path)
    repo = JobRepository(db_path)

    job_a = JobRecord(
        id="hiringcafe-100",
        platform="HiringCafe",
        title="Backend Engineer",
        company="Acme",
        url="https://hiring.cafe/jobs/100",
        description="Python backend role with APIs",
        date_posted=datetime.now(timezone.utc),
    )
    job_b = JobRecord(
        id="hiringcafe-200",
        platform="HiringCafe",
        title="Data Engineer",
        company="Beta",
        url="https://hiring.cafe/jobs/200",
        description="Data pipelines and SQL",
        date_posted=datetime.now(timezone.utc),
    )

    repo.upsert_jobs([job_a, job_b])
    repo.update_scoring(
        job_id=job_a.id,
        match_score=0.82,
        years_required=2,
        is_remote=True,
        status="Queued",
    )
    repo.update_scoring(
        job_id=job_b.id,
        match_score=0.91,
        years_required=2,
        is_remote=True,
        status="Notified",
    )

    output_path = tmp_path / "Job_Description.md"
    staged = stage_job_description(
        repository=repo,
        output_path=output_path,
        minimum_score=0.80,
    )

    assert staged.job_id == "hiringcafe-200"
    assert output_path.exists() is True
    content = output_path.read_text(encoding="utf-8")
    assert "# Job Description" in content
    assert "Data Engineer" in content
    assert "Raw Description" in content


def test_stage_job_description_raises_when_no_eligible_job(tmp_path) -> None:
    db_path = tmp_path / "jobpipe.db"
    initialize_database(db_path)
    repo = JobRepository(db_path)

    output_path = tmp_path / "Job_Description.md"
    with pytest.raises(ResumeTargetNotFoundError):
        stage_job_description(
            repository=repo,
            output_path=output_path,
            minimum_score=0.90,
        )

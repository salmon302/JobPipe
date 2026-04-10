from __future__ import annotations

from datetime import datetime, timezone

from jobpipe.storage.models import JobRecord


def sample_job() -> JobRecord:
    return JobRecord(
        id="hiringcafe-sample-1",
        platform="HiringCafe",
        title="Backend Software Engineer",
        company="Example Co",
        url="https://hiring.cafe/jobs/example-1",
        description="Python FastAPI SQL AWS role for backend API development.",
        date_posted=datetime.now(timezone.utc),
    )

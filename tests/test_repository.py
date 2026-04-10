from datetime import datetime, timezone

from jobpipe.storage.db import initialize_database
from jobpipe.storage.models import JobRecord
from jobpipe.storage.repository import JobRepository


def test_repository_upsert_and_fetch(tmp_path) -> None:
    db_path = tmp_path / "jobpipe.db"
    initialize_database(db_path)

    repo = JobRepository(db_path)
    job = JobRecord(
        id="hiringcafe-123",
        platform="HiringCafe",
        title="Backend Engineer",
        company="Acme",
        url="https://hiring.cafe/jobs/123",
        description="Python role",
        date_posted=datetime.now(timezone.utc),
    )

    inserted, updated = repo.upsert_jobs([job])
    assert inserted == 1
    assert updated == 0

    pending = repo.list_jobs_for_scoring(limit=10)
    assert len(pending) == 1
    assert pending[0].id == "hiringcafe-123"

    repo.update_scoring(
        job_id=job.id,
        match_score=0.88,
        years_required=2,
        is_remote=True,
        status="Queued",
        score_relevance=0.90,
        score_attainability=0.75,
        score_recency=0.80,
    )

    top = repo.list_top_jobs(limit=10)
    assert len(top) == 1
    assert top[0].match_score == 0.88
    assert top[0].score_relevance == 0.90
    assert top[0].score_attainability == 0.75
    assert top[0].score_recency == 0.80


def test_notification_queue_and_mark_notified(tmp_path) -> None:
    db_path = tmp_path / "jobpipe.db"
    initialize_database(db_path)

    repo = JobRepository(db_path)
    job = JobRecord(
        id="hiringcafe-124",
        platform="HiringCafe",
        title="Python Engineer",
        company="Acme",
        url="https://hiring.cafe/jobs/124",
        description="Python and SQL",
        date_posted=datetime.now(timezone.utc),
    )

    repo.upsert_jobs([job])
    repo.update_scoring(
        job_id=job.id,
        match_score=0.91,
        years_required=2,
        is_remote=True,
        status="Queued",
    )

    pending_notifications = repo.list_jobs_to_notify(threshold=0.8)
    assert len(pending_notifications) == 1
    assert pending_notifications[0].id == job.id

    repo.mark_notified([job.id])

    pending_after_mark = repo.list_jobs_to_notify(threshold=0.8)
    assert pending_after_mark == []


def test_scrape_run_lifecycle_persists_summary(tmp_path) -> None:
    db_path = tmp_path / "jobpipe.db"
    initialize_database(db_path)

    repo = JobRepository(db_path)
    started = datetime(2026, 4, 9, 9, 0, tzinfo=timezone.utc)
    finished = datetime(2026, 4, 9, 9, 10, tzinfo=timezone.utc)

    repo.create_scrape_run(run_id="run-abc", started_at=started)
    repo.complete_scrape_run(
        run_id="run-abc",
        scraped=15,
        inserted=10,
        updated=5,
        scored=12,
        above_threshold=4,
        notified=3,
        finished_at=finished,
    )

    runs = repo.list_recent_runs(limit=5)
    assert len(runs) == 1
    assert runs[0].run_id == "run-abc"
    assert runs[0].status == "Completed"
    assert runs[0].started_at == started
    assert runs[0].finished_at == finished
    assert runs[0].scraped == 15
    assert runs[0].inserted == 10
    assert runs[0].updated == 5
    assert runs[0].scored == 12
    assert runs[0].above_threshold == 4
    assert runs[0].notified == 3
    assert runs[0].error_message is None


def test_scrape_run_failure_persists_error(tmp_path) -> None:
    db_path = tmp_path / "jobpipe.db"
    initialize_database(db_path)

    repo = JobRepository(db_path)
    started = datetime(2026, 4, 9, 9, 0, tzinfo=timezone.utc)
    finished = datetime(2026, 4, 9, 9, 1, tzinfo=timezone.utc)

    repo.create_scrape_run(run_id="run-failed", started_at=started)
    repo.fail_scrape_run(
        run_id="run-failed",
        error_message="simulated failure",
        finished_at=finished,
    )

    runs = repo.list_recent_runs(limit=5)
    assert len(runs) == 1
    assert runs[0].run_id == "run-failed"
    assert runs[0].status == "Failed"
    assert runs[0].started_at == started
    assert runs[0].finished_at == finished
    assert runs[0].error_message == "simulated failure"


def test_notification_audit_record_and_list(tmp_path) -> None:
    db_path = tmp_path / "jobpipe.db"
    initialize_database(db_path)

    repo = JobRepository(db_path)
    first_time = datetime(2026, 4, 9, 11, 0, tzinfo=timezone.utc)
    second_time = datetime(2026, 4, 9, 11, 5, tzinfo=timezone.utc)

    repo.record_notification_event(
        run_id="run-abc",
        job_id="hiringcafe-123",
        title="Backend Engineer",
        company="Acme",
        score=0.91,
        url="https://hiring.cafe/jobs/123",
        delivery_status="Attempted",
        notified_at=first_time,
    )
    repo.record_notification_event(
        run_id="run-xyz",
        job_id="hiringcafe-456",
        title="Data Engineer",
        company="Beta Labs",
        score=0.86,
        url="https://hiring.cafe/jobs/456",
        delivery_status="Failed",
        error_message="toast backend unavailable",
        notified_at=second_time,
    )

    events = repo.list_recent_notifications(limit=5)
    assert len(events) == 2

    latest = events[0]
    assert latest.job_id == "hiringcafe-456"
    assert latest.delivery_status == "Failed"
    assert latest.error_message == "toast backend unavailable"
    assert latest.notified_at == second_time

    older = events[1]
    assert older.job_id == "hiringcafe-123"
    assert older.delivery_status == "Attempted"
    assert older.error_message is None
    assert older.notified_at == first_time

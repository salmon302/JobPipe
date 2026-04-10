from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from sqlite3 import Row


def _parse_datetime(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    return value


def _row_value(row: Row, key: str, default=None):
    if key in row.keys():
        return row[key]
    return default


@dataclass(slots=True)
class JobRecord:
    id: str
    platform: str
    title: str
    company: str
    url: str
    description: str
    date_posted: datetime
    match_score: float | None = None
    status: str = "Queued"
    years_required: int | None = None
    is_remote: bool | None = None
    score_relevance: float | None = None
    score_attainability: float | None = None
    score_recency: float | None = None

    @classmethod
    def from_row(cls, row: Row) -> "JobRecord":
        date_posted = _parse_datetime(row["date_posted"])
        if date_posted is None:
            raise ValueError("date_posted is required for JobRecord")

        is_remote_raw = _row_value(row, "is_remote")
        is_remote = None if is_remote_raw is None else bool(is_remote_raw)

        return cls(
            id=row["id"],
            platform=row["platform"],
            title=row["title"],
            company=row["company"],
            url=row["url"],
            description=row["description"],
            date_posted=date_posted,
            match_score=_row_value(row, "match_score"),
            status=_row_value(row, "status", "Queued"),
            years_required=_row_value(row, "years_required"),
            is_remote=is_remote,
            score_relevance=_row_value(row, "score_relevance"),
            score_attainability=_row_value(row, "score_attainability"),
            score_recency=_row_value(row, "score_recency"),
        )


@dataclass(slots=True)
class ScrapeRunRecord:
    run_id: str
    started_at: datetime
    finished_at: datetime | None
    status: str
    scraped: int
    inserted: int
    updated: int
    scored: int
    above_threshold: int
    notified: int
    error_message: str | None = None

    @classmethod
    def from_row(cls, row: Row) -> "ScrapeRunRecord":
        started_at = _parse_datetime(row["started_at"])
        if started_at is None:
            raise ValueError("started_at is required for ScrapeRunRecord")

        finished_at = _parse_datetime(row["finished_at"])

        return cls(
            run_id=row["run_id"],
            started_at=started_at,
            finished_at=finished_at,
            status=row["status"],
            scraped=row["scraped"],
            inserted=row["inserted"],
            updated=row["updated"],
            scored=row["scored"],
            above_threshold=row["above_threshold"],
            notified=row["notified"],
            error_message=row["error_message"],
        )


@dataclass(slots=True)
class NotificationAuditRecord:
    notification_id: int
    run_id: str | None
    job_id: str
    title: str
    company: str
    score: float | None
    url: str
    delivery_status: str
    error_message: str | None
    notified_at: datetime

    @classmethod
    def from_row(cls, row: Row) -> "NotificationAuditRecord":
        notified_at = _parse_datetime(row["notified_at"])
        if notified_at is None:
            raise ValueError("notified_at is required for NotificationAuditRecord")

        return cls(
            notification_id=row["notification_id"],
            run_id=row["run_id"],
            job_id=row["job_id"],
            title=row["title"],
            company=row["company"],
            score=row["score"],
            url=row["url"],
            delivery_status=row["delivery_status"],
            error_message=row["error_message"],
            notified_at=notified_at,
        )

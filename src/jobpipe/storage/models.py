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
    summary: str | None = None
    requirements: str | None = None
    location: str | None = None
    county: str | None = None
    compensation: str | None = None
    workplace_type: str | None = None
    employment_type: str | None = None
    department: str | None = None
    team: str | None = None
    views: int | None = None
    saves: int | None = None
    applications: int | None = None
    posted_at: str | None = None
    posted_ago: str | None = None
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
            summary=_row_value(row, "summary"),
            requirements=_row_value(row, "requirements"),
            location=_row_value(row, "location"),
            county=_row_value(row, "county"),
            compensation=_row_value(row, "compensation"),
            workplace_type=_row_value(row, "workplace_type"),
            employment_type=_row_value(row, "employment_type"),
            department=_row_value(row, "department"),
            team=_row_value(row, "team"),
            views=_row_value(row, "views"),
            saves=_row_value(row, "saves"),
            applications=_row_value(row, "applications"),
            posted_at=_row_value(row, "posted_at"),
            posted_ago=_row_value(row, "posted_ago"),
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
            run_id=_row_value(row, "run_id"),
            job_id=row["job_id"],
            title=row["title"],
            company=row["company"],
            score=_row_value(row, "score"),
            url=row["url"],
            delivery_status=row["delivery_status"],
            error_message=_row_value(row, "error_message"),
            notified_at=notified_at,
        )


@dataclass(slots=True)
class MasterCVVersion:
    id: int | None = None
    cv_hash: str = ""
    file_path: str = ""
    version_number: int = 1
    created_at: datetime | None = None

    @classmethod
    def from_row(cls, row: Row) -> "MasterCVVersion":
        created_at = _parse_datetime(row["created_at"])
        return cls(
            id=row["id"],
            cv_hash=row["cv_hash"],
            file_path=row["file_path"],
            version_number=row["version_number"],
            created_at=created_at,
        )


@dataclass(slots=True)
class ResumeVariant:
    id: int | None = None
    job_id: str | None = None
    variant_name: str = ""
    page_length: int = 1
    job_type: str | None = None
    target_company: str | None = None
    skills: str | None = None  # JSON array of skills
    master_cv_hash: str = ""
    generation_number: int = 1
    parent_variant_id: int | None = None
    tex_path: str = ""
    pdf_path: str | None = None
    ats_optimized: bool = False
    ats_score: float | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def from_row(cls, row: Row) -> "ResumeVariant":
        created_at = _parse_datetime(row["created_at"])
        updated_at = _parse_datetime(row["updated_at"])
        ats_optimized = bool(row["ats_optimized"]) if "ats_optimized" in row.keys() else False

        return cls(
            id=row["id"],
            job_id=_row_value(row, "job_id"),
            variant_name=row["variant_name"],
            page_length=row["page_length"],
            job_type=_row_value(row, "job_type"),
            target_company=_row_value(row, "target_company"),
            skills=_row_value(row, "skills"),
            master_cv_hash=row["master_cv_hash"],
            generation_number=row["generation_number"],
            parent_variant_id=_row_value(row, "parent_variant_id"),
            tex_path=row["tex_path"],
            pdf_path=_row_value(row, "pdf_path"),
            ats_optimized=ats_optimized,
            ats_score=_row_value(row, "ats_score"),
            created_at=created_at,
            updated_at=updated_at,
        )

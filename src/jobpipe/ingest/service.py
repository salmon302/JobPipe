# Purpose: Validate ingest payloads and build JobRecord batches for processing.
# Author: Seth Nenninger (GPT-5.2-Codex Agent)
# Timestamp: 2026-05-12T00:00:00Z
# Changelog: Add ingest payload parsing and batch processing.

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import logging
import re
from typing import Any

from jobpipe.config import Settings
from jobpipe.pipeline import process_ingest_batch
from jobpipe.storage.models import JobRecord

_MAX_JOBS_PER_REQUEST = 2000
LOGGER = logging.getLogger(__name__)
_RELATIVE_TIME_RE = re.compile(
    r"(?P<count>\d+)\s*(?P<unit>w|week|weeks|d|day|days|h|hr|hour|hours|"
    r"min|mins|minute|minutes|m)\b",
    re.IGNORECASE,
)


class IngestPayloadError(ValueError):
    pass


@dataclass(frozen=True)
class IngestResult:
    run_id: str
    ingested: int
    inserted: int
    updated: int
    scored: int
    above_threshold: int
    notified: int
    scoring_in_progress: bool = False


def _require_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if value is None:
        raise IngestPayloadError(f"{key} is required")
    text = str(value).strip()
    if not text:
        raise IngestPayloadError(f"{key} must not be empty")
    return text


def _optional_text(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(payload: dict[str, Any], key: str) -> int | None:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    digits = re.sub(r"[^0-9]", "", text)
    if not digits:
        return None
    return int(digits)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "job"


def _clean_company_name(raw: str) -> str:
    """Attempt to produce a readable company name from various inputs.

    Only transforms inputs that are clearly bad (UUIDs, URL fragments).
    Passes through normal company names unchanged.
    """
    import uuid

    text = raw.strip()

    # If it looks like a UUID, return as-is (no better info available)
    try:
        uuid.UUID(text)
        return text
    except (ValueError, AttributeError):
        pass

    # If it's a normal company name (has spaces, mixed case, reasonable length),
    # pass through unchanged
    if " " in text or any(c.isupper() for c in text if c.isalpha()):
        if 2 < len(text) < 100:
            return text

    # If it contains underscores and looks like a hostname fragment, try to clean it
    if "_" in text and any(kw in text.lower() for kw in ["portal", "student", "career", "jobs"]):
        # Extract the likely company part (first segment before common suffixes)
        parts = text.split("_")
        for part in parts:
            cleaned = re.sub(
                r"(portal|student|career|jobs|en-us|en_us|www|com|net|org)\\b",
                "",
                part,
                flags=re.IGNORECASE,
            ).strip("-")
            if cleaned and len(cleaned) > 2:
                return cleaned.title()
        return parts[0].title() if parts else text

    # If it's a hostname-like slug (e.g., "drhorton", "beallsoutlet")
    if re.match(r"^[a-z]+$", text) and len(text) > 2:
        return text.title()

    return text


def _hash_job_id(url: str) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    return f"job-{digest}"


def _parse_relative_time(value: str, now: datetime) -> datetime | None:
    match = _RELATIVE_TIME_RE.search(value)
    if not match:
        return None

    count = int(match.group("count"))
    unit = match.group("unit").lower()

    if unit.startswith("w"):
        delta = timedelta(weeks=count)
    elif unit.startswith("d"):
        delta = timedelta(days=count)
    elif unit.startswith("h"):
        delta = timedelta(hours=count)
    else:
        delta = timedelta(minutes=count)

    return now - delta


def _parse_date_posted(value: Any, now: datetime) -> datetime:
    if value is None:
        return now

    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)

    text = str(value).strip()
    if not text:
        return now

    if text.lower().endswith("z"):
        text = text[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        relative = _parse_relative_time(text, now)
        if relative is not None:
            return relative

    return now


def _compose_description(payload: dict[str, Any]) -> str:
    parts: list[str] = []

    summary = _optional_text(payload, "summary")
    if summary:
        parts.append(summary)

    requirements = _optional_text(payload, "requirements")
    if requirements:
        parts.append(requirements)

    for label, key in (
        ("Location", "location"),
        ("Compensation", "compensation"),
        ("Workplace", "workplace_type"),
        ("Employment", "employment_type"),
        ("Department", "department"),
        ("Team", "team"),
        ("Views", "views"),
        ("Saves", "saves"),
        ("Applications", "applications"),
    ):
        value = _optional_text(payload, key)
        if value:
            parts.append(f"{label}: {value}")

    return "\n".join(parts).strip()


def _build_job_record(payload: dict[str, Any]) -> JobRecord:
    title = _require_text(payload, "title")
    company_raw = _require_text(payload, "company")
    # Pass through the company name unchanged unless it looks like a bad value
    # (all-lowercase slug, UUID, etc.). Never overwrite a valid-looking name.
    # A name with uppercase letters or spaces is likely a proper company name.
    company = company_raw
    has_uppercase = any(c.isupper() for c in company_raw)
    is_lowercase_slug = re.match(r"^[a-z0-9_-]+$", company_raw) is not None
    if (is_lowercase_slug or len(company_raw) < 3) and not has_uppercase:
        # Only then try to clean it
        cleaned = _clean_company_name(company_raw)
        if cleaned != company_raw:
            company = cleaned
    url = _require_text(payload, "url")
    
    # If company name still looks like a URL fragment, try extracting from URL
    # ONLY if the current company name is clearly bad (all lowercase, no uppercase letters)
    has_uppercase = any(c.isupper() for c in company)
    if not has_uppercase and len(company) < 30:
        # Try to extract company from URL hostname
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            if parsed.hostname:
                # Extract company from hostname like "drhorton.taleo.net" -> "drhorton"
                hostname_parts = parsed.hostname.split(".")
                if len(hostname_parts) >= 2:
                    potential_company = hostname_parts[0]
                    # Clean up common prefixes
                    potential_company = re.sub(
                        r"^(www|jobs|careers|apply)\\",
                        "",
                        potential_company,
                    )
                    if potential_company and len(potential_company) > 2:
                        company = potential_company.title()
        except Exception:  # noqa: BLE001
            pass
    description = _optional_text(payload, "description") or _compose_description(payload)
    if not description:
        raise IngestPayloadError("description is required")

    summary = _optional_text(payload, "summary")
    requirements = _optional_text(payload, "requirements")
    location = _optional_text(payload, "location")
    county = _optional_text(payload, "county")
    compensation = _optional_text(payload, "compensation")
    workplace_type = _optional_text(payload, "workplace_type")
    employment_type = _optional_text(payload, "employment_type")
    department = _optional_text(payload, "department")
    team = _optional_text(payload, "team")
    views = _optional_int(payload, "views")
    saves = _optional_int(payload, "saves")
    applications = _optional_int(payload, "applications")

    date_value = (
        payload.get("date_posted")
        or payload.get("posted_at")
        or payload.get("posted")
        or payload.get("job_posted_at")
        or payload.get("posted_ago")
    )
    now = datetime.now(timezone.utc)
    date_posted = _parse_date_posted(date_value, now)

    provided_id = _optional_text(payload, "id") or _optional_text(payload, "job_id")
    provided_id = provided_id or _optional_text(payload, "source_id")
    # Use URL-based hash as the stable ID — platform-agnostic so the same URL
    # always maps to the same job record regardless of which platform sent it.
    job_id = provided_id or _hash_job_id(url)

    platform = (
        _optional_text(payload, "platform")
        or _optional_text(payload, "source")
        or "Extension"
    )

    return JobRecord(
        id=job_id,
        platform=platform,
        title=title,
        company=company,
        url=url,
        description=description,
        summary=summary,
        requirements=requirements,
        location=location,
        county=county,
        compensation=compensation,
        workplace_type=workplace_type,
        employment_type=employment_type,
        department=department,
        team=team,
        views=views,
        saves=saves,
        applications=applications,
        date_posted=date_posted,
    )


def _extract_jobs(payload: dict[str, Any]) -> list[JobRecord]:
    jobs_data = payload.get("jobs")
    if jobs_data is None:
        job = _build_job_record(payload)
        LOGGER.info("IngestService | Single job: id=%s platform=%s title=%s", job.id, job.platform, job.title)
        return [job]

    if not isinstance(jobs_data, list):
        raise IngestPayloadError("jobs must be a list")

    jobs: list[JobRecord] = []
    for entry in jobs_data:
        if not isinstance(entry, dict):
            raise IngestPayloadError("jobs entries must be objects")
        job = _build_job_record(entry)
        jobs.append(job)

    LOGGER.info("IngestService | Batch: %d jobs, sample IDs: %s", len(jobs), [j.id for j in jobs[:5]])
    return jobs


class JobIngestService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def settings(self) -> Settings:
        return self._settings

    def ingest_payload(self, payload: dict[str, Any]) -> IngestResult:
        if not isinstance(payload, dict):
            raise IngestPayloadError("payload must be an object")

        jobs = _extract_jobs(payload)
        if not jobs:
            raise IngestPayloadError("jobs list must not be empty")
        if len(jobs) > _MAX_JOBS_PER_REQUEST:
            raise IngestPayloadError("job batch exceeds max allowed size")

        batch_result = process_ingest_batch(self._settings, jobs)
        summary = batch_result.summary

        return IngestResult(
            run_id=batch_result.run_id,
            ingested=summary.ingested,
            inserted=summary.inserted,
            updated=summary.updated,
            scored=summary.scored,
            above_threshold=summary.above_threshold,
            notified=summary.notified,
            scoring_in_progress=batch_result.scoring_in_progress,
        )

    def get_run_status(self, run_id: str) -> dict[str, Any]:
        """Get the status of a scrape run."""
        repository = JobRepository(self._settings.db_path)
        run = repository.get_scrape_run(run_id)
        
        if run is None:
            raise ValueError(f"Run {run_id} not found")
        
        return {
            "run_id": run.run_id,
            "status": run.status,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "scraped": run.scraped,
            "inserted": run.inserted,
            "updated": run.updated,
            "scored": run.scored,
            "above_threshold": run.above_threshold,
            "notified": run.notified,
            "error_message": run.error_message,
        }

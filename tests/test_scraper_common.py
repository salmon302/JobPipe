from __future__ import annotations

from datetime import datetime, timezone

from jobpipe.scrapers.common import (
    build_job_id,
    merge_descriptions,
    normalize_long_text,
    parse_posted_datetime,
)


def test_normalize_long_text_collapses_whitespace() -> None:
    value = normalize_long_text("  Python \n\t FastAPI   role  ")
    assert value == "Python FastAPI role"


def test_merge_descriptions_handles_empty_values() -> None:
    assert merge_descriptions("", "Detail") == "Detail"
    assert merge_descriptions("Card", "") == "Card"


def test_merge_descriptions_avoids_duplicate_content() -> None:
    merged = merge_descriptions("Python API role", "Python API role with FastAPI and SQL")
    assert merged == "Python API role with FastAPI and SQL"


def test_merge_descriptions_combines_distinct_content() -> None:
    merged = merge_descriptions("Card summary", "Detailed scope")
    assert merged == "Card summary\n\nDetailed scope"


def test_parse_posted_datetime_parses_relative_values() -> None:
    now = datetime.now(timezone.utc)
    parsed = parse_posted_datetime("6 hours ago")

    age_hours = (now - parsed).total_seconds() / 3600
    assert 5.9 <= age_hours <= 6.1


def test_parse_posted_datetime_parses_iso_timestamp() -> None:
    parsed = parse_posted_datetime("2026-04-07T17:45:00Z")
    assert parsed == datetime(2026, 4, 7, 17, 45, tzinfo=timezone.utc)


def test_parse_posted_datetime_sets_utc_for_naive_timestamp() -> None:
    parsed = parse_posted_datetime("2026-04-07 17:45:00")
    assert parsed.tzinfo == timezone.utc
    assert parsed.year == 2026
    assert parsed.month == 4
    assert parsed.day == 7


def test_parse_posted_datetime_falls_back_to_now_for_unknown_value() -> None:
    before = datetime.now(timezone.utc)
    parsed = parse_posted_datetime("not a datetime")
    after = datetime.now(timezone.utc)

    assert before <= parsed <= after


def test_build_job_id_prefers_source_node_id() -> None:
    job_id = build_job_id("wellfound", node_id="wf-123", url="https://wellfound.com/jobs/123")
    assert job_id == "wellfound-wf-123"


def test_build_job_id_hashes_url_when_node_id_missing() -> None:
    first = build_job_id("builtin", node_id=None, url="https://builtin.com/jobs/abc")
    second = build_job_id("builtin", node_id=None, url="https://builtin.com/jobs/abc")

    assert first == second
    assert first.startswith("builtin-")
    assert len(first.removeprefix("builtin-")) == 12

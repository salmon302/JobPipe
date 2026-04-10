from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import re

from dateutil.parser import parse as parse_datetime


DEFAULT_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:137.0) Gecko/20100101 Firefox/137.0",
]

_RELATIVE_AGE_RE = re.compile(r"(\d+)\s+(hour|day|week)s?\s+ago", re.IGNORECASE)


def normalize_long_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def merge_descriptions(card_description: str, detail_description: str) -> str:
    card_text = card_description.strip()
    detail_text = detail_description.strip()

    if not card_text:
        return detail_text
    if not detail_text:
        return card_text

    if card_text.lower() in detail_text.lower():
        return detail_text

    return f"{card_text}\n\n{detail_text}"


def parse_posted_datetime(raw: str) -> datetime:
    now = datetime.now(timezone.utc)
    if not raw:
        return now

    relative_match = _RELATIVE_AGE_RE.search(raw)
    if relative_match:
        magnitude = int(relative_match.group(1))
        unit = relative_match.group(2).lower()

        if unit == "hour":
            return now - timedelta(hours=magnitude)
        if unit == "day":
            return now - timedelta(days=magnitude)
        return now - timedelta(weeks=magnitude)

    try:
        dt = parse_datetime(raw)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return now


def build_job_id(prefix: str, node_id: str | None, url: str) -> str:
    if node_id:
        return f"{prefix}-{node_id}"

    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"

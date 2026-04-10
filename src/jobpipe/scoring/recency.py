from __future__ import annotations

from datetime import datetime, timezone


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def recency_score(posted_at: datetime, is_remote: bool, now_utc: datetime | None = None) -> float:
    """Return recency multiplier in [0, 1] using SRS remote/local decay behavior."""
    now = _to_utc(now_utc or datetime.now(timezone.utc))
    posted = _to_utc(posted_at)

    age_hours = max(0.0, (now - posted).total_seconds() / 3600.0)

    if is_remote:
        # Remote jobs decay sharply after 24h; drop to 0 by 72h.
        if age_hours <= 24:
            return 1.0
        if age_hours >= 72:
            return 0.0
        return max(0.0, 1.0 - ((age_hours - 24.0) / 48.0))

    # Local jobs decay linearly across 7 days.
    max_hours = 7.0 * 24.0
    return max(0.0, 1.0 - (age_hours / max_hours))

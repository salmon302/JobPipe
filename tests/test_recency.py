from datetime import datetime, timedelta, timezone

from jobpipe.scoring.recency import recency_score


def test_remote_jobs_drop_after_24h() -> None:
    now = datetime(2026, 4, 9, tzinfo=timezone.utc)
    posted = now - timedelta(hours=30)
    value = recency_score(posted, is_remote=True, now_utc=now)
    assert value < 1.0


def test_remote_jobs_hit_zero_by_72h() -> None:
    now = datetime(2026, 4, 9, tzinfo=timezone.utc)
    posted = now - timedelta(hours=72)
    assert recency_score(posted, is_remote=True, now_utc=now) == 0.0


def test_local_jobs_decay_linearly_over_week() -> None:
    now = datetime(2026, 4, 9, tzinfo=timezone.utc)
    posted = now - timedelta(days=3)
    value = recency_score(posted, is_remote=False, now_utc=now)
    assert 0.5 < value < 0.7

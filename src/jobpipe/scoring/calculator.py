from __future__ import annotations

from dataclasses import dataclass


RELEVANCE_WEIGHT = 0.5
ATTAINABILITY_WEIGHT = 0.3
RECENCY_WEIGHT = 0.2


@dataclass(frozen=True)
class ScoreBreakdown:
    relevance: float
    attainability: float
    recency: float
    total: float


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def compute_total_match_score(
    relevance: float,
    attainability: float,
    recency: float,
) -> ScoreBreakdown:
    rel = _clamp01(relevance)
    att = _clamp01(attainability)
    rec = _clamp01(recency)

    total = (rel * RELEVANCE_WEIGHT) + (att * ATTAINABILITY_WEIGHT) + (rec * RECENCY_WEIGHT)
    return ScoreBreakdown(relevance=rel, attainability=att, recency=rec, total=_clamp01(total))

import pytest

from jobpipe.scoring.calculator import compute_total_match_score


def test_weighted_total_matches_formula() -> None:
    breakdown = compute_total_match_score(relevance=1.0, attainability=0.5, recency=0.25)
    assert breakdown.total == pytest.approx(0.7)


def test_scores_are_clamped_to_unit_interval() -> None:
    breakdown = compute_total_match_score(relevance=2.0, attainability=-1.0, recency=0.5)
    assert 0.0 <= breakdown.total <= 1.0
    assert breakdown.relevance == 1.0
    assert breakdown.attainability == 0.0

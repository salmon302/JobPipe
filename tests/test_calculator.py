import pytest

from jobpipe.scoring.calculator import (
    ScoreWeights,
    compute_blended_relevance,
    compute_confidence,
    compute_total_match_score,
    select_weights_for_job_type,
    _detect_job_type,
    _clamp01,
)


def test_clamp01() -> None:
    assert _clamp01(0.5) == 0.5
    assert _clamp01(-0.1) == 0.0
    assert _clamp01(1.5) == 1.0


def test_weighted_total_matches_formula() -> None:
    breakdown = compute_total_match_score(relevance=1.0, attainability=0.5, recency=0.25)
    assert breakdown.total == pytest.approx(0.7)


def test_scores_are_clamped_to_unit_interval() -> None:
    breakdown = compute_total_match_score(relevance=2.0, attainability=-1.0, recency=0.5)
    assert 0.0 <= breakdown.total <= 1.0
    assert breakdown.relevance == 1.0
    assert breakdown.attainability == 0.0


def test_detect_job_type_standard() -> None:
    assert _detect_job_type("Software Engineer", "Building backend services") == "standard"


def test_detect_job_type_entry() -> None:
    assert _detect_job_type("Intern", "Summer internship program") == "entry"
    assert _detect_job_type("Junior Developer", "Entry level role") == "entry"


def test_detect_job_type_senior() -> None:
    assert _detect_job_type("Senior Engineer", "Lead development team") == "senior"
    assert _detect_job_type("Principal Architect", "Staff level") == "senior"


def test_detect_job_type_research() -> None:
    assert _detect_job_type("Research Scientist", "Conduct ML research") == "research"


def test_select_weights_for_job_type() -> None:
    entry_weights = select_weights_for_job_type("entry")
    assert entry_weights.attainability > entry_weights.relevance

    senior_weights = select_weights_for_job_type("senior")
    assert senior_weights.relevance > senior_weights.attainability

    standard_weights = select_weights_for_job_type("standard")
    assert standard_weights.relevance == 0.5
    assert standard_weights.attainability == 0.3


def test_compute_blended_relevance() -> None:
    score, details = compute_blended_relevance(0.8, 0.6, 0.7)
    # 0.8*0.6 + 0.6*0.25 + 0.7*0.15 = 0.735
    assert score == pytest.approx(0.735, abs=0.01)
    assert "embed" in details
    assert "kw" in details
    assert "domain" in details


def test_compute_blended_relevance_custom_weights() -> None:
    score, details = compute_blended_relevance(1.0, 1.0, 1.0, 0.5, 0.3, 0.2)
    assert score == pytest.approx(1.0)


def test_compute_confidence_high() -> None:
    conf_level, conf_reason = compute_confidence("skills: 0.800", "Years: 0.90", cv_parsed=True)
    assert conf_level == "high"
    assert "keyword" in conf_reason.lower() or "fully parsed" in conf_reason.lower()


def test_compute_confidence_low() -> None:
    conf_level, conf_reason = compute_confidence("No CV sections", "No skills", cv_parsed=False)
    assert conf_level == "low"
    assert "not parsed" in conf_reason.lower()


def test_score_weights_normalize() -> None:
    weights = ScoreWeights(0.5, 0.3, 0.2)
    norm = weights.normalize()
    assert norm.relevance + norm.attainability + norm.recency == pytest.approx(1.0)


def test_score_weights_normalize_zero() -> None:
    norm = ScoreWeights(0.0, 0.0, 0.0).normalize()
    assert norm.relevance == pytest.approx(0.5)
    assert norm.attainability == pytest.approx(0.3)
    assert norm.recency == pytest.approx(0.2)

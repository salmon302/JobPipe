from jobpipe.scoring.attainability import attainability_score, should_discard_for_senior_role


def test_attainability_buckets_with_new_weights() -> None:
    """With new weights: years=0.40, edu=0.20, skills=0.25, remote=0.05, domain=0.10.
    
    Defaults: edu=0.8, skills=0.5, remote=0.7, domain=0.5.
    For years=0: 1.0*0.40 + 0.8*0.20 + 0.5*0.25 + 0.7*0.05 + 0.5*0.10 = 0.77
    """
    assert abs(attainability_score(0)[0] - 0.77) < 0.01
    assert abs(attainability_score(1)[0] - 0.77) < 0.01
    assert abs(attainability_score(2)[0] - 0.71) < 0.01
    assert abs(attainability_score(3)[0] - 0.65) < 0.01
    assert abs(attainability_score(4)[0] - 0.57) < 0.01
    assert abs(attainability_score(5)[0] - 0.57) < 0.01
    assert abs(attainability_score(6)[0] - 0.47) < 0.01


def test_attainability_handles_missing_years() -> None:
    # None years defaults to a mid-level seniority hint: 0.68*0.40 + 0.8*0.20 + 0.5*0.25 + 0.7*0.05 + 0.5*0.10 = 0.642
    assert abs(attainability_score(None)[0] - 0.642) < 0.01


def test_attainability_varies_by_job_seniority_hint() -> None:
    junior = attainability_score(
        required_years=None,
        job_title="Junior Backend Engineer",
        job_description="Python API work",
    )[0]
    senior = attainability_score(
        required_years=None,
        job_title="Senior Backend Engineer",
        job_description="Python API work",
    )[0]

    assert junior > senior


def test_attainability_rewards_user_experience_for_mid_level_roles() -> None:
    # years=3, user_years=4: gap=0 → years_score=0.95, so:
    # 0.95*0.40 + 0.8*0.20 + 0.5*0.25 + 0.7*0.05 + 0.5*0.10 = 0.75
    assert abs(attainability_score(required_years=3, user_years_experience=4)[0] - 0.75) < 0.01
    # years=5, user_years=4: gap=1 → years_score=0.85, so:
    # 0.85*0.40 + 0.8*0.20 + 0.5*0.25 + 0.7*0.05 + 0.5*0.10 = 0.71
    assert abs(attainability_score(required_years=5, user_years_experience=4)[0] - 0.71) < 0.01


def test_should_discard_only_for_extreme_senior_roles() -> None:
    """Graduated seniority: only discard if gap > 5 years."""
    # gap=5 (6-1=5) → not > 5, so no discard
    assert should_discard_for_senior_role(required_years=6, user_years_experience=1) is False
    # gap=7 (8-1=7) → > 5, discard
    assert should_discard_for_senior_role(required_years=8, user_years_experience=1) is True
    # gap=1, no discard
    assert should_discard_for_senior_role(required_years=5, user_years_experience=4) is False
    # None years, no discard
    assert should_discard_for_senior_role(required_years=None, user_years_experience=1) is False

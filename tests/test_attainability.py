from jobpipe.scoring.attainability import attainability_score, should_discard_for_senior_role


def test_attainability_buckets_follow_srs() -> None:
    # With default values (no education/skills/remote preference),
    # years score is weighted 50%, education 20% (0.8 default),
    # skills 20% (0.5 default), remote 10% (0.7 default)
    # So for years=0: 1.0*0.5 + 0.8*0.2 + 0.5*0.2 + 0.7*0.1 = 0.83
    assert attainability_score(0)[0] == 0.83
    assert attainability_score(1)[0] == 0.83
    assert attainability_score(2)[0] == 0.73
    assert attainability_score(3)[0] == 0.73
    assert attainability_score(4)[0] == 0.53
    assert attainability_score(5)[0] == 0.53
    assert attainability_score(6)[0] == 0.33


def test_attainability_handles_missing_years() -> None:
    # None years: 0.65*0.5 + 0.8*0.2 + 0.5*0.2 + 0.7*0.1 = 0.655
    assert attainability_score(None)[0] == 0.655


def test_attainability_rewards_user_experience_for_mid_level_roles() -> None:
    # years=3, user_years=4: years_score=0.9 (gap=0, required_years<=3), so 0.9*0.5 + 0.8*0.2 + 0.5*0.2 + 0.7*0.1 = 0.78
    assert attainability_score(required_years=3, user_years_experience=4)[0] == 0.78
    # years=5, user_years=4: years_score=0.6 (gap=1, required_years<=5), so 0.6*0.5 + 0.8*0.2 + 0.5*0.2 + 0.7*0.1 = 0.63
    assert attainability_score(required_years=5, user_years_experience=4)[0] == 0.63


def test_should_discard_for_senior_role_when_clearly_out_of_range() -> None:
    assert should_discard_for_senior_role(required_years=6, user_years_experience=1) is True
    assert should_discard_for_senior_role(required_years=5, user_years_experience=4) is False
    assert should_discard_for_senior_role(required_years=None, user_years_experience=1) is False

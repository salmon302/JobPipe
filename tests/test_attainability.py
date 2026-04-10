from jobpipe.scoring.attainability import attainability_score, should_discard_for_senior_role


def test_attainability_buckets_follow_srs() -> None:
    assert attainability_score(0) == 1.0
    assert attainability_score(1) == 1.0
    assert attainability_score(2) == 0.8
    assert attainability_score(3) == 0.8
    assert attainability_score(4) == 0.4
    assert attainability_score(5) == 0.4
    assert attainability_score(6) == 0.0


def test_attainability_handles_missing_years() -> None:
    assert attainability_score(None) == 0.65


def test_attainability_rewards_user_experience_for_mid_level_roles() -> None:
    assert attainability_score(required_years=3, user_years_experience=4) == 0.9
    assert attainability_score(required_years=5, user_years_experience=4) == 0.6


def test_should_discard_for_senior_role_when_clearly_out_of_range() -> None:
    assert should_discard_for_senior_role(required_years=6, user_years_experience=1) is True
    assert should_discard_for_senior_role(required_years=5, user_years_experience=4) is False
    assert should_discard_for_senior_role(required_years=None, user_years_experience=1) is False

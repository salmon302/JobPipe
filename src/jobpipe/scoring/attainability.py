from __future__ import annotations


SENIOR_DISCARD_THRESHOLD_YEARS = 5


def should_discard_for_senior_role(
    required_years: int | None,
    user_years_experience: int = 1,
) -> bool:
    if required_years is None:
        return False

    user_years = max(0, user_years_experience)
    if required_years < SENIOR_DISCARD_THRESHOLD_YEARS:
        return False

    # Treat clearly out-of-range senior requirements as a hard reject.
    return required_years > (user_years + 1)


def attainability_score(required_years: int | None, user_years_experience: int = 1) -> float:
    """Return a score in [0, 1], following SRS buckets with experience-aware adjustment."""

    user_years = max(0, user_years_experience)

    if required_years is None:
        return 0.65
    if required_years <= 1:
        return 1.0

    gap = max(0, required_years - user_years)

    if required_years <= 3:
        if gap <= 0:
            return 0.9
        return 0.8

    if required_years <= 5:
        if gap <= 1:
            return 0.6
        return 0.4

    if gap <= 1:
        return 0.2
    return 0.0

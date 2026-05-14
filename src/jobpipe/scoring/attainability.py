from __future__ import annotations
from typing import Optional


SENIOR_DISCARD_THRESHOLD_YEARS = 5

# Education level mapping (higher = more education)
EDUCATION_LEVELS = {
    "none": 0,
    "high_school": 1,
    "associate": 2,
    "bachelor": 3,
    "master": 4,
    "phd": 5,
}


def should_discard_for_senior_role(
    required_years: Optional[int],
    user_years_experience: int = 1,
) -> bool:
    if required_years is None:
        return False

    user_years = max(0, user_years_experience)
    if required_years < SENIOR_DISCARD_THRESHOLD_YEARS:
        return False

    # Treat clearly out-of-range senior requirements as a hard reject.
    return required_years > (user_years + 1)


def _parse_education_level(education: Optional[str]) -> int:
    """Parse education string to numeric level."""
    if not education:
        return 3  # Default to bachelor's
    education_lower = education.lower()
    for key, level in EDUCATION_LEVELS.items():
        if key in education_lower:
            return level
    return 3


def attainability_score(
    required_years: Optional[int],
    user_years_experience: int = 1,
    user_education: Optional[str] = None,
    required_education: Optional[str] = None,
    user_skills: Optional[list[str]] = None,
    job_skills: Optional[list[str]] = None,
    remote_preference: Optional[bool] = None,
    is_remote_job: Optional[bool] = None,
) -> tuple[float, str]:
    """Return a score in [0, 1] with detailed breakdown.
    
    Args:
        required_years: Years of experience required by job
        user_years_experience: User's years of experience
        user_education: User's education level (e.g., "bachelor", "master")
        required_education: Required education for job
        user_skills: List of user's skills
        job_skills: List of skills required by job
        remote_preference: User's preference for remote work (True/False/None)
        is_remote_job: Whether the job is remote
        
    Returns:
        Tuple of (score, details_string)
    """
    details = []
    
    # 1. Years of experience score (50% weight)
    years_score = _years_score(required_years, user_years_experience)
    details.append(f"Years: {years_score:.2f}")
    
    # 2. Education score (20% weight)
    edu_score = _education_score(user_education, required_education)
    details.append(f"Education: {edu_score:.2f}")
    
    # 3. Skill match score (20% weight)
    skill_score = _skill_match_score(user_skills, job_skills)
    details.append(f"Skills: {skill_score:.2f}")
    
    # 4. Remote preference score (10% weight)
    remote_score = _remote_preference_score(remote_preference, is_remote_job)
    details.append(f"Remote: {remote_score:.2f}")
    
    # Weighted average
    total = (years_score * 0.5) + (edu_score * 0.2) + (skill_score * 0.2) + (remote_score * 0.1)
    details_str = ", ".join(details)
    
    return max(0.0, min(1.0, total)), details_str


def _years_score(required_years: Optional[int], user_years: int) -> float:
    """Calculate years of experience score."""
    user_years = max(0, user_years)
    
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


def _education_score(user_education: Optional[str], required_education: Optional[str]) -> float:
    """Calculate education compatibility score."""
    if not required_education:
        return 0.8  # No requirement, assume mostly compatible
    
    user_level = _parse_education_level(user_education)
    required_level = _parse_education_level(required_education)
    
    if user_level >= required_level:
        return 1.0
    if user_level == required_level - 1:
        return 0.7
    if user_level == required_level - 2:
        return 0.4
    return 0.2


def _skill_match_score(user_skills: Optional[list[str]], job_skills: Optional[list[str]]) -> float:
    """Calculate skill match score based on overlap."""
    if not user_skills or not job_skills:
        return 0.5  # Neutral if missing data
    
    user_skills_set = set(s.lower() for s in user_skills)
    job_skills_set = set(s.lower() for s in job_skills)
    
    if not job_skills_set:
        return 0.5
    
    overlap = user_skills_set & job_skills_set
    score = len(overlap) / len(job_skills_set)
    return score


def _remote_preference_score(remote_preference: Optional[bool], is_remote_job: Optional[bool]) -> float:
    """Calculate remote preference compatibility."""
    if remote_preference is None or is_remote_job is None:
        return 0.7  # Neutral if unknown
    
    if remote_preference == is_remote_job:
        return 1.0  # Perfect match
    return 0.3  # Mismatch

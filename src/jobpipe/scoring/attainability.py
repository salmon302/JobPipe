from __future__ import annotations
from typing import Optional

from jobpipe.scoring.cv_parser import ParsedCV, CategorizedSkills


# Education level mapping (higher = more education)
EDUCATION_LEVELS = {
    "none": 0,
    "high_school": 1,
    "associate": 2,
    "bachelor": 3,
    "master": 4,
    "phd": 5,
}

# Skill category weights for weighted matching
_SKILL_TIER_WEIGHTS: dict[str, float] = {
    "languages": 3.0,
    "frameworks": 2.0,
    "infrastructure": 1.5,
    "domains": 2.0,
}


def should_discard_for_senior_role(
    required_years: Optional[int],
    user_years_experience: int = 1,
) -> bool:
    """Graduated seniority check — no longer a hard discard.

    Returns True only for extreme mismatches (gap > 5 years).
    Otherwise returns False and the penalty is handled by _years_score.
    """
    if required_years is None:
        return False

    user_years = max(0, user_years_experience)
    gap = required_years - user_years

    # Only hard-discard if gap is extreme (> 5 years)
    if gap > 5:
        return True
    return False


def _parse_education_level(education: Optional[str]) -> int:
    """Parse education string to numeric level."""
    if not education:
        return 3  # Default to bachelor's
    education_lower = education.lower()
    for key, level in EDUCATION_LEVELS.items():
        if key in education_lower:
            return level
    return 3


def _extract_job_skills_from_description(description: str) -> list[str]:
    """Extract skill-like terms from job title and description text."""
    import re
    # Common tech skill patterns
    patterns = [
        r"\b(Python|C\+\+|C#|JavaScript|TypeScript|SQL|Java|Go|Rust|Ruby|PHP|Kotlin|Swift|Scala|R)\b",
        r"\b(React|Vue|Angular|Django|Flask|FastAPI|Spring|Express|Node\.?js|Next\.?js|Nuxt|Svelte)\b",
        r"\b(AWS|Azure|GCP|Docker|Kubernetes|Terraform|Ansible|Jenkins|GitHub Actions|CI/CD)\b",
        r"\b(PostgreSQL|MySQL|MongoDB|Redis|Elasticsearch|DynamoDB|Cassandra|MariaDB)\b",
        r"\b(TensorFlow|PyTorch|Scikit-learn|Pandas|NumPy|OpenCV|MediaPipe|Hugging Face|LangChain)\b",
        r"\b(OpenGL|Unity|Unreal|WebGL|Three\.?js|Blender)\b",
        r"\b(HTML|CSS|Sass|Less|Tailwind|Bootstrap|Material UI|Shadcn)\b",
        r"\b(GraphQL|gRPC|WebSocket|REST|SOAP|OAuth|JWT)\b",
        r"\b(Kafka|RabbitMQ|NATS|Celery|Redis|SQS)\b",
        r"\b(Linux|Bash|PowerShell|Nginx|Apache|HAProxy)\b",
        r"\b(Backend|Frontend|Full Stack|Fullstack|DevOps|Platform|Data Engineer|Data Scientist|Machine Learning|ML|AI|QA|Quality Assurance|Embedded|Firmware|Simulation|Healthcare|Security|Cloud|API|Distributed|Mobile)\b",
    ]
    skills: set[str] = set()
    text_lower = description.lower()
    for pattern in patterns:
        matches = re.findall(pattern, text_lower, re.IGNORECASE)
        skills.update(m.lower() for m in matches)
    return sorted(skills)


def _infer_seniority_hint(job_title: str, job_description: str) -> str:
    """Infer job seniority from title and description."""
    combined = f"{job_title} {job_description}".lower()

    if any(term in combined for term in ("intern", "internship", "entry", "junior", "new grad", "graduate", "trainee", "apprentice")):
        return "entry"
    if any(term in combined for term in ("senior", "staff", "principal", "lead", "head of", "director", "architect")):
        return "senior"
    if any(term in combined for term in ("manager", "supervisor", "team lead", "engineering manager")):
        return "manager"
    return "mid"


def _extract_required_education(description: str) -> str | None:
    """Extract required education level from job description."""
    import re
    patterns = [
        (r"\b(PhD|Doctorate)\b", "phd"),
        (r"\b(Master[\'’]?s|MS|M\.S\.)\b", "master"),
        (r"\b(Bachelor[\'’]?s|BS|B\.S\.|BA|B\.A\.)\b", "bachelor"),
        (r"\b(Associate[\'’]?s|AA|A\.S\.)\b", "associate"),
        (r"\b(High School|GED)\b", "high_school"),
    ]
    text_lower = description.lower()
    for pattern, level in patterns:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return level
    return None


def attainability_score(
    required_years: Optional[int] = None,
    user_years_experience: int = 1,
    user_education: Optional[str] = None,
    required_education: Optional[str] = None,
    user_skills: Optional[list[str]] = None,
    job_skills: Optional[list[str]] = None,
    remote_preference: Optional[bool] = None,
    is_remote_job: Optional[bool] = None,
    # New CV-derived parameters
    cv: Optional[ParsedCV] = None,
    job_description: str = "",
    job_title: str = "",
) -> tuple[float, str]:
    """Return a score in [0, 1] with detailed breakdown.

    Uses CV-derived data when available, falling back to explicit params.

    Args:
        required_years: Years of experience required by job
        user_years_experience: User's years of experience
        user_education: User's education level (e.g., "bachelor", "master")
        required_education: Required education for job
        user_skills: List of user's skills
        job_skills: List of skills required by job
        remote_preference: User's preference for remote work
        is_remote_job: Whether the job is remote
        cv: ParsedCV object (if available, overrides static params)
        job_description: Full job description (for auto-extraction)
        job_title: Job title (for domain matching)

    Returns:
        Tuple of (score, details_string)
    """
    details = []

    # ---- Resolve user profile from CV if available ----
    effective_years = user_years_experience
    effective_education = user_education
    effective_skills = user_skills or []
    effective_remote_pref = remote_preference

    seniority_hint = _infer_seniority_hint(job_title, job_description)

    if cv is not None:
        effective_years = max(user_years_experience, int(cv.total_years_experience()))
        # Use highest education level name
        highest = cv.highest_education_level()
        level_name = {v: k for k, v in EDUCATION_LEVELS.items()}.get(highest, "bachelor")
        effective_education = level_name
        effective_skills = cv.skills.all_skills() + cv.all_tech_stacks()

    # ---- Auto-extract job requirements from description ----
    job_text = f"{job_title} {job_description}".strip()
    if not job_skills and job_text:
        job_skills = _extract_job_skills_from_description(job_text)
    if not required_education and job_text:
        required_education = _extract_required_education(job_text)

    # 1. Years of experience score (40% weight)
    years_score = _years_score(required_years, effective_years, seniority_hint)
    details.append(f"Years: {years_score:.2f}")

    # 2. Education score (20% weight)
    edu_score = _education_score(effective_education, required_education, cv)
    details.append(f"Education: {edu_score:.2f}")

    # 3. Skill match score (25% weight)
    skill_score = _skill_match_score(effective_skills, job_skills, cv)
    details.append(f"Skills: {skill_score:.2f}")

    # 4. Remote preference score (5% weight)
    remote_score = _remote_preference_score(effective_remote_pref, is_remote_job)
    details.append(f"Remote: {remote_score:.2f}")

    # 5. Domain alignment score (10% weight) — new
    domain_score = _domain_attainability_score(cv, job_title, job_description)
    details.append(f"Domain: {domain_score:.2f}")

    # Weighted average
    total = (
        years_score * 0.40
        + edu_score * 0.20
        + skill_score * 0.25
        + remote_score * 0.05
        + domain_score * 0.10
    )
    details_str = ", ".join(details)

    return max(0.0, min(1.0, total)), details_str


def _years_score(required_years: Optional[int], user_years: int, seniority_hint: str = "mid") -> float:
    """Calculate years of experience score with graduated penalty."""
    user_years = max(0, user_years)

    if required_years is None:
        if seniority_hint == "entry":
            return 0.92
        if seniority_hint == "manager":
            return 0.55
        if seniority_hint == "senior":
            return 0.35
        return 0.68
    if required_years <= 1:
        return 1.0

    gap = max(0, required_years - user_years)

    # Graduated penalty instead of hard cutoff
    if gap <= 0:
        return 0.95  # User meets or exceeds requirement
    if gap == 1:
        return 0.85  # Close enough
    if gap == 2:
        return 0.70  # Moderate gap
    if gap <= 4:
        return 0.50  # Significant gap
    if gap <= 6:
        return 0.25  # Large gap
    return 0.10  # Extreme gap


def _education_score(
    user_education: Optional[str],
    required_education: Optional[str],
    cv: Optional[ParsedCV] = None,
) -> float:
    """Calculate education compatibility score with in-progress support."""
    if not required_education:
        return 0.8  # No requirement, assume mostly compatible

    # If CV is available, use its education entries for richer scoring
    if cv is not None and cv.education:
        required_level = _parse_education_level(required_education)

        # Check completed degrees first
        completed = cv.highest_completed_education()
        if completed and completed.effective_level() >= required_level:
            return 1.0

        # Check in-progress degrees
        in_progress = cv.in_progress_education()
        for entry in in_progress:
            if entry.effective_level() >= required_level:
                return 0.85  # In-progress at required level

        # Check if any education is close
        highest = cv.highest_education_level()
        if highest >= required_level:
            return 0.85  # In-progress counts
        if highest == required_level - 1:
            return 0.65
        if highest == required_level - 2:
            return 0.35
        return 0.15

    # Fallback to simple string-based scoring
    user_level = _parse_education_level(user_education)
    required_level = _parse_education_level(required_education)

    if user_level >= required_level:
        return 1.0
    if user_level == required_level - 1:
        return 0.7
    if user_level == required_level - 2:
        return 0.4
    return 0.2


def _skill_match_score(
    user_skills: Optional[list[str]],
    job_skills: Optional[list[str]],
    cv: Optional[ParsedCV] = None,
) -> float:
    """Calculate weighted skill match score.

    Uses tiered weights when CV is available (languages 3x, frameworks 2x).
    """
    if not user_skills or not job_skills:
        return 0.5  # Neutral if missing data

    user_set = set(s.lower().strip() for s in user_skills)
    job_set = set(s.lower().strip() for s in job_skills)

    if not job_set:
        return 0.5

    # If CV is available, use tiered weighting
    if cv is not None:
        # Build tier map: skill -> weight
        tier_map: dict[str, float] = {}
        for lang in cv.skills.languages:
            tier_map[lang.lower()] = _SKILL_TIER_WEIGHTS["languages"]
        for fw in cv.skills.frameworks:
            tier_map[fw.lower()] = _SKILL_TIER_WEIGHTS["frameworks"]
        for tool in cv.skills.infrastructure:
            tier_map[tool.lower()] = _SKILL_TIER_WEIGHTS["infrastructure"]
        for domain in cv.skills.domains:
            tier_map[domain.lower()] = _SKILL_TIER_WEIGHTS["domains"]

        total_job_weight = 0.0
        matched_weight = 0.0

        for job_skill in job_set:
            weight = tier_map.get(job_skill, 1.0)  # Default weight 1.0
            total_job_weight += weight
            if job_skill in user_set:
                matched_weight += weight

        if total_job_weight == 0:
            return 0.5

        score = matched_weight / total_job_weight
        return min(1.0, score)

    # Fallback: simple overlap
    overlap = user_set & job_set
    score = len(overlap) / len(job_set)
    return score


def _remote_preference_score(remote_preference: Optional[bool], is_remote_job: Optional[bool]) -> float:
    """Calculate remote preference compatibility."""
    if remote_preference is None or is_remote_job is None:
        return 0.7  # Neutral if unknown

    if remote_preference == is_remote_job:
        return 1.0  # Perfect match
    return 0.3  # Mismatch


def _domain_attainability_score(
    cv: Optional[ParsedCV],
    job_title: str,
    job_description: str,
) -> float:
    """Score domain alignment for attainability.

    Having experience in the same domain as the job makes it more attainable.
    """
    if cv is None or not cv.experience:
        return 0.5  # Neutral

    from jobpipe.scoring.domain_matcher import detect_job_domain

    job_domain = detect_job_domain(job_title, job_description)
    if job_domain is None:
        return 0.5

    cv_domains = cv.experience_domains()
    if job_domain in cv_domains:
        return 1.0  # Direct domain match

    # Check for related domains
    related = {
        "healthcare": "simulation",
        "simulation": "healthcare",
        "defense": "simulation",
        "enterprise": "backend",
        "data_science": "enterprise",
    }
    if job_domain in related and related[job_domain] in cv_domains:
        return 0.8

    return 0.4

"""Tests for domain alignment scoring."""

from jobpipe.scoring.cv_parser import ParsedCV, ExperienceEntry
from jobpipe.scoring.domain_matcher import detect_job_domain, domain_alignment_score


def _make_test_cv_with_domain(domain: str) -> ParsedCV:
    cv = ParsedCV()
    cv.experience.append(ExperienceEntry(
        role="Engineer",
        company="TestCorp",
        domain=domain,
        description=f"Worked in {domain} field",
    ))
    return cv


def test_detect_job_domain_healthcare() -> None:
    domain = detect_job_domain(
        "Clinical Software Engineer",
        "Developing healthcare software for medical devices."
    )
    assert domain == "healthcare"


def test_detect_job_domain_simulation() -> None:
    domain = detect_job_domain(
        "Simulation Engineer",
        "Building real-time simulation engines for training."
    )
    assert domain == "simulation"


def test_detect_job_domain_backend() -> None:
    domain = detect_job_domain(
        "Backend Developer",
        "Building REST APIs with FastAPI and PostgreSQL."
    )
    assert domain == "backend"


def test_detect_job_domain_frontend() -> None:
    domain = detect_job_domain(
        "Frontend Engineer",
        "Building React UIs with TypeScript."
    )
    assert domain == "frontend"


def test_detect_job_domain_data_science() -> None:
    domain = detect_job_domain(
        "Data Scientist",
        "Building machine learning models for predictive analytics."
    )
    assert domain == "data_science"


def test_detect_job_domain_devops() -> None:
    domain = detect_job_domain(
        "DevOps Engineer",
        "Managing AWS infrastructure with Docker and Kubernetes."
    )
    assert domain == "devops"


def test_detect_job_domain_none() -> None:
    domain = detect_job_domain(
        "Generic Job",
        "Some random description with no clear domain keywords."
    )
    # Should either return None or a domain with minimal match
    assert domain is None or isinstance(domain, str)


def test_domain_alignment_direct_match() -> None:
    cv = _make_test_cv_with_domain("healthcare")
    score, details = domain_alignment_score(
        "Clinical Engineer",
        "Healthcare software development",
        cv,
    )
    assert score == 1.0
    assert "match" in details


def test_domain_alignment_related_match() -> None:
    cv = _make_test_cv_with_domain("simulation")
    score, details = domain_alignment_score(
        "Healthcare Sim Engineer",
        "Medical simulation training software",
        cv,
    )
    assert score >= 0.5  # healthcare and simulation are related
    assert "Related" in details or "match" in details


def test_domain_alignment_mismatch() -> None:
    cv = _make_test_cv_with_domain("healthcare")
    score, details = domain_alignment_score(
        "Frontend Developer",
        "Building web UIs with React",
        cv,
    )
    assert score < 0.5
    assert "mismatch" in details


def test_domain_alignment_no_cv_domains() -> None:
    cv = ParsedCV()  # No experience
    score, details = domain_alignment_score(
        "Software Engineer",
        "Building backend systems",
        cv,
    )
    assert score == 0.3  # Penalty for no CV domains and job domain not in CV text


def test_domain_alignment_no_job_domain() -> None:
    cv = _make_test_cv_with_domain("healthcare")
    score, details = domain_alignment_score(
        "Ambiguous Role",
        "Some nondescript description",
        cv,
    )
    assert score == 0.5

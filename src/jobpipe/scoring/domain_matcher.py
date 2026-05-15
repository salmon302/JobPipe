"""Domain/industry alignment scoring.

Detects the domain of a job posting and scores alignment with the
candidate's experience domains from the parsed CV.
"""

from __future__ import annotations

import re
from jobpipe.scoring.cv_parser import ParsedCV


# Domain detection keywords for job postings
_JOB_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "healthcare": [
        "healthcare", "medical", "clinical", "hospital", "patient",
        "biologics", "pharma", "pharmaceutical", "cGMP", "FDA",
        "regulated", "compliance", "drug", "therapy", "diagnostic",
        "health", "medicine", "surgical", "infusion",
    ],
    "simulation": [
        "simulation", "simulator", "real-time", "real time",
        "virtual reality", "VR", "training", "visualization",
        "rendering", "engine", "FPS", "game", "gaming",
        "3D", "graphics", "OpenGL", "Unity", "Unreal",
    ],
    "defense": [
        "defense", "military", "tactical", "combat", "casualty",
        "I/ITSEC", "security clearance", "government", "DoD",
        "national security", "defence", "weapon", "mission",
    ],
    "enterprise": [
        "enterprise", "infrastructure", "cloud", "API", "backend",
        "scalable", "high-throughput", "pipeline", "microservice",
        "distributed system", "SaaS", "platform", "integration",
    ],
    "data_science": [
        "data scientist", "machine learning", "ML", "AI",
        "data analysis", "predictive", "statistical", "NLP",
        "OCR", "dataset", "analytics", "deep learning",
        "neural network", "computer vision", "data pipeline",
    ],
    "embedded": [
        "embedded", "MCU", "microcontroller", "AVR", "Arduino",
        "ESP32", "firmware", "sensor", "IoT", "real-time os",
        "RTOS", "bare metal", "hardware",
    ],
    "audio": [
        "audio", "DSP", "signal processing", "synthesis",
        "SuperCollider", "sound", "music", "acoustic",
        "speech", "voice",
    ],
    "frontend": [
        "frontend", "front-end", "UI", "React", "Vue", "Angular",
        "web developer", "CSS", "HTML", "JavaScript", "TypeScript",
        "user interface", "UX",
    ],
    "backend": [
        "backend", "back-end", "server", "API", "REST",
        "microservice", "database", "FastAPI", "Django", "Flask",
    ],
    "devops": [
        "devops", "SRE", "infrastructure", "cloud", "AWS",
        "Docker", "Kubernetes", "Terraform", "Ansible",
        "CI/CD", "deployment", "monitoring",
    ],
    "government": [
        "government", "legislative", "congress", "senate", "house of representatives",
        "political", "public sector", "federal", "state", "municipal",
        "policy", "regulatory", "agency", "department", "bureau",
    ],
}


def detect_job_domain(title: str, description: str) -> str | None:
    """Detect the most likely domain of a job posting.

    Args:
        title: Job title.
        description: Job description text.

    Returns:
        Domain name string or None if no domain detected.
    """
    combined = f"{title} {description}".lower()
    scores: dict[str, int] = {}

    for domain, keywords in _JOB_DOMAIN_KEYWORDS.items():
        score = 0
        for kw in keywords:
            pattern = re.compile(rf"\b{re.escape(kw.lower())}\b")
            score += len(pattern.findall(combined))
        if score > 0:
            scores[domain] = score

    if not scores:
        return None
    return max(scores, key=scores.get)


def domain_alignment_score(
    job_title: str,
    job_description: str,
    cv: ParsedCV,
) -> tuple[float, str]:
    """Score how well a job's domain aligns with the candidate's experience.

    Returns:
        Tuple of (score in [0, 1], details_string).
    """
    job_domain = detect_job_domain(job_title, job_description)
    if job_domain is None:
        return 0.5, "No domain detected for job"

    cv_domains = cv.experience_domains()
    
    # If CV has no experience domains, check if the job domain is in CV skills/projects
    if not cv_domains:
        # Check if any CV skills or project domains match the job domain
        cv_all_text = cv.raw_text.lower()
        if job_domain in cv_all_text:
            return 0.75, f"Job domain '{job_domain}' found in CV text (no experience entries)"
        # No CV domains and job domain not in CV - penalize
        return 0.3, f"Job domain: {job_domain}, no CV experience domains (penalty)"

    # Check if job domain matches any CV experience domain
    if job_domain in cv_domains:
        return 1.0, f"Domain match: {job_domain}"

    # Check for related domains
    related_pairs = [
        ("healthcare", "simulation"),     # medical simulation
        ("simulation", "healthcare"),
        ("simulation", "defense"),         # military simulation
        ("defense", "simulation"),
        ("enterprise", "backend"),         # backend enterprise
        ("backend", "enterprise"),
        ("data_science", "enterprise"),    # data pipelines
        ("enterprise", "data_science"),
        ("embedded", "simulation"),        # embedded sim
        ("simulation", "embedded"),
        ("frontend", "enterprise"),
        ("enterprise", "frontend"),
        ("devops", "enterprise"),
        ("enterprise", "devops"),
        ("government", "enterprise"),     # government uses enterprise tech
        ("enterprise", "government"),
    ]

    for d1, d2 in related_pairs:
        if job_domain == d1 and d2 in cv_domains:
            return 0.75, f"Related domain: {job_domain} (CV has {d2})"

    # Complete mismatch - strong penalty
    return 0.2, f"Domain mismatch: job={job_domain}, CV has {', '.join(cv_domains)}"
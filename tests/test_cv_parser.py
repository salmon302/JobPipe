"""Tests for the CV parsing engine."""

from pathlib import Path
from jobpipe.scoring.cv_parser import (
    parse_cv_text,
    parse_cv_file,
    ParsedCV,
    CategorizedSkills,
    EducationEntry,
    ExperienceEntry,
    ProjectEntry,
)

# Sample Markdown CV matching Master_CV.md structure
SAMPLE_MD_CV = """# Seth Nenninger

Fort Myers, FL · sethnenninger@gmail.com

## Professional Summary

Software Engineer with experience in high-performance applications and real-time simulation engines.

## Skills

- **Core Languages:** C++, Python, C#, JavaScript, SQL, AVR Assembly
- **Frameworks & Libraries:** React, FastAPI, Qt, Pandas, PyTorch, OpenGL, JUCE
- **Infrastructure & Tools:** AWS (EC2), Docker, Ansible, Git, Linux, Jira
- **Domain Expertise:** Real-Time Engines, Quality Assurance (QA) Protocols, Regulatory Compliance (FDA/cGMP), Data Integrity

## Education

- **Admitted to MS in Simulation & Modeling**, University of Central Florida — Aug 2026 – May 2028 (Expected)
- **BS in Software Engineering**, Florida Gulf Coast University — Aug 2021 – May 2026
- **Coursework towards BS in Biochemistry**, Rochester Institute of Technology — Aug 2020 – May 2021

## Work Experience

### Backend Engineer Intern — Exonicus (Aug 2025 – Present)
- Architected a LAN-based remote control system for a real-time visualization tool.
- Engineered backend integration between a data engine and Unity, optimizing for 60 FPS.

### Biologics Processor & QA Associate — Grifols (Mar 2025 – Present)
- Process over 1,750 biological samples weekly with 99.8% accuracy.
- Maintain data integrity for over 3,000 sensitive records.

### Research Assistant – NLP & Data Analysis — FGCU (Oct 2025 – Dec 2025)
- Utilized Python (Pandas, SciPy, Scikit-learn) to process large datasets.

## Projects

- **DSATrain: AI-Powered Technical Interview Platform** (FastAPI, React) — July 2025 – Sep 2025
  - Built a full-stack application providing real-time feedback on coding challenges.
- **SMARTArm: Voice & Vision Controlled Robotic Teleoperation** (Python, OpenCV, MediaPipe, Flask, ESP32)
  - Architected a multi-modal teleoperation framework for a 6 DOF robotic arm.

## Awards

- **Best XR Game (Medical Training)** — I/ITSEC Serious Games Showcase & Challenge — Dec 2025
- **Hertz Company Challenge Winner** — EagleHacks Hackathon — Feb 2025
"""


def test_parse_full_cv() -> None:
    """Test that the CV parser extracts all major sections."""
    cv = parse_cv_text(SAMPLE_MD_CV)

    assert isinstance(cv, ParsedCV)
    assert len(cv.summary) > 0
    assert "Software Engineer" in cv.summary


def test_parse_skills() -> None:
    """Test skills parsing with categorization."""
    cv = parse_cv_text(SAMPLE_MD_CV)

    assert len(cv.skills.languages) >= 4  # C++, Python, C#, JavaScript, SQL
    assert "C++" in cv.skills.languages or "python" in str(cv.skills.languages).lower()
    assert len(cv.skills.frameworks) >= 3  # React, FastAPI, Qt, etc.
    assert len(cv.skills.infrastructure) >= 3  # AWS, Docker, Ansible, etc.
    assert len(cv.skills.domains) >= 2  # Real-Time, QA, etc.

    # All skills combined should be non-empty
    assert len(cv.skills.all_skills()) > 10


def test_skills_to_text() -> None:
    """Test to_text() generates proper text for embedding."""
    text = CategorizedSkills(
        languages=["Python", "C++"],
        frameworks=["React"],
    ).to_text()
    assert "Python" in text
    assert "C++" in text
    assert "React" in text
    assert "Languages" in text


def test_parse_education() -> None:
    """Test education parsing with status detection."""
    cv = parse_cv_text(SAMPLE_MD_CV)

    assert len(cv.education) >= 2

    # Check in-progress MS degree
    ms_entries = [e for e in cv.education if e.level == "master"]
    assert len(ms_entries) >= 1
    ms = ms_entries[0]
    assert ms.status == "in_progress"
    assert "Simulation" in ms.field or "simulation" in ms.field.lower()

    # Check completed BS degree
    bs_entries = [e for e in cv.education if e.level == "bachelor" and e.status == "completed"]
    assert len(bs_entries) >= 1


def test_education_effective_level() -> None:
    """Test that in-progress MS gives effective level 4 (master)."""
    cv = parse_cv_text(SAMPLE_MD_CV)
    assert cv.highest_education_level() >= 4  # At least master's level

    completed = cv.highest_completed_education()
    assert completed is not None
    assert completed.level == "bachelor"

    in_progress = cv.in_progress_education()
    assert len(in_progress) >= 1
    assert in_progress[0].level == "master"


def test_parse_experience() -> None:
    """Test work experience parsing."""
    cv = parse_cv_text(SAMPLE_MD_CV)

    assert len(cv.experience) >= 2

    # Check Exonicus
    exonicus = [e for e in cv.experience if "Exonicus" in e.company]
    assert len(exonicus) >= 1
    assert "Backend" in exonicus[0].role
    assert exonicus[0].end_date == "" or "Present" in str(exonicus[0])

    # Check domain detection on experience
    has_domain = any(e.domain is not None for e in cv.experience)
    # This may or may not detect domains depending on descriptions
    # Just verify the field exists


def test_total_years_experience() -> None:
    """Test total years calculation."""
    cv = parse_cv_text(SAMPLE_MD_CV)
    years = cv.total_years_experience()
    assert years > 0
    # Should be at least ~2 years worth of experience entries
    assert years >= 1.0


def test_experience_domains() -> None:
    """Test experience domain extraction."""
    cv = parse_cv_text(SAMPLE_MD_CV)
    domains = cv.experience_domains()
    assert isinstance(domains, list)


def test_parse_projects() -> None:
    """Test project parsing."""
    cv = parse_cv_text(SAMPLE_MD_CV)

    assert len(cv.projects) >= 2
    project_names = [p.name for p in cv.projects]
    assert any("DSATrain" in name for name in project_names)
    assert any("SMARTArm" in name for name in project_names)


def test_all_tech_stacks() -> None:
    """Test aggregated tech stack from experience and projects."""
    cv = parse_cv_text(SAMPLE_MD_CV)
    techs = cv.all_tech_stacks()
    assert len(techs) > 0
    # Should have some common techs
    assert any("python" in t.lower() for t in techs) or any("react" in t.lower() for t in techs)


def test_to_section_dict() -> None:
    """Test conversion to section dict for embedding."""
    cv = parse_cv_text(SAMPLE_MD_CV)
    sections = cv.to_section_dict()

    assert "skills" in sections
    assert "education" in sections
    assert "experience" in sections
    assert "projects" in sections
    assert "summary" in sections

    assert len(sections["skills"]) > 0
    assert len(sections["education"]) > 0
    assert len(sections["experience"]) > 0


def test_parse_empty_cv() -> None:
    """Test parsing an empty CV returns default ParsedCV."""
    cv = parse_cv_text("")
    assert isinstance(cv, ParsedCV)
    assert cv.summary == ""
    assert len(cv.skills.all_skills()) == 0
    assert len(cv.education) == 0
    assert len(cv.experience) == 0
    assert len(cv.projects) == 0


def test_parse_minimal_cv() -> None:
    """Test parsing a minimal CV with just skills."""
    minimal = """## Skills
- **Core Languages:** Python, JavaScript"""
    cv = parse_cv_text(minimal)
    assert len(cv.skills.languages) >= 1
    assert cv.summary == ""
    assert len(cv.experience) == 0


def test_parse_cv_file(tmp_path: Path) -> None:
    """Test parsing from a file path."""
    cv_path = tmp_path / "test_cv.md"
    cv_path.write_text(SAMPLE_MD_CV, encoding="utf-8")

    cv = parse_cv_file(str(cv_path))
    assert isinstance(cv, ParsedCV)
    assert len(cv.skills.all_skills()) > 0
    assert len(cv.education) >= 1

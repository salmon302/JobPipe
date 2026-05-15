"""Parse Master CV (Markdown or LaTeX) into structured dataclasses.

Supports both Markdown (.md) and LaTeX (.tex) CV formats used by JobPipe.
The parser extracts sections by header patterns and uses regex to pull out
typed data: categorized skills, education entries with status, experience
entries with tech stacks, and project entries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class CategorizedSkills:
    languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    infrastructure: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)

    def all_skills(self) -> list[str]:
        return self.languages + self.frameworks + self.infrastructure + self.domains

    def to_text(self) -> str:
        parts = []
        if self.languages:
            parts.append("Languages: " + ", ".join(self.languages))
        if self.frameworks:
            parts.append("Frameworks: " + ", ".join(self.frameworks))
        if self.infrastructure:
            parts.append("Infrastructure: " + ", ".join(self.infrastructure))
        if self.domains:
            parts.append("Domains: " + ", ".join(self.domains))
        return "\n".join(parts)


@dataclass
class EducationEntry:
    level: str          # "phd", "master", "bachelor", "associate", "high_school"
    field: str          # "Simulation & Modeling", "Software Engineering"
    status: str         # "completed", "in_progress", "coursework_only"
    start_year: int | None = None
    end_year: int | None = None
    institution: str = ""
    raw: str = ""

    def effective_level(self) -> int:
        """Return numeric level considering in-progress degrees."""
        base = {"none": 0, "high_school": 1, "associate": 2, "bachelor": 3,
                "master": 4, "phd": 5}
        level_num = base.get(self.level, 0)
        if self.status == "in_progress":
            # In-progress degrees count as 0.85 of completed
            return level_num
        return level_num

    def is_completed(self) -> bool:
        return self.status == "completed"


@dataclass
class ExperienceEntry:
    role: str
    company: str
    start_date: str = ""
    end_date: str = ""       # "" means "Present"
    tech_stack: list[str] = field(default_factory=list)
    domain: str | None = None
    description: str = ""
    raw: str = ""

    def years_active(self) -> float:
        """Estimate years of experience from this entry."""
        # Simple heuristic: count years from start to end
        start_match = re.search(r"(\d{4})", self.start_date)
        end_match = re.search(r"(\d{4})", self.end_date) if self.end_date else None
        if start_match:
            start_year = int(start_match.group(1))
            if end_match:
                return max(0.5, float(int(end_match.group(1)) - start_year))
            else:
                # Present — assume ~1 year or compute from current year
                return 1.0
        return 0.5


@dataclass
class ProjectEntry:
    name: str
    tech_stack: list[str] = field(default_factory=list)
    domain: str | None = None
    description: str = ""
    raw: str = ""


@dataclass
class ParsedCV:
    """Complete structured representation of a parsed CV."""
    skills: CategorizedSkills = field(default_factory=CategorizedSkills)
    education: list[EducationEntry] = field(default_factory=list)
    experience: list[ExperienceEntry] = field(default_factory=list)
    projects: list[ProjectEntry] = field(default_factory=list)
    awards: list[str] = field(default_factory=list)
    summary: str = ""
    raw_text: str = ""

    def total_years_experience(self) -> float:
        """Sum of estimated years across all experience entries."""
        return sum(e.years_active() for e in self.experience)

    def highest_education_level(self) -> int:
        """Highest effective education level considering in-progress degrees."""
        if not self.education:
            return 3  # default bachelor's
        return max(e.effective_level() for e in self.education)

    def highest_completed_education(self) -> EducationEntry | None:
        """Return the highest completed education entry."""
        completed = [e for e in self.education if e.is_completed()]
        if not completed:
            return None
        return max(completed, key=lambda e: e.effective_level())

    def in_progress_education(self) -> list[EducationEntry]:
        """Return all in-progress education entries."""
        return [e for e in self.education if e.status == "in_progress"]

    def all_tech_stacks(self) -> list[str]:
        """All unique tech stack items from experience and projects."""
        seen: set[str] = set()
        for exp in self.experience:
            for tech in exp.tech_stack:
                seen.add(tech.lower())
        for proj in self.projects:
            for tech in proj.tech_stack:
                seen.add(tech.lower())
        return sorted(seen)

    def experience_domains(self) -> list[str]:
        """Unique domains from experience entries."""
        return sorted({e.domain for e in self.experience if e.domain})

    def to_section_dict(self) -> dict[str, str]:
        """Convert parsed CV to section text dict for embedding."""
        sections = {}
        sections["summary"] = self.summary
        sections["skills"] = self.skills.to_text()
        edu_text = "\n".join(
            f"{e.level} in {e.field} ({e.status}) at {e.institution}"
            for e in self.education
        )
        sections["education"] = edu_text
        exp_text = "\n".join(
            f"{e.role} at {e.company} ({e.start_date}-{e.end_date}): {e.description}"
            for e in self.experience
        )
        sections["experience"] = exp_text
        proj_text = "\n".join(
            f"{p.name}: {p.description}" for p in self.projects
        )
        sections["projects"] = proj_text
        return sections


# ---------------------------------------------------------------------------
# Section header patterns (Markdown)
# ---------------------------------------------------------------------------

_MD_SECTION_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)

# LaTeX section patterns
_TEX_SECTION_RE = re.compile(
    r"\\(?:section\*?)\{([^}]+)\}", re.IGNORECASE
)

# Skill category detection — handles "- **Category:** items" format
_SKILL_CATEGORY_RE = re.compile(
    r"[-*]\s+\*\*(.+?):\*\*\s*(.*?)(?=\n\s*[-*]\s+\*\*|\n\s*\n|\Z)",
    re.DOTALL,
)

# Education entry patterns
_EDU_ENTRY_RE = re.compile(
    r"\*\*(.+?)\*\*,\s*(.+?)\s*[—–-]\s*(.+?)(?:\s*[—–-]\s*(.+))?"
)

# Experience entry patterns (Markdown)
_EXP_HEADER_RE = re.compile(
    r"^###\s+(.+?)\s*[—–-]\s*(.+?)\s*[\(（](.+?)\s*[\)）](?:\s*[—–-]\s*(.+))?",
    re.MULTILINE,
)

# Project entry patterns (Markdown)
_PROJ_HEADER_RE = re.compile(
    r"\*\*(.+?)\*\*\s*(?:\((.+?)\))?\s*[—–-]\s*(.+?)(?:\s*[—–-]\s*(.+))?",
)

# Tech stack extraction
_TECH_STACK_RE = re.compile(
    r"\b(Python|C\+\+|C#|JavaScript|TypeScript|SQL|AVR Assembly|React|FastAPI|Qt|Pandas|PyTorch|OpenGL|JUCE|AWS|EC2|Docker|Ansible|Git|Linux|Jira|OpenCV|MediaPipe|Flask|TensorFlow|TFLM|ESP32|Redis|DynamoDB|Spring|Express|Kubernetes|Terraform|Azure|GCP|MongoDB|PostgreSQL|MySQL|Elasticsearch|SuperCollider|Scikit-learn|SciPy|Unity|Vue|Angular|Django|Flutter|React Native)\b",
    re.IGNORECASE,
)

# Domain detection keywords
_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "healthcare": ["healthcare", "medical", "clinical", "cGMP", "FDA", "biologics", "patient", "drug", "infusion", "pharma"],
    "simulation": ["simulation", "real-time", "real time", "VR", "virtual reality", "training", "visualization", "engine", "FPS", "rendering"],
    "defense": ["defense", "military", "tactical", "combat", "casualty", "I/ITSEC", "security"],
    "enterprise": ["enterprise", "infrastructure", "cloud", "API", "backend", "scalable", "high-throughput", "pipeline"],
    "data_science": ["NLP", "machine learning", "data analysis", "predictive", "statistical", "OCR", "dataset"],
    "embedded": ["embedded", "MCU", "microcontroller", "AVR", "Arduino", "ESP32", "firmware", "sensor"],
    "audio": ["audio", "DSP", "signal", "synthesis", "SuperCollider", "sound"],
    "government": ["government", "legislative", "congress", "public sector", "federal", "state", "municipal", "policy", "agency"],
}

# Education level detection
_EDUCATION_LEVEL_RE = re.compile(
    r"(PhD|Doctorate|Master|MS|M\.S\.|Bachelor|BS|B\.S\.|Associate|High School)",
    re.IGNORECASE,
)

_EDUCATION_STATUS_RE = re.compile(
    r"(Expected|In Progress|Coursework|Candidate|Admitted)", re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Parsing functions
# ---------------------------------------------------------------------------

def _detect_format(text: str) -> str:
    """Detect whether text is Markdown or LaTeX format."""
    if text.strip().startswith("\\documentclass") or "\\section{" in text:
        return "latex"
    return "markdown"


def _extract_sections_markdown(text: str) -> dict[str, str]:
    """Extract sections from Markdown CV by ## headers."""
    sections: dict[str, str] = {}
    matches = list(_MD_SECTION_RE.finditer(text))
    for i, match in enumerate(matches):
        section_name = match.group(1).strip().lower()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        sections[section_name] = content
    return sections


def _extract_sections_latex(text: str) -> dict[str, str]:
    """Extract sections from LaTeX CV by \\section{} commands."""
    sections: dict[str, str] = {}
    matches = list(_TEX_SECTION_RE.finditer(text))
    for i, match in enumerate(matches):
        section_name = match.group(1).strip().lower()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        sections[section_name] = content
    return sections


def _parse_skills(text: str) -> CategorizedSkills:
    """Parse skills section into categorized structure."""
    skills = CategorizedSkills()
    if not text:
        return skills

    # Try LaTeX textbf format: \textbf{Category:} items
    latex_matches = list(re.finditer(r"\\textbf\{([^}]+)\}(.*?)(?=\\textbf\{|\\section|\\vspace|\\noindent|\\end\{document\}|$)", text, re.DOTALL))
    if latex_matches:
        for match in latex_matches:
            cat_name = match.group(1).strip()
            # Clean up category name (remove \&, LaTeX commands)
            cat_name = re.sub(r"\\&\s*", " and ", cat_name)
            items_text = match.group(2).strip()
            # Clean up LaTeX formatting
            items_text = re.sub(r"\\href\{.+?\}\{(.+?)\}", r"\1", items_text)
            items_text = re.sub(r"\\vspace\{.+?\}", "", items_text)
            items_text = re.sub(r"\\noindent\s*", "", items_text)
            # Handle escaped characters (C\#, C\+\+)
            items_text = items_text.replace("\\#", "#").replace("\\+", "+")
            # Split by comma, semicolon, or newline
            items = [s.strip() for s in re.split(r"[,;\n]", items_text) if s.strip()]
            cat_lower = cat_name.lower()
            if "language" in cat_lower:
                skills.languages.extend(items)
            elif "framework" in cat_lower or "library" in cat_lower:
                skills.frameworks.extend(items)
            elif "infrastructure" in cat_lower or "tool" in cat_lower:
                skills.infrastructure.extend(items)
            elif "domain" in cat_lower or "expertise" in cat_lower:
                skills.domains.extend(items)
            else:
                # Fallback: try to categorize by content
                skills.domains.extend(items)
        return skills

    # Try Markdown bold-category format: **Category:** items
    category_matches = _SKILL_CATEGORY_RE.findall(text)
    if category_matches:
        for cat_name, items_text in category_matches:
            items = [s.strip() for s in re.split(r"[,;]", items_text) if s.strip()]
            cat_lower = cat_name.strip().lower()
            if "language" in cat_lower:
                skills.languages.extend(items)
            elif "framework" in cat_lower or "library" in cat_lower:
                skills.frameworks.extend(items)
            elif "infrastructure" in cat_lower or "tool" in cat_lower:
                skills.infrastructure.extend(items)
            elif "domain" in cat_lower or "expertise" in cat_lower:
                skills.domains.extend(items)
            else:
                # Fallback: try to categorize by content
                skills.domains.extend(items)
        return skills

    # Fallback: extract all tech terms
    tech_matches = _TECH_STACK_RE.findall(text)
    for tech in tech_matches:
        tech_lower = tech.lower()
        # Heuristic categorization
        if tech_lower in {"python", "c++", "c#", "javascript", "typescript", "sql", "java", "go", "rust", "ruby", "php", "avr assembly"}:
            skills.languages.append(tech)
        elif tech_lower in {"react", "fastapi", "qt", "pandas", "pytorch", "opengl", "juce", "vue", "angular", "django", "flask", "spring", "express", "scikit-learn", "scipy", "tensorflow"}:
            skills.frameworks.append(tech)
        elif tech_lower in {"aws", "ec2", "docker", "ansible", "git", "linux", "jira", "kubernetes", "terraform", "azure", "gcp", "mongodb", "postgresql", "mysql", "redis", "elasticsearch"}:
            skills.infrastructure.append(tech)
        else:
            skills.domains.append(tech)

    return skills


def _parse_education(text: str) -> list[EducationEntry]:
    """Parse education section into structured entries."""
    entries: list[EducationEntry] = []
    if not text:
        return entries

    lines = [l.strip() for l in text.split("\n") if l.strip() and not l.strip().startswith("-") and not l.strip().startswith("*")]
    # Also try bullet-pointed lines
    bullet_lines = [l.strip() for l in text.split("\n") if l.strip()]

    for line in bullet_lines:
        line = line.lstrip("-*").strip()
        if not line:
            continue

        # Detect education level
        level_match = _EDUCATION_LEVEL_RE.search(line)
        level = "bachelor"
        if level_match:
            level_text = level_match.group(1).lower()
            if level_text in ("phd", "doctorate"):
                level = "phd"
            elif level_text in ("master", "ms", "m.s."):
                level = "master"
            elif level_text in ("bachelor", "bs", "b.s."):
                level = "bachelor"
            elif level_text == "associate":
                level = "associate"
            elif "high school" in level_text:
                level = "high_school"

        # Detect status
        status_match = _EDUCATION_STATUS_RE.search(line)
        status = "completed"
        if status_match:
            status_text = status_match.group(1).lower()
            if status_text in ("expected", "in progress", "candidate", "admitted"):
                status = "in_progress"
            elif status_text == "coursework":
                status = "coursework_only"

        # Extract field of study
        field = ""
        field_match = re.search(
            r"(?:in|for|—|–|-)\s*(.+?)(?:\s*[—–-]|\s*\(|\s*,\s*(?:University|College|Institute|RIT|FGCU|UCF))",
            line,
        )
        if field_match:
            field = field_match.group(1).strip()

        # Extract institution
        institution = ""
        inst_match = re.search(
            r"(University\s+of\s+[A-Za-z\s&]+|[A-Za-z]+\s+(?:University|College|Institute))\b",
            line,
        )
        if inst_match:
            institution = inst_match.group(1).strip()

        # Extract years
        years = re.findall(r"(20\d{2})", line)
        start_year = int(years[0]) if len(years) >= 1 else None
        end_year = int(years[1]) if len(years) >= 2 else None

        entries.append(EducationEntry(
            level=level,
            field=field,
            status=status,
            start_year=start_year,
            end_year=end_year,
            institution=institution,
            raw=line,
        ))

    return entries


def _parse_experience(text: str) -> list[ExperienceEntry]:
    """Parse work experience section into structured entries."""
    entries: list[ExperienceEntry] = []
    if not text:
        return entries

    # Split by ### headers
    blocks = re.split(r"\n(?=###\s)", text)
    for block in blocks:
        block = block.strip()
        if not block:
            continue

        # Parse header: ### Role — Company (Dates)
        header_match = _EXP_HEADER_RE.match(block)
        if not header_match:
            continue

        role = header_match.group(1).strip()
        company = header_match.group(2).strip()
        dates = header_match.group(3).strip()
        extra = header_match.group(4)

        # Split dates
        date_parts = re.split(r"\s*[—–-]\s*", dates)
        start_date = date_parts[0].strip() if date_parts else ""
        end_date = date_parts[1].strip() if len(date_parts) > 1 else ""

        # Extract bullet points as description
        desc_lines = []
        for line in block.split("\n")[1:]:
            line = line.strip().lstrip("-*").strip()
            if line:
                desc_lines.append(line)
        description = " ".join(desc_lines)

        # Extract tech stack from description
        tech_stack = list(set(_TECH_STACK_RE.findall(description)))

        # Detect domain
        domain = _detect_domain(f"{role} {company} {description}")

        entries.append(ExperienceEntry(
            role=role,
            company=company,
            start_date=start_date,
            end_date=end_date,
            tech_stack=tech_stack,
            domain=domain,
            description=description,
            raw=block,
        ))

    return entries


def _parse_projects(text: str) -> list[ProjectEntry]:
    """Parse projects section into structured entries."""
    entries: list[ProjectEntry] = []
    if not text:
        return entries

    # Split by bullet points with bold project names
    blocks = re.split(r"\n(?=\s*[-*]\s*\*\*)", text)
    for block in blocks:
        block = block.strip().lstrip("-*").strip()
        if not block:
            continue

        # Parse: **Project Name** (Tech) — Description
        header_match = _PROJ_HEADER_RE.match(block)
        if not header_match:
            continue

        name = header_match.group(1).strip()
        tech_text = header_match.group(2) or ""
        desc = header_match.group(3) or ""

        # Extract tech stack
        tech_stack = list(set(_TECH_STACK_RE.findall(tech_text + " " + desc)))

        # Detect domain
        domain = _detect_domain(f"{name} {desc}")

        entries.append(ProjectEntry(
            name=name,
            tech_stack=tech_stack,
            domain=domain,
            description=desc,
            raw=block,
        ))

    return entries


def _parse_awards(text: str) -> list[str]:
    """Parse awards section into list of strings."""
    if not text:
        return []
    awards = []
    for line in text.split("\n"):
        line = line.strip().lstrip("-*").strip()
        if line:
            awards.append(line)
    return awards


def _detect_domain(text: str) -> str | None:
    """Detect the most likely domain from text."""
    text_lower = text.lower()
    scores: dict[str, int] = {}
    for domain, keywords in _DOMAIN_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw.lower() in text_lower)
        if score > 0:
            scores[domain] = score
    if not scores:
        return None
    return max(scores, key=scores.get)


# ---------------------------------------------------------------------------
# Main parsing entry point
# ---------------------------------------------------------------------------

def parse_cv_text(text: str) -> ParsedCV:
    """Parse CV text (Markdown or LaTeX) into structured ParsedCV."""
    fmt = _detect_format(text)

    if fmt == "latex":
        sections = _extract_sections_latex(text)
    else:
        sections = _extract_sections_markdown(text)

    cv = ParsedCV(raw_text=text)

    # Map section names (handle variations)
    section_map: dict[str, str] = {}
    for key in sections:
        key_lower = key.lower()
        if "summary" in key_lower or "profile" in key_lower:
            section_map["summary"] = sections[key]
        elif "skill" in key_lower:
            section_map["skills"] = sections[key]
        elif "education" in key_lower:
            section_map["education"] = sections[key]
        elif "experience" in key_lower or "work" in key_lower or "employment" in key_lower:
            section_map["experience"] = sections[key]
        elif "project" in key_lower:
            section_map["projects"] = sections[key]
        elif "award" in key_lower or "honor" in key_lower:
            section_map["awards"] = sections[key]

    # Parse each section
    if "summary" in section_map:
        cv.summary = section_map["summary"].strip()
    if "skills" in section_map:
        cv.skills = _parse_skills(section_map["skills"])
    if "education" in section_map:
        cv.education = _parse_education(section_map["education"])
    if "experience" in section_map:
        cv.experience = _parse_experience(section_map["experience"])
    if "projects" in section_map:
        cv.projects = _parse_projects(section_map["projects"])
    if "awards" in section_map:
        cv.awards = _parse_awards(section_map["awards"])

    return cv


def parse_cv_file(path: str | Path) -> ParsedCV:
    """Parse CV from a file path."""
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    return parse_cv_text(text)
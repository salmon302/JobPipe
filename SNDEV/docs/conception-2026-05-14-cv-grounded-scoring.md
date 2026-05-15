Title: CV-Grounded Relevancy & Attainability Scoring Improvements
Date: 2026-05-14T16:30:00Z
Author: Seth Nenninger (DeepSeek V4 Flash Agent)
Contribution Type: Conception
Ticket/Context: ad-hoc (user request: "improve relevancy/attainability calculations based upon the master CV")
Summary: Design for parsing the Master CV into structured sections and using those to drive granular relevance scoring, CV-derived attainability factors, and composite scoring refinements.

---

## 1. Problem

The current scoring system has significant blind spots because it treats the Master CV as an opaque text blob and relies on static config values for attainability factors.

### Relevance Scoring Gaps

| Issue | Current Behavior | Impact |
|-------|-----------------|--------|
| **Flat CV embedding** | Entire `Master_CV.md` is embedded as one vector via `sentence-transformers/all-MiniLM-L6-v2`. Cosine similarity is computed between the full CV blob and each job description. | A job matching only the "Skills" section gets the same weight as one matching "Projects" — no section-level granularity. |
| **Section-weighted function is dead code** | `compute_section_weighted_relevance()` exists in `scoring/calculator.py` but is **never called** from `pipeline.py`. | The infrastructure for weighted scoring exists but is unused. |
| **No keyword/term boost** | Pure embedding similarity only. No TF-IDF, no exact-match bonus for critical CV terms. | ATS screening often relies on exact keyword hits; embedding-only misses this signal. |
| **No domain/industry detection** | The CV has clear domain signals (healthcare, simulation/causality, defense, real-time systems) but these are never extracted or matched. | A simulation engineer job and a web dev job get scored purely on embedding similarity, ignoring domain fit. |

### Attainability Scoring Gaps

| Issue | Current Behavior | Impact |
|-------|-----------------|--------|
| **Static config values** | `user_skills=[]`, `user_education=None`, `remote_preference=None` are set via env vars and never extracted from the CV. | Skill match always returns 0.5 (neutral). Education defaults to bachelor's. Remote defaults to neutral. |
| **No skill gap analysis** | Simple set overlap `len(overlap) / len(job_skills)`. No distinction between core vs. nice-to-have skills. | A job requiring Python (core CV skill) and Rust (not in CV) scores the same as one requiring Python and C++ (both in CV). |
| **Education ignores in-progress degrees** | The CV has "MS in Simulation & Modeling (Expected 2028)" but the system can only handle completed degrees. | An MS-level job gets scored as if the user only has a BS. |
| **Experience depth is flat** | Only `user_years_experience=1` is used. No consideration of *what kind* of experience (backend engineering, QA, research). | A senior backend role and a junior frontend role both see the same years-based attainability. |
| **Seniority discard is too aggressive** | `should_discard_for_senior_role` discards if `required_years > user_years + 1`. With `user_years=1`, any role asking for 3+ years is discarded. | Mid-level roles (3-5 years) that the user could realistically grow into are hard-rejected. |

### Composite Scoring Gaps

| Issue | Current Behavior | Impact |
|-------|-----------------|--------|
| **Static weights** | `relevance=0.5, attainability=0.3, recency=0.2` regardless of job type. | An internship should weight education higher; a senior role should weight experience higher. |
| **No confidence metric** | No indication of whether a score is based on rich data or defaults. | A score of 0.83 from full CV analysis looks the same as 0.83 from mostly-default values. |

---

## 2. Constraints / Analysis

### Why existing solutions fail

1. **Simple embedding similarity** (current approach) is a reasonable baseline but misses structured signals. The CV is inherently structured (skills, experience, education, projects) and flattening it discards information.

2. **Pure keyword matching** would be too brittle — synonyms, context, and seniority nuances matter. But ignoring keywords entirely (current approach) misses ATS-relevant signals.

3. **LLM-based scoring** (e.g., asking Gemini to score each job) would be cost-prohibitive at scale and introduces latency. The system needs local, fast scoring.

4. **Static config for attainability** was a reasonable MVP shortcut but the CV already contains all the data needed — it just needs to be parsed.

### Design constraints

- **Must remain local**: No API calls for scoring. Embedding + heuristics only.
- **Must be fast**: Scoring hundreds of jobs should take seconds, not minutes.
- **Must be explainable**: The `details` field in `ScoreBreakdown` should give meaningful per-job insight.
- **Must handle both .md and .tex CV formats**: The user maintains both `Master_CV.md` and `main.tex`.
- **Must be incremental**: Each phase should improve scoring without breaking existing functionality.

---

## 3. Proposed Solution

### Phase 1: CV Parsing Engine (`src/jobpipe/scoring/cv_parser.py`)

Parse the Master CV into structured sections with typed data.

```python
@dataclass
class ParsedCV:
    skills: CategorizedSkills  # languages, frameworks, tools, domains
    education: list[EducationEntry]  # multiple degrees with status
    experience: list[ExperienceEntry]  # roles with tech used
    projects: list[ProjectEntry]  # projects with tech stacks
    awards: list[str]
    summary: str

@dataclass
class CategorizedSkills:
    languages: list[str]       # C++, Python, C#, JavaScript, SQL, AVR Assembly
    frameworks: list[str]      # React, FastAPI, Qt, Pandas, PyTorch, OpenGL, JUCE
    infrastructure: list[str]  # AWS (EC2), Docker, Ansible, Git, Linux, Jira
    domains: list[str]         # Real-Time Engines, QA, Regulatory Compliance, Data Integrity

@dataclass
class EducationEntry:
    level: str          # "master", "bachelor"
    field: str          # "Simulation & Modeling", "Software Engineering"
    status: str         # "completed", "in_progress", "coursework_only"
    start_year: int | None
    end_year: int | None
    institution: str

@dataclass
class ExperienceEntry:
    role: str
    company: str
    start_date: str
    end_date: str | None  # None = present
    tech_stack: list[str]
    domain: str | None     # e.g., "healthcare", "simulation", "defense"
    description: str

@dataclass
class ProjectEntry:
    name: str
    tech_stack: list[str]
    domain: str | None
    description: str
```

**Parsing strategy**: Use regex-based section extraction for both Markdown and LaTeX formats. The CV has consistent section headers (`## Skills`, `## Education`, `## Work Experience`, `## Projects`). Skills are already categorized with bold labels. Education has consistent patterns. Experience entries have company, role, date ranges, and bullet points with tech mentions.

### Phase 2: Enhanced Relevance Scoring

#### 2a. Activate Section-Weighted Embedding

Modify `pipeline.py` to call `compute_section_weighted_relevance()` instead of flat `relevance_scores()`. Each CV section is embedded independently and compared against the job description. Weights are configurable per-section.

**Default weights** (from CV analysis — Seth's CV has strong project depth):
- Skills: 0.35
- Experience: 0.30
- Projects: 0.20 (boosted from 0.10 because projects are detailed and tech-rich)
- Education: 0.10
- Summary: 0.05 (new — professional summary alignment)

#### 2b. Keyword Density Scoring

Extract a weighted keyword lexicon from the parsed CV:
- **Tier 1 (Critical)**: Languages and core frameworks (C++, Python, React, FastAPI) — weight 3x
- **Tier 2 (Important)**: Tools and secondary frameworks (Docker, AWS, Pandas, Qt) — weight 2x
- **Tier 3 (Context)**: Domain terms (simulation, healthcare, real-time, QA, cGMP) — weight 1x

For each job, compute a keyword density score:
```
keyword_score = sum(matches * weight) / max_possible
```
This is blended with the embedding score:
```
relevance_final = 0.70 * embedding_score + 0.30 * keyword_score
```

#### 2c. Domain/Industry Alignment

Extract domain signatures from the CV (healthcare/cGMP, simulation/real-time, defense, enterprise infrastructure). For each job, detect domain keywords in the title and description. Score based on domain overlap.

### Phase 3: Enhanced Attainability Scoring

#### 3a. CV-Derived User Profile

Replace static config values with CV-parsed data:

| Config Field | Current (static) | Proposed (CV-derived) |
|-------------|-----------------|----------------------|
| `user_skills` | `[]` (env var) | All skills from CV, categorized |
| `user_education` | `None` (env var) | Highest completed + in-progress |
| `user_years_experience` | `1` (env var) | Computed from experience entries |
| `remote_preference` | env var | Keep as explicit preference |

#### 3b. Weighted Skill Matching

Instead of simple set overlap, use a weighted Jaccard-like score:

```python
def weighted_skill_match(user_skills: CategorizedSkills, job_skills: list[str]) -> float:
    """
    - Core language match: 3x weight
    - Framework match: 2x weight
    - Tool match: 1x weight
    - Domain match: 2x weight (bonus)
    """
```

Also distinguish **required** vs. **preferred/nice-to-have** skills by analyzing job description language ("must have", "required" vs. "preferred", "nice to have", "plus").

#### 3c. Education Scoring with Status

```python
def education_score(user_education: list[EducationEntry], required_education: str | None) -> float:
    """
    - Completed degree at required level: 1.0
    - In-progress degree at required level: 0.85
    - Completed degree one level below: 0.7
    - In-progress degree one level below: 0.55
    - Coursework only: 0.4
    - No match: 0.2
    """
```

For Seth's CV:
- MS in Simulation & Modeling (in progress, expected 2028) → level 4 (master)
- BS in Software Engineering (completed) → level 3 (bachelor)
- Effective education level: 4 (in-progress master's)

#### 3d. Experience Domain Alignment

Score how well the user's experience domains match the job's domain:

```python
def experience_domain_score(
    user_experience: list[ExperienceEntry],
    job_title: str,
    job_description: str,
) -> float:
    """
    Detect job domain from title/description.
    Score based on overlap with experience domains.
    Bonus for current/recent roles.
    """
```

#### 3e. Refined Seniority Handling

Replace the hard discard with a graduated penalty:

```python
def seniority_penalty(required_years: int, user_years: int, user_experience_domains: list[str]) -> float:
    """
    Instead of hard discard:
    - If gap <= 2 years: small penalty (0.9x)
    - If gap 3-5 years: moderate penalty (0.6x)
    - If gap > 5 years: heavy penalty (0.2x)
    - Bonus if user has experience in the same domain
    """
```

### Phase 4: Composite Scoring Refinements

#### 4a. Dynamic Weight Adjustment

Adjust `ScoreWeights` based on job type:

| Job Type Signal | Relevance | Attainability | Recency |
|----------------|-----------|---------------|---------|
| Default | 0.50 | 0.30 | 0.20 |
| Internship/Entry | 0.35 | 0.45 | 0.20 |
| Senior/Lead | 0.55 | 0.30 | 0.15 |
| Research/Academic | 0.60 | 0.25 | 0.15 |

#### 4b. Confidence Flag

Add a `confidence` field to `ScoreBreakdown`:

```python
@dataclass
class ScoreConfidence:
    level: str  # "high", "medium", "low"
    reasons: list[str]

    @staticmethod
    def compute(relevance_detail: str, attainability_detail: str) -> "ScoreConfidence":
        """
        High: All CV sections parsed, all attainability factors from CV
        Medium: Some defaults used
        Low: Mostly defaults, sparse job data
        """
```

#### 4c. Explainable Breakdown

Enhance the `details` string in `ScoreBreakdown` to include:
- Which CV sections contributed most
- Which skills matched/missed
- Education gap (if any)
- Domain alignment notes

---

## Implementation Plan

### Files to Create
1. `src/jobpipe/scoring/cv_parser.py` — CV parsing engine
2. `src/jobpipe/scoring/keyword_scorer.py` — Keyword density scoring
3. `src/jobpipe/scoring/domain_matcher.py` — Domain/industry alignment

### Files to Modify
1. `src/jobpipe/scoring/calculator.py` — Add confidence, dynamic weights, blended relevance
2. `src/jobpipe/scoring/attainability.py` — Accept parsed CV, weighted skills, education with status, domain alignment
3. `src/jobpipe/pipeline.py` — Use parsed CV, section-weighted relevance, enhanced attainability
4. `src/jobpipe/config.py` — Add new config fields if needed
5. `tests/test_attainability.py` — Update for new attainability signature
6. `tests/test_cv_parser.py` — New test file

### Migration Path
1. **Phase 1 first**: CV parser is independent and can be tested in isolation.
2. **Phase 2**: Activate section-weighted relevance alongside flat scoring (A/B comparison).
3. **Phase 3**: Replace static attainability config with CV-derived values.
4. **Phase 4**: Add dynamic weights and confidence as final polish.

Each phase is backwards-compatible — the system falls back to current behavior if CV parsing fails or returns incomplete data.

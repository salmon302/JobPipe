from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import json
import re
import time
from typing import Callable

from jobpipe.resume.compiler import LatexCompileConfig, LatexCompileResult, compile_latex


_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


class ApprovalRequiredError(RuntimeError):
    pass


@dataclass(frozen=True)
class ResumeWriteResult:
    tex_path: Path
    pdf_path: Path
    compile_attempts: int
    variant_id: int | None = None


def compute_master_cv_hash(master_cv_path: Path) -> str:
    """Compute SHA-256 hash of Master CV file for generational tracking."""
    content = master_cv_path.read_bytes()
    return sha256(content).hexdigest()


def detect_page_length(tex_content: str) -> int:
    """Detect page length from LaTeX content. Returns 1 or 2."""
    # Count \newpage, \pagebreak, or look for content length indicators
    page_breaks = len(re.findall(r"\\newpage|\\pagebreak|\\clearpage", tex_content))
    # Heuristic: if multiple page breaks or content is very long, likely 2 pages
    if page_breaks >= 1 or len(tex_content) > 4000:
        return 2
    return 1


def extract_job_metadata(job_description: str, master_cv_path: Path | None = None) -> dict:
    """Extract job type, skills, and other metadata from job description."""
    description_lower = job_description.lower()

    # Common job types
    job_type_keywords = {
        "Frontend": ["frontend", "ui", "react", "vue", "angular"],
        "Backend": ["backend", "api", "server", "database"],
        "Full Stack": ["full stack", "fullstack", "frontend", "backend"],
        "Data Science": ["data scientist", "machine learning", "ml", "ai"],
        "DevOps": ["devops", "sre", "infrastructure", "cloud"],
        "Mobile": ["mobile", "ios", "android", "react native", "flutter"],
        "Leadership": ["manager", "lead", "director", "head of"],
    }

    detected_type = None
    for job_type, keywords in job_type_keywords.items():
        if any(keyword in description_lower for keyword in keywords):
            detected_type = job_type
            break

    # Extract skills (common tech skills)
    skill_patterns = [
        r"\b(python|java|javascript|typescript|c\+\+|go|rust|ruby|php)\b",
        r"\b(react|vue|angular|django|flask|spring|express)\b",
        r"\b(sql|postgresql|mysql|mongodb|redis|elasticsearch)\b",
        r"\b(aws|azure|gcp|docker|kubernetes|terraform)\b",
    ]

    skills_found = set()
    for pattern in skill_patterns:
        matches = re.findall(pattern, description_lower)
        skills_found.update(matches)

    return {
        "job_type": detected_type,
        "skills": sorted(list(skills_found)),
        "skills_json": json.dumps(sorted(list(skills_found))),
    }


def _normalize_output_name(output_name: str, default_base_name: str) -> str:
    candidate = output_name.strip() if output_name else ""
    if not candidate:
        candidate = default_base_name

    candidate = _SAFE_FILENAME_RE.sub("_", candidate.strip().replace(" ", "_"))
    candidate = candidate.strip("._")

    if not candidate:
        candidate = default_base_name

    if not candidate.lower().endswith(".tex"):
        candidate = f"{candidate}.tex"

    return candidate


def _write_text_with_retries(path: Path, content: str, retries: int, backoff_seconds: float = 0.5) -> None:
    max_attempts = max(1, retries + 1)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    last_error: OSError | None = None

    path.parent.mkdir(parents=True, exist_ok=True)

    for attempt in range(1, max_attempts + 1):
        try:
            temp_path.write_text(content, encoding="utf-8")
            temp_path.replace(path)
            return
        except OSError as exc:
            last_error = exc
            if attempt == max_attempts:
                break
            time.sleep(backoff_seconds * attempt)
        finally:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass

    raise RuntimeError(f"Unable to write TeX file at {path}: {last_error}") from last_error


def write_targeted_resume(
    tex_content: str,
    output_name: str,
    output_dir: Path,
    compile_config: LatexCompileConfig,
    approved: bool,
    write_retries: int = 2,
    default_base_name: str = "Targeted_Resume",
    compile_func: Callable[[Path, Path | None, LatexCompileConfig | None], LatexCompileResult] = compile_latex,
    master_cv_path: Path | None = None,
    job_id: str | None = None,
    job_description: str | None = None,
    repository: object | None = None,
) -> ResumeWriteResult:
    if not approved:
        raise ApprovalRequiredError(
            "Write was blocked because approved=False. Review the diff in Claude and retry with approval."
        )

    normalized_name = _normalize_output_name(output_name, default_base_name)
    tex_path = output_dir / normalized_name

    _write_text_with_retries(tex_path, tex_content, retries=write_retries)

    compile_result = compile_func(
        tex_path,
        output_pdf_path=tex_path.with_suffix(".pdf"),
        config=compile_config,
    )

    variant_id = None

    # Store variant metadata in database if repository is provided
    if repository is not None:
        try:
            # Compute Master CV hash for generational tracking
            master_cv_hash = "unknown"
            generation_number = 1
            if master_cv_path and master_cv_path.exists():
                master_cv_hash = compute_master_cv_hash(master_cv_path)

                # Check if this CV version exists, create if not
                existing_cv = repository.get_cv_version_by_hash(master_cv_hash)
                if existing_cv is None:
                    repository.create_cv_version(master_cv_hash, str(master_cv_path))

                # Get generation number for this job (increment if CV changed)
                if job_id:
                    existing_variants = repository.get_variants_by_job(job_id)
                    if existing_variants:
                        # Check if the latest variant uses the same CV hash
                        latest = existing_variants[-1]
                        if latest.master_cv_hash != master_cv_hash:
                            generation_number = latest.generation_number + 1
                        else:
                            generation_number = latest.generation_number

            # Extract metadata from job description
            page_length = detect_page_length(tex_content)
            metadata = {}
            if job_description:
                metadata = extract_job_metadata(job_description, master_cv_path)

            # Get target company from job if available
            target_company = None
            if job_id and hasattr(repository, "select_resume_target_job"):
                job = repository.select_resume_target_job(0.0, job_id)
                if job:
                    target_company = job.company

            # Create variant record
            variant_id = repository.create_resume_variant(
                variant_name=normalized_name,
                tex_path=str(tex_path),
                master_cv_hash=master_cv_hash,
                job_id=job_id,
                page_length=page_length,
                job_type=metadata.get("job_type"),
                target_company=target_company,
                skills=metadata.get("skills_json"),
                generation_number=generation_number,
                pdf_path=str(compile_result.pdf_path) if compile_result.pdf_path else None,
            )
        except Exception as exc:
            import logging
            LOGGER = logging.getLogger(__name__)
            LOGGER.warning("Failed to store resume variant metadata: %s", exc)

    return ResumeWriteResult(
        tex_path=tex_path,
        pdf_path=compile_result.pdf_path,
        compile_attempts=compile_result.attempts,
        variant_id=variant_id,
    )


def ats_optimize_resume(
    tex_content: str,
    job_description: str,
    gemini_api_key: str | None = None,
    gemini_model: str = "gemini-1.5-flash",
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta",
) -> dict:
    """
    Analyze and optimize a resume for ATS (Applicant Tracking System) compatibility.
    Returns dict with 'optimized_content', 'ats_score', 'recommendations'.
    """
    import logging
    LOGGER = logging.getLogger(__name__)

    if not gemini_api_key:
        raise ValueError("Gemini API key is required for ATS optimization")

    # Build prompt for ATS analysis
    prompt = f"""You are an ATS (Applicant Tracking System) optimization expert.

TASK: Analyze the following LaTeX resume and job description. Provide:
1. An ATS compatibility score (0.0 to 1.0)
2. Specific recommendations to improve ATS parsing
3. An optimized version of the LaTeX resume

RESUME (LaTeX):
{tex_content}

JOB DESCRIPTION:
{job_description}

OUTPUT FORMAT (JSON):
{{
    "ats_score": <float 0.0-1.0>,
    "recommendations": ["recommendation1", "recommendation2", ...],
    "optimized_latex": "<optimized LaTeX content>"
}}

Focus on:
- Keyword matching with job description
- Standard section headings (Experience, Education, Skills)
- Avoid tables, graphics, or complex formatting
- Use standard fonts and simple layout
- Ensure contact info is parseable
"""

    try:
        import requests

        url = f"{gemini_base_url}/models/{gemini_model}:generateContent"
        headers = {"Content-Type": "application/json"}
        params = {"key": gemini_api_key}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 8192},
        }

        response = requests.post(url, headers=headers, params=params, json=payload, timeout=60)
        response.raise_for_status()

        result = response.json()
        response_text = result["candidates"][0]["content"]["parts"][0]["text"]

        # Extract JSON from response
        import json as json_mod

        json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
        if json_match:
            parsed = json_mod.loads(json_match.group())
            return {
                "ats_score": float(parsed.get("ats_score", 0.5)),
                "recommendations": parsed.get("recommendations", []),
                "optimized_content": parsed.get("optimized_latex", tex_content),
            }

        LOGGER.warning("Could not parse ATS optimization response as JSON")
        return {"ats_score": 0.5, "recommendations": ["Could not parse optimization results"], "optimized_content": tex_content}

    except Exception as exc:
        LOGGER.error("ATS optimization failed: %s", exc)
        raise RuntimeError(f"ATS optimization failed: {exc}") from exc

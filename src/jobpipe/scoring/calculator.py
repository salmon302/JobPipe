from __future__ import annotations

from dataclasses import dataclass, field
from typing import NamedTuple

from jobpipe.scoring.embeddings import cosine_similarity


class ScoreWeights(NamedTuple):
    """Configurable weights for scoring components."""
    relevance: float = 0.5
    attainability: float = 0.3
    recency: float = 0.2

    def normalize(self) -> "ScoreWeights":
        """Normalize weights to sum to 1.0."""
        total = self.relevance + self.attainability + self.recency
        if total == 0:
            return ScoreWeights(0.5, 0.3, 0.2)
        return ScoreWeights(
            relevance=self.relevance / total,
            attainability=self.attainability / total,
            recency=self.recency / total,
        )


@dataclass(frozen=True)
class ScoreBreakdown:
    relevance: float
    attainability: float
    recency: float
    total: float
    details: str = ""  # Additional details about scoring
    confidence: str = "medium"  # "high", "medium", "low"


@dataclass(frozen=True)
class SectionWeights:
    """Weights for different CV sections in relevance scoring."""
    skills: float = 0.35
    experience: float = 0.30
    education: float = 0.10
    projects: float = 0.20
    summary: float = 0.05


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _detect_job_type(title: str, description: str) -> str:
    """Detect job type for dynamic weight adjustment."""
    combined = f"{title} {description}".lower()
    if any(kw in combined for kw in ("intern", "internship", "entry", "junior", "graduate")):
        return "entry"
    if any(kw in combined for kw in ("senior", "lead", "principal", "staff", "head of", "director")):
        return "senior"
    if any(kw in combined for kw in ("research", "scientist", "researcher", "academic")):
        return "research"
    return "standard"


def select_weights_for_job_type(job_type: str) -> ScoreWeights:
    """Select dynamic weights based on job type."""
    weights = {
        "entry": ScoreWeights(relevance=0.35, attainability=0.45, recency=0.20),
        "senior": ScoreWeights(relevance=0.55, attainability=0.30, recency=0.15),
        "research": ScoreWeights(relevance=0.60, attainability=0.25, recency=0.15),
        "standard": ScoreWeights(relevance=0.50, attainability=0.30, recency=0.20),
    }
    return weights.get(job_type, weights["standard"])


def compute_confidence(
    relevance_detail: str,
    attainability_detail: str,
    cv_parsed: bool = False,
) -> str:
    """Determine confidence level based on data quality."""
    reasons: list[str] = []

    if cv_parsed:
        reasons.append("cv_parsed")
    if "No CV sections" in relevance_detail or "No valid sections" in relevance_detail:
        reasons.append("relevance_defaults")
    if "No keywords" in relevance_detail:
        reasons.append("no_keywords")
    if "No domain" in relevance_detail:
        reasons.append("no_domain")
    if "No skills" in attainability_detail or "No education" in attainability_detail:
        reasons.append("attainability_defaults")

    if not cv_parsed:
        return "low"
    if len(reasons) <= 1:
        return "high"
    if len(reasons) <= 3:
        return "medium"
    return "low"


def compute_total_match_score(
    relevance: float,
    attainability: float,
    recency: float,
    weights: ScoreWeights | None = None,
    confidence: str = "medium",
) -> ScoreBreakdown:
    """Compute total match score with configurable weights."""
    rel = _clamp01(relevance)
    att = _clamp01(attainability)
    rec = _clamp01(recency)

    if weights is None:
        weights = ScoreWeights()
    
    # Normalize weights to ensure they sum to 1.0
    norm_weights = weights.normalize()
    
    total = (rel * norm_weights.relevance) + (att * norm_weights.attainability) + (rec * norm_weights.recency)
    return ScoreBreakdown(
        relevance=rel, attainability=att, recency=rec,
        total=_clamp01(total), confidence=confidence,
    )


def compute_section_weighted_relevance(
    cv_sections: dict[str, str],
    job_description: str,
    embedder: "LocalEmbedder",
    section_weights: SectionWeights | None = None,
) -> tuple[float, str]:
    """Compute relevance score weighted by CV sections.
    
    Args:
        cv_sections: Dict with keys like 'skills', 'experience', 'education',
                     'projects', 'summary'
        job_description: Full job description text
        embedder: Embedder instance
        section_weights: Weights for each section
        
    Returns:
        Tuple of (weighted_score, details_string)
    """
    if section_weights is None:
        section_weights = SectionWeights()
    
    if not cv_sections or not job_description.strip():
        return 0.0, "No CV sections or job description"
    
    job_vector = embedder.embed_text(job_description)
    details_parts = []
    weighted_sum = 0.0
    weight_sum = 0.0
    
    section_map = {
        "skills": section_weights.skills,
        "experience": section_weights.experience,
        "education": section_weights.education,
        "projects": section_weights.projects,
        "summary": section_weights.summary,
    }
    
    for section_name, weight in section_map.items():
        if section_name not in cv_sections or not cv_sections[section_name].strip():
            continue
        
        section_vector = embedder.embed_text(cv_sections[section_name])
        similarity = cosine_similarity(section_vector, job_vector)
        similarity = max(-1.0, min(1.0, similarity))
        section_score = (similarity + 1.0) / 2.0
        
        weighted_sum += section_score * weight
        weight_sum += weight
        details_parts.append(f"{section_name}: {section_score:.3f} (w={weight})")
    
    if weight_sum == 0:
        return 0.0, "No valid sections found"
    
    final_score = weighted_sum / weight_sum
    details = ", ".join(details_parts)
    return final_score, details


def compute_blended_relevance(
    embedding_score: float,
    keyword_score: float,
    domain_score: float,
    embedding_weight: float = 0.60,
    keyword_weight: float = 0.25,
    domain_weight: float = 0.15,
) -> tuple[float, str]:
    """Blend embedding, keyword, and domain scores into a single relevance.

    Args:
        embedding_score: Section-weighted embedding similarity [0, 1].
        keyword_score: Keyword density score [0, 1].
        domain_score: Domain alignment score [0, 1].
        embedding_weight: Weight for embedding component.
        keyword_weight: Weight for keyword component.
        domain_weight: Weight for domain component.

    Returns:
        Tuple of (blended_score, details_string).
    """
    total_weight = embedding_weight + keyword_weight + domain_weight
    if total_weight == 0:
        return 0.0, "Zero weights for blending"

    blended = (
        _clamp01(embedding_score) * embedding_weight
        + _clamp01(keyword_score) * keyword_weight
        + _clamp01(domain_score) * domain_weight
    ) / total_weight

    details = (
        f"embed={embedding_score:.3f}(w={embedding_weight:.2f}) "
        f"kw={keyword_score:.3f}(w={keyword_weight:.2f}) "
        f"domain={domain_score:.3f}(w={domain_weight:.2f})"
    )
    return _clamp01(blended), details

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple


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


@dataclass(frozen=True)
class SectionWeights(NamedTuple):
    """Weights for different CV sections in relevance scoring."""
    skills: float = 0.4
    experience: float = 0.3
    education: float = 0.2
    projects: float = 0.1


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def compute_total_match_score(
    relevance: float,
    attainability: float,
    recency: float,
    weights: ScoreWeights | None = None,
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
    return ScoreBreakdown(relevance=rel, attainability=att, recency=rec, total=_clamp01(total))


def compute_section_weighted_relevance(
    cv_sections: dict[str, str],
    job_description: str,
    embedder: "LocalEmbedder",
    section_weights: SectionWeights | None = None,
) -> tuple[float, str]:
    """Compute relevance score weighted by CV sections.
    
    Args:
        cv_sections: Dict with keys like 'skills', 'experience', 'education', 'projects'
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

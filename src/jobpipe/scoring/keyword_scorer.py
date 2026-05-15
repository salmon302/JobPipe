"""Keyword density scoring for relevance enhancement.

Extracts a tiered keyword lexicon from the parsed CV and scores job
descriptions by keyword density. This complements embedding-based
relevance by capturing exact-match ATS signals.
"""

from __future__ import annotations

import re
from jobpipe.scoring.cv_parser import ParsedCV, CategorizedSkills


# Tier weights for keyword scoring
TIER_1_WEIGHT = 3.0  # Core languages
TIER_2_WEIGHT = 2.0  # Frameworks and important tools
TIER_3_WEIGHT = 1.0  # Domain terms and context


def build_keyword_lexicon(cv: ParsedCV) -> dict[str, float]:
    """Build a weighted keyword lexicon from parsed CV.

    Returns:
        Dict mapping lowercase keyword -> weight.
    """
    lexicon: dict[str, float] = {}

    # Tier 1: Core languages
    for lang in cv.skills.languages:
        lexicon[lang.lower()] = TIER_1_WEIGHT

    # Tier 2: Frameworks and infrastructure
    for fw in cv.skills.frameworks:
        lexicon[fw.lower()] = TIER_2_WEIGHT
    for tool in cv.skills.infrastructure:
        lexicon[tool.lower()] = TIER_2_WEIGHT

    # Tier 3: Domain expertise
    for domain in cv.skills.domains:
        # Split multi-word domains into individual terms
        for term in re.split(r"[,/()]", domain):
            term = term.strip().lower()
            if term and len(term) > 2:
                lexicon[term] = TIER_3_WEIGHT

    # Add tech stacks from experience and projects as Tier 2
    for tech in cv.all_tech_stacks():
        if tech not in lexicon:
            lexicon[tech] = TIER_2_WEIGHT

    return lexicon


def keyword_density_score(
    text: str,
    lexicon: dict[str, float],
) -> tuple[float, str]:
    """Compute keyword density score for a text against a weighted lexicon.

    Returns:
        Tuple of (score in [0, 1], details_string).
    """
    if not text or not lexicon:
        return 0.5, "No keywords or text"

    text_lower = text.lower()
    total_weight = sum(lexicon.values())
    if total_weight == 0:
        return 0.5, "Empty lexicon"

    matched_weight = 0.0
    matched_terms: list[str] = []

    for keyword, weight in lexicon.items():
        # Multi-word phrases: use simple substring match
        if " " in keyword:
            if keyword in text_lower:
                matched_weight += weight
                matched_terms.append(keyword)
        # Keywords with special characters (C++, C#, etc.): use broader boundary
        elif not keyword.isalnum():
            escaped = re.escape(keyword)
            pattern = re.compile(
                rf"(?:^|(?<=[\s,.;:!?(){{}}\[\]])){escaped}(?=[\s,.;:!?(){{}}\[\]]|$)",
                re.IGNORECASE,
            )
            if pattern.search(text_lower):
                matched_weight += weight
                matched_terms.append(keyword)
        # Regular alphanumeric keywords: word boundary match
        else:
            pattern = re.compile(rf"\b{re.escape(keyword)}\b", re.IGNORECASE)
            if pattern.search(text_lower):
                matched_weight += weight
                matched_terms.append(keyword)

    # Normalize: score = matched_weight / total_weight, capped at 1.0
    raw_score = matched_weight / total_weight
    score = min(1.0, raw_score)

    # Build details
    if matched_terms:
        details = f"Keywords: {', '.join(sorted(set(matched_terms)))} ({matched_weight:.1f}/{total_weight:.1f})"
    else:
        details = "No keyword matches"

    return score, details


def keyword_density_scores(
    texts: list[str],
    lexicon: dict[str, float],
) -> list[tuple[float, str]]:
    """Compute keyword density scores for multiple texts."""
    return [keyword_density_score(t, lexicon) for t in texts]
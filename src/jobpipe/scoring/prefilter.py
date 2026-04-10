from __future__ import annotations

import re


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def critical_skill_hits(text: str, critical_skills: list[str]) -> list[str]:
    normalized = _normalize(text)
    hits: list[str] = []

    for skill in critical_skills:
        skill_norm = skill.strip().lower()
        if not skill_norm:
            continue

        pattern = re.compile(rf"\b{re.escape(skill_norm)}\b")
        if pattern.search(normalized):
            hits.append(skill)

    return hits


def has_reject_terms(text: str, reject_terms: list[str]) -> bool:
    normalized = _normalize(text)

    for term in reject_terms:
        term_norm = term.strip().lower()
        if not term_norm:
            continue

        pattern = re.compile(rf"\b{re.escape(term_norm)}\b")
        if pattern.search(normalized):
            return True

    return False


def passes_prefilter(
    title: str,
    description: str,
    critical_skills: list[str],
    reject_terms: list[str],
) -> bool:
    combined = f"{title} {description}"

    if has_reject_terms(combined, reject_terms):
        return False

    return len(critical_skill_hits(combined, critical_skills)) > 0

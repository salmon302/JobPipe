from __future__ import annotations

import re

_YEARS_RANGE_RE = re.compile(r"\b(\d{1,2})\s*(?:-|to)\s*(\d{1,2})\s*\+?\s*years?\b", re.IGNORECASE)
_YEARS_SINGLE_RE = re.compile(r"\b(\d{1,2})\s*\+?\s*years?\b", re.IGNORECASE)

_REMOTE_RE = re.compile(r"\bremote|work from home|distributed\b", re.IGNORECASE)
_ONSITE_RE = re.compile(r"\bon[\s-]?site\b", re.IGNORECASE)


def extract_years_required(text: str) -> int | None:
    range_match = _YEARS_RANGE_RE.search(text)
    if range_match:
        lower = int(range_match.group(1))
        upper = int(range_match.group(2))
        return max(lower, upper)

    single_match = _YEARS_SINGLE_RE.search(text)
    if single_match:
        return int(single_match.group(1))

    return None


def infer_remote(text: str) -> bool:
    # If explicit on-site appears and remote does not, treat as local.
    if _ONSITE_RE.search(text) and not _REMOTE_RE.search(text):
        return False

    return bool(_REMOTE_RE.search(text))

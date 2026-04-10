from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScraperSelectorProfile:
    card_selector: str
    title_fallback_selectors: tuple[str, ...]
    company_selectors: tuple[str, ...]
    description_selectors: tuple[str, ...]
    posted_selectors: tuple[str, ...]
    detail_description_selectors: tuple[str, ...]
    next_page_selector: str


_DEFAULT_CARD_SELECTOR = "[data-job-id], article, li"
_DEFAULT_TITLE_FALLBACK_SELECTORS = ("h2", "h3")
_DEFAULT_POSTED_SELECTORS = ("time", "[datetime]", "[class*='date']", "[class*='posted']")
_DEFAULT_NEXT_PAGE_SELECTOR = "a[rel='next'], a[aria-label='Next'], button[aria-label='Next']"


HIRINGCAFE_SELECTOR_PROFILE = ScraperSelectorProfile(
    card_selector=_DEFAULT_CARD_SELECTOR,
    title_fallback_selectors=_DEFAULT_TITLE_FALLBACK_SELECTORS,
    company_selectors=("[data-company]", ".company", "[class*='company']"),
    description_selectors=("[data-description]", "p", ".description", "[class*='description']"),
    posted_selectors=_DEFAULT_POSTED_SELECTORS,
    detail_description_selectors=(
        "[data-job-description]",
        "[class*='job-description']",
        "[class*='description']",
        "article",
        "main",
    ),
    next_page_selector=_DEFAULT_NEXT_PAGE_SELECTOR,
)


WELLFOUND_SELECTOR_PROFILE = ScraperSelectorProfile(
    card_selector=_DEFAULT_CARD_SELECTOR,
    title_fallback_selectors=_DEFAULT_TITLE_FALLBACK_SELECTORS,
    company_selectors=(
        "[data-company]",
        "[data-testid*='company']",
        ".company",
        "[class*='company']",
    ),
    description_selectors=(
        "[data-description]",
        "[data-testid*='description']",
        "p",
        ".description",
        "[class*='description']",
    ),
    posted_selectors=_DEFAULT_POSTED_SELECTORS,
    detail_description_selectors=(
        "[data-job-description]",
        "[data-testid*='job-description']",
        "[class*='job-description']",
        "[class*='description']",
        "article",
        "main",
    ),
    next_page_selector=_DEFAULT_NEXT_PAGE_SELECTOR,
)


BUILTIN_SELECTOR_PROFILE = ScraperSelectorProfile(
    card_selector=_DEFAULT_CARD_SELECTOR,
    title_fallback_selectors=_DEFAULT_TITLE_FALLBACK_SELECTORS,
    company_selectors=(
        "[data-company]",
        "[data-testid*='company']",
        ".company",
        "[class*='company']",
    ),
    description_selectors=(
        "[data-description]",
        "[data-testid*='description']",
        "p",
        ".description",
        "[class*='description']",
    ),
    posted_selectors=_DEFAULT_POSTED_SELECTORS,
    detail_description_selectors=(
        "[data-job-description]",
        "[data-testid*='job-description']",
        "[class*='job-description']",
        "[class*='description']",
        "article",
        "main",
    ),
    next_page_selector=_DEFAULT_NEXT_PAGE_SELECTOR,
)

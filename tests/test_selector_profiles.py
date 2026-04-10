from __future__ import annotations

from jobpipe.scrapers.selector_profiles import (
    BUILTIN_SELECTOR_PROFILE,
    HIRINGCAFE_SELECTOR_PROFILE,
    WELLFOUND_SELECTOR_PROFILE,
)


def _assert_profile_shape(profile) -> None:
    assert profile.card_selector
    assert profile.next_page_selector
    assert profile.title_fallback_selectors
    assert profile.company_selectors
    assert profile.description_selectors
    assert profile.posted_selectors
    assert profile.detail_description_selectors


def test_selector_profiles_have_required_shape() -> None:
    _assert_profile_shape(HIRINGCAFE_SELECTOR_PROFILE)
    _assert_profile_shape(WELLFOUND_SELECTOR_PROFILE)
    _assert_profile_shape(BUILTIN_SELECTOR_PROFILE)


def test_selector_profiles_share_core_navigation_selectors() -> None:
    assert HIRINGCAFE_SELECTOR_PROFILE.next_page_selector == WELLFOUND_SELECTOR_PROFILE.next_page_selector
    assert WELLFOUND_SELECTOR_PROFILE.next_page_selector == BUILTIN_SELECTOR_PROFILE.next_page_selector
    assert "rel='next'" in HIRINGCAFE_SELECTOR_PROFILE.next_page_selector


def test_selector_profiles_share_posted_date_fallbacks() -> None:
    assert HIRINGCAFE_SELECTOR_PROFILE.posted_selectors == WELLFOUND_SELECTOR_PROFILE.posted_selectors
    assert WELLFOUND_SELECTOR_PROFILE.posted_selectors == BUILTIN_SELECTOR_PROFILE.posted_selectors


def test_platform_profiles_include_platform_specific_company_selectors() -> None:
    assert any("data-testid" in selector for selector in WELLFOUND_SELECTOR_PROFILE.company_selectors)
    assert any("data-testid" in selector for selector in BUILTIN_SELECTOR_PROFILE.company_selectors)
    assert any("data-company" in selector for selector in HIRINGCAFE_SELECTOR_PROFILE.company_selectors)

from __future__ import annotations

from pathlib import Path

import pytest

from jobpipe.scrapers.hiringcafe import (
    HiringCafeScraper,
    HiringCafeScraperConfig,
    async_playwright,
)


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "hiringcafe_listing_snapshot.html"

pytestmark = pytest.mark.skipif(async_playwright is None, reason="playwright is not installed")


async def _launch_browser(playwright):
    try:
        return await playwright.chromium.launch(headless=True)
    except Exception as exc:  # pragma: no cover - depends on local browser install
        pytest.skip(f"playwright chromium is unavailable: {exc}")


def _scraper(tmp_path: Path) -> HiringCafeScraper:
    return HiringCafeScraper(
        HiringCafeScraperConfig(
            base_url="https://hiring.cafe",
            storage_state=tmp_path / "state.json",
            headless=True,
            jitter_min=0.0,
            jitter_max=0.0,
            fetch_detail_descriptions=False,
        )
    )


@pytest.mark.anyio
async def test_parse_page_snapshot_extracts_expected_jobs(tmp_path) -> None:
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    scraper = _scraper(tmp_path)

    async with async_playwright() as playwright:
        browser = await _launch_browser(playwright)
        context = await browser.new_context()
        try:
            page = await context.new_page()
            await page.set_content(html)

            jobs = await scraper._parse_page(page)

            assert len(jobs) == 3

            first = jobs[0]
            assert first.id == "hiringcafe-123"
            assert first.title == "Backend Engineer"
            assert first.company == "Acme"
            assert first.url == "https://hiring.cafe/jobs/123"
            assert "Python" in first.description

            second = jobs[1]
            assert second.id.startswith("hiringcafe-")
            assert second.id != "hiringcafe-123"
            assert second.company == "Beta Labs"
            assert second.url == "https://hiring.cafe/jobs/456"

            third = jobs[2]
            assert third.id == "hiringcafe-789"
            assert third.company == "Gamma Systems"
            assert third.url == "https://hiring.cafe/jobs/789"
        finally:
            await context.close()
            await browser.close()


@pytest.mark.anyio
async def test_next_page_url_from_snapshot(tmp_path) -> None:
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    scraper = _scraper(tmp_path)

    async with async_playwright() as playwright:
        browser = await _launch_browser(playwright)
        context = await browser.new_context()
        try:
            page = await context.new_page()
            await page.set_content(html)

            next_page = await scraper._next_page_url(page)

            assert next_page == "https://hiring.cafe/jobs?page=2"
        finally:
            await context.close()
            await browser.close()

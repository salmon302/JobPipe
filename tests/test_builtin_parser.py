from __future__ import annotations

from pathlib import Path

import pytest

from jobpipe.scrapers.builtin import BuiltInScraper, BuiltInScraperConfig, async_playwright


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "builtin_listing_snapshot.html"

pytestmark = pytest.mark.skipif(async_playwright is None, reason="playwright is not installed")


async def _launch_browser(playwright):
    try:
        return await playwright.chromium.launch(headless=True)
    except Exception as exc:  # pragma: no cover - depends on local browser install
        pytest.skip(f"playwright chromium is unavailable: {exc}")


def _scraper(tmp_path: Path) -> BuiltInScraper:
    return BuiltInScraper(
        BuiltInScraperConfig(
            base_url="https://builtin.com",
            storage_state=tmp_path / "state.json",
            headless=True,
            jitter_min=0.0,
            jitter_max=0.0,
            fetch_detail_descriptions=False,
        )
    )


@pytest.mark.anyio
async def test_parse_page_snapshot_extracts_expected_builtin_jobs(tmp_path) -> None:
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
            assert first.id == "builtin-bi-1101"
            assert first.platform == "BuiltIn"
            assert first.title == "Backend Engineer"
            assert first.company == "Acorn Systems"
            assert first.url == "https://builtin.com/jobs/1101"

            second = jobs[1]
            assert second.id.startswith("builtin-")
            assert second.id != "builtin-bi-1101"
            assert second.company == "ModelWorks"
            assert second.url == "https://builtin.com/jobs/2202"

            third = jobs[2]
            assert third.id == "builtin-bi-3303"
            assert third.company == "Vertex Cloud"
            assert third.url == "https://builtin.com/jobs/3303"
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

            assert next_page == "https://builtin.com/jobs?page=2"
        finally:
            await context.close()
            await browser.close()

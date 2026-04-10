from __future__ import annotations

import asyncio
import importlib
import logging
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from jobpipe.scrapers.common import (
    DEFAULT_USER_AGENTS,
    build_job_id,
    merge_descriptions,
    normalize_long_text,
    parse_posted_datetime,
)
from jobpipe.scrapers.auth_state import UnusableStorageStateError, evaluate_platform_storage_state
from jobpipe.scrapers.selector_profiles import WELLFOUND_SELECTOR_PROFILE
from jobpipe.storage.models import JobRecord

try:
    _playwright_async_api = importlib.import_module("playwright.async_api")
    async_playwright = getattr(_playwright_async_api, "async_playwright")
except (ImportError, ModuleNotFoundError, AttributeError):
    async_playwright = None

Page = Any

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class WellfoundScraperConfig:
    base_url: str
    search_urls: tuple[str, ...]
    storage_state: Path
    headless: bool
    jitter_min: float
    jitter_max: float
    fetch_detail_descriptions: bool
    user_agents: tuple[str, ...] = tuple(DEFAULT_USER_AGENTS)
    require_usable_auth_state: bool = False


class WellfoundScraper:
    def __init__(self, config: WellfoundScraperConfig) -> None:
        self._config = config
        self._selectors = WELLFOUND_SELECTOR_PROFILE

    async def scrape(self, max_pages: int = 1) -> list[JobRecord]:
        if async_playwright is None:
            raise RuntimeError(
                "Playwright is not installed. Install dependencies and run `playwright install chromium`."
            )

        results: list[JobRecord] = []
        seen_ids: set[str] = set()

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=self._config.headless)

            user_agents = self._config.user_agents or tuple(DEFAULT_USER_AGENTS)
            context_kwargs = {"user_agent": random.choice(user_agents)}
            auth_status = evaluate_platform_storage_state(
                storage_state=self._config.storage_state,
                base_url=self._config.base_url,
            )
            if auth_status.usable:
                context_kwargs["storage_state"] = str(self._config.storage_state)
            else:
                issue_summary = "; ".join(auth_status.errors) or "unknown storage state issue"
                if self._config.require_usable_auth_state:
                    raise UnusableStorageStateError(
                        "Wellfound scraper requires a usable storage state, but none was found at "
                        f"{self._config.storage_state}: {issue_summary}. "
                        "Run `jobpipe auth-bootstrap --platform wellfound` first."
                    )

                LOGGER.warning(
                    (
                        "Storage state unavailable or unusable at %s (%s). "
                        "Continuing without auth cookies."
                    ),
                    self._config.storage_state,
                    issue_summary,
                )

            context = await browser.new_context(**context_kwargs)
            page = await context.new_page()

            search_urls = self._config.search_urls
            if not search_urls:
                search_urls = (f"{self._config.base_url.rstrip('/')}/jobs",)

            for next_url in search_urls:
                for _ in range(max_pages):
                    await page.goto(next_url, wait_until="domcontentloaded", timeout=60000)
                    await asyncio.sleep(
                        random.uniform(self._config.jitter_min, self._config.jitter_max)
                    )

                    jobs = await self._parse_page(page)
                    for job in jobs:
                        if job.id in seen_ids:
                            continue
                        seen_ids.add(job.id)
                        results.append(job)

                    maybe_next = await self._next_page_url(page)
                    if not maybe_next:
                        break
                    next_url = maybe_next

            await context.close()
            await browser.close()

        return results

    async def _parse_page(self, page: Page) -> list[JobRecord]:
        cards = await page.query_selector_all(self._selectors.card_selector)
        parsed: list[JobRecord] = []

        for card in cards:
            link = await card.query_selector("a[href]")
            if link is None:
                continue

            href = await link.get_attribute("href")
            if not href:
                continue

            title = (await link.inner_text()).strip()
            if not title:
                title = await self._first_text(card, list(self._selectors.title_fallback_selectors))
            if not title:
                continue

            company = await self._first_text(card, list(self._selectors.company_selectors))
            if not company:
                company = "Unknown"

            description = await self._first_text(card, list(self._selectors.description_selectors))
            if not description:
                description = title

            date_text = await self._first_text(card, list(self._selectors.posted_selectors))
            posted_at = parse_posted_datetime(date_text)

            url = urljoin(self._config.base_url, href)

            if self._should_fetch_detail_descriptions(page):
                detail_description = await self._fetch_detail_description(page, url)
                if detail_description:
                    description = merge_descriptions(description, detail_description)

            node_id = await card.get_attribute("data-job-id")
            job_id = self._build_job_id(node_id=node_id, url=url)

            parsed.append(
                JobRecord(
                    id=job_id,
                    platform="Wellfound",
                    title=title,
                    company=company,
                    url=url,
                    description=description,
                    date_posted=posted_at,
                )
            )

        return parsed

    def _should_fetch_detail_descriptions(self, page: Page) -> bool:
        return self._config.fetch_detail_descriptions and not page.url.startswith("about:blank")

    async def _fetch_detail_description(self, page: Page, job_url: str) -> str:
        detail_page = await page.context.new_page()
        try:
            await detail_page.goto(job_url, wait_until="domcontentloaded", timeout=45000)

            for selector in self._selectors.detail_description_selectors:
                node = await detail_page.query_selector(selector)
                if node is None:
                    continue

                text = (await node.inner_text()).strip()
                if len(text) >= 120:
                    return normalize_long_text(text)

            body_text = (await detail_page.inner_text("body")).strip()
            if body_text:
                return normalize_long_text(body_text)
        except Exception as exc:
            LOGGER.debug("Failed to enrich Wellfound description from %s: %s", job_url, exc)
        finally:
            await detail_page.close()

        return ""

    async def _first_text(self, root, selectors: list[str]) -> str:
        for selector in selectors:
            node = await root.query_selector(selector)
            if node is None:
                continue
            value = (await node.inner_text()).strip()
            if value:
                return value
        return ""

    async def _next_page_url(self, page: Page) -> str | None:
        next_link = await page.query_selector(self._selectors.next_page_selector)
        if next_link is None:
            return None

        href = await next_link.get_attribute("href")
        if href:
            return urljoin(self._config.base_url, href)

        return None

    def _build_job_id(self, node_id: str | None, url: str) -> str:
        return build_job_id("wellfound", node_id=node_id, url=url)

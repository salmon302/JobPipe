from __future__ import annotations

from typing import Protocol

from jobpipe.storage.models import JobRecord


class JobScraper(Protocol):
    async def scrape(self, max_pages: int = 1) -> list[JobRecord]:
        ...

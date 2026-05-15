Title: Detail Page Job Data Enrichment
Date: 2026-05-14T16:45:00Z
Author: Seth Nenninger (DeepSeek V4 Flash Agent)
Contribution Type: Conception
Ticket/Context: ad-hoc
Summary: Enrich auto-scraped jobs with full descriptions/metadata from sidebar detail pages.

## Problem
The auto-scraper batch extracts jobs from search result cards, which contain only title/company/URL. The rich data (full description, compensation, requirements, workplace type, location) only appears when clicking into a job's sidebar detail page (`/viewjob/...`). Without this enrichment, jobs are ingested with placeholder descriptions.

## Constraints/Analysis
- HiringCafe uses an SPA: navigating to `/viewjob/{id}` loads the detail panel client-side
- `__NEXT_DATA__` is stale after SPA navigation (only valid for server-rendered initial page)
- The server's `upsert_jobs` uses `ON CONFLICT(id) DO UPDATE SET` — re-sending with same ID enriches the row
- Background worker cache (`sentJobsCache`) blocks duplicate sends by `platform:id` — need cache-bypass for enrichment

## Proposed Solution
1. Add `extractHiringCafeDetailPage()` — extracts job title, company, posted info, location, compensation, workplace type, employment type, requirements, tools, full description, and engagement stats from the sidebar detail panel DOM
2. Add `SEND_ENRICHED_TO_SERVER` message action — sends to `/ingest` but bypasses the cache check, allowing overwrite of existing records
3. Detect detail page navigation in the auto-scraper — when URL changes to `/viewjob/...`, wait for the detail panel to render, extract rich data, and send as enrichment
4. Auto-scraper still runs batch scrape on search results page for initial collection, then enrichment happens automatically as the user clicks through jobs
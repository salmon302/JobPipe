Title: Detail Page Job Data Enrichment
Date: 2026-05-14T16:45:00Z
Author: Seth Nenninger (DeepSeek V4 Flash Agent)
Contribution Type: Implementation
Ticket/Context: ad-hoc
Summary: Auto-enrich jobs with full descriptions/metadata when navigating to sidebar detail pages.

## Task Reference
Ad-hoc request: User shared an example of HiringCafe sidebar detail page with rich data (full description, compensation, requirements, tools, location, workplace type, employment type) and asked how to add it to the auto-scraper.

## Specification Summary
When the user clicks a job card and navigates to the detail page (`/viewjob/...`), the auto-scraper should detect the richer page, extract the full job data, and send it as an enrichment (overwriting the placeholder data from the card batch extraction).

## Implementation Notes

### Files Changed

**`extension/content/content_script.js`** — New functions added:
1. `extractHiringCafeDetailPage()` — DOM-based extraction of all rich fields from sidebar detail panel: title, company, posted_ago, location, compensation, workplace_type, employment_type, full description, requirements, technical tools, and engagement stats
2. `tryExtractDetailPage()` — Simple wrapper that checks hostname and pathname
3. `handleDetailEnrichment()` — Message handler for `ENRICH_CURRENT_JOB` action
4. Modified `extractBatchJobs()` — Now detects `/viewjob/` path and calls detail page extractor
5. Modified `attemptAutoScrape()` — Shows "Enriching..." status on detail pages, "Enriched ✓" on success

**`extension/background/service_worker.js`** — New handler:
1. `SEND_ENRICHED_TO_SERVER` message action registered in listener
2. `handleSendEnrichedToServer()` — Sends enriched data to `/ingest`, adds to session cache
3. Modified `handleSendBatchToServer()` — Allows `enriched: true` jobs through cache filter

### How It Works
1. **Batch scrape** runs on search results pages, collecting title/company/URL from cards
2. User **clicks a card**, SPA navigates to `/viewjob/{id}`
3. Auto-scraper detects URL change, calls `extractBatchJobs()` → sees `/viewjob/` path → calls `extractHiringCafeDetailPage()`
4. Enriched single job (with full description, compensation, requirements, location, etc.) is sent to server
5. Server's `ON CONFLICT(id) DO UPDATE` overwrites the placeholder record with the full data
6. Background worker's cache allows enriched jobs through (unlike regular duplicates)

### Verification Steps
- [ ] Load HiringCafe search results page → verify batch scrape runs (collects card data)
- [ ] Click a job card → verify "Enriching..." shows in overlay, then "Enriched ✓"
- [ ] Check server database: the job should now have full description, compensation, location, etc.
- [ ] Check browser console for `JobPipe: Detail page extracted` logs
- [ ] Click multiple jobs → each should enrich independently
- [ ] Navigate back to search results → batch collection resumes

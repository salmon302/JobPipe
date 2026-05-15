Title: Fix Detail Page Auto-Scrape Enrichment
Date: 2026-05-14T17:30:00Z
Author: Seth Nenninger (DeepSeek V4 Flash Agent)
Contribution Type: Implementation
Ticket/Context: ad-hoc
Summary: Fixed auto-scrape enrichment to use __NEXT_DATA__ for rich job data instead of DOM-based detail page extraction.

## Task Reference
User reported: "When I click a job card, we not seeming to auto scrape the detail page"

## Root Cause
The `extractBatchJobs()` function was using DOM-only extraction (`extractHiringCafeJobsFromDom()`) which only gets minimal card data (title, company, URL). The `__NEXT_DATA__` script tag on the search results page already contains **full rich data** (descriptions, compensation, requirements, location, etc.) for every job, but `extractJobsFromNextData()` was never being called during batch scraping.

Additionally, the detail page DOM extractor (`extractHiringCafeDetailPage()`) was unreliable because HiringCafe uses a sidebar panel that doesn't match the expected DOM structure.

## Changes Made

**`extension/content/content_script.js`**:
1. Modified `extractBatchJobs()` to try `__NEXT_DATA__` first (rich data for all jobs), falling back to DOM extraction only when `__NEXT_DATA__` is empty (SPA navigation)
2. For detail pages (`/viewjob/...`), also try `__NEXT_DATA__` first, then fall back to DOM detail extraction

## How It Works Now
1. **Search results page (initial load)**: `__NEXT_DATA__` has full rich data for all jobs → extracted with descriptions, compensation, requirements, etc.
2. **Search results page (SPA navigation)**: `__NEXT_DATA__` is stale → falls back to DOM card extraction (basic data)
3. **Detail page (`/viewjob/...`)**: `__NEXT_DATA__` may have the job → extracts rich single job data

## Verification
- [ ] Load HiringCafe search results page → check console for "Found X job hits in __NEXT_DATA__" and "Description length: XXXX"
- [ ] Verify jobs sent to server have full descriptions (not truncated)
- [ ] Click a job card → verify detail page extraction works

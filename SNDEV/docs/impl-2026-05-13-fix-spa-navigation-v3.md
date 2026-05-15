Title: Fix SPA navigation scraping on HiringCafe (v3)
Date: 2026-05-13T23:50:00Z
Author: Seth Nenninger (GitHub Copilot Agent)
Contribution Type: Implementation
Ticket/Context: SPA next-page detection failing, refresh still required
Summary: Fixed DOM extraction selectors and eliminated reliance on stale __NEXT_DATA__ for polling

## Task Reference
User discovery: Initial scraping -> success -> next page -> fail -> REFRESH -> works.
Root cause chain:
1. __NEXT_DATA__ script tag is NEVER updated during SPA navigation (Next.js SSR-only)
2. `extractHiringCafeJobsFromDom()` was using broken DOM selectors (`[class*="job-card"]`)
3. Polling found "jobs" immediately via stale __NEXT_DATA__ and stopped polling
4. DOM-only fallback used fragile parent-walking with wrong depth

## Implementation Notes

### Files Changed:
1. **extension/content/content_script.js**
   - Rewrote `extractHiringCafeJobsFromDom()` to use correct DOM selectors:
     - Finds `a[href*="/viewjob/"]` links (actual job posting links)
     - Uses `link.closest()` instead of arbitrary parent-walking
     - Extracts titles via `.font-bold.line-clamp-2, .font-bold.line-clamp-3`
     - Extracts companies via `.line-clamp-3.font-light > .font-bold`
   - Rewrote `extractBatchJobs()` for HiringCafe:
     - Calls `extractHiringCafeJobsFromDom()` first (always works)
     - Enriches with __NEXT_DATA__ when available (adds full job metadata)
   - Fixed variable shadowing bug (`const jobs = ...` inside `extractBatchJobs`)

### Key Technical Details:
- **`__NEXT_DATA__` is NEVER updated during SPA navigation** — it's an SSR optimization that only changes on full page loads. After any client-side navigation, it still holds the original page data.
- **DOM extraction must be the primary method** — the DOM always reflects the current page state, whether initial load or after SPA navigation.
- **`link.closest()` is reliable** — it walks up the DOM tree until it finds a matching ancestor, regardless of depth.
- **`__NEXT_DATA__` enrichment is optional** — still useful for initial loads to get rich job data (description, compensation, etc.), but not relied upon for job detection.

### Verification Steps:
1. Load extension in Chrome (chrome://extensions → Reload)
2. Navigate to https://hiring.cafe and perform a search
3. First page should scrape — check console for "JobPipe: DOM extracted X jobs"
4. Click "Next page" or page 2/3 — polling should detect new DOM jobs
5. Check server logs — should see jobs from each page

### Evidence Links:
- Server log shows 73 jobs from a previous search: "0 inserted, 73 updated"
- Root cause: __NEXT_DATA__ returned stale SSR data, DOM fallback was never reached
- Fixed functions: extractHiringCafeJobsFromDom(), extractBatchJobs()

## Quality Gate Results
- Build: Not applicable (Manifest V3 extension, no build step)
- Lint: Manual review of code changes
- Typecheck: Not applicable (JavaScript)
- Tests: Manual testing required in Chrome

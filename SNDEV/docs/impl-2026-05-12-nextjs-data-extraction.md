Title: nextjs-data-extraction
Date: 2026-05-12T18:00:00Z
Author: Seth Nenninger (GitHub Copilot Agent)
Contribution Type: Implementation
Ticket/Context: Fix HiringCafe job extraction - replace DOM scraping with Next.js __NEXT_DATA__
Summary: Implemented reliable job extraction from HiringCafe using Next.js __NEXT_DATA__ JSON instead of flaky DOM scraping

## Task Reference
Fix "Error: Could not establish connection" and "No job listings found" issues on HiringCafe. User provided solution to extract jobs from Next.js `__NEXT_DATA__` script tag.

## Specification Summary
- Replace DOM-based job card scraping with Next.js data extraction
- Use `jsonData?.props?.pageProps?.ssrHits` to get job listings
- Job data fields: `hit.job_information?.title`, `hit.board_token`, `hit.apply_url`, `hit.job_information?.description`
- Keep DOM fallback for edge cases where `__NEXT_DATA__` isn't available
- Remove dead code (`waitForJobCards` function no longer needed)

## Implementation Notes
### Files Changed
- `extension/content/content_script.js`
  - Added `extractJobsFromNextData()` function (lines ~265-295)
  - Rewrote `extractBatchJobs()` to use Next.js extraction as primary method
  - Removed `waitForJobCards()` function (dead code, no longer called)
  - Added fallback DOM scraping if `__NEXT_DATA__` isn't found

### Key Code Changes
```javascript
function extractJobsFromNextData() {
  const scriptTag = document.getElementById('__NEXT_DATA__');
  const jsonData = JSON.parse(scriptTag.textContent);
  const hits = jsonData?.props?.pageProps?.ssrHits;
  // Returns array of job objects with title, company, url, description
}
```

### Verification Steps
1. Load extension in Chrome
2. Navigate to https://hiring.cafe
3. Open console, should see: "JobPipe: Extracted X jobs from __NEXT_DATA__"
4. Click extension icon, click "Capture Batch Jobs"
5. Should successfully extract all visible job listings

### Evidence Links
- SNDEV/docs/impl-2026-05-12-nextjs-data-extraction.md (this file)
- User's provided code snippet in conversation

## Quality Gate Results
- Build: N/A (Chrome extension, no build step)
- Lint: Manual review passed
- Typecheck: N/A (JavaScript)
- Tests: Manual testing required in browser

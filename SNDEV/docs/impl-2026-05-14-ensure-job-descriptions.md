Title: Ensure Job Descriptions Are Properly Scraped
Date: 2026-05-14T16:30:00Z
Author: Seth Nenninger (DeepSeek V4 Flash Agent)
Contribution Type: Implementation
Ticket/Context: ad-hoc
Summary: Fixed job description truncation, added fallback description sources, and added debug logging to verify description capture.

## Task Reference
Ad-hoc request: "We need to ensure we're scraping job descriptions"

## Specification Summary
Audit the full pipeline (content script → background worker → ingest server → database) to ensure job descriptions are being captured with meaningful content, not truncated or empty.

## Implementation Notes

### Changes Made

**`extension/content/content_script.js`** (3 changes):

1. **Removed 2000-char truncation** in `buildHiringCafeJobFromHit()`:
   - Changed `description: decodeHtmlEntities(jobInfo.description || '').substring(0, 2000)` to `description: decodeHtmlEntities(jobInfo.description || '')`
   - Full descriptions are now preserved end-to-end

2. **Added `processed.description` fallback** in `buildHiringCafeJobFromHit()`:
   - Changed to `description: decodeHtmlEntities(jobInfo.description || processed.description || '')`
   - Catches cases where the description lives in `v5_processed_job_data.description` instead of `job_information.description`

3. **Improved DOM batch extraction** in `extractHiringCafeJobsFromDom()`:
   - Replaced placeholder description (`${title} at ${company}`) with actual card text content extraction
   - Added debug logging for description lengths in batch extraction

4. **Added debug logging** in `extractJobsFromNextData()`:
   - Logs description length and first 100 chars for first 3 jobs to verify content

### Verification Steps
- [ ] Load HiringCafe job listing page, check console for "Description length" logs
- [ ] Capture a single job and verify full description arrives at server
- [ ] Run batch scrape and verify descriptions are non-empty
- [ ] Check database for stored description content

### Pipeline Audit Summary
| Stage | Description Handling | Status |
|-------|-------------------|--------|
| Content script (single capture) | `jobInfo.description` from `__NEXT_DATA__` | ✅ Full text now |
| Content script (batch DOM) | Card text content | ✅ Improved, but limited by card view |
| Background worker | Forwards `description` field as-is | ✅ No truncation |
| Ingest server | `_build_job_record` uses `description` or falls back to `_compose_description` | ✅ Proper fallback |
| Database model | `description: str` (required field) | ✅ Stored as text |
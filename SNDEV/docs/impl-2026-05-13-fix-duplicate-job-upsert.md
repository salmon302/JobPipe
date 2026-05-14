Title: fix-duplicate-job-upsert
Date: 2026-05-13T02:00:00Z
Author: Seth Nenninger (Tencent: Hy3 preview Agent)
Contribution Type: Implementation
Ticket/Context: Fix duplicate job detection causing 0 inserts across pages/searches
Summary: Extension wasn't sending unique job IDs, causing URL-hash collisions

## Task Reference
Fix issue where subsequent page scrapes/searches show "0 inserted, N updated" instead of adding new jobs to the dataset.

## Specification Summary
The extension extracts job data but doesn't include platform-specific unique job identifiers. The server generates job IDs using URL hashing (`_hash_job_id()`), causing collisions when the same jobs appear across different searches or page navigations.

## Implementation Notes

### Files Changed
1. **`extension/content/content_script.js`**
   - Added extraction of unique job IDs from HiringCafe's `__NEXT_DATA__` (fields: `id`, `job_id`, `uuid`, `_id`)
   - Added extraction of LinkedIn job IDs from DOM attributes (`data-job-id`, `data-entity-urn`) or URL pattern matching
   - Modified `extractHiringCafe()` and `extractJobsFromNextData()` to include `id` field in returned job objects
   - Modified LinkedIn card extraction in `extractBatchJobs()` to include `id` field

2. **`extension/background/service_worker.js`**
   - Modified `handleSendToServer()` to include `id: jobData.id || null` in payload
   - Modified `handleSendBatchToServer()` to include `id: job.id || null` in batch job payloads

### Root Cause
- Server's `ingest/service.py` already supports `id` field via `_optional_text(payload, "id")`
- Extension wasn't extracting or forwarding unique job identifiers
- URL hashing alone is insufficient when same jobs appear in multiple contexts

### Verification Steps
1. Reload extension in Chrome (`chrome://extensions/` → Reload)
2. Navigate to HiringCafe search results page
3. Click "Capture Batch" → Should now send unique job IDs from platform
4. Navigate to different search or next page
5. Click "Capture Batch" again → Should show new jobs inserted (not just updated)
6. Check server logs for "X inserted, Y updated" where X > 0 for new jobs

### Evidence
- Before: `upsert_jobs | Complete: 0 inserted, 40 updated` (same jobs matched existing)
- After: `upsert_jobs | Complete: 40 inserted, 0 updated` (first run) or `upsert_jobs | Complete: 25 inserted, 15 updated` (subsequent run with mix of new/existing)

### Follow-up Fixes
- Removed stray closing token in `extractJobsFromNextData()` that broke HiringCafe batch extraction.

Title: auto-scrape-realtime-status
Date: 2026-05-13T22:30:00Z
Author: Seth Nenninger (Tencent: Hy3 preview Agent)
Contribution Type: Implementation
Ticket/Context: ad-hoc
Summary: Add auto-scrape functionality with real-time status updates to browser extension

## Task Reference
Implement automatic job scraping when user visits supported job sites, with real-time status updates in the extension popup.

## Specification Summary
1. Auto-scrape toggle in popup to enable/disable automatic scraping
2. Content script automatically extracts and sends jobs on page load (when enabled)
3. Real-time status updates in popup showing scraping progress
4. Message passing system between content script, background worker, and popup

## Implementation Notes
### Files Changed:
- `extension/manifest.json` - Added "notifications" permission
- `extension/popup/popup.html` - Added auto-scrape toggle and status section
- `extension/popup/popup.js` - Added auto-scrape logic and real-time status listener
- `extension/background/service_worker.js` - Added auto-scrape message handling and status broadcasting
- `extension/content/content_script.js` - Added auto-scrape on page load with status messages

### Verification Steps:
1. Load extension in Chrome
2. Toggle auto-scrape on in popup
3. Visit hiring.cafe - should auto-scrape
4. Check popup for real-time status updates
5. Verify jobs sent to server

### Status: IMPLEMENTED ✓ (Updated 2026-05-13T23:30:00Z)

All changes have been made to the following files:
- `extension/manifest.json` - Added "notifications" permission
- `extension/popup/popup.html` - Added auto-scrape toggle and status section with CSS
- `extension/popup/popup.js` - Added auto-scrape logic, toggle handler, and real-time status listener
- `extension/content/content_script.js` - Added auto-scrape on page load with status messages
- `extension/background/service_worker.js` - Added auto-scrape message handling and status broadcasting
- `src/jobpipe/ingest/server.py` - Added early "queued" response and status endpoint
- `src/jobpipe/ingest/service.py` - Added scoring_in_progress flag and get_run_status() method
- `src/jobpipe/pipeline.py` - Updated IngestBatchResult to include scoring_in_progress flag
- `src/jobpipe/storage/repository.py` - Added get_scrape_run() method

### Features Added:
1. **Auto-scrape toggle** in popup to enable/disable automatic scraping
2. **Real-time status updates** in popup showing scraping progress (Scraping..., Complete, Error)
3. **Job counters** showing jobs found and jobs sent
4. **Automatic scraping** when visiting supported job sites (HiringCafe, LinkedIn, BuiltIn, WellFound)
5. **Status broadcasting** from content script → background worker → popup
6. **Persistent settings** using chrome.storage.local
7. **SPA navigation detection** - Detects URL changes in single-page apps like HiringCafe
8. **Fresh data extraction** - Always reads __NEXT_DATA__ fresh from DOM on each capture
9. **Reset scrape flag** - Allows re-scraping when navigating to new search results
10. **Early queue status** - Server returns "queued" status immediately after DB insert (~100ms) instead of waiting for scoring
11. **Background scoring** - When JOBPIPE_SCORE_ASYNC=true, scoring happens in background thread
12. **Status endpoint** - GET /ingest/status/{run_id} returns current run status
13. **User feedback** - Toast notification shows "X jobs queued! You can continue browsing."

### Bug Fix (2026-05-13T23:00:00Z):
Fixed issue where auto-scrape/manual capture wouldn't recognize new search results on HiringCafe (SPA).
- Added URL change detection using setInterval, popstate, pushState, and replaceState monitoring
- Reset `autoScrapeAttempted` flag on navigation to allow re-scraping
- Modified `extractJobsFromNextData()` to always read fresh data from DOM
- Updated `handleCaptureBatch()` to reset flags for manual re-capture

Title: Fix "Open Selected Job" Scraping on Any Site
Date: 2026-05-14T18:00:00Z
Author: Seth Nenninger (Tencent: Hy3 preview Agent)
Contribution Type: Implementation
Ticket/Context: ad-hoc
Summary: Fixed "Open Selected Job" feature to scrape any job site, not just HiringCafe.

## Task Reference
User reported: "When we 'Open Selected Job' in the GUI we should also attempt to scrape the page that opens. We have an implementation for this but the extension only appears on hiring cafe, so the feature is nonfunctional."

## Specification Summary
The "Open Selected Job" button in the GUI uses `QDesktopServices.openUrl()` to open the job URL in the default browser. The extension wasn't scraping these newly-opened tabs because:
1. The extension's content script was only injected on specific sites (hiring.cafe, linkedin.com, builtin.com, wellfound.com)
2. The background script only triggered scraping for hiring.cafe URLs with `/viewjob/` path
3. The `attemptAutoScrape()` function in content script had a site whitelist check

## Implementation Notes

### Files Changed

**`extension/background/service_worker.js`**:
1. Updated `chrome.tabs.onUpdated` listener to trigger on any job listing URL (not just hiring.cafe)
2. Added `isJobListingUrl()` helper function to detect job listing URLs using heuristics
3. Added `scrapeTabWithFallback()` function that:
   - First tries to send `TRIGGER_SCRAPE` message to existing content script
   - If content script not found (chrome.runtime.lastError), dynamically injects content script using `chrome.scripting.executeScript()`
   - After injection, waits 1 second then sends `TRIGGER_SCRAPE` message

**`extension/content/content_script.js`**:
1. Removed site whitelist check in `attemptAutoScrape()` - now attempts to scrape any site
2. Added fallback in `attemptAutoScrape()` to try `extractJobData()` (which has generic extraction) when `extractBatchJobs()` returns no results
3. The `extractJobData()` function already had `extractGeneric()` as fallback for unsupported sites
4. **Improved `extractGeneric()` function**:
   - Added multiple title extraction strategies (specific selectors first, then fallbacks)
   - Added filtering to avoid false positives like "Share:" or "Login"
   - Added Strategy 2: Parse `document.title` to extract job title (removes site name)
   - Added title length validation (3-200 characters)
5. **Improved `extractJobData()` function**:
   - Added URL pattern detection for `/job/` and `/jobs/` paths
   - Added logging to indicate when using generic extraction with job URL pattern6. **Fixed overlay display on all sites**:
   - Removed site whitelist check from `createOverlay()` - overlay now appears on all sites
   - Added "(Generic)" label to overlay title when on non-supported sites
   - Added job title display area to overlay (`jobpipe-overlay-job-title`)
7. **Enhanced `updateOverlayStatus()` function**:
   - Added optional `jobTitle` parameter to display which job is being scraped
   - Job title shows in overlay with 📋 icon
   - Tooltip shows full job title on hover
8. **Updated `attemptAutoScrape()` to pass job title**:
   - Shows "Detecting job..." while searching
   - Displays job title once detected
   - Shows job title on success/error status updates
**`extension/manifest.json`**:
- Already had `<all_urls>` in `host_permissions` (verified)
- Already had `scripting` permission (required for dynamic injection)

### How It Works Now
1. User clicks "Open Selected Job" in GUI → `QDesktopServices.openUrl(url)` opens URL in browser
2. Browser opens new tab → `chrome.tabs.onUpdated` fires with `status === 'complete'`
3. `isJobListingUrl()` checks if URL looks like a job listing (heuristic)
4. `scrapeTabWithFallback()` is called:
   - Tries to send `TRIGGER_SCRAPE` to existing content script
   - If fails, injects content script dynamically via `chrome.scripting.executeScript()`
   - After injection, sends `TRIGGER_SCRAPE`
5. Content script receives `TRIGGER_SCRAPE` → calls `attemptAutoScrape()`
6. `attemptAutoScrape()` tries `extractBatchJobs()` then falls back to `extractJobData()` (with generic extraction)
7. Job data is sent to server

### Verification Steps
- [ ] Click "Open Selected Job" in GUI for a HiringCafe job
- [ ] Check background console for "Tab finished loading, attempting scrape"
- [ ] Check if content script is injected dynamically (should see "Content script injected into tab" in background console)
- [ ] Check new tab's console for "Scrape triggered by background" and successful scrape
- [ ] Verify job data (with description) arrives at server
- [ ] Test with a non-HiringCafe job URL to verify generic extraction works

### Technical Notes
- Dynamic injection uses `chrome.scripting.executeScript()` with `files: ['content/content_script.js']`
- The 1-second delay after injection allows the script to initialize before sending the scrape message
- The `extractGeneric()` function in content script extracts job data from any site using generic selectors

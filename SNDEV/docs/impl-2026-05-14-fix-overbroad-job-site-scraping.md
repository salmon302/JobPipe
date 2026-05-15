Title: Fix Overbroad Job Site Scraping from All Sites
Date: 2026-05-14T19:30:00Z
Author: Seth Nenninger (DeepSeek V4 Flash Agent)
Contribution Type: Implementation
Ticket/Context: ad-hoc
Summary: Fixed "Open Selected Job" scraping that was scraping ALL tabs with job-like URLs instead of only newly-created tabs.

## Task Reference
User reported: "Our job scraper is scraping from ALL sites due to our implementation to scrape jobs from clicking 'Open Selected Job', when it should only apply onto that particular opened site."

## Specification Summary
The prior fix for "Open Selected Job" scraping introduced a bug: the `chrome.tabs.onUpdated` listener used a broad heuristic (`isJobListingUrl()`) that triggered scraping on ANY tab whose URL contained "job", "career", "position", etc. — not just tabs that were newly opened by the GUI's `QDesktopServices.openUrl()`. This caused scraping from existing tabs and unrelated site navigation.

## Implementation Notes

### Files Changed

**`extension/background/service_worker.js`**:
1. **Removed `isJobListingUrl()` function** — the heuristic (checking URL for "job", "career", "position", "/jobs/", "/viewjob/") was overly broad and caused scraping on all sites.
2. **Updated `chrome.tabs.onCreated.addListener()`** — now tracks ALL newly created tabs (not just those with `openerTabId`), since `QDesktopServices.openUrl()` from an external process doesn't set `openerTabId`. Added a 30-second cleanup timeout to avoid scraping stale/reloaded tabs.
3. **Updated `chrome.tabs.onUpdated.addListener()`** — condition changed from `openedTabIds.has(tabId) || isJobListingUrl(tab.url)` to just `openedTabIds.has(tabId)`. Only tabs that were freshly created will be scraped.

### How It Works Now
1. User clicks "Open Selected Job" in GUI → `QDesktopServices.openUrl(url)` opens URL in browser
2. `chrome.tabs.onCreated` fires → tab ID is added to `openedTabIds` set
3. `chrome.tabs.onUpdated` fires with `status === 'complete'` → checks if tab is in `openedTabIds`
4. If it is, triggers `scrapeTabWithFallback(tabId)` to attempt extraction
5. If the tab isn't one that was just created (e.g., user manually navigated), no scraping occurs
6. After 30 seconds, the tab ID is automatically removed from the set

### Verification Steps
- [ ] Click "Open Selected Job" in GUI → verify scraping occurs only on the newly opened tab
- [ ] Navigate to any job site manually → verify no automatic scraping
- [ ] Refresh an existing tab with a job URL → verify no automatic scraping
- [ ] Open a new tab and manually type a job URL → verify no automatic scraping

### Technical Notes
- The 30-second cleanup timeout prevents memory leaks from stale tab IDs
- This approach is safe because `QDesktopServices.openUrl()` always opens a new tab (not reusing existing ones)
- The `scrapeTabWithFallback()` function with dynamic content script injection still works as before

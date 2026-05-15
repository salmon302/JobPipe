Title: Auto-Scrape on "Open Selected Job" Tab
Date: 2026-05-14T17:45:00Z
Author: Seth Nenninger (DeepSeek V4 Flash Agent)
Contribution Type: Implementation
Ticket/Context: ad-hoc
Summary: When "Open Selected Job" opens a new browser tab, the extension now automatically scrapes that tab's job data.

## Task Reference
User requested: "When we 'Open Selected Job' we should also attempt to scrape the page that opens"

## Specification Summary
The GUI's "Open Selected Job" button uses `QDesktopServices.openUrl()` to open the job URL in the default browser. The extension wasn't scraping these newly-opened tabs because:
1. The extension's auto-scraper only fires on SPA navigation within an already-open tab
2. New tabs opened from outside the extension context aren't tracked

## Implementation Notes

### Files Changed

**`extension/background/service_worker.js`**:
1. Added `openedTabIds` Set to track tabs opened by our extension
2. Added `chrome.tabs.onCreated` listener — detects when a tab is opened with `openerTabId` set (meaning our extension opened it)
3. Added `chrome.tabs.onUpdated` listener — when a tracked tab finishes loading (`status === 'complete'`), sends `TRIGGER_SCRAPE` message to that tab's content script

**`extension/content/content_script.js`**:
1. Added `TRIGGER_SCRAPE` message handler — calls `attemptAutoScrape()` if not already attempted

**`extension/manifest.json`**:
1. Added `"tabs"` to `permissions` array (required for `chrome.tabs.onCreated` and `chrome.tabs.onUpdated`)

### How It Works
1. User clicks "Open Selected Job" in GUI → `QDesktopServices.openUrl(url)` opens URL in browser
2. Browser opens new tab → `chrome.tabs.onCreated` fires, sees `openerTabId` is set → adds tab ID to `openedTabIds`
3. New tab finishes loading → `chrome.tabs.onUpdated` fires with `status === 'complete'` → sends `TRIGGER_SCRAPE` to that tab
4. Content script receives `TRIGGER_SCRAPE` → calls `attemptAutoScrape()` → scrapes job data and sends to server

### Verification Steps
- [ ] Click "Open Selected Job" in GUI
- [ ] Check background console for "Tracking opened tab" and "Triggering scrape on opened tab"
- [ ] Check new tab's console for "Attempting auto-scrape" and successful scrape
- [ ] Verify job data (with description) arrives at server

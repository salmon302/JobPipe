Title: Mark Generic Site as Not a Job Board
Date: 2026-05-15T10:00:00Z
Author: Seth Nenninger (Tencent: Hy3 preview Agent)
Contribution Type: Implementation
Ticket/Context: ad-hoc
Summary: Allow users to mark generic sites as not job boards to prevent unnecessary scraping.

## Task Reference
User request: When JobPipe (generic) is active, allow user to mark site as not a job board to prevent unneeded scraping.

## Specification Summary
- Add persistent storage for excluded hostnames (sites marked as not job boards)
- Modify content script to check excluded list before attempting any scrape
- Add UI in popup to mark current site as excluded when on generic site
- Skip auto-scrape and disable capture buttons for excluded sites

## Implementation Notes
### Files Changed
1. `extension/popup/popup.js` - Add exclude button and storage logic
2. `extension/content/content_script.js` - Check excluded list before scraping
3. `extension/background/service_worker.js` - Optional: Sync excluded list if needed

### Verification Steps
- [ ] Navigate to a generic site (non-job board)
- [ ] Open popup, click "Mark as not a job board"
- [ ] Reload page, verify no auto-scrape occurs
- [ ] Try manual capture, verify button is disabled or shows message
- [ ] Check chrome.storage.local for excluded hostname

### Technical Notes
- Uses `chrome.storage.local` to persist excluded hostnames
- Excluded list is checked in content script before `attemptAutoScrape()`
- Popup dynamically shows/hides exclude button based on current site status

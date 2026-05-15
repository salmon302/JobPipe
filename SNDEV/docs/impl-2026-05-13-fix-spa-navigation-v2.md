Title: Fix SPA navigation scraping on HiringCafe (v2)
Date: 2026-05-13T23:30:00Z
Author: Seth Nenninger (Tencent: Hy3 preview Agent)
Contribution Type: Implementation
Ticket/Context: User discovered initial scrape works, next page fails, refresh fixes it
Summary: Fixed SPA navigation by polling for job signature changes instead of relying on fixed timeouts or MutationObservers

## Task Reference
User discovery: Initial scraping -> success -> next page in search -> fail -> REFRESH PAGE -> 2nd page success.
Root cause: SPA navigation (client-side routing) doesn't properly trigger re-extraction because Next.js hasn't updated __NEXT_DATA__ or rendered new job cards within the fixed timeout.

## Specification Summary
Implement robust SPA navigation detection using job signature polling:
1. Track job signature (URL + first few job IDs from __NEXT_DATA__)
2. Poll for signature changes when navigation detected
3. Wait for actual new data before scraping

## Implementation Notes

### Files Changed:
1. **extension/content/content_script.js**
   - Added `getJobSignature()` function to create signature from URL + job IDs
   - Added `pollForNewData()` function to poll for signature changes (up to 8 seconds)
   - Added `lastJobSignature` variable to track previous state
   - Modified `attemptAutoScrape()` to call `pollForNewData()` before extracting
   - Simplified navigation handlers to reset `lastJobSignature = null`
   - Removed complex MutationObserver approach (unreliable for Next.js)

### Key Technical Details:
- **Job Signature**: Combines `window.location.href` with first 5 job IDs from `__NEXT_DATA__` 
- **Polling mechanism**: Checks signature every 500ms, waits up to 8000ms for change
- **Navigation detection**: URL change (setInterval) + pushState/popstate/replaceState
- **Reset on navigation**: Setting `lastJobSignature = null` forces fresh detection

### Verification Steps:
1. Load extension in Chrome (reload from chrome://extensions)
2. Navigate to https://hiring.cafe and search
3. First page should scrape automatically
4. Click "Next page" - should see "JobPipe: Polling for new data"
5. After page loads, should see "JobPipe: New job data detected!"
6. Auto-scrape should trigger and find new jobs
7. Check server logs for new job insertions (not just updates)

### Evidence Links:
- User discovery: "Initial scraping -> success -> next page in search -> fail -> REFRESH PAGE -> 2nd page success"
- Server logs show: First batch 0 inserted/53 updated, Second batch 21 inserted/0 updated
- Modified functions: getJobSignature(), pollForNewData(), attemptAutoScrape()
- Key change: Polling for actual data changes vs fixed timeouts

## Quality Gate Results
- Build: Not applicable (Manifest V3 extension, no build step)
- Lint: Manual review of code changes
- Typecheck: Not applicable (JavaScript)
- Tests: Manual testing required in Chrome

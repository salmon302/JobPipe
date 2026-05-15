Title: Fix SPA navigation scraping on HiringCafe
Date: 2026-05-13T18:30:00Z
Author: Seth Nenninger (Tencent: Hy3 preview Agent)
Contribution Type: Implementation
Ticket/Context: User discovered initial scrape works, next page fails, refresh fixes it
Summary: Fixed SPA navigation detection on HiringCafe by adding MutationObserver to watch for __NEXT_DATA__ updates and DOM changes

## Task Reference
User discovery: Initial scraping -> success -> next page in search -> fail -> REFRESH PAGE -> 2nd page success.
Root cause: SPA navigation (client-side routing) doesn't properly trigger re-extraction because Next.js hasn't updated __NEXT_DATA__ or rendered new job cards within the fixed 1500ms timeout.

## Specification Summary
Implement robust SPA navigation detection using MutationObserver to watch for:
1. Changes to __NEXT_DATA__ script tag content (indicates new data loaded)
2. New job cards appearing in the DOM (indicates rendering complete)

Also improved attemptAutoScrape() to poll for job data instead of using fixed timeout.

## Implementation Notes

### Files Changed:
1. **extension/content/content_script.js**
   - Added `setupHiringCafeObservers()` function to create MutationObservers
   - Added `nextDataObserver` to watch for __NEXT_DATA__ script tag changes
   - Added `domObserver` to watch for new job cards in `<main>` element
   - Modified `attemptAutoScrape()` to poll for job data with 500ms intervals (max 5 seconds)
   - Added initialization call `setupHiringCafeObservers()` at script load
   - Enhanced navigation handlers (pushState/replaceState/popstate) to call `setupHiringCafeObservers()` for new pages

### Key Technical Details:
- **MutationObserver for __NEXT_DATA__**: Watches for characterData changes in the script tag, triggers scrape when content changes
- **MutationObserver for DOM**: Watches for new nodes added to `<main>`, checks if they contain job cards or links
- **Polling in attemptAutoScrape**: Instead of fixed 2000ms delay, now polls every 500ms for up to 5000ms until jobs are found
- **Fallback URL polling**: Kept setInterval as fallback for navigations that don't trigger observers

### Verification Steps:
1. Load extension in Chrome
2. Navigate to https://hiring.cafe
3. Perform initial search - should scrape successfully
4. Click "Next page" or navigate to new search results
5. Should see "JobPipe: __NEXT_DATA__ updated, triggering scrape" or "New job cards detected in DOM"
6. Auto-scrape should trigger and find jobs without manual refresh
7. Check console for polling messages showing job detection

### Evidence Links:
- User discovery: "Initial scraping -> success -> next page in search -> fail -> REFRESH PAGE -> 2nd page success"
- Modified functions: setupHiringCafeObservers(), attemptAutoScrape()
- Observers watch: __NEXT_DATA__ script tag, main element for job cards

## Quality Gate Results
- Build: Not applicable (Manifest V3 extension, no build step)
- Lint: Manual review of code changes
- Typecheck: Not applicable (JavaScript)
- Tests: Manual testing required in Chrome

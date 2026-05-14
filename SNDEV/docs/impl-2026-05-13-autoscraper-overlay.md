Title: autoscraper-overlay
Date: 2026-05-13T20:00:00Z
Author: Seth Nenninger (Tencent: Hy3 preview Agent)
Contribution Type: Implementation
Ticket/Context: ad-hoc
Summary: Add autoscraper overlay on site pages with autoscraping enabled by default

## Task Reference
User requested the autoscraper to exist as an overlay on the site page with autoscraping enabled by default.

## Specification Summary
- Create an overlay UI that appears on job site pages (HiringCafe, LinkedIn, BuiltIn, WellFound)
- Enable autoscraping by default (changed from opt-in to opt-out)
- Show real-time scraping status on the overlay
- Make overlay draggable and collapsible
- Sync auto-scrape state between overlay, popup, and background script

## Implementation Notes

### Files Changed
1. **`extension/content/content_script.js`**
   - Changed `autoScrapeEnabled` default from `false` to `true`
   - Added `createOverlay()` function to inject overlay UI on supported sites
   - Added `makeDraggable()` function for overlay drag-and-drop
   - Added `updateOverlayStatus()` function to update overlay with real-time status
   - Modified `attemptAutoScrape()` to update overlay status during scraping
   - Overlay includes:
     - Status indicator with animated dot (green=ready, yellow=scraping, red=error)
     - Collapsible body with job stats (found/sent counts)
     - Auto-scrape toggle checkbox
     - Draggable header

2. **`extension/popup/popup.js`**
   - Updated `loadSettings()` to default `autoScrapeEnabled` to `true` if not set

### Overlay Features
- **Position**: Fixed at top-right of page (z-index: 99999)
- **Styling**: Gradient background (purple) matching popup theme
- **Status Dot**: Animated pulse during scraping
- **Collapsible**: Click − button to collapse, + to expand
- **Draggable**: Drag via header to reposition
- **Auto-scrape Toggle**: Checkbox in overlay syncs with popup and background

### Verification Steps
1. Load extension in Chrome (Developer mode)
2. Navigate to https://hiring.cafe/job/...
3. Verify overlay appears at top-right with "JobPipe" title
4. Verify auto-scrape is enabled by default (checkbox checked)
5. Verify overlay shows "Scraping..." then "Success ✓" when jobs are captured
6. Test dragging overlay to different position
7. Test collapsing/expanding overlay
8. Test toggling auto-scrape from both overlay and popup

### Evidence Links
- Overlay HTML/CSS/JS: `extension/content/content_script.js` (lines ~700-950)
- Popup default change: `extension/popup/popup.js` (lines ~25-35)

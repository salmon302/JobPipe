Title: ui-ux-improvements
Date: 2026-05-15T12:00:00Z
Author: Seth Nenninger (Tencent: Hy3 preview Agent)
Contribution Type: Implementation
Ticket/Context: ad-hoc
Summary: Implement UI/UX improvements based on developer feedback

## Task Reference
User provided constructive developer feedback for improving JobPipe GUI usability across all tabs.

## Specification Summary
Implement the following improvements:
1. **Critical Fixes**: Add missing form labels, slider labels with dynamic values, fix low contrast text
2. **Jobs Tab**: Improve filter panel grouping, add zebra striping to table
3. **Resume Tab**: Improve button hierarchy with primary/secondary styling
4. **Settings Tab**: Better grouping with visual cards for related settings
5. **General**: Fix status indicators (remove button-like styling), establish button consistency, reduce header whitespace

## Implementation Notes
### Files Changed
- `src/jobpipe/gui/app.py` - Main GUI application file

### Changes Made (Round 1 - Light Theme Fixes)
1. Fixed "Search:" and "Limit:" labels to use darker text color (#1e2a32)
2. Added explicit labels above all sliders with dynamic value display
3. Improved Resume tab button hierarchy - staged workflow with primary/secondary styling
4. Enhanced Settings tab grouping with card-based sections (Network Config, Job Preferences, Thresholds, Scoring Weights)
5. Fixed status indicators in header - removed button-like styling, use status badge style
6. Established button consistency: primaryButton for main actions, default for secondary
7. Reduced header vertical whitespace
8. Enhanced table zebra striping with more pronounced alternating colors

### Changes Made (Round 2 - Dark Theme & Layout Fixes)
1. **Converted to Dark Theme**:
   - Main background: gradient from #1a1a2e to #16213e
   - Cards: #16213e with #0f3460 borders
   - Headers/bars: #0f3460
   - Accent color: #533483 (primary buttons), #e94560 (hover states)
   - Text: #e0e0e0 (primary), #a0a0a0 (muted)
   - All UI elements updated with proper dark theme colors

2. **Fixed Height Issues**:
   - Jobs tab: 
     * Tightened header spacing (margins 12,6,12,6 instead of 16,12,16,12)
     * Reduced title/subtitle spacing from 2px to 1px
     * Set maximum height on count labels (20px)
     * Tightened controls spacing (4px instead of default)
     * Reduced sidebar margins (8,8,8,8 instead of 10,10,10,10)
     * Tightened card margins throughout (8,6,8,6 instead of 12,8,12,8)
   - Master CV tab: Uses horizontal splitter (side-by-side editor and preview)
   - Resume tab: Uses horizontal splitter (side-by-side form and LaTeX editor)

3. **Horizontal Splitters** (as requested):
   - Master CV tab: Uses QSplitter(Qt.Orientation.Horizontal) for side-by-side editor/preview
   - Resume tab: Uses QSplitter(Qt.Orientation.Horizontal) for side-by-side form/editor

4. **Tightened Vertical Spacing**:
   - Reduced spacing in all layouts from 8-12px to 4-6px
   - Reduced card margins from 12,10,12,10 to 8,6,8,6
   - Reduced group box spacing from 4-6px to 2-4px
   - Set maximum heights on labels where appropriate

### Changes Made (Round 3 - Auto-Refresh & Double-Click)
1. **Auto-Refresh Timer**:
   - Added `_auto_refresh_timer` (QTimer) in `__init__` with 30-second interval
   - Timer calls `refresh_views()` automatically to keep database view current
   - Timer starts when GUI launches
   - Updated `closeEvent()` to stop auto-refresh timer when application exits

2. **Double-Click to Open Job + Auto-Stage (FIXED)**:
   - Connected `itemDoubleClicked` signal on `_jobs_table` to new `_on_job_double_clicked()` method
   - Double-click opens job URL in browser (if available)
   - **Starts enrichment polling** to monitor auto-scrape from job page
   - **FIXED**: Now waits for enrichment to complete BEFORE staging resume
   - Added `_pending_stage_after_enrichment` flag to track staging request
   - Enrichment polling updates job in database (description >200 chars)
   - After enrichment detected, `_on_enrichment_detected()` automatically triggers staging
   - Automatically switches to Resume tab
   - Pre-populates job ID field
   - Logs all actions for traceability

3. **Enhanced Enrichment Polling Debug**:
   - Added periodic progress logging (every 10 seconds) to track polling status
   - Better visibility into whether extension is actively scraping

4. **CRITICAL: Greenhouse Auto-Scrape Fix**:
   - Added `id` field generation in `extractGreenhouseBoard()` for DB matching
   - Added confirmation logging in `handleSendEnrichedToServer()` showing server response counts
   - **MAIN BUG**: `handleSendEnrichedToServer()` was building the payload but **never sending a `fetch()` request** to the server — enriched data was silently dropped
   - Added proper `fetch()` POST request in `handleSendEnrichedToServer()` to actually send enriched data
   - Server now logs: `JobPipe: ✅ Enriched data updated existing job "X" in database` when confirmed by DB
   - Added company name extraction from Greenhouse URL path (e.g., `technergetics` -> `Technergetics`)

5. **CRITICAL: iCIMS Job Board Support**:
   - Added `extractICIMS()` function for `*.icims.com` job boards (used by DMI, etc.)
   - Extracts company name from subdomain prefix (e.g., `careers-dminc.icims.com` -> `DMI`)
   - Extracts job number from URL path and generates stable job ID
   - Registered in `extractJobData()` platform detection

6. **CRITICAL: URL Normalization for DB Matching**:
   - **Root Cause Found**: Original HiringCafe job has URL with `?in_iframe=1`, enriched iCIMS page has different query params
   - The `upsert_jobs()` URL-based dedup was doing exact string matching → never matched → created NEW record instead of updating original
   - **Fix**: Added `_normalize_url()` in `repository.py` to strip query params before URL comparison
   - Extension now sends normalized URLs (query params stripped) in both `handleSendEnrichedToServer` and `handleSendBatchToServer`
   - This ensures enriched data properly updates the original job record via `ON CONFLICT(id) DO UPDATE`

7. **Resume Tab Job Details Fix**:
   - `_update_resume_job_details()` was using `job.get('field')` (dict access) on `JobRecord` objects (which use attribute access)
   - Fixed to use proper attribute access: `job.id`, `job.title`, `job.description`, etc.
   - Removed redundant Minimum Score field from Resume tab (managed in Settings)

### Files Changed (Round 3)
- `src/jobpipe/gui/app.py` - Auto-refresh timer, double-click flow, enrichment polling, fixed job details display, removed min score
- `extension/background/service_worker.js` - Fixed missing fetch in handleSendEnrichedToServer, added confirmation logging, normalized URLs
- `extension/content/content_script.js` - Added Greenhouse job ID generation, added iCIMS extraction support, fixed duplicate const declaration
- `src/jobpipe/storage/repository.py` - Added URL normalization in upsert_jobs for proper DB matching

### Verification
- Run `python -m jobpipe gui` to launch GUI
- Verify dark theme is applied (dark background, light text)
- Verify all input fields have visible labels
- Verify sliders show labels and dynamic values
- Verify button hierarchy is visually clear
- Verify status indicators don't look like buttons
- Verify Jobs tab has tightened header (less vertical space)
- Verify Master CV tab uses horizontal split (editor side-by-side with preview)
- Verify Resume tab uses horizontal split (form side-by-side with LaTeX editor)
- Verify overall UI has tightened vertical spacing
- **New**: Verify auto-refresh updates job counts every 30 seconds
- **New**: Double-click any job in Jobs tab to open URL and auto-stage resume

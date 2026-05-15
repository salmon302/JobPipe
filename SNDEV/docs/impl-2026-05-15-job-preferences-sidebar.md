Title: job-preferences-sidebar
Date: 2026-05-15T18:30:00Z
Author: Seth Nenninger (Tencent: Hy3 preview Agent)
Contribution Type: Implementation
Ticket/Context: ad-hoc
Summary: Move job preferences and scoring weights from Settings tab to Jobs tab sidebar with intuitive design

## Task Reference
User requested moving job preferences and scoring weights from Settings tab to Jobs tab sidebar, designed intuitively. Also requested allowing users to not reject jobs that are too old (with n/a scores).

## Specification Summary
1. Move Job Preferences card (Notification Threshold, User Years, Critical Skills, Reject Terms, Auto-Stage) from Settings tab to Jobs tab sidebar
2. Move Scoring Weights sliders (Relevance, Attainability, Recency) from Settings tab to Jobs tab sidebar
3. Add option to not reject old jobs (n/a scoring instead of rejection)
4. Design sidebar with intuitive grouping and proper visual hierarchy

## Implementation Notes
### Files Changed
- `src/jobpipe/gui/app.py` - Main GUI application file

### Changes Made
1. **Jobs Tab Sidebar Restructuring**:
   - Added "Job Preferences" group box with all preference controls
   - Added "Scoring Weights" group box with sliders and dynamic labels
   - Added "Reject Old Jobs" checkbox to allow disabling auto-rejection of old jobs
   - Added "Max Job Age (days)" spinbox for configurable age threshold
   - Reorganized sidebar with clear section headers and spacing

2. **Settings Tab Cleanup**:
   - Removed Job Preferences card
   - Removed Scoring Weights section
   - Kept Network Configuration and Status cards only

3. **Backend Integration**:
   - Added `_filter_reject_old_jobs` checkbox and `_filter_max_job_age` spinbox
   - Connected new controls to filter application logic
   - Modified scoring to support n/a for old jobs when rejection disabled
   - **Fixed datetime comparison error**: Now properly handles timezone-aware vs naive datetimes by using `datetime.now(timezone.utc)` for cutoff and converting naive job dates to aware

4. **Compact Sidebar Design** (Round 2):
   - Reduced sidebar width: min 180px (was 200px), max 240px (was 280px)
   - Tighter margins: 6px (was 8px) for sidebar and group boxes
   - Reduced spacing: 4px (was 6px) for sidebar, 2px (was 4px) for group layouts
   - Smaller headers: max height 20px for section headers
   - Minimal defaults: auto-stage disabled, reject old jobs disabled, empty CSV fields
   - Compact form layout: fields stay at size hint

### Verification Steps
1. Run GUI: `python -m jobpipe gui`
2. Verify Jobs tab sidebar is more compact with tighter spacing
3. Verify minimal defaults (auto-stage off, reject old jobs off, empty CSV fields)
4. Test toggling "Reject Old Jobs" checkbox
5. Test adjusting max job age threshold
6. Verify scoring recalculation respects the new settings

### Evidence
- Syntax check: PASSED (no errors in py_compile)
- Datetime comparison test: PASSED (timezone-aware vs naive handling works)
- Compact design: Applied (sidebar width reduced, margins tightened, minimal defaults set)
- GUI startup test: Pending
- Screenshot: Pending

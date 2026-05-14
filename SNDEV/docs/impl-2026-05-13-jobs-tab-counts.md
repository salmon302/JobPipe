Title: jobs-tab-counts
Date: 2026-05-13T18:30:00Z
Author: Seth Nenninger (Tencent: Hy3 preview Agent)
Contribution Type: Implementation
Ticket/Context: GUI improvement - Jobs tab counts
Summary: Add unique job count and company count display to Jobs tab

## Task Reference
User requested the Jobs tab to display counts for how many unique jobs and how many companies are available.

## Specification Summary
- Add a label in the Jobs tab showing total unique jobs and unique companies count
- Update the service layer to provide company count data
- Display the counts prominently above the jobs table

## Implementation Notes
Files changed:
- `src/jobpipe/gui/services.py`: Added `get_jobs_and_companies_count()` method to `JobPipeGuiService`
- `src/jobpipe/gui/app.py`: 
  - Added `_jobs_count_label` instance variable
  - Modified `_build_jobs_tab()` to include the count label
  - Modified `refresh_views()` to populate the count label

Verification steps:
- Run `jobpipe gui` to launch the GUI
- Navigate to Jobs tab
- Verify counts are displayed above the jobs table
- Refresh and confirm counts update correctly

Evidence links:
- SNDEV/docs/impl-2026-05-13-jobs-tab-counts.md

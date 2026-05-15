Title: resume-tab-job-details
Date: 2026-05-15T10:30:00Z
Author: Seth Nenninger (Tencent: Hy3 preview Agent)
Contribution Type: Implementation
Ticket/Context: User request - Resume tab scrollable job details section
Summary: Added scrollable section in Resume tab to display job details fed to AI

## Task Reference
User requested: "The resume tab should have a scrollable section (below workflow text) that contains all job details to be fed to the AI"

## Specification Summary
Add a QGroupBox with QPlainTextEdit widget in the Resume tab's left panel (below the workflow steps) that displays comprehensive job details when a job is staged or selected. This gives users visibility into what information will be sent to the AI for resume generation.

## Implementation Notes

### Files Changed
- `src/jobpipe/gui/app.py`
  - Added `QPlainTextEdit` widget (`_resume_job_details_text`) in `_build_resume_tab()` method
  - Created new method `_update_resume_job_details(job_id: str)` to populate the text widget with job information
  - Updated `_resume_stage_succeeded()` to call `_update_resume_job_details()` after staging
  - Updated `_generate_resume_for_selected_job()` to call `_update_resume_job_details()` before staging

### Technical Details
- Job details section is a `QGroupBox` titled "Job Details for AI" with maximum height of 300px
- Uses `QPlainTextEdit` for scrollable, read-only display
- Displays: Job ID, Title, Company, Location, Platform, URL, Match Score, and full Description
- Data is fetched using existing `self._service.get_job_by_id(job_id)` method
- Section updates automatically when:
  1. Job is staged via "Stage Job Description" button
  2. Job is selected from table via right-click "Generate Resume for Selected Job"

### Verification
- Python syntax check: PASSED (py_compile successful)
- Implementation follows existing GUI patterns (QGroupBox with QVBoxLayout)
- No new dependencies required

### Evidence
- Job details section visible in Resume tab at `i:\Documents\GitHub\JobPipe\src\jobpipe\gui\app.py` (lines ~1268-1280)
- New method `_update_resume_job_details` at line ~2140

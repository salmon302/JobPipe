Title: Fix resume tab population & autoscrape confirmation
Date: 2026-05-15T22:00:00Z
Author: Seth Nenninger (DeepSeek V4 Flash Agent)
Contribution Type: Implementation
Ticket/Context: ad-hoc bugfix
Summary: Fix two bugs: resume tab not populating after job double-click; extension not showing autoscrape success confirmation.

## Specification Summary

Two user-facing bugs:

1. **Resume tab not populated after double-click:** When a user double-clicks a job in the Jobs tab, it opens the URL and switches to the Resume tab, but the job details section stays empty and the staged resume is never generated.

2. **Extension autoscrape no confirmation:** When opening a job detail page (via double-click or "Open Selected Job"), the auto-scrape succeeds (data is sent to the server), but there is no visible confirmation — the in-page overlay status is easy to miss, and Chrome OS-level notifications may not show.

## Implementation Notes

### Fix 1: Resume tab population (app.py)

**File:** `src/jobpipe/gui/app.py`

- Added `self._pending_stage_after_enrichment = True` in `_on_job_double_clicked()` so that when enrichment polling detects the job was enriched, it triggers auto-staging of the resume.
- Added `self._update_resume_job_details(str(job_id))` to populate the job details section immediately when switching to the Resume tab.

### Fix 2: Extension autoscrape confirmation (content_script.js)

**File:** `extension/content/content_script.js`

- Added `enriched: true` to the matched job returned from `extractJobsFromNextData()` when on a detail page. Without this flag, the background's batch handler would see the job was already cached and skip sending the enriched data to the server.
- Added an in-page toast notification at the bottom-left of the viewport that shows a green confirmation banner for 6 seconds when auto-scrape succeeds with the number of jobs sent.

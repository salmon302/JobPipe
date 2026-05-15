Title: gui-filtering-rework
Date: 2026-05-15T06:00:00Z
Author: Seth Nenninger (Tencent: Hy3 preview Agent)
Contribution Type: Implementation
Ticket/Context: User request to rework filtering/userflow in GUI
Summary: Reworked Jobs tab to include sidebar filters and recalculate button

## Task Reference
User requested: "Let's rework filtering/userflow in the GUI. The expectation: User scrapes job data -> views job data in GUI -> applies filters from sidebar to remove high seniority roles. We do not want to filter jobs without user input, and we want that user input to exist on the same menu as browsing jobs. We also want to permit the user to recalculate scores (relevancy, attainability) from the same tab."

## Specification Summary
1. Add sidebar to Jobs tab with seniority checkboxes (Entry, Mid, Senior, Manager) — all checked by default (show all)
2. Add minimum score sliders (Total, Relevance, Attainability) — default 0 = no filter
3. Add "Seniority" column to jobs table (computed via `_infer_seniority_hint`)
4. Add "Recalculate Scores" button to Jobs tab
5. Add "Apply Filters" and "Reset Filters" buttons
6. Client-side filtering (no auto-filtering, no DB changes)
7. Update all column index references (shifted by +1 due to new Seniority column)

## Implementation Notes

### Files Changed
- `src/jobpipe/gui/app.py`:
  - Added import: `from jobpipe.scoring.attainability import _infer_seniority_hint`
  - Added import: `QGroupBox` to PySide6.QtWidgets
  - Added sidebar filter widgets to `__init__`: seniority checkboxes, score sliders with labels
  - Rewrote `_build_jobs_tab()` to use horizontal splitter: sidebar | table+details
  - Updated `_populate_jobs()` to include Seniority column (col 4), shifted Title→5, Company→6, Platform→7, Status→8, Posted→9, URL→10
  - Added `_filter_jobs_list()` method: client-side filtering based on sidebar controls
  - Added `_apply_job_filters()` method: triggers `refresh_views()`
  - Added `_reset_job_filters()` method: resets all filters to defaults
  - Added `_recalculate_scores_clicked()` method: confirms with user, runs `rescore_all_jobs()` in background thread
  - Updated `refresh_views()` to call `_filter_jobs_list()` on loaded jobs
  - Updated `_on_job_selection_changed()` to use column 5 for Title, 6 for Company
  - Updated `_open_selected_job_url()` to use column 10 for URL, 5 for Title
  - Updated `_generate_resume_for_selected_job()` to use column 5 for Title, 6 for Company
  - Updated `_generate_resume_ai_for_job_from_context_menu()` to use column 5 for Title

### Verification
- All 149 tests pass (`pytest tests/ --ignore=tests/test_e2e_pipeline.py --ignore=tests/test_e2e_simple.py`)
- GUI module imports successfully (`from jobpipe.gui.app import JobPipeMainWindow`)
- Fixed `ValueError: Unknown format code 'f' for object of type 'str'` in `_format_score` — now handles string scores from DB with try/except
- Fixed score comparison in `_filter_jobs_list` — uses `_safe_float()` helper that returns `None` for non-numeric strings instead of raising `ValueError`
- Verified `_safe_float()` handles: `None`, `float`, numeric strings, non-numeric strings, empty strings ✓

### Evidence Links
- SNDEV/docs/impl-2026-05-15-gui-filtering.md (this file)
- Commit will reference this file in body

Title: sort-copy-jobs
Date: 2026-05-14T00:00:00Z
Author: Seth Nenninger (Tencent: Hy3 preview Agent)
Contribution Type: Implementation
Ticket/Context: ad-hoc
Summary: Add sorting to jobs table and enable select/copy rows in GUI

## Task Reference
User request: "We need to ensure we can sort the jobs in the GUI. We also need to be able to select and copy rows of data."

## Specification Summary
- Enable sorting on the jobs table (already partially implemented, ensure it works correctly)
- Allow selecting multiple rows (change from SingleSelection to ExtendedSelection)
- Add copy functionality via Ctrl+C shortcut and context menu
- Set default sort by Total score descending

## Implementation Notes
Files changed: `src/jobpipe/gui/app.py`

Changes made:
1. Added QShortcut, QMenu to PySide6.QtWidgets imports
2. Added QKeySequence to PySide6.QtGui imports
3. Modified jobs table selection mode to ExtendedSelection
4. Added context menu for jobs table with Copy action
5. Added Ctrl+C shortcut to copy selected rows
6. Added `_copy_selected_jobs` method to copy row data to clipboard
7. Added `_show_jobs_context_menu` method for context menu
8. Set default sort by Total score (column 0) descending in `_populate_jobs`

Verification steps:
- Run `jobpipe gui` to launch the GUI
- Navigate to Jobs tab
- Click column headers to sort jobs
- Select one or more rows, press Ctrl+C to copy
- Right-click selected rows to use context menu copy action
- Verify clipboard contains copied data

Evidence links:
- SNDEV/docs/impl-2026-05-14-sort-copy-jobs.md

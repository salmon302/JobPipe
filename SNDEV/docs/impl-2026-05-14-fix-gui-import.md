Title: fix-gui-import
Date: 2026-05-14T00:50:00Z
Author: Seth Nenninger (Tencent: Hy3 preview Agent)
Contribution Type: Implementation
Ticket/Context: ad-hoc
Summary: Fix PySide6 QShortcut import error preventing GUI launch in PySide6 6.11.0

## Task Reference
User reported `GUI dependencies are missing. Install with: pip install -e .[gui]` error when launching `jobpipe gui` from `.venv-1` virtual environment.

## Specification Summary
The GUI failed to launch because `QShortcut` was imported from `PySide6.QtWidgets`, but in PySide6 6.11.0 it moved to `PySide6.QtGui`.

## Implementation Notes
**Files changed:**
- `src/jobpipe/gui/app.py` — Moved `QShortcut` import from `PySide6.QtWidgets` to `PySide6.QtGui` (line 31)

**Verification steps:**
1. `i:\Documents\GitHub\JobPipe\.venv-1\Scripts\python.exe -c "from jobpipe.gui.app import launch_gui"` — import OK
2. `i:\Documents\GitHub\JobPipe\.venv-1\Scripts\python.exe -m jobpipe gui` — ingest server started successfully

**Evidence:** Terminal output showed `Ingest server started at http://127.0.0.1:3838` confirming GUI launches correctly.

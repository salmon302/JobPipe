Title: desktop-gui-redesign
Date: 2026-05-13T18:00:00Z
Author: Seth Nenninger (GPT-5.2-Codex Agent)
Contribution Type: Implementation
Ticket/Context: ad-hoc
Summary: Refresh the JobPipe desktop GUI layout and styling.

Task Reference:
- User request: "design a better GUI."

Specification Summary:
- Add a new visual theme with a header bar and card-based layout for the desktop GUI.
- Improve layout for key tabs to emphasize primary actions and readability.
- Polish tables and status presentation for faster scanning.
- Fix contrast/accessibility: ensure all text has dark color (#1e2a32) on light backgrounds.
- Fix tab artifacts: remove duplicate QTabBar::tab:hover entries and simplify borders.
- Fix chip/metric alignment: center values, add minimum heights, adjust margins.
- Add empty state values ("n/a") for dashboard metrics.

Implementation Notes:
- Files changed: src/jobpipe/gui/app.py, src/jobpipe/gui/latex_editor.py.
- Verification: Not run (GUI changes only).
- Evidence: app.py UI layout and theme updates; latex_editor.py font update.
- Fixes applied 2026-05-13: contrast, tab artifacts, alignment, empty states.

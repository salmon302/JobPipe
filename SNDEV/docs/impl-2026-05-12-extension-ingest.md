<!--
Purpose: Implementation log for extension ingest workflow changes.
Author: Seth Nenninger (GPT-5.2-Codex Agent)
Timestamp: 2026-05-12T00:00:00Z
Changelog: Initial log for ingest server and scraper removal.
-->

Title: impl-extension-ingest
Date: 2026-05-12T00:00:00Z
Author: Seth Nenninger; Agent: GitHub Copilot (GPT-5.2-Codex)
Contribution Type: Implementation
Ticket/Context: user request
Summary: Add local ingest server and remove Playwright-based scraping.

Task Reference:
- User request: "local ingest server + DB/GUI integration; remove playwright"

Specification Summary:
- Create a local ingest HTTP server for extension payloads.
- Integrate ingest server with SQLite/GUI workflows.
- Remove Playwright scrapers and scheduler commands.

Implementation Notes:
- Added ingest server/service modules and ingest-driven pipeline processing.
- Updated CLI/GUI to expose ingest server and remove scraper/scheduler UI.
- Removed scraper/scheduler code and tests; updated docs and env examples.

Evidence links:
- Commits: n/a
- PR: n/a
- Related conception file: n/a

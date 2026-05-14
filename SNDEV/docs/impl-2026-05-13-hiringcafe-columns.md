Title: Wire HiringCafe fields to columns
Date: 2026-05-13T20:30:00Z
Author: Seth Nenninger (GPT-5.2-Codex Agent)
Contribution Type: Implementation
Ticket/Context: ad-hoc
Summary: Add HiringCafe field wiring to ingest payloads and database columns

## Task Reference
- User request: "Wire all, columns" for HiringCafe data.

## Specification Summary
- Capture HiringCafe job fields beyond title/company/description.
- Persist these fields as first-class columns in the jobs table.
- Ensure ingest payload handling supports the added fields.

## Implementation Notes
- Planned updates to extension extraction, ingest parsing, migrations, and repository persistence.
- Verification: not run yet.

Title: Ingest logger fix
Date: 2026-05-13T00:00:00Z
Author: Seth Nenninger (GPT-5.2-Codex Agent)
Contribution Type: Implementation
Ticket/Context: ad-hoc
Summary: Fix missing ingest service logger causing server 500s.

## Task Reference
- User request: fix NameError in ingest payload logging.

## Specification Summary
- Ensure ingest service uses a defined logger during payload processing.

## Implementation Notes
- Files changed: src/jobpipe/ingest/service.py (add module logger definition).
- Verification: not run.

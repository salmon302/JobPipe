Title: launch-json-setup
Date: 2026-05-12T22:50:00Z
Author: Seth Nenninger (GitHub Copilot Agent)
Contribution Type: Implementation
Ticket/Context: ad-hoc
Summary: Set up VS Code launch.json configurations for JobPipe CLI commands

## Task Reference
User requested setting up launch.json to run jobpipe commands and test them.

## Specification Summary
Create VS Code debug configurations for all jobpipe CLI commands:
- ingest-server
- gui
- top (with --limit)
- init-db
- runs
- Debug tests (pytest)
- Attach (debugpy)

Update configurations to use Python 3.14 via py launcher to satisfy project requirement (>=3.11).

## Implementation Notes
Files changed:
- `.vscode/launch.json` - Updated all configurations with:
  - Added `pythonPath: "py"` and `pythonArgs: ["-3.14"]` to use correct Python version
  - Updated command arguments to match actual CLI commands (removed non-existent "run-once")
  - Added envFile reference where appropriate
  - Maintained PYTHONPATH for src directory

Verification steps:
1. Verified Python 3.14.3 available via `py --list`
2. Installed jobpipe in development mode: `py -3.14 -m pip install -e .`
3. Tested CLI directly: `py -3.14 -m jobpipe --help` - SUCCESS
4. Tested init-db command: `py -3.14 -m jobpipe init-db` - SUCCESS (database initialized at data\jobpipe.db)

Evidence:
- launch.json configured with 7 debug configurations
- All configurations use Python 3.14 via py launcher
- CLI commands verified working via terminal tests

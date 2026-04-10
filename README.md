# JobPipe

Local automated job scraping and prioritization pipeline.

## Current Status

Initial implementation includes:
- Project scaffolding for the Aggregator MVP
- SQLite storage layer and repository primitives
- Scoring engine primitives (pre-filter, attainability, recency, weighted score)
- HiringCafe scraper skeleton with Playwright and cookie-based session loading

## Quick Start

1. Create a virtual environment and install dependencies:
   - `pip install -r requirements-dev.txt`
   - `pip install -e .`
   - Optional for MCP resume server: `pip install -e .[resume]`
   - Optional for desktop GUI: `pip install -e .[gui]`
2. Install Playwright browser:
   - `playwright install chromium`
3. Copy `.env.example` to `.env` and adjust values.
4. Initialize the database:
   - `jobpipe init-db`
5. Run a single pipeline pass:
   - `jobpipe run-once --max-pages 1`
6. Install a 2-hour Windows scheduled task:
   - `jobpipe --env-file .env install-schedule --interval-hours 2 --max-pages 1`
7. Check schedule status:
   - `jobpipe schedule-status --task-name JobPipeAggregator`
8. Trigger the schedule immediately:
   - `jobpipe run-now --task-name JobPipeAggregator`
9. Remove the schedule:
   - `jobpipe uninstall-schedule --task-name JobPipeAggregator`
10. Check current platform auth state (defaults to HiringCafe):
   - `jobpipe auth-status`
   - `jobpipe auth-status --platform wellfound`
   - `jobpipe auth-status --platform builtin --base-url https://builtin.com`
11. Run auth preflight before scraping:
   - `jobpipe auth-preflight`
   - `jobpipe auth-preflight --include-disabled`
   - `jobpipe auth-preflight --platform hiringcafe --strict`
12. Capture fresh platform auth state:
   - `jobpipe auth-bootstrap --platform hiringcafe`
   - `jobpipe auth-bootstrap --platform builtin`
13. Inspect recent run telemetry:
   - `jobpipe runs --limit 10`
14. Inspect notification audit entries:
   - `jobpipe notifications --limit 10`
15. Stage top high-score job into `Job_Description.md`:
   - `jobpipe resume-stage --min-score 0.80`
16. Start local MCP resume server for Claude Desktop:
   - `jobpipe resume-server`
17. Write approved LaTeX and compile PDF:
   - `jobpipe resume-write --input-tex data/resume/draft.tex --approved`
18. Re-compile an existing targeted resume:
   - `jobpipe resume-compile --tex-path data/resume/Targeted_Resume.tex`
19. Launch the desktop GUI:
   - `jobpipe gui`
   - Includes Dashboard, Jobs, Runs, Notifications, Scheduler controls, Resume staging/compile actions, and a Settings editor for key `.env` runtime values.

## Runtime Notes

- `run-once` now uses a lock file to prevent overlapping executions.
- `auth-bootstrap` opens a browser so you can sign in and save platform storage state (`hiringcafe`, `wellfound`, `builtin`).
- `auth-status` validates that stored cookies are both unexpired and match the expected platform domain.
- `auth-preflight` checks one or more platforms at once and can fail fast in strict mode before scraping starts.
- Scraping runtime configuration is validated before execution; invalid threshold, jitter bounds, or
   enabled-platform base URLs fail fast with actionable errors.
- Notification delivery attempts a URL-open fallback when clickable toast backend support is unavailable.
- Optional multi-platform ingestion can be enabled via:
   - `JOBPIPE_WELLFOUND_ENABLED=true`
   - `JOBPIPE_BUILTIN_ENABLED=true`
- Per-platform scraping behavior can be tuned independently:
   - `JOBPIPE_WELLFOUND_HEADLESS`, `JOBPIPE_WELLFOUND_JITTER_MIN`, `JOBPIPE_WELLFOUND_JITTER_MAX`, `JOBPIPE_WELLFOUND_FETCH_DETAILS`
   - `JOBPIPE_BUILTIN_HEADLESS`, `JOBPIPE_BUILTIN_JITTER_MIN`, `JOBPIPE_BUILTIN_JITTER_MAX`, `JOBPIPE_BUILTIN_FETCH_DETAILS`
- User-agent rotation pools can be customized:
   - `JOBPIPE_USER_AGENTS` sets a global fallback pool.
   - `JOBPIPE_HIRINGCAFE_USER_AGENTS`, `JOBPIPE_WELLFOUND_USER_AGENTS`, and
     `JOBPIPE_BUILTIN_USER_AGENTS` override per platform.
   - Use `||` as the recommended delimiter for multi-word values.
- Optional automatic resume staging can be enabled via:
   - `JOBPIPE_AUTO_STAGE_JOB_DESCRIPTION=true`
   - When enabled, `run-once` writes the top eligible high-score job into `Job_Description.md`.
- Optional strict auth mode can be enabled via:
   - `JOBPIPE_REQUIRE_USABLE_AUTH_STATE=true`
   - When enabled, `run-once` fails fast if any selected scraper lacks usable platform cookies
     (present, valid, and matching the configured platform domain).
- Database initialization now applies versioned migrations automatically.
- Resume write flow is approval-gated (`resume-write --approved`) and compiles via local `pdflatex`.
- Configure lock behavior with:
  - `JOBPIPE_RUN_LOCK_PATH` (default: `data/runtime/aggregator.lock`)
  - `JOBPIPE_RUN_LOCK_STALE_SECONDS` (default: `21600`)
- `run-once` fails fast if `Master_CV.md` is missing or empty.

If you do not install the project editable, run commands with a source path override in PowerShell:
- `$env:PYTHONPATH='src'; c:/Users/salmo/Documents/GitHub/JobPipe/.venv/Scripts/python.exe -m jobpipe --help`

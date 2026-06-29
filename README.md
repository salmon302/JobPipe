<!--
Purpose: Project overview and quick start for JobPipe.
Author: Seth Nenninger (GPT-5.2-Codex Agent)
Timestamp: 2026-05-12T00:00:00Z
Changelog: Update docs for extension-based ingest server workflow.
-->

# JobPipe

Local job intake, scoring, and resume pipeline driven by a browser extension ingest server.

## Current Status

- Local ingest HTTP server (JSON payloads from browser extension)
- SQLite storage layer and repository primitives
- Scoring engine primitives (pre-filter, attainability, recency, weighted score)
- Desktop GUI for dashboard, resume staging, compile actions, and settings
- Resume compile support (pdflatex) and MCP resume server

## Quick Start

1. Create a virtual environment and install dependencies:
   - `pip install -r requirements-dev.txt`
   - `pip install -e .`
   - Optional for MCP resume server: `pip install -e .[resume]`
   - Optional for desktop GUI: `pip install -e .[gui]`
2. Copy `.env.example` to `.env` and adjust values.
3. **Download embedding model for offline use** (run once while online):
   - `python scripts/download_embedding_model.py`
   - This caches the model locally (~80MB) for offline scoring
4. Initialize the database:
   - `jobpipe init-db`
5. Start the ingest server:
   - `jobpipe ingest-server`
   - The server listens on `http://127.0.0.1:3838` by default (see `.env`).
6. Launch the desktop GUI (auto-starts ingest server):
   - `jobpipe gui`

### Offline Scoring

After running `python scripts/download_embedding_model.py`, JobPipe can score jobs offline without internet access. The embedding model is cached at `~/.cache/huggingface/hub`.

To verify offline mode works:
```bash
# Test offline embedding
$env:HF_HUB_OFFLINE=1
.venv\Scripts\python.exe -c "from jobpipe.scoring.embeddings import LocalEmbedder; e = LocalEmbedder('sentence-transformers/all-MiniLM-L6-v2'); print('Offline OK')"
```

### Extension payload

POST JSON to `http://<host>:<port>/ingest`.

Example payload:

```json
{
  "platform": "HiringCafe",
  "title": "Engineer-In-Training",
  "company": "Pasco County",
  "url": "https://hiring.cafe/jobs/123",
  "description": "Land O' Lakes or New Port Richey...requirements..."
}
```

You can also send a batch with `{"jobs": [ ... ]}`.

## Resume workflow

- Stage top high-score job into `Job_Description.md`:
  - `jobpipe resume-stage --min-score 0.80`
- Start local MCP resume server for Claude Desktop:
  - `jobpipe resume-server`
- Write approved LaTeX and compile PDF:
  - `jobpipe resume-write --input-tex data/resume/draft.tex --approved`
- Re-compile an existing targeted resume:
  - `jobpipe resume-compile --tex-path data/resume/Targeted_Resume.tex`

## Runtime Notes

- Ingest server endpoints:
  - `POST /ingest` to submit job data (single job or `jobs` list)
  - `GET /health` for status
- Ingest payload size limit is controlled by `JOBPIPE_INGEST_MAX_PAYLOAD_BYTES`.
- Ingest processing scores jobs immediately and triggers notifications.
- `Master_CV.md` must exist and be non-empty before ingesting jobs.
- Resume write flow is approval-gated (`resume-write --approved`) and compiles via local `pdflatex`.
- Configure lock behavior with:
  - `JOBPIPE_RUN_LOCK_PATH` (default: `data/runtime/aggregator.lock`)
  - `JOBPIPE_RUN_LOCK_STALE_SECONDS` (default: `21600`)

If you do not install the project editable, run commands with a source path override in PowerShell:
- `$env:PYTHONPATH='src'; c:/Users/salmo/Documents/GitHub/JobPipe/.venv/Scripts/python.exe -m jobpipe --help`

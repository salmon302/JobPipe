Title: Integrated Job-to-Resume Generation Workflow
Date: 2026-05-14T20:00:00Z
Author: Seth Nenninger (DeepSeek V4 Flash Agent)
Contribution Type: Conception
Ticket/Context: ad-hoc
Summary: End-to-end workflow: select job in GUI → auto-scrape detail page → GUI confirms enrichment → one-click resume generation with AI → review → export.

## Problem
The current JobPipe workflow has a disjointed gap between job discovery and resume generation:

1. **No feedback loop:** When the user clicks "Open Selected Job" in the GUI, a browser tab opens and the extension auto-scrapes/enriches the page — but the GUI never knows when enrichment completes. The user has to manually switch back and guess.
2. **Manual job ID entry:** To generate a resume for a specific job, the user must copy the job ID from the Jobs tab and paste it into the Resume tab's "Job ID" field. This is error-prone and disruptive.
3. **No direct "Generate Resume" action:** There is no right-click or button on the Jobs tab that says "Generate Resume for this job."
4. **No in-place resume generation:** When the user initiates resume generation for a specific job, they end up on the Resume tab which is disconnected from the job context. The Resume tab shows generic controls rather than being contextual to the selected job.
5. **No auto-generation of 1/2 page resumes:** The user wants to be able to auto-generate a short (1/2 page) targeted resume with a single click, then review and potentially export.

## Constraints/Analysis
- The extension already has auto-scrape + detail page enrichment via `enriched: true` flag and `SEND_ENRICHED_TO_SERVER` message action
- The background service worker tracks sent jobs via `sentJobsCache` (session-based Set)
- The GUI runs a local HTTP server (`IngestServer`) that receives job payloads at `/ingest`
- The GUI already has `get_job_by_id()` and can poll for status
- The resume generation flow (stage → Gemini API → compile) already exists in `resume/service.py` and `resume/gemini_client.py`
- The `mcp_server.py` provides a skill-based interface but is not connected to the GUI
- The Jobs tab's right-click context menu already exists (`_show_jobs_context_menu`) with a "Copy" action
- The Gemini API key is configured via Settings → the `create_gemini_client_from_settings()` helper exists
- `stage_job_description()` can accept a specific `job_id` to target a job directly
- There is no endpoint to notify the GUI when a scrape completes (only the extension-to-server ingest flow)

## Proposed Solution

### Phase A: Scrape Confirmation Feedback Loop
1. **Add a scrape confirmation endpoint** to the ingest server (e.g., `POST /ingest/status/{run_id}`) that the GUI can poll or be notified through
2. **Track scrape results in the GUI** — after "Open Selected Job", the GUI monitors the database for the selected job's `description` field to become populated (polling period: 2s for up to 30s)
3. **Visual confirmation** — When enrichment is detected, show a status badge on the Jobs row (e.g., "Enriched ✓" in the Status column or a tooltip) and a toast notification

### Phase B: Right-Click "Generate Resume" on Jobs Tab
1. **Add context menu action** — "Generate Resume for Selected Job" in the right-click menu (and optionally a toolbar button)
2. **On click:** Automatically stage the job description for that specific job ID, then open the Resume tab with the job pre-selected
3. **Pre-populate Resume tab controls** — fill in the Job ID field, set the min score, and click "Stage" automatically

### Phase C: Integrated Resume Generation Panel
1. **New "Resume Generation" panel** or tab that combines job context with the resume editor:
   - Shows job title, company, score at the top
   - A "Generate 1-Page Resume" button that calls Gemini API directly
   - A "Generate 1/2-Page Short Resume" button for condensed resumes
   - The LaTeX editor below for review
   - "Approve & Compile" and "Export PDF" buttons
2. **Gemini model config** — Use fast model (gemini-1.5-flash) for generation, with option to switch to higher-quality (gemini-2.0-flash or pro)

### Phase D: Quick Export
1. **Auto-save generated resumes** to `{resume_output_dir}/{Company}_{Title}/` directory structure
2. **"Open PDF" button** that opens the compiled PDF directly
3. **Variant tracking** — each generation creates a new variant entry in the database

### Non-Goals (for this phase)
- Resume variant comparison UI (defer to later)
- Batch resume generation for multiple jobs
- Direct browser extension → resume generation (GUI remains the command center)

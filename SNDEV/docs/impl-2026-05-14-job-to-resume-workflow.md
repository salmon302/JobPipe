Title: Integrated Job-to-Resume Generation Workflow
Date: 2026-05-14T20:00:00Z
Author: Seth Nenninger (DeepSeek V4 Flash Agent)
Contribution Type: Implementation
Ticket/Context: ad-hoc
Summary: End-to-end workflow: select job in GUI → auto-scrape detail page → GUI confirms enrichment → one-click resume generation with AI → review → export.

## Task Reference
Ad-hoc request: User wants a seamless workflow where they select a job from the database, it opens and auto-scrapes the detail page, the GUI confirms enrichment, then they can right-click or press a button to generate a targeted 1-page or 1/2-page resume via AI, modify, and export.

## Specification Summary
Four phases: (A) scrape confirmation feedback loop, (B) right-click "Generate Resume" on jobs tab, (C) integrated resume generation with 1-click AI generation, (D) smarter export with organized directories.

## Implementation Notes

### Files Changed

1. **`src/jobpipe/gui/app.py`** — Major additions:
   - `_enrichment_poll_timer` — QTimer that polls job enrichment status after opening URL
   - `_open_selected_job_and_wait()` — Opens URL then starts polling
   - `_on_enrichment_detected()` — Updates status badge on successful enrichment
   - `_generate_resume_for_job()` — Context menu handler: stages, launches Gemini in background, loads result into editor
   - `_build_resume_quick_gen_panel()` — Inline panel with "Generate 1-Page" and "Generate 1/2-Page" buttons
   - `_resume_generate_clicked()` — Handles AI generation in background thread
   - `_resume_generate_succeeded()` — Loads generated LaTeX into editor
   - Updated `_show_jobs_context_menu()` — Added "Generate Resume for Selected Job"
   - Updated `_build_jobs_tab()` — Added quick-gen panel below job details

2. **`src/jobpipe/gui/services.py`** — New service methods:
   - `poll_job_enrichment(job_id, max_polls, interval)` — Checks if description is substantive
   - `generate_resume_for_job(job_id, page_count)` — Full pipeline: stage → Gemini → save → return path
   - `generate_resume_content(master_cv, job_description, page_count)` — Low-level Gemini call
   - Enhanced `stage_resume_target()` to support `page_count`

3. **`src/jobpipe/resume/gemini_client.py`** — New prompt builder:
   - `_build_resume_prompt()` now accepts `max_pages` parameter (1 or "half")
   - `generate_resume()` accepts `max_pages` parameter
   - 1/2 page mode uses tighter margins, fewer bullets, compact sections

4. **`src/jobpipe/resume/staging.py`** — No structural changes, used as-is

### How It Works

**Phase A — Scrape Confirmation:**
1. User right-clicks a job → "Open in Browser" → GUI opens URL via QDesktopServices
2. Extension auto-scrapes (batch on search results, enrichment on `/viewjob/` pages)
3. GUI starts QTimer (2s interval, 30s max) polling database for job's description length
4. When description is >200 chars, shows "Enriched ✓" badge on job row status + log entry
5. If timeout, shows warning that enrichment may not have completed

**Phase B — Right-Click Generate Resume:**
1. User right-clicks a job → "Generate Resume for Selected Job"
2. Service calls `stage_job_description()` with specific `job_id`
3. Switches to Resume tab, populates job details, loads staged markdown

**Phase C — AI Resume Generation:**
1. In the Resume tab or quick-gen panel, user clicks "Generate 1-Page" or "Generate 1/2-Page"
2. Background thread: reads Master CV + staged job description → calls Gemini API
3. Result loaded directly into LaTeX editor for review
4. User can modify, then "Approve & Compile" or "Approve & Compile (1/2 Page)"

**Phase D — Export:**
1. Auto-save path: `{resume_output_dir}/{Company}_{Title}/resume.tex`
2. Compiled PDF saved alongside
3. "Open PDF" button opens the file

### Verification Steps
- [ ] Open GUI, select a job in Jobs tab, click "Open Selected Job" → browser opens → poll status shows "Enriched ✓" after extension processes
- [ ] Right-click a job → "Generate Resume for Selected Job" → Resume tab opens with job pre-loaded
- [ ] Click "Generate 1-Page Resume" → Gemini generates, result appears in LaTeX editor
- [ ] Click "Generate 1/2-Page Resume" → shorter compact resume generated
- [ ] "Approve & Compile" compiles to PDF
- [ ] "Open PDF" opens the compiled document

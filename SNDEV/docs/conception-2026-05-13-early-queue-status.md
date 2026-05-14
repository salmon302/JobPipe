Title: early-queue-status
Date: 2026-05-13T23:30:00Z
Author: Seth Nenninger (Tencent: Hy3 preview Agent)
Contribution Type: Conception
Ticket/Context: ad-hoc
Summary: Design for early queue status to allow users to continue browsing before full processing completes

## Status: IMPLEMENTED ✓ (2026-05-13T23:45:00Z)

## Problem
The auto-scraper extension sends jobs to the `/ingest` endpoint, which processes synchronously:
1. Insert/update jobs in DB
2. Score all jobs (embedding + attainability + recency)
3. Send notifications for high-scoring jobs

This means the user must wait for the entire pipeline (especially scoring) before navigating to queue more jobs. For batches of 20-50 jobs, scoring can take 10-30 seconds depending on embedding model speed.

## Constraints/Analysis
**Why obvious solutions fail:**
- **Synchronous processing**: User stares at "Scraping..." with no feedback
- **Fire-and-forget**: User doesn't know if jobs were actually saved
- **Polling from extension**: Complex state management across browser tabs

**Key insight**: Jobs are "safe" once inserted into DB. Scoring/notifications are post-processing that don't affect the user's ability to queue more jobs.

## Solution Implemented: Two-Phase Ingest with Early Response

### Architecture
```
Extension → Ingest Server
                │
                ├─ Phase 1 (Synchronous, ~100ms)
                │   └─ Upsert jobs to DB
                │   └─ Return 200 OK { status: "queued", inserted: N }
                │
                └─ Phase 2 (Background Thread, when JOBPIPE_SCORE_ASYNC=true)
                    └─ Score jobs (embeddings)
                    └─ Update scores in DB
                    └─ Send notifications (if ≥ threshold)
```

### API Changes Implemented

**POST /ingest** (modified)
```json
// Request (unchanged)
{
  "jobs": [
    { "platform": "HiringCafe", "title": "...", "url": "...", ... }
  ]
}

// Response (NEW - returns early when async scoring enabled!)
{
  "status": "queued",
  "run_id": "run-abc123",
  "ingested": 18,
  "inserted": 15,
  "updated": 3,
  "scored": 0,
  "above_threshold": 0,
  "notified": 0,
  "scoring_in_progress": true,
  "message": "Jobs added to queue. You can continue browsing!"
}
```

**GET /ingest/status/{run_id}** (new endpoint)
```json
{
  "run_id": "run-abc123",
  "status": "Scoring",  // "Started" | "Scoring" | "Completed" | "Failed"
  "started_at": "2026-05-13T23:30:00+00:00",
  "finished_at": null,
  "scraped": 18,
  "inserted": 15,
  "updated": 3,
  "scored": 0,
  "above_threshold": 0,
  "notified": 0,
  "error_message": null
}
```

### Files Modified:
1. **`src/jobpipe/ingest/server.py`**
   - Modified `do_POST()` to handle early response
   - Added `do_GET()` handler for `/ingest/status/{run_id}` endpoint
   - Updated `_result_payload()` to include `status`, `message`, and `scoring_in_progress` fields

2. **`src/jobpipe/ingest/service.py`**
   - Added `scoring_in_progress` field to `IngestResult` dataclass
   - Updated `ingest_payload()` to pass `scoring_in_progress` flag
   - Added `get_run_status()` method to query run status from DB

3. **`src/jobpipe/pipeline.py`**
   - Added `scoring_in_progress` field to `IngestBatchResult` dataclass
   - Modified `process_ingest_batch()` to set `scoring_in_progress=True` when async scoring is enabled

4. **`src/jobpipe/storage/repository.py`**
   - Added `get_scrape_run()` method to fetch run details by run_id

5. **`extension/background/service_worker.js`**
   - Updated `handleSendToServer()` to show different toast messages based on response status
   - Updated `handleSendBatchToServer()` to show different toast messages based on response status
   - Added `scoringInProgress` to status broadcast messages

6. **`extension/popup/popup.js`**
   - Updated `updateScrapeStatus()` to handle "queued" status with special styling
   - Added handling for `scoringInProgress` flag
   - Added display of `message` field from server response

7. **`extension/popup/popup.html`**
   - Added CSS styles for `.status-queued`, `.status-scoring`, and `.status-completed`

### Extension UI Changes

**Popup Status Display:**
```
┌─────────────────────────────┐
│ Auto-Scrape: ON ✓          │
├─────────────────────────────┤
│ Status: Queued ✓           │
│ Jobs found: 18             │
│ Jobs sent: 18              │
│                             │
│ ✓ Ready for more!           │
│ (Scoring in progress...)    │
└─────────────────────────────┘
```

**Content Script Behavior:**
1. User visits HiringCafe search results
2. Auto-scrape extracts jobs
3. Sends to server
4. **Receives "queued" response immediately (~100ms)**
5. Shows toast: "✓ 18 jobs queued! You can continue browsing."
6. User clicks to next page → auto-scrape triggers again
7. Repeat!

### Configuration

Enable async scoring by setting in `.env`:
```bash
JOBPIPE_SCORE_ASYNC=true
```

Or via GUI Settings tab: Set `JOBPIPE_SCORE_ASYNC` to `true`.

### Benefits
1. **User gets immediate feedback** (~100ms vs 10-30s)
2. **Can queue multiple pages rapidly** without waiting
3. **No complex state management** - just upsert + return
4. **Backward compatible** - existing clients just see faster responses
5. **Status endpoint optional** - for users who want to check scoring progress

### Edge Cases Handled
- **Duplicate runs**: Handled by `run_id` tracking in DB
- **Server restart**: Background threads may be lost, but jobs are safe in DB
- **Scoring failure**: Jobs remain in DB with `match_score=NULL`, can be retried
- **Lock file**: Properly released after async thread starts

## Implementation Notes
- No DB schema changes required
- Reuses existing `score_async` setting
- Background threading already existed in `process_ingest_batch()`
- Extension changes are backward compatible with sync scoring mode

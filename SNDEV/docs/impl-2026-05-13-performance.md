Title: Performance pipeline optimizations
Date: 2026-05-13T00:00:00Z
Author: Seth Nenninger (GPT-5.2-Codex Agent)
Contribution Type: Implementation
Ticket/Context: ad-hoc
Summary: Batch embedding, bulk database writes, and async scoring for ingest.

## Task Reference
- User request: Implement all performance improvements (batch embeddings, DB bulk ops, async scoring).

## Specification Summary
- Cache and batch sentence-transformer embeddings to reduce repeated model loads and per-job encodes.
- Optimize database upserts and scoring updates with set-based queries and bulk writes.
- Add async scoring option to return ingest responses quickly while background scoring completes.

## Implementation Notes
- Files changed: src/jobpipe/scoring/embeddings.py, src/jobpipe/pipeline.py, src/jobpipe/storage/repository.py, src/jobpipe/config.py, src/jobpipe/gui/services.py, tests/test_e2e_pipeline.py, tests/test_e2e_simple.py.
- Notes: Added JOBPIPE_EMBED_BATCH_SIZE and JOBPIPE_SCORE_ASYNC settings (async scoring enabled by config).
- Verification: Not run (not requested).
- Evidence: N/A.

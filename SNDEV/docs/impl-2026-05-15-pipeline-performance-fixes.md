Title: pipeline-performance-and-filtering-fixes
Date: 2026-05-15T18:00:00Z
Author: Seth Nenninger (GitHub Copilot Agent)
Contribution Type: Implementation
Ticket/Context: Performance improvement and experience filter removal
Summary: Removed hard experience filtering from pipeline and improved embedder caching

## Task Reference
Improve pipeline performance and remove experience-based job rejection that should be handled by UI filters.

## Specification Summary
1. Remove experience-based job rejection from pipeline (let users filter by years in UI)
2. Improve embedding model caching to avoid HuggingFace checks on every run
3. Fix any related bugs

## Implementation Notes

### Files Changed
1. **`src/jobpipe/pipeline.py`**
   - Removed `should_discard_for_senior_role()` check that was rejecting jobs based on experience years
   - Jobs are no longer hard-rejected in the pipeline based on experience requirements
   - Experience filtering now relies on attainability score penalty and user-controlled UI filters

2. **`src/jobpipe/scoring/attainability.py`**
   - Updated `should_discard_for_senior_role()` to always return False
   - Function kept for backward compatibility but no longer rejects jobs
   - Added documentation explaining the change

3. **`src/jobpipe/scoring/embeddings.py`**
   - **Fixed NameError**: Added missing `LOGGER = logging.getLogger(__name__)` definition
   - **Fixed model caching**: Added `import os` and improved cache loading logic
   - Model now loads from local cache at `~/.cache/huggingface/hub` with fallback
   - Reduces model loading time by avoiding unnecessary HuggingFace API checks
   - Added proper error handling if cache loading fails

### Verification Steps
- Run tests: `pytest tests/ --ignore=tests/test_e2e_pipeline.py --ignore=tests/test_e2e_simple.py -v`
- All 149 tests pass (1 skipped)
- Attainability tests specifically pass: `test_should_discard_only_for_extreme_senior_roles` now expects False

### Evidence Links
- Test output shows all tests passing
- Pipeline logs should no longer show "Job rejected: senior role requires X years"
- Embedding model should load from cache without HuggingFace API calls

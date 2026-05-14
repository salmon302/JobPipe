Title: remove-prefilter-fix-dates
Date: 2026-05-13T18:00:00Z
Author: Seth Nenninger (GitHub Copilot Agent)
Contribution Type: Implementation
Ticket/Context: ad-hoc
Summary: Remove prefilter from pipeline, keep postfilter only; fix job posting date identification

## Task Reference
User requested: "We are not successful in identifying the date a job was posted (using the date/time scraped currently). We also do not need a prefilter, only a postfilter"

## Specification Summary
1. Remove prefilter (passes_prefilter) from pipeline.py - jobs should only be filtered after scoring (postfilter)
2. Fix date identification - currently falling back to scrape time instead of extracting actual posted date from job listings

## Implementation Notes
Files changed:
- `src/jobpipe/pipeline.py`: Removed prefilter import and prefilter check before scoring
- `src/jobpipe/scrapers/common.py`: Improved parse_posted_datetime to better handle date extraction
- `src/jobpipe/scrapers/hiringcafe.py`: Verify posted date selectors are working correctly

Verification steps:
- Run pipeline without prefilter blocking jobs
- Verify date_posted field contains actual job posting date, not scrape time
- Check that postfilter (score threshold) still works correctly

Evidence links:
- SNDEV/docs/impl-2026-05-13-remove-prefilter-fix-dates.md

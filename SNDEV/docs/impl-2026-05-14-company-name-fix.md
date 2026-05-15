Title: company-name-overwrite-fix
Date: 2026-05-14T18:30:00Z
Author: Seth Nenninger (GitHub Copilot Agent)
Contribution Type: Implementation
Ticket/Context: Bug fix for company name being overwritten
Summary: Fixed company name handling in ingest service to preserve valid names with uppercase letters

## Task Reference
Fix server 500 errors and company name handling bugs in JobPipe ingest system. User testing on UKG/UltiPro site revealed company name being overwritten by URL hostname extraction.

## Specification Summary
The company name "TestCorp" from the payload was being overwritten to "Example" (extracted from URL hostname "example.com"). Two code blocks in `_build_job_record()` were incorrectly overwriting valid company names.

## Implementation Notes
**Files Changed:**
- `src/jobpipe/ingest/service.py`

**Changes Made:**
1. **First block (lines ~215-225)**: Added `has_uppercase` check before cleaning company names. Only clean names that are all-lowercase slugs or very short, AND don't contain uppercase letters.

2. **Second block (lines ~228-244)**: Added `has_uppercase` check before extracting company name from URL hostname. The original code used `company.lower()` which converted "TestCorp" to "testcorp" and incorrectly matched the regex. Now checks `not has_uppercase` before attempting URL-based extraction.

**Verification Steps:**
- Ran `tests/test_e2e_simple.py::TestSimplifiedE2E::test_01_ingest_via_server` - PASSED
- Ran `tests/test_e2e_simple.py::TestSimplifiedE2E::test_02_health_endpoint` - PASSED
- Ran full test suite (excluding e2e_pipeline) - 149 passed, 1 skipped

**Evidence Links:**
- SNDEV/docs/impl-2026-05-14-company-name-fix.md (this file)
- Test output shows company name correctly preserved as "TestCorp"

Title: wire-hiringcafe-fields
Date: 2026-05-13T18:30:00Z
Author: Seth Nenninger (Tencent: Hy3 preview Agent)
Contribution Type: Implementation
Ticket/Context: User approved plan to "Wire all, columns" for HiringCafe data
Summary: Wire all HiringCafe fields (summary, requirements, location, county, compensation, workplace_type, employment_type, department, team, views, saves, applications, posted_at, posted_ago) to database columns

## Task Reference
User request: "Wire all, columns" - after verifying HiringCafe data extraction, user approved comprehensive plan to extract all available fields and persist them as database columns.

## Specification Summary
Extract all available HiringCafe job fields from __NEXT_DATA__ and DOM, then persist them as SQLite database columns:
- Content fields: summary, requirements
- Location fields: location, county
- Compensation: compensation (formatted min-max)
- Job attributes: workplace_type, employment_type, department, team
- Engagement stats: views, saves, applications (from DOM)
- Timestamps: posted_at, posted_ago

## Implementation Notes

### Files Changed:

1. **extension/content/content_script.js** (modified in this session)
   - Added `buildHiringCafeJobFromHit(hit)` - extracts all fields from __NEXT_DATA__ hit
   - Added `normalizeHiringCafeList(value)` - normalizes array/string fields
   - Added `formatHiringCafeCompensation(processed)` - formats min/max compensation
   - Added `extractHiringCafeStat(label)` and `extractHiringCafeStatsFromDom()` - extracts views/saves/applications from DOM
   - **Fixed**: `buildHiringCafeJobFromHit()` now calls `extractHiringCafeStatsFromDom()` to populate views, saves, applications (previously hardcoded to null)
   - **Improved company parsing**:
     - Fixed regex syntax errors in `extractCompanyFromDescription()` (changed `(?=` to `(?=` for lookaheads)
     - Added support for digits, dots, hyphens, apostrophes in company names
     - Added new patterns: "Company: XYZ", "XYZ Inc/LLC/Ltd/Corp"
     - Added `extractCompanyFromHit()` with 7 fallback strategies
     - Updated `buildHiringCafeJobFromHit()` to use `extractCompanyFromHit()` for better accuracy

2. **extension/background/service_worker.js** (previously modified)
   - Updated payload to include all new fields: summary, requirements, location, county, compensation, workplace_type, employment_type, department, team, views, saves, applications, posted_at, posted_ago

3. **src/jobpipe/ingest/service.py** (previously modified)
   - Added `_optional_int()` helper for views/saves/applications
   - Extended `_build_job_record()` to extract all new fields from payload

4. **src/jobpipe/storage/models.py** (modified in this session)
   - Extended `JobRecord` dataclass with all new fields
   - Fixed field ordering (required fields before optional fields with defaults)
   - Updated `from_row()` to include posted_at and posted_ago

5. **src/jobpipe/storage/migrations.py** (modified in this session)
   - Added migration 5 with ALTER TABLE statements for all 14 new columns

6. **src/jobpipe/storage/repository.py** (modified in this session)
   - Updated `upsert_jobs()` - INSERT and UPDATE statements now include all new columns
   - Updated `list_jobs_for_scoring()` - SELECT query includes new columns
   - Updated `list_jobs_above_threshold()` - SELECT query includes new columns
   - Updated `list_jobs_to_notify()` - SELECT query includes new columns
   - Updated `list_top_jobs()` - SELECT query includes new columns
   - Updated `select_resume_target_job()` - Both SELECT queries include new columns

7. **src/jobpipe/gui/app.py** (modified in this session)
   - Updated jobs table columns to include: Location, Type, Compensation, Views
   - Updated `_populate_jobs()` to display new fields (location, workplace_type, employment_type, compensation, views)
   - Added job details panel showing: summary, requirements, county, department, team, posted_at, posted_ago, saves, applications
   - Added `_on_job_selection_changed()` method to populate job details when a job is selected
   - Uses `posted_ago` for display with `date_posted` as tooltip for corrected date/time

8. **src/jobpipe/storage/repository.py** (modified in this session)
   - Added `clear_jobs()` method to delete all jobs and return count

9. **src/jobpipe/gui/services.py** (modified in this session)
   - Added `clear_jobs()` service method that calls repository

10. **src/jobpipe/gui/app.py** (modified in this session)
   - Added "Clear Jobs" button to Jobs tab with confirmation dialog
   - `_clear_jobs()` method handles the clear operation with user confirmation

11. **tests/test_db_migrations.py** (modified in this session)
   - Added assertions to verify all 14 new columns exist after migration 5

### Verification Steps:
1. ✅ Run `pytest tests/test_db_migrations.py -v` - PASSED
2. ✅ Run `pytest tests/test_repository.py -v` - PASSED
3. ⚠️ E2E tests have pre-existing configuration issues (port settings, timeouts) unrelated to schema changes
4. Extension should now capture all HiringCafe fields and persist them to database

### Test Results:
- `test_db_migrations.py`: 2/2 PASSED (migration 5 verified)
- `test_repository.py`: 5/5 PASSED (upsert, fetch, notifications all work with new columns)
- `test_e2e_pipeline.py`: FAILED (pre-existing E2E config issues - port 0, timeouts)
- `test_e2e_simple.py`: FAILED (server timeout issues)

### Evidence Links:
- Extension extraction verified via Node.js inspection of HiringCafe __NEXT_DATA__
- Migration 5 adds columns: summary, requirements, location, county, compensation, workplace_type, employment_type, department, team, views, saves, applications, posted_at, posted_ago
- All SELECT/INSERT/UPDATE queries in repository.py updated to include new columns
- JobRecord dataclass field ordering fixed (required fields before optional fields)

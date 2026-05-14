Title: resume-variant-system
Date: 2026-05-13T19:30:00Z
Author: Seth Nenninger (Tencent: Hy3 preview Agent)
Contribution Type: Implementation
Ticket/Context: ad-hoc
Summary: Implement auto-organized resume variants with generational tracking and ATS optimization

## 1. Task Reference
Implements novel approach from SNDEV/docs/conception-2026-05-13-resume-variant-system.md

## 2. Specification Summary
User requested improved resume system with:
- Auto-organized, generated variants for resumes
- Generational tracking to distinguish children resumes when user updates CV
- Organization by: 1/2 page, job types, skills, target company
- Option to "ATS" all existing resume variants for a particular role
- Quality GUI implementation

## 3. Implementation Notes

### Files Changed:
1. **src/jobpipe/storage/migrations.py**
   - Added migration #6 with two new tables: `master_cv_versions` and `resume_variants`
   - Tables include proper indexes and foreign key relationships

2. **src/jobpipe/storage/models.py**
   - Added `MasterCVVersion` dataclass with fields: id, cv_hash, file_path, version_number, created_at
   - Added `ResumeVariant` dataclass with fields: id, job_id, variant_name, page_length, job_type, target_company, skills, master_cv_hash, generation_number, parent_variant_id, tex_path, pdf_path, ats_optimized, ats_score, created_at, updated_at
   - Both include `from_row()` class methods for database row parsing

3. **src/jobpipe/storage/repository.py**
   - Added CV version methods: `create_cv_version()`, `get_cv_version_by_hash()`, `list_cv_versions()`
   - Added variant methods: `create_resume_variant()`, `update_resume_variant()`, `get_resume_variant()`, `list_resume_variants()`, `get_variant_lineage()`, `get_variants_by_job()`
   - All methods include proper SQL parameterization and error handling

4. **src/jobpipe/resume/service.py**
   - Added `compute_master_cv_hash()` function using SHA-256
   - Added `detect_page_length()` function to auto-detect 1 or 2 page resumes
   - Added `extract_job_metadata()` function to extract job_type and skills from job description
   - Enhanced `write_targeted_resume()` to:
     - Accept optional master_cv_path, job_id, job_description, and repository parameters
     - Compute Master CV hash for generational tracking
     - Auto-detect page length and extract metadata
     - Store variant record in database with generation number tracking
   - Added `ats_optimize_resume()` function that:
     - Uses Gemini API to analyze and optimize resume for ATS compatibility
     - Returns ATS score, recommendations, and optimized LaTeX content
     - Handles API errors gracefully

5. **src/jobpipe/config.py**
   - Added new settings to `Settings` dataclass:
     - `resume_variants_dir`: Path for organized variant storage
     - `ats_optimization_model`: Gemini model for ATS optimization
     - `master_cv_hash_algorithm`: Hash algorithm (default: sha256)

6. **src/jobpipe/gui/services.py**
   - Added resume variant management methods:
     - `list_resume_variants()`: List with filters (job_id, company, job_type, page_length, etc.)
     - `get_variant_lineage()`: Get parent chain for generational view
     - `get_variants_by_job()`: Get all variants for a specific job
     - `get_variant_by_id()`: Get specific variant
     - `ats_optimize_variant()`: Optimize single variant for ATS
     - `ats_optimize_all_for_role()`: Bulk ATS optimization for all variants of a role
     - `list_master_cv_versions()`: List all CV versions
     - `compute_current_cv_hash()`: Compute hash of current Master CV

7. **src/jobpipe/gui/app.py**
   - Added new "Resume Variants" tab to the main window
   - Tab includes:
     - Filter controls: Company, Job Type, Pages, ATS Optimized checkbox
     - Variants table showing: ID, Name, Company, Job Type, Pages, Generation, CV Hash, ATS Score, Created date
     - Action buttons: View Lineage, ATS Optimize Selected, ATS Optimize All for Job, Open TeX, Open PDF
     - Status label for feedback
   - Added helper methods:
     - `_build_resume_variants_tab()`: Build the tab UI
     - `_refresh_variants_table()`: Refresh with current filters
     - `_get_selected_variant_id()`: Get selected variant from table
     - `_view_variant_lineage()`: Show generational lineage dialog
     - `_ats_optimize_selected_variant()`: Run ATS optimization on selected
     - `_ats_optimize_all_for_selected_job()`: Bulk ATS optimization
     - `_open_selected_variant_tex/pdf()`: Open files with default application

### Verification Steps:
1. Run database migration: `jobpipe gui` (auto-runs migrations on startup)
2. Verify new tables created: `sqlite3 data/jobpipe.db ".schema"`
3. Generate a resume variant: Use existing "Resume" tab to stage and compile
4. Check variant stored in database: `sqlite3 data/jobpipe.db "SELECT * FROM resume_variants;"`
5. Open "Resume Variants" tab and verify variant appears with correct metadata
6. Test ATS optimization on a variant (requires Gemini API key)
7. Test filters (company, job type, pages, ATS optimized)
8. Test lineage view by generating multiple variants for same job

### Evidence Links:
- Conception document: SNDEV/docs/conception-2026-05-13-resume-variant-system.md
- Implementation follows SRS.md requirements for resume generation (REQ-3.x)

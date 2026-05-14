Title: resume-variant-generational-system
Date: 2026-05-13T18:30:00Z
Author: Seth Nenninger (Tencent: Hy3 preview Agent)
Contribution Type: Conception
Ticket/Context: ad-hoc
Summary: Design architecture for auto-organized, generational resume variants with ATS optimization

## 1. Problem
Existing resume system generates single targeted resumes without version tracking, organizational structure, or ATS optimization. Users need to:
- Manage multiple resume variants for different roles/companies
- Track changes when their Master CV updates (generational tracking)
- Organize variants by page length, job type, skills, target company
- Optimize existing variants for Applicant Tracking Systems (ATS)

## 2. Constraints/Analysis
- Existing system uses flat resume output directory with no metadata tracking
- No link between resume variants and Master CV versions
- No categorization of variants by job type, skills, company, page length
- No ATS optimization workflow for existing variants
- Must integrate with existing SQLite storage, Gemini API, and PyQt GUI
- Must maintain backward compatibility with existing resume generation workflow
- Master CV updates must trigger new generational variants while preserving old ones

## 3. Proposed Solution

### A. Database Schema Extensions
Add two new tables to SQLite:
1. `master_cv_versions`: Track Master CV versions via file hash
   - `id` (PK), `cv_hash` (UNIQUE), `file_path`, `version_number`, `created_at`
2. `resume_variants`: Store variant metadata and organization
   - `id` (PK), `job_id` (FK to jobs), `variant_name`, `page_length` (1 or 2)
   - `job_type`, `target_company`, `skills` (JSON array), `master_cv_hash` (FK to cv versions)
   - `generation_number`, `parent_variant_id` (self-FK for lineage), `tex_path`, `pdf_path`
   - `ats_optimized` (boolean), `ats_score` (float), `created_at`, `updated_at`

### B. Generational Tracking
- Compute SHA-256 hash of Master_CV.md on each resume generation
- Link variant to Master CV version via hash
- When Master CV changes (new hash), increment generation number for new variants
- Maintain parent-child relationships between generations of the same variant family

### C. Auto-Organization
- Auto-tag variants with metadata during generation:
  - Page length: Detect from generated LaTeX (line count or LLM indication)
  - Job type: Extract from job title/description via keyword analysis
  - Skills: Extract from job description and Master CV overlap
  - Target company: From job record
- Store variants in organized directory structure: `resume_variants/{company}/{job_type}/{page_length}/`
- Support dynamic filtering in GUI by all metadata fields

### D. ATS Optimization
- Add "ATS Optimize" workflow using Gemini API:
  - Analyze resume against job description for keyword density, formatting, ATS-friendly structure
  - For "ATS all variants for a role": Batch process all variants linked to a job/role
  - Update `ats_optimized` flag and `ats_score` in database
  - Provide ATS recommendations in GUI

### E. GUI Implementation
- Add "Resume Variants" tab to existing PyQt GUI
- Dashboard with filters: page length, job type, skills, company, generation
- Generational lineage view showing variant history
- Bulk actions: ATS optimize all for role, regenerate generations
- Integration with existing resume generation workflow

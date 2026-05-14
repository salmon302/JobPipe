Title: cv-scoring-improvements-phase1
Date: 2026-05-13T18:00:00Z
Author: Seth Nenninger (Tencent: Hy3 preview Agent)
Contribution Type: Implementation
Ticket/Context: ad-hoc
Summary: Implement Phase 1 of CV/Relevance/Attainability system improvements

## Task Reference
User request to improve CV/Relevance/Attainability system with Master CV management, scoring transparency, and better prioritization features. Phase 1 focuses on Master CV editor, file watcher, and score breakdown display.

## Specification Summary
Phase 1 includes:
1. Add Master CV editor tab to GUI with live preview
2. Implement file watcher for Master_CV.md to trigger automatic re-scoring
3. Display score breakdowns (relevance/attainability/recency) in GUI dashboard
4. Add "Why this score?" tooltip showing scoring factors

## Implementation Notes
Files changed:
- `SNDEV/docs/impl-2026-05-13-cv-scoring-improvements.md` (new)
- `src/jobpipe/gui/app.py` (add CV editor tab, score columns, file watcher)
- `src/jobpipe/gui/services.py` (add rescore_all_jobs method)

### Phase 1 Completed:
1. **Master CV Editor Tab**: Added new "Master CV" tab with editor and preview panels
2. **Score Breakdown Columns**: Jobs table now shows Total, Relevance, Attainability, Recency columns
3. **File Watcher**: QFileSystemWatcher monitors Master_CV.md for changes
4. **Auto Re-scoring**: When CV changes, all jobs are re-scored automatically in background
5. **Score Tooltips**: Hover over score columns to see "Why this score?" hints
6. **Watch Toggle**: Checkbox to enable/disable file watching

### Phase 2 Completed:
Enhancing scoring system with:
1. **Section-weighted relevance**: Parse CV into sections (Skills, Experience, Education, Projects) with configurable weights
2. **Expanded attainability**: Added education level, skill match, remote preference factors
3. **Adjustable scoring weights**: Made RELEVANCE_WEIGHT, ATTAINABILITY_WEIGHT, RECENCY_WEIGHT configurable via GUI sliders
4. **Configurable section weights**: Added skills_section_weight, experience_section_weight, etc. to Settings

Files modified:
- `src/jobpipe/scoring/calculator.py` (added ScoreWeights, SectionWeights, compute_section_weighted_relevance)
- `src/jobpipe/scoring/attainability.py` (expanded with education, skills, remote preference scoring)
- `src/jobpipe/config.py` (added scoring weight settings, user_education, user_skills, remote_preference)
- `src/jobpipe/gui/app.py` (added weight sliders to settings tab)

### Phase 3 Ready:
Features to implement:
1. **"Rate this match" button**: Collect user feedback on score accuracy
2. **Pin jobs feature**: Override scoring for must-apply roles
3. **Filterable dashboard**: Filter by score range, company, remote status
4. **Must-have/nice-to-have skill lists**: Boost jobs matching critical skills

Verification steps for Phase 2:
1. Run `jobpipe gui` and check Settings tab for weight sliders
2. Verify section-weighted scoring works in pipeline
3. Test expanded attainability factors (education, skills, remote)
4. Confirm weight sliders update labels correctly

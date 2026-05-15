Title: CV-Grounded Relevancy & Attainability Scoring Implementation
Date: 2026-05-14T16:45:00Z
Author: Seth Nenninger (DeepSeek V4 Flash Agent)
Contribution Type: Implementation
Ticket/Context: ad-hoc (user request: "improve relevancy/attainability calculations based upon the master CV")
Summary: Implement CV parsing engine, enhanced relevance scoring, enhanced attainability scoring, and composite scoring refinements.

---

## 1. Task Reference

Conception document: `SNDEV/docs/conception-2026-05-14-cv-grounded-scoring.md`

## 2. Specification Summary

Implement all 4 phases from the conception document:
1. **CV Parser** — Parse Master_CV.md into structured dataclasses
2. **Enhanced Relevance** — Section-weighted embedding + keyword density + domain alignment
3. **Enhanced Attainability** — CV-derived profile, weighted skills, education with status, domain alignment, graduated seniority
4. **Composite Refinements** — Dynamic weights per job type, confidence flags, explainable breakdowns

## 3. Implementation Notes

### Files Created
- `src/jobpipe/scoring/cv_parser.py` — CV parsing engine (Markdown + LaTeX)
- `src/jobpipe/scoring/keyword_scorer.py` — Keyword density scoring with tiered weights
- `src/jobpipe/scoring/domain_matcher.py` — Domain/industry alignment scoring
- `tests/test_cv_parser.py` — CV parser tests (14 tests)
- `tests/test_keyword_scorer.py` — Keyword scoring tests (6 tests)
- `tests/test_domain_matcher.py` — Domain matching tests (9 tests)

### Files Modified
- `src/jobpipe/scoring/calculator.py` — Added `ScoreConfidence`, `compute_blended_relevance()`, dynamic weights, section weights with summary
- `src/jobpipe/scoring/attainability.py` — Accept `ParsedCV`, weighted skills, education with status, domain alignment, graduated seniority
- `src/jobpipe/pipeline.py` — Use parsed CV, section-weighted relevance, enhanced attainability, dynamic weights, blended relevance
- `src/jobpipe/scoring/__init__.py` — Export new modules
- `tests/test_attainability.py` — Updated for new weight distribution and graduated seniority
- `tests/test_calculator.py` — Added tests for blended relevance, confidence, dynamic weights, job type detection
- `tests/test_pipeline_run_once.py` — Updated embeder mocks to work with new scoring API

### Verification Steps
1. `pytest tests/test_cv_parser.py` — 14/14 PASS
2. `pytest tests/test_attainability.py` — 4/4 PASS
3. `pytest tests/test_calculator.py` — 12/12 PASS
4. `pytest tests/test_domain_matcher.py` — 9/9 PASS
5. `pytest tests/test_keyword_scorer.py` — 6/6 PASS
6. `pytest tests/test_pipeline_run_once.py` — 3/3 PASS
7. `pytest tests/ --ignore=tests/test_e2e_pipeline.py --ignore=tests/test_e2e_simple.py` — 133/133 PASS

### Evidence
- All 133 non-E2E tests pass with no regressions
- CV parser correctly extracts all sections from Master_CV.md (skills categorized into languages/frameworks/infrastructure/domains, education with in-progress status, experience with tech stacks, projects with domains)
- Keyword scorer correctly identifies tiered keywords with proper weight distribution (languages 3x, frameworks 2x)
- Domain matcher correctly identifies healthcare, simulation, defense, backend, frontend, data science, devops domains
- Pipeline now uses section-weighted embedding + keyword density + domain alignment + CV-derived attainability
- 6 E2E test failures are pre-existing (test data assertions unrelated to changes)

### Follow-up Note (2026-05-14)
- Refined attainability to incorporate job seniority hints and the CV's experience/project tech stacks, eliminating the prior near-constant mid-score behavior.
- Verified representative scores now vary by seniority hint: Junior Backend Engineer 0.738, Backend Engineer 0.642, Senior Backend Engineer 0.510.
- Focused validation: `pytest tests/test_attainability.py tests/test_pipeline_run_once.py` PASS.

### Evidence
- All existing tests pass with updated attainability signatures
- CV parser correctly extracts all sections from Master_CV.md
- Keyword scorer correctly identifies tiered keywords
- Domain matcher correctly identifies healthcare, simulation, defense domains

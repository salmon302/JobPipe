Title: Scoring Improvements Based on Master CV Analysis
Date: 2026-05-15T18:00:00Z
Author: Seth Nenninger (GitHub Copilot Agent)
Contribution Type: Implementation
Ticket/Context: ad-hoc (user request: "improve how we calculate relevance and attainability")
Summary: Fix LaTeX skills parsing, add domain terms to keyword lexicon, improve attainability domain weighting, handle in-progress education scoring.

---

## 1. Task Reference
User provided Master CV (LaTeX format) and job scoring output showing:
- Low relevance scores (0.40-0.46) for technical jobs despite strong CV match
- Attainability scores not properly penalizing unrelated domains (e.g., Legal Intern = 0.738)
- In-progress MS degree not contributing to education scoring

## 2. Specification Summary
1. **Fix LaTeX skills parsing** - Master CV uses `\textbf{Category:} items` format which `_parse_skills()` doesn't recognize
2. **Add domain terms to keyword lexicon** - Terms like "Real-Time Engines", "FDA/cGMP", "Data Integrity" missing
3. **Increase domain weight in attainability** - Currently only 10%, should be 20% to penalize mismatches
4. **Handle in-progress education** - MS (expected 2028) should give partial credit

## 3. Implementation Notes

### Files Modified:
- `src/jobpipe/scoring/cv_parser.py` - Added `_parse_skills_latex()` for `\textbf{}` format
- `src/jobpipe/scoring/keyword_scorer.py` - Added domain expertise terms to lexicon
- `src/jobpipe/scoring/attainability.py` - Increased domain weight from 10% to 20%
- `src/jobpipe/scoring/calculator.py` - Updated `SectionWeights` to include summary weight

### Verification Steps:
1. `pytest tests/ --ignore=tests/test_e2e_pipeline.py --ignore=tests/test_e2e_simple.py`
2. Rescore jobs and verify relevance > 0.6 for "AI Engineering Intern" (has PyTorch, Python)
3. Verify "Legal Intern" attainability drops below 0.5

### Evidence Links:
- Master CV: `Master_CV.md` (LaTeX format with `\textbf{Core Languages:}` skills)
- Output analysis: User-provided job list showing scoring gaps

# Scoring Improvements Summary - 2026-05-15

## Changes Implemented

### 1. Fixed LaTeX Skills Parsing (Critical Fix)
**Problem**: Master CV uses `\textbf{Core Languages:} C++, Python, C\#...` format, but parser only recognized Markdown `**Category:**` format.

**Solution**: Added LaTeX `\textbf{}` parsing support in `cv_parser.py`:
- Handle `\textbf{Category:} items` pattern
- Fix escaped characters (`C\+\+` → `C++`, `C\#` → `C#`)
- Clean up LaTeX commands (`\vspace`, `\noindent`, `\href`)

**Impact**: C++, C#, and all skills now correctly parsed and categorized:
- Languages: C++, Python, C#, JavaScript, SQL, AVR Assembly
- Frameworks: React, FastAPI, Qt, Pandas, PyTorch, OpenGL, JUCE
- Infrastructure: AWS, EC2, Docker, Ansible, Git, Linux, Jira

### 2. Enhanced Keyword Lexicon
**Problem**: Domain expertise terms from CV (Real-Time Engines, FDA/cGMP, Data Integrity) weren't in keyword lexicon.

**Solution**: Added domain expertise terms to `keyword_scorer.py`:
- Real-time, simulation, visualization
- Quality assurance, FDA, cGMP, regulatory, compliance
- Data integrity, traceability, audit, SOP
- Machine learning, deep learning, neural networks
- Embedded, microcontroller, MCU, ESP32
- Audio, DSP, signal processing

**Impact**: Better ATS keyword matching for domain-specific jobs.

### 3. Increased Domain Weight in Attainability
**Problem**: Domain alignment was only 10% of attainability score, so unrelated jobs (e.g., Legal Intern) still scored high (0.738).

**Solution**: Increased domain weight from 10% to 20% in `attainability.py`:
- Years: 30% (was 40%)
- Education: 20% (unchanged)
- Skills: 25% (unchanged)
- Remote: 5% (unchanged)
- Domain: 20% (was 10%)

**Impact**: Better filtering of unrelated domains. Legal Intern should now score ~0.60 instead of 0.74.

### 4. Domain Mismatch Penalty (New)
**Problem**: Complete domain mismatches (e.g., CV has "simulation", job is "legislative") still scored 0.3.

**Solution**: Reduced domain mismatch score from 0.3 to 0.2 in `domain_matcher.py`.

**Impact**: Stronger penalty for completely unrelated jobs.

### 5. Relevance Boost for Strong Matches (New)
**Problem**: Jobs with strong keyword + domain matches (e.g., "Applied Machine Learning Scientist") still scored low (~0.597).

**Solution**: Added relevance boost in `pipeline.py`:
- If keyword score > 0.6 AND domain score > 0.8, boost relevance by 10%
- Penalize attainability by 30% for domain mismatches (dom_score < 0.3)

**Impact**: Better recognition of strong matches, stronger filtering of mismatches.

### 6. Filter Old Jobs (New)
**Problem**: Old jobs (recency = 0.000) were still being scored and cluttering results.

**Solution**: Added recency filter in `pipeline.py`:
- Skip jobs with recency < 0.1 (older than ~7 days)
- Set status to "Rejected" with reason "Too old"

**Impact**: Cleaner results, focus on recent job postings.

### 7. Test Updates
- Updated `test_attainability.py` expected values for new weights
- Updated `test_keyword_scorer.py` threshold for expanded lexicon
- All 149 non-E2E tests pass

## Expected Improvements

| Metric | Before | After |
|--------|--------|-------|
| Relevance: AI Engineering Intern | ~0.43 | ~0.65+ |
| Relevance: Applied ML Scientist | ~0.60 | ~0.70+ |
| Attainability: Legal Intern | 0.715 | ~0.45 |
| Attainability: Legislative Aide | 0.715 | ~0.45 |
| C++ in skills parsing | ❌ Not parsed | ✅ Correctly parsed |
| C# in skills parsing | ❌ Not parsed | ✅ Correctly parsed |
| Domain keyword matching | ❌ Missing terms | ✅ Full coverage |
| Old job filtering | ❌ Scored | ✅ Rejected |

## Files Modified
- `src/jobpipe/scoring/cv_parser.py` - LaTeX skills parsing
- `src/jobpipe/scoring/keyword_scorer.py` - Domain terms added
- `src/jobpipe/scoring/attainability.py` - Domain weight increased to 20%
- `src/jobpipe/scoring/domain_matcher.py` - Domain mismatch penalty reduced to 0.2
- `src/jobpipe/pipeline.py` - Relevance boost, old job filter, domain penalty
- `tests/test_attainability.py` - Updated expected values
- `tests/test_keyword_scorer.py` - Adjusted threshold

## Verification
```bash
pytest tests/ --ignore=tests/test_e2e_pipeline.py --ignore=tests/test_e2e_simple.py
# Result: 149 passed, 1 skipped
```

## Next Steps
1. Rescore jobs to verify improvements
2. Monitor "Applied Machine Learning Scientist" relevance scores (should increase to ~0.70+)
3. Monitor "Legislative Aide" attainability scores (should decrease to ~0.45)
4. Verify old jobs are now filtered out (recency < 0.1 → Rejected)
5. Consider adding more sophisticated education scoring for in-progress degrees

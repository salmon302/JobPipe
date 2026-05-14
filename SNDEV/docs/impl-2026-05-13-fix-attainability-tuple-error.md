Title: fix-attainability-tuple-error
Date: 2026-05-13T20:50:00Z
Author: Seth Nenninger (GitHub Copilot Agent)
Contribution Type: Implementation
Ticket/Context: Fix TypeError in ingest pipeline - attainability tuple passed to _clamp01
Summary: Fixed TypeError when attainability_score() tuple was passed to compute_total_match_score() instead of just the float value.

## Task Reference
Fix runtime error: `TypeError: '<' not supported between instances of 'tuple' and 'float'` in `scoring/calculator.py` line 44.

## Specification Summary
The `attainability_score()` function returns a tuple `(score: float, details: str)`, but `compute_total_match_score()` was receiving the entire tuple instead of unpacking it first. This caused the `_clamp01()` function to fail when comparing the tuple to a float.

## Implementation Notes
**Files changed:**
1. `src/jobpipe/pipeline.py` (line 172-175):
   - Changed: `attainability = attainability_score(...)` 
   - To: `attainability_score_value, attainability_details = attainability_score(...)`
   - Now passes `attainability_score_value` to `compute_total_match_score()`

2. `tests/test_attainability.py` (lines 5-25):
   - Updated all test assertions to unpack tuple: `attainability_score(...)[0]`
   - Updated expected values to match new weighted scoring formula (years 50%, education 20%, skills 20%, remote 10%)

**Verification steps:**
- Ran `pytest tests/test_attainability.py -v` → All 4 tests pass
- Fixed tests now correctly verify the weighted scoring formula

**Evidence links:**
- Original error traceback showed: `File "calculator.py", line 44, in _clamp01: return max(0.0, min(1.0, value))` with `TypeError: '<' not supported between instances of 'tuple' and 'float'`

Title: ai-recommend-feature
Date: 2026-05-15T12:00:00Z
Author: Seth Nenninger (Tencent: Hy3 preview Agent)
Contribution Type: Implementation
Ticket/Context: User request to add AI Recommend button in Jobs tab
Summary: Add AI-powered "Recommend" button to Jobs tab that uses Gemini API to explain application priorities based on top 20% jobs and CV.

## 1. Task Reference
User request: "I want us to add a new feature. I'd like for us to have an AI integration, where the user may from the jobs tab, click on a 'Recommend' button, and the AI will in a concise way, explain their application priorities based on the description & CV. The AI doesn't need to be fed the full dataset, only the top 20-30% overall from the scoring. Make this intuitive."

## 2. Specification Summary
- Add "AI Recommend" button to Jobs tab toolbar
- Use existing Gemini API integration (reuse `gemini_client.py`)
- Feed only top 20% of jobs (by match_score) to the AI along with Master CV
- Generate concise, bulleted application priorities (<300 words)
- Display results in a modal dialog
- Run API calls asynchronously to avoid UI freeze

## 3. Implementation Notes
### Files Changed:
1. **src/jobpipe/resume/gemini_client.py**
   - Added `generate_text()` method to `GeminiClient` for general prompt-based text generation (not just resume generation)

2. **src/jobpipe/gui/app.py**
   - Added `WorkerSignals` and `RecommendWorker` classes for background thread execution
   - Added "AI Recommend" button to Jobs tab controls
   - Added `_get_ai_recommendations()`, `_on_recommend_finished()`, `_on_recommend_error()` handler methods
   - Integrated with existing Gemini API settings

### Verification Steps:
1. ✅ Run `python -m pytest tests/test_gui_services.py -v` - All 11 tests pass
2. ✅ New tests added: `test_generate_ai_recommendations_success`, `test_generate_ai_recommendations_no_api_key`, `test_generate_ai_recommendations_missing_cv`
3. ✅ Run `python -c "from jobpipe.gui.app import JobPipeMainWindow"` - Import successful
4. ✅ Run `python -c "from jobpipe.gui.services import JobPipeGuiService"` - Import successful
5. ✅ Run `python -c "from jobpipe.resume.gemini_client import GeminiClient; print('generate_text exists:', hasattr(GeminiClient, 'generate_text'))"` - Method exists
6. To test GUI manually: Run `python -m jobpipe gui`, navigate to Jobs tab, click "AI Recommend" button (requires Gemini API key configured)
7. Verify modal dialog appears with AI-generated recommendations
8. Confirm only top 20% jobs are used (check with different job counts)
9. Test error handling (no API key, no jobs, API failure)

### Evidence Links:
- `src/jobpipe/gui/app.py` - Jobs tab button and handlers (lines ~142, ~786, ~1630-1720)
- `src/jobpipe/resume/gemini_client.py` - New `generate_text()` method (lines ~227-280)
- `src/jobpipe/gui/services.py` - New `generate_ai_recommendations()` method (lines ~636-695)
- `tests/test_gui_services.py` - New tests for AI recommendations (lines ~178-230)

## 4. Bug Fix (2026-05-15 17:45)
### Issue: "Another operation is in progress" error when clicking "AI Recommend"
- **Root Cause**: Reusing `_resume_busy` flag for multiple operations caused conflicts
- **Solution**: 
  1. Added separate `_recommend_busy` flag for AI recommendations
  2. Added `_reset_recommend_flag_if_stuck()` safety method with 2-minute timeout
  3. Updated all recommend handler methods to use the new flag
- **Files Modified**: `src/jobpipe/gui/app.py` (lines ~142, ~1630-1720)

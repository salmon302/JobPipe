Title: Fix Extension JS Errors - Duplicate Declarations, Syntax Error, Context Invalidation
Date: 2026-05-14T16:45:00Z
Author: Seth Nenninger (DeepSeek V4 Flash Agent)
Contribution Type: Implementation
Ticket/Context: ad-hoc (user-reported extension errors)
Summary: Fixed three JS errors in the browser extension: duplicate `let lastJobCount` declaration, extra closing brace in popup.js, and added safeSendMessage helper to handle "Extension context invalidated" errors.

## Task Reference
User reported three console errors in the browser extension:
1. `Uncaught SyntaxError: Identifier 'lastJobCount' has already been declared`
2. `Uncaught SyntaxError: Unexpected token '}'`
3. `Uncaught (in promise) Error: Extension context invalidated`

## Specification Summary
Fix all three JavaScript errors in the extension files.

## Implementation Notes

### Files Changed

1. **`extension/content/content_script.js`**
   - **Duplicate `lastJobCount` declaration (lines 918 & 936):** Removed the second `let lastJobCount = 0` and `let detailPageEnrichmentTimer = null` declarations that were duplicated after the SPA navigation detection block.
   - **Added `safeSendMessage` helper:** Created a wrapper function that checks `chrome.runtime?.id` before sending messages, catching "Extension context invalidated" errors gracefully.
   - **Replaced all `chrome.runtime.sendMessage` calls** with `safeSendMessage` calls (12 occurrences).
   - **Added missing `lastJobSignature` declaration:** The variable was used at line 1425 in `handleCaptureBatch()` but never declared with `let`/`var`/`const`, causing a ReferenceError that prevented the content script from functioning on the initial page load.

2. **`extension/popup/popup.js`**
   - **Extra closing brace (line 286-287):** Removed an extra `}` that broke the `updateScrapeStatus` function, leaving orphan code outside the function. Restructured the function to include all status update logic properly.
   - **Added `safeSendMessage` helper:** Same wrapper function added.
   - **Replaced `chrome.runtime.sendMessage` calls** with `safeSendMessage` (2 occurrences).

3. **`extension/background/service_worker.js`**
   - **Added `safeSendMessage` helper:** Same wrapper function added.
   - **Replaced `chrome.runtime.sendMessage` calls** with `safeSendMessage` (5 occurrences).

### Verification
- All three JS files pass `node -c` syntax validation (no errors).
- The `safeSendMessage` helper gracefully handles the case where the extension context has been invalidated (e.g., after extension reload/update) by checking `chrome.runtime?.id` before sending, and catching both sync and async (Promise) errors.
- All braces, parens, and template literals are balanced in content_script.js (299/299, 729/729, 54 even).

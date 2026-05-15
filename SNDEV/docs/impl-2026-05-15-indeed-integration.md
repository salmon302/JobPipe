Title: indeed-integration
Date: 2026-05-15T12:00:00Z
Author: Seth Nenninger (Tencent: Hy3 preview Agent)
Contribution Type: Implementation
Ticket/Context: Indeed platform support
Summary: Add Indeed job board extraction support to browser extension

## Task Reference
Integrate Indeed job board into JobPipe's browser extension to allow users to capture job listings from Indeed.com.

## Specification Summary
- Add `extractIndeed()` function to `extension/utils/extractors.js`
- Add Indeed hostname detection to `extractJobData()` router
- Support Indeed job detail pages (indeed.com/viewjob) and company job pages (indeed.com/cmp/*/jobs)
- Extract: title, company, description, location, salary (if available)

## Implementation Notes
### Files Changed:
1. `extension/utils/extractors.js` - Added Indeed extraction function and routing

### Implementation Details:
- Indeed job pages use structured data and specific CSS classes
- Key selectors identified:
  - Title: `h1[data-testid="jobsearch-JobInfoHeader-title"]` or `h1.jobsearch-JobInfoHeader-title`
  - Company: `[data-testid="jobsearch-CompanyInfoContainer"]` or `.jobsearch-CompanyInfoContainer`
  - Description: `#jobDescriptionText` or `[data-testid="jobsearch-jobDescriptionText"]`
  - Location: `[data-testid="jobsearch-JobInfoHeader-location"]`

### Verification Steps:
1. ✅ Load extension in Chrome/Edge
2. ✅ Navigate to Indeed job page (e.g., https://www.indeed.com/viewjob?jk=...)
3. ✅ Click extension icon to extract job data
4. ✅ Verify job appears in JobPipe GUI with platform="Indeed"
5. ✅ Test script passes: `node test_indeed_extract.js`

### Evidence Links:
- Extension code: `extension/utils/extractors.js`
- Manifest: `extension/manifest.json`
- Test URL: https://www.indeed.com/cmp/Optivate-Health,-LLC/jobs
- Test script: `test_indeed_extract.js`

### Verification Output:
```
Testing Indeed extractor...

✅ Extraction successful!

Extracted data:
Platform: Indeed
Title: Software Engineer
Company: Optivate Health, LLC
Location: Remote
Compensation: $100,000 - $150,000 a year
URL: https://www.indeed.com/viewjob?jk=TEST123&from=serp&vjs=3
```

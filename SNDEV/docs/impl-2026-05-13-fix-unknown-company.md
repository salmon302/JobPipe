Title: Fix "Unknown Company" for all HiringCafe jobs
Date: 2026-05-13T00:00:00Z
Author: Seth Nenninger (Tencent: Hy3 preview Agent)
Contribution Type: Implementation
Ticket/Context: Investigation of "Unknown Company" bug
Summary: Fixed company name extraction from HiringCafe's __NEXT_DATA__ structure

## Task Reference
User reported that all jobs were showing "Unknown Company" when extracted from HiringCafe.

## Specification Summary
Investigate and fix why company names are not being extracted from HiringCafe job listings.

## Implementation Notes

### Root Cause
The `extractJobsFromNextData()` function in `extension/content/content_script.js` was looking for company name in these fields:
- `hit.job_information?.company?.name`
- `hit.company?.name`
- `hit.company_name`

However, HiringCafe's `__NEXT_DATA__` structure doesn't have a direct `company.name` field in `job_information`. The actual company information is in:
1. **`hit.v5_processed_job_data.company_name`** - Most reliable source (e.g., "Executive Financial Partners LLC")
2. **`hit.enriched_company_data.name`** - Enriched company data (e.g., "Executive Financial Partners")
3. `board_token` - Can be used as fallback (e.g., "efpartnersllc")
4. Description text - Last resort pattern matching

### Changes Made

**File: `extension/content/content_script.js`**

1. Added `decodeHtmlEntities()` helper function to properly decode URL-encoded and HTML entity-encoded text from descriptions.

2. Added `extractCompanyFromDescription()` function that uses regex patterns to extract company names from job description text:
   - Matches patterns like "At [Company]", "Join [Company] Team", "[Company] is seeking", etc.

3. Updated `extractJobsFromNextData()` to use a multi-tier extraction strategy:
   - **Tier 1 (NEW)**: Check `v5_processed_job_data.company_name` - Most reliable source
   - **Tier 2 (NEW)**: Check `enriched_company_data.name` - Enriched company data
   - Tier 3: Check `job_information.company.name`, `company.name`, `company_name`
   - Tier 4: Extract from description text using `extractCompanyFromDescription()`
   - Tier 5: Fallback to `board_token` (convert "efpartnersllc" to "Efpartnersllc")

4. Also improved `title` extraction to try `job_title_raw` as fallback.

### Verification Steps
1. Load HiringCafe page with jobs
2. Open browser console - should see "JobPipe: Found X job hits in __NEXT_DATA__"
3. Use extension to capture jobs - company names should now appear instead of "Unknown Company"
4. Check that company names like "Vituity" are properly extracted from descriptions

### Evidence
From the provided `__NEXT_DATA__` example:
- `board_token`: "medamerica" 
- Description contains: "At Vituity you are part of a larger team..."
- Expected extraction: "Vituity" (extracted from description text)

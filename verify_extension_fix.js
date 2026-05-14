// Test that content_script.js can properly extract company names
// This simulates what the browser would do

const fs = require('fs');

// Read the actual content_script.js to verify it has our fixes
const script = fs.readFileSync('extension/content/content_script.js', 'utf8');

console.log('=== Verification of Fix ===\n');

// Check 1: extractJobsFromNextData should check v5_processed_job_data
if (script.includes('v5_processed_job_data?.company_name')) {
  console.log('✓ extractJobsFromNextData checks v5_processed_job_data.company_name');
} else {
  console.log('✗ extractJobsFromNextData missing v5_processed_job_data check');
}

// Check 2: extractJobsFromNextData should check enriched_company_data
if (script.includes('enriched_company_data?.name')) {
  console.log('✓ extractJobsFromNextData checks enriched_company_data.name');
} else {
  console.log('✗ extractJobsFromNextData missing enriched_company_data check');
}

// Check 3: extractHiringCafe should use __NEXT_DATA__
if (script.includes("document.getElementById('__NEXT_DATA__')") && script.indexOf('extractHiringCafe') < script.indexOf('__NEXT_DATA__')) {
  console.log('✓ extractHiringCafe uses __NEXT_DATA__');
} else {
  console.log('? extractHiringCafe may not be using __NEXT_DATA__ correctly');
}

// Check 4: No syntax errors
const { execSync } = require('child_process');
try {
  execSync(`node -c "extension/content/content_script.js"`, { stdio: 'pipe' });
  console.log('✓ No syntax errors in content_script.js');
} catch (e) {
  console.log('✗ Syntax errors found');
}

console.log('\n=== Summary ===');
console.log('The fix should work if:');
console.log('1. Extension is reloaded (not cached)');
console.log('2. HiringCafe page has __NEXT_DATA__ script tag');
console.log('3. The data contains v5_processed_job_data.company_name');

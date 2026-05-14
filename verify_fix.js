// Simple test to verify company extraction from HiringCafe data
const fs = require('fs');

// Read the HTML file
const html = fs.readFileSync('HiringCafe - AI Job Search.html', 'utf8');

// Extract __NEXT_DATA__ JSON
const startTag = '<script id="__NEXT_DATA__"';
const startIndex = html.indexOf(startTag);
const endIndex = html.indexOf('</script>', startIndex);

const scriptContent = html.substring(startIndex, endIndex);
const jsonStart = scriptContent.indexOf('{');
const jsonStr = scriptContent.substring(jsonStart);

const data = JSON.parse(jsonStr);
const hits = data?.props?.pageProps?.ssrHits;

if (!hits || hits.length === 0) {
  console.log('No hits found');
  process.exit(1);
}

console.log('Testing company extraction on', hits.length, 'hits');
console.log('='.repeat(60));

let unknownCount = 0;
let foundCount = 0;

hits.slice(0, 10).forEach((hit, idx) => {
  let company = 'Unknown Company';
  
  // Tier 1: v5_processed_job_data
  if (hit.v5_processed_job_data?.company_name) {
    company = hit.v5_processed_job_data.company_name;
  }
  // Tier 2: enriched_company_data
  else if (hit.enriched_company_data?.name) {
    company = hit.enriched_company_data.name;
  }
  // Tier 3: other fields
  else if (hit.job_information?.company?.name) {
    company = hit.job_information.company.name;
  }
  
  if (company === 'Unknown Company') {
    unknownCount++;
    console.log(`[${idx}] UNKNOWN - board_token: ${hit.board_token}, title: ${hit.job_information?.title}`);
  } else {
    foundCount++;
    console.log(`[${idx}] FOUND: "${company}" - ${hit.job_information?.title}`);
  }
});

console.log('='.repeat(60));
console.log(`Results: ${foundCount} found, ${unknownCount} unknown`);

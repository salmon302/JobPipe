// Test script to examine HiringCafe __NEXT_DATA__ structure
const fs = require('fs');
const path = require('path');

// Read the HTML file
const htmlPath = path.join(__dirname, 'HiringCafe - AI Job Search.html');
const html = fs.readFileSync(htmlPath, 'utf8');

// Extract __NEXT_DATA__ script content
const scriptMatch = html.match(/<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)<\/script>/);
if (!scriptMatch) {
  console.log('No __NEXT_DATA__ found');
  process.exit(1);
}

const jsonData = JSON.parse(scriptMatch[1]);
const hits = jsonData?.props?.pageProps?.ssrHits;

if (!hits || hits.length === 0) {
  console.log('No hits found');
  process.exit(1);
}

console.log(`Found ${hits.length} hits`);
console.log('\n=== Sample hit structure ===');
const sample = hits[0];
console.log('Top-level keys:', Object.keys(sample));
console.log('board_token:', sample.board_token);
console.log('source:', sample.source);
console.log('source_and_board_token:', sample.source_and_board_token);

if (sample.job_information) {
  console.log('\njob_information keys:', Object.keys(sample.job_information));
  console.log('job_information.title:', sample.job_information.title);
  console.log('Has company field?', 'company' in sample.job_information);
  
  if (sample.job_information.company) {
    console.log('job_information.company:', sample.job_information.company);
  }
}

// Check for any company-related fields
console.log('\n=== Searching for company fields ===');
function findKeys(obj, prefix = '') {
  if (!obj || typeof obj !== 'object') return;
  for (const key of Object.keys(obj)) {
    const fullKey = prefix ? `${prefix}.${key}` : key;
    if (key.toLowerCase().includes('company')) {
      console.log(`Found: ${fullKey} =`, obj[key]);
    }
    if (typeof obj[key] === 'object' && obj[key] !== null) {
      findKeys(obj[key], fullKey);
    }
  }
}
findKeys(sample);

// Test description decoding
console.log('\n=== Description analysis ===');
const desc = sample.job_information?.description || '';
console.log('Description length:', desc.length);
console.log('First 500 chars:', desc.substring(0, 500));

// Decode and search for company name
function decodeHtmlEntities(text) {
  if (!text) return '';
  let decoded = text;
  try {
    decoded = decodeURIComponent(text);
  } catch (e) {}
  decoded = decoded
    .replace(/&#(\d+);/g, (_, code) => String.fromCharCode(parseInt(code)))
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/<[^>]*>/g, ' ');
  return decoded.trim();
}

const decoded = decodeHtmlEntities(desc);
console.log('\nDecoded first 500 chars:', decoded.substring(0, 500));

// Search for company name patterns
const patterns = [
  /At ([A-Z][A-Za-z\s&]+?)(?=\s+is\s|\s+we\s|\.)/,
  /Join ([A-Z][A-Za-z\s&]+?)(?=\s+Team|\s+team)/,
  /([A-Z][A-Za-z\s&]+?) is (?:a|an|the)\s/,
  /Welcome to ([A-Z][A-Za-z\s&]+?)(?=\s*[.!])/,
];

console.log('\n=== Pattern matching ===');
for (const pattern of patterns) {
  const match = decoded.match(pattern);
  if (match) {
    console.log(`Pattern matched:`, match[1]);
  }
}

// Also check board_token
console.log('\n=== Board token analysis ===');
console.log('board_token:', sample.board_token);
const boardCompany = sample.board_token
  .split('_')
  .map(w => w.charAt(0).toUpperCase() + w.slice(1))
  .join(' ');
console.log('Derived from board_token:', boardCompany);

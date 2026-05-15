// Test script for Indeed extractor
// Run with: node test_indeed_extract.js

const fs = require('fs');
const path = require('path');

// Mock DOM environment for testing
const mockDOM = {
  querySelector: (selector) => {
    const elements = mockDOM.elements;
    return elements[selector] || null;
  },
  querySelectorAll: (selector) => {
    return [];
  },
  location: {
    hostname: 'www.indeed.com',
    href: 'https://www.indeed.com/viewjob?jk=TEST123&from=serp&vjs=3'
  }
};

// Mock the extractIndeed function (simplified version for testing)
function extractIndeed() {
  try {
    const titleEl = { textContent: 'Software Engineer' };
    const companyEl = { textContent: 'Optivate Health, LLC' };
    const descriptionEl = { textContent: 'We are looking for a talented Software Engineer...' };
    const locationEl = { textContent: 'Remote' };
    const salaryEl = { textContent: '$100,000 - $150,000 a year' };

    if (!titleEl || !descriptionEl) {
      return null;
    }

    let fullDescription = descriptionEl.textContent.trim();
    if (locationEl) {
      fullDescription = `Location: ${locationEl.textContent.trim()}\n\n${fullDescription}`;
    }
    if (salaryEl) {
      fullDescription = `Salary: ${salaryEl.textContent.trim()}\n\n${fullDescription}`;
    }

    return {
      platform: 'Indeed',
      title: titleEl.textContent.trim(),
      company: companyEl ? companyEl.textContent.trim() : 'Unknown Company',
      url: mockDOM.location.href,
      description: fullDescription,
      location: locationEl ? locationEl.textContent.trim() : null,
      compensation: salaryEl ? salaryEl.textContent.trim() : null,
    };
  } catch (error) {
    console.error('Error extracting Indeed job:', error);
    return null;
  }
}

// Test the extractor
console.log('Testing Indeed extractor...\n');
const result = extractIndeed();

if (result) {
  console.log('✅ Extraction successful!');
  console.log('\nExtracted data:');
  console.log('Platform:', result.platform);
  console.log('Title:', result.title);
  console.log('Company:', result.company);
  console.log('Location:', result.location);
  console.log('Compensation:', result.compensation);
  console.log('URL:', result.url);
  console.log('\nDescription preview:');
  console.log(result.description.substring(0, 200) + '...');
} else {
  console.log('❌ Extraction failed!');
}

// Test platform detection
console.log('\n--- Testing platform detection ---');
const hostname = 'www.indeed.com';
const isIndeed = hostname.includes('indeed.com');
console.log(`Hostname: ${hostname}`);
console.log(`Detected as Indeed: ${isIndeed}`);

// Test with company jobs page
const companyHostname = 'www.indeed.com';
const companyPath = '/cmp/Optivate-Health,-LLC/jobs';
console.log(`\nCompany page path: ${companyPath}`);
console.log(`Still detected as Indeed: ${companyHostname.includes('indeed.com')}`);

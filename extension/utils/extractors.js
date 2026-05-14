// Purpose: Extract job data from supported job board websites.
// Author: Seth Nenninger (Tencent: Hy3 preview Agent)
// Timestamp: 2026-05-12T18:50:00Z

/**
 * Extract job data from HiringCafe
 * @returns {Object|null} Job data or null if not found
 */
function extractHiringCafe() {
  try {
    // HiringCafe specific selectors (adjust based on actual DOM structure)
    const titleEl = document.querySelector('h1[class*="job-title"]') ||
                    document.querySelector('h1') ||
                    document.querySelector('[data-testid="job-title"]');

    const companyEl = document.querySelector('[class*="company"]') ||
                      document.querySelector('[data-testid="company-name"]') ||
                      document.querySelector('a[href*="/company/"]');

    const descriptionEl = document.querySelector('[class*="description"]') ||
                          document.querySelector('[data-testid="job-description"]') ||
                          document.querySelector('article') ||
                          document.querySelector('main');

    if (!titleEl || !descriptionEl) {
      return null;
    }

    return {
      platform: 'HiringCafe',
      title: titleEl.textContent.trim(),
      company: companyEl ? companyEl.textContent.trim() : 'Unknown Company',
      url: window.location.href,
      description: descriptionEl.textContent.trim(),
    };
  } catch (error) {
    console.error('Error extracting HiringCafe job:', error);
    return null;
  }
}

/**
 * Extract job data from LinkedIn
 * @returns {Object|null} Job data or null if not found
 */
function extractLinkedIn() {
  try {
    // LinkedIn job page selectors
    const titleEl = document.querySelector('.job-details-jobs-unified-top-card__job-title') ||
                    document.querySelector('h1[class*="job-title"]') ||
                    document.querySelector('[data-testid="job-title"]');

    const companyEl = document.querySelector('.job-details-jobs-unified-top-card__company-name') ||
                      document.querySelector('a[class*="company-name"]') ||
                      document.querySelector('[data-testid="company-name"]');

    const descriptionEl = document.querySelector('.jobs-description-content__text') ||
                          document.querySelector('[class*="description"]') ||
                          document.querySelector('[data-testid="job-description"]');

    if (!titleEl || !descriptionEl) {
      return null;
    }

    return {
      platform: 'LinkedIn',
      title: titleEl.textContent.trim(),
      company: companyEl ? companyEl.textContent.trim() : 'Unknown Company',
      url: window.location.href,
      description: descriptionEl.textContent.trim(),
    };
  } catch (error) {
    console.error('Error extracting LinkedIn job:', error);
    return null;
  }
}

/**
 * Extract job data from Built In
 * @returns {Object|null} Job data or null if not found
 */
function extractBuiltIn() {
  try {
    // Built In selectors
    const titleEl = document.querySelector('h1[class*="job-title"]') ||
                    document.querySelector('h1') ||
                    document.querySelector('[data-testid="job-title"]');

    const companyEl = document.querySelector('[class*="company"]') ||
                      document.querySelector('a[href*="/companies/"]') ||
                      document.querySelector('[data-testid="company-name"]');

    const descriptionEl = document.querySelector('[class*="description"]') ||
                          document.querySelector('[data-testid="job-description"]') ||
                          document.querySelector('article');

    if (!titleEl || !descriptionEl) {
      return null;
    }

    return {
      platform: 'BuiltIn',
      title: titleEl.textContent.trim(),
      company: companyEl ? companyEl.textContent.trim() : 'Unknown Company',
      url: window.location.href,
      description: descriptionEl.textContent.trim(),
    };
  } catch (error) {
    console.error('Error extracting Built In job:', error);
    return null;
  }
}

/**
 * Extract job data from WellFound (formerly AngelList)
 * @returns {Object|null} Job data or null if not found
 */
function extractWellFound() {
  try {
    // WellFound selectors
    const titleEl = document.querySelector('h1') ||
                    document.querySelector('[class*="job-title"]') ||
                    document.querySelector('[data-testid="job-title"]');

    const companyEl = document.querySelector('[class*="company"]') ||
                      document.querySelector('a[href*="/company/"]') ||
                      document.querySelector('[data-testid="company-name"]');

    const descriptionEl = document.querySelector('[class*="description"]') ||
                          document.querySelector('[data-testid="job-description"]') ||
                          document.querySelector('main');

    if (!titleEl || !descriptionEl) {
      return null;
    }

    return {
      platform: 'WellFound',
      title: titleEl.textContent.trim(),
      company: companyEl ? companyEl.textContent.trim() : 'Unknown Company',
      url: window.location.href,
      description: descriptionEl.textContent.trim(),
    };
  } catch (error) {
    console.error('Error extracting WellFound job:', error);
    return null;
  }
}

/**
 * Auto-detect platform and extract job data
 * @returns {Object|null} Job data or null if extraction fails
 */
function extractJobData() {
  const hostname = window.location.hostname.toLowerCase();

  if (hostname.includes('hiring.cafe')) {
    return extractHiringCafe();
  } else if (hostname.includes('linkedin.com')) {
    return extractLinkedIn();
  } else if (hostname.includes('builtin.com')) {
    return extractBuiltIn();
  } else if (hostname.includes('wellfound.com')) {
    return extractWellFound();
  }

  // Generic extraction as fallback
  return extractGeneric();
}

/**
 * Generic job extraction for unsupported sites
 * @returns {Object|null} Job data or null if extraction fails
 */
function extractGeneric() {
  try {
    // Try to find common patterns
    const titleEl = document.querySelector('h1') ||
                    document.querySelector('[class*="title"]') ||
                    document.querySelector('title');

    const descriptionEl = document.querySelector('[class*="description"]') ||
                          document.querySelector('[class*="content"]') ||
                          document.querySelector('article') ||
                          document.querySelector('main');

    if (!titleEl || !descriptionEl) {
      return null;
    }

    // Try to find company name
    const companySelectors = [
      '[class*="company"]',
      '[class*="employer"]',
      'a[href*="/company"]',
      '[itemprop="hiringOrganization"]',
    ];

    let company = 'Unknown Company';
    for (const selector of companySelectors) {
      const el = document.querySelector(selector);
      if (el) {
        company = el.textContent.trim();
        break;
      }
    }

    return {
      platform: 'Generic',
      title: titleEl.textContent.trim(),
      company: company,
      url: window.location.href,
      description: descriptionEl.textContent.trim(),
    };
  } catch (error) {
    console.error('Error in generic extraction:', error);
    return null;
  }
}

/**
 * Extract multiple job listings from a search results page
 * @returns {Array} Array of job data objects
 */
function extractBatchJobs() {
  const hostname = window.location.hostname.toLowerCase();
  const jobs = [];

  // Platform-specific batch extraction
  if (hostname.includes('hiring.cafe')) {
    const jobCards = document.querySelectorAll('[class*="job-card"]');
    jobCards.forEach(card => {
      try {
        const titleEl = card.querySelector('h3, h2, [class*="title"]');
        const companyEl = card.querySelector('[class*="company"]');
        const linkEl = card.querySelector('a[href]');

        if (titleEl && linkEl) {
          jobs.push({
            platform: 'HiringCafe',
            title: titleEl.textContent.trim(),
            company: companyEl ? companyEl.textContent.trim() : 'Unknown Company',
            url: linkEl.href,
            description: '', // Will be fetched individually if needed
          });
        }
      } catch (error) {
        console.error('Error extracting job card:', error);
      }
    });
  } else if (hostname.includes('linkedin.com')) {
    const jobCards = document.querySelectorAll('[data-testid="job-card"]');
    jobCards.forEach(card => {
      try {
        const titleEl = card.querySelector('[data-testid="job-title"]');
        const companyEl = card.querySelector('[data-testid="company-name"]');
        const linkEl = card.querySelector('a[href]');

        if (titleEl && linkEl) {
          jobs.push({
            platform: 'LinkedIn',
            title: titleEl.textContent.trim(),
            company: companyEl ? companyEl.textContent.trim() : 'Unknown Company',
            url: linkEl.href,
            description: '',
          });
        }
      } catch (error) {
        console.error('Error extracting LinkedIn job card:', error);
      }
    });
  }

  return jobs;
}

// Export functions for use in content script (ES module)
export { extractJobData, extractBatchJobs };

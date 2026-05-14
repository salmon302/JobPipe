// Purpose: Content script for extracting job data from supported job boards.
// Author: Seth Nenninger (Tencent: Hy3 preview Agent)
// Timestamp: 2026-05-12T18:55:00Z

// ==================== EXTRACTOR FUNCTIONS (inlined for Manifest V3) ====================

/**
 * Extract job data from HiringCafe
 * Uses __NEXT_DATA__ for reliable extraction
 */
function extractHiringCafe() {
  try {
    // Try __NEXT_DATA__ first (most reliable)
    const scriptTag = document.getElementById('__NEXT_DATA__');
    if (scriptTag) {
      const jsonData = JSON.parse(scriptTag.textContent);
      const hits = jsonData?.props?.pageProps?.ssrHits;
      
      if (hits && hits.length > 0) {
        // Find the job matching current URL or take the first one
        let hit = hits.find(h => h.apply_url === window.location.href) || hits[0];

        const job = buildHiringCafeJobFromHit(hit);
        const stats = extractHiringCafeStatsFromDom();
        return { ...job, ...stats };
      }
    }
    
    // FALLBACK: DOM scraping if __NEXT_DATA__ fails
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

    if (!titleEl || !descriptionEl) return null;

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
 */
function extractLinkedIn() {
  try {
    const titleEl = document.querySelector('.job-details-jobs-unified-top-card__job-title') ||
                    document.querySelector('h1[class*="job-title"]') ||
                    document.querySelector('[data-testid="job-title"]');

    const companyEl = document.querySelector('.job-details-jobs-unified-top-card__company-name') ||
                      document.querySelector('a[class*="company-name"]') ||
                      document.querySelector('[data-testid="company-name"]');

    const descriptionEl = document.querySelector('.jobs-description-content__text') ||
                          document.querySelector('[class*="description"]') ||
                          document.querySelector('[data-testid="job-description"]');

    if (!titleEl || !descriptionEl) return null;

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
 */
function extractBuiltIn() {
  try {
    const titleEl = document.querySelector('h1[class*="job-title"]') ||
                    document.querySelector('h1') ||
                    document.querySelector('[data-testid="job-title"]');

    const companyEl = document.querySelector('[class*="company"]') ||
                      document.querySelector('a[href*="/companies/"]') ||
                      document.querySelector('[data-testid="company-name"]');

    const descriptionEl = document.querySelector('[class*="description"]') ||
                          document.querySelector('[data-testid="job-description"]') ||
                          document.querySelector('article');

    if (!titleEl || !descriptionEl) return null;

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
 * Extract job data from WellFound
 */
function extractWellFound() {
  try {
    const titleEl = document.querySelector('h1') ||
                    document.querySelector('[class*="job-title"]') ||
                    document.querySelector('[data-testid="job-title"]');

    const companyEl = document.querySelector('[class*="company"]') ||
                      document.querySelector('a[href*="/company/"]') ||
                      document.querySelector('[data-testid="company-name"]');

    const descriptionEl = document.querySelector('[class*="description"]') ||
                          document.querySelector('[data-testid="job-description"]') ||
                          document.querySelector('main');

    if (!titleEl || !descriptionEl) return null;

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
 * Generic job extraction fallback
 */
function extractGeneric() {
  try {
    const titleEl = document.querySelector('h1') ||
                    document.querySelector('[class*="title"]') ||
                    document.querySelector('title');

    const descriptionEl = document.querySelector('[class*="description"]') ||
                          document.querySelector('[class*="content"]') ||
                          document.querySelector('article') ||
                          document.querySelector('main');

    if (!titleEl || !descriptionEl) return null;

    let company = 'Unknown Company';
    const companySelectors = [
      '[class*="company"]', '[class*="employer"]',
      'a[href*="/company"]', '[itemprop="hiringOrganization"]'
    ];
    for (const selector of companySelectors) {
      const el = document.querySelector(selector);
      if (el) { company = el.textContent.trim(); break; }
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
 * Auto-detect platform and extract job data
 */
function extractJobData() {
  const hostname = window.location.hostname.toLowerCase();
  if (hostname.includes('hiring.cafe')) return extractHiringCafe();
  if (hostname.includes('linkedin.com')) return extractLinkedIn();
  if (hostname.includes('builtin.com')) return extractBuiltIn();
  if (hostname.includes('wellfound.com')) return extractWellFound();
  return extractGeneric();
}

/**
 * Wait for job listings to appear in the DOM using polling
 * @param {number} timeout - Maximum time to wait in ms
/**
 * Decode HTML entities and URL-encoded strings
 */
function decodeHtmlEntities(text) {
  if (!text) return '';
  // First decode URL encoding
  let decoded = text;
  try {
    decoded = decodeURIComponent(text);
  } catch (e) {
    // If decodeURIComponent fails, continue with original
  }
  // Replace common HTML entities
  decoded = decoded
    .replace(/&#(\d+);/g, (_, code) => String.fromCharCode(parseInt(code)))
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'");
  // Strip HTML tags
  decoded = decoded.replace(/<[^>]*>/g, ' ');
  return decoded.trim();
}

/**
 * Extract company name from job description text
 */
function extractCompanyFromDescription(description) {
  if (!description) return null;
  
  const decoded = decodeHtmlEntities(description);
  
  // Common patterns where company names appear (fixed regex syntax)
  const patterns = [
    /At\s+([A-Z][A-Za-z0-9\s&.,'-]+?)\s+(?:is\s|we\s|has\s|\.\s|$)/,
    /Join\s+([A-Z][A-Za-z0-9\s&.,'-]+?)\s+(?:Team|team|as\s|\.\s|$)/,
    /([A-Z][A-Za-z0-9\s&.,'-]+?)\s+is\s+(?:a|an|the)\s/,
    /Welcome\s+to\s+([A-Z][A-Za-z0-9\s&.,'-]+?)(?:\s*[.!]|\s*$)/,
    /About\s+([A-Z][A-Za-z0-9\s&.,'-]+?)(?::\s|\s*$)/,
    /([A-Z][A-Za-z0-9\s&.,'-]+?)\s+is\s+(?:seeking|hiring|looking)/,
    /Company:\s*([A-Z][A-Za-z0-9\s&.,'-]+?)(?:\s*[.!]|\s*$)/,
    /([A-Z][A-Za-z0-9\s&.,'-]+?)\s+(?:Inc|LLC|Ltd|Corp|Corporation|Company)\b/,
  ];
  
  for (const pattern of patterns) {
    const match = decoded.match(pattern);
    if (match && match[1]) {
      const name = match[1].trim().replace(/\s+/g, ' ');
      // Filter out common false positives and check length
      if (name.length >= 2 &&
          !['We', 'Our', 'The', 'A', 'An', 'This', 'It', 'You'].includes(name)) {
        return name;
      }
    }
  }

  return null;
}

/**
 * Extract company name from __NEXT_DATA__ hit using multiple fallback strategies
 */
function extractCompanyFromHit(hit) {
  const processed = hit.v5_processed_job_data || {};
  const jobInfo = hit.job_information || {};

  // Strategy 1: processed.company_name (most reliable)
  if (processed.company_name) {
    return processed.company_name;
  }

  // Strategy 2: enriched_company_data.name
  if (hit.enriched_company_data?.name) {
    return hit.enriched_company_data.name;
  }

  // Strategy 3: job_information.company.name
  if (jobInfo.company?.name) {
    return jobInfo.company.name;
  }

  // Strategy 4: hit.company.name
  if (hit.company?.name) {
    return hit.company.name;
  }

  // Strategy 5: hit.company_name
  if (hit.company_name) {
    return hit.company_name;
  }

  // Strategy 6: board_token (convert from "company_name" to "Company Name")
  if (hit.board_token) {
    return hit.board_token
      .split('_')
      .map(w => w.charAt(0).toUpperCase() + w.slice(1))
      .join(' ');
  }

  // Strategy 7: Extract from description
  if (jobInfo.description) {
    const fromDesc = extractCompanyFromDescription(jobInfo.description);
    if (fromDesc) return fromDesc;
  }

  return null;
}

function normalizeHiringCafeList(value) {
  if (value === null || value === undefined) return null;
  if (Array.isArray(value)) {
    const text = value
      .map(item => String(item).trim())
      .filter(Boolean)
      .join(', ');
    return text || null;
  }
  const text = String(value).trim();
  return text || null;
}

function formatHiringCafeCompensation(processed) {
  if (!processed) return null;

  const frequency = (processed.listed_compensation_frequency || '').toLowerCase();
  const bands = [
    { key: 'yearly', min: 'yearly_min_compensation', max: 'yearly_max_compensation', suffix: '/yr' },
    { key: 'monthly', min: 'monthly_min_compensation', max: 'monthly_max_compensation', suffix: '/mo' },
    { key: 'weekly', min: 'weekly_min_compensation', max: 'weekly_max_compensation', suffix: '/wk' },
    { key: 'bi-weekly', min: 'bi-weekly_min_compensation', max: 'bi-weekly_max_compensation', suffix: '/2wk' },
    { key: 'daily', min: 'daily_min_compensation', max: 'daily_max_compensation', suffix: '/day' },
    { key: 'hourly', min: 'hourly_min_compensation', max: 'hourly_max_compensation', suffix: '/hr' },
  ];

  let band = bands.find(entry => frequency && frequency.startsWith(entry.key));
  if (!band) {
    band = bands.find(entry =>
      processed[entry.min] !== undefined || processed[entry.max] !== undefined
    );
  }
  if (!band) return null;

  const min = processed[band.min];
  const max = processed[band.max];
  if (min === undefined && max === undefined) return null;

  const currency = processed.listed_compensation_currency || 'USD';
  let formatter;
  try {
    formatter = new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: currency,
      maximumFractionDigits: 0,
    });
  } catch (e) {
    formatter = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });
  }

  const minText = min !== undefined ? formatter.format(min) : null;
  const maxText = max !== undefined ? formatter.format(max) : null;
  if (minText && maxText) return `${minText}-${maxText}${band.suffix}`;
  if (minText) return `${minText}${band.suffix}`;
  if (maxText) return `${maxText}${band.suffix}`;
  return null;
}

function extractHiringCafeStat(label) {
  const normalized = label.toLowerCase();
  const spans = Array.from(document.querySelectorAll('span'));
  for (const span of spans) {
    if (span.textContent.trim().toLowerCase() === normalized) {
      const previous = span.previousElementSibling;
      if (!previous) return null;
      const digits = previous.textContent.replace(/[^0-9]/g, '');
      if (!digits) return null;
      const value = parseInt(digits, 10);
      return Number.isNaN(value) ? null : value;
    }
  }
  return null;
}

function extractHiringCafeStatsFromDom() {
  return {
    views: extractHiringCafeStat('views'),
    saves: extractHiringCafeStat('saves'),
    applications: extractHiringCafeStat('applications'),
  };
}

function buildHiringCafeJobFromHit(hit) {
  const processed = hit.v5_processed_job_data || {};
  const jobInfo = hit.job_information || {};

  // Use improved company extraction with multiple fallback strategies
  const company = extractCompanyFromHit(hit) || 'Unknown Company';

  const jobId = hit.id || hit.job_id || hit.uuid || hit._id ||
                hit.jobId || hit.jobID || hit.external_id || null;
  const location =
    processed.formatted_workplace_location ||
    normalizeHiringCafeList(processed.workplace_cities) ||
    normalizeHiringCafeList(processed.workplace_states) ||
    jobInfo.location ||
    null;

  return {
    platform: 'HiringCafe',
    id: jobId ? `hiringcafe-${jobId}` : null,
    title: jobInfo.title || hit.job_title_raw || 'Unknown Title',
    company: company,
    url: hit.apply_url || window.location.href,
    description: decodeHtmlEntities(jobInfo.description || '').substring(0, 2000),
    summary: processed.job_summary || processed.summary || jobInfo.summary || null,
    requirements: processed.requirements_summary || jobInfo.requirements || null,
    location: location,
    county: normalizeHiringCafeList(processed.workplace_counties),
    compensation: formatHiringCafeCompensation(processed) || jobInfo.salary || null,
    workplace_type: processed.workplace_type || null,
    employment_type: normalizeHiringCafeList(processed.commitment) || jobInfo.employment_type || null,
    department: jobInfo.department || processed.job_category || null,
    team: jobInfo.team || null,
    // Extract engagement stats from DOM (views, saves, applications)
    ...extractHiringCafeStatsFromDom(),
    posted_at: processed.estimated_publish_date || jobInfo.posted_at || null,
    posted_ago: jobInfo.posted_ago || null,
  };
}

/**
 * Extract jobs from Next.js __NEXT_DATA__ script tag (HiringCafe)
 * This is the most reliable method - zero DOM flakiness
 * Always reads fresh from DOM to handle SPA navigation
 */
function extractJobsFromNextData() {
  try {
    // Always get fresh reference to script tag (don't cache)
    const scriptTag = document.getElementById('__NEXT_DATA__');
    if (!scriptTag) {
      console.log('JobPipe: No __NEXT_DATA__ script tag found');
      return [];
    }

    // Force re-read textContent (important for SPA updates)
    const scriptContent = scriptTag.textContent;
    if (!scriptContent) {
      console.log('JobPipe: __NEXT_DATA__ is empty');
      return [];
    }

    const jsonData = JSON.parse(scriptContent);
    const hits = jsonData?.props?.pageProps?.ssrHits;

    if (!hits || !Array.isArray(hits) || hits.length === 0) {
      console.log('JobPipe: No job hits found in __NEXT_DATA__');
      return [];
    }

    console.log(`JobPipe: Found ${hits.length} job hits in __NEXT_DATA__`);
    
    // Debug: Log the first hit's keys to see what fields are available
    if (hits.length > 0) {
      console.log('JobPipe: Sample hit keys:', Object.keys(hits[0]));
      console.log('JobPipe: Sample hit ID fields:', {
        id: hits[0].id,
        job_id: hits[0].job_id,
        uuid: hits[0].uuid,
        _id: hits[0]._id,
        apply_url: hits[0].apply_url,
      });
    }

    const jobs = hits.map((hit, index) => {
      const job = buildHiringCafeJobFromHit(hit);
      if (index < 3) {
        console.log(`JobPipe: Job ${index} - ID:`, job.id || 'NO-ID', '| URL:', job.url);
      }
      return job;
    });

    // Log sample jobs for debugging
    if (jobs.length > 0) {
      console.log('JobPipe: Sample jobs from __NEXT_DATA__:', jobs.slice(0, 3).map(j => ({
        id: j.id || 'NO-ID',
        title: j.title,
        url: j.url
      })));
    }

    return jobs;
  } catch (e) {
    console.error('JobPipe: Error parsing __NEXT_DATA__:', e);
    return [];
  }
}

/**
 * Extract HiringCafe jobs from the live DOM.
 * This is preferred for SPA navigation because it reflects the current page state.
 */
function extractHiringCafeJobsFromDom() {
  const jobs = [];
  const jobCards = Array.from(
    document.querySelectorAll('main article, main li, main [data-job-id], [class*="job-card"]')
  );

  const uniqueUrls = new Set();
  jobCards.forEach(card => {
    try {
      const rect = card.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) {
        return;
      }

      const link = card.querySelector('a[href*="hiring.cafe"], a[href*="/job/"]');
      if (!link) return;

      const url = link.href;
      if (uniqueUrls.has(url)) return;
      uniqueUrls.add(url);

      const titleEl = card.querySelector('h1, h2, h3, [class*="title"]') || link;
      const companyEl = card.querySelector('[class*="company"], [class*="Company"], [data-company]');
      const title = titleEl.textContent.trim() || link.textContent.trim() || link.getAttribute('aria-label') || 'Unknown Title';
      const company = companyEl?.textContent.trim() || 'Unknown Company';

      jobs.push({
        platform: 'HiringCafe',
        title: title.substring(0, 200),
        company: company,
        url: url,
        description: '',
      });
    } catch (e) {
      console.error('Error extracting job from link:', e);
    }
  });

  return jobs;
}

/**
 * Extract multiple job listings from search results page
 * Always extracts fresh data to handle SPA navigation
 */
async function extractBatchJobs() {
  const hostname = window.location.hostname.toLowerCase();
  const jobs = [];

  if (hostname.includes('hiring.cafe')) {
    console.log('JobPipe: Extracting jobs from HiringCafe...');

    const nextDataJobs = extractJobsFromNextData();
    const domJobs = extractHiringCafeJobsFromDom();

    const mergedJobs = [];
    const seenKeys = new Set();

    for (const job of [...nextDataJobs, ...domJobs]) {
      const key = job.id || job.url;
      if (!key || seenKeys.has(key)) {
        continue;
      }
      seenKeys.add(key);
      mergedJobs.push(job);
    }

    console.log(
      `JobPipe: HiringCafe merge | __NEXT_DATA__=${nextDataJobs.length} DOM=${domJobs.length} merged=${mergedJobs.length}`
    );

    if (mergedJobs.length === 0) {
      console.log('JobPipe: No HiringCafe jobs found in DOM or __NEXT_DATA__');
      return [];
    }

    // Respect a user-configurable batch limit (stored in chrome.storage.local)
    // Default to 1000 to avoid accidental huge batches but allow full captures.
    const limit = await new Promise((resolve) => {
      try {
        chrome.storage.local.get(['batchCaptureLimit'], (res) => {
          resolve(res && res.batchCaptureLimit ? res.batchCaptureLimit : 1000);
        });
      } catch (e) {
        resolve(1000);
      }
    });

    const limitedJobs = mergedJobs.slice(0, limit);
    console.log(`JobPipe: Limiting to ${limitedJobs.length} jobs (limit=${limit})`);
    return limitedJobs;
  } else if (hostname.includes('linkedin.com')) {
    const jobCards = document.querySelectorAll('[data-testid="job-card"]');
    jobCards.forEach(card => {
      try {
        const titleEl = card.querySelector('[data-testid="job-title"]');
        const companyEl = card.querySelector('[data-testid="company-name"]');
        const linkEl = card.querySelector('a[href]');
        // Extract LinkedIn job ID from data attribute or URL
        const jobId = card.getAttribute('data-job-id') || 
                     card.getAttribute('data-entity-urn') ||
                     (linkEl ? linkEl.href.match(/jobs\/view\/(\d+)/)?.[1] : null);
        if (titleEl && linkEl) {
          jobs.push({
            platform: 'LinkedIn',
            id: jobId ? `linkedin-${jobId}` : null,
            title: titleEl.textContent.trim(),
            company: companyEl ? companyEl.textContent.trim() : 'Unknown Company',
            url: linkEl.href,
            description: '',
          });
        }
      } catch (e) { console.error('Error extracting LinkedIn job card:', e); }
    });
  }

  console.log(`JobPipe: Found ${jobs.length} job listings`);
  return jobs;
}

// ==================== MESSAGE LISTENER ====================

// Listen for messages from popup or background script
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'PING') {
    sendResponse({ success: true, message: 'Content script is ready' });
    return false; // Synchronous response
  }

  if (request.action === 'CAPTURE_JOB') {
    handleCaptureJob(request, sendResponse);
    return true; // Keep message channel open for async response
  }

  if (request.action === 'CAPTURE_BATCH') {
    handleCaptureBatch(request, sendResponse);
    return true;
  }

  if (request.action === 'SET_AUTO_SCRAPE') {
    autoScrapeEnabled = request.enabled;
    console.log('JobPipe: Auto-scrape set to', autoScrapeEnabled);
    if (autoScrapeEnabled) {
      // Trigger auto-scrape on enable if on a supported site
      attemptAutoScrape();
    }
    sendResponse({ success: true });
    return false;
  }
});

// Auto-scrape state
let autoScrapeEnabled = true; // Enabled by default
let autoScrapeAttempted = false;
let lastUrl = window.location.href;
let overlayElement = null;
let overlayVisible = true;

// Check if auto-scrape is enabled on page load
chrome.storage.local.get(['autoScrapeEnabled'], (result) => {
  // Default to true if not set
  autoScrapeEnabled = result.autoScrapeEnabled !== undefined ? result.autoScrapeEnabled : true;
  console.log('JobPipe: Auto-scrape enabled:', autoScrapeEnabled);
  
  // Create overlay UI
  createOverlay();
  
  if (autoScrapeEnabled && !autoScrapeAttempted) {
    attemptAutoScrape();
  }
});

// Detect SPA navigation (URL changes without page reload)
setInterval(() => {
  const currentUrl = window.location.href;
  if (currentUrl !== lastUrl) {
    console.log('JobPipe: URL changed from', lastUrl, 'to', currentUrl);
    lastUrl = currentUrl;
    autoScrapeAttempted = false; // Reset so new page can be scraped
    if (autoScrapeEnabled) {
      setTimeout(() => attemptAutoScrape(), 1500); // Wait for page to load
    }
  }
}, 1000);

// Also listen for popstate (browser back/forward)
window.addEventListener('popstate', () => {
  console.log('JobPipe: Popstate detected');
  autoScrapeAttempted = false;
  if (autoScrapeEnabled) {
    setTimeout(() => attemptAutoScrape(), 1500);
  }
});

// Listen for pushstate/replacestate (programmatic navigation)
const originalPushState = history.pushState;
const originalReplaceState = history.replaceState;
history.pushState = function() {
  originalPushState.apply(this, arguments);
  console.log('JobPipe: Pushstate detected');
  autoScrapeAttempted = false;
  if (autoScrapeEnabled) {
    setTimeout(() => attemptAutoScrape(), 1500);
  }
};
history.replaceState = function() {
  originalReplaceState.apply(this, arguments);
  console.log('JobPipe: Replacestate detected');
  autoScrapeAttempted = false;
  if (autoScrapeEnabled) {
    setTimeout(() => attemptAutoScrape(), 1500);
  }
};

// Notify background script that content script is ready
console.log('JobPipe content script loaded on:', window.location.href);

/**
 * Create and inject the overlay UI on the page
 */
function createOverlay() {
  // Only create overlay on supported sites
  const hostname = window.location.hostname.toLowerCase();
  const isSupported = hostname.includes('hiring.cafe') ||
                      hostname.includes('linkedin.com') ||
                      hostname.includes('builtin.com') ||
                      hostname.includes('wellfound.com');
  
  if (!isSupported) return;
  
  // Check if overlay already exists
  if (document.getElementById('jobpipe-overlay')) return;
  
  const overlay = document.createElement('div');
  overlay.id = 'jobpipe-overlay';
  overlay.innerHTML = `
    <div class="jobpipe-overlay-header" id="jobpipe-overlay-header">
      <span class="jobpipe-overlay-title">📎 JobPipe</span>
      <div class="jobpipe-overlay-controls">
        <span class="jobpipe-status-dot" id="jobpipe-status-dot"></span>
        <button class="jobpipe-overlay-toggle" id="jobpipe-overlay-toggle">−</button>
      </div>
    </div>
    <div class="jobpipe-overlay-body" id="jobpipe-overlay-body">
      <div class="jobpipe-overlay-status" id="jobpipe-overlay-status">Ready</div>
      <div class="jobpipe-overlay-stats">
        <span id="jobpipe-jobs-found">Found: 0</span>
        <span id="jobpipe-jobs-sent">Sent: 0</span>
      </div>
      <div class="jobpipe-overlay-auto">
        <label>
          <input type="checkbox" id="jobpipe-auto-toggle" ${autoScrapeEnabled ? 'checked' : ''}>
          Auto-scrape
        </label>
      </div>
    </div>
  `;
  
  // Add styles
  const style = document.createElement('style');
  style.textContent = `
    #jobpipe-overlay {
      position: fixed;
      top: 10px;
      right: 10px;
      width: 220px;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: white;
      border-radius: 8px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.3);
      z-index: 99999;
      font-family: 'Segoe UI', Tahoma, sans-serif;
      font-size: 12px;
      transition: all 0.3s ease;
    }
    #jobpipe-overlay-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 8px 12px;
      border-bottom: 1px solid rgba(255,255,255,0.2);
      cursor: move;
    }
    .jobpipe-overlay-title {
      font-weight: 600;
      font-size: 13px;
    }
    .jobpipe-overlay-controls {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .jobpipe-status-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: #4ade80;
      display: inline-block;
    }
    .jobpipe-status-dot.scraping {
      background: #fbbf24;
      animation: pulse 1s infinite;
    }
    .jobpipe-status-dot.error {
      background: #f87171;
    }
    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.5; }
    }
    .jobpipe-overlay-toggle {
      background: none;
      border: none;
      color: white;
      font-size: 18px;
      cursor: pointer;
      padding: 0;
      width: 20px;
      height: 20px;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .jobpipe-overlay-body {
      padding: 10px 12px;
    }
    .jobpipe-overlay-body.collapsed {
      display: none;
    }
    .jobpipe-overlay-status {
      font-weight: 600;
      margin-bottom: 8px;
    }
    .jobpipe-overlay-stats {
      display: flex;
      justify-content: space-between;
      margin-bottom: 8px;
      font-size: 11px;
      opacity: 0.9;
    }
    .jobpipe-overlay-auto label {
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 11px;
      cursor: pointer;
    }
    .jobpipe-overlay-auto input[type="checkbox"] {
      cursor: pointer;
    }
  `;
  
  document.head.appendChild(style);
  document.body.appendChild(overlay);
  overlayElement = overlay;
  
  // Make overlay draggable
  makeDraggable(overlay, document.getElementById('jobpipe-overlay-header'));
  
  // Toggle collapse/expand
  document.getElementById('jobpipe-overlay-toggle').addEventListener('click', () => {
    const body = document.getElementById('jobpipe-overlay-body');
    const toggle = document.getElementById('jobpipe-overlay-toggle');
    body.classList.toggle('collapsed');
    toggle.textContent = body.classList.contains('collapsed') ? '+' : '−';
  });
  
  // Auto-scrape toggle in overlay
  document.getElementById('jobpipe-auto-toggle').addEventListener('change', (e) => {
    autoScrapeEnabled = e.target.checked;
    chrome.storage.local.set({ autoScrapeEnabled: autoScrapeEnabled });
    
    // Notify background
    chrome.runtime.sendMessage({
      action: 'SET_AUTO_SCRAPE',
      enabled: autoScrapeEnabled
    });
    
    if (autoScrapeEnabled && !autoScrapeAttempted) {
      attemptAutoScrape();
    }
  });
  
  console.log('JobPipe: Overlay created');
}

/**
 * Make an element draggable
 */
function makeDraggable(element, handle) {
  let isDragging = false;
  let currentX;
  let currentY;
  let initialX;
  let initialY;
  
  handle.addEventListener('mousedown', (e) => {
    if (e.target.tagName === 'BUTTON' || e.target.tagName === 'INPUT') return;
    isDragging = true;
    initialX = e.clientX - element.offsetLeft;
    initialY = e.clientY - element.offsetTop;
  });
  
  document.addEventListener('mousemove', (e) => {
    if (!isDragging) return;
    e.preventDefault();
    currentX = e.clientX - initialX;
    currentY = e.clientY - initialY;
    element.style.right = 'auto';
    element.style.left = currentX + 'px';
    element.style.top = currentY + 'px';
  });
  
  document.addEventListener('mouseup', () => {
    isDragging = false;
  });
}

/**
 * Update overlay status
 */
function updateOverlayStatus(status, jobsFound = 0, jobsSent = 0) {
  const statusEl = document.getElementById('jobpipe-overlay-status');
  const dotEl = document.getElementById('jobpipe-status-dot');
  const foundEl = document.getElementById('jobpipe-jobs-found');
  const sentEl = document.getElementById('jobpipe-jobs-sent');
  
  if (!statusEl) return;
  
  statusEl.textContent = status;
  foundEl.textContent = `Found: ${jobsFound}`;
  sentEl.textContent = `Sent: ${jobsSent}`;
  
  // Update status dot
  dotEl.className = 'jobpipe-status-dot';
  if (status === 'Scraping...') {
    dotEl.classList.add('scraping');
  } else if (status.includes('Error') || status.includes('✗')) {
    dotEl.classList.add('error');
  }
}

async function attemptAutoScrape() {
  if (autoScrapeAttempted) return;
  autoScrapeAttempted = true;

  const hostname = window.location.hostname.toLowerCase();
  const isSupported = hostname.includes('hiring.cafe') ||
                      hostname.includes('linkedin.com') ||
                      hostname.includes('builtin.com') ||
                      hostname.includes('wellfound.com');

  if (!isSupported) return;

  console.log('JobPipe: Attempting auto-scrape...');

  // Notify popup and update overlay of scraping start
  updateOverlayStatus('Scraping...', 0, 0);
  
  chrome.runtime.sendMessage({
    action: 'SCRAPE_STATUS_UPDATE',
    status: 'Scraping...',
    jobsFound: 0,
    jobsSent: 0
  });

  try {
    // Wait for page to fully load
    await new Promise(resolve => setTimeout(resolve, 2000));

    const jobs = await extractBatchJobs();

    if (!jobs || jobs.length === 0) {
      console.log('JobPipe: No jobs found to auto-scrape');
      updateOverlayStatus('No jobs found', 0, 0);
      chrome.runtime.sendMessage({
        action: 'SCRAPE_STATUS_UPDATE',
        status: 'No jobs found',
        jobsFound: 0,
        jobsSent: 0
      });
      return;
    }

    console.log(`JobPipe: Auto-scraped ${jobs.length} jobs, sending to server...`);
    updateOverlayStatus('Sending...', jobs.length, 0);

    // Notify jobs found
    chrome.runtime.sendMessage({
      action: 'SCRAPE_STATUS_UPDATE',
      status: 'Sending...',
      jobsFound: jobs.length,
      jobsSent: 0
    });

    // Get server URL
    const result = await chrome.storage.local.get(['serverUrl']);
    const serverUrl = result.serverUrl || '127.0.0.1:3838';
    const fullServerUrl = serverUrl.startsWith('http://') ? serverUrl : `http://${serverUrl}`;

    // Send to server via background script
    const response = await chrome.runtime.sendMessage({
      action: 'SEND_BATCH_TO_SERVER',
      jobs: jobs,
      serverUrl: fullServerUrl
    });

    if (response && response.success) {
      const sentCount = response.count || jobs.length;
      updateOverlayStatus('Success ✓', jobs.length, sentCount);
      chrome.runtime.sendMessage({
        action: 'SCRAPE_STATUS_UPDATE',
        status: 'Success ✓',
        jobsFound: jobs.length,
        jobsSent: sentCount
      });
    } else {
      updateOverlayStatus('Error ✗', jobs.length, 0);
      chrome.runtime.sendMessage({
        action: 'SCRAPE_STATUS_UPDATE',
        status: 'Error ✗',
        jobsFound: jobs.length,
        jobsSent: 0
      });
    }
  } catch (error) {
    console.error('JobPipe: Auto-scrape error:', error);
    updateOverlayStatus('Error ✗', 0, 0);
    chrome.runtime.sendMessage({
      action: 'SCRAPE_STATUS_UPDATE',
      status: 'Error ✗',
      jobsFound: 0,
      jobsSent: 0
    });
  }
}

/**
 * Handle single job capture
 */
async function handleCaptureJob(request, sendResponse) {
  try {
    const jobData = extractJobData();

    if (!jobData) {
      sendResponse({
        success: false,
        error: 'Could not extract job data from this page. Make sure you are on a job listing page.',
      });
      return;
    }

    // Send to server via background script
    const result = await chrome.runtime.sendMessage({
      action: 'SEND_TO_SERVER',
      jobData: jobData,
      serverUrl: request.serverUrl,
    });

    sendResponse(result);
  } catch (error) {
    console.error('Error capturing job:', error);
    sendResponse({
      success: false,
      error: error.message,
    });
  }
}

/**
 * Handle batch job capture
 */
async function handleCaptureBatch(request, sendResponse) {
  try {
    console.log('JobPipe content: handleCaptureBatch called, serverUrl=', request.serverUrl);

    // Reset auto-scrape flag to allow re-scraping (for manual capture or new searches)
    autoScrapeAttempted = false;

    // Force fresh extraction by clearing any cached data
    const jobs = await extractBatchJobs();
    console.log('JobPipe content: extractBatchJobs returned', jobs.length, 'jobs');

    if (jobs.length === 0) {
      sendResponse({
        success: false,
        error: 'No job listings found on this page. Make sure you are on a search results page. Check browser console (F12) for debug info.',
      });
      return;
    }

    // Send batch to server
    const result = await chrome.runtime.sendMessage({
      action: 'SEND_BATCH_TO_SERVER',
      jobs: jobs,
      serverUrl: request.serverUrl,
    });

    console.log('JobPipe content: sendMessage result:', result);
    sendResponse(result);
  } catch (error) {
    console.error('Error capturing batch:', error);
    sendResponse({
      success: false,
      error: error.message,
    });
  }
}

// Notify background script that content script is ready
chrome.runtime.sendMessage({ action: 'CONTENT_SCRIPT_READY' });

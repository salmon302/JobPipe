// Purpose: Content script for extracting job data from supported job boards.
// Author: Seth Nenninger (Tencent: Hy3 preview Agent)
// Timestamp: 2026-05-12T18:55:00Z

// ==================== HELPER FUNCTIONS ====================

/**
 * Safely send a message to the extension background script.
 * Handles "Extension context invalidated" errors gracefully.
 * @param {Object} message - The message to send
 * @param {Function} [callback] - Optional callback for response
 * @returns {Promise|undefined} - Returns a promise if no callback, or undefined
 */
function safeSendMessage(message, callback) {
  try {
    if (chrome.runtime?.id) {
      if (callback) {
        chrome.runtime.sendMessage(message, callback);
      } else {
        return chrome.runtime.sendMessage(message).catch((error) => {
          if (error.message?.includes('Extension context invalidated')) {
            console.warn('JobPipe: Extension context invalidated:', error.message);
          } else {
            console.error('JobPipe: Error sending message:', error);
          }
          return Promise.resolve(undefined);
        });
      }
    } else {
      console.warn('JobPipe: Extension context invalidated, cannot send message:', message.action);
      if (callback) callback(undefined);
      return Promise.resolve(undefined);
    }
  } catch (error) {
    if (error.message?.includes('Extension context invalidated')) {
      console.warn('JobPipe: Extension context invalidated:', error.message);
    } else {
      console.error('JobPipe: Error sending message:', error);
    }
    if (callback) callback(undefined);
    return Promise.resolve(undefined);
  }
}

// ==================== EXCLUDED HOSTNAMES (Not Job Board) ====================

/**
 * Get the set of excluded hostnames from storage
 * @returns {Promise<Set>} Set of excluded hostnames
 */
async function getExcludedHosts() {
  return new Promise((resolve) => {
    chrome.storage.local.get(['excludedHosts'], (result) => {
      const hosts = result.excludedHosts || [];
      resolve(new Set(hosts));
    });
  });
}

/**
 * Check if current hostname is excluded
 * @returns {Promise<boolean>} True if excluded
 */
async function isCurrentSiteExcluded() {
  const hostname = window.location.hostname.toLowerCase();
  const excludedHosts = await getExcludedHosts();
  return excludedHosts.has(hostname);
}

/**
 * Add current hostname to excluded list
 * @returns {Promise<void>}
 */
async function excludeCurrentSite() {
  const hostname = window.location.hostname.toLowerCase();
  return new Promise((resolve) => {
    chrome.storage.local.get(['excludedHosts'], (result) => {
      const hosts = result.excludedHosts || [];
      if (!hosts.includes(hostname)) {
        hosts.push(hostname);
        chrome.storage.local.set({ excludedHosts: hosts }, resolve);
      } else {
        resolve();
      }
    });
  });
}

/**
 * Remove current hostname from excluded list
 * @returns {Promise<void>}
 */
async function includeCurrentSite() {
  const hostname = window.location.hostname.toLowerCase();
  return new Promise((resolve) => {
    chrome.storage.local.get(['excludedHosts'], (result) => {
      const hosts = (result.excludedHosts || []).filter(h => h !== hostname);
      chrome.storage.local.set({ excludedHosts: hosts }, resolve);
    });
  });
}

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
 * Extract job data from UKG/UltiPro platform (rec.pro.ukg.net)
 * Used by many enterprise companies for their career portals.
 */
function extractUKG() {
  try {
    // UKG/UltiPro detail page: OpportunityDetail?opportunityId=...
    // Title is typically in an h1 or h2 with the job title
    const titleEl = document.querySelector('h1') ||
                    document.querySelector('h2') ||
                    document.querySelector('[class*="title"]') ||
                    document.querySelector('[class*="job-title"]') ||
                    document.querySelector('title');
    
    if (!titleEl) return null;
    
    let title = titleEl.textContent.trim();
    // Clean up title (remove site name after | or -)
    title = title.replace(/\s*[-|]\s*[^-|]+$/, '').trim();
    if (!title || title.length < 2) return null;
    
    // Company: look for organization name in the page
    let company = 'Unknown Company';
    
    // Strategy 1: Look for company name in breadcrumbs or header
    const companyCandidates = [
      // Breadcrumb links (common in UKG portals)
      document.querySelector('nav[aria-label="Breadcrumb"] a:last-child'),
      document.querySelector('[class*="breadcrumb"] a:last-child'),
      document.querySelector('[class*="breadcrumb"] [class*="active"]'),
      document.querySelector('[class*="organization"]'),
      document.querySelector('[class*="company-name"]'),
      document.querySelector('[class*="employer"]'),
      // Meta tags
      document.querySelector('meta[property="og:site_name"]'),
      document.querySelector('meta[name="application-name"]'),
    ];
    for (const el of companyCandidates) {
      if (el) {
        const text = el.getAttribute('content') || el.textContent.trim();
        if (text && text.length > 1 && text.length < 100 &&
            !text.toLowerCase().includes('sign in') &&
            !text.toLowerCase().includes('login') &&
            !text.toLowerCase().includes('register')) {
          company = text;
          break;
        }
      }
    }
    
    // Strategy 2: Extract from URL hostname
    if (company === 'Unknown Company') {
      // URL pattern: COM1506COMNI.rec.pro.ukg.net or similar
      const hostname = window.location.hostname;
      // Try to extract company code from subdomain
      const subdomainMatch = hostname.match(/^([^.]+)\.rec\.pro\.ukg\.net/);
      if (subdomainMatch) {
        const code = subdomainMatch[1];
        // Remove common suffixes like COMNI, COM, etc.
        const cleaned = code.replace(/COMNI|COM|CORP|INC|LLC$/i, '');
        if (cleaned && cleaned.length > 2) {
          company = cleaned;
        } else {
          company = code;
        }
      }
    }
    
    // Description: main content area
    let description = '';
    const descSelectors = [
      '[class*="description"]',
      '[class*="content"]',
      '[class*="detail"]',
      '[class*="body"]',
      'article',
      'main',
      '[role="main"]',
    ];
    for (const sel of descSelectors) {
      const el = document.querySelector(sel);
      if (el && el.textContent.trim().length > 100) {
        description = el.textContent.trim();
        break;
      }
    }
    
    // Fallback: all body text
    if (!description || description.length < 100) {
      description = document.body?.textContent?.trim() || '';
    }
    
    console.log(`JobPipe: UKG extracted - Title="${title}" Company="${company}" Desc=${description.length}chars`);
    
    return {
      platform: 'UKG',
      title: title,
      company: company,
      url: window.location.href,
      description: description,
    };
  } catch (error) {
    console.error('Error extracting UKG job:', error);
    return null;
  }
}

/**
 * Generic job extraction fallback - improved with multiple strategies
 * Attempts to extract job data from any job page, even without specialized extractor.
 * Also creates automated dev notes for unknown platforms for further investigation.
 */
function extractGeneric() {
  try {
    // Try multiple strategies to find the job title
    let title = null;
    let company = 'Unknown Company';
    let description = '';

    // === TITLE EXTRACTION ===
    
    // Strategy 1: Look for job title in common DOM patterns
    const titleSelectors = [
      'h1[class*="title"]',
      'h1[class*="job"]',
      '.job-title',
      '.posting-title',
      '[data-testid="job-title"]',
      'h1',
      '.title',
      '[class*="header"] h1',
      'header h1',
      '[class*="position"]',
      '[class*="role"]',
    ];

    for (const selector of titleSelectors) {
      const el = document.querySelector(selector);
      if (el) {
        const text = el.textContent.trim();
        // Filter out common false positives
        if (text && 
            !text.toLowerCase().includes('share') &&
            !text.toLowerCase().includes('login') &&
            !text.toLowerCase().includes('sign in') &&
            text.length > 3 && 
            text.length < 300) {
          title = text;
          break;
        }
      }
    }

    // Strategy 2: Look in the page title (document.title)
    if (!title && document.title) {
      // Remove site name from title (common pattern: "Job Title | Company | Site")
      const titleParts = document.title.split(/[|\-–—]/);
      if (titleParts.length > 0) {
        const candidate = titleParts[0].trim();
        if (candidate.length > 3 && candidate.length < 300) {
          title = candidate;
        }
      }
    }

    // Strategy 3: Look for common job title patterns in the page
    if (!title) {
      const pageText = document.body?.textContent || '';
      // Look for text that looks like a job title (capitalized words, reasonable length)
      const titleMatch = pageText.match(/\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,5})\s*(?:-|–|—|\|)/);
      if (titleMatch) {
        title = titleMatch[1].trim();
      }
    }

    // Strategy 4: Look for text near "Apply" or "Apply Now" buttons
    if (!title) {
      const applyButtons = document.querySelectorAll('a, button');
      for (const btn of applyButtons) {
        const btnText = btn.textContent.toLowerCase();
        if (btnText.includes('apply') && btnText.length < 50) {
          // Look for nearby heading
          const parent = btn.closest('section, article, div[class]');
          const heading = parent?.querySelector('h1, h2, h3');
          if (heading) {
            title = heading.textContent.trim();
            break;
          }
        }
      }
    }

    // === COMPANY EXTRACTION ===
    
    // Strategy 1: Look for company name — EXCLUDE nav/header/breadcrumb elements
    const companySelectors = [
      '[itemprop="hiringOrganization"]',
      '[itemprop="name"]',
      '[data-testid="company-name"]',
      '[class*="company-name"]:not(nav *)',
      '[class*="company"]:not(nav *):not(header *):not([class*="breadcrumb"]):not([class*="nav"])',
      '[class*="employer"]:not(nav *):not(header *)',
      'a[href*="/company"]:not(nav *)',
      '[class*="organization"]',
      'meta[property="og:site_name"]',
    ];
    
    for (const selector of companySelectors) {
      const el = document.querySelector(selector);
      if (el) { 
        const text = el.getAttribute('content') || el.textContent.trim();
        if (text && text.length > 1 && text.length < 100 &&
            !text.toLowerCase().includes('sign in') &&
            !text.toLowerCase().includes('login') &&
            !text.toLowerCase().includes('register')) {
          company = text;
          break; 
        }
      }
    }

    // Strategy 2: Look in page title for company (after the job title)
    if (company === 'Unknown Company' && document.title) {
      const titleParts = document.title.split(/[|\-–—]/);
      if (titleParts.length > 1) {
        // Company is often the second part
        const candidate = titleParts[1].trim();
        if (candidate.length > 1 && candidate.length < 100) {
          company = candidate;
        }
      }
    }

    // Strategy 3: Extract company from URL
    if (company === 'Unknown Company') {
      const hostname = window.location.hostname;
      // Try to extract from hostname like "discovery-senior-living.oasisrecruit.com"
      const match = hostname.match(/^([^.]+)\.(.+)$/);
      if (match) {
        const firstPart = match[1];
        // Convert "discovery-senior-living" to "Discovery Senior Living"
        company = firstPart
          .split(/[-_]/)
          .map(word => word.charAt(0).toUpperCase() + word.slice(1))
          .join(' ');
      }
    }

    // Strategy 4: Extract company from description text
    if (company === 'Unknown Company') {
      const pageText = document.body?.textContent || '';
      const companyFromDesc = extractCompanyFromDescription(pageText);
      if (companyFromDesc) {
        company = companyFromDesc;
      }
    }

    // === DESCRIPTION EXTRACTION ===
    
    // Try multiple selectors for description
    const descriptionSelectors = [
      '[class*="description"]',
      '[class*="content"]',
      '[class*="detail"]',
      '[class*="body"]',
      'article',
      'main',
      '[role="main"]',
      '[class*="posting"]',
      '[class*="job-detail"]',
      '[class*="job-content"]',
    ];
    
    let descriptionEl = null;
    for (const sel of descriptionSelectors) {
      const el = document.querySelector(sel);
      if (el && el.textContent.trim().length > 100) {
        descriptionEl = el;
        break;
      }
    }
    
    // Fallback: use body text if no description found
    if (!descriptionEl) {
      description = document.body?.textContent?.trim() || '';
    } else {
      description = descriptionEl.textContent.trim();
    }

    if (!title || description.length < 100) {
      console.log('JobPipe: Generic extraction failed - title:', title, 'descLength:', description.length);
      
      // Create automated dev note for unknown platform
      createAutomatedDevNote(title, company, description.length);
      
      return null;
    }

    // Create automated dev note for investigation (even on success)
    createAutomatedDevNote(title, company, description.length);

    return {
      platform: 'Generic',
      title: title,
      company: company,
      url: window.location.href,
      description: description,
    };
  } catch (error) {
    console.error('Error in generic extraction:', error);
    return null;
  }
}

/**
 * Create automated dev note for unknown platforms
 * Saves investigation notes to SNDEV/docs/ for later analysis
 */
function createAutomatedDevNote(title, company, descLength) {
  try {
    const hostname = window.location.hostname;
    const pathname = window.location.pathname;
    const url = window.location.href;
    
    // Only create note if we have basic info
    if (!title || title === 'Unknown Title') return;
    
    const noteContent = `Title: Auto-generated Dev Note - ${hostname}
Date: ${new Date().toISOString()}
Author: JobPipe Auto-Scraper (Tencent: Hy3 preview Agent)
Contribution Type: Implementation
Ticket/Context: Automated detection of unknown platform
Summary: Generic extractor used on ${hostname} - needs investigation for specialized extractor.

## Platform Details
- **Hostname**: ${hostname}
- **Path**: ${pathname}
- **Full URL**: ${url}

## Extracted Data
- **Title**: ${title}
- **Company**: ${company}
- **Description Length**: ${descLength} characters

## Investigation Needed
- [ ] Analyze page structure (F12 -> Elements)
- [ ] Identify unique CSS selectors for title, company, description
- [ ] Create specialized extractor function
- [ ] Add platform detection to extractJobData()
- [ ] Test with sample job URL

## Page Structure Notes
<!-- Add notes about unique DOM structure here after investigation -->
`;

    console.log('JobPipe: Auto-dev-note created for', hostname);
    console.log('JobPipe: Dev note content (copy to SNDEV/docs/):', noteContent);
    
    // Send to background script to save (if possible)
    safeSendMessage({
      action: 'CREATE_DEV_NOTE',
      hostname: hostname,
      content: noteContent,
    }).catch(() => {
      // Background may not be ready, just log to console
      console.log('JobPipe: Could not send dev note to background');
    });
  } catch (error) {
    console.error('Error creating automated dev note:', error);
  }
}

/**
 * Extract job data from Greenhouse job boards (e.g., job-boards.greenhouse.io/companyname/jobs/ID)
 */
function extractGreenhouseBoard() {
  try {
    // Extract company from URL path: /companyname/jobs/ID
    const urlPath = window.location.pathname;
    const match = urlPath.match(/^\/([^/]+)\/jobs?\//i);
    let company = 'Unknown';
    if (match && match[1]) {
      // Convert "technergetics" to "Technergetics"
      company = match[1]
        .split(/[-_]/)
        .map(w => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
        .join(' ');
    }
    
    // Try to get better title from page
    const titleEl = document.querySelector('h1') ||
                    document.querySelector('[class*="title"]') ||
                    document.querySelector('title');
    const title = titleEl ? titleEl.textContent.trim() : document.title;
    
    // Get description
    const descriptionEl = document.querySelector('[class*="description"]') ||
                          document.querySelector('[class*="content"]') ||
                          document.querySelector('article') ||
                          document.querySelector('main');
    
    if (!descriptionEl) {
      console.log('JobPipe: Greenhouse board - no description found');
      return null;
    }
    
    console.log(`JobPipe: Greenhouse board extracted - company: ${company}, title: ${title}`);
    
    // Generate a stable job ID from URL for matching
    const urlHash = window.location.href.split('?')[0].replace(/[^a-zA-Z0-9]/g, '_').substring(0, 64);
    const jobId = `greenhouse-${urlHash}`;
    
    console.log(`JobPipe: Greenhouse board - generated job ID: ${jobId}`);
    
    return {
      id: jobId,
      platform: 'greenhouse',
      title: title,
      company: company,
      url: window.location.href,
      description: descriptionEl.textContent.trim(),
    };
  } catch (error) {
    console.error('Error in Greenhouse board extraction:', error);
    return null;
  }
}

/**
 * Extract job data from iCIMS job boards (e.g., careers-company.icims.com/jobs/ID)
 */
function extractICIMS() {
  try {
    const hostname = window.location.hostname.toLowerCase();
    
    // Extract company from subdomain: careers-dminc.icims.com -> DMI
    let company = 'Unknown';
    const subdomainMatch = hostname.match(/^careers-([^.]+)\.icims\.com/);
    if (subdomainMatch && subdomainMatch[1]) {
      company = subdomainMatch[1]
        .split(/[-_]/)
        .map(w => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
        .join(' ');
    }
    
    // Extract job ID from path: /jobs/28734/...
    const pathMatch = window.location.pathname.match(/\/jobs?\/(\d+)/i);
    const jobNumber = pathMatch ? pathMatch[1] : 'unknown';
    
    // Try to get title
    const titleEl = document.querySelector('h1') ||
                    document.querySelector('[class*="title"]') ||
                    document.querySelector('[class*="job-title"]') ||
                    document.querySelector('[class*="JobTitle"]') ||
                    document.querySelector('title');
    const title = titleEl ? titleEl.textContent.trim() : document.title;
    
    // Try to get description - iCIMS often uses specific class patterns
    const descriptionEl = document.querySelector('[class*="description"]') ||
                          document.querySelector('[class*="Description"]') ||
                          document.querySelector('[class*="content"]') ||
                          document.querySelector('[class*="Content"]') ||
                          document.querySelector('[class*="job-body"]') ||
                          document.querySelector('[class*="JobBody"]') ||
                          document.querySelector('article') ||
                          document.querySelector('main') ||
                          document.querySelector('.iCIMS_JobHeaderGroup') ||
                          document.querySelector('.iCIMS_JobsTable');
    
    if (!descriptionEl) {
      console.log('JobPipe: iCIMS - no description element found, using generic extraction');
      // Fall back to generic extraction for the body text
      const bodyText = document.body ? document.body.innerText.trim() : '';
      if (bodyText && bodyText.length > 100) {
        const jobId = `icims-${jobNumber}-${company.replace(/[^a-zA-Z0-9]/g, '_').toLowerCase()}`;
        return {
          id: jobId,
          platform: 'icims',
          title: title,
          company: company,
          url: window.location.href.split('?')[0],
          description: bodyText.substring(0, 10000),
        };
      }
      return null;
    }
    
    console.log(`JobPipe: iCIMS extracted - company: ${company}, title: ${title}`);
    
    // Generate stable job ID from job number and company
    const jobId = `icims-${jobNumber}-${company.replace(/[^a-zA-Z0-9]/g, '_').toLowerCase()}`;
    
    return {
      id: jobId,
      platform: 'icims',
      title: title,
      company: company,
      url: window.location.href.split('?')[0],
      description: descriptionEl.textContent.trim(),
    };
  } catch (error) {
    console.error('Error in iCIMS extraction:', error);
    return null;
  }
}

/**
 * Auto-detect platform and extract job data
 */
function extractJobData() {
  const hostname = window.location.hostname.toLowerCase();
  const fullUrl = window.location.href.toLowerCase();

  // Check for known job platforms first
  if (hostname.includes('hiring.cafe')) return extractHiringCafe();
  if (hostname.includes('linkedin.com')) return extractLinkedIn();
  if (hostname.includes('builtin.com')) return extractBuiltIn();
  if (hostname.includes('wellfound.com')) return extractWellFound();
  
  // Check for UKG/UltiPro platform (rec.pro.ukg.net)
  if (hostname.includes('rec.pro.ukg.net') || hostname.includes('ukg.net')) {
    console.log('JobPipe: Detected UKG/UltiPro platform, using specialized extraction');
    return extractUKG();
  }

  // Check for oasisrecruit.com platform (used by Discovery Senior Living)
  if (hostname.includes('oasisrecruit.com')) {
    console.log('JobPipe: Detected OasisRecruit platform, using specialized extraction');
    return extractOasisRecruit();
  }

  // Check for iCIMS platform (careers-company.icims.com)
  if (hostname.includes('icims.com')) {
    console.log('JobPipe: Detected iCIMS platform, using specialized extraction');
    return extractICIMS();
  }

  // Check for common job platform patterns in URL
  if (fullUrl.includes('/job/') || fullUrl.includes('/jobs/')) {
    console.log('JobPipe: Detected job URL pattern, using generic extraction with enhanced title detection');
    // Check if it's a known platform from URL
    if (hostname.includes('greenhouse.io')) {
      console.log('JobPipe: Detected Greenhouse platform from URL');
      return extractGreenhouseBoard();
    }
  }

  // === NEW PLATFORM DETECTION ===
  
  // Paylocity
  if (hostname.includes('paylocity.com')) {
    console.log('JobPipe: Detected Paylocity platform, using specialized extraction');
    return extractPaylocity();
  }
  
  // BambooHR
  if (hostname.includes('bamboohr.com')) {
    console.log('JobPipe: Detected BambooHR platform, using specialized extraction');
    return extractBambooHR();
  }
  
  // Workday
  if (hostname.includes('myworkdayjobs.com')) {
    console.log('JobPipe: Detected Workday platform, using specialized extraction');
    return extractWorkday();
  }
  
  // GoHire
  if (hostname.includes('gohire.io')) {
    console.log('JobPipe: Detected GoHire platform, using specialized extraction');
    return extractGoHire();
  }
  
  // ADP
  if (hostname.includes('workforcenow.adp.com')) {
    console.log('JobPipe: Detected ADP platform, using specialized extraction');
    return extractADP();
  }
  
  // SuccessFactors
  if (hostname.includes('successfactors.eu')) {
    console.log('JobPipe: Detected SuccessFactors platform, using specialized extraction');
    return extractSuccessFactors();
  }
  
  // Ashby
  if (hostname.includes('ashbyhq.com')) {
    console.log('JobPipe: Detected Ashby platform, using specialized extraction');
    return extractAshby();
  }
  
  // CareerPlug
  if (hostname.includes('careerplug.com')) {
    console.log('JobPipe: Detected CareerPlug platform, using specialized extraction');
    return extractCareerPlug();
  }
  
  // Genesis
  if (hostname.includes('genesiscareers.jobs')) {
    console.log('JobPipe: Detected Genesis platform, using specialized extraction');
    return extractGenesis();
  }

  return extractGeneric();
}

/**
 * Extract job data from OasisRecruit platform (used by Discovery Senior Living, etc.)
 */
function extractOasisRecruit() {
  try {
    // OasisRecruit specific selectors
    const titleEl = document.querySelector('h1') ||
                    document.querySelector('[class*="title"]') ||
                    document.querySelector('[class*="job-title"]') ||
                    document.querySelector('title');
    
    const descriptionEl = document.querySelector('[class*="description"]') ||
                          document.querySelector('[class*="content"]') ||
                          document.querySelector('article') ||
                          document.querySelector('main');
    
    if (!titleEl || !descriptionEl) return null;
    
    let title = titleEl.textContent.trim();
    // Clean up title (remove site name, etc.)
    title = title.replace(/\s*[-|]\s*.*$/, '').trim();
    
    // Extract company from URL or page
    let company = 'Unknown Company';
    const companyEl = document.querySelector('[class*="company"]') ||
                     document.querySelector('[class*="employer"]') ||
                     document.querySelector('a[href*="/company"]');
    if (companyEl) {
      company = companyEl.textContent.trim();
    } else {
      // Try to extract from URL (e.g., discovery-senior-living.oasisrecruit.com)
      const urlMatch = hostname.match(/^([^.]+)\.oasisrecruit\.com/);
      if (urlMatch) {
        company = urlMatch[1]
          .split('-')
          .map(word => word.charAt(0).toUpperCase() + word.slice(1))
          .join(' ');
      }
    }
    
    return {
      platform: 'OasisRecruit',
      title: title,
      company: company,
      url: window.location.href,
      description: descriptionEl.textContent.trim(),
    };
  } catch (error) {
    console.error('Error extracting OasisRecruit job:', error);
    return null;
  }
}

// ==================== NEW PLATFORM EXTRACTORS ====================

/**
 * Extract job data from Paylocity (recruiting.paylocity.com)
 */
function extractPaylocity() {
  try {
    const titleEl = document.querySelector('h1') ||
                    document.querySelector('[class*="title"]') ||
                    document.querySelector('[class*="job-title"]') ||
                    document.querySelector('title');
    const title = titleEl ? titleEl.textContent.trim().replace(/\s*[-|]\s*.*$/, '').trim() : document.title;

    let company = 'Unknown Company';
    const companyEl = document.querySelector('[class*="company"]') ||
                     document.querySelector('[class*="employer"]') ||
                     document.querySelector('meta[property="og:site_name"]');
    if (companyEl) {
      company = companyEl.getAttribute('content') || companyEl.textContent.trim();
    } else {
      const hostname = window.location.hostname;
      if (hostname.includes('paylocity.com')) {
        company = 'Paylocity Client';
      }
    }

    const descriptionEl = document.querySelector('[class*="description"]') ||
                          document.querySelector('[class*="content"]') ||
                          document.querySelector('[class*="detail"]') ||
                          document.querySelector('article') ||
                          document.querySelector('main');

    if (!descriptionEl) {
      console.log('JobPipe: Paylocity - no description found');
      return null;
    }

    const urlPath = window.location.pathname;
    const jobIdMatch = urlPath.match(/\/Details\/(\d+)/i);
    const jobId = jobIdMatch ? `paylocity-${jobIdMatch[1]}` : `paylocity-${window.location.href.split('/').pop()}`;

    console.log(`JobPipe: Paylocity extracted - Title="${title}" Company="${company}"`);

    return {
      id: jobId,
      platform: 'paylocity',
      title: title,
      company: company,
      url: window.location.href.split('?')[0],
      description: descriptionEl.textContent.trim(),
    };
  } catch (error) {
    console.error('Error extracting Paylocity job:', error);
    return null;
  }
}

/**
 * Extract job data from BambooHR (*.bamboohr.com/careers/*)
 */
function extractBambooHR() {
  try {
    const titleEl = document.querySelector('h1') ||
                    document.querySelector('[class*="title"]') ||
                    document.querySelector('[class*="job-title"]') ||
                    document.querySelector('title');
    const title = titleEl ? titleEl.textContent.trim().replace(/\s*[-|]\s*.*$/, '').trim() : document.title;

    let company = 'Unknown Company';
    const hostname = window.location.hostname;
    const subdomainMatch = hostname.match(/^([^.]+)\.bamboohr\.com/);
    if (subdomainMatch && subdomainMatch[1]) {
      company = subdomainMatch[1]
        .split(/[-_]/)
        .map(w => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
        .join(' ');
    }

    const descriptionEl = document.querySelector('[class*="description"]') ||
                          document.querySelector('[class*="content"]') ||
                          document.querySelector('[class*="detail"]') ||
                          document.querySelector('article') ||
                          document.querySelector('main');

    if (!descriptionEl) {
      console.log('JobPipe: BambooHR - no description found');
      return null;
    }

    const urlPath = window.location.pathname;
    const jobIdMatch = urlPath.match(/\/careers?\/(\d+)/i);
    const jobId = jobIdMatch ? `bamboohr-${jobIdMatch[1]}` : `bamboohr-${window.location.href.split('/').pop()}`;

    console.log(`JobPipe: BambooHR extracted - Title="${title}" Company="${company}"`);

    return {
      id: jobId,
      platform: 'bamboohr',
      title: title,
      company: company,
      url: window.location.href.split('?')[0],
      description: descriptionEl.textContent.trim(),
    };
  } catch (error) {
    console.error('Error extracting BambooHR job:', error);
    return null;
  }
}

/**
 * Extract job data from Workday (*.myworkdayjobs.com)
 */
function extractWorkday() {
  try {
    const titleEl = document.querySelector('h1') ||
                    document.querySelector('[class*="title"]') ||
                    document.querySelector('[class*="job-title"]') ||
                    document.querySelector('[data-automation-id="jobPostingHeader"]') ||
                    document.querySelector('title');
    const title = titleEl ? titleEl.textContent.trim().replace(/\s*[-|]\s*.*$/, '').trim() : document.title;

    let company = 'Unknown Company';
    const hostname = window.location.hostname;
    const subdomainMatch = hostname.match(/^([^.]+)\.wd\d*\.myworkdayjobs\.com/);
    if (subdomainMatch && subdomainMatch[1]) {
      company = subdomainMatch[1]
        .split(/[-_]/)
        .map(w => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
        .join(' ');
    }

    const companyEl = document.querySelector('[class*="company"]') ||
                     document.querySelector('[class*="employer"]') ||
                     document.querySelector('[data-automation-id="subtitle"]');
    if (companyEl) {
      company = companyEl.textContent.trim() || company;
    }

    const descriptionEl = document.querySelector('[class*="description"]') ||
                          document.querySelector('[class*="content"]') ||
                          document.querySelector('[class*="detail"]') ||
                          document.querySelector('[data-automation-id="jobPostingDescription"]') ||
                          document.querySelector('article') ||
                          document.querySelector('main');

    if (!descriptionEl) {
      console.log('JobPipe: Workday - no description found');
      return null;
    }

    const urlPath = window.location.pathname;
    const jobIdMatch = urlPath.match(/\/job\/([^/]+)\/([^/]+)/i);
    const jobId = jobIdMatch ? `workday-${jobIdMatch[2]}` : `workday-${window.location.href.split('/').pop()}`;

    console.log(`JobPipe: Workday extracted - Title="${title}" Company="${company}"`);

    return {
      id: jobId,
      platform: 'workday',
      title: title,
      company: company,
      url: window.location.href.split('?')[0],
      description: descriptionEl.textContent.trim(),
    };
  } catch (error) {
    console.error('Error extracting Workday job:', error);
    return null;
  }
}

/**
 * Extract job data from GoHire (jobs.gohire.io)
 */
function extractGoHire() {
  try {
    const titleEl = document.querySelector('h1') ||
                    document.querySelector('[class*="title"]') ||
                    document.querySelector('[class*="job-title"]') ||
                    document.querySelector('title');
    const title = titleEl ? titleEl.textContent.trim().replace(/\s*[-|]\s*.*$/, '').trim() : document.title;

    let company = 'Unknown Company';
    const companyEl = document.querySelector('[class*="company"]') ||
                     document.querySelector('[class*="employer"]') ||
                     document.querySelector('[class*="organization"]');
    if (companyEl) {
      company = companyEl.textContent.trim();
    } else {
      const hostname = window.location.hostname;
      if (hostname.includes('gohire.io')) {
        company = 'GoHire Client';
      }
    }

    const descriptionEl = document.querySelector('[class*="description"]') ||
                          document.querySelector('[class*="content"]') ||
                          document.querySelector('[class*="detail"]') ||
                          document.querySelector('article') ||
                          document.querySelector('main');

    if (!descriptionEl) {
      console.log('JobPipe: GoHire - no description found');
      return null;
    }

    const urlPath = window.location.pathname;
    const jobIdMatch = urlPath.match(/\/(\w+)\/(\d+)/i);
    const jobId = jobIdMatch ? `gohire-${jobIdMatch[2]}` : `gohire-${window.location.href.split('/').pop()}`;

    console.log(`JobPipe: GoHire extracted - Title="${title}" Company="${company}"`);

    return {
      id: jobId,
      platform: 'gohire',
      title: title,
      company: company,
      url: window.location.href.split('?')[0],
      description: descriptionEl.textContent.trim(),
    };
  } catch (error) {
    console.error('Error extracting GoHire job:', error);
    return null;
  }
}

/**
 * Extract job data from ADP (workforcenow.adp.com)
 */
function extractADP() {
  try {
    const titleEl = document.querySelector('h1') ||
                    document.querySelector('[class*="title"]') ||
                    document.querySelector('[class*="job-title"]') ||
                    document.querySelector('title');
    const title = titleEl ? titleEl.textContent.trim().replace(/\s*[-|]\s*.*$/, '').trim() : document.title;

    let company = 'Unknown Company';
    const companyEl = document.querySelector('[class*="company"]') ||
                     document.querySelector('[class*="employer"]') ||
                     document.querySelector('[class*="organization"]') ||
                     document.querySelector('meta[property="og:site_name"]');
    if (companyEl) {
      company = companyEl.getAttribute('content') || companyEl.textContent.trim();
    }

    const descriptionEl = document.querySelector('[class*="description"]') ||
                          document.querySelector('[class*="content"]') ||
                          document.querySelector('[class*="detail"]') ||
                          document.querySelector('article') ||
                          document.querySelector('main');

    if (!descriptionEl) {
      console.log('JobPipe: ADP - no description found');
      return null;
    }

    const urlHash = window.location.href.split('?')[0].replace(/[^a-zA-Z0-9]/g, '_').substring(0, 64);
    const jobId = `adp-${urlHash}`;

    console.log(`JobPipe: ADP extracted - Title="${title}" Company="${company}"`);

    return {
      id: jobId,
      platform: 'adp',
      title: title,
      company: company,
      url: window.location.href.split('?')[0],
      description: descriptionEl.textContent.trim(),
    };
  } catch (error) {
    console.error('Error extracting ADP job:', error);
    return null;
  }
}

/**
 * Extract job data from SuccessFactors (*.successfactors.eu)
 */
function extractSuccessFactors() {
  try {
    const titleEl = document.querySelector('h1') ||
                    document.querySelector('[class*="title"]') ||
                    document.querySelector('[class*="job-title"]') ||
                    document.querySelector('[data-testid="job-title"]') ||
                    document.querySelector('title');
    const title = titleEl ? titleEl.textContent.trim().replace(/\s*[-|]\s*.*$/, '').trim() : document.title;

    let company = 'Unknown Company';
    const companyEl = document.querySelector('[class*="company"]') ||
                     document.querySelector('[class*="employer"]') ||
                     document.querySelector('[class*="organization"]') ||
                     document.querySelector('meta[property="og:site_name"]');
    if (companyEl) {
      company = companyEl.getAttribute('content') || companyEl.textContent.trim();
    } else {
      const hostname = window.location.hostname;
      if (hostname.includes('successfactors.eu')) {
        company = 'SuccessFactors Client';
      }
    }

    const descriptionEl = document.querySelector('[class*="description"]') ||
                          document.querySelector('[class*="content"]') ||
                          document.querySelector('[class*="detail"]') ||
                          document.querySelector('[data-testid="job-description"]') ||
                          document.querySelector('article') ||
                          document.querySelector('main');

    if (!descriptionEl) {
      console.log('JobPipe: SuccessFactors - no description found');
      return null;
    }

    const urlParams = new URLSearchParams(window.location.search);
    const jobId = urlParams.get('career_job_req_id') || urlParams.get('jobId') || window.location.href.split('/').pop();
    const jobIdClean = `successfactors-${jobId}`;

    console.log(`JobPipe: SuccessFactors extracted - Title="${title}" Company="${company}"`);

    return {
      id: jobIdClean,
      platform: 'successfactors',
      title: title,
      company: company,
      url: window.location.href.split('?')[0],
      description: descriptionEl.textContent.trim(),
    };
  } catch (error) {
    console.error('Error extracting SuccessFactors job:', error);
    return null;
  }
}

/**
 * Extract job data from Ashby (jobs.ashbyhq.com)
 */
function extractAshby() {
  try {
    const titleEl = document.querySelector('h1') ||
                    document.querySelector('[class*="title"]') ||
                    document.querySelector('[class*="job-title"]') ||
                    document.querySelector('title');
    const title = titleEl ? titleEl.textContent.trim().replace(/\s*[-|]\s*.*$/, '').trim() : document.title;

    let company = 'Unknown Company';
    const urlPath = window.location.pathname;
    const companyMatch = urlPath.match(/^\/([^/]+)/);
    if (companyMatch && companyMatch[1]) {
      company = companyMatch[1]
        .split(/[-_]/)
        .map(w => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
        .join(' ');
    }

    const descriptionEl = document.querySelector('[class*="description"]') ||
                          document.querySelector('[class*="content"]') ||
                          document.querySelector('[class*="detail"]') ||
                          document.querySelector('article') ||
                          document.querySelector('main');

    if (!descriptionEl) {
      console.log('JobPipe: Ashby - no description found');
      return null;
    }

    const jobIdMatch = urlPath.match(/\/([a-f0-9-]{36})/i);
    const jobId = jobIdMatch ? `ashby-${jobIdMatch[1]}` : `ashby-${window.location.href.split('/').pop()}`;

    console.log(`JobPipe: Ashby extracted - Title="${title}" Company="${company}"`);

    return {
      id: jobId,
      platform: 'ashby',
      title: title,
      company: company,
      url: window.location.href.split('?')[0],
      description: descriptionEl.textContent.trim(),
    };
  } catch (error) {
    console.error('Error extracting Ashby job:', error);
    return null;
  }
}

/**
 * Extract job data from CareerPlug (app.careerplug.com)
 */
function extractCareerPlug() {
  try {
    const titleEl = document.querySelector('h1') ||
                    document.querySelector('[class*="title"]') ||
                    document.querySelector('[class*="job-title"]') ||
                    document.querySelector('title');
    const title = titleEl ? titleEl.textContent.trim().replace(/\s*[-|]\s*.*$/, '').trim() : document.title;

    let company = 'Unknown Company';
    const companyEl = document.querySelector('[class*="company"]') ||
                     document.querySelector('[class*="employer"]') ||
                     document.querySelector('[class*="organization"]');
    if (companyEl) {
      company = companyEl.textContent.trim();
    }

    const descriptionEl = document.querySelector('[class*="description"]') ||
                          document.querySelector('[class*="content"]') ||
                          document.querySelector('[class*="detail"]') ||
                          document.querySelector('article') ||
                          document.querySelector('main');

    if (!descriptionEl) {
      console.log('JobPipe: CareerPlug - no description found');
      return null;
    }

    const urlPath = window.location.pathname;
    const jobIdMatch = urlPath.match(/\/jobs?\/(\d+)/i);
    const jobId = jobIdMatch ? `careerplug-${jobIdMatch[1]}` : `careerplug-${window.location.href.split('/').pop()}`;

    console.log(`JobPipe: CareerPlug extracted - Title="${title}" Company="${company}"`);

    return {
      id: jobId,
      platform: 'careerplug',
      title: title,
      company: company,
      url: window.location.href.split('?')[0],
      description: descriptionEl.textContent.trim(),
    };
  } catch (error) {
    console.error('Error extracting CareerPlug job:', error);
    return null;
  }
}

/**
 * Extract job data from Genesis (*.genesiscareers.jobs)
 */
function extractGenesis() {
  try {
    const titleEl = document.querySelector('h1') ||
                    document.querySelector('[class*="title"]') ||
                    document.querySelector('[class*="job-title"]') ||
                    document.querySelector('title');
    const title = titleEl ? titleEl.textContent.trim().replace(/\s*[-|]\s*.*$/, '').trim() : document.title;

    let company = 'Unknown Company';
    const hostname = window.location.hostname;
    const subdomainMatch = hostname.match(/^([^.]+)\.genesiscareers\.jobs/);
    if (subdomainMatch && subdomainMatch[1]) {
      company = subdomainMatch[1]
        .split(/[-_]/)
        .map(w => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
        .join(' ');
    }

    const descriptionEl = document.querySelector('[class*="description"]') ||
                          document.querySelector('[class*="content"]') ||
                          document.querySelector('[class*="detail"]') ||
                          document.querySelector('article') ||
                          document.querySelector('main');

    if (!descriptionEl) {
      console.log('JobPipe: Genesis - no description found');
      return null;
    }

    const urlPath = window.location.pathname;
    const jobIdMatch = urlPath.match(/\/jobs?\/(\d+)/i);
    const jobId = jobIdMatch ? `genesis-${jobIdMatch[1]}` : `genesis-${window.location.href.split('/').pop()}`;

    console.log(`JobPipe: Genesis extracted - Title="${title}" Company="${company}"`);

    return {
      id: jobId,
      platform: 'genesis',
      title: title,
      company: company,
      url: window.location.href.split('?')[0],
      description: descriptionEl.textContent.trim(),
    };
  } catch (error) {
    console.error('Error extracting Genesis job:', error);
    return null;
  }
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
    description: decodeHtmlEntities(jobInfo.description || processed.description || ''),
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
        console.log(`JobPipe: Job ${index} - Description length:`, job.description?.length || 0, '| Preview:', job.description?.substring(0, 100) || 'EMPTY');
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
 * This is the primary extraction method — works for both initial load and SPA navigation.
 * __NEXT_DATA__ is NOT reliable after SPA navigation (Next.js doesn't update it client-side).
 */
function extractHiringCafeJobsFromDom() {
  const jobs = [];
  const seen = new Set();

  try {
    document.querySelectorAll('a[href*="/viewjob/"]').forEach(link => {
      try {
        const url = link.href;
        if (seen.has(url)) return;
        seen.add(url);

        // Find the card container using closest() - matches relative z-index wrapper
        const card = link.closest('[class*="z-"][class*="relative"]') ||
                     link.closest('[class*="rounded-xl"]') ||
                     link.parentElement?.parentElement;
        if (!card) return;

        // Title: bold line-clamped span inside the card
        const titleEl = card.querySelector('.font-bold.line-clamp-2, .font-bold.line-clamp-3');
        const title = titleEl ? titleEl.textContent.trim() : 'Unknown Title';

        // Company: bold text inside the light description span
        const summary = card.querySelector('.line-clamp-3.font-light');
        const companyEl = summary ? summary.querySelector('.font-bold') : null;
        const company = companyEl ? companyEl.textContent.trim() : 'Unknown Company';

        // Try to get description from card text content
        const cardText = card.textContent || '';
        const description = cardText.length > title.length + company.length 
          ? cardText.substring(0, 500).trim() 
          : `${title} at ${company}`;

        jobs.push({
          platform: 'HiringCafe',
          title: title.substring(0, 200),
          company: company,
          url: url,
          description: description,
        });
      } catch (e) { /* skip failed items */ }
    });
  } catch (e) {
    console.error('JobPipe: DOM extraction error:', e);
  }

  console.log(`JobPipe: DOM extracted ${jobs.length} jobs`);
  if (jobs.length > 0) {
    console.log(`JobPipe: Sample DOM job description lengths:`, jobs.slice(0, 3).map(j => j.description?.length || 0));
  }
  return jobs;
}

// ==================== DETAIL PAGE ENRICHMENT ====================

/**
 * Extract rich job data from a HiringCafe sidebar detail page (/viewjob/...).
 * The sidebar detail panel has full descriptions, compensation, requirements, etc.
 * This is called automatically when navigating to a detail page.
 */
function extractHiringCafeDetailPage() {
  try {
    // Must be on a detail page
    if (!window.location.pathname.includes('/viewjob/')) return null;

    console.log('JobPipe: Extracting detail page...');

    // --- Title ---
    // Usually an h1 or h2 in the detail panel
    const titleEl = document.querySelector('h1') || document.querySelector('h2');
    const title = titleEl ? titleEl.textContent.trim() : null;
    if (!title) {
      console.log('JobPipe: No title found on detail page');
      return null;
    }

    // --- Company ---
    // Often found in a span after "@" symbol near the title, or in metadata area
    let company = null;
    const companyPatterns = [
      // Look for text containing "@ CompanyName" pattern
      document.querySelector('[class*="text-gray"][class*="text-sm"], [class*="text-gray"][class*="text-xs"]'),
    ];
    // Try finding company from any element containing "@"
    const allEls = document.querySelectorAll('span, p, div');
    for (const el of allEls) {
      const text = el.textContent.trim();
      const match = text.match(/@\s+(.+)/);
      if (match && match[1] && match[1].length < 100) {
        company = match[1].trim();
        break;
      }
    }

    // --- Full page text for fallback extraction ---
    const pageText = document.body?.textContent || '';

    // --- Posted info ---
    let postedAgo = null;
    const postedMatch = pageText.match(/Posted\s+(\d+\s*[dwmyh]\w*)/i);
    if (postedMatch) postedAgo = postedMatch[1];

    // --- Location ---
    let location = null;
    const locationPatterns = [
      // City, State, Country pattern
      pageText.match(/([A-Z][a-z]+(?:\s[A-Z][a-z]+)*,\s[A-Z]{2}[a-z]*\s*(?:,\s*[A-Z][a-z]+(?:\s[A-Z][a-z]+)*)?)/),
    ];
    // Try looking in elements near the title/company area
    const metadataArea = titleEl?.parentElement?.parentElement || document.body;
    const metadataText = metadataArea.textContent || '';
    const locMatch = metadataText.match(/([A-Z][a-z]+(?:\s[A-Z][a-z]+)*,\s[A-Z]{2}(?:\s[A-Z][a-z]+)?)/);
    if (locMatch) location = locMatch[1];

    if (!location) {
      // Broader search: look for city, STATE pattern
      const broadMatch = pageText.match(/([A-Z][a-z]+(?:\s[A-Z][a-z]+)*,\s[A-Z]{2}\b)/);
      if (broadMatch) location = broadMatch[1];
    }

    // --- Compensation ---
    let compensation = null;
    const compPatterns = [
      /\$\d{2,3}k\s*-\s*\$?\d{2,3}k\s*\/\s*(?:yr|mo|hr|wk|day)/i,
      /\$\d{2,3}k\s*\+\s*\/\s*(?:yr|mo|hr|wk|day)/i,
      /\$\d+[\d,]*\s*-\s*\$\d+[\d,]*\s*\/\s*(?:yr|mo|hr|wk|day)/i,
      /\$\d+[\d,]*\s*\+\s*\/\s*(?:yr|mo|hr|wk|day)/i,
    ];
    for (const pattern of compPatterns) {
      const match = pageText.match(pattern);
      if (match) { compensation = match[0].trim(); break; }
    }

    // --- Workplace type (Onsite/Hybrid/Remote) ---
    let workplaceType = null;
    const workplaceMatch = pageText.match(/\b(Onsite|Remote|Hybrid)\b/i);
    if (workplaceMatch) workplaceType = workplaceMatch[1];

    // --- Employment type (Full Time, Part Time, Contract, etc.) ---
    let employmentType = null;
    const empMatch = pageText.match(/\b(Full Time|Part Time|Contract|Temporary|Internship|Freelance)\b/i);
    if (empMatch) employmentType = empMatch[1];

    // --- Full Description ---
    // Look for "Job Description" or "Company Description" sections
    let description = '';
    const descSections = [
      'Job Description',
      'Company Description',
      'Job Description:',
      'Company Description:',
      'Description',
      'About the job',
      'About this role',
    ];
    
    // Try to find description content areas
    const contentAreas = document.querySelectorAll(
      '[class*="prose"], [class*="description"], [class*="content"], article, ' +
      '[class*="text-gray"][class*="leading"], [class*="job-description"], ' +
      '[class*="rich-text"], [class*="job-detail"]'
    );
    
    if (contentAreas.length > 0) {
      // Take the largest content area
      let largest = null;
      let largestSize = 0;
      for (const area of contentAreas) {
        const size = area.textContent.length;
        if (size > largestSize) {
          largestSize = size;
          largest = area;
        }
      }
      if (largest && largestSize > 200) {
        description = largest.textContent.trim();
      }
    }

    // If no content area found, get all non-header text
    if (!description || description.length < 200) {
      // Try to get text from the main content panel, excluding nav/header
      const mainContent = document.querySelector('main') || 
                          document.querySelector('[role="main"]') ||
                          document.querySelector('[class*="flex-1"]');
      if (mainContent) {
        description = mainContent.textContent.trim();
      } else {
        // Fallback: all body text minus header/meta noise
        description = pageText;
      }
    }

    // --- Requirements / Qualifications ---
    let requirements = null;
    const reqSections = ['Qualifications', 'Requirements', 'Qualifications:', 'Requirements:'];
    for (const section of reqSections) {
      const idx = description.indexOf(section);
      if (idx >= 0) {
        // Get ~1000 chars after the section header
        requirements = description.substring(idx, idx + 1500).trim();
        break;
      }
    }

    // --- Tools/Technologies mentioned ---
    let technicalTools = null;
    const toolsLabels = ['Technical Tools', 'Tools', 'Technologies', 'Technical Skills'];
    for (const label of toolsLabels) {
      const idx = description.indexOf(label);
      if (idx >= 0) {
        technicalTools = description.substring(idx, idx + 500).trim();
        break;
      }
    }

    // --- URL ---
    const url = window.location.href;

    // --- Views/Saves/Applications from DOM ---
    const stats = extractHiringCafeStatsFromDom();

    console.log(`JobPipe: Detail page extracted - Title="${title}" Company="${company || 'unknown'}" Desc=${description.length}chars`);

    return {
      platform: 'HiringCafe',
      title: title,
      company: company || 'Unknown Company',
      url: url,
      description: decodeHtmlEntities(description),
      location: location,
      compensation: compensation,
      workplace_type: workplaceType,
      employment_type: employmentType,
      views: stats.views ?? null,
      saves: stats.saves ?? null,
      applications: stats.applications ?? null,
      posted_ago: postedAgo,
      requirements: requirements ? decodeHtmlEntities(requirements) : null,
      technical_tools: technicalTools ? decodeHtmlEntities(technicalTools) : null,
      // Mark as enriched so background knows to bypass cache
      enriched: true,
    };
  } catch (error) {
    console.error('JobPipe: Error extracting detail page:', error);
    return null;
  }
}

/**
 * Check if we're on a HiringCafe detail page and extract enriched data.
 * Returns enriched job data or null.
 */
function tryExtractDetailPage() {
  const hostname = window.location.hostname.toLowerCase();
  if (!hostname.includes('hiring.cafe')) return null;
  if (!window.location.pathname.includes('/viewjob/')) return null;
  return extractHiringCafeDetailPage();
}

/**
 * Extract multiple job listings from search results page
 * Always extracts fresh data to handle SPA navigation
 */
async function extractBatchJobs() {
  const hostname = window.location.hostname.toLowerCase();
  const jobs = [];

  if (hostname.includes('hiring.cafe')) {
    // Check if we're on a detail page — extract rich single job data
    if (window.location.pathname.includes('/viewjob/')) {
      console.log('JobPipe: On detail page, extracting job from __NEXT_DATA__...');
      
      // Try __NEXT_DATA__ first (it has full rich data for the detail page too)
      const nextDataJobs = extractJobsFromNextData();
      if (nextDataJobs.length > 0) {
        // Find the job matching current URL
        const matchedJob = nextDataJobs.find(j => j.url === window.location.href) || nextDataJobs[0];
        console.log(`JobPipe: Detail page extracted from __NEXT_DATA__: "${matchedJob.title}" ${matchedJob.description?.length || 0}chars`);
        return [matchedJob];
      }
      
      // Fallback: DOM-based detail extraction
      console.log('JobPipe: __NEXT_DATA__ empty, trying DOM detail extraction...');
      const detailJob = extractHiringCafeDetailPage();
      if (detailJob) {
        console.log(`JobPipe: Detail page DOM extracted: "${detailJob.title}" ${detailJob.description.length}chars`);
        return [detailJob];
      }
      console.log('JobPipe: Detail page extraction failed, falling back to batch');
    }

    console.log('JobPipe: Extracting jobs from HiringCafe...');

    // Try __NEXT_DATA__ first for rich data (full descriptions, compensation, etc.)
    // This is the most reliable method on the initial search results page
    let extractedJobs = extractJobsFromNextData();
    
    if (extractedJobs.length === 0) {
      // Fallback: DOM-only extraction for SPA-navigated pages
      console.log('JobPipe: No __NEXT_DATA__ hits, falling back to DOM extraction...');
      extractedJobs = extractHiringCafeJobsFromDom();
    }

    console.log(`JobPipe: Found ${extractedJobs.length} jobs`);

    if (extractedJobs.length === 0) {
      console.log('JobPipe: No HiringCafe jobs found');
      return [];
    }

    // Respect a user-configurable batch limit
    const limit = await new Promise((resolve) => {
      try {
        chrome.storage.local.get(['batchCaptureLimit'], (res) => {
          resolve(res && res.batchCaptureLimit ? res.batchCaptureLimit : 1000);
        });
      } catch (e) {
        resolve(1000);
      }
    });

    const limitedJobs = extractedJobs.slice(0, limit);
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

  // Handle enrichment requests from background script
  if (request.action === 'ENRICH_CURRENT_JOB') {
    handleDetailEnrichment(sendResponse);
    return true;
  }

  // Handle scrape trigger from background (when a tab opened by our extension finishes loading)
  if (request.action === 'TRIGGER_SCRAPE') {
    console.log('JobPipe: Scrape triggered by background (opened tab loaded)');
    // Force a fresh scrape regardless of previous attempts
    autoScrapeAttempted = false;
    lastJobCount = 0;
    attemptAutoScrape();
    sendResponse({ success: true });
    return false;
  }

  // Handle exclude site request from popup
  if (request.action === 'EXCLUDE_SITE') {
    excludeCurrentSite().then(() => {
      sendResponse({ success: true });
      // Update overlay to show excluded status
      updateOverlayStatus('Site excluded', 0, 0, 'Marked as not a job board');
    });
    return true; // Async response
  }

  // Handle include site request from popup
  if (request.action === 'INCLUDE_SITE') {
    includeCurrentSite().then(() => {
      sendResponse({ success: true });
      // Reset auto-scrape flag to allow re-scraping
      autoScrapeAttempted = false;
    });
    return true; // Async response
  }

  // Check if current site is excluded
  if (request.action === 'CHECK_EXCLUDED') {
    isCurrentSiteExcluded().then((excluded) => {
      sendResponse({ success: true, excluded });
    });
    return true; // Async response
  }
});

// Track sent URLs locally to prevent double-sends within the same page load
let locallySentUrls = new Set();

// Auto-scrape state
let autoScrapeEnabled = true; // Enabled by default
let autoScrapeAttempted = false;
let lastUrl = window.location.href;
let overlayElement = null;
let overlayVisible = true;
let lastJobCount = 0; // Track number of jobs last scraped
let detailPageEnrichmentTimer = null; // Debounce timer for detail page enrichment
let lastJobSignature = null; // Track last job data signature for change detection

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

// Detect SPA navigation and poll for new job data

// Detect URL changes (SPA navigation)
setInterval(() => {
  const currentUrl = window.location.href;
  if (currentUrl !== lastUrl) {
    console.log('JobPipe: URL changed from', lastUrl, 'to', currentUrl);
    lastUrl = currentUrl;
    autoScrapeAttempted = false;
    lastJobCount = 0;
    if (autoScrapeEnabled) {
      setTimeout(() => attemptAutoScrape(), 500);
    }
  }
}, 500);

// Also listen for popstate (browser back/forward)
window.addEventListener('popstate', () => {
  console.log('JobPipe: Popstate detected');
  autoScrapeAttempted = false;
  lastJobCount = 0;
  if (autoScrapeEnabled) {
    setTimeout(() => attemptAutoScrape(), 500);
  }
});

// Listen for pushstate/replacestate (programmatic navigation)
const originalPushState = history.pushState;
const originalReplaceState = history.replaceState;
history.pushState = function() {
  originalPushState.apply(this, arguments);
  console.log('JobPipe: Pushstate detected');
  autoScrapeAttempted = false;
  lastJobCount = 0;
  if (autoScrapeEnabled) {
    setTimeout(() => attemptAutoScrape(), 500);
  }
};
history.replaceState = function() {
  originalReplaceState.apply(this, arguments);
  console.log('JobPipe: Replacestate detected');
  autoScrapeAttempted = false;
  lastJobCount = 0;
  if (autoScrapeEnabled) {
    setTimeout(() => attemptAutoScrape(), 500);
  }
};

// Notify background script that content script is ready
console.log('JobPipe content script loaded on:', window.location.href);

/**
 * Create and inject the overlay UI on the page
 */
function createOverlay() {
  // Check if overlay already exists
  if (document.getElementById('jobpipe-overlay')) return;
  
  const hostname = window.location.hostname.toLowerCase();
  const isGeneric = !hostname.includes('hiring.cafe') &&
                   !hostname.includes('linkedin.com') &&
                   !hostname.includes('builtin.com') &&
                   !hostname.includes('wellfound.com');
  
  const overlay = document.createElement('div');
  overlay.id = 'jobpipe-overlay';
  overlay.innerHTML = `
    <div class="jobpipe-overlay-header" id="jobpipe-overlay-header">
      <span class="jobpipe-overlay-title">📎 JobPipe${isGeneric ? ' (Generic)' : ''}</span>
      <div class="jobpipe-overlay-controls">
        <span class="jobpipe-status-dot" id="jobpipe-status-dot"></span>
        <button class="jobpipe-overlay-toggle" id="jobpipe-overlay-toggle">−</button>
      </div>
    </div>
    <div class="jobpipe-overlay-body" id="jobpipe-overlay-body">
      <div class="jobpipe-overlay-status" id="jobpipe-overlay-status">Ready</div>
      <div class="jobpipe-overlay-job-title" id="jobpipe-overlay-job-title" style="font-size:11px; opacity:0.9; margin-bottom:8px; max-height:40px; overflow:hidden;"></div>
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
      z-index: 2147483647;
      font-family: 'Segoe UI', Tahoma, sans-serif;
      font-size: 12px;
      transition: all 0.3s ease;
      isolation: isolate;
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
    safeSendMessage({
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
function updateOverlayStatus(status, jobsFound = 0, jobsSent = 0, jobTitle = null) {
  const statusEl = document.getElementById('jobpipe-overlay-status');
  const dotEl = document.getElementById('jobpipe-status-dot');
  const foundEl = document.getElementById('jobpipe-jobs-found');
  const sentEl = document.getElementById('jobpipe-jobs-sent');
  const titleEl = document.getElementById('jobpipe-overlay-job-title');
  
  if (!statusEl) return;
  
  statusEl.textContent = status;
  foundEl.textContent = `Found: ${jobsFound}`;
  sentEl.textContent = `Sent: ${jobsSent}`;
  
  // Update job title display if provided
  if (titleEl && jobTitle) {
    titleEl.textContent = `📋 ${jobTitle}`;
    titleEl.title = jobTitle; // Tooltip with full title
  }
  
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
  
  // Check if this hostname is marked as "not a job board"
  const excludedHosts = await getExcludedHosts();
  if (excludedHosts.has(hostname)) {
    console.log('JobPipe: Skipping auto-scrape - site marked as not a job board:', hostname);
    updateOverlayStatus('Site excluded', 0, 0, 'Marked as not a job board');
    return;
  }
  
  // Log the site we're attempting to scrape (now supports any site)
  console.log('JobPipe: Attempting auto-scrape on:', window.location.href, '(' + hostname + ')');

  // Check if this URL was already sent in this page session
  const currentUrl = window.location.href;
  if (locallySentUrls.has(currentUrl)) {
    console.log('JobPipe: URL already sent in this page session, skipping');
    return;
  }

  // Detect detail page for enrichment messaging
  const isDetailPage = window.location.pathname.includes('/viewjob/');

  // Notify popup and update overlay of scraping start
  updateOverlayStatus(isDetailPage ? 'Enriching...' : 'Scraping...', 0, 0, 'Detecting job...');
  
  safeSendMessage({
    action: 'SCRAPE_STATUS_UPDATE',
    status: 'Scraping...',
    jobsFound: 0,
    jobsSent: 0
  });

  try {
    // Poll for jobs to appear (SPA navigation may take time to load data)
    updateOverlayStatus('Waiting for page...', 0, 0, 'Detecting job...');
    let jobs = [];
    const maxWait = 10000;
    const startTime = Date.now();
    
    while (Date.now() - startTime < maxWait) {
      jobs = await extractBatchJobs();
      if (jobs && jobs.length > 0) {
        console.log(`JobPipe: Found ${jobs.length} jobs after ${Date.now() - startTime}ms`);
        break;
      }
      await new Promise(resolve => setTimeout(resolve, 1000));
    }

    // Fallback: try single job extraction (handles generic sites)
    if (!jobs || jobs.length === 0) {
      console.log('JobPipe: Batch extraction found no jobs, trying single job extraction...');
      const singleJob = extractJobData();
      if (singleJob) {
        jobs = [singleJob];
        console.log(`JobPipe: Single job extracted: ${singleJob.title}`);
      }
    }

    if (!jobs || jobs.length === 0) {
      console.log('JobPipe: No jobs found to auto-scrape');
      updateOverlayStatus('No jobs found', 0, 0, 'No job detected');
      safeSendMessage({
        action: 'SCRAPE_STATUS_UPDATE',
        status: 'No jobs found',
        jobsFound: 0,
        jobsSent: 0
      });
      return;
    }

    // Update overlay with job title
    const jobTitle = jobs[0]?.title || 'Unknown Job';
    console.log(`JobPipe: Auto-scraped ${jobs.length} jobs, sending to server...`);
    console.log('JobPipe: Job data sample:', JSON.stringify({
      title: jobs[0]?.title,
      company: jobs[0]?.company,
      url: jobs[0]?.url,
      descriptionLength: jobs[0]?.description?.length || 0,
      platform: jobs[0]?.platform
    }));
    updateOverlayStatus('Sending...', jobs.length, 0, jobTitle);

    // Notify jobs found
    safeSendMessage({
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
    const response = await safeSendMessage({
      action: 'SEND_BATCH_TO_SERVER',
      jobs: jobs,
      serverUrl: fullServerUrl
    });

    if (response && response.success) {
      const sentCount = response.count || jobs.length;
      const successLabel = isDetailPage && jobs.length === 1 ? 'Enriched ✓' : 'Success ✓';
      const displayTitle = jobs[0]?.title || 'Unknown Job';
      
      // Show server response confirmation if available
      let serverMsg = '';
      if (response && response.result) {
        const r = response.result;
        serverMsg = ` (inserted: ${r.inserted}, updated: ${r.updated})`;
        console.log(`JobPipe: Server confirmed - inserted=${r.inserted}, updated=${r.updated}, run=${r.run_id}`);
        if (r.updated > 0 && isDetailPage) {
          console.log(`JobPipe: ✅ Enriched job "${displayTitle}" updated existing database record`);
        }
      }
      
      updateOverlayStatus(successLabel + serverMsg, jobs.length, sentCount, displayTitle);
      safeSendMessage({
        action: 'SCRAPE_STATUS_UPDATE',
        status: successLabel,
        jobsFound: jobs.length,
        jobsSent: sentCount
      });
      // Track this URL to prevent double-sends
      locallySentUrls.add(currentUrl);
    } else {
      const displayTitle = jobs[0]?.title || 'Unknown Job';
      updateOverlayStatus('Error ✗', jobs.length, 0, displayTitle);
      safeSendMessage({
        action: 'SCRAPE_STATUS_UPDATE',
        status: 'Error ✗',
        jobsFound: jobs.length,
        jobsSent: 0
      });
    }
  } catch (error) {
    console.error('JobPipe: Auto-scrape error:', error);
    updateOverlayStatus('Error ✗', 0, 0);
    safeSendMessage({
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
    const result = await safeSendMessage({
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
 * Handle detail page enrichment request from background script.
 * Extracts rich data from the current detail page and sends it to the server.
 */
async function handleDetailEnrichment(sendResponse) {
  try {
    const detailJob = tryExtractDetailPage();
    if (!detailJob) {
      sendResponse({ success: false, error: 'Not on a detail page' });
      return;
    }

    // Get server URL
    const result = await chrome.storage.local.get(['serverUrl']);
    const serverUrl = result.serverUrl || '127.0.0.1:3838';
    const fullServerUrl = serverUrl.startsWith('http://') ? serverUrl : `http://${serverUrl}`;

    // Send as enrichment (background will bypass cache for enriched jobs)
    const response = await safeSendMessage({
      action: 'SEND_ENRICHED_TO_SERVER',
      jobData: detailJob,
      serverUrl: fullServerUrl,
    });

    sendResponse(response);
  } catch (error) {
    console.error('JobPipe: Enrichment error:', error);
    sendResponse({ success: false, error: error.message });
  }
}

/**
 * Handle batch job capture
 */
async function handleCaptureBatch(request, sendResponse) {
  try {
    console.log('JobPipe content: handleCaptureBatch called, serverUrl=', request.serverUrl);

    // Reset flags to allow re-scraping (for manual capture or new searches)
    autoScrapeAttempted = false;
    lastJobSignature = null; // Force fresh data detection

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
    const result = await safeSendMessage({
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

// Initialize job count tracking for SPA navigation detection
lastJobCount = 0;

// Notify background script that content script is ready
safeSendMessage({ action: 'CONTENT_SCRIPT_READY' });

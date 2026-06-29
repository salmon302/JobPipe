// Purpose: Background service worker for JobPipe browser extension.
// Author: Seth Nenninger (Tencent: Hy3 preview Agent)
// Timestamp: 2026-05-13T02:30:00Z

// ==================== HELPER FUNCTIONS ====================

/**
 * Safely send a message from the background script.
 * Handles "Extension context invalidated" errors gracefully.
 * @param {Object} message - The message to send
 * @param {Function} [callback] - Optional callback for response
 * @returns {Promise|undefined} - Returns a promise if no callback, or undefined
 */
function safeSendMessage(message, callback) {
  try {
    if (chrome.runtime?.id) {
      if (callback) {
        chrome.runtime.sendMessage(message, (response) => {
          if (chrome.runtime.lastError) {
            // Receiving end doesn't exist - this is normal when popup is closed
            console.warn('JobPipe: No receiver for message:', message.action, '(' + chrome.runtime.lastError.message + ')');
            callback(undefined);
          } else {
            callback(response);
          }
        });
      } else {
        return chrome.runtime.sendMessage(message).catch((error) => {
          if (error.message?.includes('Extension context invalidated') ||
              error.message?.includes('Could not establish connection') ||
              error.message?.includes('Receiving end does not exist')) {
            // These are normal when popup is closed or content script isn't ready
            console.warn('JobPipe: Message not delivered (receiver not ready):', message.action);
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

// Store for tracking sent jobs (prevent duplicates in session)
// Note: This is session-based only. If server data is cleared,
// you may need to reload the extension or the page to clear this cache.
// Cache now tracks by job ID when available, falling back to platform:url
let sentJobsCache = new Set();

// Auto-scrape state
let autoScrapeEnabled = false;

// Track tabs that were created (potentially by "Open Selected Job" in the GUI).
// QDesktopServices.openUrl() from an external process opens a new tab but does
// NOT set openerTabId, so we track ALL new tab creations with a cleanup timeout.
let openedTabIds = new Set();

// Listen for all newly created tabs — catches tabs opened by
// "Open Selected Job" (QDesktopServices.openUrl) from an external process.
chrome.tabs.onCreated.addListener((tab) => {
  console.log('JobPipe: New tab created', tab.id, tab.url);
  openedTabIds.add(tab.id);
  // Clean up after 30 seconds to avoid scraping stale/reloaded tabs
  setTimeout(() => {
    openedTabIds.delete(tab.id);
  }, 30000);
});

// When a tab finishes loading, ONLY scrape if it was just created
// (tracked via openedTabIds). Do NOT scrape all tabs with job-like URLs.
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete' && openedTabIds.has(tabId)) {
    console.log('JobPipe: Tab finished loading, attempting scrape:', tabId, tab.url);
    openedTabIds.delete(tabId);

    // Try to scrape; if content script isn't there, inject it dynamically
    scrapeTabWithFallback(tabId);
  }
});

function scrapeTabWithFallback(tabId) {
  // Check if tab still exists before trying to message it
  chrome.tabs.get(tabId, (tab) => {
    if (chrome.runtime.lastError || !tab) {
      console.warn('JobPipe: Tab', tabId, 'no longer exists, skipping scrape');
      return;
    }

    // Try to send scrape message to existing content script
    chrome.tabs.sendMessage(tabId, { action: 'TRIGGER_SCRAPE' }, (response) => {
      if (chrome.runtime.lastError) {
        // Content script not found, inject it dynamically
        console.log('JobPipe: Content script not found in tab', tabId, '- injecting dynamically');
        chrome.scripting.executeScript({
          target: { tabId: tabId },
          files: ['content/content_script.js']
        }).then(() => {
          console.log('JobPipe: Content script injected into tab', tabId);
          // Wait for script to initialize, then send scrape message with retry
          setTimeout(() => {
            chrome.tabs.sendMessage(tabId, { action: 'TRIGGER_SCRAPE' }, (response) => {
              if (chrome.runtime.lastError) {
                console.log('JobPipe: Error after injection (retrying once):', chrome.runtime.lastError.message);
                // Retry once after another short delay
                setTimeout(() => {
                  chrome.tabs.sendMessage(tabId, { action: 'TRIGGER_SCRAPE' }, (response2) => {
                    if (chrome.runtime.lastError) {
                      console.log('JobPipe: Retry failed:', chrome.runtime.lastError.message);
                    } else {
                      console.log('JobPipe: Scrape triggered on retry', response2);
                    }
                  });
                }, 500);
              } else {
                console.log('JobPipe: Scrape triggered after injection', response);
              }
            });
          }, 1500); // Increased delay to ensure script is fully loaded
        }).catch((error) => {
          console.error('JobPipe: Failed to inject content script:', error);
        });
      } else {
        console.log('JobPipe: Triggered scrape on tab', tabId, response);
      }
    });
  });
}

// Single listener for all messages
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'CLEAR_CACHE') {
    sentJobsCache.clear();
    console.log('JobPipe: Cleared sent jobs cache');
    sendResponse({ success: true });
    return false;
  }

  if (request.action === 'SEND_TO_SERVER') {
    handleSendToServer(request.jobData, request.serverUrl, sendResponse);
    return true; // Keep message channel open for async response
  }

  if (request.action === 'SEND_BATCH_TO_SERVER') {
    handleSendBatchToServer(request.jobs, request.serverUrl, sendResponse);
    return true;
  }

  if (request.action === 'SEND_ENRICHED_TO_SERVER') {
    handleSendEnrichedToServer(request.jobData, request.serverUrl, sendResponse);
    return true;
  }

  if (request.action === 'CONTENT_SCRIPT_READY') {
    console.log('Content script ready on tab:', sender.tab?.id);
    sendResponse({ success: true });
    return false;
  }

  if (request.action === 'SET_AUTO_SCRAPE') {
    autoScrapeEnabled = request.enabled;
    console.log('JobPipe: Auto-scrape set to', autoScrapeEnabled);
    // Broadcast to all popup listeners
    safeSendMessage({
      action: 'SCRAPE_STATUS_UPDATE',
      status: autoScrapeEnabled ? 'Ready' : 'Disabled',
      jobsFound: 0,
      jobsSent: 0
    }).catch(() => {
      // No popup listening, ignore
    });
    sendResponse({ success: true });
    return false;
  }

  if (request.action === 'SCRAPE_STATUS_UPDATE') {
    // Forward status update to popup
    safeSendMessage(request).catch(() => {
      // No popup listening, ignore
    });
    sendResponse({ success: true });
    return false;
  }

  if (request.action === 'CREATE_DEV_NOTE') {
    // Save automated dev note to SNDEV/docs/
    try {
      const hostname = request.hostname.replace(/[^a-zA-Z0-9]/g, '-');
      const filename = `SNDEV/docs/auto-dev-note-${hostname}-${Date.now()}.md`;
      
      // Use chrome.downloads to save the file (if permissions allow)
      const blob = new Blob([request.content], { type: 'text/markdown' });
      const url = URL.createObjectURL(blob);
      
      chrome.downloads.download({
        url: url,
        filename: filename,
        saveAs: false,
      }, (downloadId) => {
        if (chrome.runtime.lastError) {
          console.log('JobPipe: Could not save dev note via downloads:', chrome.runtime.lastError.message);
          // Fallback: just log to console
          console.log('JobPipe: Dev note content for manual save:', request.content);
        } else {
          console.log('JobPipe: Dev note saved to', filename, 'downloadId:', downloadId);
        }
        URL.revokeObjectURL(url);
      });
      
      sendResponse({ success: true, filename: filename });
    } catch (error) {
      console.error('Error saving dev note:', error);
      sendResponse({ success: false, error: error.message });
    }
    return true;
  }
});

/**
 * Send single job to JobPipe server
 */
async function handleSendToServer(jobData, serverUrl, sendResponse) {
  try {
    // Check cache for duplicates - prefer job ID if available
    const jobSignature = jobData.id ? `${jobData.platform}:${jobData.id}` : `${jobData.platform}:${jobData.url}`;
    console.log('JobPipe: Checking cache for signature:', jobSignature);
    if (sentJobsCache.has(jobSignature)) {
      console.log('JobPipe: Job already in cache, skipping');
      sendResponse({
        success: false,
        error: 'This job was already sent in this session.',
      });
      return;
    }

    const payload = {
      platform: jobData.platform,
      id: jobData.id || null,
      title: jobData.title,
      company: jobData.company,
      url: jobData.url,
      description: jobData.description,
      summary: jobData.summary || null,
      requirements: jobData.requirements || null,
      location: jobData.location || null,
      county: jobData.county || null,
      compensation: jobData.compensation || null,
      workplace_type: jobData.workplace_type || null,
      employment_type: jobData.employment_type || null,
      department: jobData.department || null,
      team: jobData.team || null,
      views: jobData.views ?? null,
      saves: jobData.saves ?? null,
      applications: jobData.applications ?? null,
      posted_at: jobData.posted_at || null,
      posted_ago: jobData.posted_ago || null,
    };

    const response = await fetch(`${serverUrl}/ingest`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
      mode: 'cors',
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Server returned ${response.status}: ${errorText}`);
    }

    const result = await response.json();

    // Add to cache - prefer job ID if available
    const cacheSignature = jobData.id ? `${jobData.platform}:${jobData.id}` : `${jobData.platform}:${jobData.url}`;
    sentJobsCache.add(cacheSignature);
    console.log('JobPipe: Added to cache:', cacheSignature, '| Cache size:', sentJobsCache.size);

    // Show notification based on response status
    if (result.status === 'queued') {
      showToastNotification(`✓ ${result.ingested || 1} jobs queued! You can continue browsing.`);
    } else {
      showToastNotification(`✓ Job "${jobData.title}" sent to JobPipe!`);
    }

    // Broadcast status update to popup
    safeSendMessage({
      action: 'SCRAPE_STATUS_UPDATE',
      status: result.status || 'completed',
      jobsFound: 1,
      jobsSent: 1,
      scoringInProgress: result.scoring_in_progress || false,
      message: result.message || '',
    }).catch(() => {
      // No popup listening, ignore
    });

    sendResponse({
      success: true,
      count: 1,
      result: result,
    });
  } catch (error) {
    console.error('Error sending to server:', error);
    showToastNotification(`✗ Error: ${error.message}`, true);
    sendResponse({
      success: false,
      error: error.message,
    });
  }
}

/**
 * Send batch of jobs to JobPipe server
 */
async function handleSendBatchToServer(jobs, serverUrl, sendResponse) {
  try {
    console.log('JobPipe: handleSendBatchToServer called with', jobs.length, 'jobs');
    console.log('JobPipe: Server URL:', serverUrl);

    // Filter out duplicates — but allow enriched jobs through (they overwrite with fuller data)
    const uniqueJobs = [];
    const seen = new Set();

    for (const job of jobs) {
      const signature = `${job.platform}:${job.url}`;
      const isEnriched = job.enriched === true;
      if (!seen.has(signature) && (isEnriched || !sentJobsCache.has(signature))) {
        seen.add(signature);
        uniqueJobs.push(job);
      }
    }

    console.log('JobPipe: Unique jobs after filtering:', uniqueJobs.length);
    console.log('JobPipe: Sample job IDs:', uniqueJobs.slice(0, 3).map(j => j.id || 'no-id'));
    const enrichedCount = uniqueJobs.filter(j => j.enriched).length;
    if (enrichedCount > 0) {
      console.log(`JobPipe: ${enrichedCount} enriched jobs will overwrite existing records`);
    }

    if (uniqueJobs.length === 0) {
      sendResponse({
        success: false,
        error: 'No new jobs to send. Jobs may have been sent already in this browser session. Try clicking "Clear Cache" button below.',
      });
      return;
    }

    const payload = {
      jobs: uniqueJobs.map(job => {
        // Normalize URL by stripping query parameters for proper DB matching
        const normalizedUrl = (job.url || '').split('?')[0].split('#')[0];
        return {
          platform: job.platform,
          id: job.id || null,
          title: job.title,
          company: job.company,
          url: normalizedUrl,  // Use normalized URL for DB matching
          description: job.description || '',
          summary: job.summary || null,
          requirements: job.requirements || null,
          location: job.location || null,
          county: job.county || null,
          compensation: job.compensation || null,
          workplace_type: job.workplace_type || null,
          employment_type: job.employment_type || null,
          department: job.department || null,
          team: job.team || null,
          views: job.views ?? null,
          saves: job.saves ?? null,
          applications: job.applications ?? null,
          posted_at: job.posted_at || null,
          posted_ago: job.posted_ago || null,
        };
      }),
    };

    console.log('JobPipe: Sending payload with', payload.jobs.length, 'jobs to', serverUrl);

    const response = await fetch(`${serverUrl}/ingest`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
      mode: 'cors',
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Server returned ${response.status}: ${errorText}`);
    }

    const result = await response.json();

    // Add to cache - prefer job ID if available
    uniqueJobs.forEach(job => {
      const sig = job.id ? `${job.platform}:${job.id}` : `${job.platform}:${job.url}`;
      sentJobsCache.add(sig);
    });
    console.log('JobPipe: Added', uniqueJobs.length, 'jobs to cache | Cache size:', sentJobsCache.size);

    // Show notification based on response status
    if (result.status === 'queued') {
      showToastNotification(`✓ ${result.ingested || uniqueJobs.length} jobs queued! You can continue browsing.`);
    } else {
      showToastNotification(`✓ Sent ${uniqueJobs.length} jobs to JobPipe!`);
    }

    // Broadcast status update to popup
    safeSendMessage({
      action: 'SCRAPE_STATUS_UPDATE',
      status: result.status || 'completed',
      jobsFound: uniqueJobs.length,
      jobsSent: uniqueJobs.length,
      scoringInProgress: result.scoring_in_progress || false,
      message: result.message || '',
    }).catch(() => {
      // No popup listening, ignore
    });

    sendResponse({
      success: true,
      count: uniqueJobs.length,
      result: result,
    });
  } catch (error) {
    console.error('Error sending batch to server:', error);
    showToastNotification(`✗ Error: ${error.message}`, true);
    sendResponse({
      success: false,
      error: error.message,
    });
  }
}

/**
 * Send enriched detail page data to JobPipe server (bypasses cache).
 * This allows overwriting placeholder descriptions with full rich data.
 */
async function handleSendEnrichedToServer(jobData, serverUrl, sendResponse) {
  try {
    // Generate a stable job ID from the URL to match existing records
    const platform = jobData.platform || 'HiringCafe';
    const url = jobData.url || '';

    // Extract job ID from URL path if available
    let jobId = jobData.id;
    if (!jobId && url.includes('/viewjob/')) {
      const pathMatch = url.match(/\/viewjob\/([^/?]+)/);
      if (pathMatch) {
        jobId = `hiringcafe-${pathMatch[1]}`;
      }
    }

    console.log('JobPipe: Sending enriched data for', jobId || url);

    // Normalize URL by stripping query parameters for proper DB matching
    const normalizedUrl = (url || '').split('?')[0].split('#')[0];

    const payload = {
      platform: platform,
      id: jobId || null,
      title: jobData.title,
      company: jobData.company,
      url: normalizedUrl,  // Use normalized URL for DB matching
      description: jobData.description || '',
      summary: jobData.summary || null,
      requirements: jobData.requirements || null,
      location: jobData.location || null,
      compensation: jobData.compensation || null,
      workplace_type: jobData.workplace_type || null,
      employment_type: jobData.employment_type || null,
      views: jobData.views ?? null,
      saves: jobData.saves ?? null,
      applications: jobData.applications ?? null,
      posted_at: jobData.posted_at || null,
      posted_ago: jobData.posted_ago || null,
    };

    console.log('JobPipe: Enriched payload - platform:', platform, 'jobId:', jobId, 'company:', jobData.company, 'descLength:', (jobData.description || '').length);

    // Actually send the enriched data to the server!
    const response = await fetch(`${serverUrl}/ingest`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      mode: 'cors',
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Server returned ${response.status}: ${errorText}`);
    }

    const result = await response.json();

    // Log confirmation: show inserted/updated counts
    console.log('JobPipe: Enriched data sent successfully');
    console.log('JobPipe: Server response - inserted:', result.inserted, 'updated:', result.updated, 'run_id:', result.run_id);
    if (result.updated > 0) {
      console.log(`JobPipe: ✅ Enriched data updated existing job "${jobData.title}" in database`);
    } else if (result.inserted > 0) {
      console.log(`JobPipe: ✅ Enriched data inserted as new job "${jobData.title}" in database`);
    }

    showToastNotification(`✓ Enriched "${jobData.title}" with full description!`);

    // Broadcast status update to popup
    safeSendMessage({
      action: 'SCRAPE_STATUS_UPDATE',
      status: 'enriched',
      jobsFound: 1,
      jobsSent: 1,
      message: `${jobData.title} enriched`,
    }).catch(() => { /* No popup listening */ });

    sendResponse({
      success: true,
      count: 1,
      result: result,
    });
  } catch (error) {
    console.error('Error sending enriched data:', error);
    showToastNotification(`✗ Enrichment error: ${error.message}`, true);
    sendResponse({
      success: false,
      error: error.message,
    });
  }
}

/**
 * Display a toast notification
 * @param {string} message - Message to display
 * @param {boolean} isError - Whether this is an error notification
 */
function showToastNotification(message, isError = false) {
  // Create notification using Chrome notifications API
  chrome.notifications.create({
    type: 'basic',
    iconUrl: chrome.runtime.getURL('icons/icon48.png'),
    title: isError ? 'JobPipe Error' : 'JobPipe',
    message: message,
  });
}

// Clear cache when extension is reloaded/updated
chrome.runtime.onInstalled.addListener(() => {
  sentJobsCache.clear();
  console.log('JobPipe extension installed/updated');
});

// Optional: Clear cache periodically (every hour)
setInterval(() => {
  if (sentJobsCache.size > 1000) {
    sentJobsCache.clear();
    console.log('Cleared sent jobs cache (size threshold reached)');
  }
}, 60 * 60 * 1000);

// Extension loaded successfully
console.log('JobPipe: Background service worker loaded successfully');

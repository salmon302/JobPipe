// Purpose: Background service worker for JobPipe browser extension.
// Author: Seth Nenninger (Tencent: Hy3 preview Agent)
// Timestamp: 2026-05-13T02:30:00Z

// Store for tracking sent jobs (prevent duplicates in session)
// Note: This is session-based only. If server data is cleared,
// you may need to reload the extension or the page to clear this cache.
// Cache now tracks by job ID when available, falling back to platform:url
let sentJobsCache = new Set();

// Auto-scrape state
let autoScrapeEnabled = false;

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

  if (request.action === 'CONTENT_SCRIPT_READY') {
    console.log('Content script ready on tab:', sender.tab?.id);
    sendResponse({ success: true });
    return false;
  }

  if (request.action === 'SET_AUTO_SCRAPE') {
    autoScrapeEnabled = request.enabled;
    console.log('JobPipe: Auto-scrape set to', autoScrapeEnabled);
    // Broadcast to all popup listeners
    chrome.runtime.sendMessage({
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
    chrome.runtime.sendMessage(request).catch(() => {
      // No popup listening, ignore
    });
    sendResponse({ success: true });
    return false;
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
    chrome.runtime.sendMessage({
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

    // Filter out duplicates
    const uniqueJobs = [];
    const seen = new Set();

    for (const job of jobs) {
      const signature = `${job.platform}:${job.url}`;
      if (!seen.has(signature) && !sentJobsCache.has(signature)) {
        seen.add(signature);
        uniqueJobs.push(job);
      }
    }

    console.log('JobPipe: Unique jobs after filtering:', uniqueJobs.length);
    console.log('JobPipe: Sample job IDs:', uniqueJobs.slice(0, 3).map(j => j.id || 'no-id'));

    if (uniqueJobs.length === 0) {
      sendResponse({
        success: false,
        error: 'No new jobs to send. Jobs may have been sent already in this browser session. Try clicking "Clear Cache" button below.',
      });
      return;
    }

    const payload = {
      jobs: uniqueJobs.map(job => ({
        platform: job.platform,
        id: job.id || null,
        title: job.title,
        company: job.company,
        url: job.url,
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
      })),
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
    chrome.runtime.sendMessage({
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

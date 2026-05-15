// Purpose: Handle popup UI interactions and communicate with background service worker.
// Author: Seth Nenninger (Tencent: Hy3 preview Agent)
// Timestamp: 2026-05-12T18:45:00Z

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

const DEFAULT_SERVER_URL = '127.0.0.1:3838';

let serverUrl = DEFAULT_SERVER_URL;

// DOM elements
const serverStatusEl = document.getElementById('serverStatus');
const pageStatusEl = document.getElementById('pageStatus');
const captureBtn = document.getElementById('captureBtn');
const captureBatchBtn = document.getElementById('captureBatchBtn');
const serverUrlInput = document.getElementById('serverUrl');
const messageEl = document.getElementById('message');
const autoScrapeToggle = document.getElementById('autoScrapeToggle');
const scrapeStatusCard = document.getElementById('scrapeStatusCard');
const scrapeStatusEl = document.getElementById('scrapeStatus');
const jobsFoundEl = document.getElementById('jobsFound');
const jobsSentEl = document.getElementById('jobsSent');

// Initialize popup
document.addEventListener('DOMContentLoaded', async () => {
  await loadSettings();
  await checkServerHealth();
  await checkCurrentPage();
  setupEventListeners();
});

async function loadSettings() {
  const result = await chrome.storage.local.get(['serverUrl', 'autoScrapeEnabled']);
  serverUrl = result.serverUrl || DEFAULT_SERVER_URL;
  serverUrlInput.value = serverUrl;
  // Default to true if not set
  const autoScrapeEnabled = result.autoScrapeEnabled !== undefined ? result.autoScrapeEnabled : true;
  autoScrapeToggle.checked = autoScrapeEnabled;
  updateScrapeStatusVisibility(autoScrapeEnabled);
}

async function saveSettings() {
  serverUrl = serverUrlInput.value.trim() || DEFAULT_SERVER_URL;
  await chrome.storage.local.set({ serverUrl });
}

async function checkServerHealth() {
  try {
    const healthUrl = `http://${serverUrl}/health`;
    const response = await fetch(healthUrl, {
      method: 'GET',
      mode: 'cors',
    });

    if (response.ok) {
      serverStatusEl.textContent = 'Connected ✓';
      serverStatusEl.className = 'status-value status-connected';
      captureBtn.disabled = false;
      captureBatchBtn.disabled = false;
    } else {
      throw new Error('Server returned non-OK status');
    }
  } catch (error) {
    serverStatusEl.textContent = 'Disconnected ✗';
    serverStatusEl.className = 'status-value status-disconnected';
    captureBtn.disabled = true;
    captureBatchBtn.disabled = true;
  }
}

async function checkCurrentPage() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

    if (!tab || !tab.url) {
      pageStatusEl.textContent = 'No page detected';
      return;
    }

    const url = new URL(tab.url);
    const hostname = url.hostname.toLowerCase();

    if (hostname.includes('hiring.cafe')) {
      pageStatusEl.textContent = 'HiringCafe ✓';
    } else if (hostname.includes('linkedin.com')) {
      pageStatusEl.textContent = 'LinkedIn ✓';
    } else if (hostname.includes('builtin.com')) {
      pageStatusEl.textContent = 'Built In ✓';
    } else if (hostname.includes('wellfound.com')) {
      pageStatusEl.textContent = 'WellFound ✓';
    } else {
      pageStatusEl.textContent = 'Unsupported site';
    }
  } catch (error) {
    pageStatusEl.textContent = 'Error checking page';
    console.error('Error checking current page:', error);
  }
}

function setupEventListeners() {
  captureBtn.addEventListener('click', async () => {
    await saveSettings();
    await captureJob(false);
  });

  captureBatchBtn.addEventListener('click', async () => {
    await saveSettings();
    await captureJob(true);
  });

  serverUrlInput.addEventListener('change', async () => {
    await saveSettings();
    await checkServerHealth();
  });

  // Add clear cache button handler
  const clearCacheBtn = document.getElementById('clearCacheBtn');
  if (clearCacheBtn) {
    clearCacheBtn.addEventListener('click', async () => {
      safeSendMessage({ action: 'CLEAR_CACHE' }, (response) => {
        if (response && response.success) {
          showMessage('Cache cleared! You can now re-send jobs.', 'success');
        }
      });
    });
  }

  // Auto-scrape toggle handler
  autoScrapeToggle.addEventListener('change', async () => {
    const enabled = autoScrapeToggle.checked;
    await chrome.storage.local.set({ autoScrapeEnabled: enabled });
    updateScrapeStatusVisibility(enabled);

    // Notify content script of auto-scrape state change
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab && tab.id) {
      chrome.tabs.sendMessage(tab.id, {
        action: 'SET_AUTO_SCRAPE',
        enabled: enabled
      }).catch(() => {
        // Content script might not be ready, ignore error
      });
    }

    // Notify background worker
    safeSendMessage({
      action: 'SET_AUTO_SCRAPE',
      enabled: enabled
    });
  });

  // Listen for real-time status updates from background
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'SCRAPE_STATUS_UPDATE') {
      updateScrapeStatus(request);
    }
  });
}

async function captureJob(captureBatch) {
  try {
    showMessage('Capturing job data...', 'info');
    console.log('JobPipe popup: captureJob called, captureBatch=', captureBatch);

    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

    if (!tab || !tab.id) {
      throw new Error('No active tab found');
    }

    // Ensure serverUrl has proper format (don't double-add http://)
    const fullServerUrl = serverUrl.startsWith('http://') ? serverUrl : `http://${serverUrl}`;
    console.log('JobPipe popup: fullServerUrl=', fullServerUrl);

    // Check if content script is ready by sending a ping
    let contentScriptReady = false;
    try {
      const pingResponse = await chrome.tabs.sendMessage(tab.id, { action: 'PING' });
      contentScriptReady = pingResponse && pingResponse.success;
    } catch (pingError) {
      console.log('JobPipe popup: Ping failed:', pingError.message);
      contentScriptReady = false;
    }

    if (!contentScriptReady) {
      // Content script not ready - likely needs page reload
      const url = new URL(tab.url);
      const hostname = url.hostname.toLowerCase();
      
      const isSupportedSite = 
        hostname.includes('hiring.cafe') ||
        hostname.includes('linkedin.com') ||
        hostname.includes('builtin.com') ||
        hostname.includes('wellfound.com');
      
      if (!isSupportedSite) {
        throw new Error('This page is not a supported job board site.');
      }
      
      throw new Error('Content script not loaded. Please reload the page (F5) and try again.');
    }

    console.log('JobPipe popup: Sending CAPTURE_BATCH message, tab.id=', tab.id);
    // Send message to content script
    const response = await chrome.tabs.sendMessage(tab.id, {
      action: captureBatch ? 'CAPTURE_BATCH' : 'CAPTURE_JOB',
      serverUrl: fullServerUrl,
    });

    console.log('JobPipe popup: Response received:', response);

    if (response && response.success) {
      const count = response.count || 1;
      showMessage(
        `Successfully captured ${count} job${count > 1 ? 's' : ''}!`,
        'success'
      );
    } else {
      throw new Error(response?.error || 'Unknown error during capture');
    }
  } catch (error) {
    console.error('JobPipe popup: Capture error:', error);
    showMessage(`Error: ${error.message}`, 'error');
  }
}

function showMessage(text, type) {
  messageEl.textContent = text;
  messageEl.className = 'message';

  if (type === 'success') {
    messageEl.classList.add('message-success');
  } else if (type === 'error') {
    messageEl.classList.add('message-error');
  } else {
    messageEl.style.display = 'block';
  }

  // Auto-hide after 5 seconds
  setTimeout(() => {
    messageEl.style.display = 'none';
  }, 5000);
}

function updateScrapeStatusVisibility(visible) {
  scrapeStatusCard.style.display = visible ? 'block' : 'none';
}

function updateScrapeStatus(data) {
  if (data.status) {
    scrapeStatusEl.textContent = data.status;
    scrapeStatusEl.className = 'status-value';
    
    // Handle "queued" status specially
    if (data.status === 'queued') {
      scrapeStatusEl.classList.add('status-queued');
      // Show additional message
      if (data.message) {
        showMessage(data.message, 'info');
      }
    } else if (data.status === 'completed') {
      scrapeStatusEl.classList.add('status-connected');
    } else if (data.status === 'Scoring') {
      scrapeStatusEl.classList.add('status-scoring');
    }
    
    // Update jobs found/sent counters if provided
    if (data.jobsFound) {
      jobsFoundEl.textContent = data.jobsFound;
    }
    if (data.jobsSent) {
      jobsSentEl.textContent = data.jobsSent;
    }
    
    // Show/hide scoring progress indicator
    if (data.scoringInProgress) {
      showMessage('Scoring in progress in background...', 'info');
    }

    if (data.status === 'Scraping...') {
      scrapeStatusEl.classList.add('status-scraping');
    } else if (data.status === 'Complete') {
      scrapeStatusEl.classList.add('status-success');
    } else if (data.status === 'Error') {
      scrapeStatusEl.classList.add('status-error');
    }

    if (data.jobsFound !== undefined) {
      jobsFoundEl.textContent = data.jobsFound;
    }
    if (data.jobsSent !== undefined) {
      jobsSentEl.textContent = data.jobsSent;
    }
  }
}

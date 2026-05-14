# JobPipe Browser Extension

A Manifest V3 browser extension for capturing job listings from popular job boards and sending them to the JobPipe local server.

## Features

- **Multi-Platform Support:** Extracts jobs from HiringCafe, LinkedIn, Built In, and WellFound
- **Single & Batch Capture:** Capture individual job listings or all visible jobs on search pages
- **Local Server Integration:** Sends extracted data to JobPipe ingest server via HTTP POST
- **Visual Feedback:** Toast notifications confirm successful captures
- **Configurable:** Adjust server URL and settings via popup UI

## Installation

### For Development/Testing

1. **Generate Icons:**
   - Open `create_icons.html` in your browser
   - Download all three icon sizes (16px, 48px, 128px)
   - Save them to the `icons/` folder

2. **Load in Chrome/Edge:**
   - Open `chrome://extensions/` (or `edge://extensions/`)
   - Enable "Developer mode" (toggle in top-right)
   - Click "Load unpacked"
   - Select the `extension/` folder

3. **Configure Server:**
   - Click the extension icon to open popup
   - Verify server URL (default: `127.0.0.1:3838`)
   - Click "Capture Job Listing" to test

### For Production (Future)

Will be published to Chrome Web Store and Edge Add-ons marketplace.

## Usage

### Capturing a Single Job

1. Navigate to a job listing on a supported job board
2. Click the JobPipe extension icon
3. Click "📥 Capture Job Listing"
4. Receive confirmation notification
5. Job data is sent to local JobPipe server

### Capturing Multiple Jobs (Batch Mode)

1. Navigate to a search results page (e.g., HiringCafe search results)
2. Click the JobPipe extension icon
3. Click "📦 Capture All Visible"
4. All detected job cards will be sent to the server

### Supported Job Boards

| Platform | Single Capture | Batch Capture |
|----------|---------------|---------------|
| HiringCafe | ✅ | ✅ |
| LinkedIn | ✅ | ✅ |
| Built In | ✅ | ⚠️ Limited |
| WellFound | ✅ | ⚠️ Limited |
| Generic Sites | ✅ | ❌ |

## Payload Format

The extension sends JSON payloads to `http://<server>/ingest`:

**Single Job:**
```json
{
  "platform": "HiringCafe",
  "title": "Senior Python Developer",
  "company": "TechCorp Inc.",
  "url": "https://hiring.cafe/jobs/123",
  "description": "Full job description text..."
}
```

**Batch Jobs:**
```json
{
  "jobs": [
    {
      "platform": "HiringCafe",
      "title": "Job 1",
      "company": "Company A",
      "url": "https://...",
      "description": ""
    },
    ...
  ]
}
```

## File Structure

```
extension/
├── manifest.json              # Manifest V3 configuration
├── popup/
│   ├── popup.html            # Extension popup UI
│   └── popup.js              # Popup logic
├── content/
│   └── content_script.js     # DOM extraction script
├── background/
│   └── service_worker.js     # Background processing
├── utils/
│   └── extractors.js        # Platform-specific extractors
├── icons/                    # Extension icons (generate using create_icons.html)
├── create_icons.html         # Icon generator tool
├── test_page.html            # Test page for development
└── README.md                 # This file
```

## Troubleshooting

### Extension not capturing jobs

1. **Check Server Status:** Ensure JobPipe ingest server is running (`jobpipe ingest-server`)
2. **Check Page Type:** Make sure you're on a job listing page, not a search page (for single capture)
3. **Check Console:** Open DevTools (F12) and check for errors in Console tab
4. **Reload Extension:** Go to `chrome://extensions/` and click reload button

### "Could not extract job data" error

- The job board may have changed their DOM structure
- Try the "Generic" extraction by visiting any job page
- Check if the page has fully loaded before capturing
- Open an issue with the job board URL for investigation

### Server connection errors

- Verify server is running on correct port (default: 3838)
- Check server URL in popup settings
- Ensure no firewall is blocking localhost connections
- Check JobPipe server logs for incoming requests

## Development

### Modifying Extraction Logic

Edit `utils/extractors.js` to update selectors for specific job boards:

```javascript
function extractHiringCafe() {
  const titleEl = document.querySelector('YOUR-NEW-SELECTOR');
  // ...
}
```

After making changes, reload the extension in `chrome://extensions/`.

### Adding New Job Boards

1. Add the domain to `manifest.json` under `host_permissions`
2. Add the domain to `content_scripts` matches
3. Create a new extraction function in `utils/extractors.js`
4. Add the platform detection in `extractJobData()`

### Testing

Use the provided `test_page.html` for quick testing without visiting actual job boards.

## License

Part of the JobPipe project. See main project LICENSE file.

## Contributing

See main JobPipe project contributing guidelines.

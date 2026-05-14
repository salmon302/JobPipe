# 🌊 JobPipe Extension - Loading Instructions

## Quick Start (3 minutes)

### Step 1: Generate Icons

1. Open `icons/generate_simple.html` in your browser
2. Click each "Download" button (16x16, 48x48, 128x128)
3. Save the files to the `icons/` folder
   - `icon16.png`
   - `icon48.png`
   - `icon128.png`

### Step 2: Load Extension in Browser

**Chrome:**
1. Open `chrome://extensions/`
2. Toggle "Developer mode" (top-right corner)
3. Click "Load unpacked"
4. Select folder: `i:\Documents\GitHub\JobPipe\extension`

**Edge:**
1. Open `edge://extensions/`
2. Toggle "Developer mode" (left sidebar)
3. Click "Load unpacked"
4. Select folder: `i:\Documents\GitHub\JobPipe\extension`

### Step 3: Test the Extension

1. Start JobPipe server (if not running):
   ```bash
   cd i:\Documents\GitHub\JobPipe
   jobpipe ingest-server
   ```

2. Open the test page:
   - Open `extension/test_page.html` in your browser

3. Click the JobPipe extension icon (top-right toolbar)

4. Click "📥 Capture Job Listing"

5. You should see:
   - Success notification: "✓ Job 'Senior Python Developer' sent to JobPipe!"
   - Server logs showing received payload

## Troubleshooting

### "Icons missing" error when loading extension
- Make sure all three PNG files are in the `icons/` folder
- Check file names match exactly: `icon16.png`, `icon48.png`, `icon128.png`

### Extension icon not visible in toolbar
- Click the puzzle piece icon (Chrome) or extensions icon (Edge) to see all extensions
- Pin JobPipe to toolbar for easy access

### "Server not connected" in popup
- Ensure JobPipe ingest server is running on port 3838
- Check server URL in popup settings (default: `127.0.0.1:3838`)

### "Could not extract job data" error
- Make sure you're on a job listing page (not search results)
- Try refreshing the page
- Check browser console (F12) for errors

## Next Steps

After loading the extension:

1. **Test on real job boards:**
   - Visit [HiringCafe](https://hiring.cafe)
   - Find a job listing
   - Click JobPipe icon → "Capture Job Listing"

2. **Check the server:**
   - JobPipe server logs should show the ingested job
   - Database should have the new entry

3. **Batch capture:**
   - Visit a search results page
   - Click "📦 Capture All Visible"
   - Multiple jobs will be sent at once

## File Structure

```
extension/
├── manifest.json              ✅ Ready
├── popup/
│   ├── popup.html            ✅ Ready
│   └── popup.js              ✅ Ready
├── content/
│   └── content_script.js     ✅ Ready
├── background/
│   └── service_worker.js     ✅ Ready
├── utils/
│   └── extractors.js        ✅ Ready
├── icons/
│   ├── icon16.png           ⚠️ Generate using generate_simple.html
│   ├── icon48.png           ⚠️ Generate using generate_simple.html
│   ├── icon128.png          ⚠️ Generate using generate_simple.html
│   └── generate_simple.html ✅ Ready
├── test_page.html            ✅ Ready
├── generate_icons.ps1        ⚠️ Alternative (PowerShell - has bugs)
├── create_icons.html         ✅ Alternative icon generator
└── LOADING_INSTRUCTIONS.md  ✅ This file
```

## Support

If you encounter issues:
1. Check the browser console (F12) for error messages
2. Check JobPipe server logs
3. Verify all files are present in the extension folder
4. Try reloading the extension in `chrome://extensions/`

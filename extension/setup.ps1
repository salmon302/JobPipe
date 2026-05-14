# Purpose: Setup script for JobPipe browser extension
# Author: Seth Nenninger (Tencent: Hy3 preview Agent)
# Timestamp: 2026-05-12T19:15:00Z

Write-Host "🌊 JobPipe Browser Extension Setup" -ForegroundColor Cyan
Write-Host "====================================" -ForegroundColor Cyan
Write-Host ""

# Check if icons exist
$iconsExist = $true
$requiredIcons = @("icon16.png", "icon48.png", "icon128.png")

foreach ($icon in $requiredIcons) {
    $iconPath = Join-Path $PSScriptRoot "icons\$icon"
    if (-not (Test-Path $iconPath)) {
        Write-Host "❌ Missing: $icon" -ForegroundColor Red
        $iconsExist = $false
    } else {
        Write-Host "✅ Found: $icon" -ForegroundColor Green
    }
}

if (-not $iconsExist) {
    Write-Host ""
    Write-Host "⚠️  Icons are missing!" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "To generate icons:" -ForegroundColor Yellow
    Write-Host "  1. Open 'create_icons.html' in your browser" -ForegroundColor Yellow
    Write-Host "  2. Click the download buttons for each icon size" -ForegroundColor Yellow
    Write-Host "  3. Save the downloaded icons to the 'icons' folder" -ForegroundColor Yellow
    Write-Host ""
    $openHtml = Read-Host "Open create_icons.html now? (Y/N)"

    if ($openHtml -eq 'Y' -or $openHtml -eq 'y') {
        Start-Process (Join-Path $PSScriptRoot "create_icons.html")
    }
}

Write-Host ""
Write-Host "📦 Extension Structure:" -ForegroundColor Cyan
Write-Host "  - manifest.json" -ForegroundColor Gray
Write-Host "  - popup/" -ForegroundColor Gray
Write-Host "  - content/" -ForegroundColor Gray
Write-Host "  - background/" -ForegroundColor Gray
Write-Host "  - utils/" -ForegroundColor Gray
Write-Host ""

Write-Host "🚀 Next Steps:" -ForegroundColor Cyan
Write-Host "  1. Ensure all icons are in the 'icons' folder" -ForegroundColor Gray
Write-Host "  2. Open Chrome/Edge and navigate to:" -ForegroundColor Gray
Write-Host "     chrome://extensions/" -ForegroundColor Gray
Write-Host "     (or edge://extensions/)" -ForegroundColor Gray
Write-Host "  3. Enable 'Developer mode' (toggle in top-right)" -ForegroundColor Gray
Write-Host "  4. Click 'Load unpacked'" -ForegroundColor Gray
Write-Host "  5. Select this folder: $PSScriptRoot" -ForegroundColor Gray
Write-Host ""

# Test if JobPipe server is running
Write-Host "🔍 Checking JobPipe Server..." -ForegroundColor Cyan
try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:3838/health" -Method GET -TimeoutSec 2 -ErrorAction Stop
    if ($response.StatusCode -eq 200) {
        Write-Host "✅ JobPipe server is running on port 3838" -ForegroundColor Green
    }
} catch {
    Write-Host "⚠️  JobPipe server not detected on port 3838" -ForegroundColor Yellow
    Write-Host "   Start it with: jobpipe ingest-server" -ForegroundColor Gray
}

Write-Host ""
Write-Host "✨ Setup complete!" -ForegroundColor Green
Write-Host ""

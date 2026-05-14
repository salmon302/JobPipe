# Purpose: Generate JobPipe extension icons using .NET drawing
# Author: Seth Nenninger (Tencent: Hy3 preview Agent)
# Timestamp: 2026-05-12T19:20:00Z

Add-Type -AssemblyName System.Drawing

$iconSizes = @(16, 48, 128)
$outputDir = Join-Path $PSScriptRoot "icons"

# Create icons directory if it doesn't exist
if (-not (Test-Path $outputDir)) {
    New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
}

foreach ($size in $iconSizes) {
    $bitmap = New-Object System.Drawing.Bitmap $size, $size
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)

    # Enable high quality rendering
    $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $graphics.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAlias

    # Create gradient brush
    $rect = New-Object System.Drawing.Rectangle 0, 0, $size, $size
    $gradientBrush = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
        $rect,
        [System.Drawing.Color]::FromArgb(255, 102, 126, 234),  # #667eea
        [System.Drawing.Color]::FromArgb(255, 118, 75, 162),   # #764ba2
        45  # Angle
    )

    # Draw rounded rectangle background
    $path = New-Object System.Drawing.Drawing2D.GraphicsPath
    $radius = [int]($size * 0.15)
    $path.AddArc(0, 0, $radius, $radius, 180, 90)
    $path.AddArc($size - $radius, 0, $radius, $radius, 270, 90)
    $path.AddArc($size - $radius, $size - $radius, $radius, $radius, 0, 90)
    $path.AddArc(0, $size - $radius, $radius, $radius, 90, 90)
    $path.CloseFigure()
    $graphics.FillPath($gradientBrush, $path)

    # Draw "JP" text using simpler DrawString overload
    $fontSize = [int]($size * 0.4)
    $font = New-Object System.Drawing.Font("Arial", $fontSize, [System.Drawing.FontStyle]::Bold)
    $textBrush = [System.Drawing.Brushes]::White

    # Calculate position to center text
    $textSize = $graphics.MeasureString("JP", $font)
    $x = ($size - $textSize.Width) / 2
    $y = ($size - $textSize.Height) / 2

    $graphics.DrawString("JP", $font, $textBrush, $x, $y)

    # Save to file
    $outputPath = Join-Path $outputDir "icon$size.png"
    $bitmap.Save($outputPath, [System.Drawing.Imaging.ImageFormat]::Png)

    # Cleanup
    $font.Dispose()
    $format.Dispose()
    $textBrush.Dispose()
    $gradientBrush.Dispose()
    $path.Dispose()
    $graphics.Dispose()
    $bitmap.Dispose()

    Write-Host "✅ Created: icon$size.png" -ForegroundColor Green
}

Write-Host ""
Write-Host "🎉 All icons generated successfully!" -ForegroundColor Cyan
Write-Host "   Location: $outputDir" -ForegroundColor Gray

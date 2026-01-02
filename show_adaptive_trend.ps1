# Adaptive Trend Finder Analyse
# PowerShell-Skript

Write-Host "================================" -ForegroundColor Cyan
Write-Host "Adaptive Trend Finder Analyse" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""

# Virtual Environment aktivieren
& .\.venv\Scripts\Activate.ps1

# Python-Skript ausführen
python visualize_adaptive_trend.py

Write-Host ""
Write-Host "Analyse abgeschlossen!" -ForegroundColor Green

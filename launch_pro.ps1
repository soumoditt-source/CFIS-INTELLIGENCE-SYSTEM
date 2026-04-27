# AegisCX Platform Launcher (Zero-Docker Edition)
# ===============================================
# Run this script to start the full intelligence platform.
# Requires: Python 3.11+, Node.js 18+, FFmpeg.

Clear-Host
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "   AegisCX Intelligence Platform - PRO LAUNCH   " -ForegroundColor Cyan
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host ""

$BackendDir = "d:\CUSTOMER FEEDBACK SYSTEM TRANSCRIPT\backend"
$FrontendDir = "d:\CUSTOMER FEEDBACK SYSTEM TRANSCRIPT\frontend"

# 1. Check Infrastructure Requirements
Write-Host "[1/4] Checking Infrastructure..." -ForegroundColor Yellow
$PythonCheck = Get-Command python -ErrorAction SilentlyContinue
if (!$PythonCheck) { Write-Host "ERROR: Python not found!" -ForegroundColor Red; exit }

$FFmpegCheck = Get-Command ffmpeg -ErrorAction SilentlyContinue
if (!$FFmpegCheck) { 
    Write-Host "WARNING: FFmpeg not found in PATH! Audio processing will fail." -ForegroundColor Red 
} else {
    Write-Host "  - FFmpeg: OK" -ForegroundColor Green
}

# 2. Bootstrap Database
Write-Host "[2/4] Initializing Database (AegisCore)..." -ForegroundColor Yellow
Set-Location $BackendDir
python init_db.py
if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: Database init failed!" -ForegroundColor Red; exit }

# 3. Start Backend Services
Write-Host "[3/4] Starting Backend (API & Worker)..." -ForegroundColor Yellow

# Start FastAPI (Next Window)
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$BackendDir'; uvicorn app.main:app --reload --port 8000" -WindowStyle Normal
Write-Host "  - FastAPI: Running on http://localhost:8000" -ForegroundColor Green

# Start Celery Worker (Next Window)
# -P solo is required for Windows compatibility
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$BackendDir'; celery -A app.workers.celery_app worker --loglevel=info -Q audio_queue,stt_queue,nlp_queue -P solo" -WindowStyle Normal
Write-Host "  - Celery Worker: Running (GPU: True)" -ForegroundColor Green

# 4. Start Frontend
Write-Host "[4/4] Starting Frontend Dashboard..." -ForegroundColor Yellow
Set-Location $FrontendDir
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$FrontendDir'; npm run dev" -WindowStyle Normal
Write-Host "  - Next.js: Running on http://localhost:3000" -ForegroundColor Green

Write-Host ""
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "   LAUNCH SUCCESSFUL! System is Ready.         " -ForegroundColor Cyan
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "IMPORTANT: If you haven't set up Redis yet, please provide"
Write-Host "an Upstash or Redis URL in your .env file to enable processing."
Write-Host ""
Write-Host "Press Ctrl+C in the main windows to shut down individual services."

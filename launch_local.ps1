#!/usr/bin/env pwsh
# ================================================================
#  AegisCX CFIS - Local Stack Launcher
#  Backend  : http://localhost:8000/api/docs
#  Frontend : http://localhost:3000
#  Health   : http://localhost:8000/api/v1/health
# ================================================================

$ErrorActionPreference = "Continue"

function Banner { Write-Host "`n$('-' * 60)" -ForegroundColor DarkCyan }
function Info   { param($m) Write-Host "  >>  $m" -ForegroundColor Cyan   }
function OK     { param($m) Write-Host "  OK  $m" -ForegroundColor Green  }
function Warn   { param($m) Write-Host "  !!  $m" -ForegroundColor Yellow }
function Err    { param($m) Write-Host "  XX  $m" -ForegroundColor Red    }

Banner
Write-Host "  AegisCX CFIS - Customer Feedback Intelligence System" -ForegroundColor White
Write-Host "  Backend : http://localhost:8000/api/docs" -ForegroundColor DarkGray
Write-Host "  Frontend: http://localhost:3000"          -ForegroundColor DarkGray
Banner

# ----------------------------------------------------------------
# Paths
# ----------------------------------------------------------------
$Root     = $PSScriptRoot
$Backend  = Join-Path $Root  "backend"
$Frontend = Join-Path $Root  "frontend"
$Venv     = Join-Path $Backend "venv311"
$IsWin    = ($IsWindows -or ($env:OS -match "Windows"))
$Python   = if ($IsWin) { Join-Path $Venv "Scripts\python.exe" } else { Join-Path $Venv "bin/python" }
$Pip      = if ($IsWin) { Join-Path $Venv "Scripts\pip.exe"    } else { Join-Path $Venv "bin/pip"    }

# ----------------------------------------------------------------
# Python version check
# ----------------------------------------------------------------
Info "Checking Python 3.10+ ..."
$BasePy = "python"
try {
    $pyVer = (& python --version 2>&1) | Out-String
    if ($pyVer -match "3\.(10|11|12|13)") {
        OK "System Python: $($pyVer.Trim())"
    } else {
        Warn "python does not look like 3.10+; trying py -3 ..."
        $BasePy = "py"
    }
} catch {
    $BasePy = "py"
}

# ----------------------------------------------------------------
# Virtual environment
# ----------------------------------------------------------------
Info "Setting up virtual environment ..."
if (-not (Test-Path $Python)) {
    & $BasePy -m venv $Venv 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        OK "venv created at $Venv"
    } else {
        Err "Failed to create venv - check Python installation"
        exit 1
    }
} else {
    OK "venv already exists"
}

# ----------------------------------------------------------------
# Install Python dependencies
# ----------------------------------------------------------------
Info "Installing / verifying Python dependencies ..."
& $Python -m pip install --quiet --upgrade pip "setuptools<72.0.0" wheel 2>&1 | Out-Null

$reqFile    = Join-Path $Backend "requirements.txt"
$filterReqs = (Get-Content $reqFile) -notmatch "^\s*(openai-whisper|#)"
$tmpReq     = Join-Path $env:TEMP "cfis_reqs.txt"
$filterReqs | Set-Content $tmpReq
& $Pip install --quiet -r $tmpReq 2>&1 | Out-Null
& $Pip install --quiet aiosqlite structlog python-dotenv 2>&1 | Out-Null
OK "Python deps ready"

# ----------------------------------------------------------------
# Create data / log directories
# ----------------------------------------------------------------
Info "Preparing data directories ..."
$dataDirs = @(
    (Join-Path $Backend "data"),
    (Join-Path $Backend "data\raw"),
    (Join-Path $Backend "data\processed"),
    (Join-Path $Backend "data\chromadb"),
    (Join-Path $Backend "logs"),
    (Join-Path $Backend "models\hf_cache")
)
foreach ($d in $dataDirs) {
    if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
}
OK "Directories ready"

# ----------------------------------------------------------------
# Initialise SQLite database
# ----------------------------------------------------------------
Info "Initialising database ..."
Push-Location $Backend
try {
    & $Python init_db.py 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        OK "Database bootstrapped"
    } else {
        Warn "init_db.py returned non-zero - checking for existing DB ..."
        $dbPath = Join-Path $Backend "data\aegiscx.db"
        if (Test-Path $dbPath) {
            OK "Existing DB found - continuing"
        } else {
            Err "DB init failed and no DB file found"
            Pop-Location
            exit 1
        }
    }
} catch {
    Warn "init_db.py exception (may already be initialised)"
}
Pop-Location

# ----------------------------------------------------------------
# Check ffmpeg
# ----------------------------------------------------------------
Info "Checking ffmpeg ..."
try {
    $ffOut = (ffmpeg -version 2>&1 | Select-Object -First 1) | Out-String
    if ($ffOut -match "ffmpeg") {
        OK "ffmpeg found"
    } else {
        Warn "ffmpeg not detected on PATH - audio upload will fail"
        Warn "Install from: https://ffmpeg.org/download.html"
    }
} catch {
    Warn "ffmpeg not found - install it to enable audio processing"
}

# ----------------------------------------------------------------
# Free ports 8000 / 3000
# ----------------------------------------------------------------
Info "Freeing ports 8000 and 3000 ..."
function Stop-Port {
    param([int]$Port)
    $entries = netstat -ano 2>$null | Select-String ":$Port\s"
    foreach ($line in $entries) {
        $pid_ = ($line -split "\s+")[-1]
        if ($pid_ -match "^\d+$" -and [int]$pid_ -gt 4) {
            try { Stop-Process -Id ([int]$pid_) -Force -ErrorAction SilentlyContinue } catch {}
        }
    }
}
Stop-Port 8000
Stop-Port 3000
Start-Sleep -Seconds 1
OK "Ports cleared"

# ----------------------------------------------------------------
# Start FastAPI backend
# ----------------------------------------------------------------
Banner
Info "Starting FastAPI backend ..."
$backendJob = Start-Job -ScriptBlock {
    param($venvPy, $dir)
    Set-Location $dir
    & $venvPy -m uvicorn app.main:app `
        --host 0.0.0.0 `
        --port 8000 `
        --reload `
        --log-level info `
        --timeout-keep-alive 75 2>&1
} -ArgumentList $Python, $Backend

# Wait up to 30s for backend health-check
$backendReady = $false
$deadline     = (Get-Date).AddSeconds(30)
Info "Waiting for backend to be ready (up to 30s) ..."
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 800
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:8000/api/v1/health" `
                               -TimeoutSec 2 -ErrorAction Stop
        if ($r.StatusCode -eq 200) {
            $backendReady = $true
            break
        }
    } catch {}
    $out = Receive-Job $backendJob -ErrorAction SilentlyContinue
    if ($out) { $out | ForEach-Object { Write-Host "[API] $_" -ForegroundColor DarkCyan } }
}

if ($backendReady) {
    OK "Backend is UP  ->  http://localhost:8000/api/docs"
} else {
    Warn "Backend did not respond within 30s - check [API] logs above"
}

# ----------------------------------------------------------------
# Install and start Next.js frontend
# ----------------------------------------------------------------
Banner
Info "Installing frontend npm packages ..."
Push-Location $Frontend
try {
    & npm install --legacy-peer-deps 2>&1 | Out-Null
    OK "npm packages ready"
} catch {
    Warn "npm install encountered issues"
}
Pop-Location

Info "Starting Next.js frontend ..."
$frontendJob = Start-Job -ScriptBlock {
    param($dir)
    Set-Location $dir
    & npm run dev 2>&1
} -ArgumentList $Frontend

# ----------------------------------------------------------------
# Live log streaming
# ----------------------------------------------------------------
Banner
OK "Both services launched!"
Write-Host ""
Write-Host "  Backend  : http://localhost:8000/api/docs"      -ForegroundColor Green
Write-Host "  Frontend : http://localhost:3000"               -ForegroundColor Green
Write-Host "  Health   : http://localhost:8000/api/v1/health" -ForegroundColor Green
Write-Host ""
Write-Host "  Press Ctrl+C to stop all services." -ForegroundColor DarkGray
Write-Host ""

$restartCount = 0
try {
    while ($true) {
        $backOut  = Receive-Job $backendJob  -ErrorAction SilentlyContinue
        $frontOut = Receive-Job $frontendJob -ErrorAction SilentlyContinue

        if ($backOut)  { $backOut  | ForEach-Object { Write-Host "[API] $_" -ForegroundColor DarkCyan   } }
        if ($frontOut) { $frontOut | ForEach-Object { Write-Host "[UI]  $_" -ForegroundColor DarkYellow  } }

        if ($backendJob.State -eq "Failed" -and $restartCount -lt 5) {
            $restartCount++
            Warn "Backend crashed! Restarting (attempt $restartCount / 5) ..."
            Start-Sleep -Seconds 5
            $backendJob = Start-Job -ScriptBlock {
                param($venvPy, $dir)
                Set-Location $dir
                & $venvPy -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --log-level info 2>&1
            } -ArgumentList $Python, $Backend
        }

        Start-Sleep -Milliseconds 400
    }
} finally {
    Write-Host "`nShutting down..." -ForegroundColor Yellow
    Stop-Job   $backendJob,  $frontendJob -ErrorAction SilentlyContinue
    Remove-Job $backendJob,  $frontendJob -ErrorAction SilentlyContinue
    OK "All services stopped."
}

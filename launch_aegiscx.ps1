# AegisCX stable launcher
# Starts backend and frontend in the background, clears the target ports,
# and writes logs to the local logs folders for quick troubleshooting.

$ErrorActionPreference = "Stop"

function Info($message) {
    Write-Host ">> $message" -ForegroundColor Cyan
}

function OK($message) {
    Write-Host "OK $message" -ForegroundColor Green
}

function Warn($message) {
    Write-Host "!! $message" -ForegroundColor Yellow
}

function Stop-PortProcess {
    param([int]$Port)

    $lines = netstat -ano 2>$null | Select-String ":$Port\s"
    foreach ($line in $lines) {
        $parts = ($line -split "\s+") | Where-Object { $_ }
        $processId = $parts[-1]
        if ($processId -match "^\d+$" -and [int]$processId -gt 4) {
            try {
                Stop-Process -Id ([int]$processId) -Force -ErrorAction Stop
                Start-Sleep -Milliseconds 400
            } catch {
                Warn "Could not stop PID $processId on port $Port"
            }
        }
    }
}

function Wait-ForUrl {
    param(
        [string]$Url,
        [int]$Attempts = 40,
        [int]$DelayMs = 1500
    )

    for ($i = 0; $i -lt $Attempts; $i++) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                return $true
            }
        } catch {
        }

        Start-Sleep -Milliseconds $DelayMs
    }

    return $false
}

$root = $PSScriptRoot
$backendPath = Join-Path $root "backend"
$frontendPath = Join-Path $root "frontend"
$pythonPath = Join-Path $backendPath "venv311\Scripts\python.exe"
$logDir = Join-Path $root "logs"
$backendOut = Join-Path $logDir "backend-live.out.log"
$backendErr = Join-Path $logDir "backend-live.err.log"
$frontendOut = Join-Path $logDir "frontend-live.out.log"
$frontendErr = Join-Path $logDir "frontend-live.err.log"
$setupScript = Join-Path $root "setup_aegiscx.ps1"

if (-not (Test-Path $pythonPath)) {
    if (Test-Path $setupScript) {
        Warn "Backend runtime is missing. Running setup_aegiscx.ps1 first."
        & powershell -ExecutionPolicy Bypass -File $setupScript
    }
}

if (-not (Test-Path $pythonPath)) {
    throw "Backend Python runtime not found at $pythonPath after setup."
}

if (-not (Test-Path (Join-Path $frontendPath "node_modules"))) {
    if (Test-Path $setupScript) {
        Warn "Frontend dependencies are missing. Running setup_aegiscx.ps1 first."
        & powershell -ExecutionPolicy Bypass -File $setupScript
    }
}

if (-not (Test-Path (Join-Path $frontendPath "node_modules"))) {
    throw "Frontend dependencies are missing after setup."
}

if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

Info "Clearing ports 8000 and 3000"
Stop-PortProcess -Port 8000
Stop-PortProcess -Port 3000

Info "Starting backend on http://127.0.0.1:8000"
Start-Process `
    -FilePath $pythonPath `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000") `
    -WorkingDirectory $backendPath `
    -WindowStyle Hidden `
    -RedirectStandardOutput $backendOut `
    -RedirectStandardError $backendErr | Out-Null

Info "Starting frontend on http://127.0.0.1:3000"
Start-Process `
    -FilePath "powershell.exe" `
    -ArgumentList @(
        "-NoProfile",
        "-Command",
        "Set-Location '$frontendPath'; `$env:NODE_OPTIONS='--max-old-space-size=4096'; npm run dev"
    ) `
    -WorkingDirectory $frontendPath `
    -WindowStyle Hidden `
    -RedirectStandardOutput $frontendOut `
    -RedirectStandardError $frontendErr | Out-Null

$backendReady = Wait-ForUrl -Url "http://127.0.0.1:8000/api/v1/health" -Attempts 40 -DelayMs 1500
$frontendReady = Wait-ForUrl -Url "http://127.0.0.1:3000" -Attempts 60 -DelayMs 1500

if ($backendReady) {
    OK "Backend is live at http://127.0.0.1:8000/api/docs"
} else {
    Warn "Backend did not answer in time. Check $backendErr"
}

if ($frontendReady) {
    OK "Frontend is live at http://127.0.0.1:3000"
} else {
    Warn "Frontend did not answer in time. Check $frontendErr"
}

Write-Host ""
Write-Host "Backend logs : $backendOut" -ForegroundColor DarkGray
Write-Host "Frontend logs: $frontendOut" -ForegroundColor DarkGray

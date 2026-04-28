# AegisCX bootstrap script
# Prepares a clean local machine by creating the backend virtualenv,
# installing Python and Node dependencies, copying safe env defaults,
# and initializing the local SQLite database.

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

function Find-Python {
    $candidates = @("python", "py")

    foreach ($candidate in $candidates) {
        try {
            $version = (& $candidate --version 2>&1 | Out-String).Trim()
            if ($version -match "Python 3\.(10|11|12|13)") {
                return $candidate
            }
        } catch {
        }
    }

    throw "Python 3.10+ was not found on PATH."
}

$root = $PSScriptRoot
$backendPath = Join-Path $root "backend"
$frontendPath = Join-Path $root "frontend"
$venvPath = Join-Path $backendPath "venv311"
$pythonPath = Join-Path $venvPath "Scripts\python.exe"
$pipPath = Join-Path $venvPath "Scripts\pip.exe"
$backendEnv = Join-Path $backendPath ".env"
$backendEnvExample = Join-Path $backendPath ".env.example"
$frontendEnvLocal = Join-Path $frontendPath ".env.local"
$frontendEnvExample = Join-Path $frontendPath ".env.example"

if (-not (Test-Path $pythonPath)) {
    Info "Checking for Python 3.10+"
    $basePython = Find-Python
    OK "Using $basePython"

    Info "Creating backend virtual environment"
    & $basePython -m venv $venvPath
    OK "Virtual environment created at $venvPath"
} else {
    OK "Backend virtual environment already exists"
}

Info "Upgrading backend packaging tools"
& $pythonPath -m pip install --upgrade pip "setuptools<82" wheel

Info "Installing backend dependencies"
& $pipPath install -r (Join-Path $backendPath "requirements.txt")
OK "Backend dependencies installed"

if (-not (Test-Path $backendEnv) -and (Test-Path $backendEnvExample)) {
    Copy-Item $backendEnvExample $backendEnv
    OK "Created backend/.env from the example template"
} elseif (Test-Path $backendEnv) {
    OK "backend/.env already exists"
}

if (-not (Test-Path $frontendEnvLocal) -and (Test-Path $frontendEnvExample)) {
    Copy-Item $frontendEnvExample $frontendEnvLocal
    OK "Created frontend/.env.local from the example template"
} elseif (Test-Path $frontendEnvLocal) {
    OK "frontend/.env.local already exists"
}

Info "Ensuring local data and log folders exist"
$dirs = @(
    (Join-Path $backendPath "data"),
    (Join-Path $backendPath "data\raw"),
    (Join-Path $backendPath "data\processed"),
    (Join-Path $backendPath "data\chromadb"),
    (Join-Path $backendPath "logs"),
    (Join-Path $root "logs")
)
foreach ($dir in $dirs) {
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
}
OK "Local directories are ready"

Info "Installing frontend dependencies"
Push-Location $frontendPath
try {
    & npm install --no-audit --no-fund
    OK "Frontend dependencies installed"
} finally {
    Pop-Location
}

Info "Initializing the local database"
Push-Location $backendPath
try {
    & $pythonPath init_db.py
    OK "Local database initialized"
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "Next step:" -ForegroundColor White
Write-Host "powershell -ExecutionPolicy Bypass -File .\launch_aegiscx.ps1" -ForegroundColor Green

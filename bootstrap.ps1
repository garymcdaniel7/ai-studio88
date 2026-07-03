# =============================================================================
# AI Studio - Developer Bootstrap Script (Windows / PowerShell)
# =============================================================================
# Run as Administrator in PowerShell:
#   Set-ExecutionPolicy Bypass -Scope Process -Force
#   .\bootstrap.ps1
# =============================================================================

#Requires -Version 5.1
$ErrorActionPreference = "Stop"

# ── Colours ──────────────────────────────────────────────────────────────────
function Write-Section  { param($msg) Write-Host "`n══════════════════════════════════════════" -ForegroundColor Cyan; Write-Host "  $msg" -ForegroundColor Cyan -BackgroundColor Black; Write-Host "══════════════════════════════════════════" -ForegroundColor Cyan }
function Write-Info     { param($msg) Write-Host "[INFO]  $msg" -ForegroundColor Blue }
function Write-OK       { param($msg) Write-Host "[OK]    $msg" -ForegroundColor Green }
function Write-Warn     { param($msg) Write-Host "[WARN]  $msg" -ForegroundColor Yellow }
function Write-Err      { param($msg) Write-Host "[ERROR] $msg" -ForegroundColor Red }

function Cmd-Exists { param($cmd) return [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

$Errors = @()

# =============================================================================
Write-Section "1 / 7  Chocolatey (Windows package manager)"
# =============================================================================
if (Cmd-Exists "choco") {
    Write-OK "Chocolatey already installed: $(choco --version)"
} else {
    Write-Info "Installing Chocolatey..."
    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
    Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
    Write-OK "Chocolatey installed."
}

function Choco-Install {
    param([string]$pkg, [string]$cmd = $pkg)
    if (Cmd-Exists $cmd) {
        Write-OK "$cmd already installed."
    } else {
        Write-Info "Installing $pkg..."
        choco install $pkg -y --no-progress
        Write-OK "$pkg installed."
    }
}

# =============================================================================
Write-Section "2 / 7  Core CLI Tools"
# =============================================================================
Choco-Install "git"         "git"
Choco-Install "gh"          "gh"
Choco-Install "git-lfs"     "git-lfs"
Choco-Install "ffmpeg"      "ffmpeg"
Choco-Install "imagemagick" "magick"

# Initialise Git LFS
git lfs install --skip-repo 2>$null
Write-OK "Git LFS initialised."

# =============================================================================
Write-Section "3 / 7  Docker Desktop"
# =============================================================================
if (Cmd-Exists "docker") {
    Write-OK "Docker already installed: $(docker --version)"
} else {
    Write-Info "Installing Docker Desktop..."
    choco install docker-desktop -y --no-progress
    Write-Warn "Docker Desktop installed. Please launch it manually and enable WSL2 integration, then re-run this script."
    $Errors += "Docker Desktop needs manual launch"
}

# =============================================================================
Write-Section "4 / 7  Node.js LTS + npm"
# =============================================================================
if (Cmd-Exists "node") {
    Write-OK "Node.js already installed: $(node --version)"
} else {
    Write-Info "Installing Node.js LTS..."
    choco install nodejs-lts -y --no-progress
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
    Write-OK "Node.js installed."
}

# =============================================================================
Write-Section "5 / 7  Python 3.12 + uv"
# =============================================================================
if (Cmd-Exists "python") {
    $pyVer = python --version 2>&1
    Write-OK "Python already installed: $pyVer"
} else {
    Write-Info "Installing Python 3.12..."
    choco install python312 -y --no-progress
    Write-OK "Python 3.12 installed."
}

if (Cmd-Exists "uv") {
    Write-OK "uv already installed: $(uv --version)"
} else {
    Write-Info "Installing uv..."
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = "$env:USERPROFILE\.local\bin;" + $env:Path
    Write-OK "uv installed."
}

# =============================================================================
Write-Section "6 / 7  Supabase CLI"
# =============================================================================
if (Cmd-Exists "supabase") {
    Write-OK "Supabase CLI already installed: $(supabase --version)"
} else {
    Write-Info "Installing Supabase CLI via Scoop..."
    if (-not (Cmd-Exists "scoop")) {
        Invoke-RestMethod -Uri https://get.scoop.sh | Invoke-Expression
    }
    scoop bucket add supabase https://github.com/supabase/scoop-bucket.git
    scoop install supabase
    Write-OK "Supabase CLI installed."
}

# =============================================================================
Write-Section "7 / 7  Python Environment + Dependencies"
# =============================================================================
$BackendDir = Join-Path $PSScriptRoot "backend"
$Pyproject  = Join-Path $BackendDir "pyproject.toml"

if (Test-Path $Pyproject) {
    Write-Info "Creating virtual environment..."
    uv venv "$BackendDir\.venv" --python python3.12
    Write-OK "Virtual environment created at backend\.venv"

    Write-Info "Installing Python dependencies..."
    Push-Location $BackendDir
    uv pip install -e ".[dev]"
    Pop-Location
    Write-OK "Dependencies installed."
} else {
    Write-Warn "backend/pyproject.toml not found - skipping Python deps."
}

# ── .env setup ───────────────────────────────────────────────────────────────
$EnvFile    = Join-Path $PSScriptRoot ".env"
$EnvExample = Join-Path $PSScriptRoot ".env.example"
if (-not (Test-Path $EnvFile)) {
    if (Test-Path $EnvExample) {
        Copy-Item $EnvExample $EnvFile
        Write-Warn ".env created from .env.example — fill in your secrets before running the app."
    }
} else {
    Write-OK ".env already exists."
}

# =============================================================================
Write-Section "Bootstrap Summary"
# =============================================================================
$tools = @("git","gh","docker","node","npm","python","uv","supabase","ffmpeg","magick")
foreach ($t in $tools) {
    if (Cmd-Exists $t) { Write-Host "  [+] $t" -ForegroundColor Green }
    else               { Write-Host "  [-] $t (not in PATH)" -ForegroundColor Red; $Errors += "$t missing" }
}

Write-Host ""
if ($Errors.Count -eq 0) {
    Write-OK "Bootstrap completed successfully!"
    Write-Host ""
    Write-Info "Next steps:"
    Write-Host "  1. Fill in .env with your credentials"
    Write-Host "  2. Run: cd backend; .venv\Scripts\activate"
    Write-Host "  3. Run: uvicorn app.main:app --reload"
    Write-Host "  4. Visit: http://localhost:8000/docs"
} else {
    Write-Warn "Bootstrap completed with warnings:"
    foreach ($e in $Errors) { Write-Host "  ! $e" -ForegroundColor Yellow }
}

Write-Host ""
Write-Info "Run .\verify_environment.ps1 to validate your setup at any time."

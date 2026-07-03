# =============================================================================
# AI Studio - Environment Verification Script (Windows / PowerShell)
# =============================================================================
# Usage: .\verify_environment.ps1
# Returns exit code 0 if all checks pass, 1 if any fail.
# =============================================================================

#Requires -Version 5.1
$ErrorActionPreference = "Continue"

function Write-Section { param($m) Write-Host "`n── $m ──" -ForegroundColor Cyan }
function Write-Pass    { param($m) Write-Host "[PASS]  $m" -ForegroundColor Green; $script:PassCount++ }
function Write-Fail    { param($m) Write-Host "[FAIL]  $m" -ForegroundColor Red;   $script:FailCount++ }
function Write-Warn    { param($m) Write-Host "[WARN]  $m" -ForegroundColor Yellow; $script:WarnCount++ }
function Write-Info    { param($m) Write-Host "[INFO]  $m" -ForegroundColor Blue }

$script:PassCount = 0
$script:FailCount = 0
$script:WarnCount = 0
$RootDir = $PSScriptRoot

function Cmd-Exists { param($cmd) return [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

function Check-Tool {
    param([string]$Name, [string]$Cmd, [string]$MinVer = "")
    if (Cmd-Exists $Cmd) {
        $ver = (& $Cmd --version 2>&1 | Select-String -Pattern '\d+\.\d+[\.\d]*' | ForEach-Object { $_.Matches[0].Value } | Select-Object -First 1)
        if ($MinVer -and $ver) {
            $curr = [version]($ver -replace '[^\d\.]','')
            $req  = [version]$MinVer
            if ($curr -lt $req) { Write-Fail "$Name`: $ver (need >= $MinVer)" }
            else                { Write-Pass "$Name`: $ver" }
        } else { Write-Pass "$Name`: $($ver ?? 'installed')" }
    } else { Write-Fail "$Name`: NOT INSTALLED" }
}

# =============================================================================
Write-Section "Software Versions"
# =============================================================================
Check-Tool "Git"          "git"        "2.35.0"
Check-Tool "GitHub CLI"   "gh"         "2.0.0"
Check-Tool "Git LFS"      "git-lfs"    "3.0.0"
Check-Tool "Docker"       "docker"     "24.0.0"
Check-Tool "Node.js"      "node"       "20.0.0"
Check-Tool "npm"          "npm"        "9.0.0"
Check-Tool "Python"       "python"     "3.12.0"
Check-Tool "uv"           "uv"         "0.4.0"
Check-Tool "Supabase CLI" "supabase"   "1.0.0"
Check-Tool "ffmpeg"       "ffmpeg"     "5.0.0"
Check-Tool "ImageMagick"  "magick"     "7.0.0"
Check-Tool "Ruff"         "ruff"       "0.3.0"
Check-Tool "Black"        "black"      "24.0.0"
Check-Tool "pytest"       "pytest"     "7.0.0"
Check-Tool "pre-commit"   "pre-commit" "3.0.0"

# =============================================================================
Write-Section "Git Repository"
# =============================================================================
$gitResult = git -C $RootDir rev-parse --is-inside-work-tree 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Pass "Git repository initialised."
    $branch = git -C $RootDir branch --show-current 2>&1
    Write-Pass "Current branch: $branch"
    $remote = git -C $RootDir remote get-url origin 2>&1
    if ($LASTEXITCODE -eq 0) { Write-Pass "Remote origin: $remote" }
    else                     { Write-Warn "No remote origin configured." }
} else { Write-Fail "Not a git repository." }

# =============================================================================
Write-Section "GitHub Authentication"
# =============================================================================
if (Cmd-Exists "gh") {
    $authResult = gh auth status 2>&1
    if ($LASTEXITCODE -eq 0) { Write-Pass "GitHub CLI authenticated." }
    else                      { Write-Warn "GitHub CLI not authenticated. Run: gh auth login" }
} else { Write-Fail "gh CLI not installed." }

# =============================================================================
Write-Section "Docker"
# =============================================================================
if (Cmd-Exists "docker") {
    $dockerInfo = docker info 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Pass "Docker daemon running."
        $composeVer = docker compose version --short 2>&1
        if ($LASTEXITCODE -eq 0) { Write-Pass "Docker Compose: $composeVer" }
        else                      { Write-Warn "Docker Compose plugin not found." }
    } else { Write-Fail "Docker installed but daemon is NOT running. Launch Docker Desktop." }
} else { Write-Fail "Docker not installed." }

# =============================================================================
Write-Section "Python Virtual Environment"
# =============================================================================
$VenvPath = Join-Path $RootDir "backend\.venv"
if (Test-Path $VenvPath) {
    Write-Pass "Virtual environment exists at backend\.venv"
    $PyBin = Join-Path $VenvPath "Scripts\python.exe"
    if (Test-Path $PyBin) {
        $pyver = & $PyBin --version 2>&1
        Write-Pass "Python in venv: $pyver"
        $fapiCheck = & $PyBin -c "import fastapi; print(fastapi.__version__)" 2>&1
        if ($LASTEXITCODE -eq 0) { Write-Pass "FastAPI: $fapiCheck" }
        else                      { Write-Warn "FastAPI not installed in venv." }
    }
} else { Write-Warn "Virtual environment not found. Run: .\bootstrap.ps1" }

# =============================================================================
Write-Section "Environment Variables"
# =============================================================================
$EnvFile = Join-Path $RootDir ".env"
if (Test-Path $EnvFile) {
    Write-Pass ".env file exists."
    $requiredVars = @(
        "SUPABASE_URL","SUPABASE_ANON_KEY","SUPABASE_SERVICE_ROLE_KEY",
        "DATABASE_URL","SECRET_KEY","B2_KEY_ID","B2_APPLICATION_KEY","B2_BUCKET_NAME"
    )
    $envContent = Get-Content $EnvFile | Where-Object { $_ -notmatch "^#" -and $_ -match "=" }
    $envDict = @{}
    foreach ($line in $envContent) {
        $parts = $line -split "=", 2
        if ($parts.Count -eq 2) { $envDict[$parts[0].Trim()] = $parts[1].Trim() }
    }
    foreach ($var in $requiredVars) {
        $val = $envDict[$var]
        if ([string]::IsNullOrEmpty($val) -or $val -match "^(your-|change_me)") {
            Write-Warn "$var is not set or is a placeholder."
        } else { Write-Pass "$var is set." }
    }
} else { Write-Fail ".env file missing. Copy .env.example to .env and fill in values." }

# =============================================================================
Write-Section "API Health Check"
# =============================================================================
try {
    $resp = Invoke-WebRequest -Uri "http://localhost:8000/health" -TimeoutSec 3 -ErrorAction Stop
    if ($resp.StatusCode -eq 200) { Write-Pass "API health check: http://localhost:8000/health OK" }
} catch { Write-Info "API not reachable at http://localhost:8000 (start with: uvicorn app.main:app --reload)" }

# =============================================================================
Write-Section "Result"
# =============================================================================
Write-Host ""
if ($script:FailCount -eq 0 -and $script:WarnCount -eq 0) {
    Write-Host "All checks passed. Environment is fully configured." -ForegroundColor Green
    exit 0
} elseif ($script:FailCount -eq 0) {
    Write-Host "$($script:WarnCount) warning(s). Environment mostly ready." -ForegroundColor Yellow
    exit 0
} else {
    Write-Host "$($script:FailCount) failure(s), $($script:WarnCount) warning(s). Fix failures before developing." -ForegroundColor Red
    exit 1
}

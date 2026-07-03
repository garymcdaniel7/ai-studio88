#!/usr/bin/env bash
# =============================================================================
# AI Studio - Environment Verification Script (macOS / Linux)
# =============================================================================
# Usage: ./verify_environment.sh
# Returns exit code 0 if all checks pass, 1 if any fail.
# =============================================================================

set -uo pipefail

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${BLUE}[INFO]${RESET}  $*"; }
pass()    { echo -e "${GREEN}[PASS]${RESET}  $*"; }
fail()    { echo -e "${RED}[FAIL]${RESET}  $*"; FAIL_COUNT=$((FAIL_COUNT+1)); }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; WARN_COUNT=$((WARN_COUNT+1)); }
section() { echo -e "\n${CYAN}${BOLD}── $* ──${RESET}"; }

FAIL_COUNT=0
WARN_COUNT=0
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cmd_exists() { command -v "$1" &>/dev/null; }
version_gte() { [ "$(printf '%s\n' "$2" "$1" | sort -V | head -n1)" = "$2" ]; }

# =============================================================================
section "Software Versions"
# =============================================================================

check_tool() {
  local name="$1" cmd="$2" min_ver="$3" ver_flag="${4:---version}"
  if cmd_exists "$cmd"; then
    local ver
    ver=$("$cmd" $ver_flag 2>&1 | head -1 | grep -oE '[0-9]+\.[0-9]+(\.[0-9]+)?' | head -1)
    if [ -n "$min_ver" ] && ! version_gte "${ver:-0}" "$min_ver"; then
      fail "$name: $ver (need >= $min_ver)"
    else
      pass "$name: ${ver:-installed}"
    fi
  else
    fail "$name: NOT INSTALLED"
  fi
}

check_tool "Homebrew"     brew       "4.0.0"
check_tool "Git"          git        "2.35.0"
check_tool "GitHub CLI"   gh         "2.0.0"
check_tool "Git LFS"      git-lfs    "3.0.0"
check_tool "Docker"       docker     "24.0.0"
check_tool "Node.js"      node       "20.0.0"
check_tool "npm"          npm        "9.0.0"
check_tool "Python 3.12"  python3.12 "3.12.0"
check_tool "uv"           uv         "0.4.0"
check_tool "Supabase CLI" supabase   "1.0.0"
check_tool "ffmpeg"       ffmpeg     "5.0.0"
check_tool "ImageMagick"  convert    "7.0.0"
check_tool "Ruff"         ruff       "0.3.0"
check_tool "Black"        black      "24.0.0"
check_tool "pytest"       pytest     "7.0.0"
check_tool "pre-commit"   pre-commit "3.0.0"

# =============================================================================
section "Git Repository"
# =============================================================================
if git -C "$ROOT_DIR" rev-parse --is-inside-work-tree &>/dev/null; then
  pass "Git repository initialised."
  BRANCH=$(git -C "$ROOT_DIR" branch --show-current 2>/dev/null)
  pass "Current branch: $BRANCH"

  REMOTE=$(git -C "$ROOT_DIR" remote get-url origin 2>/dev/null || echo "")
  if [ -n "$REMOTE" ]; then
    pass "Remote origin: $REMOTE"
  else
    warn "No remote origin configured. Run: git remote add origin <url>"
  fi

  STATUS=$(git -C "$ROOT_DIR" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
  if [ "$STATUS" -gt 0 ]; then
    warn "Working tree has $STATUS uncommitted change(s)."
  else
    pass "Working tree clean."
  fi
else
  fail "Not a git repository."
fi

# =============================================================================
section "GitHub Authentication"
# =============================================================================
if cmd_exists gh; then
  if gh auth status &>/dev/null; then
    pass "GitHub CLI authenticated."
    gh auth status 2>&1 | grep "Logged in" | head -1 | while read -r line; do
      info "  $line"
    done
  else
    warn "GitHub CLI not authenticated. Run: gh auth login"
  fi
else
  fail "gh CLI not installed."
fi

# =============================================================================
section "Docker"
# =============================================================================
if cmd_exists docker; then
  if docker info &>/dev/null; then
    pass "Docker daemon running."
    if cmd_exists docker && docker compose version &>/dev/null; then
      pass "Docker Compose: $(docker compose version --short 2>/dev/null)"
    else
      warn "Docker Compose plugin not found."
    fi
  else
    fail "Docker installed but daemon is NOT running. Launch Docker Desktop."
  fi
else
  fail "Docker not installed."
fi

# =============================================================================
section "Python Environment"
# =============================================================================
VENV="$ROOT_DIR/backend/.venv"
if [ -d "$VENV" ]; then
  pass "Virtual environment exists at backend/.venv"
  PY_BIN="$VENV/bin/python"
  if [ -f "$PY_BIN" ]; then
    pass "Python in venv: $($PY_BIN --version)"
  fi
else
  warn "Virtual environment not found. Run: ./bootstrap.sh"
fi

# ── FastAPI ────────────────────────────────────────────────────────────────────
if [ -f "$VENV/bin/python" ]; then
  if "$VENV/bin/python" -c "import fastapi" 2>/dev/null; then
    FAPI_VER=$("$VENV/bin/python" -c "import fastapi; print(fastapi.__version__)" 2>/dev/null)
    pass "FastAPI installed: $FAPI_VER"
  else
    warn "FastAPI not installed in venv. Run: uv pip install -e backend/.[dev]"
  fi
fi

# =============================================================================
section "Environment Variables"
# =============================================================================
ENV_FILE="$ROOT_DIR/.env"
if [ -f "$ENV_FILE" ]; then
  pass ".env file exists."

  required_vars=(
    "SUPABASE_URL"
    "SUPABASE_ANON_KEY"
    "SUPABASE_SERVICE_ROLE_KEY"
    "DATABASE_URL"
    "SECRET_KEY"
    "B2_KEY_ID"
    "B2_APPLICATION_KEY"
    "B2_BUCKET_NAME"
  )

  while IFS= read -r line || [ -n "$line" ]; do
    [[ "$line" =~ ^#.*$ ]] && continue
    [[ -z "$line" ]] && continue
    KEY="${line%%=*}"
    VAL="${line#*=}"
    export "$KEY=$VAL"
  done < "$ENV_FILE"

  for var in "${required_vars[@]}"; do
    val="${!var:-}"
    if [ -z "$val" ] || [ "$val" = "your-value-here" ] || [[ "$val" == change_me* ]]; then
      warn "$var is not set or is a placeholder."
    else
      pass "$var is set."
    fi
  done
else
  fail ".env file missing. Copy .env.example to .env and fill in values."
fi

# =============================================================================
section "Supabase"
# =============================================================================
if cmd_exists supabase; then
  SUPA_STATUS=$(supabase status 2>&1 || true)
  if echo "$SUPA_STATUS" | grep -q "API URL"; then
    pass "Supabase local stack running."
  else
    warn "Supabase local stack not running. Run: supabase start"
  fi
fi

# =============================================================================
section "API Health Check"
# =============================================================================
API_URL="${API_URL:-http://localhost:8000}"
if curl -sf "$API_URL/health" &>/dev/null; then
  pass "API health check: $API_URL/health OK"
else
  info "API not reachable at $API_URL (start with: uvicorn app.main:app --reload)"
fi

# =============================================================================
section "Pre-commit Hooks"
# =============================================================================
if [ -f "$ROOT_DIR/.pre-commit-config.yaml" ]; then
  if [ -f "$ROOT_DIR/.git/hooks/pre-commit" ]; then
    pass "Pre-commit hooks installed."
  else
    warn "Pre-commit config exists but hooks not installed. Run: pre-commit install"
  fi
else
  warn ".pre-commit-config.yaml not found."
fi

# =============================================================================
section "Result"
# =============================================================================
echo ""
if [ "$FAIL_COUNT" -eq 0 ] && [ "$WARN_COUNT" -eq 0 ]; then
  echo -e "${GREEN}${BOLD}✅  All checks passed. Environment is fully configured.${RESET}"
  exit 0
elif [ "$FAIL_COUNT" -eq 0 ]; then
  echo -e "${YELLOW}${BOLD}⚠️   $WARN_COUNT warning(s). Environment mostly ready — review warnings above.${RESET}"
  exit 0
else
  echo -e "${RED}${BOLD}❌  $FAIL_COUNT failure(s), $WARN_COUNT warning(s). Fix failures before developing.${RESET}"
  exit 1
fi

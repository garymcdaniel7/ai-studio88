#!/usr/bin/env bash
# =============================================================================
# AI Studio - Developer Bootstrap Script (macOS / Linux)
# =============================================================================
# Run this once after cloning the repository:
#   chmod +x bootstrap.sh && ./bootstrap.sh
# =============================================================================

set -euo pipefail

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

info()    { echo -e "${BLUE}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*" >&2; }
section() { echo -e "\n${CYAN}${BOLD}══════════════════════════════════════════${RESET}"; echo -e "${CYAN}${BOLD}  $*${RESET}"; echo -e "${CYAN}${BOLD}══════════════════════════════════════════${RESET}"; }

ERRORS=()
trap 'error "Bootstrap failed at line $LINENO"; exit 1' ERR

# ── OS Detection ─────────────────────────────────────────────────────────────
OS="$(uname -s)"
ARCH="$(uname -m)"
info "Detected OS: $OS ($ARCH)"

# ── Helper: command exists ────────────────────────────────────────────────────
cmd_exists() { command -v "$1" &>/dev/null; }

# ── Helper: version compare ───────────────────────────────────────────────────
version_gte() {
  local current="$1" required="$2"
  [ "$(printf '%s\n' "$required" "$current" | sort -V | head -n1)" = "$required" ]
}

# =============================================================================
section "1 / 8  Homebrew"
# =============================================================================
if cmd_exists brew; then
  success "Homebrew already installed: $(brew --version | head -1)"
else
  if [ "$OS" = "Darwin" ]; then
    info "Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    # Add to PATH for Apple Silicon
    if [ "$ARCH" = "arm64" ]; then
      eval "$(/opt/homebrew/bin/brew shellenv)"
      echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
    fi
    success "Homebrew installed."
  else
    warn "Linux detected – skipping Homebrew. Use your system package manager."
  fi
fi

# ── Brew tap shortcut ─────────────────────────────────────────────────────────
brew_install() {
  local pkg="$1"
  local cmd="${2:-$1}"
  if cmd_exists "$cmd"; then
    success "$cmd already installed."
  else
    info "Installing $pkg via Homebrew..."
    brew install "$pkg"
    success "$cmd installed."
  fi
}

# =============================================================================
section "2 / 8  Core CLI Tools"
# =============================================================================
brew_install git git
brew_install gh gh
brew_install git-lfs git-lfs
brew_install ffmpeg ffmpeg
brew_install imagemagick convert

# Initialise Git LFS
git lfs install --skip-repo 2>/dev/null || true
success "Git LFS initialised."

# =============================================================================
section "3 / 8  Docker Desktop"
# =============================================================================
if cmd_exists docker; then
  success "Docker already installed: $(docker --version)"
else
  if [ "$OS" = "Darwin" ]; then
    info "Installing Docker Desktop via Homebrew Cask..."
    brew install --cask docker
    warn "Docker Desktop installed. Please launch it from /Applications before continuing."
    warn "Re-run this script after Docker Desktop is running."
  else
    error "Please install Docker manually: https://docs.docker.com/engine/install/"
    ERRORS+=("docker not installed on Linux")
  fi
fi

# =============================================================================
section "4 / 8  Node.js LTS + npm"
# =============================================================================
if cmd_exists node; then
  NODE_VER="$(node --version | tr -d 'v')"
  REQUIRED_NODE="20.0.0"
  if version_gte "$NODE_VER" "$REQUIRED_NODE"; then
    success "Node.js already installed: v$NODE_VER"
  else
    warn "Node.js v$NODE_VER is older than required v$REQUIRED_NODE. Upgrading..."
    brew upgrade node
  fi
else
  info "Installing Node.js LTS..."
  brew install node
  success "Node.js installed: $(node --version)"
fi

if cmd_exists npm; then
  success "npm already installed: $(npm --version)"
fi

# =============================================================================
section "5 / 8  Python 3.12 + uv"
# =============================================================================
if cmd_exists python3.12; then
  success "Python 3.12 already installed: $(python3.12 --version)"
else
  info "Installing Python 3.12..."
  brew install python@3.12
  success "Python 3.12 installed."
fi

if cmd_exists uv; then
  success "uv already installed: $(uv --version)"
else
  info "Installing uv (Python package manager)..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
  success "uv installed: $(uv --version)"
fi

# =============================================================================
section "6 / 8  Supabase CLI"
# =============================================================================
if cmd_exists supabase; then
  success "Supabase CLI already installed: $(supabase --version)"
else
  info "Installing Supabase CLI..."
  brew install supabase/tap/supabase
  success "Supabase CLI installed: $(supabase --version)"
fi

# =============================================================================
section "7 / 8  Python Virtual Environment + Dependencies"
# =============================================================================
BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/backend"

if [ ! -f "$BACKEND_DIR/pyproject.toml" ]; then
  warn "backend/pyproject.toml not found – skipping Python dependency install."
else
  info "Creating Python virtual environment with uv..."
  uv venv "$BACKEND_DIR/.venv" --python python3.12
  success "Virtual environment created at backend/.venv"

  info "Installing Python dependencies..."
  (cd "$BACKEND_DIR" && uv pip install -e ".[dev]")
  success "Python dependencies installed."
fi

# ── Pre-commit ────────────────────────────────────────────────────────────────
if [ -f "$(pwd)/.pre-commit-config.yaml" ]; then
  info "Installing pre-commit hooks..."
  (cd "$(dirname "${BASH_SOURCE[0]}")" && \
    source backend/.venv/bin/activate 2>/dev/null || true && \
    pre-commit install)
  success "Pre-commit hooks installed."
fi

# =============================================================================
section "8 / 8  Environment Variables"
# =============================================================================
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ ! -f "$ROOT_DIR/.env" ]; then
  if [ -f "$ROOT_DIR/.env.example" ]; then
    cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
    warn ".env created from .env.example — fill in your secrets before running the app."
  else
    warn "No .env.example found. Create .env manually."
  fi
else
  success ".env already exists."
fi

# =============================================================================
section "Bootstrap Summary"
# =============================================================================
echo ""
info "Installed tools:"
for tool in brew git gh git-lfs docker node npm python3.12 uv supabase ffmpeg convert; do
  if cmd_exists "$tool"; then
    echo -e "  ${GREEN}✓${RESET} $tool"
  else
    echo -e "  ${RED}✗${RESET} $tool (not found in PATH)"
    ERRORS+=("$tool missing from PATH after install")
  fi
done

echo ""
if [ ${#ERRORS[@]} -eq 0 ]; then
  success "Bootstrap completed successfully!"
  echo ""
  info "Next steps:"
  echo "  1. Fill in .env with your credentials"
  echo "  2. Run: cd backend && source .venv/bin/activate"
  echo "  3. Run: uvicorn app.main:app --reload"
  echo "  4. Visit: http://localhost:8000/docs"
else
  warn "Bootstrap completed with warnings:"
  for e in "${ERRORS[@]}"; do
    echo -e "  ${YELLOW}!${RESET} $e"
  done
fi

echo ""
info "Run ./verify_environment.sh to validate your setup at any time."

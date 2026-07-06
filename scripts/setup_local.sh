#!/bin/bash
# =============================================================================
# AI Studio — Local Setup Script
# =============================================================================
# Installs Ollama locally (macOS via brew), pulls the default model,
# and verifies the connection to the AI Studio backend.
#
# Usage:
#   chmod +x scripts/setup_local.sh
#   ./scripts/setup_local.sh
#
# What this does:
#   1. Installs Homebrew (if not present)
#   2. Installs Ollama via brew (if not present)
#   3. Starts Ollama serve (if not running)
#   4. Pulls llama3.1:8b model (~4.7 GB download)
#   5. Verifies Ollama is reachable at localhost:11434
#   6. Verifies connection to AI Studio backend
# =============================================================================

set -e

OLLAMA_URL="http://localhost:11434"
BACKEND_URL="http://localhost:8000"
MODEL="llama3.1:8b"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}"
echo "╔══════════════════════════════════════╗"
echo "║    AI Studio — Local Setup           ║"
echo "╚══════════════════════════════════════╝"
echo -e "${NC}"

# --------------------------------------------------------------------------
# Step 1: Check/Install Homebrew
# --------------------------------------------------------------------------
echo -e "${YELLOW}[1/6] Checking Homebrew...${NC}"
if command -v brew &>/dev/null; then
    echo -e "  ${GREEN}✓${NC} Homebrew already installed ($(brew --version | head -1))"
else
    echo "  Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    echo -e "  ${GREEN}✓${NC} Homebrew installed"
fi

# --------------------------------------------------------------------------
# Step 2: Check/Install Ollama
# --------------------------------------------------------------------------
echo -e "${YELLOW}[2/6] Checking Ollama...${NC}"
if command -v ollama &>/dev/null; then
    echo -e "  ${GREEN}✓${NC} Ollama already installed ($(ollama --version 2>/dev/null || echo 'version unknown'))"
else
    echo "  Installing Ollama via brew..."
    brew install ollama
    echo -e "  ${GREEN}✓${NC} Ollama installed"
fi

# --------------------------------------------------------------------------
# Step 3: Start Ollama (if not running)
# --------------------------------------------------------------------------
echo -e "${YELLOW}[3/6] Starting Ollama...${NC}"
if curl -s "$OLLAMA_URL/api/tags" &>/dev/null; then
    echo -e "  ${GREEN}✓${NC} Ollama already running at $OLLAMA_URL"
else
    echo "  Starting ollama serve in background..."
    ollama serve &>/dev/null &
    OLLAMA_PID=$!
    
    # Wait for it to be ready (up to 15 seconds)
    for i in {1..15}; do
        if curl -s "$OLLAMA_URL/api/tags" &>/dev/null; then
            break
        fi
        sleep 1
    done
    
    if curl -s "$OLLAMA_URL/api/tags" &>/dev/null; then
        echo -e "  ${GREEN}✓${NC} Ollama started (PID: $OLLAMA_PID)"
    else
        echo -e "  ${RED}✗${NC} Failed to start Ollama. Try running 'ollama serve' manually."
        exit 1
    fi
fi

# --------------------------------------------------------------------------
# Step 4: Pull model
# --------------------------------------------------------------------------
echo -e "${YELLOW}[4/6] Pulling model: ${MODEL}...${NC}"
EXISTING=$(curl -s "$OLLAMA_URL/api/tags" | grep -o "\"$MODEL\"" || true)
if [ -n "$EXISTING" ]; then
    echo -e "  ${GREEN}✓${NC} Model $MODEL already downloaded"
else
    echo "  Downloading $MODEL (~4.7 GB, this may take a few minutes)..."
    ollama pull "$MODEL"
    echo -e "  ${GREEN}✓${NC} Model $MODEL ready"
fi

# --------------------------------------------------------------------------
# Step 5: Verify Ollama
# --------------------------------------------------------------------------
echo -e "${YELLOW}[5/6] Verifying Ollama...${NC}"
MODELS=$(curl -s "$OLLAMA_URL/api/tags" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('models',[])))" 2>/dev/null || echo "0")
if [ "$MODELS" -gt 0 ]; then
    echo -e "  ${GREEN}✓${NC} Ollama verified: $MODELS model(s) available"
else
    echo -e "  ${YELLOW}⚠${NC} Ollama running but no models loaded. Run: ollama pull $MODEL"
fi

# Quick inference test
echo "  Testing inference..."
RESPONSE=$(curl -s -X POST "$OLLAMA_URL/api/generate" \
    -H "Content-Type: application/json" \
    -d "{\"model\": \"$MODEL\", \"prompt\": \"Say hello in 5 words.\", \"stream\": false}" \
    --max-time 30 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('response','')[:80])" 2>/dev/null || echo "")

if [ -n "$RESPONSE" ]; then
    echo -e "  ${GREEN}✓${NC} Inference test passed: \"$RESPONSE\""
else
    echo -e "  ${YELLOW}⚠${NC} Inference test skipped (model may still be loading)"
fi

# --------------------------------------------------------------------------
# Step 6: Connect to AI Studio backend
# --------------------------------------------------------------------------
echo -e "${YELLOW}[6/6] Connecting to AI Studio...${NC}"
BACKEND_HEALTH=$(curl -s "$BACKEND_URL/" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status',''))" 2>/dev/null || echo "")

if [ "$BACKEND_HEALTH" = "ok" ]; then
    echo -e "  ${GREEN}✓${NC} AI Studio backend connected at $BACKEND_URL"
    
    # Tell the backend Ollama is ready
    OLLAMA_CHECK=$(curl -s "$BACKEND_URL/api/v1/infrastructure/services/health" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('ollama',{}).get('online',False))" 2>/dev/null || echo "")
    if [ "$OLLAMA_CHECK" = "True" ]; then
        echo -e "  ${GREEN}✓${NC} Backend detected Ollama — toggle will show ON"
    else
        echo -e "  ${YELLOW}⚠${NC} Backend can't reach Ollama yet. Refresh the Admin page."
    fi
else
    echo -e "  ${YELLOW}⚠${NC} AI Studio backend not running at $BACKEND_URL"
    echo "     Start it with: uv run uvicorn backend.main:app --reload"
    echo "     Ollama is ready and will connect when the backend starts."
fi

# --------------------------------------------------------------------------
# Done
# --------------------------------------------------------------------------
echo ""
echo -e "${GREEN}╔══════════════════════════════════════╗"
echo "║    Setup Complete!                   ║"
echo "╚══════════════════════════════════════╝${NC}"
echo ""
echo "  Ollama:  $OLLAMA_URL (running)"
echo "  Model:   $MODEL"
echo "  Brain:   Open http://localhost:3000/brain to chat"
echo ""
echo "  To keep Ollama running after reboot:"
echo "    brew services start ollama"
echo ""

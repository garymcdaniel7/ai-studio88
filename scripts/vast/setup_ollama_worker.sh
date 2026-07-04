#!/bin/bash
# =============================================================================
# Setup Ollama on a Vast.ai GPU Worker
# =============================================================================
# Downloads Ollama, installs it, pulls model from B2 cache (or registry),
# and starts serving on port 11434.
#
# Usage (on worker via SSH):
#   bash setup_ollama_worker.sh
#
# Environment variables:
#   OLLAMA_MODEL — model to serve (default: llama3.2)
#   B2_KEY_ID, B2_APPLICATION_KEY, B2_ENDPOINT_URL — for B2 cache download
#   MODEL_CACHE_BUCKET — B2 bucket name
# =============================================================================

set -euo pipefail

OLLAMA_MODEL="${OLLAMA_MODEL:-llama3.2}"
OLLAMA_PORT="${OLLAMA_PORT:-11434}"

echo "=============================================="
echo " AI Studio — Ollama Worker Setup"
echo "=============================================="
echo " Model: $OLLAMA_MODEL"
echo " Port:  $OLLAMA_PORT"
echo ""

# Install Ollama
echo "[1/3] Installing Ollama..."
if ! command -v ollama &> /dev/null; then
    curl -fsSL https://ollama.com/install.sh | sh
fi
echo "      Done."

# Start Ollama in background
echo "[2/3] Starting Ollama server..."
ollama serve > /tmp/ollama.log 2>&1 &
sleep 3

# Verify it's running
if curl -s http://localhost:$OLLAMA_PORT/api/tags > /dev/null 2>&1; then
    echo "      Ollama running on port $OLLAMA_PORT"
else
    echo "      [WARN] Ollama may not have started correctly"
    cat /tmp/ollama.log | tail -5
fi

# Pull model (from registry — B2 cache TODO for .gguf files)
echo "[3/3] Pulling model: $OLLAMA_MODEL..."
ollama pull "$OLLAMA_MODEL"

echo ""
echo "=============================================="
echo " Ollama ready!"
echo " API: http://localhost:$OLLAMA_PORT"
echo " Model: $OLLAMA_MODEL"
echo "=============================================="

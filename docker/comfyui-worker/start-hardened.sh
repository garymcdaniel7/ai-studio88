#!/bin/bash
# =============================================================================
# AI Studio GPU Worker — Hardened Startup (Story 049)
# =============================================================================
# Production startup: NO SSH, non-root, minimal logging.
# Secrets from environment only (never logged).
# =============================================================================

set -e

echo "╔══════════════════════════════════════════════╗"
echo "║    AI Studio GPU Worker (Hardened)           ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "User:  $(whoami) ($(id -u):$(id -g))"
echo "GPU:   $(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null || echo 'detecting...')"
echo "VRAM:  $(nvidia-smi --query-gpu=memory.total --format=csv,noheader 2>/dev/null || echo 'detecting...')"
echo "Disk:  $(df -h /workspace 2>/dev/null | tail -1 | awk '{print $4}') free"
echo "SSH:   DISABLED (production mode)"
echo ""

# SECURITY: Verify we are NOT running as root
if [ "$(id -u)" = "0" ]; then
    echo "ERROR: Running as root is not permitted in hardened mode."
    echo "       Use the production image with USER comfyui."
    exit 1
fi

# SECURITY: Never log secret values
echo "[1/3] Checking credentials..."
if [ -n "$B2_KEY_ID" ]; then
    echo "      B2: configured (key ID present)"
else
    echo "      B2: NOT configured (model download may fail)"
fi
if [ -n "$HF_TOKEN" ]; then
    echo "      HuggingFace: configured"
else
    echo "      HuggingFace: NOT configured"
fi
echo ""

# Download models
echo "[2/3] Loading models..."
MODELS=${MODELS:-"sdxl-turbo"}
python3 /workspace/download_models.py --models "$MODELS" 2>&1 || echo "      [WARN] Model download had errors"
echo "      Models ready"
echo ""

# Start Ollama (background, non-blocking)
echo "[3/3] Starting services..."
ollama serve > /tmp/ollama.log 2>&1 &
(sleep 10 && ollama pull llama3.1:8b > /tmp/ollama_pull.log 2>&1) &

# Start ComfyUI (foreground — keeps container alive)
echo ""
echo "════════════════════════════════════════════════"
echo "  READY — ComfyUI at http://0.0.0.0:8188"
echo "  Mode:  PRODUCTION (hardened, non-root)"
echo "════════════════════════════════════════════════"
echo ""

cd /workspace/ComfyUI
exec python3 main.py --listen 0.0.0.0 --port 8188 --preview-method auto

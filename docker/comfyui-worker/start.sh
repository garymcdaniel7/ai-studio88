#!/bin/bash
# AI Studio GPU Worker — Startup Script
# 
# Boot sequence:
# 1. Start SSH (for remote access)
# 2. Download models from B2 cache (or HuggingFace fallback)
# 3. Start ComfyUI
# 4. Start Ollama (background)
#
# Environment variables:
#   B2_KEY_ID — Backblaze B2 key ID (for model cache)
#   B2_APPLICATION_KEY — Backblaze B2 app key
#   HF_TOKEN — HuggingFace token (fallback downloads)
#   MODELS — comma-separated list: "sdxl-turbo,flux-dev" (default: sdxl-turbo)

set -e

echo "╔══════════════════════════════════════════════╗"
echo "║       AI Studio GPU Worker v1.0             ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "GPU:  $(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null || echo 'detecting...')"
echo "VRAM: $(nvidia-smi --query-gpu=memory.total --format=csv,noheader 2>/dev/null || echo 'detecting...')"
echo "Disk: $(df -h /workspace | tail -1 | awk '{print $4}') free"
echo ""

# 1. Start SSH
echo "[1/4] Starting SSH server..."
/usr/sbin/sshd -D &
echo "      SSH ready"

# 2. Download models
echo "[2/4] Loading models..."
MODELS=${MODELS:-"sdxl-turbo"}
python3 /workspace/download_models.py --models "$MODELS"
echo "      Models ready"

# 3. Start Ollama (background, non-blocking)
echo "[3/4] Starting Ollama..."
ollama serve > /tmp/ollama.log 2>&1 &
(sleep 10 && ollama pull llama3.1:8b > /tmp/ollama_pull.log 2>&1) &
echo "      Ollama starting (model pull in background)"

# 4. Start ComfyUI (foreground — keeps container alive)
echo "[4/4] Starting ComfyUI on port 8188..."
echo ""
echo "════════════════════════════════════════════════"
echo "  READY — ComfyUI at http://0.0.0.0:8188"
echo "  SSH tunnel: ssh -N -L 8188:localhost:8188 -p PORT root@HOST"
echo "════════════════════════════════════════════════"
echo ""

cd /workspace/ComfyUI
exec python3 main.py --listen 0.0.0.0 --port 8188 --preview-method auto

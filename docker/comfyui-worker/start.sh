#!/bin/bash
# AI Studio GPU Worker — Startup Script
# Launches all services concurrently for fastest boot.
#
# Services:
# 1. SSH server (for debugging / Vast.ai compatibility)
# 2. Ollama (LLM inference)
# 3. ComfyUI (image/video generation)
# 4. Model loader (downloads from B2 if not on volume)

echo "=== AI Studio GPU Worker Starting ==="
echo "GPU: $(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null || echo 'detecting...')"
echo "VRAM: $(nvidia-smi --query-gpu=memory.total --format=csv,noheader 2>/dev/null || echo 'detecting...')"
echo ""

# Start SSH (background)
/usr/sbin/sshd -D &

# Start Ollama (background)
echo "[1/3] Starting Ollama..."
ollama serve > /tmp/ollama.log 2>&1 &
OLLAMA_PID=$!

# Wait for Ollama to be ready, then pull model
(
    sleep 5
    echo "[1/3] Pulling dolphin-llama3:8b (uncensored)..."
    ollama pull dolphin-llama3:8b > /tmp/ollama_pull.log 2>&1
    echo "[1/3] Ollama ready with dolphin-llama3:8b"
) &

# Check if models exist on persistent volume
MODEL_DIR="/workspace/ComfyUI/models/checkpoints"
VOLUME_DIR="/runpod-volume/models"

if [ -d "$VOLUME_DIR" ] && [ "$(ls -A $VOLUME_DIR 2>/dev/null)" ]; then
    echo "[2/3] Linking models from persistent volume..."
    # Symlink models from volume to ComfyUI
    for f in "$VOLUME_DIR"/*.safetensors; do
        [ -f "$f" ] && ln -sf "$f" "$MODEL_DIR/$(basename $f)" 2>/dev/null
    done
    echo "[2/3] Models linked: $(ls $MODEL_DIR/*.safetensors 2>/dev/null | wc -l) files"
else
    echo "[2/3] No persistent volume models. Will download on first use."
    # Download SDXL Turbo (smallest, fastest for testing)
    if [ ! -f "$MODEL_DIR/sd_xl_turbo_1.0_fp16.safetensors" ]; then
        echo "[2/3] Downloading SDXL Turbo (7GB)..."
        python -c "
from huggingface_hub import hf_hub_download
import os
hf_hub_download('stabilityai/sdxl-turbo', 'sd_xl_turbo_1.0_fp16.safetensors',
    local_dir='$MODEL_DIR', token=os.getenv('HF_TOKEN') or None)
print('SDXL Turbo downloaded!')
" > /tmp/model_download.log 2>&1 &
    fi
fi

# Start ComfyUI (foreground — main process)
echo "[3/3] Starting ComfyUI on port 8188..."
cd /workspace/ComfyUI
python main.py --listen 0.0.0.0 --port 8188 --preview-method auto

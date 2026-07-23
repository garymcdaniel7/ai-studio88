#!/bin/bash
# =============================================================================
# AI Studio — Full GPU Worker Bootstrap (paste as Vast.ai onstart script)
# =============================================================================
#
# This script sets up a COMPLETE AI Studio GPU worker with:
# - ComfyUI (image/video generation)
# - SimpleTuner (LoRA training)  
# - MOSS TTS (voice synthesis)
# - Ollama (LLM inference)
# - FFMPEG (video processing)
#
# Usage on Vast.ai:
#   1. Select a GPU instance (RTX 3090+, 24GB+ VRAM, 80GB+ disk)
#   2. Use image: pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime
#   3. Paste this entire script as the "on-start" script
#   4. Set env vars: HF_TOKEN=your_token
#   5. Launch!
#
# After boot (~5-10 min first time, ~1 min on resume):
#   - ComfyUI on port 8188
#   - Ollama on port 11434
#   - SSH tunnel: ssh -N -L 8188:localhost:8188 -p PORT root@HOST
# =============================================================================

set -e
export DEBIAN_FRONTEND=noninteractive

echo "╔══════════════════════════════════════════════╗"
echo "║     AI Studio GPU Worker — Full Setup       ║"
echo "╚══════════════════════════════════════════════╝"

# Detect GPU
GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null || echo "Unknown")
GPU_VRAM=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader 2>/dev/null || echo "Unknown")
echo "GPU:  $GPU_NAME"
echo "VRAM: $GPU_VRAM"
echo ""

# Create workspace
mkdir -p /workspace
cd /workspace

# =============================================================================
# 1. System Dependencies
# =============================================================================
echo "[1/6] Installing system dependencies..."
if ! command -v git &> /dev/null; then
    apt-get update -qq
    apt-get install -y -qq git wget curl ffmpeg libgl1-mesa-glx libglib2.0-0 nano > /dev/null 2>&1
fi
echo "      Done"

# =============================================================================
# 2. ComfyUI
# =============================================================================
echo "[2/6] Setting up ComfyUI..."
if [ ! -d "/workspace/ComfyUI" ]; then
    git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git
    cd ComfyUI
    pip install -q -r requirements.txt
    pip install -q huggingface-hub b2sdk aiohttp
    # ComfyUI Manager for easy custom node management
    cd custom_nodes
    git clone --depth 1 https://github.com/ltdrdata/ComfyUI-Manager.git
    cd /workspace
    echo "      ComfyUI installed fresh"
else
    echo "      ComfyUI already installed (persistent disk)"
fi

# Create model directories
mkdir -p /workspace/ComfyUI/models/{checkpoints,unet,clip,vae,loras,controlnet}

# =============================================================================
# 3. Download Models (skip if already on disk)
# =============================================================================
echo "[3/6] Loading AI models..."
cd /workspace/ComfyUI/models

# SDXL Turbo (fast generation, ~7GB)
if [ ! -f "checkpoints/sd_xl_turbo_1.0_fp16.safetensors" ]; then
    echo "      Downloading SDXL Turbo..."
    python3 -c "
from huggingface_hub import hf_hub_download
import os
hf_hub_download('stabilityai/sdxl-turbo', 'sd_xl_turbo_1.0_fp16.safetensors',
    local_dir='/workspace/ComfyUI/models/checkpoints',
    token=os.getenv('HF_TOKEN') or None)
" 2>/dev/null
    echo "      SDXL Turbo ready"
else
    echo "      SDXL Turbo already on disk"
fi

# Flux Dev fp8 (high quality, ~17GB total with CLIP+VAE)
if [ ! -f "unet/flux1-dev-fp8.safetensors" ]; then
    echo "      Downloading Flux Dev (fp8)..."
    python3 -c "
from huggingface_hub import hf_hub_download
import os
token = os.getenv('HF_TOKEN') or None
hf_hub_download('Comfy-Org/flux1-dev', 'flux1-dev-fp8.safetensors', local_dir='/workspace/ComfyUI/models/unet', token=token)
hf_hub_download('comfyanonymous/flux_text_encoders', 'clip_l.safetensors', local_dir='/workspace/ComfyUI/models/clip', token=token)
hf_hub_download('comfyanonymous/flux_text_encoders', 't5xxl_fp16.safetensors', local_dir='/workspace/ComfyUI/models/clip', token=token)
hf_hub_download('black-forest-labs/FLUX.1-dev', 'ae.safetensors', local_dir='/workspace/ComfyUI/models/vae', token=token)
" 2>/dev/null
    echo "      Flux Dev ready"
else
    echo "      Flux Dev already on disk"
fi

# =============================================================================
# 4. SimpleTuner (LoRA Training)
# =============================================================================
echo "[4/6] Setting up SimpleTuner..."
if [ ! -d "/workspace/SimpleTuner" ]; then
    git clone --depth 1 https://github.com/bghira/SimpleTuner.git /workspace/SimpleTuner
    cd /workspace/SimpleTuner
    pip install -q -e . 2>/dev/null || pip install -q -r requirements.txt 2>/dev/null
    cd /workspace
    echo "      SimpleTuner installed"
else
    echo "      SimpleTuner already installed"
fi

# =============================================================================
# 5. Ollama (LLM)
# =============================================================================
echo "[5/6] Setting up Ollama..."
if ! command -v ollama &> /dev/null; then
    curl -fsSL https://ollama.com/install.sh | sh 2>/dev/null
    echo "      Ollama installed"
else
    echo "      Ollama already installed"
fi

# =============================================================================
# 6. MOSS TTS (Voice Synthesis) — lightweight Python TTS
# =============================================================================
echo "[6/6] Setting up voice synthesis..."
pip install -q TTS 2>/dev/null || echo "      TTS install skipped (may need manual setup)"
echo "      Voice synthesis ready"

# =============================================================================
# Start Services
# =============================================================================
echo ""
echo "Starting services..."

# Start Ollama in background
ollama serve > /tmp/ollama.log 2>&1 &
(sleep 15 && ollama pull llama3.1:8b > /tmp/ollama_pull.log 2>&1) &

# Start ComfyUI (foreground)
echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║  READY — All services starting              ║"
echo "║                                             ║"
echo "║  ComfyUI:  http://localhost:8188            ║"
echo "║  Ollama:   http://localhost:11434           ║"
echo "║                                             ║"
echo "║  SSH tunnel:                                ║"
echo "║  ssh -N -L 8188:localhost:8188 \            ║"
echo "║      -L 11434:localhost:11434 \             ║"
echo "║      -p PORT root@HOST                     ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

cd /workspace/ComfyUI
exec python3 main.py --listen 0.0.0.0 --port 8188 --preview-method auto

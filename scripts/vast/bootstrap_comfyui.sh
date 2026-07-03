#!/bin/bash
# =============================================================================
# ComfyUI Bootstrap Script for Vast.ai Workers
# =============================================================================
# This script runs on the Vast.ai instance after launch.
# It installs ComfyUI, ComfyUI Manager, creates standard directories,
# and starts ComfyUI on 0.0.0.0:8188.
#
# Usage (on the instance):
#   bash bootstrap_comfyui.sh
#
# Or set as onstart script when launching via Vast.ai.
# =============================================================================

set -euo pipefail

COMFYUI_DIR="/workspace/ComfyUI"
COMFYUI_PORT="${COMFYUI_PORT:-8188}"
COMFYUI_LISTEN="${COMFYUI_LISTEN:-0.0.0.0}"

echo "=============================================="
echo " AI Studio — ComfyUI Worker Bootstrap"
echo "=============================================="
echo ""

# ─── System Dependencies ─────────────────────────────────────────────────────
echo "[1/6] Installing system dependencies..."
apt-get update -qq
apt-get install -y -qq git wget curl ffmpeg libgl1-mesa-glx > /dev/null 2>&1
echo "      Done."

# ─── Clone/Update ComfyUI ────────────────────────────────────────────────────
echo "[2/6] Setting up ComfyUI..."
if [ -d "$COMFYUI_DIR" ]; then
    echo "      ComfyUI directory exists — pulling latest..."
    cd "$COMFYUI_DIR"
    git pull --quiet || echo "      (git pull skipped — may have local changes)"
else
    echo "      Cloning ComfyUI..."
    git clone --quiet https://github.com/comfyanonymous/ComfyUI.git "$COMFYUI_DIR"
    cd "$COMFYUI_DIR"
fi

echo "      Installing Python requirements..."
pip install -q -r requirements.txt
echo "      Done."

# ─── Install ComfyUI Manager ─────────────────────────────────────────────────
echo "[3/6] Installing ComfyUI Manager..."
MANAGER_DIR="$COMFYUI_DIR/custom_nodes/ComfyUI-Manager"
if [ -d "$MANAGER_DIR" ]; then
    cd "$MANAGER_DIR"
    git pull --quiet || true
else
    git clone --quiet https://github.com/ltdrdata/ComfyUI-Manager.git "$MANAGER_DIR"
fi
echo "      Done."

# ─── Create Standard Directories ─────────────────────────────────────────────
echo "[4/6] Creating standard model directories..."
cd "$COMFYUI_DIR"
mkdir -p models/checkpoints
mkdir -p models/loras
mkdir -p models/vae
mkdir -p models/controlnet
mkdir -p models/upscale_models
mkdir -p models/clip
mkdir -p models/embeddings
mkdir -p models/hypernetworks
mkdir -p input
mkdir -p output
mkdir -p temp
echo "      Directories ready."

# ─── Print Structure ─────────────────────────────────────────────────────────
echo "[5/6] Directory structure:"
echo "      $COMFYUI_DIR/"
echo "      ├── models/"
echo "      │   ├── checkpoints/"
echo "      │   ├── loras/"
echo "      │   ├── vae/"
echo "      │   ├── controlnet/"
echo "      │   ├── upscale_models/"
echo "      │   ├── clip/"
echo "      │   ├── embeddings/"
echo "      │   └── hypernetworks/"
echo "      ├── custom_nodes/"
echo "      │   └── ComfyUI-Manager/"
echo "      ├── input/"
echo "      ├── output/"
echo "      └── temp/"

# ─── Start ComfyUI ───────────────────────────────────────────────────────────
echo "[6/6] Starting ComfyUI on ${COMFYUI_LISTEN}:${COMFYUI_PORT}..."
echo ""
echo "=============================================="
echo " Health URL: http://${COMFYUI_LISTEN}:${COMFYUI_PORT}/system_stats"
echo "=============================================="
echo ""

cd "$COMFYUI_DIR"
python main.py --listen "$COMFYUI_LISTEN" --port "$COMFYUI_PORT"

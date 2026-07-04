#!/bin/bash
# =============================================================================
# ComfyUI Bootstrap Script for Vast.ai Workers
# =============================================================================
# This script runs on the Vast.ai instance after launch.
# It installs ComfyUI, creates standard directories, downloads models
# from Backblaze B2 cache (fast) or HuggingFace (fallback), and starts
# ComfyUI on 0.0.0.0:8188.
#
# Environment variables (passed from AI Studio .env):
#   B2_KEY_ID, B2_APPLICATION_KEY, B2_ENDPOINT_URL, B2_REGION
#   MODEL_CACHE_BUCKET, MODEL_CACHE_PREFIX, MODEL_CACHE_ENABLED
#   HF_TOKEN (optional, for authenticated HuggingFace downloads)
#   COMFYUI_PORT (default: 8188)
#   MODELS_TO_DOWNLOAD (comma-separated known model names, e.g. "sdxl-turbo")
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
MODELS_TO_DOWNLOAD="${MODELS_TO_DOWNLOAD:-sdxl-turbo}"

echo "=============================================="
echo " AI Studio — ComfyUI Worker Bootstrap"
echo "=============================================="
echo ""

# ─── System Dependencies ─────────────────────────────────────────────────────
echo "[1/7] Installing system dependencies..."
apt-get update -qq
apt-get install -y -qq git wget curl ffmpeg libgl1-mesa-glx > /dev/null 2>&1
echo "      Done."

# ─── Clone/Update ComfyUI ────────────────────────────────────────────────────
echo "[2/7] Setting up ComfyUI..."
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
echo "[3/7] Installing ComfyUI Manager..."
MANAGER_DIR="$COMFYUI_DIR/custom_nodes/ComfyUI-Manager"
if [ -d "$MANAGER_DIR" ]; then
    cd "$MANAGER_DIR"
    git pull --quiet || true
else
    git clone --quiet https://github.com/ltdrdata/ComfyUI-Manager.git "$MANAGER_DIR"
fi
echo "      Done."

# ─── Create Standard Directories ─────────────────────────────────────────────
echo "[4/7] Creating standard model directories..."
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

# ─── Install Model Cache Dependencies ────────────────────────────────────────
echo "[5/7] Installing model download tools..."
pip install -q boto3 huggingface-hub python-dotenv
echo "      Done."

# ─── Download Models (B2 Cache → HuggingFace) ────────────────────────────────
echo "[6/7] Downloading models..."
echo "      Strategy: Backblaze B2 cache first, HuggingFace fallback"
echo "      Models requested: $MODELS_TO_DOWNLOAD"
echo ""

# Parse comma-separated model names
IFS=',' read -ra MODEL_NAMES <<< "$MODELS_TO_DOWNLOAD"

for MODEL_NAME in "${MODEL_NAMES[@]}"; do
    MODEL_NAME=$(echo "$MODEL_NAME" | xargs)  # trim whitespace
    echo "      Downloading: $MODEL_NAME"

    # Try B2 cache first via Python
    python3 -c "
import os, sys
sys.path.insert(0, '/workspace')

# Inline model registry (no dependency on AI Studio backend)
KNOWN_MODELS = {
    'sdxl-turbo': {
        'filename': 'sd_xl_turbo_1.0_fp16.safetensors',
        'model_type': 'checkpoint',
        'hf_repo': 'stabilityai/sdxl-turbo',
        'hf_filename': 'sd_xl_turbo_1.0_fp16.safetensors',
        'subfolder': 'checkpoints',
    },
    'sdxl-base': {
        'filename': 'sd_xl_base_1.0.safetensors',
        'model_type': 'checkpoint',
        'hf_repo': 'stabilityai/stable-diffusion-xl-base-1.0',
        'hf_filename': 'sd_xl_base_1.0.safetensors',
        'subfolder': 'checkpoints',
    },
    'flux-dev': {
        'filename': 'flux1-dev.safetensors',
        'model_type': 'checkpoint',
        'hf_repo': 'black-forest-labs/FLUX.1-dev',
        'hf_filename': 'flux1-dev.safetensors',
        'subfolder': 'checkpoints',
    },
    'sdxl-vae': {
        'filename': 'sdxl_vae.safetensors',
        'model_type': 'vae',
        'hf_repo': 'stabilityai/sdxl-vae',
        'hf_filename': 'sdxl_vae.safetensors',
        'subfolder': 'vae',
    },
}

model_name = '$MODEL_NAME'
model = KNOWN_MODELS.get(model_name)
if not model:
    print(f'      [WARN] Unknown model: {model_name}, skipping')
    sys.exit(0)

dest_dir = f'/workspace/ComfyUI/models/{model[\"subfolder\"]}'
dest_path = os.path.join(dest_dir, model['filename'])

# Already exists?
if os.path.exists(dest_path) and os.path.getsize(dest_path) > 1000000:
    print(f'      [OK] Already exists: {dest_path}')
    sys.exit(0)

os.makedirs(dest_dir, exist_ok=True)
downloaded = False

# Try Backblaze B2 cache
b2_key = os.environ.get('B2_KEY_ID', '')
b2_secret = os.environ.get('B2_APPLICATION_KEY', '')
b2_endpoint = os.environ.get('B2_ENDPOINT_URL', '')
cache_bucket = os.environ.get('MODEL_CACHE_BUCKET', '')
cache_prefix = os.environ.get('MODEL_CACHE_PREFIX', 'models/')
cache_enabled = os.environ.get('MODEL_CACHE_ENABLED', 'true').lower() == 'true'

if cache_enabled and b2_key and b2_secret and cache_bucket:
    try:
        import boto3
        from botocore.exceptions import ClientError
        client = boto3.client('s3', endpoint_url=b2_endpoint,
                             aws_access_key_id=b2_key,
                             aws_secret_access_key=b2_secret,
                             region_name=os.environ.get('B2_REGION', 'us-east-005'))
        key = f\"{cache_prefix}{model['subfolder']}/{model['filename']}\"
        client.head_object(Bucket=cache_bucket, Key=key)
        print(f'      [INFO] Found in B2 cache, downloading...')
        client.download_file(cache_bucket, key, dest_path)
        downloaded = True
        print(f'      [OK] Downloaded from B2: {os.path.getsize(dest_path) / 1e9:.2f} GB')
    except (ClientError, Exception) as e:
        print(f'      [INFO] Not in B2 cache: {e}')

# Fallback to HuggingFace
if not downloaded:
    try:
        from huggingface_hub import hf_hub_download
        hf_token = os.environ.get('HF_TOKEN', '') or None
        print(f'      [INFO] Downloading from HuggingFace: {model[\"hf_repo\"]}')
        if hf_token:
            print(f'      [INFO] Using authenticated download')
        hf_hub_download(model['hf_repo'], model['hf_filename'],
                       local_dir=dest_dir, token=hf_token)
        downloaded = True
        print(f'      [OK] Downloaded from HuggingFace')
    except Exception as e:
        print(f'      [ERROR] HuggingFace download failed: {e}')

if not downloaded:
    print(f'      [ERROR] Failed to download {model_name}')
    sys.exit(1)
" || echo "      [WARN] Model download script failed for $MODEL_NAME"
done

echo ""
echo "      Model download complete."

# ─── Start ComfyUI ───────────────────────────────────────────────────────────
echo "[7/7] Starting ComfyUI on ${COMFYUI_LISTEN}:${COMFYUI_PORT}..."
echo ""
echo "=============================================="
echo " Health URL: http://${COMFYUI_LISTEN}:${COMFYUI_PORT}/system_stats"
echo "=============================================="
echo ""

cd "$COMFYUI_DIR"
python main.py --listen "$COMFYUI_LISTEN" --port "$COMFYUI_PORT"

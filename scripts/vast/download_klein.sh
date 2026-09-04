#!/bin/bash
# Download flux2-klein models (Comfy-Org split files) for ComfyUI worker
set -e
export HF_TOKEN="${HF_TOKEN:-}"
mkdir -p /workspace/ComfyUI/models/unet /workspace/ComfyUI/models/clip /workspace/ComfyUI/models/vae

echo "=== flux2-klein unet ==="
python3 - <<'PY'
import os
from huggingface_hub import hf_hub_download
token = os.getenv('HF_TOKEN') or None
p = hf_hub_download(
    'Comfy-Org/flux2-klein',
    'split_files/diffusion_models/flux-2-klein-4b.safetensors',
    local_dir='/workspace/ComfyUI/models/unet',
    token=token,
)
print('klein unet OK:', p)
PY

echo "=== flux2-klein clip (qwen 3 4b) ==="
python3 - <<'PY'
import os
from huggingface_hub import hf_hub_download
token = os.getenv('HF_TOKEN') or None
p = hf_hub_download(
    'Comfy-Org/flux2-klein',
    'split_files/text_encoders/qwen_3_4b.safetensors',
    local_dir='/workspace/ComfyUI/models/clip',
    token=token,
)
print('klein clip OK:', p)
PY

echo "=== flux2-klein vae ==="
python3 - <<'PY'
import os
from huggingface_hub import hf_hub_download
token = os.getenv('HF_TOKEN') or None
p = hf_hub_download(
    'Comfy-Org/flux2-klein',
    'split_files/vae/flux2-vae.safetensors',
    local_dir='/workspace/ComfyUI/models/vae',
    token=token,
)
print('klein vae OK:', p)
PY

# ComfyUI expects files at the model root, not nested under split_files
echo "=== move to ComfyUI expected locations ==="
mv -f /workspace/ComfyUI/models/unet/split_files/diffusion_models/flux-2-klein-4b.safetensors /workspace/ComfyUI/models/unet/ 2>/dev/null || true
mv -f /workspace/ComfyUI/models/clip/split_files/text_encoders/qwen_3_4b.safetensors /workspace/ComfyUI/models/clip/ 2>/dev/null || true
mv -f /workspace/ComfyUI/models/vae/split_files/vae/flux2-vae.safetensors /workspace/ComfyUI/models/vae/ 2>/dev/null || true

echo "=== final model dirs ==="
ls -la /workspace/ComfyUI/models/unet/ /workspace/ComfyUI/models/clip/ /workspace/ComfyUI/models/vae/ 2>/dev/null
echo "=== DONE ==="

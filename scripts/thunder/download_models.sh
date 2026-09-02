#!/bin/bash
# Download flux2-klein (UI default) + sdxl-turbo models onto the Thunder ComfyUI worker.
set -e
export HF_TOKEN="${HF_TOKEN:-}"
COMFY=/home/ubuntu/ComfyUI
[ -d "$COMFY" ] || COMFY=/workspace/ComfyUI
[ -d "$COMFY" ] || COMFY=$(find / -maxdepth 4 -type d -name "ComfyUI" 2>/dev/null | head -1)
echo "ComfyUI dir: $COMFY"
mkdir -p "$COMFY/models/unet" "$COMFY/models/clip" "$COMFY/models/vae" "$COMFY/models/checkpoints"
cd "$COMFY"

# flux2-klein (Comfy-Org split files) — UI default model
echo "=== downloading flux2-klein unet (7.75GB) ==="
huggingface-cli download Comfy-Org/flux2-klein split_files/diffusion_models/flux-2-klein-4b.safetensors --local-dir /tmp/hf_klein 2>&1 | tail -2 || \
python3 -c "from huggingface_hub import hf_hub_download; hf_hub_download('Comfy-Org/flux2-klein','split_files/diffusion_models/flux-2-klein-4b.safetensors',local_dir='/tmp/hf_klein')" 2>&1 | tail -2
cp /tmp/hf_klein/split_files/diffusion_models/flux-2-klein-4b.safetensors "$COMFY/models/unet/" 2>/dev/null || true

echo "=== downloading qwen_3_4b clip (8GB) ==="
python3 -c "from huggingface_hub import hf_hub_download; hf_hub_download('Comfy-Org/flux2-klein','split_files/text_encoders/qwen_3_4b.safetensors',local_dir='/tmp/hf_klein')" 2>&1 | tail -2
cp /tmp/hf_klein/split_files/text_encoders/qwen_3_4b.safetensors "$COMFY/models/clip/" 2>/dev/null || true

echo "=== downloading flux2-vae (0.34GB) ==="
python3 -c "from huggingface_hub import hf_hub_download; hf_hub_download('Comfy-Org/flux2-klein','split_files/vae/flux2-vae.safetensors',local_dir='/tmp/hf_klein')" 2>&1 | tail -2
cp /tmp/hf_klein/split_files/vae/flux2-vae.safetensors "$COMFY/models/vae/" 2>/dev/null || true

# sdxl-turbo
echo "=== downloading sdxl-turbo (6.9GB) ==="
python3 -c "from huggingface_hub import hf_hub_download; hf_hub_download('stabilityai/sdxl-turbo','sd_xl_turbo_1.0_fp16.safetensors',local_dir='/tmp/hf_sdxl')" 2>&1 | tail -2
cp /tmp/hf_sdxl/sd_xl_turbo_1.0_fp16.safetensors "$COMFY/models/checkpoints/" 2>/dev/null || true

echo "=== DONE. Files now present: ==="
ls -la "$COMFY/models/unet/" 2>/dev/null | grep -i klein || true
ls -la "$COMFY/models/clip/" 2>/dev/null | grep -i qwen || true
ls -la "$COMFY/models/vae/" 2>/dev/null | grep -i flux2 || true
ls -la "$COMFY/models/checkpoints/" 2>/dev/null | grep -i turbo || true

#!/usr/bin/env python3
"""AI Studio Model Downloader — B2 cache with HuggingFace fallback.

Downloads AI models to the ComfyUI models directory.
Priority: local disk (already there) → B2 cache (fast) → HuggingFace (slow).

Usage:
    python download_models.py --models "sdxl-turbo,flux-dev"

Environment:
    B2_KEY_ID — Backblaze B2 key for model cache
    B2_APPLICATION_KEY — Backblaze B2 app key
    HF_TOKEN — HuggingFace token for gated models
"""

import argparse
import os
import sys
from pathlib import Path

COMFYUI_DIR = Path("/workspace/ComfyUI/models")

# Model registry: what files each model needs and where to get them
MODEL_REGISTRY = {
    "sdxl-turbo": {
        "files": [
            {
                "path": "checkpoints/sd_xl_turbo_1.0_fp16.safetensors",
                "b2_key": "models/sd_xl_turbo_1.0_fp16.safetensors",
                "hf_repo": "stabilityai/sdxl-turbo",
                "hf_file": "sd_xl_turbo_1.0_fp16.safetensors",
                "size_gb": 6.94,
            }
        ],
    },
    "flux-dev": {
        "files": [
            {
                "path": "unet/flux1-dev-fp8.safetensors",
                "b2_key": "models/flux1-dev-fp8.safetensors",
                "hf_repo": "Comfy-Org/flux1-dev",
                "hf_file": "flux1-dev-fp8.safetensors",
                "size_gb": 17.2,
            },
            {
                "path": "clip/clip_l.safetensors",
                "b2_key": "models/clip_l.safetensors",
                "hf_repo": "comfyanonymous/flux_text_encoders",
                "hf_file": "clip_l.safetensors",
                "size_gb": 0.24,
            },
            {
                "path": "clip/t5xxl_fp16.safetensors",
                "b2_key": "models/t5xxl_fp16.safetensors",
                "hf_repo": "comfyanonymous/flux_text_encoders",
                "hf_file": "t5xxl_fp16.safetensors",
                "size_gb": 9.8,
            },
            {
                "path": "vae/ae.safetensors",
                "b2_key": "models/ae.safetensors",
                "hf_repo": "black-forest-labs/FLUX.1-dev",
                "hf_file": "ae.safetensors",
                "size_gb": 0.32,
            },
        ],
    },
    "sd15": {
        "files": [
            {
                "path": "checkpoints/v1-5-pruned-emaonly.safetensors",
                "b2_key": "models/v1-5-pruned-emaonly.safetensors",
                "hf_repo": "stable-diffusion-v1-5/stable-diffusion-v1-5",
                "hf_file": "v1-5-pruned-emaonly.safetensors",
                "size_gb": 4.27,
            }
        ],
    },
}


def download_from_b2(b2_key: str, local_path: Path) -> bool:
    """Try to download from Backblaze B2 model cache."""
    key_id = os.getenv("B2_KEY_ID", "")
    app_key = os.getenv("B2_APPLICATION_KEY", "")
    bucket_name = os.getenv("B2_BUCKET_NAME", "ai-studio88")

    if not key_id or not app_key:
        return False

    try:
        from b2sdk.v2 import B2Api, InMemoryAccountInfo

        info = InMemoryAccountInfo()
        b2_api = B2Api(info)
        b2_api.authorize_account("production", key_id, app_key)
        bucket = b2_api.get_bucket_by_name(bucket_name)

        local_path.parent.mkdir(parents=True, exist_ok=True)
        bucket.download_file_by_name(b2_key).save_to(str(local_path))
        return True
    except Exception as e:
        print(f"      B2 download failed: {e}")
        return False


def download_from_hf(repo: str, filename: str, local_path: Path) -> bool:
    """Download from HuggingFace Hub."""
    try:
        from huggingface_hub import hf_hub_download

        token = os.getenv("HF_TOKEN", "") or None
        local_dir = str(local_path.parent)
        hf_hub_download(repo, filename, local_dir=local_dir, token=token)
        return True
    except Exception as e:
        print(f"      HF download failed: {e}")
        return False


def download_model_file(file_info: dict) -> bool:
    """Download a single model file using the priority chain."""
    local_path = COMFYUI_DIR / file_info["path"]

    # Already exists?
    if local_path.exists() and local_path.stat().st_size > 1_000_000:
        print(f"      ✓ {file_info['path']} (already on disk)")
        return True

    local_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"      ↓ {file_info['path']} ({file_info['size_gb']}GB)")

    # Try B2 first (faster, same region)
    if download_from_b2(file_info["b2_key"], local_path):
        print(f"      ✓ {file_info['path']} (from B2 cache)")
        return True

    # Fall back to HuggingFace
    if download_from_hf(file_info["hf_repo"], file_info["hf_file"], local_path):
        print(f"      ✓ {file_info['path']} (from HuggingFace)")
        return True

    print(f"      ✗ {file_info['path']} FAILED")
    return False


def main():
    parser = argparse.ArgumentParser(description="Download AI models for ComfyUI")
    parser.add_argument("--models", default="sdxl-turbo", help="Comma-separated model IDs")
    args = parser.parse_args()

    models_to_load = [m.strip() for m in args.models.split(",") if m.strip()]
    print(f"  Models requested: {', '.join(models_to_load)}")

    total_files = 0
    downloaded = 0

    for model_id in models_to_load:
        if model_id not in MODEL_REGISTRY:
            print(f"  ⚠ Unknown model: {model_id} (skipping)")
            continue

        model = MODEL_REGISTRY[model_id]
        print(f"  [{model_id}]")

        for file_info in model["files"]:
            total_files += 1
            if download_model_file(file_info):
                downloaded += 1

    print(f"  Result: {downloaded}/{total_files} files ready")

    if downloaded == 0 and total_files > 0:
        print("  WARNING: No models loaded! Generation will fail.")
        print("  Set B2_KEY_ID + B2_APPLICATION_KEY or HF_TOKEN in environment.")
        sys.exit(1)


if __name__ == "__main__":
    main()

"""Model Cache — Backblaze B2 + HuggingFace download layer.

Provides a two-tier download strategy for AI models:
1. Check Backblaze B2 model cache (fast, no rate limits)
2. Fall back to HuggingFace Hub (slower, may be rate-limited)

Models are stored in B2 under: {MODEL_CACHE_PREFIX}{model_type}/{filename}
Example: models/checkpoints/sd_xl_turbo_1.0_fp16.safetensors
"""
from __future__ import annotations

import os
import hashlib
from pathlib import Path
from typing import Optional

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

# ── Configuration ─────────────────────────────────────────────────────────────

B2_KEY_ID = os.getenv("B2_KEY_ID", "")
B2_APPLICATION_KEY = os.getenv("B2_APPLICATION_KEY", "")
B2_ENDPOINT_URL = os.getenv("B2_ENDPOINT_URL", "")
B2_REGION = os.getenv("B2_REGION", "us-east-005")

MODEL_CACHE_BUCKET = os.getenv("MODEL_CACHE_BUCKET", os.getenv("B2_BUCKET_NAME", ""))
MODEL_CACHE_PREFIX = os.getenv("MODEL_CACHE_PREFIX", "models/")
MODEL_CACHE_ENABLED = os.getenv("MODEL_CACHE_ENABLED", "true").lower() == "true"

HF_TOKEN = os.getenv("HF_TOKEN", "")

# Model type → subfolder mapping (matches ComfyUI directory structure)
MODEL_TYPES = {
    "checkpoint": "checkpoints",
    "lora": "loras",
    "vae": "vae",
    "controlnet": "controlnet",
    "upscaler": "upscale_models",
    "clip": "clip",
    "embedding": "embeddings",
}


class ModelCacheError(Exception):
    """Raised when model cache operations fail."""


# ── B2 Client ─────────────────────────────────────────────────────────────────

def _get_b2_client():
    """Create boto3 S3 client for Backblaze B2."""
    if not B2_KEY_ID or not B2_APPLICATION_KEY:
        raise ModelCacheError("B2_KEY_ID and B2_APPLICATION_KEY required for model cache")
    return boto3.client(
        "s3",
        endpoint_url=B2_ENDPOINT_URL,
        aws_access_key_id=B2_KEY_ID,
        aws_secret_access_key=B2_APPLICATION_KEY,
        region_name=B2_REGION,
    )


def _cache_key(model_type: str, filename: str) -> str:
    """Build the B2 storage key for a model file."""
    subfolder = MODEL_TYPES.get(model_type, model_type)
    return f"{MODEL_CACHE_PREFIX}{subfolder}/{filename}"


# ── Cache Operations ──────────────────────────────────────────────────────────

def model_exists_in_cache(model_type: str, filename: str) -> bool:
    """Check if a model file exists in the B2 cache."""
    if not MODEL_CACHE_ENABLED:
        return False
    try:
        client = _get_b2_client()
        key = _cache_key(model_type, filename)
        # Use list_objects with exact prefix (more reliable on B2 than head_object)
        resp = client.list_objects_v2(Bucket=MODEL_CACHE_BUCKET, Prefix=key, MaxKeys=1)
        contents = resp.get("Contents", [])
        return len(contents) > 0 and contents[0].get("Key") == key
    except ClientError:
        return False
    except ModelCacheError:
        return False


def get_cache_download_url(model_type: str, filename: str, expires_in: int = 3600) -> Optional[str]:
    """Get a signed download URL for a cached model."""
    if not MODEL_CACHE_ENABLED:
        return None
    try:
        client = _get_b2_client()
        key = _cache_key(model_type, filename)
        # Verify exists first via list
        resp = client.list_objects_v2(Bucket=MODEL_CACHE_BUCKET, Prefix=key, MaxKeys=1)
        contents = resp.get("Contents", [])
        if not contents or contents[0].get("Key") != key:
            return None
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": MODEL_CACHE_BUCKET, "Key": key},
            ExpiresIn=expires_in,
        )
    except (ClientError, ModelCacheError):
        return None


def upload_to_cache(
    local_path: str,
    model_type: str,
    filename: Optional[str] = None,
    content_type: str = "application/octet-stream",
) -> str:
    """Upload a local model file to the B2 cache.

    Args:
        local_path: Path to the local file
        model_type: One of: checkpoint, lora, vae, controlnet, upscaler, clip, embedding
        filename: Override filename (defaults to basename of local_path)
        content_type: MIME type

    Returns:
        The B2 storage key
    """
    path = Path(local_path)
    if not path.exists():
        raise ModelCacheError(f"File not found: {local_path}")

    fname = filename or path.name
    key = _cache_key(model_type, fname)
    file_size = path.stat().st_size

    print(f"[INFO] Uploading {fname} ({file_size / 1e9:.2f} GB) to B2 cache...")
    print(f"       Key: {key}")

    client = _get_b2_client()

    # Use multipart upload for files > 100MB
    if file_size > 100 * 1024 * 1024:
        config = boto3.s3.transfer.TransferConfig(
            multipart_threshold=100 * 1024 * 1024,
            multipart_chunksize=100 * 1024 * 1024,
            max_concurrency=4,
        )
        client.upload_file(
            str(path),
            MODEL_CACHE_BUCKET,
            key,
            Config=config,
            ExtraArgs={"ContentType": content_type},
        )
    else:
        with open(path, "rb") as f:
            client.put_object(
                Bucket=MODEL_CACHE_BUCKET,
                Key=key,
                Body=f,
                ContentType=content_type,
            )

    print(f"[OK] Uploaded to: s3://{MODEL_CACHE_BUCKET}/{key}")
    return key


def download_from_cache(
    model_type: str,
    filename: str,
    dest_dir: str,
) -> Optional[str]:
    """Download a model file from B2 cache to a local directory.

    Args:
        model_type: Model type (checkpoint, lora, etc.)
        filename: The filename to download
        dest_dir: Local directory to save into

    Returns:
        Local file path if successful, None if not in cache
    """
    if not MODEL_CACHE_ENABLED:
        return None

    key = _cache_key(model_type, filename)
    dest_path = Path(dest_dir) / filename

    try:
        client = _get_b2_client()
        # Check exists
        client.head_object(Bucket=MODEL_CACHE_BUCKET, Key=key)

        print(f"[INFO] Downloading from B2 cache: {key}")
        Path(dest_dir).mkdir(parents=True, exist_ok=True)

        config = boto3.s3.transfer.TransferConfig(
            multipart_threshold=100 * 1024 * 1024,
            max_concurrency=4,
        )
        client.download_file(
            MODEL_CACHE_BUCKET,
            key,
            str(dest_path),
            Config=config,
        )
        print(f"[OK] Downloaded to: {dest_path} ({dest_path.stat().st_size / 1e9:.2f} GB)")
        return str(dest_path)
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey"):
            return None
        raise ModelCacheError(f"B2 download failed: {e}")
    except ModelCacheError:
        return None


def list_cached_models(model_type: Optional[str] = None) -> list[dict]:
    """List all models in the B2 cache.

    Args:
        model_type: Filter by type, or None for all

    Returns:
        List of dicts with key, filename, size, last_modified
    """
    try:
        client = _get_b2_client()
    except ModelCacheError:
        return []

    prefix = MODEL_CACHE_PREFIX
    if model_type:
        subfolder = MODEL_TYPES.get(model_type, model_type)
        prefix = f"{MODEL_CACHE_PREFIX}{subfolder}/"

    try:
        response = client.list_objects_v2(Bucket=MODEL_CACHE_BUCKET, Prefix=prefix)
        contents = response.get("Contents", [])
        results = []
        for obj in contents:
            key = obj["Key"]
            filename = key.split("/")[-1]
            if not filename:
                continue
            results.append({
                "key": key,
                "filename": filename,
                "size_bytes": obj["Size"],
                "size_gb": round(obj["Size"] / 1e9, 2),
                "last_modified": obj["LastModified"].isoformat(),
                "model_type": key.replace(MODEL_CACHE_PREFIX, "").split("/")[0],
            })
        return results
    except ClientError:
        return []


# ── HuggingFace Download ──────────────────────────────────────────────────────

def download_from_huggingface(
    repo_id: str,
    filename: str,
    dest_dir: str,
    token: Optional[str] = None,
) -> str:
    """Download a model file from HuggingFace Hub.

    Args:
        repo_id: HuggingFace repo (e.g. "stabilityai/sdxl-turbo")
        filename: File within the repo
        dest_dir: Local directory to save into
        token: HF token (uses HF_TOKEN env var if not provided)

    Returns:
        Local file path
    """
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        raise ModelCacheError("huggingface_hub not installed. Run: pip install huggingface-hub")

    hf_token = token or HF_TOKEN or None

    print(f"[INFO] Downloading from HuggingFace: {repo_id}/{filename}")
    if hf_token:
        print(f"       Using authenticated download (HF_TOKEN set)")
    else:
        print(f"       WARNING: Unauthenticated download — may be rate-limited")

    path = hf_hub_download(
        repo_id=repo_id,
        filename=filename,
        local_dir=dest_dir,
        token=hf_token,
    )
    print(f"[OK] Downloaded to: {path}")
    return path


# ── Smart Download (Cache-first) ─────────────────────────────────────────────

def smart_download(
    model_type: str,
    filename: str,
    dest_dir: str,
    hf_repo: Optional[str] = None,
    hf_filename: Optional[str] = None,
) -> str:
    """Download a model using the best available source.

    Priority:
    1. Check if already exists locally
    2. Try Backblaze B2 cache
    3. Fall back to HuggingFace Hub

    Args:
        model_type: checkpoint, lora, vae, etc.
        filename: Target filename
        dest_dir: Destination directory
        hf_repo: HuggingFace repo ID (for fallback)
        hf_filename: Filename in HF repo (defaults to filename)

    Returns:
        Local file path
    """
    dest_path = Path(dest_dir) / filename

    # 1. Already exists locally?
    if dest_path.exists() and dest_path.stat().st_size > 0:
        print(f"[OK] Model already exists: {dest_path} ({dest_path.stat().st_size / 1e9:.2f} GB)")
        return str(dest_path)

    # 2. Try B2 cache
    cached = download_from_cache(model_type, filename, dest_dir)
    if cached:
        return cached

    # 3. Fall back to HuggingFace
    if hf_repo:
        hf_file = hf_filename or filename
        return download_from_huggingface(hf_repo, hf_file, dest_dir)

    raise ModelCacheError(
        f"Model '{filename}' not found locally, in B2 cache, or HuggingFace repo not specified"
    )


# ── Model Registry (known models) ────────────────────────────────────────────

KNOWN_MODELS = {
    "sd15-pruned": {
        "filename": "v1-5-pruned-emaonly.safetensors",
        "model_type": "checkpoint",
        "hf_repo": "stable-diffusion-v1-5/stable-diffusion-v1-5",
        "hf_filename": "v1-5-pruned-emaonly.safetensors",
        "size_gb": 4.3,
        "description": "SD 1.5 pruned — small, fast, good for smoke tests",
    },
    "sdxl-turbo": {
        "filename": "sd_xl_turbo_1.0_fp16.safetensors",
        "model_type": "checkpoint",
        "hf_repo": "stabilityai/sdxl-turbo",
        "hf_filename": "sd_xl_turbo_1.0_fp16.safetensors",
        "size_gb": 6.5,
        "description": "SDXL Turbo — 1-step generation, fastest for testing",
    },
    "sdxl-base": {
        "filename": "sd_xl_base_1.0.safetensors",
        "model_type": "checkpoint",
        "hf_repo": "stabilityai/stable-diffusion-xl-base-1.0",
        "hf_filename": "sd_xl_base_1.0.safetensors",
        "size_gb": 6.9,
        "description": "SDXL Base 1.0 — production quality",
    },
    "wan-2.1-t2v": {
        "filename": "wan2.1_t2v_14B_bf16.safetensors",
        "model_type": "checkpoint",
        "hf_repo": "Wan-AI/Wan2.1-T2V-14B",
        "hf_filename": "diffusion_pytorch_model.safetensors",
        "size_gb": 28.3,
        "description": "WAN 2.1 Text-to-Video 14B — video generation",
    },
    "wan-2.1-i2v": {
        "filename": "wan2.1_i2v_14B_bf16.safetensors",
        "model_type": "checkpoint",
        "hf_repo": "Wan-AI/Wan2.1-I2V-14B-720P",
        "hf_filename": "diffusion_pytorch_model.safetensors",
        "size_gb": 28.3,
        "description": "WAN 2.1 Image-to-Video 14B 720P — video from images",
    },
    "flux-dev": {
        "filename": "flux1-dev.safetensors",
        "model_type": "checkpoint",
        "hf_repo": "black-forest-labs/FLUX.1-dev",
        "hf_filename": "flux1-dev.safetensors",
        "size_gb": 12.0,
        "description": "Flux Dev — highest quality, needs 24GB+ VRAM",
    },
    "sdxl-vae": {
        "filename": "sdxl_vae.safetensors",
        "model_type": "vae",
        "hf_repo": "stabilityai/sdxl-vae",
        "hf_filename": "sdxl_vae.safetensors",
        "size_gb": 0.3,
        "description": "SDXL VAE — required for SDXL models",
    },
}


def get_known_model(name: str) -> Optional[dict]:
    """Look up a model by short name."""
    return KNOWN_MODELS.get(name)


def list_known_models() -> list[dict]:
    """List all known/supported models."""
    return [{"name": k, **v} for k, v in KNOWN_MODELS.items()]

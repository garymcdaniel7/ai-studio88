#!/usr/bin/env python3
"""Cache Ollama model weights to Backblaze B2 for GPU worker deployment.

Copies the local Ollama model files to B2 so GPU workers can download
them quickly without pulling from the Ollama registry every time.

Usage:
    python scripts/vast/cache_ollama_model.py --model llama3.2
    python scripts/vast/cache_ollama_model.py --model llama3.1:8b
    python scripts/vast/cache_ollama_model.py --list
"""
import sys
import os
import argparse
import subprocess
import json
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from dotenv import load_dotenv
load_dotenv()

import boto3
from boto3.s3.transfer import TransferConfig

B2_KEY_ID = os.getenv("B2_KEY_ID", "")
B2_APPLICATION_KEY = os.getenv("B2_APPLICATION_KEY", "")
B2_ENDPOINT_URL = os.getenv("B2_ENDPOINT_URL", "")
B2_REGION = os.getenv("B2_REGION", "us-east-005")
MODEL_CACHE_BUCKET = os.getenv("MODEL_CACHE_BUCKET", os.getenv("B2_BUCKET_NAME", ""))

OLLAMA_DIR = Path.home() / ".ollama" / "models"


def get_model_path(model_name: str) -> Path | None:
    """Find the model blob directory for an Ollama model."""
    # Ollama stores models as manifests + blobs
    # The manifest is at ~/.ollama/models/manifests/registry.ollama.ai/library/{model}/{tag}
    parts = model_name.split(":")
    name = parts[0]
    tag = parts[1] if len(parts) > 1 else "latest"

    manifest_path = OLLAMA_DIR / "manifests" / "registry.ollama.ai" / "library" / name / tag
    if not manifest_path.exists():
        return None
    return manifest_path


def get_model_blobs(model_name: str) -> list[Path]:
    """Get all blob files for a model."""
    manifest_path = get_model_path(model_name)
    if not manifest_path:
        return []

    try:
        manifest = json.loads(manifest_path.read_text())
        blobs = []
        # Get config blob
        config = manifest.get("config", {})
        if config.get("digest"):
            blob = OLLAMA_DIR / "blobs" / config["digest"].replace(":", "-")
            if blob.exists():
                blobs.append(blob)
        # Get layer blobs
        for layer in manifest.get("layers", []):
            digest = layer.get("digest", "")
            blob = OLLAMA_DIR / "blobs" / digest.replace(":", "-")
            if blob.exists():
                blobs.append(blob)
        return blobs
    except Exception as e:
        print(f"[ERROR] Failed to parse manifest: {e}")
        return []


def list_local_models():
    """List locally available Ollama models."""
    try:
        result = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print(result.stdout)
        else:
            print("[ERROR] Cannot list models. Is Ollama running?")
    except FileNotFoundError:
        print("[ERROR] Ollama not installed")


def upload_model_to_b2(model_name: str, force: bool = False):
    """Upload Ollama model blobs to B2."""
    blobs = get_model_blobs(model_name)
    if not blobs:
        print(f"[ERROR] Model '{model_name}' not found locally.")
        print(f"        Pull it first: ollama pull {model_name}")
        return

    total_size = sum(b.stat().st_size for b in blobs)
    print(f"[INFO] Model: {model_name}")
    print(f"       Blobs: {len(blobs)} files, {total_size/1e9:.2f} GB total")

    # Also save the manifest
    manifest_path = get_model_path(model_name)

    client = boto3.client("s3", endpoint_url=B2_ENDPOINT_URL,
                          aws_access_key_id=B2_KEY_ID,
                          aws_secret_access_key=B2_APPLICATION_KEY,
                          region_name=B2_REGION)
    config = TransferConfig(multipart_threshold=100*1024*1024,
                           multipart_chunksize=100*1024*1024, max_concurrency=4)

    # Upload manifest
    safe_name = model_name.replace(":", "_").replace("/", "_")
    manifest_key = f"models/ollama/{safe_name}/manifest.json"
    print(f"[INFO] Uploading manifest...")
    client.upload_file(str(manifest_path), MODEL_CACHE_BUCKET, manifest_key)

    # Upload blobs
    for i, blob in enumerate(blobs):
        blob_key = f"models/ollama/{safe_name}/blobs/{blob.name}"
        size_gb = blob.stat().st_size / 1e9
        print(f"[INFO] Uploading blob {i+1}/{len(blobs)} ({size_gb:.2f} GB)...")
        try:
            client.upload_file(str(blob), MODEL_CACHE_BUCKET, blob_key, Config=config)
        except Exception as e:
            print(f"[ERROR] Upload failed: {e}")
            print(f"        You may need to increase your B2 storage cap.")
            return

    print(f"\n[OK] Model '{model_name}' cached in B2!")
    print(f"     Key prefix: models/ollama/{safe_name}/")
    print(f"     Total uploaded: {total_size/1e9:.2f} GB")


def main():
    parser = argparse.ArgumentParser(description="Cache Ollama models to B2")
    parser.add_argument("--model", help="Model name (e.g. llama3.2, llama3.1:8b)")
    parser.add_argument("--list", action="store_true", help="List local models")
    parser.add_argument("--force", action="store_true", help="Re-upload even if exists")
    args = parser.parse_args()

    if args.list:
        list_local_models()
        return

    if not args.model:
        print("[ERROR] --model required. Use --list to see available models.")
        sys.exit(1)

    if not B2_KEY_ID or not B2_APPLICATION_KEY:
        print("[ERROR] B2 credentials not configured in .env")
        sys.exit(1)

    upload_model_to_b2(args.model, force=args.force)


if __name__ == "__main__":
    main()

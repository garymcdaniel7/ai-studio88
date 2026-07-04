#!/usr/bin/env python3
"""Upload a model file to Backblaze B2 model cache.

Supports uploading local files or downloading from HuggingFace first.

Usage:
    # Upload a local file
    python scripts/vast/upload_model.py --file ./sd_xl_turbo_1.0_fp16.safetensors --type checkpoint

    # Download from HuggingFace and upload to cache
    python scripts/vast/upload_model.py --hf stabilityai/sdxl-turbo --hf-file sd_xl_turbo_1.0_fp16.safetensors --type checkpoint

    # Upload a known model by name
    python scripts/vast/upload_model.py --known sdxl-turbo

    # List cached models
    python scripts/vast/upload_model.py --list

    # List known models
    python scripts/vast/upload_model.py --list-known
"""
import sys
import os
import argparse
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv
load_dotenv()

from backend.providers.vast.model_cache import (
    upload_to_cache,
    list_cached_models,
    list_known_models,
    get_known_model,
    download_from_huggingface,
    model_exists_in_cache,
    ModelCacheError,
)


def main():
    parser = argparse.ArgumentParser(description="Upload models to Backblaze B2 cache")
    parser.add_argument("--file", help="Local file path to upload")
    parser.add_argument("--type", choices=["checkpoint", "lora", "vae", "controlnet", "upscaler", "clip", "embedding"],
                        help="Model type (determines subfolder)")
    parser.add_argument("--hf", help="HuggingFace repo ID (e.g. stabilityai/sdxl-turbo)")
    parser.add_argument("--hf-file", help="Filename in the HF repo")
    parser.add_argument("--known", help="Upload a known model by name (e.g. sdxl-turbo)")
    parser.add_argument("--list", action="store_true", help="List all cached models")
    parser.add_argument("--list-known", action="store_true", help="List known/supported models")
    parser.add_argument("--force", action="store_true", help="Re-upload even if already cached")
    args = parser.parse_args()

    if args.list:
        models = list_cached_models()
        if not models:
            print("[INFO] No models in cache (or B2 not configured)")
            return
        print(f"[OK] {len(models)} model(s) in B2 cache:\n")
        print(f"{'Type':<14} {'Filename':<45} {'Size'}")
        print("-" * 70)
        for m in models:
            print(f"{m['model_type']:<14} {m['filename']:<45} {m['size_gb']} GB")
        return

    if args.list_known:
        models = list_known_models()
        print(f"[INFO] {len(models)} known models:\n")
        print(f"{'Name':<14} {'Type':<12} {'Size':<8} {'Description'}")
        print("-" * 80)
        for m in models:
            print(f"{m['name']:<14} {m['model_type']:<12} {m['size_gb']:<8} {m['description']}")
        return

    # Upload a known model
    if args.known:
        model = get_known_model(args.known)
        if not model:
            print(f"[ERROR] Unknown model '{args.known}'. Use --list-known to see options.")
            sys.exit(1)

        filename = model["filename"]
        model_type = model["model_type"]

        if not args.force and model_exists_in_cache(model_type, filename):
            print(f"[OK] '{filename}' already exists in cache. Use --force to re-upload.")
            return

        # Download from HF first
        print(f"[INFO] Downloading '{args.known}' from HuggingFace...")
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                local_path = download_from_huggingface(
                    model["hf_repo"], model["hf_filename"], tmpdir
                )
                upload_to_cache(local_path, model_type, filename)
                print(f"\n[OK] '{args.known}' uploaded to B2 cache successfully!")
            except ModelCacheError as e:
                print(f"[ERROR] {e}")
                sys.exit(1)
        return

    # Upload from HuggingFace
    if args.hf:
        if not args.hf_file:
            print("[ERROR] --hf-file required when using --hf")
            sys.exit(1)
        if not args.type:
            print("[ERROR] --type required when using --hf")
            sys.exit(1)

        filename = args.hf_file
        if not args.force and model_exists_in_cache(args.type, filename):
            print(f"[OK] '{filename}' already in cache. Use --force to re-upload.")
            return

        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                local_path = download_from_huggingface(args.hf, args.hf_file, tmpdir)
                upload_to_cache(local_path, args.type, filename)
                print(f"\n[OK] Uploaded to B2 cache!")
            except ModelCacheError as e:
                print(f"[ERROR] {e}")
                sys.exit(1)
        return

    # Upload a local file
    if args.file:
        if not args.type:
            print("[ERROR] --type required when using --file")
            sys.exit(1)
        if not os.path.exists(args.file):
            print(f"[ERROR] File not found: {args.file}")
            sys.exit(1)

        filename = os.path.basename(args.file)
        if not args.force and model_exists_in_cache(args.type, filename):
            print(f"[OK] '{filename}' already in cache. Use --force to re-upload.")
            return

        try:
            upload_to_cache(args.file, args.type, filename)
            print(f"\n[OK] Uploaded to B2 cache!")
        except ModelCacheError as e:
            print(f"[ERROR] {e}")
            sys.exit(1)
        return

    parser.print_help()


if __name__ == "__main__":
    main()

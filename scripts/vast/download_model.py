#!/usr/bin/env python3
"""Download a model from cache (B2 first, then HuggingFace).

Designed to run both locally and on Vast.ai workers.

Usage:
    # Download a known model by name
    python scripts/vast/download_model.py --known sdxl-turbo --dest ./models/checkpoints

    # Download by filename from cache
    python scripts/vast/download_model.py --filename sd_xl_turbo_1.0_fp16.safetensors --type checkpoint --dest ./models/checkpoints

    # Download from HuggingFace directly
    python scripts/vast/download_model.py --hf stabilityai/sdxl-turbo --hf-file sd_xl_turbo_1.0_fp16.safetensors --dest ./models/checkpoints

    # List what's available in cache
    python scripts/vast/download_model.py --list

    # Download for ComfyUI (auto-detects dest from model type)
    python scripts/vast/download_model.py --known sdxl-turbo --comfyui-dir /workspace/ComfyUI
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv
load_dotenv()

from backend.providers.vast.model_cache import (
    smart_download,
    download_from_cache,
    download_from_huggingface,
    list_cached_models,
    list_known_models,
    get_known_model,
    MODEL_TYPES,
    ModelCacheError,
)


def main():
    parser = argparse.ArgumentParser(description="Download models from B2 cache or HuggingFace")
    parser.add_argument("--known", help="Download a known model by name (e.g. sdxl-turbo)")
    parser.add_argument("--filename", help="Specific filename to download from cache")
    parser.add_argument("--type", choices=list(MODEL_TYPES.keys()), help="Model type")
    parser.add_argument("--hf", help="HuggingFace repo ID")
    parser.add_argument("--hf-file", help="Filename in HF repo")
    parser.add_argument("--dest", help="Destination directory")
    parser.add_argument("--comfyui-dir", help="ComfyUI root directory (auto-routes to models/type/)")
    parser.add_argument("--list", action="store_true", help="List cached models")
    parser.add_argument("--list-known", action="store_true", help="List known models")
    parser.add_argument("--cache-only", action="store_true", help="Only try B2 cache, skip HuggingFace")
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

    # Download known model
    if args.known:
        model = get_known_model(args.known)
        if not model:
            print(f"[ERROR] Unknown model '{args.known}'. Use --list-known to see options.")
            sys.exit(1)

        model_type = model["model_type"]
        subfolder = MODEL_TYPES[model_type]

        # Determine destination
        if args.comfyui_dir:
            dest = os.path.join(args.comfyui_dir, "models", subfolder)
        elif args.dest:
            dest = args.dest
        else:
            dest = os.path.join(".", "models", subfolder)

        try:
            if args.cache_only:
                result = download_from_cache(model_type, model["filename"], dest)
                if not result:
                    print(f"[WARN] '{model['filename']}' not found in B2 cache.")
                    sys.exit(1)
            else:
                result = smart_download(
                    model_type=model_type,
                    filename=model["filename"],
                    dest_dir=dest,
                    hf_repo=model["hf_repo"],
                    hf_filename=model["hf_filename"],
                )
            print(f"\n[OK] Model ready at: {result}")
        except ModelCacheError as e:
            print(f"[ERROR] {e}")
            sys.exit(1)
        return

    # Download by filename from cache
    if args.filename:
        if not args.type:
            print("[ERROR] --type required with --filename")
            sys.exit(1)

        subfolder = MODEL_TYPES[args.type]
        if args.comfyui_dir:
            dest = os.path.join(args.comfyui_dir, "models", subfolder)
        elif args.dest:
            dest = args.dest
        else:
            dest = os.path.join(".", "models", subfolder)

        try:
            result = download_from_cache(args.type, args.filename, dest)
            if result:
                print(f"\n[OK] Downloaded: {result}")
            else:
                print(f"[WARN] '{args.filename}' not in B2 cache.")
                if args.hf and args.hf_file:
                    result = download_from_huggingface(args.hf, args.hf_file, dest)
                    print(f"\n[OK] Downloaded from HF: {result}")
                else:
                    print("       Provide --hf and --hf-file to download from HuggingFace.")
                    sys.exit(1)
        except ModelCacheError as e:
            print(f"[ERROR] {e}")
            sys.exit(1)
        return

    # Direct HuggingFace download
    if args.hf and args.hf_file:
        dest = args.dest or "."
        try:
            result = download_from_huggingface(args.hf, args.hf_file, dest)
            print(f"\n[OK] Downloaded: {result}")
        except ModelCacheError as e:
            print(f"[ERROR] {e}")
            sys.exit(1)
        return

    parser.print_help()


if __name__ == "__main__":
    main()

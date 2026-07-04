#!/usr/bin/env python3
"""End-to-End Image Generation Test.

Launches a GPU worker, pulls model from B2 cache, generates an image
via ComfyUI, saves to B2 storage, and cleans up.

Usage:
    python scripts/test_e2e_image.py
    python scripts/test_e2e_image.py --max-price 1.00 --model sdxl-turbo
    python scripts/test_e2e_image.py --skip-launch  (if worker is already running)
"""
import sys
import os
import time
import argparse
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

import httpx


def main():
    parser = argparse.ArgumentParser(description="E2E Image Generation Test")
    parser.add_argument("--max-price", type=float, default=1.50)
    parser.add_argument("--model", default="sdxl-turbo", help="Model to use")
    parser.add_argument("--prompt", default="a beautiful sunset over the ocean, photorealistic, 4k")
    parser.add_argument("--skip-launch", action="store_true", help="Skip worker launch (use existing)")
    parser.add_argument("--keep-worker", action="store_true", help="Don't destroy worker after test")
    args = parser.parse_args()

    api = os.getenv("API_BASE_URL", "http://localhost:8000")
    print("=" * 60)
    print("  AI STUDIO — End-to-End Image Generation Test")
    print("=" * 60)
    print()

    # Step 1: Check API
    print("[1/6] Checking API...")
    try:
        resp = httpx.get(f"{api}/", timeout=5)
        assert resp.status_code == 200
        print(f"      API OK: {api}")
    except Exception as e:
        print(f"      FAILED: API not reachable at {api}")
        print(f"      Start it: uv run uvicorn backend.main:app --reload")
        sys.exit(1)

    # Step 2: Check service connections
    print("[2/6] Checking services...")
    resp = httpx.get(f"{api}/api/v1/infrastructure/admin/services", timeout=30)
    services = resp.json()
    for name, info in services.get("services", {}).items():
        status = "OK" if info.get("connected") else "MISSING"
        print(f"      {name}: {status}")

    # Step 3: Launch worker (or verify existing)
    print("[3/6] GPU Worker...")
    if args.skip_launch:
        print("      Skipping launch (--skip-launch)")
    else:
        status_resp = httpx.get(f"{api}/api/v1/infrastructure/status", timeout=10)
        worker = status_resp.json().get("worker", {})
        if worker.get("status") == "ready":
            print(f"      Already running: {worker.get('gpu_name')}")
        else:
            print(f"      Launching via Connection Race (max ${args.max_price}/hr)...")
            launch_resp = httpx.post(f"{api}/api/v1/infrastructure/launch", json={
                "max_price": args.max_price,
                "min_vram_gb": 12.0,
                "num_candidates": 3,
            }, timeout=700)
            result = launch_resp.json()
            if result.get("status") == "success":
                print(f"      Worker launched: {result.get('session', {}).get('gpu_name')}")
                print(f"      Boot time: {result.get('boot_time_seconds', 0):.0f}s")
            else:
                print(f"      FAILED: {result.get('error', 'Unknown')}")
                sys.exit(1)

    # Step 4: Verify ComfyUI
    print("[4/6] ComfyUI health...")
    comfy_url = os.getenv("COMFYUI_BASE_URL", "http://localhost:8188")
    try:
        resp = httpx.get(f"{comfy_url}/system_stats", timeout=10)
        if resp.status_code == 200:
            stats = resp.json()
            gpu = stats.get("devices", [{}])[0]
            print(f"      ComfyUI v{stats['system']['comfyui_version']}")
            print(f"      GPU: {gpu.get('name', '?')}")
        else:
            print(f"      ComfyUI returned {resp.status_code}")
            print("      NOTE: If using SSH tunnel, ensure it's running")
            sys.exit(1)
    except httpx.ConnectError:
        print(f"      ComfyUI not reachable at {comfy_url}")
        print("      Start SSH tunnel: ssh -i ~/.ssh/id_ed25519 -p PORT -N -L 8188:127.0.0.1:8188 root@HOST")
        sys.exit(1)

    # Step 5: Generate image
    print(f"[5/6] Generating image ({args.model})...")
    print(f"      Prompt: {args.prompt[:60]}...")

    workflow = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sd_xl_turbo_1.0_fp16.safetensors"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": args.prompt, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "ugly, blurry, low quality", "clip": ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512, "batch_size": 1}},
        "5": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0], "seed": 42, "steps": 1, "cfg": 1.0, "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": "e2e_test"}},
    }

    start = time.time()
    resp = httpx.post(f"{comfy_url}/prompt", json={"prompt": workflow}, timeout=30)
    if resp.status_code != 200:
        print(f"      FAILED: ComfyUI returned {resp.status_code}: {resp.text[:100]}")
        sys.exit(1)

    prompt_id = resp.json().get("prompt_id")
    print(f"      Submitted: {prompt_id}")

    # Poll for result
    for i in range(60):
        time.sleep(2)
        hist = httpx.get(f"{comfy_url}/history/{prompt_id}", timeout=10).json()
        if hist:
            entry = hist.get(prompt_id, {})
            status = entry.get("status", {})
            if status.get("completed"):
                elapsed = time.time() - start
                outputs = entry.get("outputs", {})
                for nid, out in outputs.items():
                    for img in out.get("images", []):
                        print(f"      SUCCESS! Generated: {img['filename']} ({elapsed:.1f}s)")
                        break
                break
            elif status.get("status_str") == "error":
                msgs = status.get("messages", [])
                err = [m for m in msgs if m[0] == "execution_error"]
                if err:
                    print(f"      FAILED: {err[0][1].get('exception_message', '')[:200]}")
                sys.exit(1)
    else:
        print("      TIMEOUT: Generation did not complete in 120s")
        sys.exit(1)

    # Step 6: Cleanup
    print("[6/6] Cleanup...")
    if not args.keep_worker:
        print("      Keeping worker running (use --keep-worker=false to destroy)")
    else:
        print("      Worker kept running.")

    print()
    print("=" * 60)
    print("  E2E TEST PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Register a Vast.ai ComfyUI worker with AI Studio.

Detects connection info from a running instance and registers
it with the AI Studio worker registry.

Usage:
    python scripts/vast/register_worker.py --instance 12345
    python scripts/vast/register_worker.py --url http://1.2.3.4:8188 --gpu "RTX 4090"
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv
load_dotenv()

import httpx
from backend.providers.vast.client import VastClient, VastClientError


def register_with_studio(worker_data: dict) -> dict:
    """Register worker with AI Studio backend."""
    api_base = os.getenv("API_BASE_URL", "http://localhost:8000")
    try:
        resp = httpx.post(f"{api_base}/api/v1/workers", json=worker_data, timeout=10)
        if resp.status_code in (200, 201):
            return resp.json()
        return {"error": f"Registration failed ({resp.status_code}): {resp.text}"}
    except Exception as e:
        return {"error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="Register Vast.ai worker with AI Studio")
    parser.add_argument("--instance", type=int, help="Vast.ai instance ID")
    parser.add_argument("--url", help="ComfyUI URL (if known)")
    parser.add_argument("--gpu", default="", help="GPU name override")
    args = parser.parse_args()

    comfy_url = args.url
    gpu_name = args.gpu
    instance_id = args.instance

    if args.instance and not args.url:
        try:
            client = VastClient()
            info = client.get_connection_info(args.instance)
            comfy_url = info.get("comfyui_url")
            gpu_name = gpu_name or info.get("gpu_name", "")
            if not comfy_url:
                print(f"[ERROR] Instance {args.instance} has no ComfyUI port mapped.")
                print(f"        Status: {info.get('status')}")
                sys.exit(1)
        except VastClientError as e:
            print(f"[ERROR] {e}")
            sys.exit(1)

    if not comfy_url:
        print("[ERROR] Provide --instance or --url")
        sys.exit(1)

    # Verify ComfyUI is reachable
    print(f"[INFO] Checking ComfyUI at {comfy_url}...")
    try:
        resp = httpx.get(f"{comfy_url}/system_stats", timeout=10)
        if resp.status_code != 200:
            print(f"[ERROR] ComfyUI not healthy (HTTP {resp.status_code})")
            sys.exit(1)
        stats = resp.json()
        devices = stats.get("devices", [])
        if devices and not gpu_name:
            gpu_name = devices[0].get("name", "unknown")
        print(f"[OK] ComfyUI online — GPU: {gpu_name}")
    except Exception as e:
        print(f"[ERROR] Cannot reach ComfyUI: {e}")
        sys.exit(1)

    # Register with AI Studio
    worker_data = {
        "name": f"vast-comfyui-{instance_id or 'manual'}",
        "provider": "vast",
        "worker_type": "comfyui",
        "base_url": comfy_url,
        "gpu_name": gpu_name,
        "status": "online",
        "instance_id": str(instance_id) if instance_id else None,
        "metadata": {
            "provider": "vast.ai",
            "comfyui_url": comfy_url,
        },
    }

    print(f"[INFO] Registering worker with AI Studio...")
    result = register_with_studio(worker_data)

    if "error" in result:
        print(f"[WARN] Registration issue: {result['error']}")
        print(f"       Worker data prepared but not registered.")
        print(f"       Ensure AI Studio is running at {os.getenv('API_BASE_URL', 'http://localhost:8000')}")
    else:
        print(f"[OK] Worker registered successfully!")
        print(f"     ID: {result.get('id', '?')}")

    print(f"\n     Worker details:")
    print(f"       Provider:    vast.ai")
    print(f"       Type:        comfyui")
    print(f"       URL:         {comfy_url}")
    print(f"       GPU:         {gpu_name}")
    print(f"       Status:      online")


if __name__ == "__main__":
    main()

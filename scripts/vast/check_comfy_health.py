#!/usr/bin/env python3
"""Check ComfyUI health on a Vast.ai instance.

Usage:
    python scripts/vast/check_comfy_health.py --instance 12345
    python scripts/vast/check_comfy_health.py --url http://1.2.3.4:8188
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv
load_dotenv()

import httpx
from backend.providers.vast.client import VastClient, VastClientError


def check_comfyui(url: str) -> dict:
    """Check ComfyUI health at a given URL."""
    try:
        resp = httpx.get(f"{url}/system_stats", timeout=10)
        if resp.status_code == 200:
            return {"status": "healthy", "url": url, "data": resp.json()}
        return {"status": "unhealthy", "url": url, "code": resp.status_code}
    except httpx.ConnectError:
        return {"status": "unreachable", "url": url}
    except Exception as e:
        return {"status": "error", "url": url, "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="Check ComfyUI health")
    parser.add_argument("--instance", type=int, help="Vast.ai instance ID")
    parser.add_argument("--url", help="Direct ComfyUI URL")
    args = parser.parse_args()

    if args.url:
        comfy_url = args.url.rstrip("/")
    elif args.instance:
        try:
            client = VastClient()
            info = client.get_connection_info(args.instance)
            comfy_url = info.get("comfyui_url")
            if not comfy_url:
                print(f"[WARN] Instance {args.instance} has no ComfyUI port mapped yet.")
                print(f"       Status: {info.get('status')}")
                print(f"       GPU: {info.get('gpu_name')}")
                sys.exit(1)
        except VastClientError as e:
            print(f"[ERROR] {e}")
            sys.exit(1)
    else:
        comfy_url = os.getenv("COMFYUI_BASE_URL", "http://localhost:8188")

    print(f"[INFO] Checking ComfyUI at: {comfy_url}")
    result = check_comfyui(comfy_url)

    if result["status"] == "healthy":
        data = result.get("data", {})
        devices = data.get("devices", [])
        print(f"[OK] ComfyUI is healthy!")
        if devices:
            for d in devices:
                print(f"     GPU: {d.get('name', '?')} — VRAM: {d.get('vram_total', 0) / 1e9:.1f}GB")
    elif result["status"] == "unreachable":
        print(f"[ERROR] ComfyUI unreachable at {comfy_url}")
        print(f"        Instance may still be starting up. Wait and retry.")
        sys.exit(1)
    else:
        print(f"[ERROR] ComfyUI status: {result['status']}")
        sys.exit(1)


if __name__ == "__main__":
    main()

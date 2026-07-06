#!/usr/bin/env python3
"""Service Verification Script — checks all AI Studio connections.

Run: uv run python scripts/verify_services.py

Checks:
  1. Backend API health
  2. Supabase connection
  3. Backblaze B2 storage
  4. Vast.ai GPU provider
  5. RunPod GPU provider
  6. ComfyUI (local tunnel)
  7. Redis
  8. Ollama (local LLM)
  9. ElevenLabs (voice)
  10. Image generation (end-to-end)
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

import httpx

API_BASE = "http://localhost:8000"
COMFYUI_URL = os.getenv("COMFYUI_BASE_URL", "http://localhost:8188")

results = []


def check(name: str, fn):
    try:
        ok, detail = fn()
        status = "✅" if ok else "⚠️"
        results.append((name, ok, detail))
        print(f"  {status} {name}: {detail}")
    except Exception as e:
        results.append((name, False, str(e)))
        print(f"  ❌ {name}: {e}")


def check_backend():
    r = httpx.get(f"{API_BASE}/api/v1/health", timeout=5)
    return r.status_code == 200, f"HTTP {r.status_code}"


def check_supabase():
    from backend.database import supabase
    result = supabase.table("talent").select("id").limit(1).execute()
    return True, f"Connected ({len(result.data or [])} talent rows)"


def check_b2():
    from backend.storage import _get_client
    client = _get_client()
    bucket = os.getenv("B2_BUCKET_NAME", "")
    client.head_bucket(Bucket=bucket)
    return True, f"Bucket '{bucket}' accessible"


def check_vast():
    from backend.providers.vast.client import VastClient
    client = VastClient()
    user = client.validate_api_key()
    balance = user.get("credit", user.get("balance", 0))
    instances = client.get_instances()
    running = [i for i in instances if i.get("actual_status") == "running"]
    return True, f"${balance:.2f} balance, {len(running)} running instance(s)"


def check_runpod():
    api_key = os.getenv("RUNPOD_API_KEY", "")
    if not api_key:
        return False, "RUNPOD_API_KEY not set"
    from backend.providers.runpod.client import RunPodClient
    client = RunPodClient(api_key=api_key)
    status = client.get_status()
    if status.get("api_connected"):
        return True, f"${status.get('balance', 0):.2f} balance"
    return False, status.get("error", "Connection failed")


def check_comfyui():
    r = httpx.get(f"{COMFYUI_URL}/system_stats", timeout=5)
    if r.status_code == 200:
        data = r.json()
        version = data.get("system", {}).get("comfyui_version", "?")
        return True, f"v{version} running"
    return False, f"HTTP {r.status_code}"


def check_redis():
    import redis
    r = redis.Redis(host="localhost", port=6379, socket_timeout=3)
    return r.ping(), "PONG"


def check_ollama():
    r = httpx.get("http://localhost:11434/api/tags", timeout=3)
    if r.status_code == 200:
        models = r.json().get("models", [])
        names = [m.get("name", "") for m in models[:3]]
        return True, f"{len(models)} model(s): {', '.join(names)}"
    return False, f"HTTP {r.status_code}"


def check_elevenlabs():
    api_key = os.getenv("ELEVENLABS_API_KEY", "")
    if not api_key:
        return False, "ELEVENLABS_API_KEY not set"
    r = httpx.get(
        "https://api.elevenlabs.io/v1/voices",
        headers={"xi-api-key": api_key},
        timeout=5,
    )
    if r.status_code == 200:
        voices = r.json().get("voices", [])
        return True, f"{len(voices)} voices available"
    return False, f"HTTP {r.status_code}: {r.text[:100]}"


def check_generation():
    r = httpx.post(
        f"{API_BASE}/api/v1/generate/image",
        json={"prompt": "a red apple on a white table", "model": "sdxl-turbo"},
        timeout=60,
    )
    if r.status_code == 200:
        data = r.json()
        if data.get("success"):
            return True, f"{data.get('generation_time')}s, seed={data.get('seed')}"
    return False, f"HTTP {r.status_code}: {r.text[:100]}"


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  AI Studio — Service Verification")
    print("=" * 60 + "\n")

    print("Core Services:")
    check("Backend API", check_backend)
    check("Supabase (DB)", check_supabase)
    check("Backblaze B2 (Storage)", check_b2)

    print("\nGPU Providers:")
    check("Vast.ai", check_vast)
    check("RunPod", check_runpod)
    check("ComfyUI (tunnel)", check_comfyui)

    print("\nInfrastructure:")
    check("Redis", check_redis)
    check("Ollama (Brain)", check_ollama)

    print("\nExternal APIs:")
    check("ElevenLabs (Voice)", check_elevenlabs)

    print("\nEnd-to-End:")
    check("Image Generation", check_generation)

    # Summary
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"\n{'=' * 60}")
    print(f"  Results: {passed}/{total} services operational")
    print(f"{'=' * 60}\n")

    sys.exit(0 if passed >= 6 else 1)

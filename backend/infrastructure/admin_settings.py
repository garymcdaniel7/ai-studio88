"""Admin Settings — Central configuration and service connection management.

Provides a unified view of all configured services, their connection status,
and allows toggling/configuring providers. Designed for dashboard consumption.

Services tracked:
- GPU (Vast.ai) — connection + balance
- ComfyUI — health check
- Storage (Backblaze B2) — connection test
- Database (Supabase) — connection test
- Voice (ElevenLabs) — API key validation
- Music (Suno) — readiness check
- Publishing (Webhooks) — endpoint validation
- Model Cache — inventory
- HuggingFace — token validation
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def _check_service(name: str, fn) -> dict:
    """Run a service check with timing and error handling."""
    start = time.time()
    try:
        result = fn()
        result["response_ms"] = round((time.time() - start) * 1000, 1)
        return result
    except Exception as e:
        return {
            "service": name,
            "connected": False,
            "error": str(e)[:200],
            "response_ms": round((time.time() - start) * 1000, 1),
        }


def check_vast_ai() -> dict:
    """Check Vast.ai API connection and balance."""
    from backend.providers.vast.client import VastClient, VastClientError
    api_key = os.getenv("VAST_API_KEY") or os.getenv("VASTAI_API_KEY")
    if not api_key:
        return {"service": "vast_ai", "connected": False, "error": "No API key configured"}
    try:
        client = VastClient(api_key=api_key)
        account = client.validate_api_key()
        return {
            "service": "vast_ai",
            "connected": True,
            "username": account.get("username", account.get("email", "")),
            "balance": account.get("credit", 0),
        }
    except VastClientError as e:
        return {"service": "vast_ai", "connected": False, "error": str(e)[:100]}


def check_backblaze_b2() -> dict:
    """Check Backblaze B2 storage connection."""
    import boto3
    from botocore.exceptions import ClientError
    key_id = os.getenv("B2_KEY_ID", "")
    app_key = os.getenv("B2_APPLICATION_KEY", "")
    endpoint = os.getenv("B2_ENDPOINT_URL", "")
    bucket = os.getenv("B2_BUCKET_NAME", "")
    if not key_id or not app_key:
        return {"service": "backblaze_b2", "connected": False, "error": "Credentials not configured"}
    try:
        client = boto3.client("s3", endpoint_url=endpoint,
                              aws_access_key_id=key_id, aws_secret_access_key=app_key,
                              region_name=os.getenv("B2_REGION", "us-east-005"))
        resp = client.list_objects_v2(Bucket=bucket, MaxKeys=1)
        return {
            "service": "backblaze_b2",
            "connected": True,
            "bucket": bucket,
            "objects": resp.get("KeyCount", 0),
        }
    except Exception as e:
        return {"service": "backblaze_b2", "connected": False, "error": str(e)[:100]}


def check_supabase() -> dict:
    """Check Supabase database connection."""
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_ANON_KEY", "") or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        return {"service": "supabase", "connected": False, "error": "Not configured"}
    try:
        from backend.database import supabase
        result = supabase.table("talent").select("id").limit(1).execute()
        return {
            "service": "supabase",
            "connected": True,
            "url": url[:30] + "...",
            "tables_accessible": True,
        }
    except Exception as e:
        return {"service": "supabase", "connected": False, "error": str(e)[:100]}


def check_comfyui() -> dict:
    """Check ComfyUI connection."""
    url = os.getenv("COMFYUI_BASE_URL", "http://localhost:8188")
    try:
        resp = httpx.get(f"{url}/system_stats", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            devices = data.get("devices", [])
            gpu = devices[0] if devices else {}
            return {
                "service": "comfyui",
                "connected": True,
                "version": data.get("system", {}).get("comfyui_version", "?"),
                "gpu": gpu.get("name", "Unknown"),
                "vram_gb": round(gpu.get("vram_total", 0) / 1e9, 1),
            }
        return {"service": "comfyui", "connected": False, "error": f"HTTP {resp.status_code}"}
    except httpx.ConnectError:
        return {"service": "comfyui", "connected": False, "error": f"Not reachable at {url}"}
    except Exception as e:
        return {"service": "comfyui", "connected": False, "error": str(e)[:100]}


def check_elevenlabs() -> dict:
    """Check ElevenLabs API connection."""
    api_key = os.getenv("ELEVENLABS_API_KEY", "")
    live = os.getenv("ELEVENLABS_LIVE", "false").lower() == "true"
    if not api_key:
        return {"service": "elevenlabs", "connected": False, "mode": "not_configured"}
    if not live:
        return {"service": "elevenlabs", "connected": True, "mode": "simulated", "key_set": True}
    try:
        resp = httpx.get("https://api.elevenlabs.io/v1/user",
                         headers={"xi-api-key": api_key}, timeout=10)
        if resp.status_code == 200:
            user = resp.json()
            sub = user.get("subscription", {})
            return {
                "service": "elevenlabs",
                "connected": True,
                "mode": "live",
                "tier": sub.get("tier", "?"),
                "chars_remaining": sub.get("character_limit", 0) - sub.get("character_count", 0),
            }
        return {"service": "elevenlabs", "connected": False, "error": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"service": "elevenlabs", "connected": False, "error": str(e)[:100]}


def check_huggingface() -> dict:
    """Check HuggingFace token."""
    token = os.getenv("HF_TOKEN", "")
    if not token:
        return {"service": "huggingface", "connected": False, "mode": "unauthenticated",
                "note": "Downloads will be rate-limited without HF_TOKEN"}
    try:
        resp = httpx.get("https://huggingface.co/api/whoami-v2",
                         headers={"Authorization": f"Bearer {token}"}, timeout=10)
        if resp.status_code == 200:
            user = resp.json()
            return {
                "service": "huggingface",
                "connected": True,
                "username": user.get("name", "?"),
                "mode": "authenticated",
            }
        return {"service": "huggingface", "connected": False, "error": f"Token invalid (HTTP {resp.status_code})"}
    except Exception as e:
        return {"service": "huggingface", "connected": False, "error": str(e)[:100]}


def check_model_cache() -> dict:
    """Check model cache inventory."""
    try:
        from backend.providers.vast.model_cache import list_cached_models, list_known_models
        cached = list_cached_models()
        known = list_known_models()
        return {
            "service": "model_cache",
            "connected": True,
            "cached_models": len(cached),
            "known_models": len(known),
            "total_cached_gb": round(sum(m.get("size_gb", 0) for m in cached), 1),
            "files": [m["filename"] for m in cached],
        }
    except Exception as e:
        return {"service": "model_cache", "connected": False, "error": str(e)[:100]}


# =============================================================================
# Aggregated Status
# =============================================================================


def get_all_service_status() -> dict[str, Any]:
    """Check all configured services and return their connection status.

    Returns a dict with each service's connection info, suitable for
    an admin dashboard.
    """
    services = {
        "vast_ai": _check_service("vast_ai", check_vast_ai),
        "backblaze_b2": _check_service("backblaze_b2", check_backblaze_b2),
        "supabase": _check_service("supabase", check_supabase),
        "comfyui": _check_service("comfyui", check_comfyui),
        "elevenlabs": _check_service("elevenlabs", check_elevenlabs),
        "huggingface": _check_service("huggingface", check_huggingface),
        "model_cache": _check_service("model_cache", check_model_cache),
    }

    connected_count = sum(1 for s in services.values() if s.get("connected"))
    total = len(services)

    return {
        "summary": {
            "total_services": total,
            "connected": connected_count,
            "disconnected": total - connected_count,
            "health": "healthy" if connected_count >= 3 else ("degraded" if connected_count >= 1 else "offline"),
        },
        "services": services,
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

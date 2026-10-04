"""Ollama Pre-Flight Check — VRAM guard for H3/Wan-class GPU dispatch.

H3 MiniMax and WAN video models require ~43GB VRAM on the A6000.
Ollama squats ~6GB just by running, which pushes the model over budget
and produces CUDA OOM errors mid-render.

This module provides a pre-flight check that MCP executors call before
dispatching any generation that requires full VRAM. If Ollama is detected
consuming significant VRAM, the check returns a clear action message:
the caller should kill Ollama before retrying.
"""

from __future__ import annotations

import logging
import subprocess
import time
from typing import Any

logger = logging.getLogger(__name__)

# VRAM threshold in MB: if Ollama is using MORE than this, flag it
# Ollama on an 8B Q4 model sits around 5000-6000MB
OLLAMA_VRAM_THRESHOLD_MB = 2000  # anything above 2GB is worth flagging

# Models that require nearly all VRAM — these trigger the guard
# H3 needs ~43GB on a 48GB A6000, leaving only ~5GB headroom
# WAN 14B needs ~28GB+, also tight with Ollama running
VRAM_CRITICAL_MODELS = frozenset({
    "minimax-h3",
    "minimax-h3-fl2va",
    "minimax-h3-ref2va",
    "minimax-h3-sparseref15",
    "wan-2.1-t2v",
    "wan-2.1-i2v",
    "wan-2.2-t2v",
    "wan-2.2-14b",
    "wan-2.2-remix",
    "krea2-nsfw",
    "krea2-identity-edit",
})


def check_ollama(timeout: float = 3.0) -> dict[str, Any]:
    """Check if Ollama is running and how much VRAM it's consuming.

    Returns:
        {
            "ollama_running": bool,
            "vram_used_mb": int,          # estimated
            "models_loaded": list[str],   # Ollama model names
            "action_required": bool,       # True if Ollama needs to be killed
            "message": str,               # Human-readable diagnosis
        }
    """
    result: dict[str, Any] = {
        "ollama_running": False,
        "vram_used_mb": 0,
        "models_loaded": [],
        "action_required": False,
        "message": "",
    }

    # Step 1: Check if Ollama process is running
    try:
        ps = subprocess.run(
            ["pgrep", "-f", "ollama"],
            capture_output=True, text=True, timeout=timeout,
        )
        if ps.returncode != 0 or not ps.stdout.strip():
            result["ollama_running"] = False
            result["message"] = "Ollama is not running — no VRAM conflict"
            return result
        result["ollama_running"] = True
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        result["message"] = f"Cannot check Ollama process: {e}"
        return result

    # Step 2: Check VRAM via nvidia-smi
    try:
        smi = subprocess.run(
            [
                "nvidia-smi",
                "--query-compute-apps=pid,name,used_gpu_memory",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True, text=True, timeout=timeout,
        )
        if smi.returncode == 0 and smi.stdout.strip():
            total_ollama_vram = 0
            for line in smi.stdout.strip().split("\n"):
                parts = [p.strip() for p in line.split(", ")]
                if len(parts) >= 3 and ("ollama" in parts[1].lower()):
                    try:
                        total_ollama_vram += int(parts[2])
                    except (ValueError, IndexError):
                        pass

            result["vram_used_mb"] = total_ollama_vram
        else:
            # Fallback: rough estimate — each Ollama model uses ~6GB
            result["vram_used_mb"] = 6000
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.warning("nvidia-smi check failed: %s", e)
        result["vram_used_mb"] = 6000  # conservative default

    # Step 3: Check which Ollama models are loaded
    try:
        import httpx
        resp = httpx.get("http://127.0.0.1:11434/api/tags", timeout=timeout)
        if resp.status_code == 200:
            models = resp.json().get("models", [])
            result["models_loaded"] = [m.get("name", "?") for m in models]
    except Exception:
        pass  # non-critical

    # Step 4: Determine if action is required
    if result["vram_used_mb"] > OLLAMA_VRAM_THRESHOLD_MB:
        result["action_required"] = True
        result["message"] = (
            f"Ollama is running and consuming ~{result['vram_used_mb']}MB VRAM. "
            f"Models loaded: {', '.join(result['models_loaded']) or 'unknown'}. "
            f"Kill Ollama with `pkill -9 -f ollama` before dispatching H3/Wan renders, "
            f"or the generation may OOM on the ~43GB model."
        )
    else:
        result["message"] = (
            f"Ollama running but minimal VRAM usage (~{result['vram_used_mb']}MB). "
            f"Should be safe for generation."
        )

    return result


def guard_h3_dispatch(model_name: str) -> dict[str, Any]:
    """Pre-flight guard for H3/Wan-class dispatch.

    Checks if the model is VRAM-critical, and if so, whether Ollama
    is squatting VRAM that would cause an OOM.

    Returns:
        {"can_dispatch": True}
        or {"can_dispatch": False, "reason": "...", "ollama_status": {...}}
    """
    # Only check VRAM-critical models
    model_key = model_name.lower().replace(" ", "-")
    if model_key not in VRAM_CRITICAL_MODELS:
        return {"can_dispatch": True}

    ollama_status = check_ollama()
    if ollama_status["action_required"]:
        return {
            "can_dispatch": False,
            "reason": ollama_status["message"],
            "ollama_status": ollama_status,
        }

    return {"can_dispatch": True, "ollama_status": ollama_status}
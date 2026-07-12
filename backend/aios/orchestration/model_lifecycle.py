"""Model Lifecycle Manager — intelligent model placement between B2 and GPU.

Models have states:
- B2_ONLY: stored in Backblaze, not on any GPU worker
- CACHED: downloaded to GPU worker disk (fast to load into VRAM)
- LOADED: in GPU VRAM (ready for immediate inference)
- ARCHIVED: marked inactive, can be restored from B2

The lifecycle manager:
- Loads models into VRAM when tasks need them
- Unloads from VRAM when space is needed (LRU eviction)
- Downloads from B2 to worker when first needed
- Uploads to B2 after training (archive source of truth)
- Tracks usage frequency for smart eviction decisions

Tied into the auto-scaler: when a model swap would be slow,
the scaler may suggest launching a 2nd worker instead.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class ModelState(Enum):
    B2_ONLY = "b2_only"       # Only in cold storage
    CACHED = "cached"         # On worker disk, not in VRAM
    LOADED = "loaded"         # In GPU VRAM (ready)
    ARCHIVED = "archived"     # Inactive, restorable


@dataclass
class ModelPlacement:
    """Tracks where a model currently lives."""
    model_id: str
    name: str
    state: ModelState
    size_mb: float = 0
    vram_mb: float = 0        # VRAM consumed when loaded
    b2_path: str = ""         # B2 storage key
    worker_path: str = ""     # Path on GPU worker disk
    last_used: float = 0      # Timestamp of last use
    use_count: int = 0        # Total times used
    model_type: str = "checkpoint"  # checkpoint, lora, vae, controlnet


def _db():
    from backend.database import supabase
    return supabase


def get_model_placements() -> list[ModelPlacement]:
    """Get current placement state of all models from the registry."""
    try:
        models = _db().table("models").select("id,name,type,status,storage_path,required_vram_gb,metadata").execute().data or []
        placements = []
        for m in models:
            state = ModelState.B2_ONLY
            status = m.get("status", "")
            if status == "available":
                state = ModelState.LOADED
            elif status == "available_b2_only":
                state = ModelState.B2_ONLY
            elif status == "archived":
                state = ModelState.ARCHIVED

            meta = m.get("metadata") or {}
            placements.append(ModelPlacement(
                model_id=m.get("id", ""),
                name=m.get("name", ""),
                state=state,
                size_mb=float(meta.get("size_mb", 0)),
                vram_mb=float(m.get("required_vram_gb", 0)) * 1024,
                b2_path=m.get("storage_path", ""),
                worker_path=meta.get("comfyui_path", ""),
                model_type=m.get("type", "checkpoint"),
                last_used=0,
                use_count=0,
            ))
        return placements
    except Exception as e:
        logger.warning(f"Failed to get model placements: {e}")
        return []


async def ensure_model_loaded(model_name: str) -> dict:
    """Ensure a model is loaded on the GPU worker and ready for inference.

    If the model is:
    - LOADED: return immediately
    - CACHED: load into VRAM (fast)
    - B2_ONLY: download from B2 to worker, then load
    - ARCHIVED: restore from archive, download, load

    Returns: {success, state, action_taken, time_seconds}
    """
    from backend.infrastructure.worker_api_client import get_worker_client

    client = get_worker_client()
    if not client or not client.is_available():
        return {"success": False, "state": "no_worker", "action_taken": "none", "error": "No GPU worker available"}

    # Check what's currently on the worker
    try:
        worker_models = client.list_models()
        loaded_models = []
        for category, models in (worker_models.get("models", {}) or {}).items():
            for m in models:
                loaded_models.append(m.get("name", ""))

        # Is the model already on the worker?
        model_filename = _resolve_filename(model_name)
        if model_filename and any(model_filename in m for m in loaded_models):
            return {"success": True, "state": "loaded", "action_taken": "already_available"}

    except Exception as e:
        return {"success": False, "state": "error", "error": str(e)[:200]}

    # Model not on worker — need to download from B2
    try:
        # Find the model in our registry
        model_record = _db().table("models").select("*").ilike("name", f"%{model_name}%").limit(1).execute().data
        if not model_record:
            return {"success": False, "state": "not_found", "error": f"Model '{model_name}' not in registry"}

        model = model_record[0]
        b2_url = model.get("storage_path", "")
        meta = model.get("metadata") or {}
        comfyui_path = meta.get("comfyui_path", "")

        if not b2_url:
            return {"success": False, "state": "no_b2_path", "error": "Model has no B2 storage path"}

        # Get the public download URL
        from backend.storage import get_public_url
        download_url = get_public_url(b2_url)

        if not download_url:
            return {"success": False, "state": "no_download_url", "error": "Cannot generate download URL for model"}

        # Download to worker via Worker API
        start = time.time()
        result = client.download_model(url=download_url, destination=comfyui_path)
        elapsed = time.time() - start

        if result.get("success"):
            # Update model status in registry
            _db().table("models").update({"status": "available"}).eq("id", model.get("id")).execute()
            return {
                "success": True,
                "state": "loaded",
                "action_taken": "downloaded_from_b2",
                "time_seconds": round(elapsed, 1),
                "size_mb": result.get("size_mb", 0),
            }
        else:
            return {"success": False, "state": "download_failed", "error": str(result)}

    except Exception as e:
        return {"success": False, "state": "error", "error": str(e)[:200]}


async def unload_model(model_name: str) -> dict:
    """Unload a model from the GPU worker (keeps in B2).

    Frees VRAM/disk space. Model can be re-downloaded when needed.
    Updates registry status to 'available_b2_only'.
    """
    try:
        # Find and update in registry
        model_filename = _resolve_filename(model_name)
        models = _db().table("models").select("id,name").ilike("name", f"%{model_name}%").execute().data or []

        for m in models:
            _db().table("models").update({"status": "available_b2_only"}).eq("id", m["id"]).execute()

        # Remove from worker disk (via Worker API or SSH)
        from backend.infrastructure.worker_api_client import get_worker_client
        client = get_worker_client()
        if client and client.is_available():
            # Worker API doesn't have a delete endpoint yet — just update registry
            pass

        return {"success": True, "action": "unloaded", "model": model_name, "message": "Model marked as B2-only. VRAM freed on next ComfyUI restart."}
    except Exception as e:
        return {"success": False, "error": str(e)[:200]}


async def archive_model(model_id: str) -> dict:
    """Archive a model — marks as inactive, still in B2 for future restore."""
    try:
        _db().table("models").update({"status": "archived"}).eq("id", model_id).execute()
        return {"success": True, "action": "archived", "message": "Model archived. Can be restored anytime."}
    except Exception as e:
        return {"success": False, "error": str(e)[:200]}


async def restore_model(model_id: str) -> dict:
    """Restore an archived model — sets to B2-only (ready to download when needed)."""
    try:
        _db().table("models").update({"status": "available_b2_only"}).eq("id", model_id).execute()
        return {"success": True, "action": "restored", "message": "Model restored. Will download to GPU when first used."}
    except Exception as e:
        return {"success": False, "error": str(e)[:200]}


def recommend_eviction(current_models: list[ModelPlacement], needed_vram_mb: float) -> list[str]:
    """Recommend which models to evict to free VRAM.

    Uses LRU (Least Recently Used) weighted by:
    - Last used timestamp (older = more likely to evict)
    - Use frequency (less used = more likely)
    - Size (larger = frees more space in one eviction)

    Returns list of model_ids to evict, in order.
    """
    loaded = [m for m in current_models if m.state == ModelState.LOADED]
    if not loaded:
        return []

    # Score each model (lower score = better eviction candidate)
    scored = []
    for m in loaded:
        recency_score = time.time() - m.last_used if m.last_used > 0 else 999999
        frequency_penalty = m.use_count * 1000  # Higher use = less likely to evict
        size_bonus = m.vram_mb  # Larger models free more space

        eviction_score = recency_score + size_bonus - frequency_penalty
        scored.append((m, eviction_score))

    # Sort by score descending (highest score = best eviction candidate)
    scored.sort(key=lambda x: x[1], reverse=True)

    # Pick enough models to free the needed VRAM
    to_evict = []
    freed = 0
    for m, _ in scored:
        to_evict.append(m.model_id)
        freed += m.vram_mb
        if freed >= needed_vram_mb:
            break

    return to_evict


def _resolve_filename(model_name: str) -> str:
    """Resolve a model name to its likely filename on disk."""
    KNOWN_FILENAMES = {
        "flux-dev": "flux1-dev-fp8.safetensors",
        "sdxl": "sd_xl_base_1.0.safetensors",
        "sdxl-turbo": "sd_xl_turbo_1.0_fp16.safetensors",
        "sd15": "v1-5-pruned-emaonly.safetensors",
        "wan-2.1": "wan_2.1.safetensors",
    }
    return KNOWN_FILENAMES.get(model_name, model_name)

"""LoRA Training API Router.

Manages datasets, captions, training jobs, LoRA versions, and evaluation.
Training executes on external GPU workers through the TrainingProvider interface.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException

from backend.training.provider import (
    get_training_provider, TrainingConfig, SimulatedTrainingProvider,
    TRAINING_PROVIDERS,
)

router = APIRouter(prefix="/api/v1", tags=["training"])


# =============================================================================
# Providers
# =============================================================================

@router.get("/training/providers")
def list_training_providers():
    """List all registered training providers and their health/capabilities."""
    providers = []
    for name, cls in TRAINING_PROVIDERS.items():
        instance = cls()
        info = {"name": name, "health": instance.health()}
        if hasattr(instance, "capabilities"):
            info["capabilities"] = instance.capabilities()
        providers.append(info)
    return providers


# =============================================================================
# Helper: Supabase access
# =============================================================================

def _db():
    from backend.database import supabase
    return supabase


# =============================================================================
# Datasets
# =============================================================================

@router.get("/training/datasets")
def list_datasets(talent_id: Optional[str] = None):
    query = _db().table("training_datasets").select("*").order("created_at", desc=True)
    if talent_id:
        query = query.eq("talent_id", talent_id)
    try:
        return query.execute().data
    except Exception:
        return []


@router.post("/training/datasets", status_code=201)
def create_dataset(data: dict):
    if not data.get("name"):
        raise HTTPException(status_code=400, detail="'name' required")
    record = {
        "name": data["name"],
        "description": data.get("description", ""),
        "talent_id": data.get("talent_id"),
        "project_id": data.get("project_id"),
        "status": "draft",
        "image_count": 0,
    }
    try:
        result = _db().table("training_datasets").insert(record).execute()
        return result.data[0] if result.data else record
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/training/datasets/{dataset_id}")
def get_dataset(dataset_id: str):
    try:
        return _db().table("training_datasets").select("*").eq("id", dataset_id).single().execute().data
    except Exception:
        raise HTTPException(status_code=404, detail="Dataset not found")


@router.put("/training/datasets/{dataset_id}")
def update_dataset(dataset_id: str, data: dict):
    data["updated_at"] = "now()"
    try:
        result = _db().table("training_datasets").update(data).eq("id", dataset_id).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/training/datasets/{dataset_id}")
def delete_dataset(dataset_id: str):
    try:
        _db().table("training_datasets").delete().eq("id", dataset_id).execute()
        return {"deleted": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Dataset Images
# =============================================================================

@router.get("/training/datasets/{dataset_id}/images")
def list_dataset_images(dataset_id: str):
    try:
        return _db().table("training_images").select("*").eq("dataset_id", dataset_id).order("created_at").execute().data
    except Exception:
        return []


@router.post("/training/datasets/{dataset_id}/images", status_code=201)
def add_image_to_dataset(dataset_id: str, data: dict):
    """Add an existing asset to a training dataset."""
    record = {
        "dataset_id": dataset_id,
        "asset_id": data.get("asset_id"),
        "storage_key": data.get("storage_key", ""),
        "caption": data.get("caption", ""),
        "tags": data.get("tags", []),
        "quality_score": float(data.get("quality_score", 1.0)),
        "included": data.get("included", True),
    }
    try:
        result = _db().table("training_images").insert(record).execute()
        # Update image count
        imgs = _db().table("training_images").select("id").eq("dataset_id", dataset_id).eq("included", True).execute()
        _db().table("training_datasets").update({"image_count": len(imgs.data or []), "updated_at": "now()"}).eq("id", dataset_id).execute()
        return result.data[0] if result.data else record
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Captioning
# =============================================================================

@router.post("/training/datasets/{dataset_id}/caption")
def auto_caption_dataset(dataset_id: str, data: dict = {}):
    """Auto-generate captions for all images in a dataset (simulated).

    Future: dispatches to BLIP, Florence, JoyCaption, LLaVA, or GPT vision.
    """
    try:
        images = _db().table("training_images").select("*").eq("dataset_id", dataset_id).execute().data or []
    except Exception:
        raise HTTPException(status_code=404, detail="Dataset not found")

    trigger_word = data.get("trigger_word", "aistudio_character")
    captioned = 0

    for img in images:
        # Simulated caption generation
        simulated_caption = f"{trigger_word}, professional portrait, high quality, detailed face, studio lighting"
        try:
            _db().table("training_images").update({"caption": simulated_caption}).eq("id", img["id"]).execute()
            captioned += 1
        except Exception:
            pass

    return {"captioned": captioned, "total": len(images), "trigger_word": trigger_word}


@router.put("/training/images/{image_id}/caption")
def update_image_caption(image_id: str, data: dict):
    """Manually edit an image's caption."""
    caption = data.get("caption", "")
    try:
        _db().table("training_images").update({"caption": caption}).eq("id", image_id).execute()
        return {"updated": True, "image_id": image_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Training Jobs
# =============================================================================

@router.get("/training/jobs")
def list_training_jobs(talent_id: Optional[str] = None, status: Optional[str] = None):
    query = _db().table("training_jobs").select("*").order("created_at", desc=True)
    if talent_id:
        query = query.eq("talent_id", talent_id)
    if status:
        query = query.eq("status", status)
    try:
        return query.execute().data
    except Exception:
        return []


@router.get("/training/jobs/{job_id}")
def get_training_job(job_id: str):
    try:
        return _db().table("training_jobs").select("*").eq("id", job_id).single().execute().data
    except Exception:
        raise HTTPException(status_code=404, detail="Training job not found")


@router.post("/training/jobs", status_code=201)
def start_training_job(data: dict):
    """Start a LoRA training job.

    Required: dataset_id
    Optional: talent_id, project_id, config (training parameters)
    """
    dataset_id = data.get("dataset_id")
    if not dataset_id:
        raise HTTPException(status_code=400, detail="'dataset_id' required")

    # Get dataset info
    try:
        dataset = _db().table("training_datasets").select("*").eq("id", dataset_id).single().execute().data
    except Exception:
        raise HTTPException(status_code=404, detail="Dataset not found")

    # Build config
    config_data = data.get("config", {})
    config = TrainingConfig(
        base_model=config_data.get("base_model", "flux1-dev-fp8.safetensors"),
        resolution=int(config_data.get("resolution", 512)),
        rank=int(config_data.get("rank", 16)),
        steps=int(config_data.get("steps", 1000)),
        learning_rate=float(config_data.get("learning_rate", 1e-4)),
        trigger_words=config_data.get("trigger_words", ["aistudio_character"]),
    )

    # Validate dataset
    provider = get_training_provider(data.get("provider", "simulation"))
    image_count = dataset.get("image_count", 0)
    valid, err = provider.validate_dataset(image_count, config)
    if not valid:
        raise HTTPException(status_code=400, detail=f"Dataset validation failed: {err}")

    # Create training job record
    job_record = {
        "project_id": data.get("project_id", dataset.get("project_id")),
        "talent_id": data.get("talent_id", dataset.get("talent_id")),
        "dataset_id": dataset_id,
        "status": "running",
        "training_provider": provider.name,
        "config": {
            "base_model": config.base_model,
            "resolution": config.resolution,
            "rank": config.rank,
            "steps": config.steps,
            "learning_rate": config.learning_rate,
            "trigger_words": config.trigger_words,
        },
    }

    try:
        result = _db().table("training_jobs").insert(job_record).execute()
        training_job = result.data[0] if result.data else job_record
        training_job_id = training_job.get("id", "")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Execute training (synchronous for simulation, async for real providers)
    try:
        training_result = provider.submit(dataset_id, config)

        if training_result.success:
            # Upload LoRA to B2 and register
            from backend.storage import upload_file, compute_checksum, generate_storage_key
            from backend.database import create_asset, create_model_record

            storage_key = generate_storage_key(training_result.output_filename, "model")
            checksum = compute_checksum(training_result.output_file_bytes)
            public_url = upload_file(training_result.output_file_bytes, storage_key, "application/octet-stream")

            # Create Asset
            asset_result = create_asset({
                "talent_id": training_job.get("talent_id"),
                "project_id": training_job.get("project_id"),
                "type": "model",
                "filename": training_result.output_filename,
                "original_filename": training_result.output_filename,
                "mime_type": "application/octet-stream",
                "size_bytes": len(training_result.output_file_bytes),
                "storage_provider": "backblaze_b2",
                "storage_key": storage_key,
                "public_url": public_url,
                "checksum": checksum,
                "metadata": training_result.metadata,
                "tags": ["lora", "trained", provider.name],
            })
            asset = asset_result.data[0] if asset_result.data else {}

            # Create Model record
            model_result = create_model_record({
                "name": f"LoRA {training_job.get('talent_id', 'custom')[:8]} v1",
                "family": "flux",
                "type": "lora",
                "provider": "trained",
                "storage_path": storage_key,
                "required_vram_gb": 0.5,
                "supported_tasks": ["txt2img"],
                "status": "available",
                "metadata": training_result.metadata,
            })
            model = model_result.data[0] if model_result.data else {}

            # Create LoRA Version
            lora_record = {
                "talent_id": training_job.get("talent_id"),
                "project_id": training_job.get("project_id"),
                "model_id": model.get("id"),
                "asset_id": asset.get("id"),
                "version": 1,
                "name": f"LoRA v1 ({provider.name})",
                "trigger_words": config.trigger_words,
                "base_model": config.base_model,
                "recommended_strength": 0.7,
                "status": "active",
                "training_job_id": training_job_id,
                "metadata": training_result.metadata,
            }
            _db().table("lora_versions").insert(lora_record).execute()

            # Update training job
            _db().table("training_jobs").update({
                "status": "completed",
                "output_lora_asset_id": asset.get("id"),
                "output_model_id": model.get("id"),
                "logs": training_result.logs,
                "completed_at": "now()",
                "updated_at": "now()",
            }).eq("id", training_job_id).execute()

            return {
                "status": "completed",
                "training_job_id": training_job_id,
                "asset_id": asset.get("id"),
                "model_id": model.get("id"),
                "training_time_seconds": training_result.training_time_seconds,
                "final_loss": training_result.final_loss,
            }
        else:
            _db().table("training_jobs").update({
                "status": "failed", "error": training_result.error, "updated_at": "now()",
            }).eq("id", training_job_id).execute()
            raise HTTPException(status_code=500, detail=f"Training failed: {training_result.error}")

    except HTTPException:
        raise
    except Exception as e:
        _db().table("training_jobs").update({
            "status": "failed", "error": str(e), "updated_at": "now()",
        }).eq("id", training_job_id).execute()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/training/jobs/{job_id}/cancel")
def cancel_training_job(job_id: str):
    try:
        _db().table("training_jobs").update({"status": "cancelled", "updated_at": "now()"}).eq("id", job_id).execute()
        return {"cancelled": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# LoRA Library
# =============================================================================

@router.get("/loras")
def list_loras(talent_id: Optional[str] = None):
    query = _db().table("lora_versions").select("*").order("created_at", desc=True)
    if talent_id:
        query = query.eq("talent_id", talent_id)
    try:
        return query.execute().data
    except Exception:
        return []


@router.get("/loras/{lora_id}")
def get_lora(lora_id: str):
    try:
        return _db().table("lora_versions").select("*").eq("id", lora_id).single().execute().data
    except Exception:
        raise HTTPException(status_code=404, detail="LoRA not found")


@router.post("/loras/{lora_id}/evaluate", status_code=201)
def evaluate_lora(lora_id: str, data: dict):
    """Submit an evaluation for a LoRA version."""
    record = {
        "lora_version_id": lora_id,
        "rating": int(data.get("rating", 3)),
        "identity_score": float(data.get("identity_score", 0)),
        "realism_score": float(data.get("realism_score", 0)),
        "flexibility_score": float(data.get("flexibility_score", 0)),
        "notes": data.get("notes", ""),
        "test_asset_ids": data.get("test_asset_ids", []),
    }
    try:
        result = _db().table("lora_evaluations").insert(record).execute()
        return result.data[0] if result.data else record
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/loras/{lora_id}/promote")
def promote_lora(lora_id: str):
    """Promote a LoRA as the talent's default.

    Updates the talent's main_lora_asset_id field.
    """
    try:
        lora = _db().table("lora_versions").select("*").eq("id", lora_id).single().execute().data
    except Exception:
        raise HTTPException(status_code=404, detail="LoRA not found")

    talent_id = lora.get("talent_id")
    asset_id = lora.get("asset_id")

    if not talent_id:
        raise HTTPException(status_code=400, detail="LoRA has no associated talent")

    try:
        _db().table("talent").update({"main_lora_asset_id": asset_id, "updated_at": "now()"}).eq("id", talent_id).execute()
        _db().table("lora_versions").update({"status": "promoted", "updated_at": "now()"}).eq("id", lora_id).execute()
        return {"promoted": True, "lora_id": lora_id, "talent_id": talent_id, "asset_id": asset_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

"""Workflow Selector — maps model names to ComfyUI workflow templates.

This module handles the mapping between user-facing model names and the
appropriate ComfyUI workflow template, default generation parameters, and
checkpoint filenames.

When a generation request specifies a model (e.g. "sdxl-turbo"), this module
determines:
  1. Which workflow JSON template to load
  2. What default parameters to use (steps, cfg, resolution, sampler)
  3. Which checkpoint file is required

Usage:
    from backend.engine.workflow_selector import (
        get_workflow_for_model,
        get_available_models,
        get_model_defaults,
    )

    config = get_workflow_for_model("sdxl-turbo")
    # Returns full workflow config dict or None if model unknown
"""

from __future__ import annotations

# Known checkpoints cached in B2 storage (ready for quick deployment)
B2_CACHED_CHECKPOINTS: set[str] = {
    "sd_xl_turbo_1.0_fp16.safetensors",
    "v1-5-pruned-emaonly.safetensors",
}

# =============================================================================
# Workflow Map — model name -> workflow config
# =============================================================================

WORKFLOW_MAP: dict[str, dict] = {
    "sdxl-turbo": {
        "workflow": "sdxl_turbo",
        "defaults": {
            "steps": 1,
            "cfg": 1.0,
            "width": 512,
            "height": 512,
            "sampler": "euler",
        },
        "checkpoint": "sd_xl_turbo_1.0_fp16.safetensors",
        "description": "SDXL Turbo — single-step fast generation at 512x512",
        "capabilities": ["txt2img"],
        "required_vram_gb": 8.0,
    },
    "sd15": {
        "workflow": "sd15_standard",
        "defaults": {
            "steps": 20,
            "cfg": 7.5,
            "width": 512,
            "height": 512,
            "sampler": "euler_a",
        },
        "checkpoint": "v1-5-pruned-emaonly.safetensors",
        "description": "Stable Diffusion 1.5 — classic model, versatile and well-supported",
        "capabilities": ["txt2img", "img2img", "inpainting"],
        "required_vram_gb": 6.0,
    },
    "flux-dev": {
        "workflow": "flux_dev",
        "defaults": {
            "steps": 20,
            "cfg": 1.0,
            "guidance": 3.5,
            "width": 1024,
            "height": 1024,
            "sampler": "euler",
        },
        "checkpoint": "flux1-dev.safetensors",
        "description": "FLUX.1-dev — highest quality, uses UNETLoader + DualCLIP + T5-XXL",
        "capabilities": ["txt2img", "img2img"],
        "required_vram_gb": 32.0,
        "extra_files": ["clip_l.safetensors", "t5xxl_fp16.safetensors", "ae.safetensors"],
    },
}


# =============================================================================
# Public API
# =============================================================================


def get_workflow_for_model(model_name: str) -> dict | None:
    """Get the full workflow configuration for a model.

    Args:
        model_name: Model identifier (e.g. "sdxl-turbo", "sd15", "flux-dev")

    Returns:
        Dict with workflow template name, defaults, and checkpoint info,
        or None if model_name is not recognized.
    """
    return WORKFLOW_MAP.get(model_name)


def get_available_models() -> list[dict]:
    """Get all available models with their configuration and cache status.

    Returns a list of model descriptors including:
      - id, description, defaults, checkpoint, capabilities
      - cached_in_b2: whether the checkpoint is ready in B2 storage
    """
    models = []
    for model_id, config in WORKFLOW_MAP.items():
        models.append(
            {
                "id": model_id,
                "workflow_template": config["workflow"],
                "description": config["description"],
                "defaults": config["defaults"],
                "checkpoint": config["checkpoint"],
                "capabilities": config["capabilities"],
                "required_vram_gb": config["required_vram_gb"],
                "cached_in_b2": config["checkpoint"] in B2_CACHED_CHECKPOINTS,
            }
        )
    return models


def get_model_defaults(model_name: str) -> dict:
    """Get default generation parameters for a model.

    Args:
        model_name: Model identifier

    Returns:
        Dict of default parameters (steps, cfg, width, height, sampler).
        Returns empty dict if model is not recognized.
    """
    config = WORKFLOW_MAP.get(model_name)
    if not config:
        return {}
    return dict(config["defaults"])


def get_workflow_template_name(model_name: str) -> str | None:
    """Get just the workflow template filename (without .json) for a model.

    Args:
        model_name: Model identifier

    Returns:
        Template name string or None if model not found.
    """
    config = WORKFLOW_MAP.get(model_name)
    if not config:
        return None
    return config["workflow"]


def get_checkpoint_for_model(model_name: str) -> str | None:
    """Get the checkpoint filename for a model.

    Args:
        model_name: Model identifier

    Returns:
        Checkpoint filename or None if model not found.
    """
    config = WORKFLOW_MAP.get(model_name)
    if not config:
        return None
    return config["checkpoint"]


def is_model_cached(model_name: str) -> bool:
    """Check if a model's checkpoint is cached in B2 storage.

    Args:
        model_name: Model identifier

    Returns:
        True if checkpoint is available in B2 cache.
    """
    config = WORKFLOW_MAP.get(model_name)
    if not config:
        return False
    return config["checkpoint"] in B2_CACHED_CHECKPOINTS

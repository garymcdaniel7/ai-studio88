"""Model Registry — validated model-to-workflow resolution for MCP tool dispatch.

Every model name an MCP client sends must resolve to:
- A ComfyUI workflow template that exists on disk
- Required on-disk model files (by name, for pre-flight checking)
- A provider class or dispatch lane

This is the single source of truth the MCP executors use to validate
generation requests before they reach the GPU or job queue.
Unknown models return a structured, actionable error — never simulation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# =============================================================================
# Model Registration
# =============================================================================

# ComfyUI workflow templates directory on the worker
WORKFLOWS_DIR = Path("./workflows/comfyui")

# Base paths relative to ComfyUI's models directory
MODEL_DIRS = {
    "checkpoints": "models/checkpoints/",
    "loras": "models/loras/",
    "vae": "models/vae/",
    "controlnet": "models/controlnet/",
    "unet": "models/unet/",
    "clip": "models/clip/",
}


@dataclass(frozen=True)
class ModelSpec:
    """Spec for a generation model exposed via MCP."""

    name: str  # Canonical name the MCP tool uses (e.g. "krea2-nsfw")
    display_name: str  # Human label
    lane: Literal["image", "video"]  # Which generation lane
    workflow_template: str  # ComfyUI workflow JSON name (without .json)
    required_model_files: list[str]  # On-disk filenames, relative to model type dir
    provider: Literal["comfyui-worker", "job-queue"]  # Dispatch mechanism
    requires_ollama_kill: bool = False  # Pre-flight VRAM check needed
    tags: list[str] | None = None  # Search/filter tags
    notes: str = ""


# =============================================================================
# KNOWN MODELS — models the MCP surface can validate against
# =============================================================================

KNOWN_MODELS: dict[str, ModelSpec] = {
    # ── Image Models ──────────────────────────────────────────────────────
    "flux-dev": ModelSpec(
        name="flux-dev",
        display_name="Flux Dev (Fast)",
        lane="image",
        workflow_template="flux_dev",
        required_model_files=["flux1-dev-fp8.safetensors"],
        provider="comfyui-worker",
        tags=["flux", "fast", "photo"],
        notes="Fast flux model, ~$0.005/img. Good for iteration.",
    ),
    "flux-dev-basic": ModelSpec(
        name="flux-dev-basic",
        display_name="Flux Dev Basic T2I",
        lane="image",
        workflow_template="flux_text_to_image_basic",
        required_model_files=["flux1-dev-fp8.safetensors"],
        provider="comfyui-worker",
        tags=["flux", "t2i"],
        notes="Simpler T2I-only flux workflow.",
    ),
    "sdxl-turbo": ModelSpec(
        name="sdxl-turbo",
        display_name="SDXL Turbo",
        lane="image",
        workflow_template="sdxl_turbo",
        required_model_files=["sd_xl_turbo_1.0_fp16.safetensors"],
        provider="comfyui-worker",
        tags=["sdxl", "turbo", "fast"],
        notes="~1-4 step generation, near-instant.",
    ),
    "sd15": ModelSpec(
        name="sd15",
        display_name="Stable Diffusion 1.5",
        lane="image",
        workflow_template="sd15_standard",
        required_model_files=["v1-5-pruned-emaonly.safetensors"],
        provider="comfyui-worker",
        tags=["sd15", "legacy"],
        notes="SD 1.5 base model. Slower but widely compatible.",
    ),
    # ── Video Models ──────────────────────────────────────────────────────
    "wan-2.1-t2v": ModelSpec(
        name="wan-2.1-t2v",
        display_name="WAN 2.1 Text-to-Video",
        lane="video",
        workflow_template="wan21_t2v_native",
        required_model_files=["Wan2.1_T2V_14B_fp16.safetensors"],
        provider="job-queue",
        requires_ollama_kill=True,
        tags=["wan", "t2v", "14b"],
        notes="Text-to-video via WAN 2.1 14B. ~3-10 min per 2s clip.",
    ),
    "wan-2.1-i2v": ModelSpec(
        name="wan-2.1-i2v",
        display_name="WAN 2.1 Image-to-Video",
        lane="video",
        workflow_template="wan21_i2v_native",
        required_model_files=["Wan2.1_I2V_14B_fp16.safetensors"],
        provider="job-queue",
        requires_ollama_kill=True,
        tags=["wan", "i2v", "14b"],
        notes="Image-to-video via WAN 2.1 14B.",
    ),
    "wan-2.2-t2v": ModelSpec(
        name="wan-2.2-t2v",
        display_name="WAN 2.2 Text-to-Video",
        lane="video",
        workflow_template="wan22_t2v_native",
        required_model_files=["wan2.2_ti2v_5B_fp16.safetensors"],
        provider="job-queue",
        requires_ollama_kill=True,
        tags=["wan", "t2v", "5b"],
        notes="WAN 2.2 5B T2V. ~2-3 min per clip. Faster than 14B.",
    ),
    "wan-2.2-14b": ModelSpec(
        name="wan-2.2-14b",
        display_name="WAN 2.2 14B Text-to-Video",
        lane="video",
        workflow_template="wan22_14b_native",
        required_model_files=["wan2.2_ti2v_14B_fp16.safetensors"],
        provider="job-queue",
        requires_ollama_kill=True,
        tags=["wan", "t2v", "14b"],
        notes="WAN 2.2 14B T2V. Highest quality, slowest.",
    ),
    "wan-2.2-remix": ModelSpec(
        name="wan-2.2-remix",
        display_name="WAN 2.2 Remix (NSFW i2v)",
        lane="video",
        workflow_template="wan22_remix_nsfw_i2v",
        required_model_files=["wan2.2_remix_14B_fp16.safetensors"],
        provider="job-queue",
        requires_ollama_kill=True,
        tags=["wan", "i2v", "remix", "nsfw"],
        notes="WAN 2.2 Remix with Lightning LoRA support. ~2 min with 4+4 step.",
    ),
}


def get_spec(model_name: str) -> ModelSpec | None:
    """Look up a model spec by its canonical name.

    Returns None for unknown models — the caller should return a
    structured error, never fall through to simulation.
    """
    return KNOWN_MODELS.get(model_name)


def validate_model_for_dispatch(
    model_name: str, lane: str, workflows_dir: Path | str | None = None
) -> dict:
    """Validate a model before dispatch.

    Checks:
    1. Model is KNOWN (spec exists)
    2. Model is in the correct lane (image/video)
    3. Workflow template exists on disk

    Returns:
        {"valid": True}
        or {"valid": False, "error": "...", "suggestions": [...]}
    """
    spec = get_spec(model_name)
    if not spec:
        known = list(KNOWN_MODELS.keys())
        return {
            "valid": False,
            "error": f"Unknown model '{model_name}'",
            "suggestions": known,
        }

    if spec.lane != lane:
        return {
            "valid": False,
            "error": f"Model '{model_name}' is a {spec.lane} model, not {lane}",
        }

    # Check workflow template exists
    wd = Path(workflows_dir) if workflows_dir else WORKFLOWS_DIR
    template_path = wd / f"{spec.workflow_template}.json"
    if not template_path.exists():
        return {
            "valid": False,
            "error": f"Workflow template '{spec.workflow_template}' not found at {template_path}",
        }

    return {"valid": True, "spec": spec}


def list_models_by_lane(lane: str) -> list[dict]:
    """List all known models for a lane, in MCP-friendly format."""
    return [
        {
            "name": spec.name,
            "display_name": spec.display_name,
            "tags": spec.tags or [],
            "notes": spec.notes,
        }
        for spec in KNOWN_MODELS.values()
        if spec.lane == lane
    ]


# DEPRECATED — kept for import compatibility with existing callers.
# Use KNOWN_MODELS directly or get_spec() instead.
WORKFLOW_MODEL_MAP: dict[str, str] = {
    "flux-dev": "flux1-dev-fp8.safetensors",
    "sdxl": "sd_xl_base_1.0.safetensors",
    "sdxl-turbo": "sd_xl_turbo_1.0_fp16.safetensors",
    "sd15": "v1-5-pruned-emaonly.safetensors",
}
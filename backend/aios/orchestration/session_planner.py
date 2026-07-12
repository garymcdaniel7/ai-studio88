"""Session Planner — asks what kind of session and pre-allocates resources.

Before heavy operations, the AI asks:
  "What kind of session are we having? Image, video, training?"

Based on the answer, it:
- Selects the right worker type (cheap vs powerful)
- Pre-loads the right models (Flux for images, WAN for video)
- Sets budget expectations
- Monitors for reduced need and suggests releasing resources

This prevents surprise GPU costs and ensures resources are allocated well.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class SessionType(Enum):
    IMAGE = "image"           # Portraits, products, landscapes
    VIDEO = "video"           # Clips, animations, motion
    TRAINING = "training"     # LoRA training
    MIXED = "mixed"           # Multiple types
    CHAT_ONLY = "chat_only"   # No GPU needed (brain only)


@dataclass
class SessionPlan:
    """A planned session with resource requirements."""
    session_type: SessionType
    estimated_duration_minutes: int = 30
    models_needed: list[str] = field(default_factory=list)
    min_vram_gb: int = 12
    preferred_provider: str = "vast"  # vast or runpod
    estimated_cost_usd: float = 0.0
    auto_release_idle_minutes: int = 10
    reasoning: list[str] = field(default_factory=list)


@dataclass
class WorkerRequirement:
    """What a specific task needs from a GPU worker."""
    task: str                  # "generate_image", "generate_video", "train_lora"
    model: str                 # checkpoint needed
    min_vram_gb: int = 12
    persistent_volume: bool = False  # RunPod persistent needed?
    estimated_time_seconds: int = 60
    priority: int = 5          # 1-10, higher = more urgent


def plan_session(
    session_type: str = "auto",
    tasks: list[str] | None = None,
    talent_id: str | None = None,
) -> SessionPlan:
    """Create a session plan based on intended work.

    Args:
        session_type: image, video, training, mixed, chat_only, or auto
        tasks: specific tasks planned (generate_image, train_lora, etc.)
        talent_id: if set, checks what LoRAs need to be loaded

    Returns:
        SessionPlan with resource requirements and reasoning
    """
    plan = SessionPlan(session_type=SessionType.CHAT_ONLY)
    reasoning = []

    # Auto-detect from tasks
    if session_type == "auto" and tasks:
        has_image = any("image" in t for t in tasks)
        has_video = any("video" in t for t in tasks)
        has_training = any("train" in t for t in tasks)

        if has_training:
            plan.session_type = SessionType.TRAINING
        elif has_video:
            plan.session_type = SessionType.VIDEO
        elif has_image:
            plan.session_type = SessionType.IMAGE
        else:
            plan.session_type = SessionType.CHAT_ONLY
    elif session_type != "auto":
        plan.session_type = SessionType(session_type)

    # Configure based on session type
    if plan.session_type == SessionType.IMAGE:
        plan.models_needed = ["flux-dev"]
        plan.min_vram_gb = 24
        plan.preferred_provider = "vast"
        plan.estimated_duration_minutes = 30
        plan.estimated_cost_usd = 0.076 * 0.5  # RTX 3090 for 30 min
        plan.auto_release_idle_minutes = 10
        reasoning.append("Image session: Flux Dev needs 24GB VRAM, Vast.ai is cheapest")

    elif plan.session_type == SessionType.VIDEO:
        plan.models_needed = ["wan-2.1"]
        plan.min_vram_gb = 24
        plan.preferred_provider = "vast"
        plan.estimated_duration_minutes = 60
        plan.estimated_cost_usd = 0.076 * 1.0  # 1 hour
        plan.auto_release_idle_minutes = 15
        reasoning.append("Video session: WAN 2.1 needs 24GB, longer sessions typical")

    elif plan.session_type == SessionType.TRAINING:
        plan.models_needed = ["flux-dev"]
        plan.min_vram_gb = 24
        plan.preferred_provider = "runpod"  # Persistent volume for models
        plan.estimated_duration_minutes = 120
        plan.estimated_cost_usd = 2.0  # Training job estimate
        plan.auto_release_idle_minutes = 5  # Release fast after training
        reasoning.append("Training: RunPod preferred (persistent volume, models cached)")

    elif plan.session_type == SessionType.MIXED:
        plan.models_needed = ["flux-dev", "wan-2.1"]
        plan.min_vram_gb = 24
        plan.preferred_provider = "vast"
        plan.estimated_duration_minutes = 60
        plan.estimated_cost_usd = 0.076 * 1.0
        plan.auto_release_idle_minutes = 10
        reasoning.append("Mixed session: may need model swaps between image/video")

    else:  # CHAT_ONLY
        plan.models_needed = []
        plan.min_vram_gb = 0
        plan.estimated_cost_usd = 0.0
        plan.auto_release_idle_minutes = 0
        reasoning.append("Chat-only: no GPU needed, using local Ollama or cloud LLM")

    # Check talent-specific LoRAs
    if talent_id and plan.session_type != SessionType.CHAT_ONLY:
        try:
            from backend.database import supabase
            loras = supabase.table("talent_loras").select("name,model_id").eq("talent_id", talent_id).eq("always_on", True).execute().data or []
            if loras:
                plan.models_needed.append(f"lora:{loras[0].get('name', 'identity')}")
                reasoning.append(f"Talent LoRA: {loras[0].get('name', '')} will be auto-loaded")
        except Exception:
            pass

    plan.reasoning = reasoning
    return plan


def should_release_worker(
    idle_minutes: float,
    session_plan: SessionPlan,
    pending_jobs: int = 0,
) -> tuple[bool, str]:
    """Determine if a worker should be released.

    Returns (should_release, reason)
    """
    if pending_jobs > 0:
        return False, f"{pending_jobs} jobs still pending"

    threshold = session_plan.auto_release_idle_minutes
    if threshold <= 0:
        return False, "No auto-release configured for this session type"

    if idle_minutes >= threshold:
        return True, f"Idle for {idle_minutes:.0f} min (threshold: {threshold} min)"

    return False, f"Idle {idle_minutes:.0f} min, threshold is {threshold} min"


def recommend_model_swap(
    current_models: list[str],
    needed_model: str,
    vram_total_gb: float,
    vram_used_gb: float,
) -> dict:
    """Recommend whether to swap models or if there's room to load another.

    Returns: {action: "load"|"swap"|"already_loaded", evict: str|None, reason: str}
    """
    if needed_model in current_models:
        return {"action": "already_loaded", "evict": None, "reason": f"{needed_model} already in VRAM"}

    # Estimate VRAM needed for the new model
    MODEL_VRAM = {
        "flux-dev": 12.0, "sdxl": 6.5, "sdxl-turbo": 6.5,
        "sd15": 4.0, "wan-2.1": 14.0,
    }
    needed_vram = MODEL_VRAM.get(needed_model, 8.0)
    free_vram = vram_total_gb - vram_used_gb

    if free_vram >= needed_vram:
        return {"action": "load", "evict": None, "reason": f"Enough free VRAM ({free_vram:.1f}GB) to load {needed_model} ({needed_vram:.1f}GB)"}

    # Need to evict something
    # Pick the least recently used model to evict
    if current_models:
        evict = current_models[-1]  # Simple: evict last loaded
        return {"action": "swap", "evict": evict, "reason": f"Need {needed_vram:.1f}GB for {needed_model}, evicting {evict}"}

    return {"action": "load", "evict": None, "reason": "VRAM empty, loading directly"}

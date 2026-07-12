"""AIOS Auto-Scaler — intelligent GPU fleet management.

Decides when to:
- Upgrade to a larger GPU (need more VRAM)
- Add another GPU instance (parallel workloads)
- Release idle instances (save money)
- Swap models between instances (optimize placement)

Decision factors:
- Current VRAM usage vs needed
- Queue depth (jobs waiting)
- Budget remaining
- Task type (can it share GPU or needs exclusive?)
- Provider pricing (cheapest option for the task)

This is the "Ogun" agent responsibility in the AIOS architecture.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# =============================================================================
# GPU Profile Knowledge
# =============================================================================

GPU_PROFILES = {
    "RTX_3090": {"vram_gb": 24, "price_range": (0.06, 0.12), "tier": "standard"},
    "RTX_4090": {"vram_gb": 24, "price_range": (0.20, 0.50), "tier": "premium"},
    "A100_40GB": {"vram_gb": 40, "price_range": (0.80, 1.50), "tier": "enterprise"},
    "A100_80GB": {"vram_gb": 80, "price_range": (1.50, 3.00), "tier": "enterprise"},
    "H100": {"vram_gb": 80, "price_range": (2.50, 4.00), "tier": "enterprise"},
}

# What each task needs
TASK_REQUIREMENTS = {
    "generate_image_flux": {"min_vram_gb": 12, "exclusive": False, "avg_seconds": 45},
    "generate_image_sdxl": {"min_vram_gb": 8, "exclusive": False, "avg_seconds": 4},
    "generate_video_wan": {"min_vram_gb": 24, "exclusive": True, "avg_seconds": 120},
    "train_lora": {"min_vram_gb": 24, "exclusive": True, "avg_seconds": 1200},
    "ollama_inference": {"min_vram_gb": 8, "exclusive": False, "avg_seconds": 10},
    "moss_tts": {"min_vram_gb": 4, "exclusive": False, "avg_seconds": 5},
    "stable_audio": {"min_vram_gb": 10, "exclusive": False, "avg_seconds": 30},
}


@dataclass
class WorkerState:
    """Current state of a GPU worker."""
    id: str
    gpu_name: str = ""
    vram_total_gb: float = 24
    vram_used_gb: float = 0
    current_task: str | None = None
    models_loaded: list[str] = field(default_factory=list)
    provider: str = "vast"  # vast or runpod
    hourly_cost: float = 0.08
    idle_minutes: float = 0
    status: str = "active"  # active, busy, idle, stopped


@dataclass
class ScaleDecision:
    """A scaling decision from the auto-scaler."""
    action: str  # "launch", "stop", "upgrade", "swap_model", "none"
    reason: str
    target_gpu: str = ""  # GPU type to launch
    target_provider: str = "vast"
    estimated_cost_hr: float = 0.0
    priority: int = 5  # 1-10
    requires_approval: bool = True


def evaluate_scaling(
    current_workers: list[WorkerState],
    pending_tasks: list[dict],
    daily_budget_remaining: float = 20.0,
) -> list[ScaleDecision]:
    """Evaluate whether the fleet needs to scale.

    Args:
        current_workers: active GPU workers and their state
        pending_tasks: tasks waiting in queue
        daily_budget_remaining: how much we can still spend today

    Returns:
        List of scaling decisions (may be empty if no action needed)
    """
    decisions = []

    if not pending_tasks:
        # No pending work — check if we should release idle workers
        for w in current_workers:
            if w.idle_minutes > float(os.getenv("FLEET_IDLE_TIMEOUT", "10")):
                decisions.append(ScaleDecision(
                    action="stop",
                    reason=f"Worker {w.id} idle for {w.idle_minutes:.0f} min (threshold: {os.getenv('FLEET_IDLE_TIMEOUT', '10')} min)",
                    requires_approval=False,
                ))
        return decisions

    # Check if current workers can handle pending tasks
    for task in pending_tasks:
        task_type = task.get("type", "generate_image_flux")
        req = TASK_REQUIREMENTS.get(task_type, TASK_REQUIREMENTS["generate_image_flux"])

        # Can any current worker handle this?
        can_handle = False
        for w in current_workers:
            if w.status == "active" and not w.current_task:
                free_vram = w.vram_total_gb - w.vram_used_gb
                if free_vram >= req["min_vram_gb"]:
                    can_handle = True
                    break
            elif w.status == "active" and not req["exclusive"]:
                free_vram = w.vram_total_gb - w.vram_used_gb
                if free_vram >= req["min_vram_gb"]:
                    can_handle = True
                    break

        if not can_handle:
            # Need more GPU capacity
            if daily_budget_remaining > 0.50:
                # Determine what GPU to launch
                gpu_type, provider, cost = _recommend_gpu(task_type, current_workers)

                decisions.append(ScaleDecision(
                    action="launch",
                    reason=f"Task '{task_type}' needs {req['min_vram_gb']}GB VRAM but no available worker has capacity",
                    target_gpu=gpu_type,
                    target_provider=provider,
                    estimated_cost_hr=cost,
                    priority=8 if req["exclusive"] else 5,
                    requires_approval=cost > 0.20,  # Auto-approve cheap instances
                ))
            else:
                decisions.append(ScaleDecision(
                    action="none",
                    reason=f"Need more GPU for '{task_type}' but daily budget nearly exhausted (${daily_budget_remaining:.2f} remaining)",
                    priority=3,
                    requires_approval=False,
                ))

    # Check if we should upgrade (e.g., multiple tasks need exclusive GPU)
    exclusive_tasks = [t for t in pending_tasks if TASK_REQUIREMENTS.get(t.get("type", ""), {}).get("exclusive")]
    if len(exclusive_tasks) > 1 and len(current_workers) < 2:
        decisions.append(ScaleDecision(
            action="launch",
            reason=f"{len(exclusive_tasks)} exclusive tasks pending — need parallel workers",
            target_gpu="RTX_3090",
            target_provider="vast",
            estimated_cost_hr=0.08,
            priority=7,
            requires_approval=True,
        ))

    return decisions


def _recommend_gpu(task_type: str, current_workers: list[WorkerState]) -> tuple[str, str, float]:
    """Recommend the best GPU for a task considering cost and availability."""
    req = TASK_REQUIREMENTS.get(task_type, TASK_REQUIREMENTS["generate_image_flux"])

    if req["min_vram_gb"] > 40:
        return "A100_80GB", "vast", 2.0
    elif req["min_vram_gb"] > 24:
        return "A100_40GB", "vast", 1.0
    elif task_type == "train_lora":
        # Training benefits from RunPod persistent volume
        return "RTX_3090", "runpod", 0.10
    else:
        return "RTX_3090", "vast", 0.08


def get_fleet_summary(workers: list[WorkerState]) -> dict:
    """Get a summary of the current fleet state."""
    total_vram = sum(w.vram_total_gb for w in workers)
    used_vram = sum(w.vram_used_gb for w in workers)
    hourly_cost = sum(w.hourly_cost for w in workers if w.status != "stopped")

    return {
        "total_workers": len(workers),
        "active_workers": len([w for w in workers if w.status == "active"]),
        "idle_workers": len([w for w in workers if w.status == "idle"]),
        "total_vram_gb": total_vram,
        "used_vram_gb": used_vram,
        "free_vram_gb": total_vram - used_vram,
        "hourly_cost_usd": hourly_cost,
        "daily_projection_usd": hourly_cost * 24,
    }

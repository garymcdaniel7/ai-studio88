"""AIOS Resource Interceptor — monitors ALL generation/training requests.

Hooks into every heavy operation regardless of source (Brain, Create page,
Training page, MCP, API) and:
1. Checks if GPU resources are available
2. If not: triggers auto-scaler to provision more
3. Logs resource usage for learning
4. Tracks patterns (time of day, task frequency, burst detection)

The interceptor learns over time:
- "User always generates at 2pm" → pre-warm worker at 1:55pm
- "User generates 10 images then trains" → suggest training after batch
- "Video generation always follows image gen" → keep WAN model warm

This is the "Ogun" (infrastructure) agent's sensing layer.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ResourceRequest:
    """A request for GPU resources."""
    task_type: str           # generate_image, generate_video, train_lora, etc.
    source: str              # "brain", "create_page", "training_page", "mcp", "api"
    model_needed: str = ""   # flux-dev, wan-2.1, etc.
    vram_needed_gb: float = 12
    exclusive: bool = False
    timestamp: float = field(default_factory=time.time)
    talent_id: str | None = None
    estimated_seconds: int = 45


# =============================================================================
# Usage Pattern Tracker (learns over time)
# =============================================================================

@dataclass
class UsagePattern:
    """Learned usage pattern."""
    hour_of_day: int         # 0-23
    task_type: str
    frequency: int = 0       # How many times this hour/task combo has occurred
    avg_gap_seconds: float = 0  # Average time between requests


class PatternTracker:
    """Tracks resource usage patterns for predictive scaling."""

    def __init__(self) -> None:
        self._history: list[ResourceRequest] = []
        self._patterns: dict[str, UsagePattern] = {}
        self._burst_window: list[float] = []  # timestamps of recent requests
        self._burst_threshold = 5  # 5 requests in 60 seconds = burst mode

    def record(self, request: ResourceRequest) -> None:
        """Record a resource request for pattern learning."""
        self._history.append(request)

        # Track burst detection
        now = time.time()
        self._burst_window = [t for t in self._burst_window if now - t < 60]
        self._burst_window.append(now)

        # Update hourly pattern
        from datetime import datetime
        hour = datetime.now().hour
        key = f"{hour}:{request.task_type}"
        if key not in self._patterns:
            self._patterns[key] = UsagePattern(hour_of_day=hour, task_type=request.task_type)
        self._patterns[key].frequency += 1

        # Persist to Supabase (non-blocking)
        self._persist_pattern(request)

    def is_burst_mode(self) -> bool:
        """Detect if user is in a burst of activity."""
        return len(self._burst_window) >= self._burst_threshold

    def predict_next_task(self) -> str | None:
        """Predict what the user will do next based on patterns.

        If the last 3 tasks were image generation and they usually
        train a LoRA after 10 images, suggest pre-warming training worker.
        """
        if len(self._history) < 3:
            return None

        recent = [r.task_type for r in self._history[-5:]]

        # Pattern: many images → training
        image_count = sum(1 for t in recent if "image" in t)
        if image_count >= 3:
            return "train_lora"  # User might want to train next

        # Pattern: image → video (animate the result)
        if recent[-1] == "generate_image":
            # Check if user frequently follows with video
            sequences = [(self._history[i].task_type, self._history[i+1].task_type) for i in range(len(self._history)-1)]
            img_to_vid = sum(1 for a, b in sequences if "image" in a and "video" in b)
            if img_to_vid > 2:
                return "generate_video"

        return None

    def get_insights(self) -> dict:
        """Get learning insights for display."""
        if not self._history:
            return {"total_requests": 0, "patterns": [], "burst_mode": False}

        from collections import Counter
        task_counts = Counter(r.task_type for r in self._history)
        source_counts = Counter(r.source for r in self._history)

        return {
            "total_requests": len(self._history),
            "task_breakdown": dict(task_counts.most_common(5)),
            "source_breakdown": dict(source_counts.most_common(5)),
            "burst_mode": self.is_burst_mode(),
            "predicted_next": self.predict_next_task(),
            "peak_hours": self._get_peak_hours(),
        }

    def _get_peak_hours(self) -> list[int]:
        """Get the hours with most activity."""
        from collections import Counter
        from datetime import datetime
        hours = Counter(datetime.fromtimestamp(r.timestamp).hour for r in self._history)
        return [h for h, _ in hours.most_common(3)]

    def _persist_pattern(self, request: ResourceRequest) -> None:
        """Persist usage data to Supabase for long-term learning."""
        try:
            from backend.database import supabase
            supabase.table("aios_decisions").insert({
                "session_id": "resource_tracking",
                "decision_type": "resource_request",
                "provider": request.source,
                "model": request.task_type,
                "input_summary": f"{request.task_type} via {request.source}",
                "output_summary": f"VRAM: {request.vram_needed_gb}GB, Model: {request.model_needed}",
                "latency_ms": request.estimated_seconds * 1000,
                "metadata": {"talent_id": request.talent_id, "exclusive": request.exclusive},
            }).execute()
        except Exception:
            pass  # Non-critical


# =============================================================================
# Singleton
# =============================================================================

_tracker: PatternTracker | None = None


def get_tracker() -> PatternTracker:
    global _tracker
    if _tracker is None:
        _tracker = PatternTracker()
    return _tracker


# =============================================================================
# Intercept function — called before every heavy operation
# =============================================================================


def intercept_resource_request(
    task_type: str,
    source: str,
    model: str = "",
    talent_id: str | None = None,
) -> dict:
    """Intercept a resource request and evaluate capacity.

    Called by every generation/training endpoint before starting work.

    Returns:
        {
            "proceed": bool — whether to start the task
            "message": str — explanation
            "scaling_needed": bool — if True, auto-scaler was triggered
            "prediction": str|None — what the system thinks comes next
        }
    """
    from backend.aios.orchestration.autoscaler import (
        TASK_REQUIREMENTS,
        WorkerState,
        evaluate_scaling,
    )

    tracker = get_tracker()

    # Build resource request
    req_info = TASK_REQUIREMENTS.get(task_type, TASK_REQUIREMENTS.get("generate_image_flux", {}))
    request = ResourceRequest(
        task_type=task_type,
        source=source,
        model_needed=model,
        vram_needed_gb=req_info.get("min_vram_gb", 12),
        exclusive=req_info.get("exclusive", False),
        talent_id=talent_id,
        estimated_seconds=req_info.get("avg_seconds", 45),
    )

    # Record for pattern learning
    tracker.record(request)

    # Check current capacity
    try:
        from backend.infrastructure.worker_api_client import get_worker_client
        client = get_worker_client()
        if client and client.is_available():
            # Worker is available — proceed
            return {
                "proceed": True,
                "message": "GPU worker available",
                "scaling_needed": False,
                "prediction": tracker.predict_next_task(),
                "burst_mode": tracker.is_burst_mode(),
            }
    except Exception:
        pass

    # No worker available — check if we should auto-provision
    workers: list[WorkerState] = []
    decisions = evaluate_scaling(workers, [{"type": task_type}])

    if decisions:
        return {
            "proceed": False,
            "message": f"No GPU available. Recommended: {decisions[0].reason}",
            "scaling_needed": True,
            "scaling_decision": {
                "action": decisions[0].action,
                "gpu": decisions[0].target_gpu,
                "provider": decisions[0].target_provider,
                "cost_hr": decisions[0].estimated_cost_hr,
            },
            "prediction": tracker.predict_next_task(),
        }

    return {
        "proceed": False,
        "message": "No GPU worker available. Launch one from Admin → Fleet.",
        "scaling_needed": False,
        "prediction": tracker.predict_next_task(),
    }

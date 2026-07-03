"""Job Router — assigns jobs to the optimal worker based on requirements.

Routing decisions consider:
- VRAM requirements
- Provider compatibility
- Model support
- Priority
- Queue length
- Worker availability
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.execution.worker_manager import Worker, list_workers, mark_worker_busy
from backend.execution.provider_interface import ExecutionRequest


@dataclass
class RoutingDecision:
    """Result of a routing decision."""
    worker_id: str
    worker_name: str
    provider: str
    reason: str
    estimated_wait_seconds: int = 0


class JobRouter:
    """Routes execution requests to the best available worker."""

    def route(self, request: ExecutionRequest) -> RoutingDecision | None:
        """Find the best worker for a request.

        Returns None if no suitable worker is available.
        """
        # Get all available workers
        available = [w for w in list_workers() if w.is_available]

        if not available:
            return None

        # Filter by VRAM requirement
        vram_needed = self._estimate_vram(request)
        capable = [w for w in available if w.gpu.vram_free_gb >= vram_needed]

        if not capable:
            # Fall back to any available worker (might work with model offloading)
            capable = available

        # Filter by model support
        if request.model:
            model_match = [w for w in capable if request.model in w.gpu.supported_models]
            if model_match:
                capable = model_match

        # Filter by provider preference
        if request.provider:
            provider_match = [w for w in capable if w.provider == request.provider]
            if provider_match:
                capable = provider_match

        # Score workers: prefer less queue, more free VRAM
        def score(w: Worker) -> float:
            vram_score = w.gpu.vram_free_gb / max(w.gpu.vram_total_gb, 1)
            queue_penalty = w.queue_size * 0.1
            return vram_score - queue_penalty

        capable.sort(key=score, reverse=True)
        best = capable[0]

        reason_parts = [f"VRAM {best.gpu.vram_free_gb:.1f}GB free"]
        if best.queue_size == 0:
            reason_parts.append("no queue")
        else:
            reason_parts.append(f"queue: {best.queue_size}")

        return RoutingDecision(
            worker_id=best.id,
            worker_name=best.name,
            provider=best.provider,
            reason=", ".join(reason_parts),
            estimated_wait_seconds=best.queue_size * 30,
        )

    def assign(self, request: ExecutionRequest) -> RoutingDecision | None:
        """Route and assign (mark worker busy). Returns decision or None."""
        decision = self.route(request)
        if decision:
            mark_worker_busy(decision.worker_id, request.job_id)
        return decision

    def _estimate_vram(self, request: ExecutionRequest) -> float:
        """Estimate VRAM requirement based on request type and model."""
        model = request.model.lower() if request.model else ""

        if "flux" in model:
            return 22.0
        elif "sdxl" in model:
            return 10.0
        elif "wan" in model or "hunyuan" in model:
            return 22.0
        elif request.type == "training":
            return 20.0
        elif request.type == "video":
            return 20.0
        elif request.type == "editing":
            return 6.0
        elif request.type == "audio":
            return 4.0
        else:
            return 12.0  # Default


# Singleton
job_router = JobRouter()

"""GPU Optimizer — routes jobs to optimal compute resources."""
from __future__ import annotations

from backend.intelligence_engine.agents.base import BaseAgent, AgentOutput
from backend.intelligence_engine.context import IntelligenceContext


class GPUOptimizer(BaseAgent):

    @property
    def name(self) -> str:
        return "GPU Optimizer"

    @property
    def role(self) -> str:
        return "Routes jobs to the best available GPU provider for cost/speed"

    def think(self, context: IntelligenceContext) -> AgentOutput:
        content_type = context.content_type
        gpu = context.gpu_status
        recs = []
        reasoning_parts = []

        # Determine VRAM requirement
        if content_type in ("video", "reel"):
            vram_needed = 24
            provider = "Vast.ai A100 80GB"
            cost = "$0.85/hr"
            time_est = "~3 min"
        elif content_type in ("carousel", "story"):
            vram_needed = 24
            provider = "Vast.ai RTX 4090"
            cost = "$0.40/hr"
            time_est = "~2 min (parallel)"
        else:
            vram_needed = 24
            provider = "Vast.ai RTX 4090"
            cost = "$0.40/hr"
            time_est = "~45 sec"

        # Check local GPU availability
        if gpu.get("status") == "idle" and gpu.get("vram_free_gb", 0) >= vram_needed:
            provider = f"Local ({gpu.get('name', 'GPU')})"
            cost = "$0.00"
            reasoning_parts.append(f"Local GPU idle with {gpu.get('vram_free_gb')}GB free → use local")
        else:
            reasoning_parts.append(f"Need {vram_needed}GB VRAM → {provider}")

        recs.append({
            "title": f"GPU: {provider}",
            "content": f"Route to {provider} at {cost}. ETA: {time_est}.",
            "type": "gpu_routing",
            "provider": provider,
            "cost": cost,
            "time_estimate": time_est,
            "vram_needed": vram_needed,
        })

        # Queue awareness
        queue_size = gpu.get("queue_size", 0)
        if queue_size > 0:
            recs.append({
                "title": "Queue Status",
                "content": f"{queue_size} job(s) ahead. Consider priority boost.",
                "type": "queue_warning",
            })
            reasoning_parts.append(f"Queue has {queue_size} jobs")

        return AgentOutput(
            agent=self.name,
            recommendations=recs,
            reasoning=" | ".join(reasoning_parts),
            confidence=0.80,
            metadata={"provider": provider, "cost": cost, "time_estimate": time_est},
        )

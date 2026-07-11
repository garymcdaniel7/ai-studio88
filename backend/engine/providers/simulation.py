"""Simulation Provider — development/testing provider.

Produces fake outputs with realistic timing and progress updates.
Used for end-to-end testing without real GPU hardware.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from typing import TYPE_CHECKING

from backend.engine.models import (
    GenerationOutput,
    GenerationProgress,
    GenerationRequest,
    GenerationType,
    ProviderCapabilities,
    ProviderHealth,
)
from backend.engine.provider import GenerationProvider

if TYPE_CHECKING:
    from collections.abc import Callable


class SimulationProvider(GenerationProvider):
    """Simulates generation with configurable delays and realistic output."""

    def __init__(self, step_delay: float = 0.3) -> None:
        self._step_delay = step_delay

    @property
    def name(self) -> str:
        return "simulation"

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            healthy=True,
            provider_name=self.name,
            message="Simulation provider always healthy",
            gpu_name="Simulated RTX 4090",
            vram_total_gb=24.0,
            vram_free_gb=20.0,
            queue_size=0,
        )

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name=self.name,
            supports_image=True,
            supports_video=True,
            supports_upscale=True,
            supports_training=True,
            supports_voice=True,
            max_resolution=4096,
            supported_models=["flux-dev", "sdxl", "wan-2.1", "any"],
            max_batch_size=4,
        )

    def submit(
        self,
        request: GenerationRequest,
        on_progress: Callable[[GenerationProgress], None] | None = None,
    ) -> GenerationOutput:
        """Simulate generation with progress updates."""
        steps = request.steps or 20
        start_time = time.time()

        # Simulate step-by-step progress
        for step in range(1, steps + 1):
            time.sleep(self._step_delay)
            if on_progress:
                on_progress(
                    GenerationProgress(
                        percent=int((step / steps) * 100),
                        step=step,
                        total_steps=steps,
                        message=f"Simulating step {step}/{steps}",
                    )
                )

        elapsed = time.time() - start_time

        # Generate a deterministic "seed" if not provided
        seed_used = request.seed if request.seed > 0 else abs(hash(request.prompt)) % 999999

        # Create a fake filename
        file_id = uuid.uuid4().hex[:12]
        ext = "mp4" if request.type == GenerationType.VIDEO else "png"
        filename = f"gen_{file_id}.{ext}"

        # Simulate file content (just a hash for testing)
        fake_content = hashlib.sha256(f"{request.prompt}-{seed_used}".encode()).digest()

        return GenerationOutput(
            file_bytes=fake_content,
            filename=filename,
            mime_type=f"video/{ext}" if ext == "mp4" else f"image/{ext}",
            width=request.width,
            height=request.height,
            seed_used=seed_used,
            generation_time_seconds=round(elapsed, 2),
            metadata={
                "provider": self.name,
                "model": request.model,
                "steps": steps,
                "cfg_scale": request.cfg_scale,
                "sampler": "euler",
                "scheduler": "normal",
                "prompt": request.prompt,
                "negative_prompt": request.negative_prompt,
                "lora": request.lora,
                "lora_strength": request.lora_strength,
            },
        )

    def cancel(self, job_id: str) -> bool:
        return True  # Simulation cancels instantly

    def validate_workflow(self, workflow: dict) -> tuple[bool, str]:
        if not workflow:
            return False, "Empty workflow"
        return True, ""

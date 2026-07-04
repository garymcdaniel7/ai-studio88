"""Training Provider Interface.

All training backends (Kohya, OneTrainer, FluxGym, Civitai, etc.)
implement this interface. AI Studio dispatches training through it
without knowing provider-specific details.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class TrainingConfig:
    """Configuration for a LoRA training job."""
    base_model: str = "flux1-dev-fp8.safetensors"
    resolution: int = 512
    rank: int = 16
    alpha: int = 16
    learning_rate: float = 1e-4
    steps: int = 1000
    repeats: int = 10
    epochs: int = 0  # 0 = use steps instead
    batch_size: int = 1
    optimizer: str = "adamw"
    scheduler: str = "cosine"
    network_dim: int = 16
    network_alpha: int = 16
    save_every_n_steps: int = 200
    trigger_words: list[str] = field(default_factory=list)
    sample_prompts: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)


@dataclass
class TrainingProgress:
    """Progress update from training."""
    step: int = 0
    total_steps: int = 0
    loss: float = 0.0
    learning_rate: float = 0.0
    message: str = ""


@dataclass
class TrainingResult:
    """Result from a completed training job."""
    success: bool = False
    output_file_bytes: bytes | None = None
    output_filename: str = ""
    total_steps: int = 0
    final_loss: float = 0.0
    training_time_seconds: float = 0.0
    logs: str = ""
    error: str | None = None
    metadata: dict = field(default_factory=dict)


class TrainingProvider(ABC):
    """Abstract base for all training providers."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def health(self) -> dict: ...

    @abstractmethod
    def validate_dataset(self, image_count: int, config: TrainingConfig) -> tuple[bool, str]: ...

    @abstractmethod
    def submit(self, dataset_path: str, config: TrainingConfig,
               on_progress: Callable[[TrainingProgress], None] | None = None) -> TrainingResult: ...

    @abstractmethod
    def cancel(self, job_id: str) -> bool: ...


# =============================================================================
# Simulated Training Provider
# =============================================================================

import time
import hashlib
import uuid


class SimulatedTrainingProvider(TrainingProvider):
    """Simulates LoRA training for development/testing."""

    @property
    def name(self) -> str:
        return "simulation"

    def health(self) -> dict:
        return {"healthy": True, "provider": self.name, "message": "Simulation always ready"}

    def validate_dataset(self, image_count: int, config: TrainingConfig) -> tuple[bool, str]:
        if image_count < 5:
            return False, f"Need at least 5 images, got {image_count}"
        if image_count > 200:
            return False, f"Max 200 images, got {image_count}"
        return True, ""

    def submit(self, dataset_path: str, config: TrainingConfig,
               on_progress: Callable[[TrainingProgress], None] | None = None) -> TrainingResult:
        """Simulate training with progress updates."""
        start = time.time()
        total_steps = config.steps
        step_delay = 0.01  # Fast for simulation

        for step in range(1, total_steps + 1):
            time.sleep(step_delay)
            if on_progress and step % 100 == 0:
                loss = max(0.01, 0.5 - (step / total_steps) * 0.4)
                on_progress(TrainingProgress(
                    step=step, total_steps=total_steps,
                    loss=loss, learning_rate=config.learning_rate,
                    message=f"Step {step}/{total_steps}, loss={loss:.4f}",
                ))

        # Generate fake LoRA output
        fake_lora = hashlib.sha256(f"lora-{dataset_path}-{time.time()}".encode()).digest() * 32
        filename = f"lora_{uuid.uuid4().hex[:8]}.safetensors"

        return TrainingResult(
            success=True,
            output_file_bytes=fake_lora,
            output_filename=filename,
            total_steps=total_steps,
            final_loss=0.08,
            training_time_seconds=round(time.time() - start, 2),
            logs=f"Training completed: {total_steps} steps, final loss 0.08",
            metadata={
                "provider": self.name,
                "config": {
                    "base_model": config.base_model,
                    "rank": config.rank,
                    "resolution": config.resolution,
                    "learning_rate": config.learning_rate,
                    "steps": config.steps,
                    "optimizer": config.optimizer,
                    "trigger_words": config.trigger_words,
                },
            },
        )

    def cancel(self, job_id: str) -> bool:
        return True

    def capabilities(self) -> dict:
        """Return simulated training capabilities."""
        return {
            "provider": self.name,
            "supported_base_models": [
                "flux1-dev-fp8.safetensors",
                "sd_xl_base_1.0.safetensors",
            ],
            "max_steps": 5000,
            "max_images": 200,
            "min_images": 5,
            "min_vram_gb": 0,
            "supported_optimizers": ["adamw"],
            "supported_schedulers": ["cosine"],
            "max_resolution": 1024,
            "supported_ranks": [4, 8, 16, 32, 64, 128],
            "live_mode": False,
        }


# =============================================================================
# Provider Registry
# =============================================================================

TRAINING_PROVIDERS: dict[str, type[TrainingProvider]] = {
    "simulation": SimulatedTrainingProvider,
    # Future: "kohya", "onetrainer", "fluxgym", "civitai", "replicate"
}


def _register_vast_provider():
    """Lazily register VastTrainingProvider to avoid circular imports."""
    from backend.training.vast_provider import VastTrainingProvider
    TRAINING_PROVIDERS["vast"] = VastTrainingProvider


_register_vast_provider()


def get_training_provider(name: str = "simulation") -> TrainingProvider:
    cls = TRAINING_PROVIDERS.get(name)
    if not cls:
        raise ValueError(f"Unknown training provider: {name}")
    return cls()

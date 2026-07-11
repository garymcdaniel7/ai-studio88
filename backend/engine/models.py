"""Internal workflow models for the Generation Engine.

These are provider-agnostic representations. The translation layer
converts them to provider-specific payloads (ComfyUI JSON, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class GenerationStatus(StrEnum):
    QUEUED = "queued"
    PROVISIONING = "provisioning"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class GenerationType(StrEnum):
    IMAGE = "image_generation"
    VIDEO = "video_generation"
    UPSCALE = "image_upscale"
    EDIT = "image_edit"
    LORA_TRAINING = "lora_training"
    VOICE = "voice_generation"
    WORKFLOW = "workflow_execution"


@dataclass
class GenerationRequest:
    """A request to generate content. Created from a ProductionPlan."""

    type: GenerationType
    prompt: str
    negative_prompt: str = ""
    width: int = 1024
    height: int = 1024
    steps: int = 20
    cfg_scale: float = 7.0
    seed: int = -1
    model: str = "flux-dev"
    lora: str | None = None
    lora_strength: float = 0.7
    # Extra params for provider-specific features
    extra: dict = field(default_factory=dict)
    # Context links
    talent_id: str | None = None
    project_id: str | None = None
    workflow_id: str | None = None
    creative_session_id: str | None = None


@dataclass
class GenerationOutput:
    """Output from a completed generation."""

    file_path: str | None = None
    file_bytes: bytes | None = None
    file_url: str | None = None
    filename: str = ""
    mime_type: str = "image/png"
    width: int | None = None
    height: int | None = None
    seed_used: int | None = None
    generation_time_seconds: float = 0.0
    metadata: dict = field(default_factory=dict)


@dataclass
class GenerationProgress:
    """Progress update from a running generation."""

    percent: int = 0
    step: int = 0
    total_steps: int = 0
    preview_url: str | None = None
    message: str = ""


@dataclass
class ProviderCapabilities:
    """What a provider can do."""

    name: str
    supports_image: bool = True
    supports_video: bool = False
    supports_upscale: bool = True
    supports_training: bool = False
    supports_voice: bool = False
    max_resolution: int = 2048
    supported_models: list[str] = field(default_factory=list)
    max_batch_size: int = 1


@dataclass
class ProviderHealth:
    """Health status of a provider."""

    healthy: bool = False
    provider_name: str = ""
    message: str = ""
    gpu_name: str | None = None
    vram_total_gb: float | None = None
    vram_free_gb: float | None = None
    queue_size: int = 0
    current_job: str | None = None


@dataclass
class ModelInfo:
    """Registry entry for a model (checkpoint, LoRA, VAE, etc.)."""

    id: str = ""
    name: str = ""
    type: str = "checkpoint"  # checkpoint, lora, vae, controlnet, embedding, upscaler, ipadapter
    version: str = "1.0"
    provider: str = ""
    path: str = ""
    capabilities: list[str] = field(default_factory=list)
    required_vram_gb: float = 0.0
    supported_resolutions: list[str] = field(default_factory=list)
    status: str = "available"  # available, downloading, unavailable
    metadata: dict = field(default_factory=dict)

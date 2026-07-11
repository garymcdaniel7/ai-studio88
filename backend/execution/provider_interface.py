"""Execution Provider Interfaces.

Each media type has its own provider interface. Providers are completely
replaceable — no provider-specific logic exists outside the provider layer.

The hierarchy:
  ExecutionProvider (base)
    ├── ImageProvider (Flux, SDXL, ComfyUI, Forge)
    ├── VideoProvider (WAN, Hunyuan, LTX)
    ├── TrainingProvider (LoRA training, fine-tuning)
    ├── AudioProvider (ElevenLabs, XTTS, OpenVoice)
    └── EditingProvider (upscale, face swap, lip sync, compositing)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass
class ExecutionRequest:
    """A request to execute a task on a worker."""

    job_id: str = ""
    type: str = "image"  # image, video, training, audio, editing
    provider: str = ""
    model: str = ""
    parameters: dict = field(default_factory=dict)
    priority: int = 5
    timeout_seconds: int = 300
    # Context
    talent_id: str | None = None
    project_id: str | None = None
    workflow_id: str | None = None


@dataclass
class ExecutionResult:
    """Result from a completed execution."""

    success: bool = False
    output_bytes: bytes | None = None
    output_url: str | None = None
    filename: str = ""
    mime_type: str = ""
    runtime_seconds: float = 0.0
    metadata: dict = field(default_factory=dict)
    error: str | None = None


@dataclass
class ProviderInfo:
    """Static information about a provider."""

    name: str
    type: str  # image, video, training, audio, editing
    version: str = "1.0"
    supported_models: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    min_vram_gb: float = 0.0
    status: str = "available"  # available, unavailable, degraded


@dataclass
class ProviderHealthStatus:
    """Health status of a provider."""

    name: str
    healthy: bool = False
    message: str = ""
    latency_ms: float = 0.0
    queue_size: int = 0


class ExecutionProvider(ABC):
    """Base class for all execution providers."""

    @property
    @abstractmethod
    def info(self) -> ProviderInfo:
        """Static provider information."""
        ...

    @abstractmethod
    def health(self) -> ProviderHealthStatus:
        """Check provider health."""
        ...

    @abstractmethod
    def execute(
        self, request: ExecutionRequest, on_progress: Callable | None = None
    ) -> ExecutionResult:
        """Execute a request. Blocks until complete (for sync execution)."""
        ...

    @abstractmethod
    def cancel(self, job_id: str) -> bool:
        """Cancel a running job."""
        ...

    @abstractmethod
    def supports(self, model: str) -> bool:
        """Check if this provider supports a given model."""
        ...


class ImageProvider(ExecutionProvider):
    """Interface for image generation providers (Flux, SDXL, ComfyUI, Forge)."""

    pass


class VideoProvider(ExecutionProvider):
    """Interface for video generation providers (WAN, Hunyuan, LTX)."""

    pass


class TrainingProvider(ExecutionProvider):
    """Interface for training providers (LoRA, DreamBooth)."""

    pass


class AudioProvider(ExecutionProvider):
    """Interface for audio/voice providers (ElevenLabs, XTTS, OpenVoice)."""

    pass


class EditingProvider(ExecutionProvider):
    """Interface for post-processing (upscale, face swap, lip sync)."""

    pass

"""Provider Registry — tracks all available execution providers.

Providers register themselves here. The job router queries this registry
to find which providers can handle a given request.

Future providers are added by:
1. Implementing ExecutionProvider (or subtype)
2. Registering in PROVIDER_REGISTRY
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.execution.provider_interface import (
    ExecutionProvider,
    ExecutionRequest,
    ExecutionResult,
    ProviderInfo,
    ProviderHealthStatus,
)


# =============================================================================
# Simulated Provider (development/testing)
# =============================================================================

import time
import uuid
import hashlib


class SimulatedExecutionProvider(ExecutionProvider):
    """Simulates execution for development. Follows the full interface."""

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(
            name="simulation",
            type="image",
            version="1.0",
            supported_models=["flux-dev", "sdxl", "wan-2.1", "any"],
            capabilities=["txt2img", "img2img", "upscale", "video", "training"],
            min_vram_gb=0.0,
            status="available",
        )

    def health(self) -> ProviderHealthStatus:
        return ProviderHealthStatus(
            name="simulation",
            healthy=True,
            message="Simulation always healthy",
            latency_ms=1.0,
            queue_size=0,
        )

    def execute(self, request: ExecutionRequest, on_progress=None) -> ExecutionResult:
        steps = request.parameters.get("steps", 5)
        delay = request.parameters.get("step_delay", 0.3)
        start = time.time()

        for i in range(1, steps + 1):
            time.sleep(delay)
            if on_progress:
                on_progress(int((i / steps) * 100))

        fake_bytes = hashlib.sha256(f"{request.job_id}-{time.time()}".encode()).digest()
        filename = f"sim_{uuid.uuid4().hex[:8]}.png"

        return ExecutionResult(
            success=True,
            output_bytes=fake_bytes,
            filename=filename,
            mime_type="image/png",
            runtime_seconds=round(time.time() - start, 2),
            metadata={
                "provider": "simulation",
                "model": request.model,
                "parameters": request.parameters,
            },
        )

    def cancel(self, job_id: str) -> bool:
        return True

    def supports(self, model: str) -> bool:
        return True  # Simulation supports everything


# =============================================================================
# Placeholder Providers (stubs for future implementation)
# =============================================================================

class _PlaceholderProvider(ExecutionProvider):
    """Base for placeholder providers that aren't implemented yet."""
    _name: str = "placeholder"
    _type: str = "image"
    _models: list = []

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(
            name=self._name, type=self._type,
            supported_models=self._models,
            capabilities=[], status="unavailable",
        )

    def health(self) -> ProviderHealthStatus:
        return ProviderHealthStatus(name=self._name, healthy=False, message="Not implemented yet")

    def execute(self, request, on_progress=None) -> ExecutionResult:
        return ExecutionResult(success=False, error=f"{self._name} provider not implemented")

    def cancel(self, job_id: str) -> bool:
        return False

    def supports(self, model: str) -> bool:
        return model.lower() in [m.lower() for m in self._models]


class ComfyUIExecutionProvider(_PlaceholderProvider):
    _name = "comfyui"
    _type = "image"
    _models = ["flux-dev", "sdxl", "sd1.5", "pony"]


class WanExecutionProvider(_PlaceholderProvider):
    _name = "wan"
    _type = "video"
    _models = ["wan-2.1"]


class HunyuanExecutionProvider(_PlaceholderProvider):
    _name = "hunyuan"
    _type = "video"
    _models = ["hunyuan-video"]


class ForgeExecutionProvider(_PlaceholderProvider):
    _name = "forge"
    _type = "image"
    _models = ["sdxl", "sd1.5", "flux-dev"]


class InvokeAIExecutionProvider(_PlaceholderProvider):
    _name = "invokeai"
    _type = "image"
    _models = ["sdxl", "flux-dev"]


class ElevenLabsExecutionProvider(_PlaceholderProvider):
    _name = "elevenlabs"
    _type = "audio"
    _models = ["eleven-turbo", "eleven-multilingual"]


class XTTSExecutionProvider(_PlaceholderProvider):
    _name = "xtts"
    _type = "audio"
    _models = ["xtts-v2"]


class OpenVoiceExecutionProvider(_PlaceholderProvider):
    _name = "openvoice"
    _type = "audio"
    _models = ["openvoice-v2"]


# =============================================================================
# Registry
# =============================================================================

PROVIDER_REGISTRY: dict[str, type[ExecutionProvider]] = {
    "simulation": SimulatedExecutionProvider,
    "comfyui": ComfyUIExecutionProvider,
    "wan": WanExecutionProvider,
    "hunyuan": HunyuanExecutionProvider,
    "forge": ForgeExecutionProvider,
    "invokeai": InvokeAIExecutionProvider,
    "elevenlabs": ElevenLabsExecutionProvider,
    "xtts": XTTSExecutionProvider,
    "openvoice": OpenVoiceExecutionProvider,
}


def get_provider(name: str) -> ExecutionProvider | None:
    """Get a provider instance by name."""
    cls = PROVIDER_REGISTRY.get(name)
    return cls() if cls else None


def list_providers() -> list[dict]:
    """List all registered providers with their info and health."""
    result = []
    for name, cls in PROVIDER_REGISTRY.items():
        p = cls()
        info = p.info
        health = p.health()
        result.append({
            "name": info.name,
            "type": info.type,
            "version": info.version,
            "status": info.status,
            "healthy": health.healthy,
            "message": health.message,
            "supported_models": info.supported_models,
            "capabilities": info.capabilities,
        })
    return result


def get_all_healthy_providers() -> list[ExecutionProvider]:
    """Get all providers that are currently healthy."""
    return [cls() for cls in PROVIDER_REGISTRY.values() if cls().health().healthy]

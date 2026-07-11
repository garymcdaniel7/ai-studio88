"""Generation Engine — orchestrates content generation through providers.

Responsibilities:
- Accept production plans from Creative Session
- Convert plans into executable GenerationRequests
- Queue and track jobs
- Dispatch to the appropriate provider
- Handle progress updates
- Register outputs as Assets
- Update job/workflow records

Usage:
    from backend.engine.generation_engine import GenerationEngine
    engine = GenerationEngine()
    result = engine.generate(request)
"""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv

from backend.engine.models import (
    GenerationOutput,
    GenerationRequest,
    ProviderHealth,
)
from backend.engine.provider import (
    GenerationProvider,
    ProviderError,
)
from backend.engine.providers.comfyui import ComfyUIProvider
from backend.engine.providers.simulation import SimulationProvider

load_dotenv()

# =============================================================================
# Provider Registry
# =============================================================================

PROVIDERS: dict[str, type[GenerationProvider]] = {
    "simulation": SimulationProvider,
    "comfyui": ComfyUIProvider,
}


def get_default_provider_name() -> str:
    """Get the configured default provider from environment."""
    return os.getenv("GENERATION_PROVIDER", "simulation")


# =============================================================================
# Model Registry (in-memory for now, DB-backed in future)
# =============================================================================

from backend.engine.models import ModelInfo

MODEL_REGISTRY: list[ModelInfo] = [
    ModelInfo(
        id="flux-dev",
        name="FLUX.1-dev",
        type="checkpoint",
        version="1.0",
        provider="black-forest-labs",
        path="flux1-dev-fp8.safetensors",
        capabilities=["txt2img", "img2img"],
        required_vram_gb=24.0,
        supported_resolutions=["512x512", "768x768", "1024x1024", "1536x1536"],
        status="available",
    ),
    ModelInfo(
        id="sdxl",
        name="Stable Diffusion XL",
        type="checkpoint",
        version="1.0",
        provider="stability-ai",
        path="sd_xl_base_1.0.safetensors",
        capabilities=["txt2img", "img2img", "inpainting"],
        required_vram_gb=12.0,
        supported_resolutions=["512x512", "768x768", "1024x1024"],
        status="available",
    ),
    ModelInfo(
        id="wan-2.1",
        name="WAN Video 2.1",
        type="checkpoint",
        version="2.1",
        provider="wan",
        path="wan_2.1.safetensors",
        capabilities=["txt2video", "img2video"],
        required_vram_gb=24.0,
        supported_resolutions=["512x512", "768x768"],
        status="available",
    ),
]


def get_model_registry() -> list[ModelInfo]:
    """Get all registered models."""
    return MODEL_REGISTRY


def get_model(model_id: str) -> ModelInfo | None:
    """Get a model by ID."""
    for m in MODEL_REGISTRY:
        if m.id == model_id:
            return m
    return None


# =============================================================================
# GPU Manager (simulated metrics for now)
# =============================================================================

from dataclasses import dataclass


@dataclass
class GPUStatus:
    """Current GPU status."""

    name: str = "Simulated RTX 4090"
    vram_total_gb: float = 24.0
    vram_free_gb: float = 20.0
    temperature_c: int = 45
    utilization_pct: int = 0
    queue_size: int = 0
    current_job: str | None = None
    estimated_finish: str | None = None
    provider: str = "simulation"
    status: str = "idle"  # idle, busy, offline


_gpu_status = GPUStatus()


def get_gpu_status() -> GPUStatus:
    """Get current GPU status (simulated)."""
    return _gpu_status


def update_gpu_status(**kwargs) -> GPUStatus:
    """Update GPU status fields."""
    global _gpu_status
    for k, v in kwargs.items():
        if hasattr(_gpu_status, k):
            setattr(_gpu_status, k, v)
    return _gpu_status


# =============================================================================
# Generation Engine
# =============================================================================


class GenerationEngine:
    """Main engine that orchestrates generation through providers."""

    def __init__(self, provider_name: str | None = None) -> None:
        name = provider_name or get_default_provider_name()
        provider_class = PROVIDERS.get(name)
        if not provider_class:
            raise ValueError(f"Unknown provider: {name}. Available: {list(PROVIDERS.keys())}")
        self._provider: GenerationProvider = provider_class()
        self._provider_name = name

    @property
    def provider_name(self) -> str:
        return self._provider_name

    def health(self) -> ProviderHealth:
        """Check provider health."""
        return self._provider.health()

    def generate(
        self,
        request: GenerationRequest,
        on_progress: Any = None,
    ) -> GenerationOutput:
        """Execute a generation request through the configured provider.

        Args:
            request: The generation request
            on_progress: Optional callback(GenerationProgress)

        Returns:
            GenerationOutput with file data and metadata

        Raises:
            ProviderError on failure
        """
        # Update GPU status
        update_gpu_status(
            status="busy",
            current_job=f"{request.type.value}",
            utilization_pct=80,
            vram_free_gb=_gpu_status.vram_total_gb * 0.3,
        )

        try:
            output = self._provider.submit(request, on_progress)

            # Enrich output metadata
            output.metadata["provider"] = self._provider_name
            output.metadata["generation_type"] = request.type.value
            if request.talent_id:
                output.metadata["talent_id"] = request.talent_id
            if request.project_id:
                output.metadata["project_id"] = request.project_id
            if request.creative_session_id:
                output.metadata["creative_session_id"] = request.creative_session_id

            return output

        finally:
            # Reset GPU status
            update_gpu_status(
                status="idle",
                current_job=None,
                utilization_pct=0,
                vram_free_gb=_gpu_status.vram_total_gb * 0.85,
            )

    def generate_and_register(
        self,
        request: GenerationRequest,
        on_progress: Any = None,
    ) -> dict:
        """Generate content AND register the output as an asset.

        This is the full pipeline:
        1. Execute generation via provider
        2. Upload output to B2 storage
        3. Create asset record in Supabase
        4. Return the asset record

        Returns:
            dict: The created asset record from Supabase
        """
        from backend.database import create_asset
        from backend.storage import compute_checksum, generate_storage_key, upload_file

        # Generate
        output = self.generate(request, on_progress)

        if not output.file_bytes:
            raise ProviderError(self._provider_name, "Provider returned no file data")

        # Upload to B2
        storage_key = generate_storage_key(
            original_filename=output.filename,
            asset_type=request.type.value.replace("_generation", "").replace("image_", ""),
            project_id=request.project_id,
        )

        checksum = compute_checksum(output.file_bytes)
        public_url = upload_file(output.file_bytes, storage_key, output.mime_type)

        # Create asset record
        asset_data = {
            "project_id": request.project_id,
            "talent_id": request.talent_id,
            "type": request.type.value.replace("_generation", "").replace("image_", "image"),
            "filename": output.filename,
            "original_filename": output.filename,
            "mime_type": output.mime_type,
            "size_bytes": len(output.file_bytes),
            "storage_provider": "backblaze_b2",
            "storage_key": storage_key,
            "public_url": public_url,
            "checksum": checksum,
            "metadata": {
                **output.metadata,
                "seed_used": output.seed_used,
                "generation_time_seconds": output.generation_time_seconds,
                "width": output.width,
                "height": output.height,
            },
            "tags": [request.type.value, request.model, self._provider_name],
        }

        result = create_asset(asset_data)
        return result.data[0] if result.data else asset_data

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
from backend.engine.providers.thunder_h3 import ThunderH3Provider
from backend.generation_cost_gate import estimate_generation_cost, execute_with_cost_gate

load_dotenv()

# =============================================================================
# Provider Registry
# =============================================================================

PROVIDERS: dict[str, type[GenerationProvider]] = {
    "simulation": SimulationProvider,
    "comfyui": ComfyUIProvider,
    "thunder-h3": ThunderH3Provider,
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
    ModelInfo(
        id="thunder-h3",
        name="MiniMax H3 (Thunder A6000 — local)",
        type="checkpoint",
        version="1.0",
        provider="thunder-h3",
        path="minimax_h3_fl2va_pruned_int8_convrot.safetensors",
        capabilities=["img2video"],
        required_vram_gb=48.0,
        supported_resolutions=["768x1152"],
        status="available",
        metadata={
            "fps": 24,
            "max_duration_seconds": 25,
            "lengths": [124, 141, 209, 226, 243, 260, 277, 294, 362, 480, 600],
            "notes": "Gary's Thunder A6000 box - uncensored local H3 (ComfyUI). "
                     "Image-to-video only, native 32kHz audio, 8-step res_multistep.",
        },
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
        from backend.compliance.filters import enforce_prompt_compliance

        enforce_prompt_compliance(request.prompt)

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
        org_id: str,
        on_progress: Any = None,
        *,
        job_id: str,
        estimated_cost_usd: float | None = None,
    ) -> dict:
        """Generate, store, and register an output behind the shared cost gate.

        The legacy synchronous path is bridged into the same gate used by
        ``Worker._process_job``. Reservation happens before provider execution;
        finalization happens only after B2 upload and asset registration. Any
        provider, timeout, scan, storage, or database failure releases the
        active reservation while ``generate`` retains its GPU cleanup ``finally``.
        """
        from backend.compliance.output_scan import scan_generated_output
        from backend.database import create_asset
        from backend.storage import compute_checksum, generate_storage_key, upload_file

        if not org_id:
            raise ValueError("org_id is required before generation")
        if not job_id:
            raise ValueError("job_id is required before generation")

        # The authenticated/API command context is authoritative. Never permit a
        # request payload's optional org_id to become asset or storage ownership.
        request.org_id = org_id
        estimate = estimated_cost_usd or estimate_generation_cost(
            request.model,
            request.steps,
            request.type.value,
        )
        model_info = get_model(request.model)
        model_version = model_info.version if model_info else "unknown"

        def generate_and_store() -> dict:
            output = self.generate(request, on_progress)
            if not output.file_bytes:
                raise ProviderError(self._provider_name, "Provider returned no file data")

            output.metadata.update(
                {
                    "org_id": org_id,
                    "job_id": job_id,
                    "workflow_id": request.workflow_id,
                    "model_id": request.model,
                    "model_version": model_version,
                    "estimated_cost_usd": estimate,
                }
            )
            scan_generated_output(
                output.file_bytes,
                asset_id=None,
                org_id=org_id,
                metadata=output.metadata,
            )

            storage_key = generate_storage_key(
                original_filename=output.filename,
                asset_type=request.type.value.replace("_generation", "").replace("image_", ""),
                project_id=request.project_id,
                org_id=org_id,
                talent_id=request.talent_id,
                job_id=job_id,
            )
            checksum = compute_checksum(output.file_bytes)
            public_url = upload_file(
                output.file_bytes,
                storage_key,
                output.mime_type,
                org_id=org_id,
                job_id=job_id,
                metadata={
                    "workflow_id": request.workflow_id or "",
                    "model_id": request.model,
                    "model_version": model_version,
                },
            )

            actual_cost = output.metadata.get("actual_cost_usd", estimate)
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
                    "actual_cost_usd": actual_cost,
                },
                "tags": [request.type.value, request.model, self._provider_name],
            }
            result = create_asset(asset_data, org_id)
            return result.data[0] if result.data else asset_data

        return execute_with_cost_gate(
            org_id=org_id,
            job_id=job_id,
            operation=f"generation:{request.type.value}",
            provider=self._provider_name,
            estimated_cost_usd=estimate,
            execute=generate_and_store,
            actual_cost=lambda asset, fallback: float(
                asset.get("metadata", {}).get("actual_cost_usd", fallback)
            ),
        )

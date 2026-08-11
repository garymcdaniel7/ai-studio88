"""Simulation compute provider for testing and development.

Returns synthetic results without provisioning real infrastructure.
Used in unit tests, local development, and CI pipelines.

Validates: Requirements R13.1, R24.1
"""

from __future__ import annotations

import uuid

from backend.app.providers.compute import (
    ComputeProviderCapabilities,
    ComputeRequirements,
    CostEstimate,
    HealthState,
    HealthStatus,
    InstanceHandle,
    InstanceState,
    InstanceStatus,
    OfferInfo,
)


class SimulationProvider:
    """Compute provider that simulates provisioning without real GPUs.

    All methods return synthetic, deterministic results suitable for testing.
    No external calls are made.
    """

    def __init__(self) -> None:
        self._instances: dict[str, InstanceState] = {}

    @property
    def capabilities(self) -> ComputeProviderCapabilities:
        """Return simulation provider capabilities."""
        return ComputeProviderCapabilities(
            name="simulation",
            display_name="Simulation (Testing)",
            supports_persistent_storage=True,
            supports_network_volume=True,
            supports_stop_resume=True,
            supports_snapshot=True,
            supports_multi_gpu=True,
            supports_autoscaling=False,
            supports_private_networking=False,
            supports_custom_images=True,
            supports_worker_health=True,
            supports_cost_estimation=True,
            min_vram_gb=8,
            max_vram_gb=80,
            regions=["sim-us-east", "sim-eu-west"],
            gpu_types=["RTX_4090", "A100_80GB", "H100"],
            startup_time_seconds=1,
        )

    async def provision(self, requirements: ComputeRequirements) -> InstanceHandle:
        """Simulate instance provisioning.

        Returns a handle with a generated instance ID immediately.
        """
        instance_id = f"sim-{uuid.uuid4().hex[:12]}"
        self._instances[instance_id] = InstanceState.RUNNING
        return InstanceHandle(
            instance_id=instance_id,
            host="127.0.0.1",
            port=8188,
            state=InstanceState.RUNNING,
        )

    async def terminate(self, instance_id: str) -> None:
        """Simulate instance termination."""
        self._instances[instance_id] = InstanceState.TERMINATED

    async def health_check(self, instance_id: str) -> HealthStatus:
        """Simulate health check — always returns healthy for known instances."""
        state = self._instances.get(instance_id)
        if state is None or state == InstanceState.TERMINATED:
            return HealthStatus(
                instance_id=instance_id,
                state=HealthState.UNREACHABLE,
                message="Instance not found or terminated",
            )
        return HealthStatus(
            instance_id=instance_id,
            state=HealthState.HEALTHY,
            message="Simulation healthy",
            latency_ms=1.0,
        )

    async def get_status(self, instance_id: str) -> InstanceStatus:
        """Simulate status retrieval."""
        state = self._instances.get(instance_id, InstanceState.TERMINATED)
        return InstanceStatus(
            instance_id=instance_id,
            state=state,
            uptime_seconds=60.0 if state == InstanceState.RUNNING else 0.0,
            gpu_utilization_pct=25.0 if state == InstanceState.RUNNING else None,
            vram_used_gb=4.0 if state == InstanceState.RUNNING else None,
        )

    async def list_available(self) -> list[OfferInfo]:
        """Return synthetic offers for testing."""
        return [
            OfferInfo(
                offer_id="sim-offer-4090",
                gpu_name="RTX 4090",
                vram_gb=24,
                price_per_hour_usd=0.40,
                available=True,
                region="sim-us-east",
            ),
            OfferInfo(
                offer_id="sim-offer-a100",
                gpu_name="A100 80GB",
                vram_gb=80,
                price_per_hour_usd=1.20,
                available=True,
                region="sim-us-east",
            ),
            OfferInfo(
                offer_id="sim-offer-h100",
                gpu_name="H100",
                vram_gb=80,
                price_per_hour_usd=2.50,
                available=True,
                region="sim-eu-west",
            ),
        ]

    async def estimate_cost(self, requirements: ComputeRequirements) -> CostEstimate:
        """Return a deterministic cost estimate for testing."""
        # Simple formula: $0.50/hr base, scale by VRAM
        hourly_rate = 0.50 * (requirements.vram_gb / 12)
        duration = requirements.max_duration_seconds
        total = hourly_rate * (duration / 3600)
        return CostEstimate(
            estimated_usd=round(total, 4),
            estimated_duration_seconds=duration,
            confidence=1.0,
        )

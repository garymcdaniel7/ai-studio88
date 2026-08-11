"""Provider-agnostic compute interface.

Defines the ComputeProvider Protocol and supporting dataclasses.
This module MUST NOT import from any provider-specific packages.

Validates: Requirements R13.1, R13.2, R13.3, R13.4
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable
from uuid import UUID


# =============================================================================
# Enums
# =============================================================================


class InstanceState(str, Enum):
    """Generic instance lifecycle states — provider-agnostic."""

    PENDING = "pending"
    PROVISIONING = "provisioning"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"
    TERMINATED = "terminated"


class HealthState(str, Enum):
    """Health check result states — provider-agnostic."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNREACHABLE = "unreachable"


class ComputeMode(str, Enum):
    """Compute ownership mode per workspace (R13.2)."""

    PLATFORM_MANAGED = "platform_managed"
    CUSTOMER_MANAGED = "customer_managed"
    HYBRID = "hybrid"


# =============================================================================
# Dataclasses (generic — no provider-specific fields)
# =============================================================================


@dataclass(frozen=True)
class ComputeProviderCapabilities:
    """Capabilities a compute provider may or may not support.

    Used by the workload scheduler to route only to providers
    satisfying the workload's required capabilities (A2-002).

    Validates: Requirements R13.3, R13.4, A2-002
    """

    name: str
    display_name: str
    supports_persistent_storage: bool = False
    supports_network_volume: bool = False
    supports_stop_resume: bool = False
    supports_snapshot: bool = False
    supports_multi_gpu: bool = False
    supports_autoscaling: bool = False
    supports_private_networking: bool = False
    supports_custom_images: bool = False
    supports_worker_health: bool = False
    supports_cost_estimation: bool = False
    min_vram_gb: int = 8
    max_vram_gb: int = 80
    regions: list[str] = field(default_factory=list)
    gpu_types: list[str] = field(default_factory=list)
    startup_time_seconds: int = 120

    def satisfies(self, required: list[str]) -> bool:
        """Check if this provider satisfies all required capability flags.

        Args:
            required: List of capability names (e.g., ['persistent_storage', 'multi_gpu']).

        Returns:
            True if all required capabilities are supported.
        """
        capability_map = {
            "persistent_storage": self.supports_persistent_storage,
            "network_volume": self.supports_network_volume,
            "stop_resume": self.supports_stop_resume,
            "snapshot": self.supports_snapshot,
            "multi_gpu": self.supports_multi_gpu,
            "autoscaling": self.supports_autoscaling,
            "private_networking": self.supports_private_networking,
            "custom_images": self.supports_custom_images,
            "worker_health": self.supports_worker_health,
            "cost_estimation": self.supports_cost_estimation,
        }
        return all(capability_map.get(cap, False) for cap in required)


@dataclass(frozen=True)
class ComputeRequirements:
    """Requirements for provisioning a compute instance."""

    vram_gb: int
    gpu_count: int = 1
    storage_gb: int = 50
    cuda_version: str = "11.8"
    workload_type: str = "image_generation"
    model_ids: list[str] = field(default_factory=list)
    max_duration_seconds: int = 1800
    org_id: UUID | None = None
    required_capabilities: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class InstanceHandle:
    """Handle to a provisioned compute instance — provider-agnostic."""

    instance_id: str
    host: str
    port: int
    state: InstanceState = InstanceState.RUNNING


@dataclass(frozen=True)
class HealthStatus:
    """Health check result for a compute instance."""

    instance_id: str
    state: HealthState
    message: str = ""
    latency_ms: float | None = None


@dataclass(frozen=True)
class InstanceStatus:
    """Current status of a compute instance."""

    instance_id: str
    state: InstanceState
    uptime_seconds: float = 0.0
    gpu_utilization_pct: float | None = None
    vram_used_gb: float | None = None


@dataclass(frozen=True)
class OfferInfo:
    """Available compute offer — provider-agnostic."""

    offer_id: str
    gpu_name: str
    vram_gb: int
    price_per_hour_usd: float
    available: bool = True
    region: str = ""


@dataclass(frozen=True)
class CostEstimate:
    """Estimated cost for a workload — provider-agnostic."""

    estimated_usd: float
    estimated_duration_seconds: int
    confidence: float = 0.8  # 0.0 to 1.0


# =============================================================================
# Exceptions
# =============================================================================


class ComputeProviderError(Exception):
    """Base exception for compute provider operations."""

    def __init__(self, message: str, provider: str | None = None) -> None:
        self.message = message
        self.provider = provider
        super().__init__(message)


class ProvisionError(ComputeProviderError):
    """Raised when provisioning fails (transient — may retry)."""


class TerminateError(ComputeProviderError):
    """Raised when termination fails."""


class ProviderUnavailableError(ComputeProviderError):
    """Raised when the provider is unreachable (maps to HTTP 503)."""


class ProviderNotFoundError(ComputeProviderError):
    """Raised when a requested provider is not registered."""


# =============================================================================
# Protocol
# =============================================================================


@runtime_checkable
class ComputeProvider(Protocol):
    """Provider-agnostic compute interface.

    All compute providers implement this protocol.

    This protocol uses ONLY generic identifiers:
    - instance_id (str) — never provider-specific IDs
    - requirements (ComputeRequirements) — generic workload spec
    - Return types are generic dataclasses defined above

    Validates: Requirements R13.1, R13.2, R13.3
    """

    @property
    def capabilities(self) -> ComputeProviderCapabilities:
        """Return this provider's declared capabilities."""
        ...

    async def provision(self, requirements: ComputeRequirements) -> InstanceHandle:
        """Provision a new compute instance matching requirements."""
        ...

    async def terminate(self, instance_id: str) -> None:
        """Terminate a compute instance and release resources."""
        ...

    async def health_check(self, instance_id: str) -> HealthStatus:
        """Check health of a running compute instance."""
        ...

    async def get_status(self, instance_id: str) -> InstanceStatus:
        """Get current status of a compute instance."""
        ...

    async def list_available(self) -> list[OfferInfo]:
        """List available compute offers from this provider."""
        ...

    async def estimate_cost(self, requirements: ComputeRequirements) -> CostEstimate:
        """Estimate cost for a workload before provisioning."""
        ...

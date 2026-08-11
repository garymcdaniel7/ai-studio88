"""Provider abstractions for external services (compute, storage, LLM, etc.).

Key exports:
- ComputeProvider: Protocol for compute backends
- ComputeProviderCapabilities: Capability discovery dataclass
- Registry functions: register_provider, get_provider, list_providers
"""

from backend.app.providers.compute import (
    ComputeMode,
    ComputeProvider,
    ComputeProviderCapabilities,
    ComputeProviderError,
    ComputeRequirements,
    CostEstimate,
    HealthState,
    HealthStatus,
    InstanceHandle,
    InstanceState,
    InstanceStatus,
    OfferInfo,
    ProviderNotFoundError,
    ProviderUnavailableError,
    ProvisionError,
    TerminateError,
)
from backend.app.providers.registry import (
    clear_registry,
    get_cheapest_provider,
    get_provider,
    get_registry_size,
    list_providers,
    register_provider,
    unregister_provider,
)

__all__ = [
    # Protocol
    "ComputeProvider",
    # Dataclasses
    "ComputeProviderCapabilities",
    "ComputeRequirements",
    "CostEstimate",
    "HealthStatus",
    "InstanceHandle",
    "InstanceStatus",
    "OfferInfo",
    # Enums
    "ComputeMode",
    "HealthState",
    "InstanceState",
    # Exceptions
    "ComputeProviderError",
    "ProviderNotFoundError",
    "ProviderUnavailableError",
    "ProvisionError",
    "TerminateError",
    # Registry
    "clear_registry",
    "get_cheapest_provider",
    "get_provider",
    "get_registry_size",
    "list_providers",
    "register_provider",
    "unregister_provider",
]

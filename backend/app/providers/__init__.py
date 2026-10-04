"""Provider abstractions for external services (compute, storage, LLM, etc.).

Key exports:
- ComputeProvider: Protocol for compute backends
- ComputeProviderCapabilities: Capability discovery dataclass
- Registry functions: register_provider, get_provider, list_providers
"""

from backend.app.providers.byo import (
    ProviderAdapter,
    ProviderError,
    ProviderErrorCode,
    ProviderEstimate,
    ProviderHealth,
    ProviderMetadata,
    ProviderRegistry,
    ProviderRequest,
    ProviderResult,
    TenantProviderSelection,
    WorkloadKind,
    build_default_registry,
)
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
from backend.app.providers.ollama_config import (
    DOLPHIN_LLAMA3_WARNING,
    OllamaConfiguration,
    configuration_from_settings,
    is_uncensored_model,
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
    # BYO provider ports and registry
    "ProviderAdapter",
    "ProviderError",
    "ProviderErrorCode",
    "ProviderEstimate",
    "ProviderHealth",
    "ProviderMetadata",
    "ProviderRequest",
    "ProviderResult",
    "ProviderRegistry",
    "TenantProviderSelection",
    "WorkloadKind",
    "build_default_registry",
    "DOLPHIN_LLAMA3_WARNING",
    "OllamaConfiguration",
    "configuration_from_settings",
    "is_uncensored_model",
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

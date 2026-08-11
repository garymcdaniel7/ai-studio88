"""Compute provider registry.

Manages registration, lookup, and selection of compute providers.
This module is the single entry point for resolving provider instances.

Validates: Requirements R13.1, R13.4
"""

from __future__ import annotations

import structlog

from backend.app.providers.compute import (
    ComputeProvider,
    ComputeProviderCapabilities,
    ComputeProviderError,
    ComputeRequirements,
    CostEstimate,
    ProviderNotFoundError,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Module-level registry (singleton within process)
# =============================================================================

_registry: dict[str, ComputeProvider] = {}


def register_provider(name: str, provider: ComputeProvider) -> None:
    """Register a compute provider by name.

    Args:
        name: Unique identifier for the provider (e.g., "runpod", "vastai").
        provider: A ComputeProvider implementation instance.

    Raises:
        ValueError: If name is empty or provider is None.
    """
    if not name:
        raise ValueError("Provider name must not be empty")
    if provider is None:
        raise ValueError("Provider instance must not be None")

    _registry[name] = provider
    logger.info(
        "compute_provider_registered",
        provider=name,
        display_name=provider.capabilities.display_name,
    )


def unregister_provider(name: str) -> None:
    """Remove a provider from the registry.

    Args:
        name: Provider name to remove.

    Raises:
        ProviderNotFoundError: If the provider is not registered.
    """
    if name not in _registry:
        raise ProviderNotFoundError(
            f"Provider '{name}' is not registered", provider=name
        )
    del _registry[name]
    logger.info("compute_provider_unregistered", provider=name)


def get_provider(name: str) -> ComputeProvider:
    """Get a registered provider by name.

    Args:
        name: Provider identifier.

    Returns:
        The registered ComputeProvider instance.

    Raises:
        ProviderNotFoundError: If no provider is registered with that name.
    """
    provider = _registry.get(name)
    if provider is None:
        available = list(_registry.keys())
        raise ProviderNotFoundError(
            f"Provider '{name}' not found. Available: {available}",
            provider=name,
        )
    return provider


def list_providers() -> list[ComputeProviderCapabilities]:
    """List capabilities of all registered providers.

    Returns:
        List of ComputeProviderCapabilities for each registered provider.
    """
    return [provider.capabilities for provider in _registry.values()]


async def get_cheapest_provider(
    gpu_type: str | None = None,
    min_vram_gb: int = 12,
    duration_seconds: int = 1800,
) -> str:
    """Select the cheapest provider for a given workload.

    Queries estimate_cost on all registered providers and returns
    the name of the one with the lowest estimated cost.

    Args:
        gpu_type: Preferred GPU type (optional filter).
        min_vram_gb: Minimum VRAM required.
        duration_seconds: Expected job duration in seconds.

    Returns:
        Name of the cheapest registered provider.

    Raises:
        ProviderNotFoundError: If no providers are registered.
        ComputeProviderError: If no provider can serve the request.
    """
    if not _registry:
        raise ProviderNotFoundError(
            "No compute providers registered", provider=None
        )

    requirements = ComputeRequirements(
        vram_gb=min_vram_gb,
        max_duration_seconds=duration_seconds,
    )

    estimates: list[tuple[str, CostEstimate]] = []
    for name, provider in _registry.items():
        # Filter by VRAM capability
        caps = provider.capabilities
        if caps.max_vram_gb < min_vram_gb:
            continue
        if gpu_type and gpu_type not in caps.gpu_types and caps.gpu_types:
            continue

        try:
            estimate = await provider.estimate_cost(requirements)
            estimates.append((name, estimate))
        except Exception as exc:
            logger.warning(
                "compute_cost_estimate_failed",
                provider=name,
                error=str(exc),
            )
            continue

    if not estimates:
        raise ComputeProviderError(
            f"No provider can serve request (vram={min_vram_gb}GB, gpu={gpu_type})"
        )

    # Sort by estimated cost, return cheapest
    estimates.sort(key=lambda x: x[1].estimated_usd)
    return estimates[0][0]


def clear_registry() -> None:
    """Clear all registered providers. Used for testing only."""
    _registry.clear()


def get_registry_size() -> int:
    """Return the number of registered providers."""
    return len(_registry)

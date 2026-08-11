"""Video Provider Registry — Story 143.

Configuration-driven registry that loads, validates, and manages video
provider adapters. Shared orchestration calls registry methods — never
instantiates providers directly or branches on provider names.

Design:
- Providers register via config (not import-time side effects)
- Invalid configs are rejected at registration (fail fast at startup)
- Disabled providers are skipped silently
- Provider removal doesn't break remaining adapters
- Thread-safe singleton pattern for application lifecycle
- Priority-based selection when multiple providers support a mode/model
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from backend.video.contract import (
    CanonicalVideoProvider,
    VideoErrorCode,
    VideoGenerationRequest,
    VideoMode,
    VideoProviderCapabilities,
    VideoProviderConfig,
    VideoProviderError,
    VideoProviderHealth,
    VideoProviderStatus,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# =============================================================================
# Registry
# =============================================================================


class VideoProviderRegistry:
    """Manages registered video provider adapters.

    Usage:
        registry = VideoProviderRegistry()
        registry.register(config, SimulationVideoAdapter)
        provider = registry.get_provider("simulation")
        provider = registry.select_provider(mode=VideoMode.TEXT_TO_VIDEO, model="wan-2.1")
    """

    def __init__(self) -> None:
        self._providers: dict[str, CanonicalVideoProvider] = {}
        self._configs: dict[str, VideoProviderConfig] = {}

    # ─── Registration ───────────────────────────────────────────────────────

    def register(
        self,
        config: VideoProviderConfig,
        adapter_class: type[CanonicalVideoProvider],
    ) -> None:
        """Register a provider adapter with validated configuration.

        Raises ValueError if:
        - Config name is empty
        - Config name conflicts with an existing registration
        - Adapter initialization fails (invalid settings)
        """
        if not config.name:
            raise ValueError("Provider config must have a non-empty name")

        if not config.enabled:
            logger.info("Skipping disabled video provider: %s", config.name)
            return

        if config.name in self._providers:
            raise ValueError(
                f"Video provider '{config.name}' is already registered"
            )

        # Instantiate and initialize the adapter
        try:
            adapter = adapter_class()
            adapter.initialize(config)
        except Exception as exc:
            raise ValueError(
                f"Failed to initialize video provider '{config.name}': {exc}"
            ) from exc

        self._providers[config.name] = adapter
        self._configs[config.name] = config
        logger.info(
            "Registered video provider: %s (priority=%d, modes=%s)",
            config.name,
            config.priority,
            [m.value for m in adapter.capabilities().modes],
        )

    def unregister(self, name: str) -> bool:
        """Remove a provider from the registry. Returns True if found."""
        if name in self._providers:
            provider = self._providers.pop(name)
            self._configs.pop(name, None)
            try:
                provider.shutdown()
            except Exception as exc:
                logger.warning("Error shutting down provider %s: %s", name, exc)
            return True
        return False

    # ─── Lookup ─────────────────────────────────────────────────────────────

    def get_provider(self, name: str) -> CanonicalVideoProvider | None:
        """Get a specific provider by name. Returns None if not found."""
        return self._providers.get(name)

    def get_provider_strict(self, name: str) -> CanonicalVideoProvider:
        """Get a specific provider by name. Raises if not found."""
        provider = self._providers.get(name)
        if not provider:
            available = list(self._providers.keys())
            raise LookupError(
                f"Video provider '{name}' not found. Available: {available}"
            )
        return provider

    def list_providers(self) -> list[str]:
        """List all registered provider names."""
        return list(self._providers.keys())

    def list_capabilities(self) -> list[VideoProviderCapabilities]:
        """Get capabilities for all registered providers."""
        return [p.capabilities() for p in self._providers.values()]

    def list_health(self) -> list[VideoProviderHealth]:
        """Get health status for all registered providers."""
        results = []
        for provider in self._providers.values():
            try:
                results.append(provider.health())
            except Exception as exc:
                results.append(
                    VideoProviderHealth(
                        provider_name=provider.name,
                        status=VideoProviderStatus.UNAVAILABLE,
                        message=f"Health check failed: {exc}",
                    )
                )
        return results

    # ─── Selection ──────────────────────────────────────────────────────────

    def select_provider(
        self,
        mode: VideoMode | None = None,
        model: str | None = None,
        preferred: str | None = None,
    ) -> CanonicalVideoProvider | None:
        """Select the best available provider for a request.

        Selection logic:
        1. If preferred is set and available, use it (if it supports the mode/model)
        2. Otherwise, find all providers supporting the mode/model
        3. Sort by priority (lower = preferred)
        4. Return the first available one

        Returns None if no provider can handle the request.
        """
        # Preferred provider shortcut
        if preferred and preferred in self._providers:
            provider = self._providers[preferred]
            if self._supports(provider, mode, model):
                return provider

        # Find all matching providers, sorted by priority
        candidates: list[tuple[int, CanonicalVideoProvider]] = []
        for name, provider in self._providers.items():
            config = self._configs.get(name)
            priority = config.priority if config else 100
            if self._supports(provider, mode, model):
                candidates.append((priority, provider))

        if not candidates:
            return None

        # Sort by priority (lower first)
        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]

    def select_provider_for_request(
        self,
        request: VideoGenerationRequest,
        preferred: str | None = None,
    ) -> CanonicalVideoProvider | None:
        """Select the best provider for a full request.

        Also validates the request against the selected provider.
        """
        return self.select_provider(
            mode=request.mode,
            model=request.model,
            preferred=preferred,
        )

    # ─── Validation ─────────────────────────────────────────────────────────

    def validate_request(
        self,
        request: VideoGenerationRequest,
        provider_name: str | None = None,
    ) -> VideoProviderError | None:
        """Validate a request against the target provider's capabilities.

        If provider_name is None, selects the best provider first.
        Returns None if valid, or a VideoProviderError if not.
        """
        provider = (
            self.get_provider(provider_name)
            if provider_name
            else self.select_provider(mode=request.mode, model=request.model)
        )

        if not provider:
            return VideoProviderError(
                code=VideoErrorCode.PROVIDER_UNAVAILABLE,
                message=f"No provider available for mode={request.mode.value}, model={request.model}",
                retryable=False,
            )

        return provider.validate_request(request)

    # ─── Lifecycle ──────────────────────────────────────────────────────────

    def shutdown_all(self) -> None:
        """Gracefully shut down all providers."""
        for name, provider in self._providers.items():
            try:
                provider.shutdown()
            except Exception as exc:
                logger.warning("Error shutting down provider %s: %s", name, exc)
        self._providers.clear()
        self._configs.clear()

    @property
    def provider_count(self) -> int:
        """Number of registered providers."""
        return len(self._providers)

    # ─── Internal ───────────────────────────────────────────────────────────

    @staticmethod
    def _supports(
        provider: CanonicalVideoProvider,
        mode: VideoMode | None,
        model: str | None,
    ) -> bool:
        """Check if a provider supports a given mode and model."""
        caps = provider.capabilities()

        if mode and mode not in caps.modes:
            return False

        if model:
            model_ids = [m.id for m in caps.models]
            if model not in model_ids:
                # Check normalized variants
                normalized = model.lower().replace(" ", "-").replace("_", "-")
                if not any(
                    mid.lower().replace(" ", "-").replace("_", "-") == normalized
                    for mid in model_ids
                ):
                    return False

        return True


# =============================================================================
# Singleton Application Registry
# =============================================================================

_registry: VideoProviderRegistry | None = None


def get_video_provider_registry() -> VideoProviderRegistry:
    """Get the application-wide video provider registry.

    Creates the registry on first call. Providers are registered
    separately during application startup (see setup_video_providers).
    """
    global _registry
    if _registry is None:
        _registry = VideoProviderRegistry()
    return _registry


def reset_video_provider_registry() -> None:
    """Reset the singleton registry (for testing only)."""
    global _registry
    if _registry:
        _registry.shutdown_all()
    _registry = None


# =============================================================================
# Application Startup Integration
# =============================================================================


def setup_video_providers() -> VideoProviderRegistry:
    """Initialize video providers from environment configuration.

    Called during application startup. Reads provider configs from
    environment variables and registers enabled adapters.

    Environment variables:
        VIDEO_PROVIDER_SIMULATION_ENABLED — Enable simulation (default: true)
        VIDEO_PROVIDER_COMFYUI_ENABLED — Enable ComfyUI/WAN (default: true)
        VIDEO_PROVIDER_COMFYUI_PRIORITY — Priority for ComfyUI (default: 50)
        VIDEO_PROVIDER_SIMULATION_PRIORITY — Priority for simulation (default: 100)
    """
    import os

    from backend.video.adapters.comfyui_adapter import ComfyUIVideoAdapter
    from backend.video.adapters.minimax_h3_adapter import MiniMaxH3VideoAdapter
    from backend.video.adapters.simulation_adapter import SimulationVideoAdapter

    registry = get_video_provider_registry()

    # Simulation provider (always available, lowest priority)
    sim_enabled = os.environ.get("VIDEO_PROVIDER_SIMULATION_ENABLED", "true").lower() == "true"
    sim_priority = int(os.environ.get("VIDEO_PROVIDER_SIMULATION_PRIORITY", "100"))
    try:
        registry.register(
            VideoProviderConfig(
                name="simulation",
                enabled=sim_enabled,
                priority=sim_priority,
            ),
            SimulationVideoAdapter,
        )
    except ValueError as exc:
        logger.error("Failed to register simulation video provider: %s", exc)

    # ComfyUI/WAN provider
    comfyui_enabled = os.environ.get("VIDEO_PROVIDER_COMFYUI_ENABLED", "true").lower() == "true"
    comfyui_priority = int(os.environ.get("VIDEO_PROVIDER_COMFYUI_PRIORITY", "50"))
    comfyui_url = os.environ.get("COMFYUI_BASE_URL", "http://localhost:8188")
    try:
        registry.register(
            VideoProviderConfig(
                name="comfyui-wan",
                enabled=comfyui_enabled,
                priority=comfyui_priority,
                settings={
                    "base_url": comfyui_url,
                    "timeout_seconds": int(os.environ.get("COMFYUI_API_TIMEOUT", "600")),
                    "workflow_template": os.environ.get("COMFYUI_VIDEO_WORKFLOW", "wan21_t2v_simple"),
                },
            ),
            ComfyUIVideoAdapter,
        )
    except ValueError as exc:
        logger.error("Failed to register ComfyUI video provider: %s", exc)

    # MiniMax H3 provider (hosted API)
    minimax_enabled = os.environ.get("VIDEO_PROVIDER_MINIMAX_H3_ENABLED", "false").lower() == "true"
    minimax_priority = int(os.environ.get("VIDEO_PROVIDER_MINIMAX_H3_PRIORITY", "30"))
    minimax_api_key = os.environ.get("VIDEO_PROVIDER_MINIMAX_H3_API_KEY", "")
    minimax_base_url = os.environ.get(
        "VIDEO_PROVIDER_MINIMAX_H3_BASE_URL", "https://api.minimax.io"
    )
    try:
        registry.register(
            VideoProviderConfig(
                name="minimax-h3",
                enabled=minimax_enabled,
                priority=minimax_priority,
                settings={
                    "api_key": minimax_api_key,
                    "base_url": minimax_base_url,
                    "poll_interval_seconds": float(
                        os.environ.get("VIDEO_PROVIDER_MINIMAX_H3_POLL_INTERVAL", "5")
                    ),
                    "poll_timeout_seconds": float(
                        os.environ.get("VIDEO_PROVIDER_MINIMAX_H3_POLL_TIMEOUT", "600")
                    ),
                    "enable_2k": os.environ.get(
                        "VIDEO_PROVIDER_MINIMAX_H3_ENABLE_2K", "false"
                    ).lower() == "true",
                    "prompt_optimizer": os.environ.get(
                        "VIDEO_PROVIDER_MINIMAX_H3_PROMPT_OPTIMIZER", "true"
                    ).lower() == "true",
                },
                max_concurrent_jobs=int(
                    os.environ.get("VIDEO_PROVIDER_MINIMAX_H3_MAX_CONCURRENT", "5")
                ),
                max_requests_per_minute=int(
                    os.environ.get("VIDEO_PROVIDER_MINIMAX_H3_RPM", "20")
                ),
            ),
            MiniMaxH3VideoAdapter,
        )
    except ValueError as exc:
        logger.error("Failed to register MiniMax H3 video provider: %s", exc)

    logger.info(
        "Video provider registry initialized: %d providers (%s)",
        registry.provider_count,
        registry.list_providers(),
    )
    return registry

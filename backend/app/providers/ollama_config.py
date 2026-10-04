"""Safe Ollama configuration and status contracts.

Ollama is intentionally credential-free. This module separates backend-only
endpoint configuration from the client-safe status metadata used by Settings,
Brain health, and provider discovery surfaces.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.core.config import Settings

DOLPHIN_LLAMA3_WARNING = (
    "dolphin-llama3 is an uncensored model. Enable it only after reviewing "
    "your workspace safety, moderation, and content policies."
)
_UNCENSORED_MODEL_PREFIX = "dolphin-llama3"


def is_uncensored_model(model: str) -> bool:
    """Return whether a model identifier is the explicitly opt-in dolphin model."""
    return model.strip().lower().split(":", 1)[0] == _UNCENSORED_MODEL_PREFIX


@dataclass(frozen=True)
class OllamaConfiguration:
    """Backend Ollama settings with a safe client-facing status projection."""

    enabled: bool
    base_url: str
    mode: str
    privacy_mode: str
    model: str
    health_timeout_seconds: float
    timeout_seconds: float
    max_tokens: int
    max_latency_ms: int
    uncensored_opt_in: bool
    safety_mode: str

    @property
    def uncensored(self) -> bool:
        """Return whether the configured model is uncensored."""
        return is_uncensored_model(self.model)

    @property
    def warning(self) -> str | None:
        """Return the safety warning only for an active uncensored selection."""
        return DOLPHIN_LLAMA3_WARNING if self.uncensored else None

    def safe_status(
        self,
        *,
        healthy: bool | None = None,
        health_status: str | None = None,
        fallback_mode: str = "auto",
    ) -> dict[str, Any]:
        """Return status metadata without endpoint URLs, credentials, or payloads."""
        return {
            "provider": "ollama",
            "enabled": self.enabled,
            "healthy": healthy,
            "status": health_status or ("configured" if self.enabled else "disabled"),
            "configured": bool(self.base_url),
            "mode": self.mode,
            "privacy_mode": self.privacy_mode,
            "model": self.model,
            "credential_required": False,
            "cost_tier": "free",
            "estimated_cost_usd": 0.0,
            "health_timeout_seconds": self.health_timeout_seconds,
            "timeout_seconds": self.timeout_seconds,
            "max_tokens": self.max_tokens,
            "max_latency_ms": self.max_latency_ms,
            "uncensored": self.uncensored,
            "uncensored_opt_in": self.uncensored_opt_in,
            "safety_mode": self.safety_mode,
            "warning": self.warning,
            "fallback_mode": fallback_mode,
            "endpoint_exposed": False,
        }


def configuration_from_settings(settings: Settings) -> OllamaConfiguration:
    """Build the backend-only Ollama configuration from validated Settings."""
    return OllamaConfiguration(
        enabled=settings.ollama_enabled,
        base_url=settings.ollama_base_url.rstrip("/"),
        mode=settings.ollama_mode,
        privacy_mode=settings.ollama_privacy_mode,
        model=settings.ollama_model,
        health_timeout_seconds=settings.ollama_health_timeout_seconds,
        timeout_seconds=settings.ollama_timeout_seconds,
        max_tokens=settings.ollama_max_tokens,
        max_latency_ms=settings.ollama_max_latency_ms,
        uncensored_opt_in=settings.ollama_uncensored_opt_in,
        safety_mode=settings.ollama_safety_mode,
    )


__all__ = [
    "DOLPHIN_LLAMA3_WARNING",
    "OllamaConfiguration",
    "configuration_from_settings",
    "is_uncensored_model",
]

"""Capability registry and tenant policy for BYO providers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.config import Settings, get_settings
from app.providers.byo_adapters import (
    ElevenLabsAdapter,
    GeminiAdapter,
    HTTPProviderAdapter,
    OllamaLocalAdapter,
)
from app.providers.byo_contracts import (
    ProviderAdapter,
    ProviderError,
    ProviderErrorCode,
    ProviderEstimate,
    ProviderHealth,
    ProviderMetadata,
    ProviderRequest,
    ProviderResponse,
    ProviderResult,
    RequestTransport,
    WorkloadKind,
)
from app.providers.ollama_config import configuration_from_settings
from backend.credentials import ProviderType

__all__ = [
    "ElevenLabsAdapter",
    "GeminiAdapter",
    "HTTPProviderAdapter",
    "OllamaLocalAdapter",
    "ProviderAdapter",
    "ProviderError",
    "ProviderErrorCode",
    "ProviderEstimate",
    "ProviderHealth",
    "ProviderMetadata",
    "ProviderRequest",
    "ProviderResponse",
    "ProviderResult",
    "ProviderRegistry",
    "RequestTransport",
    "TenantProviderSelection",
    "WorkloadKind",
    "build_default_registry",
]


@dataclass(frozen=True)
class TenantProviderSelection:
    """Explicit tenant-owned default and fallback policy."""

    default_provider: str
    fallback_chain: tuple[str, ...] = ()
    fallback_mode: str = "auto"
    allow_platform_fallback: bool = False
    allow_organization_pool: bool = True
    denied_providers: tuple[str, ...] = ()

    def candidates(self, requested_provider: str | None = None) -> tuple[str, ...]:
        """Return deterministic candidates with duplicates removed."""
        values = ((requested_provider,) if requested_provider else ()) + (
            self.default_provider,
            *self.fallback_chain,
        )
        return tuple(dict.fromkeys(value.lower() for value in values if value))


class ProviderRegistry:
    """Capability-aware registry with tenant-scoped provider selection."""

    def __init__(
        self,
        adapters: list[ProviderAdapter] | None = None,
        *,
        defaults: dict[WorkloadKind, TenantProviderSelection] | None = None,
    ) -> None:
        self._adapters = {adapter.metadata.name: adapter for adapter in adapters or []}
        self._defaults = defaults or {}
        self._selections: dict[tuple[str, WorkloadKind], TenantProviderSelection] = {}

    def register(self, adapter: ProviderAdapter) -> None:
        """Register or replace an adapter by its stable provider name."""
        self._adapters[adapter.metadata.name] = adapter

    def get(self, provider: str) -> ProviderAdapter:
        """Return an adapter or raise a safe unsupported-provider error."""
        try:
            return self._adapters[provider.lower()]
        except KeyError as exc:
            raise ProviderError(
                "Requested provider is unsupported",
                ProviderErrorCode.UNSUPPORTED_CAPABILITY,
                provider.lower(),
                status_code=422,
            ) from exc

    def list_metadata(self) -> list[dict[str, Any]]:
        """List safe capability metadata for all registered providers."""
        return [self._adapters[name].metadata.as_dict() for name in sorted(self._adapters)]

    def set_selection(
        self,
        org_id: str,
        workload: WorkloadKind,
        selection: TenantProviderSelection,
    ) -> None:
        """Set a selection for a trusted tenant context."""
        if not org_id:
            raise ValueError("org_id is required")
        if any(provider not in self._adapters for provider in selection.candidates()):
            raise ValueError("Provider selection contains an unknown provider")
        self._selections[(org_id, workload)] = selection

    def selection(self, org_id: str, workload: WorkloadKind) -> TenantProviderSelection:
        """Return explicit tenant selection or the configured safe default."""
        configured = self._selections.get((org_id, workload))
        if configured:
            return configured
        configured_default = self._defaults.get(workload)
        if configured_default:
            return configured_default
        defaults = {
            WorkloadKind.LLM: ("ollama", ("openai", "gemini")),
            WorkloadKind.GPU: ("thunder_compute", ("runcomfy",)),
            WorkloadKind.VOICE: ("elevenlabs", ()),
            WorkloadKind.MODEL: ("replicate", ()),
        }
        default, fallback = defaults[workload]
        if default not in self._adapters:
            default = fallback[0] if fallback else default
        return TenantProviderSelection(default_provider=default, fallback_chain=fallback)

    def candidates(
        self,
        org_id: str,
        workload: WorkloadKind,
        requested_provider: str | None = None,
    ) -> tuple[ProviderAdapter, ...]:
        """Resolve tenant policy into ordered adapters."""
        selection = self.selection(org_id, workload)
        return tuple(self.get(name) for name in selection.candidates(requested_provider))


def _metadata(settings: Settings) -> list[ProviderMetadata]:
    """Build requested provider metadata from Settings only."""
    timeout = settings.provider_timeout_seconds
    health_timeout = settings.provider_health_timeout_seconds
    retries = settings.provider_retry_attempts
    ollama = configuration_from_settings(settings)
    return [
        ProviderMetadata(
            "thunder_compute", "Thunder Compute", WorkloadKind.GPU,
            ProviderType.THUNDER_COMPUTE, ("image", "video", "training", "batch"),
            base_url=settings.thunder_compute_base_url, health_path="/v1/auth/validate",
            execute_path="/v1/generate", timeout_seconds=timeout,
            health_timeout_seconds=health_timeout, max_retries=5,
            rate_limit_per_minute=60, cost_unit="hour", cost_rate_usd=0.35,
            supports_batch=True,
        ),
        ProviderMetadata(
            "runcomfy", "RunComfy", WorkloadKind.GPU, ProviderType.RUNCOMFY,
            ("image", "video", "training", "webhook", "batch"),
            base_url=settings.runcomfy_base_url, health_path="/health",
            execute_path="/api/prompt", timeout_seconds=timeout,
            health_timeout_seconds=health_timeout, max_retries=3,
            rate_limit_per_minute=120, cost_unit="hour", cost_rate_usd=2.50,
            supports_batch=True, supports_webhooks=True,
        ),
        ProviderMetadata(
            "gemini", "Gemini", WorkloadKind.LLM, ProviderType.GEMINI,
            ("text", "vision", "structured_output"),
            models=("gemini-2.5-flash", "gemini-2.5-pro"), base_url=settings.gemini_base_url,
            health_path="/v1beta/models", execute_path="/v1beta/models/generateContent",
            timeout_seconds=timeout, health_timeout_seconds=health_timeout, max_retries=retries,
            rate_limit_per_minute=60, cost_unit="million_tokens", cost_rate_usd=0.30,
        ),
        ProviderMetadata(
            "openai", "OpenAI", WorkloadKind.LLM, ProviderType.OPENAI,
            ("text", "vision", "tools", "structured_output"),
            models=("gpt-4o", "gpt-4o-mini", "gpt-4-turbo"), base_url=settings.openai_base_url,
            health_path="/models", execute_path="/chat/completions", timeout_seconds=timeout,
            health_timeout_seconds=health_timeout, max_retries=retries,
            rate_limit_per_minute=500, cost_unit="million_tokens", cost_rate_usd=2.50,
        ),
        ProviderMetadata(
            "elevenlabs", "ElevenLabs", WorkloadKind.VOICE, ProviderType.ELEVENLABS,
            ("tts", "voice_clone", "multilingual"),
            models=("eleven_turbo_v2", "eleven_multilingual_v2"),
            base_url=settings.elevenlabs_base_url, health_path="/user",
            execute_path="/text-to-speech/eleven_turbo_v2", timeout_seconds=timeout,
            health_timeout_seconds=health_timeout, max_retries=retries,
            rate_limit_per_minute=60, cost_unit="million_characters", cost_rate_usd=0.30,
        ),
        ProviderMetadata(
            "replicate", "Replicate", WorkloadKind.MODEL, ProviderType.REPLICATE,
            ("image", "video", "audio", "model_version"), base_url=settings.replicate_base_url,
            health_path="/v1/models", execute_path="/v1/predictions", timeout_seconds=timeout,
            health_timeout_seconds=health_timeout, max_retries=3,
            rate_limit_per_minute=60, cost_unit="request", cost_rate_usd=0.01,
        ),
        ProviderMetadata(
            "ollama", "Ollama (local-first)", WorkloadKind.LLM, ProviderType.OLLAMA,
            ("text", "local", "free"), models=(ollama.model,),
            base_url=ollama.base_url, health_path="/api/tags",
            execute_path="/api/generate", timeout_seconds=ollama.timeout_seconds,
            health_timeout_seconds=ollama.health_timeout_seconds, max_retries=0,
            max_tokens=ollama.max_tokens, max_latency_ms=ollama.max_latency_ms,
            cost_unit="request", cost_rate_usd=0.0, local=True,
            enabled=ollama.enabled, privacy_mode=ollama.privacy_mode,
            uncensored=ollama.uncensored, warning=ollama.warning,
            credential_required=False,
        ),
    ]


def build_default_registry(
    settings: Settings | None = None,
    *,
    transport: RequestTransport | None = None,
) -> ProviderRegistry:
    """Build the BYO registry from Settings with injectable transport."""
    active_settings = settings or get_settings()
    adapters: list[ProviderAdapter] = []
    for metadata in _metadata(active_settings):
        adapter_class: type[HTTPProviderAdapter] = HTTPProviderAdapter
        if metadata.name == "gemini":
            adapter_class = GeminiAdapter
        elif metadata.name == "elevenlabs":
            adapter_class = ElevenLabsAdapter
        elif metadata.name == "ollama":
            adapter_class = OllamaLocalAdapter
        adapters.append(adapter_class(metadata, transport=transport))

    llm_default = "ollama" if active_settings.ollama_enabled else "openai"
    defaults = {
        WorkloadKind.LLM: TenantProviderSelection(
            default_provider=llm_default,
            fallback_chain=("openai", "gemini"),
            fallback_mode=active_settings.llm_fallback_mode,
            allow_platform_fallback=active_settings.byo_allow_platform_fallback,
            allow_organization_pool=active_settings.byo_allow_organization_pool,
        )
    }
    return ProviderRegistry(adapters, defaults=defaults)

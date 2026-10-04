"""Provider-neutral ports and safe BYO value objects."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from backend.credentials import ProviderType


class WorkloadKind(StrEnum):
    """Workload classes supported by the BYO provider router."""

    GPU = "gpu"
    LLM = "llm"
    VOICE = "voice"
    MODEL = "model"


class ProviderErrorCode(StrEnum):
    """Stable provider failure classes used by retry and HTTP mapping."""

    AUTH_FAILED = "provider_auth_failed"
    CREDENTIAL_REQUIRED = "credential_required"
    CREDENTIAL_EXPIRED = "credential_expired"
    RATE_LIMITED = "provider_rate_limited"
    TIMEOUT = "provider_timeout"
    PROVIDER_DOWN = "provider_down"
    OUT_OF_MEMORY = "provider_oom"
    WEBHOOK_MISSED = "provider_webhook_missed"
    CONTENT_FAILURE = "content_failure"
    WORKFLOW_FAILURE = "workflow_failure"
    UNSUPPORTED_CAPABILITY = "unsupported_capability"


@dataclass(frozen=True)
class ProviderMetadata:
    """Safe provider capability, health, cost, and credential metadata."""

    name: str
    display_name: str
    workload: WorkloadKind
    credential_provider: ProviderType | None
    capabilities: tuple[str, ...]
    models: tuple[str, ...] = ()
    base_url: str = ""
    health_path: str = "/health"
    execute_path: str = "/generate"
    timeout_seconds: float = 60.0
    health_timeout_seconds: float = 5.0
    max_retries: int = 2
    max_tokens: int | None = None
    max_latency_ms: int | None = None
    rate_limit_per_minute: int | None = None
    cost_unit: str = "request"
    cost_rate_usd: float = 0.0
    supports_batch: bool = False
    supports_webhooks: bool = False
    local: bool = False
    enabled: bool = True
    privacy_mode: str = "cloud"
    uncensored: bool = False
    warning: str | None = None
    credential_required: bool = True

    def as_dict(self) -> dict[str, Any]:
        """Return client-safe metadata without credentials or secrets."""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "workload": self.workload.value,
            "credential_provider": (
                self.credential_provider.value if self.credential_provider else None
            ),
            "capabilities": list(self.capabilities),
            "models": list(self.models),
            # Never return the configured endpoint; it is backend topology.
            "endpoint_configured": bool(self.base_url),
            "timeout_seconds": self.timeout_seconds,
            "health_timeout_seconds": self.health_timeout_seconds,
            "max_tokens": self.max_tokens,
            "max_latency_ms": self.max_latency_ms,
            "max_retries": self.max_retries,
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "cost_unit": self.cost_unit,
            "supports_batch": self.supports_batch,
            "supports_webhooks": self.supports_webhooks,
            "local": self.local,
            "enabled": self.enabled,
            "privacy_mode": self.privacy_mode,
            "uncensored": self.uncensored,
            "warning": self.warning,
            "credential_required": self.credential_required,
        }


@dataclass(frozen=True)
class ProviderHealth:
    """Provider health result with a safe diagnostic reason."""

    provider: str
    healthy: bool
    status: str
    latency_ms: float | None = None
    reason: str = ""


@dataclass(frozen=True)
class ProviderEstimate:
    """Preflight cost estimate required before paid dispatch."""

    provider: str
    estimated_cost_usd: float
    duration_seconds: int
    confidence: float
    currency: str = "USD"


@dataclass(frozen=True)
class ProviderRequest:
    """Provider-neutral dispatch request."""

    workload: WorkloadKind
    model: str
    payload: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: float | None = None
    job_id: str | None = None
    workflow_id: str | None = None
    workflow_version: str | None = None


@dataclass(frozen=True)
class ProviderResult:
    """Provider-neutral execution result."""

    provider: str
    model: str
    output: Any
    actual_cost_usd: float | None = None
    provider_job_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderResponse:
    """Minimal injectable HTTP response used by contract tests."""

    status_code: int
    body: dict[str, Any] = field(default_factory=dict)


class ProviderError(Exception):
    """Safe, classified provider error; message must never contain a secret."""

    def __init__(
        self,
        message: str,
        code: ProviderErrorCode,
        provider: str,
        *,
        retryable: bool = False,
        status_code: int = 503,
    ) -> None:
        self.code = code
        self.provider = provider
        self.retryable = retryable
        self.status_code = status_code
        super().__init__(message)


class ProviderAdapter(Protocol):
    """Provider-neutral adapter port."""

    @property
    def metadata(self) -> ProviderMetadata: ...

    async def health(self, credential: str | None = None) -> ProviderHealth: ...

    async def estimate_cost(self, request: ProviderRequest) -> ProviderEstimate: ...

    async def execute(
        self, request: ProviderRequest, credential: str | None = None
    ) -> ProviderResult: ...

    async def cleanup(self, request: ProviderRequest) -> None: ...


RequestTransport = Callable[
    [str, str, dict[str, str], dict[str, Any], dict[str, str], float],
    Awaitable[ProviderResponse],
]

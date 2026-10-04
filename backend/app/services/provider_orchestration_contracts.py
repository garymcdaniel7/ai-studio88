"""Secret-free provider orchestration result and error contracts."""

from __future__ import annotations

import threading
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.providers.byo import ProviderResult, WorkloadKind


class ProviderOrchestrationError(Exception):
    """Structured, secret-free orchestration failure."""

    def __init__(
        self,
        message: str,
        code: str,
        *,
        provider: str | None = None,
        status_code: int = 503,
        retryable: bool = False,
    ) -> None:
        self.message = message
        self.code = code
        self.provider = provider
        self.status_code = status_code
        self.retryable = retryable
        super().__init__(message)

    def as_dict(self) -> dict[str, Any]:
        """Return a client-safe structured error."""
        return {"detail": self.message, "code": self.code, "provider": self.provider}


@dataclass(frozen=True)
class ProviderDispatchResult:
    """Safe dispatch response with immutable provenance."""

    result: ProviderResult
    provider: str
    estimate_usd: float
    reservation_id: str | None
    attempts: int
    fallback_chain: tuple[str, ...]
    provenance: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """Serialize without provider credentials or request payloads."""
        return {
            "provider": self.provider,
            "model": self.result.model,
            "output": self.result.output,
            "actual_cost_usd": self.result.actual_cost_usd,
            "provider_job_id": self.result.provider_job_id,
            "estimate_usd": self.estimate_usd,
            "reservation_id": self.reservation_id,
            "attempts": self.attempts,
            "fallback_chain": list(self.fallback_chain),
            "provenance": dict(self.provenance),
        }


PrivacyChecker = Callable[[str, WorkloadKind], bool | Awaitable[bool]]
RESULT_LOCK = threading.Lock()
IDEMPOTENT_RESULTS: dict[tuple[str, str], ProviderDispatchResult] = {}

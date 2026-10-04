"""Shared cost, credential, privacy, and error helpers for BYO routing."""

from __future__ import annotations

import inspect
from typing import Any

from app.providers.byo import (
    ProviderAdapter,
    ProviderError,
    ProviderErrorCode,
    ProviderRequest,
    WorkloadKind,
)
from app.services.provider_orchestration_contracts import ProviderOrchestrationError


class ProviderOrchestrationSupport:
    """Mixin containing non-routing provider orchestration helpers."""

    async def _is_allowed(self, provider: str, workload: WorkloadKind) -> bool:
        """Apply optional workspace privacy policy before credential access."""
        if self._privacy_checker is None:
            return True
        result = self._privacy_checker(provider, workload)
        return bool(await result) if inspect.isawaitable(result) else bool(result)

    def _resolve_credential(self, adapter: ProviderAdapter, *, actor: str) -> Any:
        """Resolve customer → organization pool → platform credential safely."""
        if not adapter.metadata.credential_required:
            return None
        selection = self.registry.selection(self.org_id, adapter.metadata.workload)
        material = self._credentials.resolve_material(
            org_id=self.org_id,
            provider=adapter.metadata.credential_provider,
            actor=actor,
            purpose=f"provider_dispatch:{adapter.metadata.name}",
            allow_platform_fallback=selection.allow_platform_fallback,
            allow_org_pool=selection.allow_organization_pool,
        )
        if material is not None:
            return material
        statuses = self._credentials.get_status(
            org_id=self.org_id,
            provider=adapter.metadata.credential_provider,
        )
        if any(row.get("status") == "expired" for row in statuses):
            raise ProviderOrchestrationError(
                "Provider credential has expired",
                "CREDENTIAL_EXPIRED",
                provider=adapter.metadata.name,
                status_code=401,
            )
        raise ProviderOrchestrationError(
            "Provider credential is required",
            "CREDENTIAL_REQUIRED",
            provider=adapter.metadata.name,
            status_code=401,
        )

    @staticmethod
    async def _estimate(adapter: ProviderAdapter, request: ProviderRequest) -> Any:
        """Run the provider cost preflight before any dispatch."""
        try:
            estimate = await adapter.estimate_cost(request)
        except ProviderError as exc:
            raise ProviderOrchestrationSupport._map_provider_error(exc) from exc
        if estimate.estimated_cost_usd < 0:
            raise ProviderOrchestrationError(
                "Provider returned an invalid cost estimate",
                "COST_ESTIMATE_UNAVAILABLE",
                provider=adapter.metadata.name,
                status_code=503,
            )
        return estimate

    def _reserve(self, amount: float, provider: str, job_id: str | None) -> Any:
        """Reserve paid work before adapter health or execution calls."""
        if amount <= 0:
            return None
        try:
            return self._cost.reserve_cost(
                self.org_id,
                amount,
                operation="provider_dispatch",
                job_id=job_id,
                provider=provider,
            )
        except (self._cost.BudgetExceededError, self._cost.LedgerUnavailableError) as exc:
            raise ProviderOrchestrationError(
                "Provider dispatch rejected by the cost gate",
                "COST_GATE_REJECTED",
                provider=provider,
                status_code=402,
            ) from exc

    def _finalize(self, reservation: Any, amount: float) -> None:
        """Finalize a reservation with provider-reported or estimated cost."""
        if reservation is not None:
            self._cost.finalize_cost(reservation.reservation_id, max(amount, 0.0))

    def _release(self, reservation: Any) -> None:
        """Release held budget on failure or cancellation."""
        self._cost.release_reservation(reservation.reservation_id, reason="provider_failure")

    @staticmethod
    def _provenance(
        adapter: ProviderAdapter,
        request: ProviderRequest,
        material: Any,
        *,
        attempt: int,
        reservation: Any,
    ) -> dict[str, Any]:
        """Build immutable, secret-free execution provenance."""
        credential_provenance = material.provenance() if material else {
            "credential_id": "local",
            "source": "local",
        }
        return {
            "provider": adapter.metadata.name,
            "provider_version": "byo-v1",
            "model": request.model,
            "workflow_id": request.workflow_id,
            "workflow_version": request.workflow_version,
            "job_id": request.job_id,
            "credential": credential_provenance,
            "attempt": attempt,
            "reservation_id": getattr(reservation, "reservation_id", None),
            "cost_tier": "free" if adapter.metadata.cost_rate_usd == 0 else "paid",
            "cost_notice": (
                "Fallback provider may incur usage charges"
                if adapter.metadata.cost_rate_usd > 0
                else None
            ),
            "safety_warning": adapter.metadata.warning,
        }

    @staticmethod
    def _enforce_fallback_mode(mode: str, chain: list[str]) -> None:
        """Enforce explicit AUTO/ASK/STRICT fallback policy."""
        del chain
        normalized = (mode or "auto").lower()
        if normalized == "strict":
            raise ProviderOrchestrationError(
                "Preferred provider unavailable and fallback is disabled",
                "FALLBACK_DISABLED",
                status_code=503,
            )
        if normalized == "ask":
            raise ProviderOrchestrationError(
                "Provider fallback requires confirmation",
                "FALLBACK_CONFIRMATION_REQUIRED",
                status_code=409,
            )

    @staticmethod
    def _map_provider_error(error: ProviderError) -> ProviderOrchestrationError:
        """Map provider failures to structured, secret-free service errors."""
        code_map = {
            ProviderErrorCode.AUTH_FAILED: ("PROVIDER_AUTH_FAILED", 401),
            ProviderErrorCode.CREDENTIAL_REQUIRED: ("CREDENTIAL_REQUIRED", 401),
            ProviderErrorCode.CREDENTIAL_EXPIRED: ("CREDENTIAL_EXPIRED", 401),
            ProviderErrorCode.RATE_LIMITED: ("PROVIDER_RATE_LIMITED", 429),
            ProviderErrorCode.TIMEOUT: ("PROVIDER_TIMEOUT", 504),
            ProviderErrorCode.PROVIDER_DOWN: ("PROVIDER_DOWN", 503),
            ProviderErrorCode.OUT_OF_MEMORY: ("PROVIDER_OOM", 422),
            ProviderErrorCode.WEBHOOK_MISSED: ("WEBHOOK_MISSED", 504),
            ProviderErrorCode.CONTENT_FAILURE: ("CONTENT_FAILURE", 422),
            ProviderErrorCode.WORKFLOW_FAILURE: ("WORKFLOW_FAILURE", 422),
            ProviderErrorCode.UNSUPPORTED_CAPABILITY: ("UNSUPPORTED_CAPABILITY", 422),
        }
        code, status = code_map.get(error.code, ("PROVIDER_ERROR", 503))
        return ProviderOrchestrationError(
            "Provider request failed",
            code,
            provider=error.provider,
            status_code=status,
            retryable=error.retryable,
        )

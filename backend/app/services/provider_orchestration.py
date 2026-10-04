"""Tenant-scoped BYO provider routing, cost gates, retries, and provenance."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.providers.byo import (
    ProviderError,
    ProviderErrorCode,
    ProviderRegistry,
    ProviderRequest,
    WorkloadKind,
)
from app.services.provider_orchestration_contracts import (
    IDEMPOTENT_RESULTS,
    RESULT_LOCK,
    PrivacyChecker,
    ProviderDispatchResult,
    ProviderOrchestrationError,
)
from app.services.provider_orchestration_support import ProviderOrchestrationSupport
from backend import cost_ledger
from backend.credentials import CredentialService


class BYOProviderOrchestrator(ProviderOrchestrationSupport):

    def __init__(
        self,
        *,
        org_id: str,
        registry: ProviderRegistry,
        privacy_checker: PrivacyChecker | None = None,
        cost_backend: Any = cost_ledger,
        credential_service: type[CredentialService] = CredentialService,
    ) -> None:
        if not org_id:
            raise ValueError("org_id is required")
        self.org_id = org_id
        self.registry = registry
        self._privacy_checker = privacy_checker
        self._cost = cost_backend
        self._credentials = credential_service

    async def health(self, provider: str, actor: str = "system") -> dict[str, Any]:
        """Return safe provider health and capability metadata."""
        adapter = self.registry.get(provider)
        credential = self._resolve_credential(adapter, actor=actor)
        result = await adapter.health(credential.secret if credential else None)
        return {
            "provider": result.provider,
            "healthy": result.healthy,
            "status": result.status,
            "latency_ms": result.latency_ms,
            "reason": result.reason,
            "capabilities": adapter.metadata.as_dict(),
        }

    async def dispatch_brain_completion(
        self,
        prompt: str,
        *,
        model: str = "llama3.1:8b",
        actor: str,
        idempotency_key: str,
        requested_provider: str | None = None,
        max_tokens: int = 2048,
    ) -> ProviderDispatchResult:
        """Route a Brain completion through the same BYO policy boundary."""
        if model == "llama3.1:8b":
            preferred = self.registry.selection(self.org_id, WorkloadKind.LLM).default_provider
            preferred_adapter = self.registry.get(preferred)
            if preferred_adapter.metadata.models:
                model = preferred_adapter.metadata.models[0]
        preferred_adapter = self.registry.get(
            self.registry.selection(self.org_id, WorkloadKind.LLM).default_provider
        )
        bounded_tokens = max_tokens
        if preferred_adapter.metadata.max_tokens is not None:
            bounded_tokens = min(max_tokens, preferred_adapter.metadata.max_tokens)
        request = ProviderRequest(
            workload=WorkloadKind.LLM,
            model=model,
            payload={"prompt": prompt, "max_tokens": bounded_tokens},
            timeout_seconds=preferred_adapter.metadata.timeout_seconds,
        )
        return await self.dispatch(
            request,
            actor=actor,
            idempotency_key=idempotency_key,
            requested_provider=requested_provider,
        )

    async def dispatch(
        self,
        request: ProviderRequest,
        *,
        actor: str,
        idempotency_key: str,
        requested_provider: str | None = None,
    ) -> ProviderDispatchResult:
        """Preflight, reserve, dispatch, retry, and record provider provenance.

        The tenant is bound at construction time. A caller cannot select a
        different organization through this method or its request object.
        """
        if not idempotency_key or not idempotency_key.strip():
            raise ProviderOrchestrationError(
                "Idempotency key is required", "IDEMPOTENCY_REQUIRED", status_code=422
            )
        cache_key = (self.org_id, idempotency_key.strip())
        with RESULT_LOCK:
            prior = IDEMPOTENT_RESULTS.get(cache_key)
        if prior is not None:
            return prior

        selection = self.registry.selection(self.org_id, request.workload)
        candidates = self.registry.candidates(
            self.org_id, request.workload, requested_provider
        )
        denied = {name.lower() for name in selection.denied_providers}
        fallback_chain: list[str] = []
        failures: list[ProviderError] = []

        for index, adapter in enumerate(candidates):
            provider_name = adapter.metadata.name
            if not adapter.metadata.enabled:
                fallback_chain.append(f"{provider_name}:disabled")
                continue
            if provider_name.lower() in denied:
                fallback_chain.append(f"{provider_name}:privacy_denied")
                continue
            if not await self._is_allowed(provider_name, request.workload):
                fallback_chain.append(f"{provider_name}:privacy_denied")
                continue
            if index > 0:
                self._enforce_fallback_mode(selection.fallback_mode, fallback_chain)

            candidate_request = self._request_for_adapter(request, adapter)
            try:
                material = self._resolve_credential(adapter, actor=actor)
            except ProviderOrchestrationError as exc:
                fallback_chain.append(f"{provider_name}:{exc.code}")
                if selection.fallback_mode.lower() == "strict" or index == len(candidates) - 1:
                    raise
                continue

            credential = material.secret if material else None
            try:
                estimate = await self._estimate(adapter, candidate_request)
            except ProviderOrchestrationError as exc:
                fallback_chain.append(f"{provider_name}:{exc.code}")
                if index == len(candidates) - 1:
                    raise
                continue
            reservation = self._reserve(
                estimate.estimated_cost_usd,
                provider_name,
                request.job_id,
            )
            attempts = 0
            try:
                max_attempts = adapter.metadata.max_retries + 1
                for attempt in range(max_attempts):
                    attempts = attempt + 1
                    try:
                        health = await adapter.health(credential)
                        if not health.healthy:
                            raise ProviderError(
                                "Provider is unavailable",
                                ProviderErrorCode.PROVIDER_DOWN,
                                provider_name,
                                retryable=True,
                                status_code=503,
                            )
                        result = await adapter.execute(candidate_request, credential)
                        self._finalize(reservation, result.actual_cost_usd or estimate.estimated_cost_usd)
                        dispatch_result = ProviderDispatchResult(
                            result=result,
                            provider=provider_name,
                            estimate_usd=estimate.estimated_cost_usd,
                            reservation_id=getattr(reservation, "reservation_id", None),
                            attempts=attempts,
                            fallback_chain=tuple(fallback_chain),
                            provenance=self._provenance(
                                adapter,
                                candidate_request,
                                material,
                                attempt=attempts,
                                reservation=reservation,
                            ),
                        )
                        with RESULT_LOCK:
                            IDEMPOTENT_RESULTS[cache_key] = dispatch_result
                        return dispatch_result
                    except ProviderError as exc:
                        failures.append(exc)
                        if not exc.retryable or attempts >= max_attempts:
                            fallback_chain.append(f"{provider_name}:{exc.code.value}")
                            break
                else:
                    fallback_chain.append(f"{provider_name}:retry_exhausted")
            except ProviderOrchestrationError:
                raise
            finally:
                await adapter.cleanup(candidate_request)
                if reservation is not None and getattr(reservation, "status", "") in {
                    "active",
                    "committed",
                }:
                    self._release(reservation)

            if failures and failures[-1].code in {
                ProviderErrorCode.CONTENT_FAILURE,
                ProviderErrorCode.WORKFLOW_FAILURE,
                ProviderErrorCode.UNSUPPORTED_CAPABILITY,
            }:
                raise self._map_provider_error(failures[-1])

        if failures:
            raise self._map_provider_error(failures[-1])
        raise ProviderOrchestrationError(
            "No configured provider can serve this workload",
            "PROVIDER_DOWN",
            status_code=503,
        )

    @staticmethod
    def _request_for_adapter(
        request: ProviderRequest,
        adapter: Any,
    ) -> ProviderRequest:
        """Adapt local model/limits to the current fallback provider safely."""
        metadata = adapter.metadata
        model = request.model
        if (
            request.workload == WorkloadKind.LLM
            and metadata.models
            and model not in metadata.models
            and model.lower().split(":", 1)[0] in {"llama3.1", "dolphin-llama3"}
        ):
            model = metadata.models[0]

        payload = dict(request.payload)
        if metadata.max_tokens is not None and "max_tokens" in payload:
            payload["max_tokens"] = min(int(payload["max_tokens"]), metadata.max_tokens)

        timeout = request.timeout_seconds or metadata.timeout_seconds
        timeout = min(timeout, metadata.timeout_seconds)
        if metadata.max_latency_ms is not None:
            timeout = min(timeout, metadata.max_latency_ms / 1000)
        return replace(request, model=model, payload=payload, timeout_seconds=timeout)


def clear_provider_idempotency() -> None:
    """Clear in-memory idempotency state for isolated tests."""
    with RESULT_LOCK:
        IDEMPOTENT_RESULTS.clear()

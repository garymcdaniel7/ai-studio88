"""Provider-specific HTTP adapters for the BYO provider contracts."""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.providers.byo_contracts import (
    ProviderError,
    ProviderErrorCode,
    ProviderEstimate,
    ProviderHealth,
    ProviderMetadata,
    ProviderRequest,
    ProviderResponse,
    ProviderResult,
    RequestTransport,
)


async def _http_transport(
    method: str,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    params: dict[str, str],
    timeout: float,
) -> ProviderResponse:
    """Perform one HTTP request; adapters sanitize all resulting errors."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.request(
            method,
            url,
            headers=headers,
            json=payload or None,
            params=params or None,
        )
        try:
            body = response.json()
        except ValueError:
            body = {}
        return ProviderResponse(
            status_code=response.status_code,
            body=body if isinstance(body, dict) else {},
        )


class HTTPProviderAdapter:
    """Shared HTTP implementation for user-owned provider APIs."""

    def __init__(
        self,
        metadata: ProviderMetadata,
        *,
        transport: RequestTransport | None = None,
    ) -> None:
        self._metadata = metadata
        self._transport = transport or _http_transport

    @property
    def metadata(self) -> ProviderMetadata:
        """Return safe static metadata."""
        return self._metadata

    def _auth_headers(self, credential: str | None) -> dict[str, str]:
        """Build auth headers without retaining or logging the credential."""
        return {"Authorization": f"Bearer {credential}"} if credential else {}

    def _auth_params(self, credential: str | None) -> dict[str, str]:
        """Build provider-specific auth query parameters."""
        return {}

    def _url(self, path: str) -> str:
        """Join configured base URL and endpoint path."""
        return f"{self._metadata.base_url.rstrip('/')}/{path.lstrip('/')}"

    async def _request(
        self,
        method: str,
        path: str,
        *,
        credential: str | None,
        payload: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> ProviderResponse:
        """Call transport and classify status without exposing response bodies."""
        if self._metadata.credential_required and not credential:
            raise ProviderError(
                "Provider credential is required",
                ProviderErrorCode.CREDENTIAL_REQUIRED,
                self._metadata.name,
                status_code=401,
            )
        try:
            response = await self._transport(
                method,
                self._url(path),
                self._auth_headers(credential),
                payload or {},
                self._auth_params(credential),
                min(
                    timeout or self._metadata.timeout_seconds,
                    (self._metadata.max_latency_ms / 1000)
                    if self._metadata.max_latency_ms is not None
                    else timeout or self._metadata.timeout_seconds,
                ),
            )
        except (httpx.TimeoutException, TimeoutError) as exc:
            raise ProviderError(
                "Provider request timed out",
                ProviderErrorCode.TIMEOUT,
                self._metadata.name,
                retryable=True,
                status_code=504,
            ) from exc
        except (httpx.ConnectError, httpx.TransportError, OSError) as exc:
            raise ProviderError(
                "Provider is unavailable",
                ProviderErrorCode.PROVIDER_DOWN,
                self._metadata.name,
                retryable=True,
                status_code=503,
            ) from exc

        if response.status_code in (401, 403):
            raise ProviderError(
                "Provider authentication failed",
                ProviderErrorCode.AUTH_FAILED,
                self._metadata.name,
                status_code=401,
            )
        if response.status_code == 408:
            raise ProviderError(
                "Provider request timed out",
                ProviderErrorCode.TIMEOUT,
                self._metadata.name,
                retryable=True,
                status_code=504,
            )
        if response.status_code == 429:
            raise ProviderError(
                "Provider rate limit reached",
                ProviderErrorCode.RATE_LIMITED,
                self._metadata.name,
                retryable=True,
                status_code=429,
            )
        if response.status_code in (500, 502, 503, 504):
            raise ProviderError(
                "Provider is unavailable",
                ProviderErrorCode.PROVIDER_DOWN,
                self._metadata.name,
                retryable=True,
                status_code=503,
            )
        if response.status_code in (400, 404, 409, 422):
            raise ProviderError(
                "Provider rejected the workload",
                ProviderErrorCode.CONTENT_FAILURE,
                self._metadata.name,
                status_code=422,
            )
        if response.status_code < 200 or response.status_code >= 300:
            raise ProviderError(
                "Provider request failed",
                ProviderErrorCode.PROVIDER_DOWN,
                self._metadata.name,
                retryable=True,
                status_code=503,
            )
        return response

    async def health(self, credential: str | None = None) -> ProviderHealth:
        """Check configured provider health with a bounded timeout."""
        if not self._metadata.enabled:
            return ProviderHealth(
                self._metadata.name,
                False,
                "disabled",
                reason="disabled",
            )
        if self._metadata.credential_required and not credential:
            return ProviderHealth(
                self._metadata.name,
                False,
                "credential_required",
                reason="credential_required",
            )
        started = time.perf_counter()
        try:
            await self._request(
                "GET",
                self._metadata.health_path,
                credential=credential,
                timeout=self._metadata.health_timeout_seconds,
            )
        except ProviderError as exc:
            return ProviderHealth(
                self._metadata.name,
                False,
                exc.code.value,
                (time.perf_counter() - started) * 1000,
                reason=exc.code.value,
            )
        return ProviderHealth(
            self._metadata.name,
            True,
            "healthy",
            (time.perf_counter() - started) * 1000,
        )

    async def estimate_cost(self, request: ProviderRequest) -> ProviderEstimate:
        """Estimate cost locally from declared provider pricing metadata."""
        payload = request.payload
        duration = int(payload.get("duration_seconds", self._default_duration(request)))
        units = self._units(request)
        estimated = round(max(units, 0.0) * self._metadata.cost_rate_usd, 6)
        return ProviderEstimate(
            provider=self._metadata.name,
            estimated_cost_usd=estimated,
            duration_seconds=duration,
            confidence=0.8,
        )

    async def execute(
        self, request: ProviderRequest, credential: str | None = None
    ) -> ProviderResult:
        """Submit one provider-neutral request through the adapter."""
        if not self._metadata.enabled:
            raise ProviderError(
                "Provider is disabled",
                ProviderErrorCode.UNSUPPORTED_CAPABILITY,
                self._metadata.name,
                status_code=503,
            )
        if request.model not in self._metadata.models and self._metadata.models:
            raise ProviderError(
                "Requested model is unsupported by provider",
                ProviderErrorCode.UNSUPPORTED_CAPABILITY,
                self._metadata.name,
                status_code=422,
            )
        requested_tokens = request.payload.get("max_tokens")
        if (
            requested_tokens is not None
            and self._metadata.max_tokens is not None
            and int(requested_tokens) > self._metadata.max_tokens
        ):
            raise ProviderError(
                "Requested token limit exceeds provider policy",
                ProviderErrorCode.UNSUPPORTED_CAPABILITY,
                self._metadata.name,
                status_code=422,
            )
        response = await self._request(
            "POST",
            self._metadata.execute_path,
            credential=credential,
            payload=request.payload,
            timeout=request.timeout_seconds,
        )
        estimate = await self.estimate_cost(request)
        return ProviderResult(
            provider=self._metadata.name,
            model=request.model,
            output=response.body,
            actual_cost_usd=estimate.estimated_cost_usd,
            provider_job_id=str(response.body.get("id")) if response.body.get("id") else None,
            metadata={"status_code": response.status_code},
        )

    async def cleanup(self, request: ProviderRequest) -> None:
        """No persistent state is retained by BYO HTTP adapters."""
        del request

    def _default_duration(self, request: ProviderRequest) -> int:
        """Choose a conservative duration for preflight estimates."""
        return int(request.timeout_seconds or self._metadata.timeout_seconds)

    def _units(self, request: ProviderRequest) -> float:
        """Return billable units according to the metadata cost unit."""
        payload = request.payload
        if self._metadata.cost_unit == "hour":
            return int(payload.get("duration_seconds", self._default_duration(request))) / 3600
        if self._metadata.cost_unit == "million_tokens":
            return int(payload.get("max_tokens", 2048)) / 1_000_000
        if self._metadata.cost_unit == "million_characters":
            return len(str(payload.get("text", ""))) / 1_000_000
        return 1.0


class GeminiAdapter(HTTPProviderAdapter):
    """Google Gemini BYO LLM adapter."""

    def _auth_headers(self, credential: str | None) -> dict[str, str]:
        return {"Content-Type": "application/json"}

    def _auth_params(self, credential: str | None) -> dict[str, str]:
        return {"key": credential} if credential else {}


class ElevenLabsAdapter(HTTPProviderAdapter):
    """ElevenLabs BYO voice adapter."""

    def _auth_headers(self, credential: str | None) -> dict[str, str]:
        return (
            {"xi-api-key": credential, "Content-Type": "application/json"}
            if credential
            else {}
        )


class OllamaLocalAdapter(HTTPProviderAdapter):
    """Credential-free Ollama adapter with model-aware health checks."""

    async def health(self, credential: str | None = None) -> ProviderHealth:
        """Check Ollama reachability and, when advertised, model availability."""
        if not self.metadata.enabled:
            return ProviderHealth(self.metadata.name, False, "disabled", reason="disabled")
        started = time.perf_counter()
        try:
            response = await self._request(
                "GET",
                self.metadata.health_path,
                credential=credential,
                timeout=self.metadata.health_timeout_seconds,
            )
        except ProviderError as exc:
            return ProviderHealth(
                self.metadata.name,
                False,
                exc.code.value,
                (time.perf_counter() - started) * 1000,
                reason=exc.code.value,
            )

        advertised_models = response.body.get("models")
        if isinstance(advertised_models, list) and advertised_models:
            names = {
                str(item.get("name", ""))
                for item in advertised_models
                if isinstance(item, dict)
            }
            available_bases = {name.split(":", 1)[0] for name in names}
            if self.metadata.models and not any(
                model in names or model.split(":", 1)[0] in available_bases
                for model in self.metadata.models
            ):
                return ProviderHealth(
                    self.metadata.name,
                    False,
                    "model_unavailable",
                    (time.perf_counter() - started) * 1000,
                    reason="model_unavailable",
                )

        return ProviderHealth(
            self.metadata.name,
            True,
            "healthy",
            (time.perf_counter() - started) * 1000,
        )

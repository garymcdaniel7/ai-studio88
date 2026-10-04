"""Unit coverage for tenant BYO routing, cost gates, and retry policy."""

from __future__ import annotations

from typing import Any

import pytest

from app.core.config import Settings
from app.providers.byo import (
    ProviderErrorCode,
    ProviderEstimate,
    ProviderHealth,
    ProviderMetadata,
    ProviderRegistry,
    ProviderRequest,
    ProviderResponse,
    ProviderResult,
    TenantProviderSelection,
    WorkloadKind,
    build_default_registry,
)
from app.services.provider_orchestration import (
    BYOProviderOrchestrator,
    ProviderOrchestrationError,
    clear_provider_idempotency,
)
from backend import cost_ledger
from backend.credentials import CredentialService, ProviderType, _credential_audit, _store

ORG_A = "11111111-1111-1111-1111-111111111111"
SECRET = "sk-byo-secret-never-return"


def settings() -> Settings:
    """Build isolated test settings without loading project environment files."""
    return Settings(_env_file=None, app_env="test")


async def successful_transport(
    method: str,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    params: dict[str, str],
    timeout: float,
) -> ProviderResponse:
    """Return deterministic health and execution responses."""
    del headers, payload, params, timeout
    return ProviderResponse(200, {"id": "provider-job-1", "url": url, "method": method})


@pytest.fixture(autouse=True)
def reset_state() -> None:
    """Reset in-memory credential, cost, and idempotency state."""
    _store.clear()
    _credential_audit.clear()
    cost_ledger._reset_store()
    clear_provider_idempotency()
    yield
    _store.clear()
    _credential_audit.clear()
    cost_ledger._reset_store()
    clear_provider_idempotency()


class _ScriptedAdapter:
    """Small provider double used to verify routing and retry semantics."""

    def __init__(self, name: str, outcomes: list[str]) -> None:
        self._outcomes = list(outcomes)
        self.execute_calls = 0
        self.health_calls = 0
        self._metadata = ProviderMetadata(
            name=name,
            display_name=name,
            workload=WorkloadKind.GPU,
            credential_provider=None,
            capabilities=("image",),
            models=("model",),
            cost_unit="request",
            cost_rate_usd=0.01,
            credential_required=False,
            max_retries=3,
        )

    @property
    def metadata(self) -> Any:
        """Return fake metadata."""
        return self._metadata

    async def health(self, credential: str | None = None) -> ProviderHealth:
        """Return healthy while counting health checks."""
        del credential
        self.health_calls += 1
        return ProviderHealth(self._metadata.name, True, "healthy")

    async def estimate_cost(self, request: ProviderRequest) -> ProviderEstimate:
        """Return a deterministic paid estimate."""
        del request
        return ProviderEstimate(self._metadata.name, 0.01, 1, 1.0)

    async def execute(
        self, request: ProviderRequest, credential: str | None = None
    ) -> ProviderResult:
        """Produce scripted provider outcomes."""
        del request, credential
        self.execute_calls += 1
        outcome = self._outcomes.pop(0) if self._outcomes else "success"
        if outcome == "timeout":
            from app.providers.byo import ProviderError

            raise ProviderError(
                "timeout", ProviderErrorCode.TIMEOUT, self._metadata.name, retryable=True
            )
        if outcome == "content":
            from app.providers.byo import ProviderError

            raise ProviderError("content", ProviderErrorCode.CONTENT_FAILURE, self._metadata.name)
        return ProviderResult(self._metadata.name, "model", {"ok": True}, 0.01)

    async def cleanup(self, request: ProviderRequest) -> None:
        """No-op cleanup for the fake."""
        del request


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fallback_order_cost_gate_and_idempotency() -> None:
    """AUTO fallback is ordered, cost-gated before dispatch, and idempotent."""
    first = _ScriptedAdapter("first", ["timeout", "timeout", "timeout", "timeout"])
    second = _ScriptedAdapter("second", ["success"])
    registry = ProviderRegistry([first, second])
    registry.set_selection(
        ORG_A,
        WorkloadKind.GPU,
        TenantProviderSelection("first", ("second",), fallback_mode="auto"),
    )
    orchestrator = BYOProviderOrchestrator(org_id=ORG_A, registry=registry)

    request = ProviderRequest(WorkloadKind.GPU, "model", {"duration_seconds": 1})
    result = await orchestrator.dispatch(request, actor="user-a", idempotency_key="job-1")
    again = await orchestrator.dispatch(request, actor="user-a", idempotency_key="job-1")

    assert result.provider == "second"
    assert result is again
    assert first.execute_calls == 4
    assert second.execute_calls == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cost_gate_rejects_before_provider_dispatch() -> None:
    """Hard budget rejection happens after estimate but before health/execute."""
    adapter = _ScriptedAdapter("first", ["success"])
    registry = ProviderRegistry([adapter])
    registry.set_selection(ORG_A, WorkloadKind.GPU, TenantProviderSelection("first"))
    cost_ledger.set_workspace_limits(
        ORG_A,
        cost_ledger.BudgetLimits(daily_hard_usd=0.001, daily_soft_usd=0.001),
    )
    orchestrator = BYOProviderOrchestrator(org_id=ORG_A, registry=registry)

    with pytest.raises(ProviderOrchestrationError) as exc_info:
        await orchestrator.dispatch(
            ProviderRequest(WorkloadKind.GPU, "model", {}),
            actor="user-a",
            idempotency_key="over-budget",
        )
    assert exc_info.value.code == "COST_GATE_REJECTED"
    assert adapter.health_calls == 0
    assert adapter.execute_calls == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_no_retry_for_content_failure_and_cleanup_runs() -> None:
    """Content/workflow failures fail fast and do not consume retries."""
    adapter = _ScriptedAdapter("first", ["content"])
    registry = ProviderRegistry([adapter])
    registry.set_selection(ORG_A, WorkloadKind.GPU, TenantProviderSelection("first"))
    orchestrator = BYOProviderOrchestrator(org_id=ORG_A, registry=registry)

    with pytest.raises(ProviderOrchestrationError) as exc_info:
        await orchestrator.dispatch(
            ProviderRequest(WorkloadKind.GPU, "model", {}),
            actor="user-a",
            idempotency_key="content-failure",
        )
    assert exc_info.value.code == "CONTENT_FAILURE"
    assert adapter.execute_calls == 1
    assert adapter.health_calls == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_expired_credential_blocks_dispatch_without_network() -> None:
    """Expired tenant credentials map to a safe auth error before provider calls."""
    registry = build_default_registry(settings=settings(), transport=successful_transport)
    registry.set_selection(
        ORG_A,
        WorkloadKind.LLM,
        TenantProviderSelection("openai", allow_platform_fallback=False),
    )
    CredentialService.store(
        org_id=ORG_A,
        provider=ProviderType.OPENAI,
        secret=SECRET,
        expires_at="2000-01-01T00:00:00+00:00",
        actor="user-a",
    )
    orchestrator = BYOProviderOrchestrator(org_id=ORG_A, registry=registry)

    with pytest.raises(ProviderOrchestrationError) as exc_info:
        await orchestrator.dispatch(
            ProviderRequest(WorkloadKind.LLM, "gpt-4o-mini", {}),
            actor="user-a",
            idempotency_key="expired-key",
        )
    assert exc_info.value.code == "CREDENTIAL_EXPIRED"
    assert SECRET not in str(exc_info.value)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_privacy_denied_provider_is_not_dispatched() -> None:
    """Workspace privacy policy blocks a provider before health or execution."""
    adapter = _ScriptedAdapter("first", ["success"])
    registry = ProviderRegistry([adapter])
    registry.set_selection(ORG_A, WorkloadKind.GPU, TenantProviderSelection("first"))
    orchestrator = BYOProviderOrchestrator(
        org_id=ORG_A,
        registry=registry,
        privacy_checker=lambda provider, workload: False,
    )

    with pytest.raises(ProviderOrchestrationError) as exc_info:
        await orchestrator.dispatch(
            ProviderRequest(WorkloadKind.GPU, "model", {}),
            actor="user-a",
            idempotency_key="privacy-denied",
        )
    assert exc_info.value.code == "PROVIDER_DOWN"
    assert adapter.execute_calls == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_brain_completion_is_local_first_and_free() -> None:
    """Brain uses local Ollama first and does not reserve paid budget."""
    registry = build_default_registry(settings=settings(), transport=successful_transport)
    orchestrator = BYOProviderOrchestrator(org_id=ORG_A, registry=registry)

    result = await orchestrator.dispatch_brain_completion(
        "Write a short scene", actor="user-a", idempotency_key="brain-local-1"
    )

    assert result.provider == "ollama"
    assert result.estimate_usd == 0
    assert result.reservation_id is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_unavailable_local_ollama_falls_back_to_tenant_cloud_key() -> None:
    """A bounded local health failure falls back to a tenant-owned cloud key."""
    calls: list[str] = []

    async def local_down_cloud_up(
        method: str,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        params: dict[str, str],
        timeout: float,
    ) -> ProviderResponse:
        del method, headers, payload, params, timeout
        calls.append(url)
        if "localhost" in url:
            return ProviderResponse(503, {})
        return ProviderResponse(200, {"id": "cloud-job-1"})

    CredentialService.store(
        org_id=ORG_A,
        provider=ProviderType.OPENAI,
        secret=SECRET,
        actor="user-a",
    )
    registry = build_default_registry(settings=settings(), transport=local_down_cloud_up)
    orchestrator = BYOProviderOrchestrator(org_id=ORG_A, registry=registry)

    result = await orchestrator.dispatch_brain_completion(
        "Write a short scene",
        actor="user-a",
        idempotency_key="local-down-cloud-fallback",
    )

    assert result.provider == "openai"
    assert result.estimate_usd > 0
    assert any("localhost" in url for url in calls)
    assert any("api.openai.com" in url for url in calls)
    assert "ollama:provider_down" in result.fallback_chain
    assert SECRET not in str(result.as_dict())
    assert result.provenance["cost_notice"] == "Fallback provider may incur usage charges"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_strict_mode_does_not_fallback_after_local_failure() -> None:
    """STRICT tenant policy fails closed instead of silently incurring cloud cost."""
    async def local_down(*_: Any, **__: Any) -> ProviderResponse:
        return ProviderResponse(503, {})

    registry = build_default_registry(settings=settings(), transport=local_down)
    registry.set_selection(
        ORG_A,
        WorkloadKind.LLM,
        TenantProviderSelection("ollama", ("openai",), fallback_mode="strict"),
    )
    orchestrator = BYOProviderOrchestrator(org_id=ORG_A, registry=registry)

    with pytest.raises(ProviderOrchestrationError) as exc_info:
        await orchestrator.dispatch_brain_completion(
            "Do not leave local processing",
            actor="user-a",
            idempotency_key="strict-local-only",
        )

    assert exc_info.value.code == "FALLBACK_DISABLED"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cloud_fallback_is_tenant_isolated() -> None:
    """A cloud credential from tenant A is never usable by tenant B."""
    CredentialService.store(
        org_id=ORG_A,
        provider=ProviderType.OPENAI,
        secret=SECRET,
        actor="user-a",
    )

    async def cloud_only(*_: Any, **__: Any) -> ProviderResponse:
        return ProviderResponse(200, {"id": "cloud-job-2"})

    registry = build_default_registry(settings=settings(), transport=cloud_only)
    registry.set_selection(
        ORG_A,
        WorkloadKind.LLM,
        TenantProviderSelection("openai", (), fallback_mode="auto"),
    )
    registry.set_selection(
        "22222222-2222-2222-2222-222222222222",
        WorkloadKind.LLM,
        TenantProviderSelection("openai", (), fallback_mode="auto"),
    )

    tenant_a = BYOProviderOrchestrator(org_id=ORG_A, registry=registry)
    tenant_b = BYOProviderOrchestrator(
        org_id="22222222-2222-2222-2222-222222222222", registry=registry
    )
    result = await tenant_a.dispatch_brain_completion(
        "Tenant A",
        actor="user-a",
        idempotency_key="tenant-a-cloud",
    )
    assert result.provider == "openai"

    with pytest.raises(ProviderOrchestrationError) as exc_info:
        await tenant_b.dispatch_brain_completion(
            "Tenant B",
            actor="user-b",
            idempotency_key="tenant-b-cloud",
        )
    assert exc_info.value.code == "CREDENTIAL_REQUIRED"
    assert SECRET not in str(exc_info.value)

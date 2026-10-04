"""Unit/property coverage for BYO credentials and provider contracts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.core.config import Settings
from app.providers.byo import (
    ProviderErrorCode,
    ProviderRequest,
    ProviderResponse,
    TenantProviderSelection,
    WorkloadKind,
    build_default_registry,
)
from app.services.provider_orchestration import clear_provider_idempotency
from backend import cost_ledger
from backend.credentials import CredentialService, ProviderType, _credential_audit, _store

ORG_A = "11111111-1111-1111-1111-111111111111"
ORG_B = "22222222-2222-2222-2222-222222222222"
SECRET = "sk-byo-secret-never-return"


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


def settings() -> Settings:
    """Build isolated test settings without loading project environment files."""
    return Settings(_env_file=None, app_env="test")


@pytest.mark.unit
def test_registry_exposes_requested_capabilities_without_secrets() -> None:
    """All requested BYO providers expose safe metadata and policy controls."""
    registry = build_default_registry(settings=settings())
    metadata = {item["name"]: item for item in registry.list_metadata()}

    assert {
        "thunder_compute",
        "runcomfy",
        "gemini",
        "openai",
        "elevenlabs",
        "replicate",
        "ollama",
    } <= metadata.keys()
    assert metadata["runcomfy"]["supports_webhooks"] is True
    assert metadata["thunder_compute"]["supports_batch"] is True
    assert metadata["ollama"]["local"] is True
    assert metadata["ollama"]["credential_required"] is False
    assert all("api_key" not in str(item).lower() for item in metadata.values())


@pytest.mark.unit
def test_credential_lifecycle_masks_secret_and_preserves_rotation_overlap() -> None:
    """Customer keys rotate with a bounded overlap and never disclose material."""
    stored = CredentialService.store(
        org_id=ORG_A,
        provider=ProviderType.OPENAI,
        secret=SECRET,
        key_id=SECRET,
        expires_at=(datetime.now(UTC) + timedelta(days=90)).isoformat(),
        actor="user-a",
    )
    rotated = CredentialService.rotate(
        org_id=ORG_A,
        provider=ProviderType.OPENAI,
        new_secret="sk-new-secret-never-return",
        actor="user-a",
    )

    assert SECRET not in str(stored)
    assert SECRET not in str(rotated)
    assert stored["key_hint"] != SECRET
    assert rotated["version"] == 2
    assert rotated["status"] == "active"
    old = [row for row in _store.values() if row.version == 1][0]
    assert old.rotation_overlap_until is not None
    assert CredentialService.resolve(org_id=ORG_A, provider=ProviderType.OPENAI) == "sk-new-secret-never-return"
    assert CredentialService.resolve(org_id=ORG_B, provider=ProviderType.OPENAI) is None


@pytest.mark.unit
@given(org_id=st.uuids(version=4).map(str))
def test_credentials_are_tenant_isolated_for_arbitrary_orgs(org_id: str) -> None:
    """**Validates: Requirements 2.17, 3.1, 3.13**

    A key stored for one tenant is never resolved by a different tenant.
    """
    other_org = ORG_B if org_id != ORG_B else ORG_A
    CredentialService.store(
        org_id=org_id,
        provider=ProviderType.REPLICATE,
        secret=SECRET,
        actor="test",
    )
    assert CredentialService.resolve(
        org_id=org_id, provider=ProviderType.REPLICATE, allow_platform_fallback=False
    ) == SECRET
    assert CredentialService.resolve(
        org_id=other_org, provider=ProviderType.REPLICATE, allow_platform_fallback=False
    ) is None


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


@pytest.mark.unit
@pytest.mark.asyncio
async def test_provider_contract_success_cost_and_auth_failure() -> None:
    """A mocked provider transport covers success, estimate, and auth mapping."""
    registry = build_default_registry(settings=settings(), transport=successful_transport)
    adapter = registry.get("openai")
    request = ProviderRequest(WorkloadKind.LLM, "gpt-4o-mini", {"max_tokens": 100})

    health = await adapter.health(SECRET)
    estimate = await adapter.estimate_cost(request)
    result = await adapter.execute(request, SECRET)

    assert health.healthy is True
    assert estimate.estimated_cost_usd > 0
    assert result.provider == "openai"
    assert result.output["id"] == "provider-job-1"

    async def auth_transport(*_: Any, **__: Any) -> ProviderResponse:
        return ProviderResponse(401, {})

    auth_registry = build_default_registry(settings=settings(), transport=auth_transport)
    with pytest.raises(Exception) as exc_info:
        await auth_registry.get("openai").execute(request, SECRET)
    assert exc_info.value.code == ProviderErrorCode.AUTH_FAILED
    assert SECRET not in str(exc_info.value)


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (429, ProviderErrorCode.RATE_LIMITED),
        (408, ProviderErrorCode.TIMEOUT),
        (503, ProviderErrorCode.PROVIDER_DOWN),
        (422, ProviderErrorCode.CONTENT_FAILURE),
    ],
)
async def test_provider_contract_maps_failure_classes(
    status_code: int, expected: ProviderErrorCode
) -> None:
    """Provider HTTP classes are normalized without returning provider bodies."""

    async def failing_transport(*_: Any, **__: Any) -> ProviderResponse:
        return ProviderResponse(status_code, {"secret": SECRET})

    registry = build_default_registry(settings=settings(), transport=failing_transport)
    with pytest.raises(Exception) as exc_info:
        await registry.get("replicate").execute(
            ProviderRequest(WorkloadKind.MODEL, "model-version", {}), SECRET
        )
    assert exc_info.value.code == expected
    assert SECRET not in str(exc_info.value)


@pytest.mark.unit
def test_ollama_defaults_local_first_and_redacts_endpoint() -> None:
    """Local Ollama is the default LLM route without exposing backend topology."""
    registry = build_default_registry(settings=settings())
    selection = registry.selection(ORG_A, WorkloadKind.LLM)
    metadata = registry.get("ollama").metadata.as_dict()

    assert selection.default_provider == "ollama"
    assert selection.fallback_mode == "auto"
    assert metadata["enabled"] is True
    assert metadata["credential_required"] is False
    assert metadata["local"] is True
    assert metadata["endpoint_configured"] is True
    assert "base_url" not in metadata
    assert "localhost" not in str(metadata)


@pytest.mark.unit
def test_dolphin_requires_explicit_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    """The uncensored model is rejected when opt-in is explicitly disabled."""
    monkeypatch.delenv("OLLAMA_UNCENSORED_OPT_IN", raising=False)

    with pytest.raises(ValueError, match="UNCENSORED_OPT_IN"):
        Settings(
            _env_file=None,
            app_env="test",
            ollama_model="dolphin-llama3:8b",
            ollama_uncensored_opt_in=False,
        )


@pytest.mark.unit
def test_dolphin_opt_in_exposes_warning_and_safe_capabilities() -> None:
    """Explicit opt-in exposes only the warning and safe capability metadata."""
    configured = Settings(
        _env_file=None,
        app_env="test",
        ollama_model="dolphin-llama3:8b",
        ollama_uncensored_opt_in=True,
    )
    registry = build_default_registry(settings=configured)
    status = registry.get("ollama").metadata.as_dict()

    assert status["uncensored"] is True
    assert status["local"] is True
    assert status["credential_required"] is False
    assert "uncensored" in status["warning"].lower()
    assert "http://" not in str(status)
    assert "api_key" not in str(status).lower()


@pytest.mark.unit
def test_protected_profiles_reject_local_ollama_endpoint() -> None:
    """Staging/production cannot silently depend on a local Ollama process."""
    with pytest.raises(ValueError, match="managed_vps"):
        Settings(
            _env_file=None,
            app_env="production",
            ollama_enabled=True,
            ollama_mode="local",
            ollama_base_url="http://localhost:11434",
        )


@pytest.mark.unit
def test_selection_is_tenant_scoped() -> None:
    """A provider preference for one organization never changes another tenant."""
    registry = build_default_registry(settings=settings())
    registry.set_selection(
        ORG_A,
        WorkloadKind.LLM,
        selection=TenantProviderSelection("openai", fallback_chain=("gemini",)),
    )

    assert registry.selection(ORG_A, WorkloadKind.LLM).default_provider == "openai"
    assert registry.selection(ORG_B, WorkloadKind.LLM).default_provider == "ollama"

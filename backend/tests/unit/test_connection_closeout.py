"""Close-out tests for connection credential namespaces and provider evidence."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException, status

from app.providers.byo_adapters import HTTPProviderAdapter
from app.providers.byo_contracts import (
    ProviderError,
    ProviderErrorCode,
    ProviderHealth,
    ProviderMetadata,
    ProviderResponse,
    WorkloadKind,
)
from app.services.connection_service import ConnectionService
from backend.credentials import CredentialService, ProviderType, _store

ORG_A = UUID("11111111-1111-1111-1111-111111111111")
ORG_B = UUID("22222222-2222-2222-2222-222222222222")
USER_A = UUID("33333333-3333-3333-3333-333333333333")
CONNECTION_ID = UUID("44444444-4444-4444-4444-444444444444")
TOKEN_REF = UUID("55555555-5555-5555-5555-555555555555")


class FakeConnectionRepository:
    """Small tenant-local repository double for service lifecycle tests."""

    def __init__(self, org_id: UUID, connection: SimpleNamespace | None = None) -> None:
        self.org_id = org_id
        self.connection = connection
        self.deleted = False

    async def create(self, **kwargs: object) -> SimpleNamespace:
        """Create a connection using the service-assigned authoritative ID."""
        self.connection = SimpleNamespace(
            id=kwargs["id"],
            org_id=self.org_id,
            provider_name=kwargs["provider_name"],
            lifecycle_state=kwargs["lifecycle_state"],
            oauth_token_ref=None,
            capabilities=kwargs.get("capabilities", []),
            allowed_roles=kwargs.get("allowed_roles", []),
            tool_policy=kwargs.get("tool_policy", {}),
            health_status=None,
            last_health_check_at=None,
            ownership=kwargs.get("ownership"),
            category=kwargs.get("category"),
            display_name=kwargs.get("display_name"),
        )
        return self.connection

    async def get_by_id(self, connection_id: UUID) -> SimpleNamespace:
        """Return only the tenant-owned connection."""
        if self.connection is None or self.connection.id != connection_id or self.deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
        return self.connection

    async def find_by_provider(self, **_: object) -> SimpleNamespace | None:
        """Return an active duplicate candidate when present."""
        if self.connection is not None and not self.deleted:
            if self.connection.lifecycle_state not in {"disconnected", "revoked"}:
                return self.connection
        return None

    async def update_fields(self, connection_id: UUID, **kwargs: object) -> SimpleNamespace:
        """Apply safe connection field updates."""
        connection = await self.get_by_id(connection_id)
        for key, value in kwargs.items():
            setattr(connection, key, value)
        return connection

    async def update_health(self, connection_id: UUID, health_status: str) -> SimpleNamespace:
        """Record health status for a connection."""
        connection = await self.get_by_id(connection_id)
        connection.health_status = health_status
        return connection

    async def update_lifecycle_state(
        self, connection_id: UUID, new_state: str
    ) -> SimpleNamespace:
        """Record a lifecycle transition."""
        connection = await self.get_by_id(connection_id)
        connection.lifecycle_state = new_state
        return connection

    async def delete(self, connection_id: UUID) -> None:
        """Delete a failed provisional connection."""
        await self.get_by_id(connection_id)
        self.deleted = True


def make_service(
    *,
    org_id: UUID = ORG_A,
    lifecycle_state: str = "connected",
    provider_name: str = "openai",
    oauth_token_ref: UUID | None = TOKEN_REF,
) -> tuple[ConnectionService, FakeConnectionRepository]:
    """Build a service without opening a database connection."""
    connection = SimpleNamespace(
        id=CONNECTION_ID,
        org_id=org_id,
        provider_name=provider_name,
        lifecycle_state=lifecycle_state,
        oauth_token_ref=oauth_token_ref,
        capabilities=["chat"],
        allowed_roles=["owner", "admin", "editor"],
        tool_policy={},
        health_status="healthy",
        last_health_check_at=None,
        ownership="workspace",
        category="ai_provider",
        display_name="Test connection",
    )
    repository = FakeConnectionRepository(org_id, connection)
    service = object.__new__(ConnectionService)
    service._org_id = org_id
    service._repo = repository
    return service, repository


def oauth_settings(**overrides: str) -> SimpleNamespace:
    """Return safe test OAuth settings without reading an environment file."""
    values = {
        "fanvue_client_id": "client-id",
        "fanvue_client_secret": "client-secret",
        "api_base_url": "http://localhost:8000",
        "oauth_redirect_uri": "http://localhost:8000/api/v1/connections/callback",
        "provider_timeout_seconds": 5.0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_oauth_exchange_uses_configured_token_url_and_never_fabricates() -> None:
    """Successful OAuth exchange returns only the provider's mocked evidence."""
    response = SimpleNamespace(
        status_code=200,
        json=lambda: {
            "access_token": "provider-access-secret",
            "refresh_token": "provider-refresh-secret",
            "expires_in": 3600,
        },
    )

    class FakeClient:
        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, url: str, *, data: dict[str, str]) -> SimpleNamespace:
            self.url = url
            self.data = data
            return response

    client = FakeClient()
    service, _ = make_service()
    with (
        patch(
            "app.services.connection_service.get_settings",
            return_value=oauth_settings(),
        ),
        patch("app.services.connection_service.httpx.AsyncClient", return_value=client),
    ):
        token_data = await service._exchange_oauth_code("fanvue", "one-time-code")

    assert token_data["access_token"] == "provider-access-secret"
    assert client.url == "https://auth.fanvue.com/oauth/token"
    assert client.data["client_id"] == "client-id"
    assert client.data["client_secret"] == "client-secret"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_oauth_missing_configuration_is_structured_and_secret_free() -> None:
    """OAuth cannot create a token or connected state without provider config."""
    service, _ = make_service()
    with patch(
        "app.services.connection_service.get_settings",
        return_value=oauth_settings(fanvue_client_id="", fanvue_client_secret=""),
    ), pytest.raises(HTTPException) as exc_info:
        await service._exchange_oauth_code("fanvue", "secret-auth-code")

    error = exc_info.value
    assert error.headers["X-Error-Code"] == "CONNECTION_PROVIDER_UNCONFIGURED"
    assert error.detail["code"] == "CONNECTION_PROVIDER_UNCONFIGURED"
    assert "secret-auth-code" not in str(error.detail)


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("provider_status", [401, 403, 429, 500])
async def test_oauth_provider_failures_are_structured(
    provider_status: int,
) -> None:
    """Provider rejection never becomes a fabricated token response."""
    response = SimpleNamespace(status_code=provider_status, json=lambda: {})

    class FakeClient:
        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, url: str, *, data: dict[str, str]) -> SimpleNamespace:
            return response

    service, _ = make_service()
    with (
        patch(
            "app.services.connection_service.get_settings",
            return_value=oauth_settings(),
        ),
        patch("app.services.connection_service.httpx.AsyncClient", return_value=FakeClient()),
        pytest.raises(HTTPException) as exc_info,
    ):
        await service._exchange_oauth_code("fanvue", "one-time-code")

    assert "access_token" not in str(exc_info.value.detail)
    assert "one-time-code" not in str(exc_info.value.detail)
    assert exc_info.value.headers["X-Error-Code"].startswith("CONNECTION_PROVIDER_")


class FakeProbeAdapter:
    """Provider adapter double exposing only safe metadata and health evidence."""

    def __init__(self, evidence: ProviderHealth) -> None:
        self.metadata = SimpleNamespace(base_url="https://provider.example")
        self._evidence = evidence

    async def health(self, credential: str | None = None) -> ProviderHealth:
        """Return mocked provider evidence without logging the credential."""
        assert credential == "sk-closeout-secret-value"
        return self._evidence


class FakeProbeRegistry:
    """Registry double used to prove validation goes through an adapter."""

    def __init__(self, adapter: FakeProbeAdapter | None = None, error: Exception | None = None):
        self.adapter = adapter
        self.error = error

    def get(self, provider_name: str) -> FakeProbeAdapter:
        """Resolve the only test provider or raise its configured failure."""
        if self.error:
            raise self.error
        assert provider_name == "openai"
        assert self.adapter is not None
        return self.adapter


@pytest.mark.unit
@pytest.mark.asyncio
async def test_api_key_validation_requires_successful_provider_probe() -> None:
    """Only healthy adapter evidence yields valid API-key validation."""
    service, _ = make_service()
    registry = FakeProbeRegistry(
        FakeProbeAdapter(ProviderHealth("openai", True, "healthy"))
    )
    with patch("app.services.connection_service.build_default_registry", return_value=registry):
        result = await service._validate_api_key("openai", "sk-closeout-secret-value")

    assert result == {
        "valid": True,
        "reason": "provider_probe_succeeded",
        "evidence": {"status": "healthy"},
    }


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["provider_auth_failed", "provider_rate_limited", "provider_down"])
async def test_api_key_probe_failures_never_mark_connection_connected(reason: str) -> None:
    """401/403/429/500-class probe failures are safe negative evidence."""
    service, _ = make_service()
    registry = FakeProbeRegistry(
        FakeProbeAdapter(ProviderHealth("openai", False, reason, reason=reason))
    )
    with patch("app.services.connection_service.build_default_registry", return_value=registry):
        result = await service._validate_api_key("openai", "sk-closeout-secret-value")

    assert result["valid"] is False
    assert result["reason"] == reason


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("provider_status", [200, 401, 403, 429, 500])
async def test_api_key_validation_uses_mocked_http_transport(provider_status: int) -> None:
    """Provider adapter transport statuses become safe validation evidence."""
    async def transport(
        method: str,
        url: str,
        headers: dict[str, str],
        payload: dict[str, object],
        params: dict[str, str],
        timeout: float,
    ) -> ProviderResponse:
        assert method == "GET"
        assert url.endswith("/models")
        assert headers["Authorization"] == "Bearer sk-closeout-secret-value"
        return ProviderResponse(provider_status, {"data": []})

    metadata = ProviderMetadata(
        name="openai",
        display_name="OpenAI",
        workload=WorkloadKind.LLM,
        credential_provider=ProviderType.OPENAI,
        capabilities=("text",),
        base_url="https://api.example",
        health_path="/models",
    )
    adapter = HTTPProviderAdapter(metadata, transport=transport)
    service, _ = make_service()
    registry = FakeProbeRegistry(adapter)
    with patch("app.services.connection_service.build_default_registry", return_value=registry):
        result = await service._validate_api_key("openai", "sk-closeout-secret-value")

    assert result["valid"] is (provider_status == 200)
    assert "sk-closeout-secret-value" not in str(result)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_api_key_unconfigured_probe_is_structured() -> None:
    """An adapter without an endpoint cannot establish provider evidence."""
    service, _ = make_service()
    adapter = FakeProbeAdapter(ProviderHealth("openai", True, "healthy"))
    adapter.metadata.base_url = ""
    with patch(
        "app.services.connection_service.build_default_registry",
        return_value=FakeProbeRegistry(adapter),
    ), pytest.raises(HTTPException) as exc_info:
        await service._validate_api_key("openai", "sk-closeout-secret-value")

    assert exc_info.value.headers["X-Error-Code"] == "CONNECTION_PROVIDER_UNCONFIGURED"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_invalid_api_key_evidence_rolls_back_provisional_connection() -> None:
    """A wrong key cannot leave a connecting or connected record behind."""
    service, repository = make_service()
    repository.connection = None
    bad_key = "sk-wrong-key-secret-value"
    with patch.object(
        service,
        "_validate_api_key",
        new=AsyncMock(return_value={"valid": False, "reason": "provider_auth_failed"}),
    ), pytest.raises(HTTPException) as exc_info:
        await service.create_api_key_connection(
            provider_name="openai",
            category="ai_provider",
            ownership="workspace",
            display_name="OpenAI",
            api_key=bad_key,
            user_id=USER_A,
        )

    assert exc_info.value.headers["X-Error-Code"] == "API_KEY_INVALID"
    assert bad_key not in str(exc_info.value.detail)
    assert repository.deleted is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_api_key_probe_unsupported_is_structured() -> None:
    """Providers without an adapter fail closed instead of claiming validation."""
    service, _ = make_service()
    unsupported = ProviderError(
        "Requested provider is unsupported",
        ProviderErrorCode.UNSUPPORTED_CAPABILITY,
        "unsupported",
        status_code=422,
    )
    with patch(
        "app.services.connection_service.build_default_registry",
        return_value=FakeProbeRegistry(error=unsupported),
    ), pytest.raises(HTTPException) as exc_info:
        await service._validate_api_key("unsupported", "sk-closeout-secret-value")

    assert exc_info.value.headers["X-Error-Code"] == "PROVIDER_VALIDATION_UNSUPPORTED"
    assert "sk-closeout-secret-value" not in str(exc_info.value.detail)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_api_key_storage_uses_created_connection_id_and_only_probe_evidence_connects() -> None:
    """API-key storage namespace is the connection ID, not a token reference."""
    service, repository = make_service()
    repository.connection = None
    stored = AsyncMock(return_value=TOKEN_REF)
    discovered = AsyncMock(return_value=["chat"])
    with (
        patch.object(
            service,
            "_validate_api_key",
            new=AsyncMock(return_value={"valid": True, "reason": "provider_probe_succeeded"}),
        ),
        patch.object(service, "_store_encrypted_token", new=stored),
        patch.object(service, "_discover_capabilities", new=discovered),
    ):
        result = await service.create_api_key_connection(
            provider_name="openai",
            category="ai_provider",
            ownership="workspace",
            display_name="OpenAI",
            api_key="sk-closeout-secret-value",
            user_id=USER_A,
        )

    assert result.lifecycle_state == "connected"
    assert stored.await_args.kwargs["connection_id"] == result.id
    assert stored.await_args.kwargs["connection_id"] != TOKEN_REF
    assert result.health_status == "healthy"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_revoke_failure_does_not_mark_connection_revoked() -> None:
    """An active credential that fails revocation leaves lifecycle unchanged."""
    service, repository = make_service()
    with (
        patch(
            "app.services.connection_service.CredentialService.get_status",
            return_value=[{"status": "active"}],
        ),
        patch(
            "app.services.connection_service.CredentialService.revoke",
            return_value=False,
        ),pytest.raises(HTTPException) as exc_info
    ):
        await service.revoke_connection(CONNECTION_ID, USER_A)

    assert exc_info.value.headers["X-Error-Code"] == "CREDENTIAL_REVOKE_FAILED"
    assert repository.connection.lifecycle_state == "connected"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_health_uses_connection_id_namespace() -> None:
    """Health validation uses connection.id even when the row ref differs."""
    service, _ = make_service()
    with patch(
        "app.services.connection_service.CredentialService.validate",
        return_value={"valid": False, "reason": "revoked"},
    ) as validate:
        await service.health_check(CONNECTION_ID)

    assert validate.call_args.kwargs["environment"] == f"connection:{CONNECTION_ID}:access"
    assert str(TOKEN_REF) not in validate.call_args.kwargs["environment"]


@pytest.mark.unit
def test_credential_namespace_isolation_and_validate_after_revoke() -> None:
    """Same environment names remain isolated by tenant and connection ID."""
    connection_a = uuid4()
    connection_b = uuid4()
    created_ids: list[str] = []
    try:
        first = CredentialService.store(
            org_id=str(ORG_A),
            provider=ProviderType.OPENAI,
            secret="org-a-secret-value",
            environment=f"connection:{connection_a}:access",
            actor=str(USER_A),
        )
        second = CredentialService.store(
            org_id=str(ORG_B),
            provider=ProviderType.OPENAI,
            secret="org-b-secret-value",
            environment=f"connection:{connection_b}:access",
            actor=str(USER_A),
        )
        created_ids.extend([first["id"], second["id"]])
        assert CredentialService.validate(
            org_id=str(ORG_A),
            provider=ProviderType.OPENAI,
            environment=f"connection:{connection_a}:access",
        )["valid"]
        assert CredentialService.revoke(
            org_id=str(ORG_A),
            provider=ProviderType.OPENAI,
            environment=f"connection:{connection_a}:access",
            actor=str(USER_A),
        )
        assert not CredentialService.validate(
            org_id=str(ORG_A),
            provider=ProviderType.OPENAI,
            environment=f"connection:{connection_a}:access",
        )["valid"]
        assert CredentialService.validate(
            org_id=str(ORG_B),
            provider=ProviderType.OPENAI,
            environment=f"connection:{connection_b}:access",
        )["valid"]
    finally:
        for record_id in created_ids:
            _store.pop(record_id, None)

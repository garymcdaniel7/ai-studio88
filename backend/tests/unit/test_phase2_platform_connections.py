"""Phase 2 Group 9 connection, capability, and policy tests.

All provider and persistence calls are mocked. These tests do not contact
Fanvue or any other external provider.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from fastapi import HTTPException, status
from starlette.requests import Request

from app.core.dependencies import get_current_user_id
from app.services.connection_service import ConnectionService
from app.services.platform_registry import (
    PlatformAvailability,
    list_platform_definitions,
)
from app.services.publishing_policy_service import (
    PlatformUnavailableError,
    PublishPolicyInput,
    evaluate_publish_policy,
)
from backend.credentials import CredentialService, ProviderType, _store

ORG_A = UUID("11111111-1111-1111-1111-111111111111")
ORG_B = UUID("22222222-2222-2222-2222-222222222222")
USER_A = UUID("33333333-3333-3333-3333-333333333333")
CONNECTION_ID = UUID("44444444-4444-4444-4444-444444444444")
TOKEN_REF = UUID("55555555-5555-5555-5555-555555555555")


class FakeConnectionRepository:
    """In-memory repository double that preserves tenant-scoped behavior."""

    def __init__(self, org_id: UUID, connection: SimpleNamespace | None = None) -> None:
        self.org_id = org_id
        self.connection = connection

    async def find_by_provider(self, **_: object) -> SimpleNamespace | None:
        """Return the current connection for duplicate checks."""
        if self.connection and self.connection.lifecycle_state not in {"disconnected", "revoked"}:
            return self.connection
        return None

    async def create(self, **kwargs: object) -> SimpleNamespace:
        """Create a tenant-owned fake connection."""
        self.connection = SimpleNamespace(
            id=CONNECTION_ID,
            org_id=self.org_id,
            provider_name=kwargs["provider_name"],
            lifecycle_state=kwargs["lifecycle_state"],
            oauth_token_ref=kwargs.get("oauth_token_ref"),
            capabilities=kwargs.get("capabilities", []),
            allowed_roles=kwargs.get("allowed_roles", ["owner", "admin", "editor"]),
            tool_policy=kwargs.get("tool_policy", {}),
            health_status=kwargs.get("health_status"),
            last_health_check_at=kwargs.get("last_health_check_at"),
            ownership=kwargs.get("ownership"),
            category=kwargs.get("category"),
            display_name=kwargs.get("display_name"),
        )
        return self.connection

    async def get_by_id(self, connection_id: UUID) -> SimpleNamespace:
        """Return only this repository's tenant-owned connection."""
        if self.connection is None or self.connection.id != connection_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
        return self.connection

    async def update_fields(self, connection_id: UUID, **kwargs: object) -> SimpleNamespace:
        """Update the fake connection after tenant lookup."""
        connection = await self.get_by_id(connection_id)
        for key, value in kwargs.items():
            setattr(connection, key, value)
        return connection

    async def update_lifecycle_state(self, connection_id: UUID, new_state: str) -> SimpleNamespace:
        """Update lifecycle state after tenant lookup."""
        connection = await self.get_by_id(connection_id)
        connection.lifecycle_state = new_state
        return connection

    async def update_health(self, connection_id: UUID, health_status: str) -> SimpleNamespace:
        """Update health status after tenant lookup."""
        connection = await self.get_by_id(connection_id)
        connection.health_status = health_status
        connection.last_health_check_at = datetime.now(UTC)
        return connection


def make_service(
    org_id: UUID = ORG_A,
    *,
    lifecycle_state: str = "connected",
    provider_name: str = "fanvue",
    capabilities: list[str] | None = None,
    allowed_roles: list[str] | None = None,
    tool_policy: dict | None = None,
    oauth_token_ref: UUID | None = TOKEN_REF,
) -> tuple[ConnectionService, FakeConnectionRepository]:
    """Build a service without opening a database connection."""
    connection = SimpleNamespace(
        id=CONNECTION_ID,
        org_id=org_id,
        provider_name=provider_name,
        lifecycle_state=lifecycle_state,
        oauth_token_ref=oauth_token_ref,
        capabilities=capabilities or ["publish_media"],
        allowed_roles=allowed_roles or ["owner", "admin", "editor"],
        tool_policy=tool_policy or {},
        health_status="healthy",
        last_health_check_at=None,
        ownership="workspace",
        category="social",
        display_name="Fanvue",
    )
    repository = FakeConnectionRepository(org_id, connection)
    service = object.__new__(ConnectionService)
    service._org_id = org_id
    service._repo = repository
    return service, repository


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fanvue_connect_callback_is_state_bound_and_secret_free() -> None:
    """Fanvue callback binds state to tenant/connection and returns a reference only."""
    service = ConnectionService.__new__(ConnectionService)
    service._org_id = ORG_A
    repository = FakeConnectionRepository(ORG_A)
    service._repo = repository

    with patch(
        "app.services.connection_service.get_settings",
        return_value=SimpleNamespace(
            fanvue_client_id="fanvue-client-id",
            fanvue_client_secret="fanvue-client-secret",
            api_base_url="http://localhost:8000",
            provider_timeout_seconds=5.0,
        ),
    ):
        initiated = await service.initiate_oauth(
            provider_name="fanvue",
            category="social",
            ownership="workspace",
            display_name="Fanvue Creator",
            user_id=USER_A,
        )
    assert "client_secret" not in initiated["redirect_url"]
    assert "access_token" not in initiated

    service._exchange_oauth_code = AsyncMock(  # type: ignore[method-assign]
        return_value={"access_token": "provider-secret", "refresh_token": "refresh-secret"}
    )
    service._store_encrypted_token = AsyncMock(return_value=TOKEN_REF)  # type: ignore[method-assign]
    service._discover_capabilities = AsyncMock(return_value=["publish_media"])  # type: ignore[method-assign]

    connected = await service.complete_oauth_callback(
        CONNECTION_ID,
        "one-time-code",
        state=initiated["state"],
    )
    assert connected.oauth_token_ref == TOKEN_REF
    assert connected.lifecycle_state == "connected"
    assert "provider-secret" not in repr(connected)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_oauth_state_mismatch_returns_409() -> None:
    """A callback with a state from another flow is rejected."""
    service, _ = make_service(org_id=ORG_A, lifecycle_state="connecting", oauth_token_ref=None)
    with pytest.raises(HTTPException) as exc_info:
        await service.complete_oauth_callback(CONNECTION_ID, "code", state="wrong-state")
    assert exc_info.value.status_code == status.HTTP_409_CONFLICT


@pytest.mark.unit
@pytest.mark.asyncio
async def test_health_marks_expired_credential_for_reauthorization() -> None:
    """An expired encrypted credential transitions a connection to reauth_required."""
    service, repository = make_service()
    with patch(
        "app.services.connection_service.CredentialService.validate",
        return_value={"valid": False, "reason": "expired"},
    ):
        result = await service.health_check(CONNECTION_ID)
    assert result.health_status == "auth_expired"
    assert result.lifecycle_state == "reauth_required"
    assert repository.connection.org_id == ORG_A


@pytest.mark.unit
@pytest.mark.asyncio
async def test_revoke_wipes_credential_access_without_exposing_secret() -> None:
    """Revocation calls both encrypted namespaces and retains revoked state."""
    service, repository = make_service()
    with patch(
        "app.services.connection_service.CredentialService.revoke",
        return_value=True,
    ) as revoke:
        result = await service.revoke_connection(CONNECTION_ID, USER_A)
    assert result.lifecycle_state == "revoked"
    assert revoke.call_count == 2
    assert all("secret" not in str(call.kwargs) for call in revoke.call_args_list)
    assert repository.connection.org_id == ORG_A


@pytest.mark.unit
@pytest.mark.asyncio
async def test_role_denial_returns_403_before_policy_evaluation() -> None:
    """Viewer access is denied by the connection role policy."""
    service, _ = make_service(allowed_roles=["admin", "owner"])
    with pytest.raises(HTTPException) as exc_info:
        await service.check_publish_policy(
            CONNECTION_ID,
            "viewer",
            PublishPolicyInput(),
        )
    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fanvue_policy_denial_returns_422_with_missing_gates() -> None:
    """Fanvue requires disclosure, age, consent, moderation, and confirmation gates."""
    service, _ = make_service()
    with pytest.raises(HTTPException) as exc_info:
        await service.check_publish_policy(
            CONNECTION_ID,
            "editor",
            PublishPolicyInput(),
        )
    assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "missing_requirements" in str(exc_info.value.detail)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cross_tenant_connection_lookup_returns_404() -> None:
    """Tenant B cannot use Tenant A's connection identifier."""
    service, repository = make_service(org_id=ORG_B)
    repository.connection = None
    with pytest.raises(HTTPException) as exc_info:
        await service.check_publish_policy(CONNECTION_ID, "owner", PublishPolicyInput())
    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.unit
def test_platform_registry_keeps_unverified_integrations_disabled() -> None:
    """Only the verified Fanvue rollout is enabled by default."""
    platforms = {item["platform"]: item for item in list_platform_definitions()}
    assert platforms["fanvue"]["enabled"] is True
    for platform in ("onlyfans", "loyalfans", "instagram", "tiktok", "youtube"):
        assert platforms[platform]["availability"] == PlatformAvailability.COMING_SOON
        assert platforms[platform]["enabled"] is False
        assert platforms[platform]["verified"] is False


@pytest.mark.unit
def test_policy_engine_rejects_unverified_platform_and_accepts_complete_fanvue_evidence() -> None:
    """Capability metadata cannot be mistaken for platform policy approval."""
    with pytest.raises(PlatformUnavailableError):
        evaluate_publish_policy("onlyfans", PublishPolicyInput())

    decision = evaluate_publish_policy(
        "fanvue",
        PublishPolicyInput(
            ai_label_present=True,
            watermark_present=True,
            caption_disclosure_present=True,
            age_verified=True,
            consent_verified=True,
            identity_verified=True,
            moderation_passed=True,
            publish_confirmed=True,
        ),
    )
    assert decision.allowed is True
    assert decision.missing_requirements == ()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_missing_bearer_token_remains_401() -> None:
    """The canonical auth dependency rejects unauthenticated connection callers."""
    request = Request({"type": "http", "method": "GET", "path": "/api/v1/connections", "headers": []})
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_id(request)
    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.unit
@pytest.mark.asyncio
async def test_credential_reference_storage_never_returns_raw_secret() -> None:
    """OAuth material is encrypted and masked at the credential boundary."""
    service, _ = make_service()
    secret = "fanvue-access-secret-not-for-output"
    reference = await service._store_encrypted_token(  # noqa: SLF001
        {"access_token": secret},
        provider_name="fanvue",
        connection_id=CONNECTION_ID,
        actor=str(USER_A),
    )
    status_rows = CredentialService.get_status(
        org_id=str(ORG_A),
        provider=ProviderType.FANVUE,
        environment=f"connection:{CONNECTION_ID}:access",
    )
    try:
        assert isinstance(reference, UUID)
        assert status_rows
        assert secret not in str(status_rows)
        assert secret not in str(CredentialService.get_status(org_id=str(ORG_A)))
        record = next(record for record in _store.values() if record.org_id == str(ORG_A))
        assert secret not in record.encrypted_secret
    finally:
        for record_id in [
            record_id for record_id, record in _store.items() if record.org_id == str(ORG_A)
        ]:
            del _store[record_id]

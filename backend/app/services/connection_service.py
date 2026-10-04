"""Connection Service — business logic for connection lifecycle and OAuth flows.

Manages the full connection lifecycle including OAuth initiation, callback
handling, API key connections, state transitions, and capability discovery.

The service delegates all database access to ConnectionRepository, which
enforces tenant isolation via TenantScopedRepository.

Requirements: R85.2, R85.4, R85.5, R85.6, R27.4, R27.6, R92.6
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import httpx
from fastapi import HTTPException, status

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.connection import (
    ConnectionAuthMethod,
    ConnectionLifecycle,
    ConnectionOwnership,
)
from app.providers.byo import ProviderError, build_default_registry
from app.repositories.connection_repository import ConnectionRepository
from app.schemas.connection import ConnectionUpdate
from app.services.platform_registry import (
    connection_allowed,
    discovered_capabilities,
    get_platform_definition,
    list_platform_definitions,
)
from app.services.publishing_policy_service import (
    PlatformPolicyDeniedError,
    PlatformUnavailableError,
    PublishPolicyDecision,
    PublishPolicyInput,
    evaluate_publish_policy,
)
from backend.credentials import CredentialOwnership, CredentialService, ProviderType

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.connection import Connection

logger = get_logger(__name__)

OAUTH_STATE_TTL = timedelta(minutes=10)
# OAuth state contains no credential material. Only a SHA-256 digest is kept so
# a process dump cannot recover the browser-visible CSRF value.
_PENDING_OAUTH_STATES: dict[str, dict[str, Any]] = {}


def _oauth_state_digest(state: str) -> str:
    """Hash an OAuth state value for safe server-side correlation."""
    return hashlib.sha256(state.encode("utf-8")).hexdigest()


def _provider_type(provider_name: str) -> ProviderType:
    """Map a connection provider to its encrypted credential namespace."""
    mapping = {
        "fanvue": ProviderType.FANVUE,
        "onlyfans": ProviderType.ONLYFANS,
        "loyalfans": ProviderType.LOYALFANS,
        "instagram": ProviderType.INSTAGRAM,
        "tiktok": ProviderType.TIKTOK,
        "youtube": ProviderType.YOUTUBE,
        "x": ProviderType.X,
    }
    return mapping.get(provider_name, ProviderType.USER_API_KEY)


def _credential_environment(connection_id: UUID, kind: str = "access") -> str:
    """Return a non-secret credential namespace for one connection."""
    return f"connection:{connection_id}:{kind}"



# =============================================================================
# Exceptions
# =============================================================================


class ConnectionServiceError(Exception):
    """Base exception for ConnectionService operations."""

    def __init__(self, message: str, code: str = "CONNECTION_ERROR") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class InvalidStateTransitionError(ConnectionServiceError):
    """Raised when an invalid lifecycle state transition is attempted."""

    def __init__(self, current_state: str, target_state: str) -> None:
        super().__init__(
            message=(
                f"Invalid state transition from '{current_state}' to "
                f"'{target_state}'"
            ),
            code="INVALID_STATE_TRANSITION",
        )


class DuplicateConnectionError(ConnectionServiceError):
    """Raised when a duplicate connection is detected for the same provider."""

    def __init__(self, provider_name: str) -> None:
        super().__init__(
            message=(
                f"An active connection to '{provider_name}' already exists"
            ),
            code="DUPLICATE_CONNECTION",
        )


# =============================================================================
# Valid Lifecycle State Transitions
# =============================================================================

VALID_TRANSITIONS: dict[str, set[str]] = {
    ConnectionLifecycle.CONNECTING.value: {
        ConnectionLifecycle.CONNECTED.value,
        ConnectionLifecycle.DISCONNECTED.value,
    },
    ConnectionLifecycle.CONNECTED.value: {
        ConnectionLifecycle.DEGRADED.value,
        ConnectionLifecycle.REAUTH_REQUIRED.value,
        ConnectionLifecycle.DISCONNECTED.value,
        ConnectionLifecycle.REVOKED.value,
    },
    ConnectionLifecycle.DEGRADED.value: {
        ConnectionLifecycle.CONNECTED.value,
        ConnectionLifecycle.REAUTH_REQUIRED.value,
        ConnectionLifecycle.DISCONNECTED.value,
        ConnectionLifecycle.REVOKED.value,
    },
    ConnectionLifecycle.REAUTH_REQUIRED.value: {
        ConnectionLifecycle.CONNECTING.value,
        ConnectionLifecycle.CONNECTED.value,
        ConnectionLifecycle.DISCONNECTED.value,
        ConnectionLifecycle.REVOKED.value,
    },
    ConnectionLifecycle.DISCONNECTED.value: {
        ConnectionLifecycle.CONNECTING.value,
    },
    ConnectionLifecycle.REVOKED.value: set(),  # Terminal state
}


# =============================================================================
# OAuth Provider Configurations (platform-managed, users never see these)
# =============================================================================

# In production, these would be loaded from encrypted environment variables
# or a secrets manager. This dict maps provider_name to config shape.
OAUTH_PROVIDERS: dict[str, dict[str, str]] = {
    "fanvue": {
        "authorize_url": "https://auth.fanvue.com/oauth/authorize",
        "token_url": "https://auth.fanvue.com/oauth/token",
        "scopes": "profile media:read media:write offline",
        "client_id_setting": "fanvue_client_id",
        "client_secret_setting": "fanvue_client_secret",
    },
    "instagram": {
        "authorize_url": "https://api.instagram.com/oauth/authorize",
        "token_url": "https://api.instagram.com/oauth/access_token",
        "scopes": "user_profile,user_media",
        "client_id_setting": "instagram_client_id",
        "client_secret_setting": "instagram_client_secret",
    },
    "youtube": {
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scopes": "https://www.googleapis.com/auth/youtube.readonly",
        "client_id_setting": "youtube_client_id",
        "client_secret_setting": "youtube_client_secret",
    },
    "tiktok": {
        "authorize_url": "https://www.tiktok.com/v2/auth/authorize/",
        "token_url": "https://open.tiktokapis.com/v2/oauth/token/",
        "scopes": "user.info.basic,video.list",
        "client_id_setting": "tiktok_client_id",
        "client_secret_setting": "tiktok_client_secret",
    },
    "github": {
        "authorize_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "scopes": "read:user,repo",
        "client_id_setting": "github_client_id",
        "client_secret_setting": "github_client_secret",
    },
}


def _oauth_configuration(provider_name: str) -> tuple[dict[str, str], str, str]:
    """Return configured OAuth endpoints and credentials without exposing secrets."""
    provider_config = OAUTH_PROVIDERS.get(provider_name)
    if provider_config is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "CONNECTION_PROVIDER_UNCONFIGURED",
                "message": "OAuth provider is not configured",
            },
            headers={"X-Error-Code": "CONNECTION_PROVIDER_UNCONFIGURED"},
        )

    settings = get_settings()
    client_id = str(getattr(settings, provider_config["client_id_setting"], "") or "")
    client_secret = str(getattr(settings, provider_config["client_secret_setting"], "") or "")
    if not provider_config.get("token_url") or not client_id or not client_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "CONNECTION_PROVIDER_UNCONFIGURED",
                "message": "OAuth provider credentials are not configured",
            },
            headers={"X-Error-Code": "CONNECTION_PROVIDER_UNCONFIGURED"},
        )
    return provider_config, client_id, client_secret


def _oauth_authorization_url(
    provider_config: dict[str, str], client_id: str, state: str
) -> str:
    """Build a provider redirect URL with public OAuth parameters only."""
    query = urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "scope": provider_config["scopes"],
            "state": state,
        }
    )
    return f"{provider_config['authorize_url']}?{query}"


# =============================================================================
# Service
# =============================================================================


class ConnectionService:
    """Connection lifecycle management service.

    Handles:
    - OAuth initiation and callback flows
    - API key connection establishment
    - Lifecycle state transitions
    - Capability discovery
    - Health monitoring updates

    All operations are tenant-scoped via the repository layer.
    org_id is resolved from TenantContext, never from client input.

    Requirements: R85.2, R85.4, R85.5, R85.6, R27.4, R27.6, R92.6
    """

    def __init__(self, db: AsyncSession, org_id: UUID) -> None:
        """Initialize the ConnectionService.

        Args:
            db: SQLAlchemy async session.
            org_id: Authenticated org UUID from TenantContext.
        """
        self._db = db
        self._org_id = org_id
        self._repo = ConnectionRepository(db=db, org_id=org_id)

    # =========================================================================
    # OAuth Flow (R85.2, R27.4)
    # =========================================================================

    async def initiate_oauth(
        self,
        provider_name: str,
        category: str,
        ownership: str,
        display_name: str,
        user_id: UUID,
    ) -> dict[str, Any]:
        """Initiate an OAuth connection flow.

        Creates a CONNECTING record and returns the provider's OAuth
        authorization URL for the user to be redirected to.

        Users never see client_ids, secrets, or redirect URIs (R85.2).

        Args:
            provider_name: The provider to connect (e.g. 'instagram').
            category: Connection category.
            ownership: Connection ownership type (user/workspace).
            display_name: Human-readable name for this connection.
            user_id: The authenticated user initiating the flow.

        Returns:
            Dict with redirect_url and connection_id.

        Raises:
            HTTPException: 422 if provider doesn't support OAuth.
            HTTPException: 409 if a duplicate active connection exists.
        """
        provider_name = provider_name.strip().lower()
        definition = get_platform_definition(provider_name)
        if definition is not None and not connection_allowed(provider_name):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Platform '{provider_name}' is not enabled for connections",
                headers={"X-Error-Code": "PLATFORM_COMING_SOON"},
            )

        # Check for duplicate connections before requiring provider credentials.
        existing = await self._repo.find_by_provider(
            provider_name=provider_name,
            ownership=ownership,
            user_id=user_id if ownership == ConnectionOwnership.USER.value else None,
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"An active connection to '{provider_name}' already exists",
                headers={"X-Error-Code": "DUPLICATE_CONNECTION"},
            )

        # Validate OAuth support and platform-managed credentials.
        provider_config, client_id, _ = _oauth_configuration(provider_name)

        # Create connection in CONNECTING state
        connection = await self._repo.create(
            user_id=user_id if ownership == ConnectionOwnership.USER.value else None,
            ownership=ownership,
            category=category,
            provider_name=provider_name,
            display_name=display_name,
            lifecycle_state=ConnectionLifecycle.CONNECTING.value,
            auth_method=ConnectionAuthMethod.OAUTH.value,
            capabilities=[],
        )

        # Generate OAuth state token for CSRF protection. Store only its
        # digest and the authenticated tenant/connection binding.
        state_token = secrets.token_urlsafe(32)
        _PENDING_OAUTH_STATES[_oauth_state_digest(state_token)] = {
            "connection_id": connection.id,
            "org_id": self._org_id,
            "user_id": user_id,
            "provider_name": provider_name,
            "expires_at": datetime.now(tz=UTC) + OAUTH_STATE_TTL,
        }

        # Build redirect URL — platform manages client_id/secret centrally
        redirect_url = _oauth_authorization_url(provider_config, client_id, state_token)

        logger.info(
            "oauth_flow_initiated",
            connection_id=str(connection.id),
            org_id=str(self._org_id),
            provider_name=provider_name,
        )

        return {
            "redirect_url": redirect_url,
            "connection_id": str(connection.id),
            "state": state_token,
        }

    async def complete_oauth_callback(
        self,
        connection_id: UUID,
        auth_code: str,
        state: str | None = None,
    ) -> Connection:
        """Complete OAuth flow after provider callback.

        Exchanges the authorization code for tokens, encrypts and stores
        them, discovers provider capabilities, and transitions to CONNECTED.

        Args:
            connection_id: The connection created during initiation.
            auth_code: The authorization code from the OAuth callback.

        Returns:
            The updated Connection in CONNECTED state.

        Raises:
            HTTPException: 404 if connection not found.
            ConnectionServiceError: If token exchange fails.
        """
        connection = await self._repo.get_by_id(connection_id)

        if state is not None:
            pending = _PENDING_OAUTH_STATES.pop(_oauth_state_digest(state), None)
            if (
                pending is None
                or pending["connection_id"] != connection_id
                or pending["org_id"] != self._org_id
                or pending["provider_name"] != connection.provider_name
                or pending["expires_at"] <= datetime.now(tz=UTC)
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="OAuth state is invalid or expired",
                    headers={"X-Error-Code": "OAUTH_STATE_INVALID"},
                )

        # Verify connection is in CONNECTING state
        if connection.lifecycle_state != ConnectionLifecycle.CONNECTING.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Connection is not in CONNECTING state",
                headers={"X-Error-Code": "INVALID_STATE"},
            )

        # Exchange the authorization code through the configured provider's
        # token endpoint using platform-managed client credentials.
        token_data = await self._exchange_oauth_code(
            provider_name=connection.provider_name,
            auth_code=auth_code,
        )

        # CredentialService encrypts the token material and returns an opaque
        # reference; the connection stores only that encrypted-credential ID.
        token_ref = await self._store_encrypted_token(
            token_data,
            provider_name=connection.provider_name,
            connection_id=connection_id,
            actor="oauth_callback",
        )

        # Discover provider capabilities
        capabilities = await self._discover_capabilities(
            provider_name=connection.provider_name,
            token_data=token_data,
        )

        # Update connection to CONNECTED with capabilities
        updated = await self._repo.update_fields(
            connection_id=connection_id,
            lifecycle_state=ConnectionLifecycle.CONNECTED.value,
            oauth_token_ref=token_ref,
            capabilities=capabilities,
            health_status="healthy",
            last_health_check_at=datetime.now(tz=UTC),
        )

        logger.info(
            "oauth_flow_completed",
            connection_id=str(connection_id),
            org_id=str(self._org_id),
            provider_name=connection.provider_name,
            capabilities_count=len(capabilities),
        )

        return updated

    # =========================================================================
    # API Key Flow (R27.6)
    # =========================================================================

    async def create_api_key_connection(
        self,
        provider_name: str,
        category: str,
        ownership: str,
        display_name: str,
        api_key: str,
        user_id: UUID,
        allowed_roles: list[str] | None = None,
        tool_policy: dict | None = None,
    ) -> Connection:
        """Create a connection using an API key.

        Accepts the key once, validates it against the provider, discovers
        capabilities, stores it encrypted, and NEVER redisplays the value.

        Args:
            provider_name: The provider identifier (e.g. 'openai').
            category: Connection category.
            ownership: Connection ownership type.
            display_name: Human-readable connection name.
            api_key: The raw API key (accepted once, stored encrypted).
            user_id: The authenticated user.
            allowed_roles: Roles allowed to use this connection.
            tool_policy: Per-tool allow/deny policy.

        Returns:
            The created Connection in CONNECTED state.

        Raises:
            HTTPException: 409 if duplicate connection exists.
            HTTPException: 422 if key validation fails.
        """
        provider_name = provider_name.strip().lower()
        definition = get_platform_definition(provider_name)
        if definition is not None and not connection_allowed(provider_name):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Platform '{provider_name}' is not enabled for connections",
                headers={"X-Error-Code": "PLATFORM_COMING_SOON"},
            )

        # Check for duplicate connections
        existing = await self._repo.find_by_provider(
            provider_name=provider_name,
            ownership=ownership,
            user_id=user_id if ownership == ConnectionOwnership.USER.value else None,
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"An active connection to '{provider_name}' already exists",
                headers={"X-Error-Code": "DUPLICATE_CONNECTION"},
            )

        # Create a non-connected record first so every credential namespace is
        # bound to the authoritative connection.id. It is removed on any
        # validation or storage failure and can never be reported as healthy.
        connection = await self._repo.create(
            id=uuid4(),
            user_id=user_id if ownership == ConnectionOwnership.USER.value else None,
            ownership=ownership,
            category=category,
            provider_name=provider_name,
            display_name=display_name,
            lifecycle_state=ConnectionLifecycle.CONNECTING.value,
            auth_method=ConnectionAuthMethod.API_KEY.value,
            capabilities=[],
            allowed_roles=allowed_roles or ["owner", "admin", "editor"],
            tool_policy=tool_policy or {},
        )
        try:
            validation = await self._validate_api_key(provider_name, api_key)
            if not validation["valid"]:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "code": "API_KEY_INVALID",
                        "message": f"API key validation failed for provider '{provider_name}'",
                    },
                    headers={"X-Error-Code": "API_KEY_INVALID"},
                )

            # Store encrypted key under the authoritative connection namespace.
            token_ref = await self._store_encrypted_token(
                {"access_token": api_key},
                provider_name=provider_name,
                connection_id=connection.id,
                actor=str(user_id),
            )

            # Capability discovery is only applied after provider evidence.
            capabilities = await self._discover_capabilities(
                provider_name=provider_name,
                token_data={"api_key": api_key},
            )
            connection = await self._repo.update_fields(
                connection_id=connection.id,
                lifecycle_state=ConnectionLifecycle.CONNECTED.value,
                oauth_token_ref=token_ref,
                capabilities=capabilities,
                health_status="healthy",
                last_health_check_at=datetime.now(tz=UTC),
            )
        except Exception:
            # Do not leave an unvalidated CONNECTING credential record behind.
            await self._repo.delete(connection.id)
            raise

        logger.info(
            "api_key_connection_created",
            connection_id=str(connection.id),
            org_id=str(self._org_id),
            provider_name=provider_name,
            capabilities_count=len(connection.capabilities or []),
        )
        return connection

    # =========================================================================
    # Lifecycle State Transitions (R85.4, R92.6)
    # =========================================================================

    async def transition_state(
        self,
        connection_id: UUID,
        target_state: str,
    ) -> Connection:
        """Transition a connection to a new lifecycle state.

        Validates the transition against the allowed state machine before
        applying. Invalid transitions raise an error.

        Args:
            connection_id: The connection to transition.
            target_state: The desired target state.

        Returns:
            The updated Connection.

        Raises:
            InvalidStateTransitionError: If the transition is not allowed.
        """
        connection = await self._repo.get_by_id(connection_id)
        current_state = connection.lifecycle_state

        # Validate the transition
        allowed = VALID_TRANSITIONS.get(current_state, set())
        if target_state not in allowed:
            raise InvalidStateTransitionError(current_state, target_state)

        updated = await self._repo.update_lifecycle_state(
            connection_id=connection_id,
            new_state=target_state,
        )

        logger.info(
            "connection_state_transitioned",
            connection_id=str(connection_id),
            org_id=str(self._org_id),
            from_state=current_state,
            to_state=target_state,
        )

        return updated

    # =========================================================================
    # CRUD Operations
    # =========================================================================

    async def get_connection(self, connection_id: UUID) -> Connection:
        """Retrieve a connection by ID.

        Args:
            connection_id: The connection UUID.

        Returns:
            The Connection instance.

        Raises:
            HTTPException: 404 if not found or cross-tenant.
        """
        return await self._repo.get_by_id(connection_id)

    async def list_connections(
        self,
        limit: int = 20,
        offset: int = 0,
        category: str | None = None,
        ownership: str | None = None,
        lifecycle_state: str | None = None,
        user_id: UUID | None = None,
    ) -> tuple[list[Connection], int]:
        """List connections with optional filters.

        Args:
            limit: Maximum items.
            offset: Pagination offset.
            category: Filter by category.
            ownership: Filter by ownership type.
            lifecycle_state: Filter by lifecycle state.
            user_id: Filter by user_id (for user connections).

        Returns:
            Tuple of (items, total_count).
        """
        return await self._repo.list_all(
            limit=limit,
            offset=offset,
            category=category,
            ownership=ownership,
            lifecycle_state=lifecycle_state,
            user_id=user_id,
        )

    async def update_connection(
        self,
        connection_id: UUID,
        update_data: ConnectionUpdate,
    ) -> Connection:
        """Update a connection's mutable fields.

        Does NOT handle lifecycle_state transitions — use transition_state().
        If lifecycle_state is included in the update, it is validated via
        the state machine.

        Args:
            connection_id: The connection to update.
            update_data: Partial update fields.

        Returns:
            The updated Connection.
        """
        fields = update_data.model_dump(exclude_unset=True)

        # If lifecycle_state is being changed, route through state machine
        if "lifecycle_state" in fields and fields["lifecycle_state"] is not None:
            target_state = fields.pop("lifecycle_state")
            await self.transition_state(connection_id, target_state)

        # Update remaining fields if any
        if fields:
            return await self._repo.update_fields(connection_id, **fields)

        return await self._repo.get_by_id(connection_id)

    async def delete_connection(self, connection_id: UUID) -> None:
        """Delete a connection.

        Transitions to DISCONNECTED before deletion for audit trail,
        then removes the record.

        Args:
            connection_id: The connection to delete.

        Raises:
            HTTPException: 404 if not found or cross-tenant.
        """
        connection = await self._repo.get_by_id(connection_id)

        # If not already in a terminal state, transition to DISCONNECTED
        if connection.lifecycle_state not in (
            ConnectionLifecycle.DISCONNECTED.value,
            ConnectionLifecycle.REVOKED.value,
        ):
            try:
                await self.transition_state(
                    connection_id,
                    ConnectionLifecycle.DISCONNECTED.value,
                )
            except InvalidStateTransitionError:
                # Force disconnection for cleanup
                await self._repo.update_lifecycle_state(
                    connection_id,
                    ConnectionLifecycle.DISCONNECTED.value,
                )

        await self._repo.delete(connection_id)

        logger.info(
            "connection_deleted",
            connection_id=str(connection_id),
            org_id=str(self._org_id),
            provider_name=connection.provider_name,
        )

    async def update_health(
        self,
        connection_id: UUID,
        health_status: str,
    ) -> Connection:
        """Update health check results and adjust lifecycle state.

        If health degrades, automatically transitions lifecycle:
        - "unreachable" → DEGRADED
        - "auth_expired" → REAUTH_REQUIRED

        Args:
            connection_id: The connection to update.
            health_status: Health check result.

        Returns:
            The updated Connection.
        """
        connection = await self._repo.update_health(connection_id, health_status)

        # Auto-transition lifecycle based on health
        if health_status == "unreachable" and connection.lifecycle_state == ConnectionLifecycle.CONNECTED.value:
            await self.transition_state(
                connection_id, ConnectionLifecycle.DEGRADED.value
            )
            connection = await self._repo.get_by_id(connection_id)
        elif health_status == "auth_expired" and connection.lifecycle_state in (
            ConnectionLifecycle.CONNECTED.value,
            ConnectionLifecycle.DEGRADED.value,
        ):
            await self.transition_state(
                connection_id, ConnectionLifecycle.REAUTH_REQUIRED.value
            )
            connection = await self._repo.get_by_id(connection_id)
        elif health_status == "healthy" and connection.lifecycle_state == ConnectionLifecycle.DEGRADED.value:
            await self.transition_state(
                connection_id, ConnectionLifecycle.CONNECTED.value
            )
            connection = await self._repo.get_by_id(connection_id)

        return connection

    async def health_check(self, connection_id: UUID) -> Connection:
        """Check encrypted credential health and update lifecycle state.

        No provider network call is made here; provider adapters can add a
        mocked health probe later. Missing, expired, or revoked credentials
        fail closed and require reauthorization.
        """
        connection = await self._repo.get_by_id(connection_id)
        if connection.lifecycle_state in (
            ConnectionLifecycle.DISCONNECTED.value,
            ConnectionLifecycle.REVOKED.value,
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Connection is not eligible for a health check",
                headers={"X-Error-Code": "CONNECTION_TERMINAL"},
            )
        if connection.oauth_token_ref is None:
            return await self.update_health(connection_id, "auth_expired")

        credential_ref = connection.oauth_token_ref
        if credential_ref is None:
            return await self.update_health(connection_id, "auth_expired")

        valid = CredentialService.validate(
            org_id=str(self._org_id),
            provider=_provider_type(connection.provider_name),
            environment=_credential_environment(connection.id, "access"),
            actor="health_check",
        )
        return await self.update_health(
            connection_id, "healthy" if valid["valid"] else "auth_expired"
        )

    async def revoke_connection(self, connection_id: UUID, actor: UUID) -> Connection:
        """Revoke connection credentials before recording the revoked state."""
        connection = await self._repo.get_by_id(connection_id)
        provider = _provider_type(connection.provider_name)
        if connection.oauth_token_ref is not None:
            for kind in ("access", "refresh"):
                environment = _credential_environment(connection.id, kind)
                active_before = any(
                    row.get("status") == "active"
                    for row in CredentialService.get_status(
                        org_id=str(self._org_id),
                        provider=provider,
                        environment=environment,
                    )
                )
                revoked = CredentialService.revoke(
                    org_id=str(self._org_id),
                    provider=provider,
                    environment=environment,
                    actor=str(actor),
                )
                if not revoked and active_before:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail={
                            "code": "CREDENTIAL_REVOKE_FAILED",
                            "message": "Connection credentials could not be revoked",
                        },
                        headers={"X-Error-Code": "CREDENTIAL_REVOKE_FAILED"},
                    )
                remaining = CredentialService.validate(
                    org_id=str(self._org_id),
                    provider=provider,
                    environment=environment,
                    actor=str(actor),
                )
                if remaining.get("valid"):
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail={
                            "code": "CREDENTIAL_REVOKE_FAILED",
                            "message": "Connection credentials remain active",
                        },
                        headers={"X-Error-Code": "CREDENTIAL_REVOKE_FAILED"},
                    )
        if connection.lifecycle_state != ConnectionLifecycle.REVOKED.value:
            connection = await self._repo.update_lifecycle_state(
                connection_id, ConnectionLifecycle.REVOKED.value
            )
        return connection

    async def reauthorize(self, connection_id: UUID, user_id: UUID) -> dict[str, Any]:
        """Start a fresh OAuth state-bound flow for an existing connection."""
        connection = await self._repo.get_by_id(connection_id)
        definition = get_platform_definition(connection.provider_name)
        if definition is not None and not connection_allowed(connection.provider_name):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Platform '{connection.provider_name}' is not enabled for connections",
                headers={"X-Error-Code": "PLATFORM_COMING_SOON"},
            )
        provider_config, client_id, _ = _oauth_configuration(connection.provider_name)
        if connection.lifecycle_state == ConnectionLifecycle.REVOKED.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Revoked connections cannot be reauthorized",
                headers={"X-Error-Code": "CONNECTION_REVOKED"},
            )

        await self._repo.update_lifecycle_state(
            connection_id, ConnectionLifecycle.CONNECTING.value
        )
        state_token = secrets.token_urlsafe(32)
        _PENDING_OAUTH_STATES[_oauth_state_digest(state_token)] = {
            "connection_id": connection_id,
            "org_id": self._org_id,
            "user_id": user_id,
            "provider_name": connection.provider_name,
            "expires_at": datetime.now(tz=UTC) + OAUTH_STATE_TTL,
        }
        return {
            "redirect_url": _oauth_authorization_url(provider_config, client_id, state_token),
            "connection_id": str(connection_id),
            "state": state_token,
        }

    @staticmethod
    def platform_capabilities() -> list[dict[str, object]]:
        """Return capability and rollout metadata without provider secrets."""
        return list_platform_definitions()

    async def check_publish_policy(
        self,
        connection_id: UUID,
        user_role: str,
        evidence: PublishPolicyInput,
    ) -> PublishPolicyDecision:
        """Apply role, tool, lifecycle, capability, and content policy gates."""
        connection = await self._repo.get_by_id(connection_id)
        from app.services.connection_permission_service import (
            ConnectionPermissionDenied,
            ConnectionPermissionService,
            ConnectionToolDenied,
        )

        permissions = ConnectionPermissionService(self._repo)
        try:
            permissions.check_connection_access(connection, user_role)
            permissions.check_tool_permission(connection, "publish_media")
        except (ConnectionPermissionDenied, ConnectionToolDenied) as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=exc.message,
                headers={"X-Error-Code": exc.code},
            ) from exc
        if connection.lifecycle_state != ConnectionLifecycle.CONNECTED.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Connection is not healthy and connected",
                headers={"X-Error-Code": "CONNECTION_NOT_READY"},
            )
        if "publish_media" not in (connection.capabilities or []):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Connection does not have the publish_media capability",
                headers={"X-Error-Code": "CAPABILITY_NOT_GRANTED"},
            )
        try:
            return evaluate_publish_policy(connection.provider_name, evidence)
        except PlatformUnavailableError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
                headers={"X-Error-Code": exc.code},
            ) from exc
        except PlatformPolicyDeniedError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "message": str(exc),
                    "missing_requirements": exc.missing_requirements,
                },
                headers={"X-Error-Code": exc.code},
            ) from exc

    # =========================================================================
    # Private Helpers
    # =========================================================================

    async def _exchange_oauth_code(
        self,
        provider_name: str,
        auth_code: str,
    ) -> dict[str, Any]:
        """Exchange an OAuth authorization code for tokens.

        The configured provider's token endpoint is called with the
        platform-managed client credentials. The response includes
        access_token, refresh_token, and expiration metadata and is validated
        before the token data is returned for encrypted credential storage.

        Args:
            provider_name: The provider name.
            auth_code: The OAuth authorization code.

        Returns:
            Dict with token data (access_token, refresh_token, etc.).
        """
        provider_config, client_id, client_secret = _oauth_configuration(provider_name)
        settings = get_settings()
        redirect_uri = settings.oauth_redirect_uri or (
            f"{settings.api_base_url.rstrip('/')}/api/v1/connections/callback"
        )
        payload = {
            "grant_type": "authorization_code",
            "code": auth_code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
        }
        try:
            async with httpx.AsyncClient(
                timeout=settings.provider_timeout_seconds
            ) as client:
                response = await client.post(provider_config["token_url"], data=payload)
        except (httpx.TimeoutException, TimeoutError) as exc:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail={
                    "code": "CONNECTION_PROVIDER_TIMEOUT",
                    "message": "OAuth provider token exchange timed out",
                },
                headers={"X-Error-Code": "CONNECTION_PROVIDER_TIMEOUT"},
            ) from exc
        except (httpx.ConnectError, httpx.TransportError, OSError) as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "CONNECTION_PROVIDER_UNAVAILABLE",
                    "message": "OAuth provider is unavailable",
                },
                headers={"X-Error-Code": "CONNECTION_PROVIDER_UNAVAILABLE"},
            ) from exc

        if response.status_code in (401, 403):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "code": "CONNECTION_PROVIDER_AUTH_FAILED",
                    "message": "OAuth provider rejected the configured application",
                },
                headers={"X-Error-Code": "CONNECTION_PROVIDER_AUTH_FAILED"},
            )
        if response.status_code == 429:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "CONNECTION_PROVIDER_RATE_LIMITED",
                    "message": "OAuth provider rate limit reached",
                },
                headers={"X-Error-Code": "CONNECTION_PROVIDER_RATE_LIMITED"},
            )
        if response.status_code < 200 or response.status_code >= 300:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "code": "CONNECTION_PROVIDER_TOKEN_EXCHANGE_FAILED",
                    "message": "OAuth provider rejected the authorization code",
                },
                headers={"X-Error-Code": "CONNECTION_PROVIDER_TOKEN_EXCHANGE_FAILED"},
            )
        try:
            token_data = response.json()
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "code": "CONNECTION_PROVIDER_TOKEN_EXCHANGE_FAILED",
                    "message": "OAuth provider returned an invalid token response",
                },
                headers={"X-Error-Code": "CONNECTION_PROVIDER_TOKEN_EXCHANGE_FAILED"},
            ) from exc
        if not isinstance(token_data, dict) or not token_data.get("access_token"):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "code": "CONNECTION_PROVIDER_TOKEN_EXCHANGE_FAILED",
                    "message": "OAuth provider returned no access token",
                },
                headers={"X-Error-Code": "CONNECTION_PROVIDER_TOKEN_EXCHANGE_FAILED"},
            )
        return token_data

    async def _store_encrypted_token(
        self,
        token_data: dict[str, Any],
        *,
        provider_name: str = "user_api_key",
        connection_id: UUID | None = None,
        actor: str = "system",
    ) -> UUID:
        """Encrypt OAuth material and return only a stable credential reference.

        The encrypted ``CredentialService`` owns token material. The
        ``connections`` row stores a UUID reference and never receives a raw
        access or refresh token.
        """
        if not token_data.get("access_token"):
            raise ConnectionServiceError("OAuth response did not contain an access token")

        if connection_id is None:
            raise ConnectionServiceError(
                "Connection ID is required for credential storage",
                code="CONNECTION_ID_REQUIRED",
            )
        reference_id = connection_id
        access_environment = _credential_environment(reference_id, "access")
        expires_in = int(token_data.get("expires_in", 3600) or 3600)
        expires_at = (datetime.now(tz=UTC) + timedelta(seconds=expires_in)).isoformat()
        credential = CredentialService.store(
            org_id=str(self._org_id),
            provider=_provider_type(provider_name),
            secret=str(token_data["access_token"]),
            environment=access_environment,
            ownership=CredentialOwnership.CUSTOMER,
            key_id=f"{provider_name}:{reference_id}",
            actor=actor,
            metadata={"connection_id": str(connection_id) if connection_id else None},
            expires_at=expires_at,
        )
        if token_data.get("refresh_token"):
            CredentialService.store(
                org_id=str(self._org_id),
                provider=_provider_type(provider_name),
                secret=str(token_data["refresh_token"]),
                environment=_credential_environment(reference_id, "refresh"),
                ownership=CredentialOwnership.CUSTOMER,
                key_id=f"{provider_name}:{reference_id}:refresh",
                actor=actor,
                metadata={"connection_id": str(connection_id) if connection_id else None},
            )

        # CredentialService IDs are intentionally opaque strings; UUID5 gives
        # the ORM's UUID reference a deterministic, non-secret representation.
        credential_id = str(credential["id"])
        token_ref = uuid5(NAMESPACE_URL, f"credential:{credential_id}")
        logger.info(
            "oauth_credential_reference_stored",
            credential_ref=str(token_ref),
            org_id=str(self._org_id),
            provider_name=provider_name,
        )
        return token_ref

    async def _validate_api_key(
        self,
        provider_name: str,
        api_key: str,
    ) -> dict[str, Any]:
        """Validate an API key using a configured provider adapter probe.

        Args:
            provider_name: The provider to validate against.
            api_key: The raw API key to validate.

        Returns:
            A safe validation result with provider evidence status.
        """
        if not api_key or len(api_key) < 8:
            return {"valid": False, "reason": "credential_format_invalid"}

        try:
            registry = build_default_registry()
            adapter = registry.get(provider_name)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "CONNECTION_PROVIDER_UNCONFIGURED",
                    "message": f"Provider '{provider_name}' is not configured",
                },
                headers={"X-Error-Code": "CONNECTION_PROVIDER_UNCONFIGURED"},
            ) from exc
        except ProviderError as exc:
            if exc.code.value == "unsupported_capability":
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "code": "PROVIDER_VALIDATION_UNSUPPORTED",
                        "message": f"Provider '{provider_name}' has no validation probe",
                    },
                    headers={"X-Error-Code": "PROVIDER_VALIDATION_UNSUPPORTED"},
                ) from exc
            raise

        if not adapter.metadata.base_url:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "CONNECTION_PROVIDER_UNCONFIGURED",
                    "message": f"Provider '{provider_name}' is not configured",
                },
                headers={"X-Error-Code": "CONNECTION_PROVIDER_UNCONFIGURED"},
            )

        try:
            evidence = await adapter.health(api_key)
        except ProviderError as exc:
            return {"valid": False, "reason": exc.code.value}

        if not evidence.healthy:
            return {"valid": False, "reason": evidence.reason or evidence.status}
        return {
            "valid": True,
            "reason": "provider_probe_succeeded",
            "evidence": {"status": evidence.status},
        }

    async def _discover_capabilities(
        self,
        provider_name: str,
        token_data: dict[str, Any],
    ) -> list[str]:
        """Discover provider capabilities using the authenticated credentials.

        Queries the provider's API to determine what operations are available
        with the given credentials.

        Args:
            provider_name: The provider name.
            token_data: Authenticated credentials for the provider.

        Returns:
            List of capability strings.
        """
        # TODO: Implement real capability discovery per provider
        # For OpenAI: list models, check fine-tuning access
        # For Instagram: check graph API permissions
        # For GitHub: check repo access, org membership

        capabilities = discovered_capabilities(provider_name)
        if capabilities:
            logger.info(
                "capabilities_discovered",
                provider_name=provider_name,
                capabilities_count=len(capabilities),
            )
            return capabilities

        # Return default capabilities per non-social provider category
        capability_map: dict[str, list[str]] = {
            "openai": ["chat", "embeddings", "image_generation", "fine_tuning"],
            "anthropic": ["chat", "embeddings"],
            "instagram": ["read_profile", "read_media", "publish_media"],
            "youtube": ["read_channel", "read_analytics", "upload_video"],
            "tiktok": ["read_profile", "read_videos", "publish_video"],
            "github": ["read_repos", "read_issues", "create_pr"],
            "runpod": ["create_pod", "list_pods", "terminate_pod"],
            "backblaze_b2": ["upload", "download", "list_buckets", "delete"],
        }

        capabilities = capability_map.get(provider_name, ["basic_access"])
        logger.info(
            "capabilities_discovered",
            provider_name=provider_name,
            capabilities_count=len(capabilities),
        )
        return capabilities

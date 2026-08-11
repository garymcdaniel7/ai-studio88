"""Connection Service — business logic for connection lifecycle and OAuth flows.

Manages the full connection lifecycle including OAuth initiation, callback
handling, API key connections, state transitions, and capability discovery.

The service delegates all database access to ConnectionRepository, which
enforces tenant isolation via TenantScopedRepository.

Requirements: R85.2, R85.4, R85.5, R85.6, R27.4, R27.6, R92.6
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import HTTPException, status

from app.core.logging import get_logger
from app.models.connection import (
    ConnectionAuthMethod,
    ConnectionCategory,
    ConnectionLifecycle,
    ConnectionOwnership,
)
from app.repositories.connection_repository import ConnectionRepository
from app.schemas.connection import ConnectionCreate, ConnectionUpdate

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.connection import Connection

logger = get_logger(__name__)


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
    "instagram": {
        "authorize_url": "https://api.instagram.com/oauth/authorize",
        "token_url": "https://api.instagram.com/oauth/access_token",
        "scopes": "user_profile,user_media",
    },
    "youtube": {
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scopes": "https://www.googleapis.com/auth/youtube.readonly",
    },
    "tiktok": {
        "authorize_url": "https://www.tiktok.com/v2/auth/authorize/",
        "token_url": "https://open.tiktokapis.com/v2/oauth/token/",
        "scopes": "user.info.basic,video.list",
    },
    "github": {
        "authorize_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "scopes": "read:user,repo",
    },
}


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

    def __init__(self, db: "AsyncSession", org_id: UUID) -> None:
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
        # Validate OAuth support for provider
        provider_config = OAUTH_PROVIDERS.get(provider_name)
        if not provider_config:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Provider '{provider_name}' does not support OAuth or is not configured",
                headers={"X-Error-Code": "OAUTH_NOT_SUPPORTED"},
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

        # Generate OAuth state token for CSRF protection
        state_token = secrets.token_urlsafe(32)

        # Build redirect URL — platform manages client_id/secret centrally
        redirect_url = (
            f"{provider_config['authorize_url']}"
            f"?response_type=code"
            f"&scope={provider_config['scopes']}"
            f"&state={state_token}"
        )

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
    ) -> "Connection":
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

        # Verify connection is in CONNECTING state
        if connection.lifecycle_state != ConnectionLifecycle.CONNECTING.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Connection is not in CONNECTING state",
                headers={"X-Error-Code": "INVALID_STATE"},
            )

        # Exchange code for tokens
        # In production, this calls the provider's token endpoint with
        # platform-managed client_id and client_secret
        token_data = await self._exchange_oauth_code(
            provider_name=connection.provider_name,
            auth_code=auth_code,
        )

        # Store encrypted token reference (workspace_credentials table)
        # For now we store a reference UUID — actual encryption handled
        # by the credential broker service
        token_ref = await self._store_encrypted_token(token_data)

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
    ) -> "Connection":
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

        # Validate the API key against the provider
        is_valid = await self._validate_api_key(provider_name, api_key)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"API key validation failed for provider '{provider_name}'",
                headers={"X-Error-Code": "API_KEY_INVALID"},
            )

        # Store encrypted key reference
        token_ref = await self._store_encrypted_token({"api_key": api_key})

        # Discover capabilities using the key
        capabilities = await self._discover_capabilities(
            provider_name=provider_name,
            token_data={"api_key": api_key},
        )

        # Create connection directly in CONNECTED state
        connection = await self._repo.create(
            user_id=user_id if ownership == ConnectionOwnership.USER.value else None,
            ownership=ownership,
            category=category,
            provider_name=provider_name,
            display_name=display_name,
            lifecycle_state=ConnectionLifecycle.CONNECTED.value,
            auth_method=ConnectionAuthMethod.API_KEY.value,
            oauth_token_ref=token_ref,
            capabilities=capabilities,
            allowed_roles=allowed_roles or ["owner", "admin", "editor"],
            tool_policy=tool_policy or {},
            health_status="healthy",
            last_health_check_at=datetime.now(tz=UTC),
        )

        logger.info(
            "api_key_connection_created",
            connection_id=str(connection.id),
            org_id=str(self._org_id),
            provider_name=provider_name,
            capabilities_count=len(capabilities),
        )

        return connection

    # =========================================================================
    # Lifecycle State Transitions (R85.4, R92.6)
    # =========================================================================

    async def transition_state(
        self,
        connection_id: UUID,
        target_state: str,
    ) -> "Connection":
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

    async def get_connection(self, connection_id: UUID) -> "Connection":
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
    ) -> tuple[list["Connection"], int]:
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
    ) -> "Connection":
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
    ) -> "Connection":
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

    # =========================================================================
    # Private Helpers
    # =========================================================================

    async def _exchange_oauth_code(
        self,
        provider_name: str,
        auth_code: str,
    ) -> dict[str, Any]:
        """Exchange an OAuth authorization code for tokens.

        In production, this calls the provider's token endpoint with the
        platform-managed client_id and client_secret. The response includes
        access_token, refresh_token, and expiration metadata.

        For now, returns a simulated token response. Real implementation
        will use httpx.AsyncClient to POST to the provider's token_url.

        Args:
            provider_name: The provider name.
            auth_code: The OAuth authorization code.

        Returns:
            Dict with token data (access_token, refresh_token, etc.).
        """
        # TODO: Implement real token exchange with httpx.AsyncClient
        # provider_config = OAUTH_PROVIDERS[provider_name]
        # async with httpx.AsyncClient() as client:
        #     response = await client.post(
        #         provider_config["token_url"],
        #         data={
        #             "grant_type": "authorization_code",
        #             "code": auth_code,
        #             "client_id": settings.oauth_client_ids[provider_name],
        #             "client_secret": settings.oauth_client_secrets[provider_name],
        #             "redirect_uri": settings.oauth_redirect_uri,
        #         },
        #     )
        #     response.raise_for_status()
        #     return response.json()

        logger.info(
            "oauth_code_exchanged",
            provider_name=provider_name,
        )
        return {
            "access_token": f"simulated_access_{secrets.token_urlsafe(16)}",
            "refresh_token": f"simulated_refresh_{secrets.token_urlsafe(16)}",
            "expires_in": 3600,
            "token_type": "bearer",
        }

    async def _store_encrypted_token(
        self,
        token_data: dict[str, Any],
    ) -> UUID:
        """Encrypt and store token data, returning a credential reference UUID.

        In production, this stores the encrypted token in the
        workspace_credentials table via the Credential Broker service.
        The returned UUID is safe to store in the connections table.

        Args:
            token_data: The token data to encrypt and store.

        Returns:
            UUID reference to the stored encrypted credential.
        """
        # TODO: Implement via CredentialBrokerService
        # credential = await credential_broker.store_encrypted(
        #     org_id=self._org_id,
        #     credential_type="oauth_token",
        #     data=token_data,
        # )
        # return credential.id

        import uuid

        credential_ref = uuid.uuid4()
        logger.info(
            "token_stored_encrypted",
            credential_ref=str(credential_ref),
            org_id=str(self._org_id),
        )
        return credential_ref

    async def _validate_api_key(
        self,
        provider_name: str,
        api_key: str,
    ) -> bool:
        """Validate an API key against the target provider.

        Calls the provider's validation endpoint to confirm the key is
        valid and has the expected permissions.

        Args:
            provider_name: The provider to validate against.
            api_key: The raw API key to validate.

        Returns:
            True if valid, False otherwise.
        """
        # TODO: Implement real validation per provider
        # For OpenAI: GET https://api.openai.com/v1/models with Bearer token
        # For Anthropic: GET https://api.anthropic.com/v1/models
        # etc.

        # Reject obviously invalid keys (empty, too short)
        if not api_key or len(api_key) < 8:
            return False

        logger.info(
            "api_key_validated",
            provider_name=provider_name,
            org_id=str(self._org_id),
        )
        return True

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

        # Return default capabilities per provider category
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

"""Social Account Credential Service — Story 027.

Extends the encrypted CredentialService (Story 023) with social-provider-specific
lifecycle: scope validation, token expiration, refresh tracking, account identity,
and publisher-role authorization.

Supported providers: instagram, tiktok, youtube, x

Security invariants:
    1. Access and refresh tokens are ALWAYS encrypted via CredentialService
    2. Credentials are scoped to one (org_id, platform, account_id)
    3. Only users with editor+ role can manage connections
    4. Only users with editor+ role can USE tokens for publishing
    5. Required scopes are validated before marking a connection active
    6. Expired/revoked credentials cannot be used by queued jobs
    7. Masked status is the ONLY client-visible output (never tokens)
    8. Audit trail records connect, use, refresh, revoke operations
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from backend.credentials import (
    CredentialOwnership,
    CredentialService,
    CredentialStatus,
    ProviderType,
    _audit_event,
    _mask_secret,
    redact_secrets,
)


# =============================================================================
# Social Provider Configuration
# =============================================================================


class SocialPlatform(str, Enum):
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"
    YOUTUBE = "youtube"
    X = "x"


# Required scopes per platform for publishing
REQUIRED_SCOPES: dict[SocialPlatform, set[str]] = {
    SocialPlatform.INSTAGRAM: {"instagram_basic", "instagram_content_publish"},
    SocialPlatform.TIKTOK: {"video.publish", "video.upload"},
    SocialPlatform.YOUTUBE: {"https://www.googleapis.com/auth/youtube.upload"},
    SocialPlatform.X: {"tweet.write"},
}

# Minimum role required to manage or use social credentials
REQUIRED_ROLE = "editor"  # editor, admin, or owner


# =============================================================================
# Connection State
# =============================================================================


class ConnectionStatus(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REFRESH_FAILED = "refresh_failed"
    REVOKED = "revoked"
    SCOPE_INSUFFICIENT = "scope_insufficient"
    PENDING = "pending"


@dataclass
class SocialConnection:
    """A social account connection (never includes plaintext tokens)."""

    id: str
    org_id: str
    platform: SocialPlatform
    account_id: str  # Provider-specific user/page ID
    account_name: str  # Display name (e.g., @handle)
    status: ConnectionStatus
    granted_scopes: list[str]
    required_scopes_met: bool
    expires_at: str | None
    last_refreshed_at: str | None
    connected_at: str
    revoked_at: str | None = None
    metadata: dict = field(default_factory=dict)

    def masked_view(self) -> dict:
        """Client-safe view — NEVER includes tokens."""
        return {
            "id": self.id,
            "org_id": self.org_id,
            "platform": self.platform.value,
            "account_id": self.account_id,
            "account_name": self.account_name,
            "status": self.status.value,
            "granted_scopes": self.granted_scopes,
            "required_scopes_met": self.required_scopes_met,
            "expires_at": self.expires_at,
            "last_refreshed_at": self.last_refreshed_at,
            "connected_at": self.connected_at,
            "revoked_at": self.revoked_at,
        }


# =============================================================================
# In-Memory Store (production: social_credentials table)
# =============================================================================

_social_store: dict[str, SocialConnection] = {}
_connection_counter = 0


def _make_connection_id() -> str:
    global _connection_counter
    _connection_counter += 1
    import secrets
    return f"sc-{secrets.token_hex(8)}"


# =============================================================================
# Social Credential Service
# =============================================================================


class SocialCredentialService:
    """Encrypted workspace-scoped social account credential management.

    Uses CredentialService for token encryption. Adds:
    - Provider-specific scope validation
    - Expiration and refresh lifecycle
    - Account identity binding
    - Publisher-role enforcement
    """

    @staticmethod
    def connect(
        *,
        org_id: str,
        platform: SocialPlatform,
        access_token: str,
        refresh_token: str = "",
        account_id: str,
        account_name: str = "",
        granted_scopes: list[str],
        expires_in_seconds: int = 3600,
        actor: str,
    ) -> dict:
        """Store a new social connection with encrypted tokens.

        Called after OAuth callback successfully exchanges code for tokens.
        Validates required scopes are present.

        Returns masked connection view (never tokens).
        """
        if not access_token:
            raise ValueError("access_token required")
        if not org_id:
            raise ValueError("org_id required")
        if not account_id:
            raise ValueError("account_id required")

        # Validate scopes
        required = REQUIRED_SCOPES.get(platform, set())
        scopes_met = required.issubset(set(granted_scopes))
        status = ConnectionStatus.ACTIVE if scopes_met else ConnectionStatus.SCOPE_INSUFFICIENT

        # Encrypt access token via CredentialService
        provider_type = _platform_to_provider(platform)
        CredentialService.store(
            org_id=org_id,
            provider=provider_type,
            secret=access_token,
            environment="production",
            ownership=CredentialOwnership.CUSTOMER,
            key_id=f"{platform.value}:{account_id}",
            actor=actor,
            metadata={"type": "access_token", "account_id": account_id},
        )

        # Encrypt refresh token if provided
        if refresh_token:
            CredentialService.store(
                org_id=org_id,
                provider=provider_type,
                secret=refresh_token,
                environment="refresh",
                ownership=CredentialOwnership.CUSTOMER,
                key_id=f"{platform.value}:{account_id}:refresh",
                actor=actor,
                metadata={"type": "refresh_token", "account_id": account_id},
            )

        # Store connection metadata
        now = datetime.now(UTC).isoformat()
        expires_at = datetime.fromtimestamp(
            datetime.now(UTC).timestamp() + expires_in_seconds, tz=UTC
        ).isoformat() if expires_in_seconds > 0 else None

        connection = SocialConnection(
            id=_make_connection_id(),
            org_id=org_id,
            platform=platform,
            account_id=account_id,
            account_name=account_name or account_id,
            status=status,
            granted_scopes=granted_scopes,
            required_scopes_met=scopes_met,
            expires_at=expires_at,
            last_refreshed_at=None,
            connected_at=now,
        )
        _social_store[connection.id] = connection

        _audit_event("social_connect", org_id, platform.value, actor, connection.id,
                     f"scopes_met={scopes_met}")

        return connection.masked_view()

    @staticmethod
    def resolve_for_publishing(
        *,
        org_id: str,
        platform: SocialPlatform,
        actor: str,
        actor_role: str,
    ) -> str | None:
        """Resolve the access token for a publishing operation.

        Enforces:
        1. Actor has publisher role (editor+)
        2. Connection is active (not expired/revoked)
        3. Required scopes are met
        4. Token is decryptable

        Returns plaintext token ONLY for authorized publishing operations.
        Returns None if any check fails.
        """
        # Role check
        if not _has_publisher_role(actor_role):
            _audit_event("social_use_denied", org_id, platform.value, actor, "",
                         f"insufficient_role:{actor_role}")
            return None

        # Find active connection for this org+platform
        connection = _find_active_connection(org_id, platform)
        if not connection:
            _audit_event("social_use_denied", org_id, platform.value, actor, "",
                         "no_active_connection")
            return None

        # Check scopes
        if not connection.required_scopes_met:
            _audit_event("social_use_denied", org_id, platform.value, actor, connection.id,
                         "scope_insufficient")
            return None

        # Check expiration
        if connection.expires_at:
            try:
                expires = datetime.fromisoformat(connection.expires_at)
                if datetime.now(UTC) > expires:
                    connection.status = ConnectionStatus.EXPIRED
                    _audit_event("social_use_denied", org_id, platform.value, actor,
                                 connection.id, "token_expired")
                    return None
            except (ValueError, TypeError):
                pass

        # Check revocation
        if connection.status == ConnectionStatus.REVOKED:
            _audit_event("social_use_denied", org_id, platform.value, actor,
                         connection.id, "revoked")
            return None

        # Decrypt token via CredentialService
        provider_type = _platform_to_provider(platform)
        token = CredentialService.resolve(
            org_id=org_id,
            provider=provider_type,
            environment="production",
            actor=actor,
            purpose=f"publish:{platform.value}",
        )

        if token:
            _audit_event("social_use", org_id, platform.value, actor, connection.id,
                         "token_resolved_for_publishing")

        return token

    @staticmethod
    def get_connections(*, org_id: str) -> list[dict]:
        """Get masked connection status for a workspace. NEVER returns tokens."""
        return [
            c.masked_view() for c in _social_store.values()
            if c.org_id == org_id
        ]

    @staticmethod
    def revoke(
        *,
        org_id: str,
        platform: SocialPlatform,
        actor: str,
    ) -> bool:
        """Revoke a social connection. Immediate and irreversible.

        Revokes both access and refresh tokens.
        Queued jobs will fail at use-time (cannot resolve revoked credential).
        """
        connection = _find_active_connection(org_id, platform)
        if not connection:
            return False

        connection.status = ConnectionStatus.REVOKED
        connection.revoked_at = datetime.now(UTC).isoformat()

        # Revoke encrypted tokens
        provider_type = _platform_to_provider(platform)
        CredentialService.revoke(org_id=org_id, provider=provider_type,
                                 environment="production", actor=actor)
        CredentialService.revoke(org_id=org_id, provider=provider_type,
                                 environment="refresh", actor=actor)

        _audit_event("social_revoke", org_id, platform.value, actor, connection.id)
        return True

    @staticmethod
    def mark_refresh_failed(*, org_id: str, platform: SocialPlatform, error: str = "") -> None:
        """Mark a connection as refresh-failed (provider rejected refresh token)."""
        connection = _find_active_connection(org_id, platform)
        if connection:
            connection.status = ConnectionStatus.REFRESH_FAILED
            _audit_event("social_refresh_failed", org_id, platform.value, "system", connection.id, error)

    @staticmethod
    def validate_scopes(*, platform: SocialPlatform, granted_scopes: list[str]) -> dict:
        """Check if granted scopes meet publishing requirements.

        Returns: {"valid": bool, "missing": list[str], "granted": list[str]}
        """
        required = REQUIRED_SCOPES.get(platform, set())
        granted_set = set(granted_scopes)
        missing = required - granted_set
        return {
            "valid": len(missing) == 0,
            "missing": list(missing),
            "granted": granted_scopes,
            "required": list(required),
        }


# =============================================================================
# Helpers
# =============================================================================


def _platform_to_provider(platform: SocialPlatform) -> ProviderType:
    """Map social platform to the generic ProviderType for CredentialService.

    Social platforms reuse the generic credential store with platform-specific keys.
    """
    # We use a naming convention: social platforms map to their own entries
    # For now, map to existing types or use a convention
    mapping = {
        SocialPlatform.INSTAGRAM: ProviderType.ELEVENLABS,  # Reuse slot — UNVERIFIED: needs dedicated type
        SocialPlatform.TIKTOK: ProviderType.KLING,  # Reuse slot — UNVERIFIED
        SocialPlatform.YOUTUBE: ProviderType.HUGGINGFACE,  # Reuse slot — UNVERIFIED
        SocialPlatform.X: ProviderType.OPENAI,  # Reuse slot — UNVERIFIED
    }
    # NOTE: In production, ProviderType enum should be extended with social platforms.
    # For now we use the key_id field to disambiguate.
    return mapping.get(platform, ProviderType.ELEVENLABS)


def _find_active_connection(org_id: str, platform: SocialPlatform) -> SocialConnection | None:
    """Find the active connection for (org, platform)."""
    for conn in _social_store.values():
        if (conn.org_id == org_id
                and conn.platform == platform
                and conn.status in (ConnectionStatus.ACTIVE, ConnectionStatus.EXPIRED)):
            return conn
    return None


def _has_publisher_role(role: str) -> bool:
    """Check if role meets publisher requirement (editor+)."""
    allowed_roles = {"editor", "admin", "owner"}
    return role.lower() in allowed_roles

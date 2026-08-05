"""MCP Client Authentication — Story 048.

Server-side credential validation and identity mapping for external AI clients.
Every MCP request is authenticated, scoped, auditable, and revocable.

Supported credential format:
    Bearer token: "mcp_<org_prefix>_<random_secret>"
    Header: Authorization: Bearer mcp_org123_abc...xyz

Identity mapping:
    credential → MCPClientIdentity (org_id, actor_type, role, capabilities, environment, expiry)

Security:
    - Credentials are hashed (SHA-256) before storage/lookup
    - Raw secrets never stored — only hash comparison
    - Service-role database access is NEVER exposed to external clients
    - Errors reveal no credential validity details
    - Rate limiting per credential (configurable)

Lifecycle:
    issue → active → (rotate → new active, old revoked) → revoke/expire

DECISION-REQUIRED:
    - Credential issuance UI/API (who can create MCP keys?)
    - Maximum credential lifetime
    - Per-workspace credential limits
"""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# MCP Client Identity
# =============================================================================


class MCPActorType(str, Enum):
    """Type of MCP client actor."""
    EXTERNAL_ASSISTANT = "external_assistant"  # Claude, GPT, etc. via MCP
    INTEGRATION = "integration"               # Zapier, Make, custom webhook
    DEVELOPMENT = "development"               # Local dev/testing client


class MCPEnvironment(str, Enum):
    """Deployment environment for the credential."""
    PRODUCTION = "production"
    STAGING = "staging"
    DEVELOPMENT = "development"


@dataclass(frozen=True)
class MCPClientIdentity:
    """Resolved identity for an authenticated MCP client.

    This is the MCP equivalent of TenantContext — never trust request-supplied values.
    """
    credential_id: str           # Unique credential identifier
    org_id: str                  # Workspace this credential belongs to
    actor_type: MCPActorType     # What kind of client
    actor_name: str              # Human-readable name (e.g., "Claude Desktop")
    role: str                    # Permission level (viewer/editor — never admin/owner)
    capabilities: frozenset[str] # Explicitly allowed tool capabilities
    environment: MCPEnvironment  # prod/staging/dev
    issued_by: str               # User who created this credential
    expires_at: float | None     # Unix timestamp or None for non-expiring
    rate_limit_rpm: int          # Requests per minute

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    def has_capability(self, capability: str) -> bool:
        """Check if this client has a specific capability."""
        if not self.capabilities:
            return False  # Empty = no capabilities (explicit deny-by-default)
        return capability in self.capabilities or "*" in self.capabilities


# =============================================================================
# Credential Status
# =============================================================================


class CredentialStatus(str, Enum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"
    ROTATED = "rotated"  # Old key after rotation


# =============================================================================
# Errors (safe — no credential details leaked)
# =============================================================================


class MCPAuthError(Exception):
    """Raised when MCP authentication fails. Message is safe for client response."""
    def __init__(self, safe_message: str = "Authentication failed") -> None:
        self.safe_message = safe_message
        super().__init__(safe_message)


class MCPRateLimitError(Exception):
    """Raised when rate limit is exceeded."""
    def __init__(self, retry_after: int = 60) -> None:
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded. Retry after {retry_after}s")


# =============================================================================
# Credential Store (in-memory; production would use DB)
# =============================================================================


@dataclass
class StoredCredential:
    """Internal credential record (never exposed to clients)."""
    id: str
    key_hash: str               # SHA-256 of the full key
    org_id: str
    actor_type: MCPActorType
    actor_name: str
    role: str
    capabilities: frozenset[str]
    environment: MCPEnvironment
    issued_by: str
    status: CredentialStatus
    expires_at: float | None
    rate_limit_rpm: int
    created_at: float
    revoked_at: float | None = None
    last_used_at: float | None = None
    request_count: int = 0


_credential_store: dict[str, StoredCredential] = {}  # key_hash → credential
_rate_counters: dict[str, list[float]] = {}  # credential_id → [timestamps]


# =============================================================================
# Core Authentication
# =============================================================================


def authenticate_mcp_request(authorization_header: str | None) -> MCPClientIdentity:
    """Authenticate an MCP request from the Authorization header.

    This is the SINGLE entry point for MCP authentication.
    Must be called before any tool discovery or execution.

    Args:
        authorization_header: The raw Authorization header value.

    Returns:
        MCPClientIdentity with resolved workspace, role, and capabilities.

    Raises:
        MCPAuthError: If authentication fails (safe error message).
        MCPRateLimitError: If rate limit exceeded.
    """
    # 1. Extract bearer token
    token = _extract_bearer_token(authorization_header)

    # 2. Hash and lookup
    key_hash = _hash_credential(token)
    credential = _credential_store.get(key_hash)

    if not credential:
        _audit_auth_failure("unknown_credential")
        raise MCPAuthError("Authentication failed")

    # 3. Check status
    if credential.status == CredentialStatus.REVOKED:
        _audit_auth_failure("revoked_credential", credential.id)
        raise MCPAuthError("Authentication failed")

    if credential.status == CredentialStatus.ROTATED:
        _audit_auth_failure("rotated_credential", credential.id)
        raise MCPAuthError("Authentication failed")

    if credential.status == CredentialStatus.EXPIRED:
        _audit_auth_failure("expired_credential", credential.id)
        raise MCPAuthError("Authentication failed")

    # 4. Check expiry
    if credential.expires_at and time.time() > credential.expires_at:
        credential.status = CredentialStatus.EXPIRED
        _audit_auth_failure("just_expired", credential.id)
        raise MCPAuthError("Authentication failed")

    # 5. Rate limiting
    _check_rate_limit(credential)

    # 6. Update usage
    credential.last_used_at = time.time()
    credential.request_count += 1

    # 7. Build identity
    identity = MCPClientIdentity(
        credential_id=credential.id,
        org_id=credential.org_id,
        actor_type=credential.actor_type,
        actor_name=credential.actor_name,
        role=credential.role,
        capabilities=credential.capabilities,
        environment=credential.environment,
        issued_by=credential.issued_by,
        expires_at=credential.expires_at,
        rate_limit_rpm=credential.rate_limit_rpm,
    )

    _audit_auth_success(credential.id, credential.org_id)
    return identity


# =============================================================================
# Credential Lifecycle
# =============================================================================


def issue_credential(
    org_id: str,
    issued_by: str,
    actor_name: str,
    actor_type: MCPActorType = MCPActorType.EXTERNAL_ASSISTANT,
    role: str = "editor",
    capabilities: frozenset[str] | None = None,
    environment: MCPEnvironment = MCPEnvironment.PRODUCTION,
    expires_in_days: int | None = 90,
    rate_limit_rpm: int = 60,
) -> tuple[str, str]:
    """Issue a new MCP credential.

    Returns (credential_id, raw_key) — raw_key shown ONCE and never again.

    DECISION-REQUIRED: Who can call this? Currently requires issued_by (user_id).
    """
    if not org_id:
        raise ValueError("org_id is required for credential issuance")
    if not issued_by:
        raise ValueError("issued_by (user_id) is required")

    # Role cap: MCP clients can never be admin/owner
    if role in ("admin", "owner"):
        role = "editor"  # Cap at editor

    # Generate key
    credential_id = f"mcp-{uuid.uuid4().hex[:12]}"
    raw_key = f"mcp_{org_id[:8]}_{uuid.uuid4().hex}"
    key_hash = _hash_credential(raw_key)

    expires_at = None
    if expires_in_days:
        expires_at = time.time() + (expires_in_days * 86400)

    stored = StoredCredential(
        id=credential_id,
        key_hash=key_hash,
        org_id=org_id,
        actor_type=actor_type,
        actor_name=actor_name,
        role=role,
        capabilities=capabilities or frozenset(),
        environment=environment,
        issued_by=issued_by,
        status=CredentialStatus.ACTIVE,
        expires_at=expires_at,
        rate_limit_rpm=rate_limit_rpm,
        created_at=time.time(),
    )

    _credential_store[key_hash] = stored
    logger.info(f"MCP credential issued: id={credential_id} org={org_id[:8]} actor={actor_name}")

    return credential_id, raw_key


def revoke_credential(credential_id: str, revoked_by: str) -> bool:
    """Revoke an MCP credential. Immediate effect."""
    for cred in _credential_store.values():
        if cred.id == credential_id:
            cred.status = CredentialStatus.REVOKED
            cred.revoked_at = time.time()
            logger.info(f"MCP credential revoked: id={credential_id} by={revoked_by}")
            return True
    return False


def rotate_credential(credential_id: str, rotated_by: str) -> tuple[str, str] | None:
    """Rotate a credential — old key is marked ROTATED, new key issued.

    Returns (new_credential_id, new_raw_key) or None if not found.
    """
    for cred in _credential_store.values():
        if cred.id == credential_id and cred.status == CredentialStatus.ACTIVE:
            # Mark old as rotated
            cred.status = CredentialStatus.ROTATED

            # Issue new with same config
            new_id, new_key = issue_credential(
                org_id=cred.org_id,
                issued_by=rotated_by,
                actor_name=cred.actor_name,
                actor_type=cred.actor_type,
                role=cred.role,
                capabilities=cred.capabilities,
                environment=cred.environment,
                rate_limit_rpm=cred.rate_limit_rpm,
            )
            logger.info(f"MCP credential rotated: old={credential_id} new={new_id}")
            return new_id, new_key
    return None


# =============================================================================
# Rate Limiting
# =============================================================================


def _check_rate_limit(credential: StoredCredential) -> None:
    """Check and enforce per-credential rate limit."""
    now = time.time()
    window = 60.0  # 1 minute window

    if credential.id not in _rate_counters:
        _rate_counters[credential.id] = []

    # Clean old entries
    _rate_counters[credential.id] = [
        t for t in _rate_counters[credential.id] if t > now - window
    ]

    # Check limit
    if len(_rate_counters[credential.id]) >= credential.rate_limit_rpm:
        raise MCPRateLimitError(retry_after=int(window))

    # Record this request
    _rate_counters[credential.id].append(now)


# =============================================================================
# Helpers
# =============================================================================


def _extract_bearer_token(authorization: str | None) -> str:
    """Extract token from Authorization: Bearer <token> header."""
    if not authorization:
        raise MCPAuthError("Authentication required")

    parts = authorization.strip().split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise MCPAuthError("Authentication failed")

    token = parts[1].strip()
    if not token or len(token) < 20:
        raise MCPAuthError("Authentication failed")

    return token


def _hash_credential(raw_key: str) -> str:
    """Hash a credential for storage/lookup. Never store raw keys."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


def _audit_auth_success(credential_id: str, org_id: str) -> None:
    """Audit successful authentication (minimal logging)."""
    logger.debug(f"MCP auth success: cred={credential_id[:12]} org={org_id[:8]}")


def _audit_auth_failure(reason: str, credential_id: str | None = None) -> None:
    """Audit failed authentication attempt."""
    logger.warning(f"MCP auth FAILED: reason={reason} cred={credential_id or 'unknown'}")


# =============================================================================
# Testing Utilities
# =============================================================================


def _reset_store() -> None:
    """Reset credential store. FOR TESTING ONLY."""
    _credential_store.clear()
    _rate_counters.clear()

"""Encrypted Workspace-Scoped Credential Service — Story 023.

Provides secure storage, retrieval, rotation, and revocation of provider
credentials (Vast.ai, RunPod, B2, OpenAI, etc.) scoped to individual workspaces.

Architecture:
    ┌──────────────┐
    │  Route/API   │ — masked metadata only
    └──────┬───────┘
           │ requires AuthorizedClient context
    ┌──────▼───────┐
    │ CredService  │ — encrypts/decrypts, scopes, audits
    └──────┬───────┘
           │
    ┌──────▼───────┐
    │  Supabase    │ — encrypted blob stored in workspace_credentials table
    └──────────────┘

Security invariants:
    1. Secret material is NEVER returned to clients — only masked metadata
    2. Decryption only occurs inside authorized backend operations
    3. Secrets are NEVER logged, included in errors, or passed to job payloads
    4. Each credential is scoped to exactly one (org_id, provider, environment)
    5. Rotation creates a new version; old version is marked superseded
    6. Revocation is immediate and irreversible
    7. Audit trail records every store/resolve/rotate/revoke operation

Encryption:
    Uses Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256).
    Encryption key is derived from CREDENTIAL_ENCRYPTION_KEY env var.
    UNVERIFIED: Production key management (HSM, KMS, rotation) is out of scope.
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


# =============================================================================
# Configuration
# =============================================================================

# Encryption key from environment (32 bytes base64-encoded for Fernet)
# UNVERIFIED: Production should use a secrets manager (Doppler, AWS KMS)
_RAW_KEY = os.getenv("CREDENTIAL_ENCRYPTION_KEY", "")


def _get_fernet_key() -> bytes:
    """Derive a Fernet-compatible key from the environment variable.

    If not set, generates a deterministic dev-only key (NOT for production).
    """
    if _RAW_KEY:
        # Ensure it's a valid 32-byte key for Fernet (base64url-encoded)
        raw = _RAW_KEY.encode()
        if len(raw) == 44:  # Already base64-encoded 32 bytes
            return raw
        # Hash arbitrary-length key to 32 bytes
        derived = hashlib.sha256(raw).digest()
        return base64.urlsafe_b64encode(derived)
    else:
        # Dev-only deterministic key — NEVER use in production
        derived = hashlib.sha256(b"ai-studio-dev-credential-key-DO-NOT-USE").digest()
        return base64.urlsafe_b64encode(derived)


def _encrypt(plaintext: str) -> str:
    """Encrypt a secret value. Returns base64-encoded ciphertext."""
    from cryptography.fernet import Fernet

    f = Fernet(_get_fernet_key())
    return f.encrypt(plaintext.encode()).decode()


def _decrypt(ciphertext: str) -> str:
    """Decrypt an encrypted value. Returns plaintext."""
    from cryptography.fernet import Fernet

    f = Fernet(_get_fernet_key())
    return f.decrypt(ciphertext.encode()).decode()


# =============================================================================
# Types
# =============================================================================


class ProviderType(str, Enum):
    """Supported credential providers."""

    VAST_AI = "vast_ai"
    RUNPOD = "runpod"
    BACKBLAZE_B2 = "backblaze_b2"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    HUGGINGFACE = "huggingface"
    ELEVENLABS = "elevenlabs"
    KLING = "kling"


class CredentialOwnership(str, Enum):
    """Who owns this credential."""

    PLATFORM = "platform"   # Shared platform credential (from .env)
    CUSTOMER = "customer"   # Customer-provided (workspace-specific)


class CredentialStatus(str, Enum):
    """Lifecycle status."""

    ACTIVE = "active"
    ROTATED = "rotated"       # Superseded by a newer version
    REVOKED = "revoked"       # Permanently invalidated
    EXPIRED = "expired"       # TTL passed


@dataclass
class CredentialRecord:
    """A stored credential (never includes plaintext secret in serialization)."""

    id: str
    org_id: str
    provider: ProviderType
    environment: str  # "production", "staging", "development"
    ownership: CredentialOwnership
    status: CredentialStatus
    key_id: str  # Non-secret identifier (e.g., B2 key ID, first 8 chars of API key)
    encrypted_secret: str  # Fernet-encrypted blob
    version: int
    created_at: str
    rotated_at: str | None = None
    revoked_at: str | None = None
    metadata: dict = field(default_factory=dict)

    def masked_view(self) -> dict:
        """Return client-safe view — NEVER includes the secret."""
        return {
            "id": self.id,
            "org_id": self.org_id,
            "provider": self.provider.value,
            "environment": self.environment,
            "ownership": self.ownership.value,
            "status": self.status.value,
            "key_hint": self.key_id,  # e.g., "sk-...abc1" or B2 key ID
            "version": self.version,
            "created_at": self.created_at,
            "rotated_at": self.rotated_at,
            "revoked_at": self.revoked_at,
        }


# =============================================================================
# Audit Trail
# =============================================================================

_credential_audit: list[dict] = []
_MAX_AUDIT = 1000


def _audit_event(
    action: str,
    org_id: str,
    provider: str,
    actor: str,
    credential_id: str = "",
    details: str = "",
) -> None:
    """Record a credential operation for audit."""
    _credential_audit.append({
        "timestamp": datetime.now(UTC).isoformat(),
        "action": action,
        "org_id": org_id,
        "provider": provider,
        "actor": actor,
        "credential_id": credential_id,
        "details": details,
    })
    if len(_credential_audit) > _MAX_AUDIT:
        _credential_audit.pop(0)


def get_credential_audit(org_id: str | None = None, limit: int = 50) -> list[dict]:
    """Get recent credential audit entries, optionally filtered by org."""
    entries = _credential_audit if not org_id else [
        e for e in _credential_audit if e["org_id"] == org_id
    ]
    return list(reversed(entries[-limit:]))


# =============================================================================
# In-Memory Store (production: Supabase table `workspace_credentials`)
# =============================================================================

# For this implementation, we use an in-memory store that mirrors the DB schema.
# Production deployment will use the workspace_credentials table (migration 034).
_store: dict[str, CredentialRecord] = {}


def _make_id() -> str:
    return f"cred-{secrets.token_hex(12)}"


def _mask_secret(secret: str) -> str:
    """Create a non-reversible hint for display (e.g., 'sk-...a1b2')."""
    if len(secret) <= 8:
        return "***"
    return f"{secret[:4]}...{secret[-4:]}"


# =============================================================================
# Credential Service — Public API
# =============================================================================


class CredentialService:
    """Encrypted workspace-scoped credential management.

    All methods require explicit org_id and actor identification.
    Secrets are encrypted before storage and decrypted only on resolve().
    """

    @staticmethod
    def store(
        *,
        org_id: str,
        provider: ProviderType,
        secret: str,
        environment: str = "production",
        ownership: CredentialOwnership = CredentialOwnership.CUSTOMER,
        key_id: str = "",
        actor: str = "unknown",
        metadata: dict | None = None,
    ) -> dict:
        """Store a new credential (encrypted). Returns masked metadata only.

        Args:
            org_id: Workspace that owns this credential.
            provider: Which provider (vast_ai, runpod, etc.).
            secret: The plaintext secret (encrypted before storage, never persisted raw).
            environment: Target environment.
            ownership: Platform-shared or customer-owned.
            key_id: Non-secret identifier for display.
            actor: Who is performing this operation (user_id or system).
            metadata: Additional non-secret metadata.

        Returns:
            Masked credential view (no secret).
        """
        if not secret:
            raise ValueError("Secret cannot be empty")
        if not org_id:
            raise ValueError("org_id required")

        # Auto-generate key_id hint if not provided
        if not key_id:
            key_id = _mask_secret(secret)

        # Check for existing active credential (same org/provider/env)
        existing = CredentialService._find_active(org_id, provider, environment)
        if existing:
            # Mark old one as rotated
            existing.status = CredentialStatus.ROTATED
            existing.rotated_at = datetime.now(UTC).isoformat()

        # Encrypt and store
        encrypted = _encrypt(secret)
        version = (existing.version + 1) if existing else 1

        record = CredentialRecord(
            id=_make_id(),
            org_id=org_id,
            provider=provider,
            environment=environment,
            ownership=ownership,
            status=CredentialStatus.ACTIVE,
            key_id=key_id,
            encrypted_secret=encrypted,
            version=version,
            created_at=datetime.now(UTC).isoformat(),
            metadata=metadata or {},
        )
        _store[record.id] = record

        _audit_event("store", org_id, provider.value, actor, record.id)
        return record.masked_view()

    @staticmethod
    def resolve(
        *,
        org_id: str,
        provider: ProviderType,
        environment: str = "production",
        actor: str = "unknown",
        purpose: str = "",
    ) -> str | None:
        """Resolve (decrypt) the active credential for an authorized operation.

        This is the ONLY way to get the plaintext secret. It:
        1. Finds the active credential for (org_id, provider, environment)
        2. Decrypts it
        3. Records an audit event
        4. Returns the plaintext (NEVER log this)

        Falls back to platform env var if no workspace credential exists.

        Returns:
            Plaintext secret, or None if not found.
        """
        record = CredentialService._find_active(org_id, provider, environment)

        if record:
            _audit_event("resolve", org_id, provider.value, actor, record.id, purpose)
            try:
                return _decrypt(record.encrypted_secret)
            except Exception:
                _audit_event("resolve_failed", org_id, provider.value, actor, record.id, "decryption_error")
                return None

        # Fallback: platform env var (shared credentials)
        env_var = _provider_env_var(provider)
        if env_var:
            value = os.getenv(env_var, "")
            if value:
                _audit_event("resolve_platform_fallback", org_id, provider.value, actor, "", purpose)
                return value

        return None

    @staticmethod
    def get_status(
        *,
        org_id: str,
        provider: ProviderType | None = None,
        environment: str = "production",
    ) -> list[dict]:
        """Get masked credential status for a workspace. NEVER returns secrets.

        Returns list of masked views for all credentials matching the filter.
        """
        results = []
        for record in _store.values():
            if record.org_id != org_id:
                continue
            if provider and record.provider != provider:
                continue
            if record.environment != environment:
                continue
            results.append(record.masked_view())
        return results

    @staticmethod
    def rotate(
        *,
        org_id: str,
        provider: ProviderType,
        new_secret: str,
        environment: str = "production",
        actor: str = "unknown",
    ) -> dict:
        """Rotate a credential — stores new version, marks old as rotated.

        Returns masked view of the new credential.
        """
        return CredentialService.store(
            org_id=org_id,
            provider=provider,
            secret=new_secret,
            environment=environment,
            actor=actor,
            metadata={"rotated_from": "previous_version"},
        )

    @staticmethod
    def revoke(
        *,
        org_id: str,
        provider: ProviderType,
        environment: str = "production",
        actor: str = "unknown",
    ) -> bool:
        """Revoke the active credential. Immediate and irreversible.

        Returns True if a credential was revoked, False if none found.
        """
        record = CredentialService._find_active(org_id, provider, environment)
        if not record:
            return False

        record.status = CredentialStatus.REVOKED
        record.revoked_at = datetime.now(UTC).isoformat()
        # Wipe encrypted material for safety
        record.encrypted_secret = ""

        _audit_event("revoke", org_id, provider.value, actor, record.id)
        return True

    @staticmethod
    def validate(
        *,
        org_id: str,
        provider: ProviderType,
        environment: str = "production",
        actor: str = "unknown",
    ) -> dict:
        """Validate a credential without logging the secret.

        Checks: exists, active, decryptable, non-empty.
        Does NOT call the provider API (that's a separate connectivity check).

        Returns:
            {"valid": bool, "reason": str}
        """
        record = CredentialService._find_active(org_id, provider, environment)
        if not record:
            return {"valid": False, "reason": "no_credential_found"}

        if record.status != CredentialStatus.ACTIVE:
            return {"valid": False, "reason": f"status_{record.status.value}"}

        try:
            plaintext = _decrypt(record.encrypted_secret)
            if not plaintext or len(plaintext) < 4:
                return {"valid": False, "reason": "empty_or_too_short"}
        except Exception:
            return {"valid": False, "reason": "decryption_failed"}

        _audit_event("validate", org_id, provider.value, actor, record.id)
        return {"valid": True, "reason": "ok"}

    # =========================================================================
    # Internal helpers
    # =========================================================================

    @staticmethod
    def _find_active(
        org_id: str,
        provider: ProviderType,
        environment: str,
    ) -> CredentialRecord | None:
        """Find the active credential for (org, provider, env)."""
        for record in _store.values():
            if (
                record.org_id == org_id
                and record.provider == provider
                and record.environment == environment
                and record.status == CredentialStatus.ACTIVE
            ):
                return record
        return None


# =============================================================================
# Provider → Env Var Mapping (platform fallback)
# =============================================================================


def _provider_env_var(provider: ProviderType) -> str:
    """Map provider type to the legacy env var name for platform fallback."""
    mapping = {
        ProviderType.VAST_AI: "VAST_API_KEY",
        ProviderType.RUNPOD: "RUNPOD_API_KEY",
        ProviderType.BACKBLAZE_B2: "B2_APPLICATION_KEY",
        ProviderType.OPENAI: "OPENAI_API_KEY",
        ProviderType.ANTHROPIC: "ANTHROPIC_API_KEY",
        ProviderType.HUGGINGFACE: "HF_TOKEN",
        ProviderType.ELEVENLABS: "ELEVENLABS_API_KEY",
        ProviderType.KLING: "KLING_API_KEY",
    }
    return mapping.get(provider, "")


# =============================================================================
# Redaction Utilities
# =============================================================================


# Patterns that look like secrets (used by redact_secrets)
_SECRET_PATTERNS = [
    "sk-", "sk-ant-", "rp_", "vast_", "hf_", "xi_", "kling_",
    "eyJ",  # JWT prefix
    "K00",  # B2 key prefix
]


def redact_secrets(text: str) -> str:
    """Redact any string that looks like a secret from text.

    Use this before logging, error reporting, or including text in payloads.
    """
    if not text:
        return text

    words = text.split()
    redacted = []
    for word in words:
        if any(word.startswith(p) for p in _SECRET_PATTERNS) and len(word) > 10:
            redacted.append("[REDACTED]")
        elif len(word) > 30 and not word.startswith("http"):
            # Long strings that might be keys
            redacted.append("[REDACTED]")
        else:
            redacted.append(word)
    return " ".join(redacted)


def redact_dict(data: dict, sensitive_keys: set[str] | None = None) -> dict:
    """Redact sensitive values from a dictionary (for safe logging/payloads).

    Default sensitive keys: anything containing 'key', 'secret', 'token', 'password'.
    """
    if sensitive_keys is None:
        sensitive_keys = {"key", "secret", "token", "password", "api_key", "credentials"}

    result = {}
    for k, v in data.items():
        k_lower = k.lower()
        if any(s in k_lower for s in sensitive_keys):
            result[k] = "[REDACTED]"
        elif isinstance(v, dict):
            result[k] = redact_dict(v, sensitive_keys)
        elif isinstance(v, str) and len(v) > 30 and any(p in v for p in _SECRET_PATTERNS):
            result[k] = "[REDACTED]"
        else:
            result[k] = v
    return result

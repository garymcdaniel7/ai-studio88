"""Voice-Cloning Consent — Story 103.

Durable consent records for voice cloning and generation. Every clone and
generated clip requires a valid persisted consent evaluated server-side.
Request-only booleans CANNOT authorize production cloning.

Consent Lifecycle:
    PENDING   → Created, awaiting evidence upload
    ACTIVE    → Valid, authorized for use
    EXPIRED   → Past expiration date
    REVOKED   → Explicitly revoked (blocks future use, preserves history)

Record Fields:
    - subject_talent_id: whose voice is being cloned
    - grantor_id: who gave consent (may differ from subject)
    - org_id: workspace scope
    - evidence: storage key to signed document/recording
    - source_sample_ids: which audio samples are authorized
    - permitted_purposes: what the voice can be used for
    - provider_scope: which providers may use it
    - effective_from / expires_at: validity window
    - revoked_at / revoked_by / revocation_reason: revocation state

Execution Gate:
    Before cloning or generating with a cloned voice, the system MUST:
    1. Find a consent record for the talent + org
    2. Verify it is ACTIVE (not expired, not revoked)
    3. Verify the requested purpose is permitted
    4. Record the consent_id on the job/asset
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


# =============================================================================
# Consent State
# =============================================================================


class ConsentState(StrEnum):
    PENDING = "pending"       # Created, evidence not yet confirmed
    ACTIVE = "active"         # Valid and authorizing
    EXPIRED = "expired"       # Past expiration date
    REVOKED = "revoked"       # Explicitly revoked


class ConsentPurpose(StrEnum):
    VOICE_CLONING = "voice_cloning"
    TEXT_TO_SPEECH = "text_to_speech"
    LIP_SYNC = "lip_sync"
    COMMERCIAL_USE = "commercial_use"
    SOCIAL_MEDIA = "social_media"
    INTERNAL_ONLY = "internal_only"


# =============================================================================
# Consent Record
# =============================================================================


@dataclass
class VoiceConsentRecord:
    """Durable voice-cloning consent with full provenance."""

    # Identity
    consent_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    org_id: str = ""
    version: int = 1

    # Subject and grantor
    subject_talent_id: str = ""     # Whose voice
    grantor_id: str = ""            # Who gave consent (user_id)
    grantor_name: str = ""          # Human-readable
    grantor_relationship: str = ""  # e.g., "self", "agent", "employer"

    # Evidence
    evidence_storage_key: str = ""  # Signed document/recording in B2
    evidence_type: str = ""         # "signed_document", "audio_confirmation", "written_email"
    evidence_uploaded_at: str | None = None

    # Source samples authorized
    source_sample_ids: list[str] = field(default_factory=list)

    # Scope
    permitted_purposes: list[ConsentPurpose] = field(default_factory=list)
    provider_scope: list[str] = field(default_factory=list)  # Which providers

    # Validity
    state: ConsentState = ConsentState.PENDING
    effective_from: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    expires_at: str | None = None   # None = no expiration

    # Revocation
    revoked_at: str | None = None
    revoked_by: str | None = None
    revocation_reason: str | None = None

    # Audit
    created_by: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict:
        return {
            "consent_id": self.consent_id,
            "org_id": self.org_id,
            "version": self.version,
            "subject_talent_id": self.subject_talent_id,
            "grantor_id": self.grantor_id,
            "state": self.state.value,
            "permitted_purposes": [p.value for p in self.permitted_purposes],
            "provider_scope": self.provider_scope,
            "effective_from": self.effective_from,
            "expires_at": self.expires_at,
            "revoked_at": self.revoked_at,
            "evidence_type": self.evidence_type,
            "created_at": self.created_at,
        }


# =============================================================================
# Consent Registry
# =============================================================================

_consent_store: dict[str, VoiceConsentRecord] = {}


def clear_registry() -> None:
    _consent_store.clear()


def register_consent(consent: VoiceConsentRecord) -> VoiceConsentRecord:
    """Register a consent record."""
    _consent_store[consent.consent_id] = consent
    return consent


def get_consent(consent_id: str) -> VoiceConsentRecord | None:
    return _consent_store.get(consent_id)


def find_active_consent(
    org_id: str,
    talent_id: str,
    *,
    now: str | None = None,
) -> VoiceConsentRecord | None:
    """Find the active consent for a talent in a workspace.

    Returns None if no valid consent exists.
    """
    current = now or datetime.now(UTC).isoformat()

    for consent in _consent_store.values():
        if consent.org_id != org_id:
            continue
        if consent.subject_talent_id != talent_id:
            continue
        if consent.state != ConsentState.ACTIVE:
            continue
        # Check expiration
        if consent.expires_at and consent.expires_at < current:
            continue
        return consent

    return None


# =============================================================================
# Consent Validation (Execution Gate)
# =============================================================================


class ConsentError(Exception):
    """Raised when consent validation fails."""

    def __init__(self, message: str, code: str = "CONSENT_DENIED"):
        self.message = message
        self.code = code
        super().__init__(message)


class ConsentExpiredError(ConsentError):
    def __init__(self, consent_id: str, expired_at: str):
        super().__init__(
            f"Consent {consent_id} expired at {expired_at}",
            code="CONSENT_EXPIRED",
        )


class ConsentRevokedError(ConsentError):
    def __init__(self, consent_id: str, reason: str = ""):
        msg = f"Consent {consent_id} has been revoked"
        if reason:
            msg += f": {reason}"
        super().__init__(msg, code="CONSENT_REVOKED")


class ConsentNotFoundError(ConsentError):
    def __init__(self, talent_id: str, org_id: str):
        super().__init__(
            f"No valid consent found for talent {talent_id} in workspace {org_id}",
            code="CONSENT_NOT_FOUND",
        )


class ConsentPurposeError(ConsentError):
    def __init__(self, purpose: str, consent_id: str):
        super().__init__(
            f"Purpose '{purpose}' not permitted by consent {consent_id}",
            code="PURPOSE_NOT_PERMITTED",
        )


class ConsentCrossTenantError(ConsentError):
    def __init__(self):
        super().__init__(
            "Cross-workspace consent use is denied",
            code="CROSS_TENANT_DENIED",
        )


def validate_consent_for_execution(
    *,
    consent_id: str | None = None,
    org_id: str,
    talent_id: str,
    purpose: ConsentPurpose,
    now: str | None = None,
) -> VoiceConsentRecord:
    """Validate that consent authorizes the requested action.

    This is the server-side execution gate. Called before:
    - Voice cloning
    - TTS generation with cloned voice
    - Lip-sync with cloned voice

    Returns the valid consent record.
    Raises ConsentError subclass on failure.
    """
    current = now or datetime.now(UTC).isoformat()

    # Find consent
    if consent_id:
        consent = get_consent(consent_id)
        if consent is None:
            raise ConsentNotFoundError(talent_id, org_id)
    else:
        consent = find_active_consent(org_id, talent_id, now=current)
        if consent is None:
            raise ConsentNotFoundError(talent_id, org_id)

    # Cross-tenant check
    if consent.org_id != org_id:
        raise ConsentCrossTenantError()

    # Talent match
    if consent.subject_talent_id != talent_id:
        raise ConsentNotFoundError(talent_id, org_id)

    # State check
    if consent.state == ConsentState.REVOKED:
        raise ConsentRevokedError(consent.consent_id, consent.revocation_reason or "")

    if consent.state == ConsentState.PENDING:
        raise ConsentError(
            f"Consent {consent.consent_id} is pending — evidence not yet confirmed",
            code="CONSENT_PENDING",
        )

    if consent.state != ConsentState.ACTIVE:
        raise ConsentError(
            f"Consent {consent.consent_id} is in state '{consent.state.value}'",
            code="CONSENT_INVALID_STATE",
        )

    # Expiration check
    if consent.expires_at and consent.expires_at < current:
        raise ConsentExpiredError(consent.consent_id, consent.expires_at)

    # Purpose check
    if purpose not in consent.permitted_purposes:
        raise ConsentPurposeError(purpose.value, consent.consent_id)

    return consent


# =============================================================================
# Consent Activation
# =============================================================================


def activate_consent(
    consent_id: str,
    *,
    evidence_storage_key: str,
    evidence_type: str,
    actor_id: str,
) -> VoiceConsentRecord:
    """Activate a pending consent after evidence is uploaded.

    Transitions PENDING → ACTIVE.
    """
    consent = get_consent(consent_id)
    if consent is None:
        raise ConsentError(f"Consent {consent_id} not found")

    if consent.state != ConsentState.PENDING:
        raise ConsentError(
            f"Cannot activate consent in state '{consent.state.value}' (must be pending)"
        )

    if not evidence_storage_key:
        raise ConsentError("Evidence storage key is required for activation")

    consent.state = ConsentState.ACTIVE
    consent.evidence_storage_key = evidence_storage_key
    consent.evidence_type = evidence_type
    consent.evidence_uploaded_at = datetime.now(UTC).isoformat()
    consent.updated_at = datetime.now(UTC).isoformat()
    consent.version += 1

    return consent


# =============================================================================
# Revocation
# =============================================================================


def revoke_consent(
    consent_id: str,
    *,
    revoked_by: str,
    reason: str,
) -> VoiceConsentRecord:
    """Revoke a consent record.

    Blocks ALL future use. Historical evidence is preserved for audit.
    Idempotent: revoking already-revoked consent is a no-op.
    """
    consent = get_consent(consent_id)
    if consent is None:
        raise ConsentError(f"Consent {consent_id} not found")

    if consent.state == ConsentState.REVOKED:
        return consent  # Idempotent

    consent.state = ConsentState.REVOKED
    consent.revoked_at = datetime.now(UTC).isoformat()
    consent.revoked_by = revoked_by
    consent.revocation_reason = reason
    consent.updated_at = datetime.now(UTC).isoformat()
    consent.version += 1

    return consent


# =============================================================================
# Legacy Handling
# =============================================================================


@dataclass
class LegacyConsentStub:
    """Placeholder for voice profiles created without consent records.

    These cannot authorize new work but document the legacy state.
    """

    talent_id: str
    org_id: str
    legacy_reason: str = "Created before consent system (pre-Story 103)"
    requires_migration: bool = True


def create_legacy_stub(talent_id: str, org_id: str) -> LegacyConsentStub:
    """Create a legacy stub for a voice without consent.

    This does NOT authorize any work — it documents the gap.
    """
    return LegacyConsentStub(talent_id=talent_id, org_id=org_id)


def is_legacy_voice(talent_id: str, org_id: str) -> bool:
    """Check if a voice exists without any consent record."""
    return find_active_consent(org_id, talent_id) is None

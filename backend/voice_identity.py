"""Cloned Voice Identity Provenance — Story 104.

One authoritative record linking consent, source sample, provider result,
and every generated clip. Revocation blocks future use while preserving
historical lineage.

Lifecycle:
    initiated → sample_verified → provider_processing → finalized → active
    active → revoked | retired

Immutable provenance chain:
    consent_version → source_sample (asset+checksum) → provider_voice_id →
    creation_job → voice_identity → generated_clips

Finalization requires:
    1. Valid consent reference (not revoked)
    2. Verified source sample (asset exists, checksum matches)
    3. Provider voice ID returned (backend evidence, not client-supplied)
    4. Provider model/version persisted

Revocation:
    - Blocks ALL new clip generation
    - Does NOT retroactively delete existing clips (historical lineage preserved)
    - Propagates to all callers checking voice eligibility
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================


class VoiceStatus(str, Enum):
    INITIATED = "initiated"               # Clone request started
    SAMPLE_VERIFIED = "sample_verified"   # Source sample confirmed
    PROVIDER_PROCESSING = "provider_processing"  # Sent to provider
    FINALIZED = "finalized"               # Provider returned voice ID
    ACTIVE = "active"                     # Ready for production use
    REVOKED = "revoked"                   # Consent withdrawn / retired
    FAILED = "failed"                     # Provider or verification failure


# =============================================================================
# Data Structures
# =============================================================================


@dataclass
class SourceSampleEvidence:
    """Verified source sample used for voice cloning."""
    sample_asset_id: str = ""
    sample_upload_id: str = ""    # From talent_media_upload (Story 102)
    sample_checksum: str = ""     # SHA-256 at time of cloning
    sample_storage_key: str = ""
    content_type: str = ""
    duration_seconds: float = 0.0
    verified_at: float | None = None


@dataclass
class ProviderEvidence:
    """Evidence from the voice cloning provider."""
    provider_name: str = ""       # elevenlabs, play.ht, etc.
    provider_voice_id: str = ""   # The remote voice ID
    provider_model: str = ""      # Model used (e.g. "eleven_multilingual_v2")
    provider_model_version: str = ""
    creation_job_id: str = ""     # Job that triggered the cloning
    settings: dict[str, Any] = field(default_factory=dict)  # stability, clarity, etc.
    created_at: float | None = None


@dataclass
class ClonedVoiceIdentity:
    """Authoritative cloned voice identity with full provenance."""
    voice_id: str = field(default_factory=lambda: f"voice-{uuid.uuid4().hex[:12]}")
    org_id: str = ""
    talent_id: str = ""

    # Status
    status: VoiceStatus = VoiceStatus.INITIATED

    # Consent
    consent_ref: str = ""         # Reference to consent record
    consent_version: str = ""     # Version of consent at creation time
    consent_valid: bool = True    # Still valid (set False on revocation)

    # Source sample
    source_sample: SourceSampleEvidence = field(default_factory=SourceSampleEvidence)

    # Provider result
    provider_evidence: ProviderEvidence = field(default_factory=ProviderEvidence)

    # Identity metadata
    voice_name: str = ""
    created_by: str = ""
    created_at: float = field(default_factory=time.time)
    finalized_at: float | None = None
    revoked_at: float | None = None
    revoked_reason: str | None = None

    # Version (for retraining with new samples)
    version: int = 1

    # Generated clips reference this voice_id
    clip_count: int = 0

    @property
    def is_usable(self) -> bool:
        """Can this voice be used for new generation?"""
        return self.status == VoiceStatus.ACTIVE and self.consent_valid

    @property
    def is_finalized(self) -> bool:
        return self.status in (VoiceStatus.FINALIZED, VoiceStatus.ACTIVE)


# =============================================================================
# Store
# =============================================================================

_voices: dict[str, ClonedVoiceIdentity] = {}
_clip_refs: dict[str, str] = {}  # clip_asset_id → voice_id

# Simulation flags
_simulate_sample_deleted: bool = False
_simulate_provider_failure: bool = False


# =============================================================================
# Lifecycle API
# =============================================================================


def initiate_voice_clone(
    org_id: str,
    talent_id: str,
    consent_ref: str,
    consent_version: str,
    sample_asset_id: str,
    sample_checksum: str,
    sample_storage_key: str,
    created_by: str,
    voice_name: str = "",
    content_type: str = "audio/wav",
    duration_seconds: float = 0.0,
) -> ClonedVoiceIdentity:
    """Initiate a voice cloning request with consent and sample verification."""
    if not org_id or not talent_id or not created_by:
        raise ValueError("org_id, talent_id, and created_by are required")

    if not consent_ref:
        raise ConsentRequired("consent_ref is required for voice cloning")

    if not sample_asset_id or not sample_checksum:
        raise SampleInvalid("sample_asset_id and sample_checksum are required")

    voice = ClonedVoiceIdentity(
        org_id=org_id,
        talent_id=talent_id,
        consent_ref=consent_ref,
        consent_version=consent_version,
        voice_name=voice_name or f"{talent_id}_voice_v1",
        created_by=created_by,
        source_sample=SourceSampleEvidence(
            sample_asset_id=sample_asset_id,
            sample_checksum=sample_checksum,
            sample_storage_key=sample_storage_key,
            content_type=content_type,
            duration_seconds=duration_seconds,
        ),
    )

    _voices[voice.voice_id] = voice
    logger.info(f"VOICE_CLONE_INITIATED: id={voice.voice_id} talent={talent_id}")
    return voice


def verify_sample(voice_id: str, org_id: str) -> ClonedVoiceIdentity:
    """Verify the source sample exists and checksum matches."""
    voice = _get_voice(voice_id, org_id)

    if voice.status != VoiceStatus.INITIATED:
        return voice  # Idempotent

    if _simulate_sample_deleted:
        voice.status = VoiceStatus.FAILED
        raise SampleInvalid("Source sample has been deleted")

    # In production: verify asset exists in B2, checksum matches
    voice.source_sample.verified_at = time.time()
    voice.status = VoiceStatus.SAMPLE_VERIFIED

    logger.info(f"VOICE_SAMPLE_VERIFIED: id={voice_id}")
    return voice


def send_to_provider(voice_id: str, org_id: str, job_id: str) -> ClonedVoiceIdentity:
    """Mark voice as sent to cloning provider."""
    voice = _get_voice(voice_id, org_id)

    if voice.status != VoiceStatus.SAMPLE_VERIFIED:
        raise InvalidVoiceState(f"Cannot send to provider from state {voice.status.value}")

    voice.status = VoiceStatus.PROVIDER_PROCESSING
    voice.provider_evidence.creation_job_id = job_id

    return voice


def finalize_voice(
    voice_id: str,
    org_id: str,
    provider_voice_id: str,
    provider_name: str,
    provider_model: str,
    provider_model_version: str = "",
    settings: dict[str, Any] | None = None,
) -> ClonedVoiceIdentity:
    """Finalize voice clone with provider evidence.

    Finalization requires:
    1. Valid consent (not revoked)
    2. Verified source sample
    3. Provider voice ID (backend evidence)

    Idempotent: if already finalized with same provider_voice_id, returns existing.
    """
    voice = _get_voice(voice_id, org_id)

    # Idempotent check
    if voice.is_finalized and voice.provider_evidence.provider_voice_id == provider_voice_id:
        return voice

    # Gate 1: Consent still valid
    if not voice.consent_valid:
        raise ConsentRevoked("Consent has been revoked — cannot finalize voice")

    # Gate 2: Sample was verified
    if not voice.source_sample.verified_at:
        raise SampleInvalid("Source sample not verified — cannot finalize")

    # Gate 3: Must be in correct state
    if voice.status not in (VoiceStatus.PROVIDER_PROCESSING, VoiceStatus.SAMPLE_VERIFIED):
        if voice.status == VoiceStatus.FAILED:
            # Allow retry of failed finalization
            pass
        else:
            raise InvalidVoiceState(f"Cannot finalize from state {voice.status.value}")

    # Gate 4: Provider evidence required
    if not provider_voice_id:
        raise ProviderError("provider_voice_id is required (backend evidence)")

    if _simulate_provider_failure:
        voice.status = VoiceStatus.FAILED
        raise ProviderError("Provider cloning failed")

    # Finalize
    voice.provider_evidence = ProviderEvidence(
        provider_name=provider_name,
        provider_voice_id=provider_voice_id,
        provider_model=provider_model,
        provider_model_version=provider_model_version,
        creation_job_id=voice.provider_evidence.creation_job_id,
        settings=settings or {},
        created_at=time.time(),
    )
    voice.status = VoiceStatus.FINALIZED
    voice.finalized_at = time.time()

    logger.info(
        f"VOICE_FINALIZED: id={voice_id} provider={provider_name} "
        f"voice_id={provider_voice_id}"
    )
    return voice


def activate_voice(voice_id: str, org_id: str) -> ClonedVoiceIdentity:
    """Activate a finalized voice for production use."""
    voice = _get_voice(voice_id, org_id)

    if voice.status == VoiceStatus.ACTIVE:
        return voice  # Idempotent

    if voice.status != VoiceStatus.FINALIZED:
        raise InvalidVoiceState(f"Cannot activate from state {voice.status.value}")

    if not voice.consent_valid:
        raise ConsentRevoked("Cannot activate — consent has been revoked")

    voice.status = VoiceStatus.ACTIVE
    logger.info(f"VOICE_ACTIVATED: id={voice_id}")
    return voice


# =============================================================================
# Revocation
# =============================================================================


def revoke_voice(voice_id: str, org_id: str, reason: str) -> ClonedVoiceIdentity:
    """Revoke a voice identity — blocks all future use.

    Does NOT delete existing clips (historical lineage preserved).
    """
    voice = _get_voice(voice_id, org_id)

    if voice.status == VoiceStatus.REVOKED:
        return voice  # Idempotent

    voice.status = VoiceStatus.REVOKED
    voice.consent_valid = False
    voice.revoked_at = time.time()
    voice.revoked_reason = reason

    logger.info(f"VOICE_REVOKED: id={voice_id} reason={reason}")
    return voice


def check_voice_usable(voice_id: str, org_id: str) -> bool:
    """Check if a voice can be used for new generation."""
    voice = _voices.get(voice_id)
    if not voice or voice.org_id != org_id:
        return False
    return voice.is_usable


# =============================================================================
# Clip Lineage
# =============================================================================


def register_clip(voice_id: str, org_id: str, clip_asset_id: str) -> bool:
    """Register a generated clip against this voice identity.

    Clips can only be registered against usable voices.
    Historical clips remain linked even after revocation.
    """
    voice = _voices.get(voice_id)
    if not voice or voice.org_id != org_id:
        raise VoiceNotFound("Voice not found")

    if not voice.is_usable:
        raise VoiceRevoked("Cannot generate new clips with a revoked voice")

    voice.clip_count += 1
    _clip_refs[clip_asset_id] = voice_id
    return True


def get_clip_provenance(clip_asset_id: str, org_id: str) -> dict[str, Any] | None:
    """Get the voice provenance for a generated clip.

    Returns full lineage chain even for revoked voices (historical).
    """
    voice_id = _clip_refs.get(clip_asset_id)
    if not voice_id:
        return None

    voice = _voices.get(voice_id)
    if not voice or voice.org_id != org_id:
        return None

    return {
        "voice_id": voice.voice_id,
        "talent_id": voice.talent_id,
        "consent_ref": voice.consent_ref,
        "consent_version": voice.consent_version,
        "sample_asset_id": voice.source_sample.sample_asset_id,
        "sample_checksum": voice.source_sample.sample_checksum,
        "provider_name": voice.provider_evidence.provider_name,
        "provider_voice_id": voice.provider_evidence.provider_voice_id,
        "provider_model": voice.provider_evidence.provider_model,
        "voice_status": voice.status.value,
        "version": voice.version,
    }


# =============================================================================
# Query
# =============================================================================


def get_voice(voice_id: str, org_id: str) -> ClonedVoiceIdentity | None:
    """Get voice identity with tenant isolation."""
    voice = _voices.get(voice_id)
    if not voice or voice.org_id != org_id:
        return None
    return voice


def get_active_voice(talent_id: str, org_id: str) -> ClonedVoiceIdentity | None:
    """Get the active voice for a talent."""
    for v in _voices.values():
        if v.org_id == org_id and v.talent_id == talent_id and v.status == VoiceStatus.ACTIVE:
            return v
    return None


# =============================================================================
# Helpers
# =============================================================================


def _get_voice(voice_id: str, org_id: str) -> ClonedVoiceIdentity:
    voice = _voices.get(voice_id)
    if not voice or voice.org_id != org_id:
        raise VoiceNotFound(f"Voice {voice_id} not found")
    return voice


# =============================================================================
# Exceptions
# =============================================================================


class VoiceError(Exception):
    """Base voice identity error."""


class VoiceNotFound(VoiceError):
    """Voice not found or cross-tenant."""


class ConsentRequired(VoiceError):
    """Consent reference is required."""


class ConsentRevoked(VoiceError):
    """Consent has been revoked."""


class SampleInvalid(VoiceError):
    """Source sample is invalid or missing."""


class ProviderError(VoiceError):
    """Provider cloning failed."""


class InvalidVoiceState(VoiceError):
    """Invalid state transition."""


class VoiceRevoked(VoiceError):
    """Voice is revoked — cannot be used."""


# =============================================================================
# Testing Support
# =============================================================================


def _reset_store() -> None:
    global _simulate_sample_deleted, _simulate_provider_failure
    _voices.clear()
    _clip_refs.clear()
    _simulate_sample_deleted = False
    _simulate_provider_failure = False


def _inject_condition(condition: str, enabled: bool = True) -> None:
    global _simulate_sample_deleted, _simulate_provider_failure
    if condition == "sample_deleted":
        _simulate_sample_deleted = enabled
    elif condition == "provider_failure":
        _simulate_provider_failure = enabled

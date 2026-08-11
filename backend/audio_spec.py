"""Audio Generation Specification — Story 105.

One immutable specification drives both preview and final audio output.
The approved performance is reproducible: same spec → same voice behavior.

Preview and final share the same spec. Saving a preview promotes the exact
asset or regenerates from the recorded specification. Mutable UI state
cannot silently change approved settings.

Spec Fields (immutable after creation):
    - voice_id + voice_version: exact voice identity
    - consent_id + consent_version: consent at time of generation
    - provider + model: which TTS provider/model
    - text: the script/content
    - language + pronunciation_guide
    - speed, emotion, stability, similarity_boost, seed
    - intent: preview or final

Intent:
    PREVIEW — lightweight generation for approval (may use lower quality)
    FINAL   — production-grade output (requires persisted asset)

Promotion:
    A preview asset can be promoted to final without regeneration if the
    spec is unchanged and consent is still valid.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


# =============================================================================
# Generation Intent
# =============================================================================


class AudioIntent(StrEnum):
    PREVIEW = "preview"     # For approval, may be lower quality
    FINAL = "final"         # Production-grade, requires persisted asset


class AudioStatus(StrEnum):
    PENDING = "pending"
    GENERATING = "generating"
    COMPLETED = "completed"
    PROMOTED = "promoted"       # Preview promoted to final
    FAILED = "failed"
    CONSENT_REVOKED = "consent_revoked"


# =============================================================================
# Audio Generation Specification (immutable)
# =============================================================================


@dataclass
class AudioGenerationSpec:
    """Immutable specification for audio generation.

    Both preview and final use the SAME spec. Only intent differs.
    Once created, fields cannot be changed (new spec required for changes).
    """

    # Identity
    spec_id: str = field(default_factory=lambda: f"aspec-{uuid.uuid4().hex[:12]}")
    org_id: str = ""
    user_id: str = ""

    # Voice identity (exact version)
    voice_id: str = ""
    voice_version: str = ""
    talent_id: str = ""

    # Consent (exact version at generation time)
    consent_id: str = ""
    consent_version: int = 0

    # Provider
    provider: str = ""              # elevenlabs, moss, custom
    model: str = ""                 # e.g., "eleven_multilingual_v2"

    # Content
    text: str = ""
    language: str = "en"
    pronunciation_guide: str = ""   # SSML or phonetic hints

    # Voice parameters
    speed: float = 1.0              # 0.5-2.0
    emotion: str = ""               # neutral, happy, sad, excited...
    stability: float = 0.5          # 0-1 (provider-specific)
    similarity_boost: float = 0.75  # 0-1 (provider-specific)
    seed: int | None = None         # For reproducibility (if provider supports)

    # Intent
    intent: AudioIntent = AudioIntent.PREVIEW

    # Hash (computed)
    spec_hash: str = ""

    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    is_immutable: bool = True

    def compute_hash(self) -> str:
        """Compute deterministic hash of the specification.

        Same voice + text + settings = same hash regardless of intent.
        Intent is NOT part of the hash (preview and final match).
        """
        parts = [
            self.voice_id, self.voice_version,
            self.provider, self.model,
            self.text, self.language, self.pronunciation_guide,
            str(self.speed), self.emotion,
            str(self.stability), str(self.similarity_boost),
            str(self.seed or 0),
        ]
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:24]

    def to_dict(self) -> dict:
        return {
            "spec_id": self.spec_id,
            "org_id": self.org_id,
            "voice_id": self.voice_id,
            "voice_version": self.voice_version,
            "talent_id": self.talent_id,
            "consent_id": self.consent_id,
            "consent_version": self.consent_version,
            "provider": self.provider,
            "model": self.model,
            "text": self.text,
            "language": self.language,
            "speed": self.speed,
            "emotion": self.emotion,
            "stability": self.stability,
            "similarity_boost": self.similarity_boost,
            "seed": self.seed,
            "intent": self.intent.value,
            "spec_hash": self.spec_hash,
            "created_at": self.created_at,
        }


def finalize_spec(spec: AudioGenerationSpec) -> AudioGenerationSpec:
    """Compute hash and lock the specification."""
    spec.spec_hash = spec.compute_hash()
    spec.is_immutable = True
    return spec


# =============================================================================
# Audio Generation Job
# =============================================================================


@dataclass
class AudioGenerationJob:
    """A durable job linked to an immutable audio spec."""

    job_id: str = field(default_factory=lambda: f"ajob-{uuid.uuid4().hex[:12]}")
    spec_id: str = ""
    spec_hash: str = ""
    org_id: str = ""
    user_id: str = ""
    intent: AudioIntent = AudioIntent.PREVIEW
    status: AudioStatus = AudioStatus.PENDING

    # Output
    asset_id: str | None = None
    output_url: str | None = None

    # Timing
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    completed_at: str | None = None

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "spec_id": self.spec_id,
            "spec_hash": self.spec_hash,
            "intent": self.intent.value,
            "status": self.status.value,
            "asset_id": self.asset_id,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }


# =============================================================================
# Preview Promotion
# =============================================================================


class PromotionError(Exception):
    def __init__(self, message: str, code: str = "PROMOTION_FAILED"):
        self.message = message
        self.code = code
        super().__init__(message)


def promote_preview_to_final(
    *,
    preview_job: AudioGenerationJob,
    spec: AudioGenerationSpec,
    consent_still_valid: bool,
) -> AudioGenerationJob:
    """Promote a preview asset to final without regeneration.

    Requirements:
    1. Preview must be COMPLETED with an asset_id
    2. Consent must still be valid
    3. Spec must match (same spec_hash)

    Idempotent: promoting already-promoted job returns it unchanged.
    """
    if preview_job.status == AudioStatus.PROMOTED:
        return preview_job  # Idempotent

    if preview_job.status != AudioStatus.COMPLETED:
        raise PromotionError(
            f"Cannot promote job in status '{preview_job.status.value}' (must be completed)"
        )

    if not preview_job.asset_id:
        raise PromotionError("Preview job has no asset to promote")

    if not consent_still_valid:
        raise PromotionError(
            "Consent is no longer valid — cannot promote to final",
            code="CONSENT_INVALID",
        )

    if preview_job.spec_hash != spec.spec_hash:
        raise PromotionError(
            "Spec hash mismatch — settings changed since preview",
            code="SPEC_DRIFT",
        )

    preview_job.status = AudioStatus.PROMOTED
    preview_job.intent = AudioIntent.FINAL
    preview_job.completed_at = datetime.now(UTC).isoformat()
    return preview_job


# =============================================================================
# Regeneration from Spec
# =============================================================================


def regenerate_from_spec(
    spec: AudioGenerationSpec,
    *,
    intent: AudioIntent = AudioIntent.FINAL,
    consent_still_valid: bool = True,
) -> AudioGenerationJob:
    """Create a new generation job from the same immutable spec.

    Used when the creator wants a fresh generation (not promoting preview).
    Same spec guarantees same voice configuration.
    """
    if not consent_still_valid:
        raise PromotionError(
            "Consent is no longer valid — cannot regenerate",
            code="CONSENT_INVALID",
        )

    job = AudioGenerationJob(
        spec_id=spec.spec_id,
        spec_hash=spec.spec_hash,
        org_id=spec.org_id,
        user_id=spec.user_id,
        intent=intent,
        status=AudioStatus.PENDING,
    )
    return job


# =============================================================================
# Setting Drift Detection
# =============================================================================


def detect_setting_drift(
    original_spec: AudioGenerationSpec,
    current_ui_state: dict,
) -> list[str]:
    """Detect if UI state has drifted from the approved spec.

    Returns list of changed fields. Empty = no drift.
    Prevents mutable UI from silently changing settings.
    """
    drifted: list[str] = []

    field_checks = [
        ("text", original_spec.text),
        ("speed", original_spec.speed),
        ("emotion", original_spec.emotion),
        ("stability", original_spec.stability),
        ("similarity_boost", original_spec.similarity_boost),
        ("language", original_spec.language),
        ("voice_id", original_spec.voice_id),
    ]

    for field_name, spec_value in field_checks:
        ui_value = current_ui_state.get(field_name)
        if ui_value is not None and ui_value != spec_value:
            drifted.append(field_name)

    return drifted


# =============================================================================
# Spec Comparison (preview vs final parity)
# =============================================================================


def specs_match(spec_a: AudioGenerationSpec, spec_b: AudioGenerationSpec) -> bool:
    """Check if two specs produce the same voice output.

    Compares content hashes (intent-independent).
    """
    return spec_a.compute_hash() == spec_b.compute_hash()


def create_final_from_preview_spec(preview_spec: AudioGenerationSpec) -> AudioGenerationSpec:
    """Create a final-intent spec from a preview spec.

    All settings identical — only intent changes.
    This is used when regenerating (not promoting the preview asset).
    """
    final_spec = AudioGenerationSpec(
        org_id=preview_spec.org_id,
        user_id=preview_spec.user_id,
        voice_id=preview_spec.voice_id,
        voice_version=preview_spec.voice_version,
        talent_id=preview_spec.talent_id,
        consent_id=preview_spec.consent_id,
        consent_version=preview_spec.consent_version,
        provider=preview_spec.provider,
        model=preview_spec.model,
        text=preview_spec.text,
        language=preview_spec.language,
        pronunciation_guide=preview_spec.pronunciation_guide,
        speed=preview_spec.speed,
        emotion=preview_spec.emotion,
        stability=preview_spec.stability,
        similarity_boost=preview_spec.similarity_boost,
        seed=preview_spec.seed,
        intent=AudioIntent.FINAL,
    )
    finalize_spec(final_spec)
    return final_spec

"""Audio Generation Specification Tests (Story 105).

Proves: spec parity between preview/final, consent validation, promotion
idempotency, setting drift prevention, and revocation handling.

Run with:
    pytest tests/unit/test_audio_spec.py -v
"""
from __future__ import annotations

import pytest

from backend.audio_spec import (
    AudioGenerationJob,
    AudioGenerationSpec,
    AudioIntent,
    AudioStatus,
    PromotionError,
    create_final_from_preview_spec,
    detect_setting_drift,
    finalize_spec,
    promote_preview_to_final,
    regenerate_from_spec,
    specs_match,
)


# =============================================================================
# Helpers
# =============================================================================


def _make_spec(intent: AudioIntent = AudioIntent.PREVIEW, **overrides) -> AudioGenerationSpec:
    defaults = {
        "org_id": "org-123",
        "user_id": "user-456",
        "voice_id": "voice-melissa",
        "voice_version": "v2",
        "talent_id": "talent-1",
        "consent_id": "consent-abc",
        "consent_version": 1,
        "provider": "elevenlabs",
        "model": "eleven_multilingual_v2",
        "text": "Welcome to AI Studio, where creativity meets technology.",
        "language": "en",
        "speed": 1.0,
        "emotion": "neutral",
        "stability": 0.5,
        "similarity_boost": 0.75,
        "seed": 42,
        "intent": intent,
    }
    defaults.update(overrides)
    spec = AudioGenerationSpec(**defaults)
    finalize_spec(spec)
    return spec


def _completed_preview(spec: AudioGenerationSpec) -> AudioGenerationJob:
    return AudioGenerationJob(
        spec_id=spec.spec_id,
        spec_hash=spec.spec_hash,
        org_id=spec.org_id,
        user_id=spec.user_id,
        intent=AudioIntent.PREVIEW,
        status=AudioStatus.COMPLETED,
        asset_id="asset-preview-1",
    )


# =============================================================================
# Spec Parity (Preview = Final)
# =============================================================================


class TestSpecParity:

    @pytest.mark.unit
    def test_preview_and_final_same_hash(self):
        """Preview and final specs with same settings produce same hash."""
        preview = _make_spec(intent=AudioIntent.PREVIEW)
        final = _make_spec(intent=AudioIntent.FINAL)
        assert preview.spec_hash == final.spec_hash

    @pytest.mark.unit
    def test_specs_match_function(self):
        """specs_match confirms parity regardless of intent."""
        preview = _make_spec(intent=AudioIntent.PREVIEW)
        final = _make_spec(intent=AudioIntent.FINAL)
        assert specs_match(preview, final) is True

    @pytest.mark.unit
    def test_different_text_different_hash(self):
        """Different text produces different hash."""
        spec_a = _make_spec(text="Hello world")
        spec_b = _make_spec(text="Goodbye world")
        assert spec_a.spec_hash != spec_b.spec_hash

    @pytest.mark.unit
    def test_different_voice_different_hash(self):
        """Different voice produces different hash."""
        spec_a = _make_spec(voice_id="voice-A")
        spec_b = _make_spec(voice_id="voice-B")
        assert spec_a.spec_hash != spec_b.spec_hash

    @pytest.mark.unit
    def test_different_speed_different_hash(self):
        """Different speed produces different hash."""
        spec_a = _make_spec(speed=1.0)
        spec_b = _make_spec(speed=1.5)
        assert spec_a.spec_hash != spec_b.spec_hash

    @pytest.mark.unit
    def test_create_final_from_preview_matches(self):
        """Final spec created from preview has same hash."""
        preview = _make_spec(intent=AudioIntent.PREVIEW)
        final = create_final_from_preview_spec(preview)
        assert final.intent == AudioIntent.FINAL
        assert final.spec_hash == preview.spec_hash

    @pytest.mark.unit
    def test_hash_deterministic(self):
        """Same inputs always produce same hash."""
        spec1 = _make_spec()
        spec2 = _make_spec()
        assert spec1.spec_hash == spec2.spec_hash

    @pytest.mark.unit
    def test_hash_length(self):
        """Hash is 24 hex characters."""
        spec = _make_spec()
        assert len(spec.spec_hash) == 24
        assert all(c in "0123456789abcdef" for c in spec.spec_hash)


# =============================================================================
# Consent Validation
# =============================================================================


class TestConsentValidation:

    @pytest.mark.unit
    def test_promotion_with_valid_consent(self):
        """Promotion succeeds when consent is still valid."""
        spec = _make_spec()
        job = _completed_preview(spec)
        result = promote_preview_to_final(
            preview_job=job, spec=spec, consent_still_valid=True,
        )
        assert result.status == AudioStatus.PROMOTED

    @pytest.mark.unit
    def test_promotion_blocked_consent_revoked(self):
        """Promotion blocked when consent is revoked."""
        spec = _make_spec()
        job = _completed_preview(spec)
        with pytest.raises(PromotionError) as exc_info:
            promote_preview_to_final(
                preview_job=job, spec=spec, consent_still_valid=False,
            )
        assert exc_info.value.code == "CONSENT_INVALID"

    @pytest.mark.unit
    def test_regeneration_blocked_consent_revoked(self):
        """Regeneration blocked when consent is revoked."""
        spec = _make_spec()
        with pytest.raises(PromotionError) as exc_info:
            regenerate_from_spec(spec, consent_still_valid=False)
        assert exc_info.value.code == "CONSENT_INVALID"

    @pytest.mark.unit
    def test_consent_id_preserved_in_spec(self):
        """Consent ID and version are preserved in the spec."""
        spec = _make_spec(consent_id="consent-xyz", consent_version=3)
        assert spec.consent_id == "consent-xyz"
        assert spec.consent_version == 3


# =============================================================================
# Promotion Idempotency
# =============================================================================


class TestPromotionIdempotency:

    @pytest.mark.unit
    def test_promote_twice_is_noop(self):
        """Promoting already-promoted job returns without change."""
        spec = _make_spec()
        job = _completed_preview(spec)
        promote_preview_to_final(preview_job=job, spec=spec, consent_still_valid=True)
        assert job.status == AudioStatus.PROMOTED

        # Promote again
        result = promote_preview_to_final(
            preview_job=job, spec=spec, consent_still_valid=True,
        )
        assert result.status == AudioStatus.PROMOTED  # No error

    @pytest.mark.unit
    def test_promote_pending_fails(self):
        """Cannot promote a job that hasn't completed."""
        spec = _make_spec()
        job = AudioGenerationJob(
            spec_id=spec.spec_id, spec_hash=spec.spec_hash,
            status=AudioStatus.PENDING,
        )
        with pytest.raises(PromotionError):
            promote_preview_to_final(preview_job=job, spec=spec, consent_still_valid=True)

    @pytest.mark.unit
    def test_promote_without_asset_fails(self):
        """Cannot promote job without an asset."""
        spec = _make_spec()
        job = AudioGenerationJob(
            spec_id=spec.spec_id, spec_hash=spec.spec_hash,
            status=AudioStatus.COMPLETED, asset_id=None,
        )
        with pytest.raises(PromotionError) as exc_info:
            promote_preview_to_final(preview_job=job, spec=spec, consent_still_valid=True)
        assert "no asset" in exc_info.value.message.lower()


# =============================================================================
# Setting Drift Prevention
# =============================================================================


class TestSettingDrift:

    @pytest.mark.unit
    def test_no_drift_detected(self):
        """Matching UI state produces no drift."""
        spec = _make_spec()
        ui_state = {
            "text": spec.text,
            "speed": spec.speed,
            "emotion": spec.emotion,
            "voice_id": spec.voice_id,
        }
        drifted = detect_setting_drift(spec, ui_state)
        assert drifted == []

    @pytest.mark.unit
    def test_text_change_detected(self):
        """Changed text is detected as drift."""
        spec = _make_spec(text="Original text")
        ui_state = {"text": "Modified text"}
        drifted = detect_setting_drift(spec, ui_state)
        assert "text" in drifted

    @pytest.mark.unit
    def test_speed_change_detected(self):
        """Changed speed is detected."""
        spec = _make_spec(speed=1.0)
        ui_state = {"speed": 1.5}
        drifted = detect_setting_drift(spec, ui_state)
        assert "speed" in drifted

    @pytest.mark.unit
    def test_multiple_drift_fields(self):
        """Multiple changes all reported."""
        spec = _make_spec(text="A", speed=1.0, emotion="neutral")
        ui_state = {"text": "B", "speed": 2.0, "emotion": "happy"}
        drifted = detect_setting_drift(spec, ui_state)
        assert "text" in drifted
        assert "speed" in drifted
        assert "emotion" in drifted

    @pytest.mark.unit
    def test_missing_ui_fields_not_drift(self):
        """Fields absent from UI state are not flagged as drift."""
        spec = _make_spec()
        ui_state = {}  # Nothing submitted
        drifted = detect_setting_drift(spec, ui_state)
        assert drifted == []

    @pytest.mark.unit
    def test_spec_hash_mismatch_blocks_promotion(self):
        """Changed settings (different hash) prevent promotion."""
        original_spec = _make_spec(text="Approved text")
        job = _completed_preview(original_spec)

        modified_spec = _make_spec(text="Changed text")
        with pytest.raises(PromotionError) as exc_info:
            promote_preview_to_final(
                preview_job=job, spec=modified_spec, consent_still_valid=True,
            )
        assert exc_info.value.code == "SPEC_DRIFT"


# =============================================================================
# Regeneration
# =============================================================================


class TestRegeneration:

    @pytest.mark.unit
    def test_regenerate_creates_new_job(self):
        """Regeneration creates a new pending job from same spec."""
        spec = _make_spec()
        job = regenerate_from_spec(spec, intent=AudioIntent.FINAL)
        assert job.status == AudioStatus.PENDING
        assert job.spec_id == spec.spec_id
        assert job.spec_hash == spec.spec_hash
        assert job.intent == AudioIntent.FINAL

    @pytest.mark.unit
    def test_regenerate_preserves_spec_reference(self):
        """Regenerated job references the original spec."""
        spec = _make_spec()
        job = regenerate_from_spec(spec)
        assert job.spec_id == spec.spec_id

    @pytest.mark.unit
    def test_regenerate_with_consent_valid(self):
        """Regeneration with valid consent succeeds."""
        spec = _make_spec()
        job = regenerate_from_spec(spec, consent_still_valid=True)
        assert job.status == AudioStatus.PENDING


# =============================================================================
# Serialization
# =============================================================================


class TestSerialization:

    @pytest.mark.unit
    def test_spec_serializable(self):
        """AudioGenerationSpec.to_dict() is JSON-serializable."""
        import json
        spec = _make_spec()
        json.dumps(spec.to_dict())

    @pytest.mark.unit
    def test_job_serializable(self):
        """AudioGenerationJob.to_dict() is JSON-serializable."""
        import json
        spec = _make_spec()
        job = _completed_preview(spec)
        json.dumps(job.to_dict())

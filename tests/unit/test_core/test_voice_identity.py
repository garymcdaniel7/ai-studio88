"""Cloned voice identity provenance tests — Story 104.

Tests prove:
  - No consent blocks finalization
  - Sample deleted blocks verification
  - Provider failure handled
  - Duplicate callback is idempotent
  - Revocation blocks new clip generation
  - Historical lineage preserved after revocation
  - Cross-tenant access rejected
  - Idempotent finalization
  - Full lifecycle: initiate → verify → provider → finalize → activate
  - Clip provenance traceable
"""

import pytest

from backend.voice_identity import (
    ConsentRequired,
    ConsentRevoked,
    InvalidVoiceState,
    ProviderError,
    SampleInvalid,
    VoiceNotFound,
    VoiceRevoked,
    VoiceStatus,
    _inject_condition,
    _reset_store,
    activate_voice,
    check_voice_usable,
    finalize_voice,
    get_active_voice,
    get_clip_provenance,
    get_voice,
    initiate_voice_clone,
    register_clip,
    revoke_voice,
    send_to_provider,
    verify_sample,
)


@pytest.fixture(autouse=True)
def clean():
    _reset_store()
    yield
    _reset_store()


ORG = "org-test-001"
OTHER_ORG = "org-other-999"
TALENT = "talent-001"
USER = "user-001"


def _initiated_voice(**overrides) -> str:
    """Create an initiated voice clone and return its ID."""
    defaults = dict(
        org_id=ORG,
        talent_id=TALENT,
        consent_ref="consent-voice-001",
        consent_version="v1",
        sample_asset_id="sample-ast-001",
        sample_checksum="abc123def456789",
        sample_storage_key=f"{ORG}/voice_sample/{TALENT}/sample.wav",
        created_by=USER,
        content_type="audio/wav",
        duration_seconds=30.0,
    )
    defaults.update(overrides)
    v = initiate_voice_clone(**defaults)
    return v.voice_id


def _finalized_voice() -> str:
    """Create a fully finalized voice."""
    vid = _initiated_voice()
    verify_sample(vid, ORG)
    send_to_provider(vid, ORG, "job-clone-001")
    finalize_voice(vid, ORG, "el-voice-abc", "elevenlabs", "eleven_multilingual_v2", "2.0")
    return vid


def _active_voice() -> str:
    """Create an active voice."""
    vid = _finalized_voice()
    activate_voice(vid, ORG)
    return vid


# =============================================================================
# Full Lifecycle
# =============================================================================


@pytest.mark.unit
class TestFullLifecycle:

    def test_complete_lifecycle(self):
        vid = _initiated_voice()
        v = get_voice(vid, ORG)
        assert v.status == VoiceStatus.INITIATED

        verify_sample(vid, ORG)
        assert v.status == VoiceStatus.SAMPLE_VERIFIED

        send_to_provider(vid, ORG, "job-001")
        assert v.status == VoiceStatus.PROVIDER_PROCESSING

        finalize_voice(vid, ORG, "prov-voice-123", "elevenlabs", "v2", "2.0")
        assert v.status == VoiceStatus.FINALIZED
        assert v.provider_evidence.provider_voice_id == "prov-voice-123"

        activate_voice(vid, ORG)
        assert v.status == VoiceStatus.ACTIVE
        assert v.is_usable


# =============================================================================
# Consent Required
# =============================================================================


@pytest.mark.unit
class TestConsentRequired:

    def test_no_consent_blocks_initiation(self):
        with pytest.raises(ConsentRequired):
            initiate_voice_clone(ORG, TALENT, "", "v1", "s1", "hash", "key", USER)

    def test_revoked_consent_blocks_finalization(self):
        vid = _initiated_voice()
        verify_sample(vid, ORG)
        send_to_provider(vid, ORG, "j1")
        # Revoke consent
        v = get_voice(vid, ORG)
        v.consent_valid = False
        with pytest.raises(ConsentRevoked):
            finalize_voice(vid, ORG, "pv-1", "el", "v2")

    def test_revoked_consent_blocks_activation(self):
        vid = _finalized_voice()
        v = get_voice(vid, ORG)
        v.consent_valid = False
        with pytest.raises(ConsentRevoked):
            activate_voice(vid, ORG)


# =============================================================================
# Sample Deleted
# =============================================================================


@pytest.mark.unit
class TestSampleDeleted:

    def test_deleted_sample_blocks_verification(self):
        _inject_condition("sample_deleted")
        vid = _initiated_voice()
        with pytest.raises(SampleInvalid):
            verify_sample(vid, ORG)
        v = get_voice(vid, ORG)
        assert v.status == VoiceStatus.FAILED


# =============================================================================
# Provider Failure
# =============================================================================


@pytest.mark.unit
class TestProviderFailure:

    def test_provider_failure_marks_failed(self):
        _inject_condition("provider_failure")
        vid = _initiated_voice()
        verify_sample(vid, ORG)
        send_to_provider(vid, ORG, "j1")
        with pytest.raises(ProviderError):
            finalize_voice(vid, ORG, "pv-1", "el", "v2")
        v = get_voice(vid, ORG)
        assert v.status == VoiceStatus.FAILED

    def test_no_provider_voice_id_rejected(self):
        vid = _initiated_voice()
        verify_sample(vid, ORG)
        send_to_provider(vid, ORG, "j1")
        with pytest.raises(ProviderError, match="provider_voice_id"):
            finalize_voice(vid, ORG, "", "el", "v2")


# =============================================================================
# Duplicate Callback (Idempotent)
# =============================================================================


@pytest.mark.unit
class TestDuplicateCallback:

    def test_duplicate_finalization_idempotent(self):
        vid = _initiated_voice()
        verify_sample(vid, ORG)
        send_to_provider(vid, ORG, "j1")
        finalize_voice(vid, ORG, "pv-123", "el", "v2")
        # Second call with same provider_voice_id — idempotent
        v = finalize_voice(vid, ORG, "pv-123", "el", "v2")
        assert v.status == VoiceStatus.FINALIZED

    def test_duplicate_activation_idempotent(self):
        vid = _finalized_voice()
        activate_voice(vid, ORG)
        v = activate_voice(vid, ORG)
        assert v.status == VoiceStatus.ACTIVE


# =============================================================================
# Revocation
# =============================================================================


@pytest.mark.unit
class TestRevocation:

    def test_revocation_blocks_new_clips(self):
        vid = _active_voice()
        revoke_voice(vid, ORG, "consent withdrawn")
        with pytest.raises(VoiceRevoked):
            register_clip(vid, ORG, "new-clip-001")

    def test_revocation_idempotent(self):
        vid = _active_voice()
        revoke_voice(vid, ORG, "reason1")
        v = revoke_voice(vid, ORG, "reason2")
        assert v.status == VoiceStatus.REVOKED

    def test_check_usable_returns_false_after_revoke(self):
        vid = _active_voice()
        assert check_voice_usable(vid, ORG) is True
        revoke_voice(vid, ORG, "done")
        assert check_voice_usable(vid, ORG) is False


# =============================================================================
# Historical Lineage
# =============================================================================


@pytest.mark.unit
class TestHistoricalLineage:

    def test_clip_provenance_preserved_after_revocation(self):
        vid = _active_voice()
        register_clip(vid, ORG, "clip-001")
        revoke_voice(vid, ORG, "consent revoked")

        # Historical clip still has provenance
        prov = get_clip_provenance("clip-001", ORG)
        assert prov is not None
        assert prov["voice_id"] == vid
        assert prov["consent_ref"] == "consent-voice-001"
        assert prov["voice_status"] == "revoked"

    def test_clip_links_to_voice(self):
        vid = _active_voice()
        register_clip(vid, ORG, "clip-002")
        prov = get_clip_provenance("clip-002", ORG)
        assert prov["provider_voice_id"] == "el-voice-abc"
        assert prov["sample_asset_id"] == "sample-ast-001"


# =============================================================================
# Cross-Tenant
# =============================================================================


@pytest.mark.unit
class TestCrossTenant:

    def test_cross_tenant_get_returns_none(self):
        vid = _initiated_voice()
        assert get_voice(vid, OTHER_ORG) is None

    def test_cross_tenant_finalize_raises(self):
        vid = _initiated_voice()
        with pytest.raises(VoiceNotFound):
            finalize_voice(vid, OTHER_ORG, "pv-1", "el", "v2")

    def test_cross_tenant_clip_provenance_none(self):
        vid = _active_voice()
        register_clip(vid, ORG, "clip-x")
        assert get_clip_provenance("clip-x", OTHER_ORG) is None

    def test_cross_tenant_register_clip_raises(self):
        vid = _active_voice()
        with pytest.raises(VoiceNotFound):
            register_clip(vid, OTHER_ORG, "evil-clip")

    def test_cross_tenant_check_usable_false(self):
        vid = _active_voice()
        assert check_voice_usable(vid, OTHER_ORG) is False


# =============================================================================
# Active Voice Query
# =============================================================================


@pytest.mark.unit
class TestActiveVoiceQuery:

    def test_get_active_voice_for_talent(self):
        _active_voice()
        v = get_active_voice(TALENT, ORG)
        assert v is not None
        assert v.talent_id == TALENT
        assert v.status == VoiceStatus.ACTIVE

    def test_no_active_voice_returns_none(self):
        _initiated_voice()
        assert get_active_voice(TALENT, ORG) is None

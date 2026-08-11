"""Talent media upload classification tests — Story 102.

Tests prove:
  - Role misuse rejected (voice as avatar, image as voice)
  - MIME mismatch rejected
  - Consent required for training_ref and voice_sample
  - Cross-tenant access rejected
  - Duplicate upload returns existing (idempotent)
  - Reclassification is audited
  - Corrupt file rejected
  - Partial failure tracked (reconciling state)
  - Downstream role access enforced
  - File size limit enforced
  - Happy path for each role
"""

import pytest

from backend.talent_media_upload import (
    AuthorizationError,
    MediaRole,
    UploadStatus,
    UploadValidationError,
    _inject_condition,
    _reset_store,
    authorize_role_access,
    get_talent_uploads,
    get_training_references,
    get_upload,
    get_voice_samples,
    reclassify_upload,
    upload_talent_media,
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


# =============================================================================
# Happy Path (each role)
# =============================================================================


@pytest.mark.unit
class TestHappyPath:

    def test_avatar_upload(self):
        u = upload_talent_media(ORG, TALENT, MediaRole.AVATAR, "photo.jpg",
                                "image/jpeg", 500_000, uploaded_by=USER)
        assert u.status == UploadStatus.ACCEPTED
        assert u.role == MediaRole.AVATAR
        assert ORG in u.storage_key

    def test_training_ref_with_consent(self):
        u = upload_talent_media(ORG, TALENT, MediaRole.TRAINING_REF, "ref.png",
                                "image/png", 2_000_000, uploaded_by=USER,
                                consent_ref="consent-001")
        assert u.status == UploadStatus.ACCEPTED

    def test_wardrobe_ref(self):
        u = upload_talent_media(ORG, TALENT, MediaRole.WARDROBE_REF, "outfit.jpg",
                                "image/jpeg", 1_000_000, uploaded_by=USER)
        assert u.status == UploadStatus.ACCEPTED

    def test_voice_sample_with_consent(self):
        u = upload_talent_media(ORG, TALENT, MediaRole.VOICE_SAMPLE, "voice.wav",
                                "audio/wav", 5_000_000, uploaded_by=USER,
                                consent_ref="consent-voice-001")
        assert u.status == UploadStatus.ACCEPTED

    def test_continuity_ref_image(self):
        u = upload_talent_media(ORG, TALENT, MediaRole.CONTINUITY_REF, "pose.jpg",
                                "image/jpeg", 3_000_000, uploaded_by=USER)
        assert u.status == UploadStatus.ACCEPTED

    def test_continuity_ref_video(self):
        u = upload_talent_media(ORG, TALENT, MediaRole.CONTINUITY_REF, "clip.mp4",
                                "video/mp4", 50_000_000, uploaded_by=USER)
        assert u.status == UploadStatus.ACCEPTED


# =============================================================================
# Role Misuse (MIME Mismatch)
# =============================================================================


@pytest.mark.unit
class TestRoleMisuse:

    def test_audio_rejected_for_avatar(self):
        u = upload_talent_media(ORG, TALENT, MediaRole.AVATAR, "voice.mp3",
                                "audio/mpeg", 1_000_000, uploaded_by=USER)
        assert u.status == UploadStatus.REJECTED
        assert "Invalid content type" in u.rejection_reason

    def test_image_rejected_for_voice_sample(self):
        u = upload_talent_media(ORG, TALENT, MediaRole.VOICE_SAMPLE, "photo.jpg",
                                "image/jpeg", 1_000_000, uploaded_by=USER,
                                consent_ref="c-1")
        assert u.status == UploadStatus.REJECTED

    def test_video_rejected_for_training_ref(self):
        u = upload_talent_media(ORG, TALENT, MediaRole.TRAINING_REF, "clip.mp4",
                                "video/mp4", 5_000_000, uploaded_by=USER,
                                consent_ref="c-1")
        assert u.status == UploadStatus.REJECTED


# =============================================================================
# Consent Required
# =============================================================================


@pytest.mark.unit
class TestConsentRequired:

    def test_training_ref_without_consent_rejected(self):
        u = upload_talent_media(ORG, TALENT, MediaRole.TRAINING_REF, "ref.jpg",
                                "image/jpeg", 1_000_000, uploaded_by=USER)
        assert u.status == UploadStatus.REJECTED
        assert "Consent" in u.rejection_reason

    def test_voice_sample_without_consent_rejected(self):
        u = upload_talent_media(ORG, TALENT, MediaRole.VOICE_SAMPLE, "voice.wav",
                                "audio/wav", 2_000_000, uploaded_by=USER)
        assert u.status == UploadStatus.REJECTED
        assert "Consent" in u.rejection_reason

    def test_avatar_without_consent_accepted(self):
        u = upload_talent_media(ORG, TALENT, MediaRole.AVATAR, "pic.jpg",
                                "image/jpeg", 500_000, uploaded_by=USER)
        assert u.status == UploadStatus.ACCEPTED


# =============================================================================
# Cross-Tenant
# =============================================================================


@pytest.mark.unit
class TestCrossTenant:

    def test_cross_tenant_get_returns_none(self):
        u = upload_talent_media(ORG, TALENT, MediaRole.AVATAR, "pic.jpg",
                                "image/jpeg", 500_000, uploaded_by=USER)
        assert get_upload(u.upload_id, OTHER_ORG) is None

    def test_cross_tenant_list_empty(self):
        upload_talent_media(ORG, TALENT, MediaRole.AVATAR, "pic.jpg",
                            "image/jpeg", 500_000, uploaded_by=USER)
        assert get_talent_uploads(OTHER_ORG, TALENT) == []


# =============================================================================
# Duplicate (Idempotent)
# =============================================================================


@pytest.mark.unit
class TestDuplicate:

    def test_duplicate_returns_existing(self):
        content = b"same file content"
        u1 = upload_talent_media(ORG, TALENT, MediaRole.AVATAR, "pic.jpg",
                                  "image/jpeg", len(content), file_content=content,
                                  uploaded_by=USER)
        u2 = upload_talent_media(ORG, TALENT, MediaRole.AVATAR, "pic.jpg",
                                  "image/jpeg", len(content), file_content=content,
                                  uploaded_by=USER)
        assert u1.upload_id == u2.upload_id


# =============================================================================
# Reclassification
# =============================================================================


@pytest.mark.unit
class TestReclassification:

    def test_reclassify_is_audited(self):
        u = upload_talent_media(ORG, TALENT, MediaRole.CONTINUITY_REF, "pose.jpg",
                                "image/jpeg", 1_000_000, uploaded_by=USER)
        result = reclassify_upload(u.upload_id, ORG, MediaRole.WARDROBE_REF, "admin-001")
        assert result.role == MediaRole.WARDROBE_REF
        assert result.original_role == MediaRole.CONTINUITY_REF
        assert result.reclassified is True
        assert result.reclassified_by == "admin-001"

    def test_reclassify_to_invalid_mime_rejected(self):
        u = upload_talent_media(ORG, TALENT, MediaRole.CONTINUITY_REF, "clip.mp4",
                                "video/mp4", 5_000_000, uploaded_by=USER)
        with pytest.raises(UploadValidationError, match="not valid"):
            reclassify_upload(u.upload_id, ORG, MediaRole.AVATAR, "admin")

    def test_reclassify_to_consent_role_without_consent_rejected(self):
        u = upload_talent_media(ORG, TALENT, MediaRole.CONTINUITY_REF, "face.jpg",
                                "image/jpeg", 1_000_000, uploaded_by=USER)
        with pytest.raises(UploadValidationError, match="Consent"):
            reclassify_upload(u.upload_id, ORG, MediaRole.TRAINING_REF, "admin")

    def test_reclassify_without_actor_raises(self):
        u = upload_talent_media(ORG, TALENT, MediaRole.AVATAR, "pic.jpg",
                                "image/jpeg", 500_000, uploaded_by=USER)
        with pytest.raises(AuthorizationError):
            reclassify_upload(u.upload_id, ORG, MediaRole.WARDROBE_REF, "")


# =============================================================================
# Corrupt File
# =============================================================================


@pytest.mark.unit
class TestCorruptFile:

    def test_corrupt_file_rejected(self):
        _inject_condition("corrupt_file")
        u = upload_talent_media(ORG, TALENT, MediaRole.AVATAR, "bad.jpg",
                                "image/jpeg", 500_000, uploaded_by=USER)
        assert u.status == UploadStatus.REJECTED
        assert "corrupt" in u.rejection_reason.lower()


# =============================================================================
# Partial Failure (Reconciling)
# =============================================================================


@pytest.mark.unit
class TestPartialFailure:

    def test_storage_success_db_failure(self):
        _inject_condition("storage_failure")
        u = upload_talent_media(ORG, TALENT, MediaRole.AVATAR, "pic.jpg",
                                "image/jpeg", 500_000, uploaded_by=USER)
        assert u.status == UploadStatus.RECONCILING


# =============================================================================
# File Size
# =============================================================================


@pytest.mark.unit
class TestFileSize:

    def test_oversized_avatar_rejected(self):
        u = upload_talent_media(ORG, TALENT, MediaRole.AVATAR, "huge.jpg",
                                "image/jpeg", 15_000_000, uploaded_by=USER)  # > 10MB
        assert u.status == UploadStatus.REJECTED
        assert "too large" in u.rejection_reason.lower()

    def test_within_limit_accepted(self):
        u = upload_talent_media(ORG, TALENT, MediaRole.AVATAR, "ok.jpg",
                                "image/jpeg", 9_000_000, uploaded_by=USER)
        assert u.status == UploadStatus.ACCEPTED


# =============================================================================
# Downstream Role Access
# =============================================================================


@pytest.mark.unit
class TestDownstreamAccess:

    def test_correct_role_authorized(self):
        u = upload_talent_media(ORG, TALENT, MediaRole.TRAINING_REF, "ref.jpg",
                                "image/jpeg", 1_000_000, uploaded_by=USER,
                                consent_ref="c-1")
        assert authorize_role_access(u.upload_id, ORG, MediaRole.TRAINING_REF) is True

    def test_wrong_role_denied(self):
        """Prevents silent repurposing — voice sample cannot be used as training data."""
        u = upload_talent_media(ORG, TALENT, MediaRole.VOICE_SAMPLE, "voice.wav",
                                "audio/wav", 2_000_000, uploaded_by=USER,
                                consent_ref="c-1")
        assert authorize_role_access(u.upload_id, ORG, MediaRole.TRAINING_REF) is False

    def test_cross_tenant_access_denied(self):
        u = upload_talent_media(ORG, TALENT, MediaRole.AVATAR, "pic.jpg",
                                "image/jpeg", 500_000, uploaded_by=USER)
        assert authorize_role_access(u.upload_id, OTHER_ORG, MediaRole.AVATAR) is False


# =============================================================================
# Query Helpers
# =============================================================================


@pytest.mark.unit
class TestQueryHelpers:

    def test_get_training_references(self):
        upload_talent_media(ORG, TALENT, MediaRole.TRAINING_REF, "r1.jpg",
                            "image/jpeg", 1_000_000, uploaded_by=USER, consent_ref="c1")
        upload_talent_media(ORG, TALENT, MediaRole.TRAINING_REF, "r2.jpg",
                            "image/jpeg", 1_000_000, uploaded_by=USER, consent_ref="c2")
        upload_talent_media(ORG, TALENT, MediaRole.AVATAR, "av.jpg",
                            "image/jpeg", 500_000, uploaded_by=USER)
        refs = get_training_references(ORG, TALENT)
        assert len(refs) == 2

    def test_get_voice_samples(self):
        upload_talent_media(ORG, TALENT, MediaRole.VOICE_SAMPLE, "v1.wav",
                            "audio/wav", 2_000_000, uploaded_by=USER, consent_ref="c1")
        samples = get_voice_samples(ORG, TALENT)
        assert len(samples) == 1

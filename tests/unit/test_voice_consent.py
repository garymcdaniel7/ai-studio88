"""Voice-Cloning Consent Tests (Story 103).

Proves: consent required for execution, revocation blocks future use,
expiry enforced, cross-tenant denied, purpose validation, activation,
and legacy handling.

Run with:
    pytest tests/unit/test_voice_consent.py -v
"""
from __future__ import annotations

import pytest

from backend.voice_consent import (
    ConsentCrossTenantError,
    ConsentError,
    ConsentExpiredError,
    ConsentNotFoundError,
    ConsentPurpose,
    ConsentPurposeError,
    ConsentRevokedError,
    ConsentState,
    VoiceConsentRecord,
    activate_consent,
    clear_registry,
    create_legacy_stub,
    find_active_consent,
    is_legacy_voice,
    register_consent,
    revoke_consent,
    validate_consent_for_execution,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def _clean():
    clear_registry()
    yield
    clear_registry()


def _active_consent(**overrides) -> VoiceConsentRecord:
    defaults = {
        "org_id": "org-123",
        "subject_talent_id": "talent-1",
        "grantor_id": "user-456",
        "grantor_name": "Melissa",
        "grantor_relationship": "self",
        "state": ConsentState.ACTIVE,
        "evidence_storage_key": "/org-123/consent/talent-1/signed.pdf",
        "evidence_type": "signed_document",
        "permitted_purposes": [ConsentPurpose.VOICE_CLONING, ConsentPurpose.TEXT_TO_SPEECH],
        "provider_scope": ["elevenlabs"],
        "created_by": "user-456",
    }
    defaults.update(overrides)
    consent = VoiceConsentRecord(**defaults)
    register_consent(consent)
    return consent


# =============================================================================
# Consent Required
# =============================================================================


class TestConsentRequired:

    @pytest.mark.unit
    def test_valid_consent_passes(self):
        """Active consent with matching purpose passes validation."""
        consent = _active_consent()
        result = validate_consent_for_execution(
            org_id="org-123", talent_id="talent-1",
            purpose=ConsentPurpose.VOICE_CLONING,
        )
        assert result.consent_id == consent.consent_id

    @pytest.mark.unit
    def test_no_consent_raises(self):
        """Missing consent raises ConsentNotFoundError."""
        with pytest.raises(ConsentNotFoundError):
            validate_consent_for_execution(
                org_id="org-123", talent_id="talent-no-consent",
                purpose=ConsentPurpose.VOICE_CLONING,
            )

    @pytest.mark.unit
    def test_pending_consent_not_valid(self):
        """Pending consent cannot authorize execution."""
        consent = _active_consent(state=ConsentState.PENDING, evidence_storage_key="")
        with pytest.raises(ConsentError) as exc_info:
            validate_consent_for_execution(
                consent_id=consent.consent_id,
                org_id="org-123", talent_id="talent-1",
                purpose=ConsentPurpose.VOICE_CLONING,
            )
        assert exc_info.value.code == "CONSENT_PENDING"

    @pytest.mark.unit
    def test_explicit_consent_id_lookup(self):
        """Can validate using explicit consent_id."""
        consent = _active_consent()
        result = validate_consent_for_execution(
            consent_id=consent.consent_id,
            org_id="org-123", talent_id="talent-1",
            purpose=ConsentPurpose.VOICE_CLONING,
        )
        assert result.consent_id == consent.consent_id

    @pytest.mark.unit
    def test_invalid_consent_id_raises(self):
        """Non-existent consent_id raises error."""
        with pytest.raises(ConsentNotFoundError):
            validate_consent_for_execution(
                consent_id="ghost-id",
                org_id="org-123", talent_id="talent-1",
                purpose=ConsentPurpose.VOICE_CLONING,
            )


# =============================================================================
# Revocation Blocks
# =============================================================================


class TestRevocation:

    @pytest.mark.unit
    def test_revoked_consent_blocks_execution(self):
        """Revoked consent raises ConsentRevokedError."""
        consent = _active_consent()
        revoke_consent(consent.consent_id, revoked_by="admin-1", reason="Subject withdrew")

        with pytest.raises(ConsentRevokedError) as exc_info:
            validate_consent_for_execution(
                consent_id=consent.consent_id,
                org_id="org-123", talent_id="talent-1",
                purpose=ConsentPurpose.VOICE_CLONING,
            )
        assert "revoked" in exc_info.value.message

    @pytest.mark.unit
    def test_revocation_preserves_history(self):
        """Revoked consent still exists for audit (not deleted)."""
        consent = _active_consent()
        revoke_consent(consent.consent_id, revoked_by="admin-1", reason="Test")
        record = find_active_consent("org-123", "talent-1")
        # find_active_consent returns None (not active), but record still exists
        assert record is None
        from backend.voice_consent import get_consent
        preserved = get_consent(consent.consent_id)
        assert preserved is not None
        assert preserved.state == ConsentState.REVOKED
        assert preserved.revoked_by == "admin-1"

    @pytest.mark.unit
    def test_double_revocation_idempotent(self):
        """Revoking already-revoked consent is a no-op."""
        consent = _active_consent()
        revoke_consent(consent.consent_id, revoked_by="admin-1", reason="First")
        result = revoke_consent(consent.consent_id, revoked_by="admin-2", reason="Second")
        # First revocation details preserved
        assert result.revoked_by == "admin-1"
        assert result.revocation_reason == "First"

    @pytest.mark.unit
    def test_revocation_sets_timestamp(self):
        """Revocation records timestamp."""
        consent = _active_consent()
        revoke_consent(consent.consent_id, revoked_by="user-1", reason="Changed mind")
        from backend.voice_consent import get_consent
        revoked = get_consent(consent.consent_id)
        assert revoked.revoked_at is not None


# =============================================================================
# Expiry Enforced
# =============================================================================


class TestExpiry:

    @pytest.mark.unit
    def test_expired_consent_blocks(self):
        """Consent past expiration date raises ConsentExpiredError."""
        consent = _active_consent(expires_at="2020-01-01T00:00:00Z")
        with pytest.raises(ConsentExpiredError):
            validate_consent_for_execution(
                consent_id=consent.consent_id,
                org_id="org-123", talent_id="talent-1",
                purpose=ConsentPurpose.VOICE_CLONING,
                now="2025-06-01T00:00:00Z",
            )

    @pytest.mark.unit
    def test_non_expired_consent_passes(self):
        """Consent before expiration passes."""
        _active_consent(expires_at="2030-12-31T23:59:59Z")
        result = validate_consent_for_execution(
            org_id="org-123", talent_id="talent-1",
            purpose=ConsentPurpose.VOICE_CLONING,
            now="2025-06-01T00:00:00Z",
        )
        assert result.state == ConsentState.ACTIVE

    @pytest.mark.unit
    def test_no_expiration_always_valid(self):
        """Consent without expires_at never expires."""
        _active_consent(expires_at=None)
        result = validate_consent_for_execution(
            org_id="org-123", talent_id="talent-1",
            purpose=ConsentPurpose.VOICE_CLONING,
            now="2099-01-01T00:00:00Z",
        )
        assert result.state == ConsentState.ACTIVE


# =============================================================================
# Cross-Tenant Denied
# =============================================================================


class TestCrossTenant:

    @pytest.mark.unit
    def test_cross_org_consent_denied(self):
        """Cannot use consent from different workspace."""
        consent = _active_consent(org_id="org-123")
        with pytest.raises(ConsentCrossTenantError):
            validate_consent_for_execution(
                consent_id=consent.consent_id,
                org_id="org-evil",
                talent_id="talent-1",
                purpose=ConsentPurpose.VOICE_CLONING,
            )

    @pytest.mark.unit
    def test_same_org_allowed(self):
        """Same workspace consent passes tenant check."""
        consent = _active_consent(org_id="org-123")
        result = validate_consent_for_execution(
            consent_id=consent.consent_id,
            org_id="org-123", talent_id="talent-1",
            purpose=ConsentPurpose.VOICE_CLONING,
        )
        assert result.org_id == "org-123"


# =============================================================================
# Purpose Validation
# =============================================================================


class TestPurpose:

    @pytest.mark.unit
    def test_permitted_purpose_passes(self):
        """Requesting a permitted purpose passes."""
        _active_consent(permitted_purposes=[ConsentPurpose.TEXT_TO_SPEECH])
        result = validate_consent_for_execution(
            org_id="org-123", talent_id="talent-1",
            purpose=ConsentPurpose.TEXT_TO_SPEECH,
        )
        assert result.state == ConsentState.ACTIVE

    @pytest.mark.unit
    def test_unpermitted_purpose_denied(self):
        """Requesting an unpermitted purpose raises error."""
        _active_consent(permitted_purposes=[ConsentPurpose.VOICE_CLONING])
        with pytest.raises(ConsentPurposeError) as exc_info:
            validate_consent_for_execution(
                org_id="org-123", talent_id="talent-1",
                purpose=ConsentPurpose.COMMERCIAL_USE,
            )
        assert "commercial_use" in exc_info.value.message

    @pytest.mark.unit
    def test_multiple_purposes_allowed(self):
        """Consent with multiple purposes authorizes each."""
        _active_consent(permitted_purposes=[
            ConsentPurpose.VOICE_CLONING,
            ConsentPurpose.TEXT_TO_SPEECH,
            ConsentPurpose.LIP_SYNC,
        ])
        for purpose in [ConsentPurpose.VOICE_CLONING, ConsentPurpose.TEXT_TO_SPEECH, ConsentPurpose.LIP_SYNC]:
            result = validate_consent_for_execution(
                org_id="org-123", talent_id="talent-1", purpose=purpose,
            )
            assert result.state == ConsentState.ACTIVE


# =============================================================================
# Activation
# =============================================================================


class TestActivation:

    @pytest.mark.unit
    def test_activate_pending_consent(self):
        """Pending consent activates with evidence."""
        consent = VoiceConsentRecord(
            org_id="org-1", subject_talent_id="t-1", grantor_id="u-1",
            state=ConsentState.PENDING, created_by="u-1",
            permitted_purposes=[ConsentPurpose.VOICE_CLONING],
        )
        register_consent(consent)

        result = activate_consent(
            consent.consent_id,
            evidence_storage_key="/org-1/consent/signed.pdf",
            evidence_type="signed_document",
            actor_id="u-1",
        )
        assert result.state == ConsentState.ACTIVE
        assert result.evidence_storage_key == "/org-1/consent/signed.pdf"
        assert result.version == 2

    @pytest.mark.unit
    def test_activate_without_evidence_fails(self):
        """Cannot activate without evidence."""
        consent = VoiceConsentRecord(
            org_id="org-1", subject_talent_id="t-1", grantor_id="u-1",
            state=ConsentState.PENDING, created_by="u-1",
        )
        register_consent(consent)

        with pytest.raises(ConsentError) as exc_info:
            activate_consent(consent.consent_id, evidence_storage_key="", evidence_type="", actor_id="u-1")
        assert "evidence" in exc_info.value.message.lower()

    @pytest.mark.unit
    def test_activate_non_pending_fails(self):
        """Cannot activate consent that isn't pending."""
        consent = _active_consent()
        with pytest.raises(ConsentError):
            activate_consent(consent.consent_id, evidence_storage_key="/k", evidence_type="doc", actor_id="u-1")


# =============================================================================
# Legacy Handling
# =============================================================================


class TestLegacy:

    @pytest.mark.unit
    def test_legacy_voice_detected(self):
        """Voice without consent is detected as legacy."""
        assert is_legacy_voice("talent-no-consent", "org-123") is True

    @pytest.mark.unit
    def test_voice_with_consent_not_legacy(self):
        """Voice with active consent is not legacy."""
        _active_consent()
        assert is_legacy_voice("talent-1", "org-123") is False

    @pytest.mark.unit
    def test_legacy_stub_created(self):
        """Legacy stub documents the gap."""
        stub = create_legacy_stub("talent-old", "org-1")
        assert stub.requires_migration is True
        assert stub.talent_id == "talent-old"

    @pytest.mark.unit
    def test_legacy_stub_does_not_authorize(self):
        """Legacy stub cannot be used for consent validation."""
        create_legacy_stub("talent-old", "org-1")
        with pytest.raises(ConsentNotFoundError):
            validate_consent_for_execution(
                org_id="org-1", talent_id="talent-old",
                purpose=ConsentPurpose.VOICE_CLONING,
            )


# =============================================================================
# Serialization
# =============================================================================


class TestSerialization:

    @pytest.mark.unit
    def test_consent_serializable(self):
        """VoiceConsentRecord.to_dict() is JSON-serializable."""
        import json
        consent = _active_consent()
        json.dumps(consent.to_dict())

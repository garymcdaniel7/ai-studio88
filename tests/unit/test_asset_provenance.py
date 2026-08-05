"""Asset Provenance Contract Tests (Story 073).

Proves: complete lineage, idempotent registration, tenant isolation,
incomplete provenance detection, derived asset links, publishing gate,
legacy backfill, and amendment audit trail.

Run with:
    pytest tests/unit/test_asset_provenance.py -v
"""
from __future__ import annotations

import pytest

from backend.asset_provenance import (
    REQUIRED_PROVENANCE_FIELDS,
    AssetMediaType,
    AssetProvenance,
    LineageLink,
    ProvenanceAmendment,
    ProvenanceState,
    backfill_provenance,
    can_publish,
    clear_registry,
    determine_provenance_state,
    get_children,
    get_lineage,
    get_provenance,
    mark_legacy,
    register_lineage,
    register_provenance,
    validate_provenance,
    verify_provenance_access,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def _clean_registry():
    """Clear in-memory registry between tests."""
    clear_registry()
    yield
    clear_registry()


def _complete_image_provenance(**overrides) -> AssetProvenance:
    """Create a fully valid image provenance record."""
    defaults = {
        "org_id": "org-123",
        "user_id": "user-456",
        "media_type": AssetMediaType.IMAGE,
        "job_id": "gen-abc123",
        "spec_hash": "deadbeef01234567",
        "effective_prompt": "A futuristic city at sunset",
        "model_id": "flux-dev",
        "model_version": "1.0",
        "width": 1024,
        "height": 1024,
        "storage_key": "/org-123/images/talent-1/job-abc/out.webp",
        "checksum_sha256": "a1b2c3d4e5f6" * 5 + "ab",
        "mime_type": "image/webp",
        "size_bytes": 245000,
        "provider": "comfyui",
        "seed_used": 42,
    }
    defaults.update(overrides)
    return AssetProvenance(**defaults)


def _complete_voice_provenance(**overrides) -> AssetProvenance:
    """Create a fully valid voice provenance record."""
    defaults = {
        "org_id": "org-123",
        "user_id": "user-456",
        "media_type": AssetMediaType.AUDIO_VOICE,
        "job_id": "gen-voice-1",
        "spec_hash": "voice1234",
        "effective_prompt": "Welcome to AI Studio",
        "model_id": "elevenlabs",
        "talent_id": "talent-789",
        "storage_key": "/org-123/audio/talent-789/job-v1/speech.mp3",
        "checksum_sha256": "voicechecksum123456",
        "mime_type": "audio/mpeg",
        "size_bytes": 120000,
        "provider": "elevenlabs",
    }
    defaults.update(overrides)
    return AssetProvenance(**defaults)


# =============================================================================
# Provenance Validation
# =============================================================================


class TestProvenanceValidation:

    @pytest.mark.unit
    def test_complete_image_has_no_missing_fields(self):
        """Fully populated image provenance passes validation."""
        prov = _complete_image_provenance()
        missing = validate_provenance(prov)
        assert missing == []

    @pytest.mark.unit
    def test_missing_prompt_detected(self):
        """Missing effective_prompt is detected."""
        prov = _complete_image_provenance(effective_prompt="")
        missing = validate_provenance(prov)
        assert "effective_prompt" in missing

    @pytest.mark.unit
    def test_missing_storage_key_detected(self):
        """Missing storage_key is detected."""
        prov = _complete_image_provenance(storage_key="")
        missing = validate_provenance(prov)
        assert "storage_key" in missing

    @pytest.mark.unit
    def test_missing_model_detected(self):
        """Missing model_id is detected."""
        prov = _complete_image_provenance(model_id="")
        missing = validate_provenance(prov)
        assert "model_id" in missing

    @pytest.mark.unit
    def test_voice_requires_talent_id(self):
        """Voice provenance requires talent_id."""
        prov = _complete_voice_provenance(talent_id=None)
        missing = validate_provenance(prov)
        assert "talent_id" in missing

    @pytest.mark.unit
    def test_lip_sync_requires_parent_assets(self):
        """Lip-sync provenance requires parent_asset_ids."""
        prov = AssetProvenance(
            org_id="org-1", user_id="u-1", job_id="j-1",
            media_type=AssetMediaType.LIP_SYNC,
            storage_key="/k", checksum_sha256="abc", mime_type="video/mp4",
            size_bytes=1000, parent_asset_ids=[],
        )
        missing = validate_provenance(prov)
        assert "parent_asset_ids" in missing

    @pytest.mark.unit
    def test_lip_sync_with_parents_passes(self):
        """Lip-sync with parent assets passes required check."""
        prov = AssetProvenance(
            org_id="org-1", user_id="u-1", job_id="j-1",
            media_type=AssetMediaType.LIP_SYNC,
            storage_key="/k", checksum_sha256="abc", mime_type="video/mp4",
            size_bytes=1000, parent_asset_ids=["parent-video", "parent-audio"],
        )
        missing = validate_provenance(prov)
        assert "parent_asset_ids" not in missing


# =============================================================================
# Provenance State Determination
# =============================================================================


class TestProvenanceState:

    @pytest.mark.unit
    def test_no_job_id_is_pending(self):
        """Record without job_id is PENDING."""
        prov = AssetProvenance(org_id="org-1", user_id="u-1", job_id="")
        state = determine_provenance_state(prov)
        assert state == ProvenanceState.PENDING

    @pytest.mark.unit
    def test_complete_fields_is_complete(self):
        """All required fields present → COMPLETE."""
        prov = _complete_image_provenance()
        state = determine_provenance_state(prov)
        assert state == ProvenanceState.COMPLETE

    @pytest.mark.unit
    def test_missing_required_is_incomplete(self):
        """Missing required field → LINEAGE_INCOMPLETE."""
        prov = _complete_image_provenance(checksum_sha256="")
        state = determine_provenance_state(prov)
        assert state == ProvenanceState.LINEAGE_INCOMPLETE


# =============================================================================
# Idempotent Registration
# =============================================================================


class TestIdempotentRegistration:

    @pytest.mark.unit
    def test_first_registration_succeeds(self):
        """First registration creates the record."""
        prov = _complete_image_provenance()
        result = register_provenance(prov)
        assert result.asset_id == prov.asset_id
        assert result.registered_at is not None

    @pytest.mark.unit
    def test_duplicate_registration_returns_existing(self):
        """Re-registering same asset_id returns existing without error."""
        prov = _complete_image_provenance()
        first = register_provenance(prov)

        # Try again with same asset_id
        prov2 = _complete_image_provenance(
            asset_id=prov.asset_id,
            effective_prompt="Different prompt",
        )
        second = register_provenance(prov2)

        # Returns original, not overwritten
        assert second.effective_prompt == first.effective_prompt
        assert second.asset_id == first.asset_id

    @pytest.mark.unit
    def test_different_asset_id_creates_new(self):
        """Different asset_id creates a new record."""
        prov1 = _complete_image_provenance()
        prov2 = _complete_image_provenance()  # New uuid auto-generated
        register_provenance(prov1)
        register_provenance(prov2)

        assert get_provenance(prov1.asset_id) is not None
        assert get_provenance(prov2.asset_id) is not None
        assert prov1.asset_id != prov2.asset_id

    @pytest.mark.unit
    def test_registration_sets_state(self):
        """Registration auto-determines provenance state."""
        prov = _complete_image_provenance()
        result = register_provenance(prov)
        assert result.provenance_state == ProvenanceState.COMPLETE

    @pytest.mark.unit
    def test_incomplete_registration_marks_state(self):
        """Incomplete provenance is registered with LINEAGE_INCOMPLETE."""
        prov = _complete_image_provenance(model_id="")
        result = register_provenance(prov)
        assert result.provenance_state == ProvenanceState.LINEAGE_INCOMPLETE


# =============================================================================
# Lineage Links
# =============================================================================


class TestLineage:

    @pytest.mark.unit
    def test_register_lineage_link(self):
        """Lineage link is created between child and parent."""
        link = LineageLink(
            child_asset_id="child-1",
            parent_asset_id="parent-1",
            relationship="derived_from",
            org_id="org-123",
        )
        result = register_lineage(link)
        assert result.child_asset_id == "child-1"
        assert result.parent_asset_id == "parent-1"

    @pytest.mark.unit
    def test_duplicate_lineage_idempotent(self):
        """Duplicate lineage link is ignored (idempotent)."""
        link = LineageLink(
            child_asset_id="child-1", parent_asset_id="parent-1", org_id="org-1",
        )
        register_lineage(link)
        register_lineage(link)  # Duplicate

        links = get_lineage("child-1")
        assert len(links) == 1

    @pytest.mark.unit
    def test_get_lineage_returns_parents(self):
        """get_lineage returns all parent links for a child."""
        register_lineage(LineageLink(
            child_asset_id="child-1", parent_asset_id="parent-a", org_id="org-1",
        ))
        register_lineage(LineageLink(
            child_asset_id="child-1", parent_asset_id="parent-b", org_id="org-1",
        ))

        links = get_lineage("child-1")
        assert len(links) == 2
        parent_ids = {l.parent_asset_id for l in links}
        assert parent_ids == {"parent-a", "parent-b"}

    @pytest.mark.unit
    def test_get_children_returns_derivatives(self):
        """get_children returns all assets derived from a parent."""
        register_lineage(LineageLink(
            child_asset_id="remix-1", parent_asset_id="original", org_id="org-1",
        ))
        register_lineage(LineageLink(
            child_asset_id="remix-2", parent_asset_id="original", org_id="org-1",
        ))

        children = get_children("original")
        assert len(children) == 2

    @pytest.mark.unit
    def test_unrelated_asset_has_no_lineage(self):
        """Asset with no links returns empty lineage."""
        links = get_lineage("standalone-asset")
        assert links == []


# =============================================================================
# Tenant Isolation
# =============================================================================


class TestTenantIsolation:

    @pytest.mark.unit
    def test_same_org_access_allowed(self):
        """Same org_id grants provenance access."""
        prov = _complete_image_provenance(org_id="org-123")
        assert verify_provenance_access(prov, "org-123") is True

    @pytest.mark.unit
    def test_different_org_denied(self):
        """Different org_id denies provenance access."""
        prov = _complete_image_provenance(org_id="org-123")
        assert verify_provenance_access(prov, "org-evil") is False

    @pytest.mark.unit
    def test_empty_org_denied(self):
        """Empty requesting_org_id is denied."""
        prov = _complete_image_provenance(org_id="org-123")
        assert verify_provenance_access(prov, "") is False


# =============================================================================
# Incomplete Provenance Detection
# =============================================================================


class TestIncompleteProvenance:

    @pytest.mark.unit
    def test_missing_multiple_fields_all_reported(self):
        """All missing fields are reported, not just the first."""
        prov = AssetProvenance(
            org_id="org-1", user_id="u-1", job_id="j-1",
            media_type=AssetMediaType.IMAGE,
            # Missing: model_id, effective_prompt, width, height,
            # storage_key, checksum, mime_type, size_bytes
        )
        missing = validate_provenance(prov)
        assert len(missing) >= 5
        assert "model_id" in missing
        assert "effective_prompt" in missing
        assert "storage_key" in missing

    @pytest.mark.unit
    def test_zero_size_bytes_is_missing(self):
        """size_bytes=0 counts as missing (no empty file outputs)."""
        prov = _complete_image_provenance(size_bytes=0)
        missing = validate_provenance(prov)
        assert "size_bytes" in missing

    @pytest.mark.unit
    def test_seed_none_is_acceptable(self):
        """seed_used=None is acceptable (provider may not report it).
        seed is NOT in required fields."""
        prov = _complete_image_provenance(seed_used=None)
        missing = validate_provenance(prov)
        assert "seed_used" not in missing


# =============================================================================
# Derived Assets
# =============================================================================


class TestDerivedAssets:

    @pytest.mark.unit
    def test_composite_requires_parent_ids(self):
        """Composite media type requires parent_asset_ids."""
        prov = AssetProvenance(
            org_id="org-1", user_id="u-1", job_id="j-1",
            media_type=AssetMediaType.COMPOSITE,
            storage_key="/k", checksum_sha256="abc", mime_type="video/mp4",
            size_bytes=5000, parent_asset_ids=[],
        )
        missing = validate_provenance(prov)
        assert "parent_asset_ids" in missing

    @pytest.mark.unit
    def test_composite_with_parents_passes(self):
        """Composite with parents has no parent_asset_ids violation."""
        prov = AssetProvenance(
            org_id="org-1", user_id="u-1", job_id="j-1",
            media_type=AssetMediaType.COMPOSITE,
            storage_key="/k", checksum_sha256="abc", mime_type="video/mp4",
            size_bytes=5000, parent_asset_ids=["src-1", "src-2"],
        )
        missing = validate_provenance(prov)
        assert "parent_asset_ids" not in missing

    @pytest.mark.unit
    def test_image_does_not_require_parents(self):
        """Standard image does NOT require parent_asset_ids."""
        prov = _complete_image_provenance(parent_asset_ids=[])
        missing = validate_provenance(prov)
        assert "parent_asset_ids" not in missing


# =============================================================================
# Publishing Gate
# =============================================================================


class TestPublishingGate:

    @pytest.mark.unit
    def test_complete_provenance_can_publish(self):
        """Complete provenance allows publishing."""
        prov = _complete_image_provenance()
        prov.provenance_state = ProvenanceState.COMPLETE
        allowed, reasons = can_publish(prov)
        assert allowed is True
        assert reasons == []

    @pytest.mark.unit
    def test_incomplete_provenance_blocks_publish(self):
        """Incomplete provenance blocks publishing."""
        prov = _complete_image_provenance()
        prov.provenance_state = ProvenanceState.LINEAGE_INCOMPLETE
        allowed, reasons = can_publish(prov)
        assert allowed is False
        assert any("incomplete" in r.lower() for r in reasons)

    @pytest.mark.unit
    def test_talent_without_consent_blocks_publish(self):
        """Talent-linked asset without consent evidence blocks publishing."""
        prov = _complete_image_provenance(talent_id="talent-1", consent_evidence_ids=[])
        prov.provenance_state = ProvenanceState.COMPLETE
        allowed, reasons = can_publish(prov)
        assert allowed is False
        assert any("consent" in r.lower() for r in reasons)

    @pytest.mark.unit
    def test_talent_with_consent_allows_publish(self):
        """Talent-linked asset WITH consent evidence allows publishing."""
        prov = _complete_image_provenance(
            talent_id="talent-1",
            consent_evidence_ids=["consent-abc"],
        )
        prov.provenance_state = ProvenanceState.COMPLETE
        allowed, reasons = can_publish(prov)
        assert allowed is True

    @pytest.mark.unit
    def test_derived_asset_without_parents_blocks(self):
        """Derived asset missing parent refs blocks publishing."""
        prov = AssetProvenance(
            org_id="org-1", user_id="u-1", job_id="j-1",
            media_type=AssetMediaType.LIP_SYNC,
            storage_key="/k", checksum_sha256="abc", mime_type="video/mp4",
            size_bytes=5000, parent_asset_ids=[],
            provenance_state=ProvenanceState.COMPLETE,
        )
        allowed, reasons = can_publish(prov)
        assert allowed is False
        assert any("parent" in r.lower() for r in reasons)


# =============================================================================
# Legacy Backfill
# =============================================================================


class TestLegacyBackfill:

    @pytest.mark.unit
    def test_mark_legacy_creates_stub(self):
        """mark_legacy creates a LEGACY state record."""
        prov = mark_legacy("old-asset-1", "org-123")
        assert prov.provenance_state == ProvenanceState.LEGACY
        assert prov.asset_id == "old-asset-1"
        assert prov.org_id == "org-123"

    @pytest.mark.unit
    def test_backfill_updates_fields(self):
        """Backfill applies data to legacy record."""
        mark_legacy("old-1", "org-1")
        result = backfill_provenance("old-1", {
            "job_id": "recovered-job",
            "model_id": "sdxl",
            "effective_prompt": "Recovered prompt",
            "storage_key": "/org-1/images/old.png",
            "checksum_sha256": "oldchecksum",
            "mime_type": "image/png",
            "size_bytes": 50000,
            "width": 512,
            "height": 512,
            "user_id": "user-1",
        })
        assert result is not None
        assert result.model_id == "sdxl"
        assert result.effective_prompt == "Recovered prompt"

    @pytest.mark.unit
    def test_backfill_promotes_to_complete(self):
        """Backfill with all required fields promotes to COMPLETE."""
        mark_legacy("old-2", "org-1")
        backfill_provenance("old-2", {
            "job_id": "j-1",
            "model_id": "flux-dev",
            "effective_prompt": "test",
            "storage_key": "/k",
            "checksum_sha256": "abc",
            "mime_type": "image/webp",
            "size_bytes": 1000,
            "width": 1024,
            "height": 1024,
            "user_id": "u-1",
            "org_id": "org-1",
            "media_type": AssetMediaType.IMAGE,
        })
        prov = get_provenance("old-2")
        assert prov is not None
        assert prov.provenance_state == ProvenanceState.COMPLETE

    @pytest.mark.unit
    def test_backfill_nonexistent_returns_none(self):
        """Backfilling non-existent asset returns None."""
        result = backfill_provenance("ghost-asset", {"model_id": "sdxl"})
        assert result is None

    @pytest.mark.unit
    def test_backfill_complete_record_is_noop(self):
        """Cannot backfill an already-COMPLETE record."""
        prov = _complete_image_provenance()
        register_provenance(prov)
        result = backfill_provenance(prov.asset_id, {"model_id": "changed"})
        assert result is not None
        assert result.model_id == "flux-dev"  # Unchanged


# =============================================================================
# Configuration Coverage
# =============================================================================


class TestConfiguration:

    @pytest.mark.unit
    def test_all_media_types_have_required_fields(self):
        """Every media type has defined required provenance fields."""
        for media_type in AssetMediaType:
            assert media_type in REQUIRED_PROVENANCE_FIELDS, (
                f"{media_type.value} missing from REQUIRED_PROVENANCE_FIELDS"
            )

    @pytest.mark.unit
    def test_all_required_fields_exist_on_model(self):
        """Every required field name exists as an attribute on AssetProvenance."""
        prov = AssetProvenance()
        for media_type, fields in REQUIRED_PROVENANCE_FIELDS.items():
            for field_name in fields:
                assert hasattr(prov, field_name), (
                    f"{field_name} required for {media_type.value} "
                    f"but not on AssetProvenance"
                )

    @pytest.mark.unit
    def test_provenance_serializable(self):
        """AssetProvenance.to_dict() is JSON-serializable."""
        import json
        prov = _complete_image_provenance()
        json.dumps(prov.to_dict())

    @pytest.mark.unit
    def test_amendment_serializable(self):
        """ProvenanceAmendment.to_dict() is JSON-serializable."""
        import json
        amendment = ProvenanceAmendment(
            asset_id="a-1", org_id="org-1",
            field_name="model_id", old_value="sdxl", new_value="flux-dev",
            reason="Corrected model attribution", amended_by="admin-1",
        )
        json.dumps(amendment.to_dict())

"""Canonical Creative DNA tests — Story 080.

Tests prove:
  - One canonical record per talent (idempotent create)
  - Updates create attributable versions
  - Conflict detection between legacy flat/JSON and canonical
  - Concurrent edit detection via expected_version
  - Rollback to prior version creates new version with old values
  - Cross-tenant access blocked (no existence leak)
  - Legacy adapter reads/writes route through canonical
  - Historical generation references exact version used
  - Backfill from legacy: null handling, priority, no silent discard
"""

import pytest

from backend.creative_dna import (
    ConcurrentEditConflict,
    ConflictResolution,
    DNANotFound,
    VersionNotFound,
    _reset_store,
    backfill_from_legacy,
    create_dna,
    detect_conflicts,
    get_dna_for_generation,
    get_effective_dna,
    get_historical_dna,
    read_legacy_format,
    rollback_dna,
    update_dna,
    write_from_legacy,
)


@pytest.fixture(autouse=True)
def clean():
    _reset_store()
    yield
    _reset_store()


ORG = "org-test-001"
OTHER_ORG = "org-other-999"
TALENT = "talent-001"
AUTHOR = "user-author-001"


# =============================================================================
# Creation & Versioning
# =============================================================================


@pytest.mark.unit
class TestCreationVersioning:

    def test_create_dna(self):
        dna = create_dna(ORG, TALENT, AUTHOR, {
            "trigger_words": ["ohwx"],
            "negative_prompt": "blurry, low quality",
            "visual_style": "photorealistic",
        })
        assert dna.talent_id == TALENT
        assert dna.org_id == ORG
        assert dna.version_count == 1
        assert dna.effective.trigger_words == ["ohwx"]

    def test_create_idempotent(self):
        d1 = create_dna(ORG, TALENT, AUTHOR)
        d2 = create_dna(ORG, TALENT, AUTHOR)
        assert d1.dna_id == d2.dna_id

    def test_update_creates_version(self):
        create_dna(ORG, TALENT, AUTHOR, {"negative_prompt": "old"})
        dna = update_dna(TALENT, ORG, AUTHOR, {"negative_prompt": "new"}, reason="Improved")
        assert dna.version_count == 2
        assert dna.effective.negative_prompt == "new"
        assert dna.effective.reason == "Improved"
        assert dna.get_version(1).negative_prompt == "old"

    def test_update_preserves_unchanged_fields(self):
        create_dna(ORG, TALENT, AUTHOR, {
            "trigger_words": ["ohwx"],
            "visual_style": "cinematic",
        })
        dna = update_dna(TALENT, ORG, AUTHOR, {"visual_style": "anime"})
        assert dna.effective.trigger_words == ["ohwx"]  # Unchanged
        assert dna.effective.visual_style == "anime"    # Updated

    def test_version_author_tracked(self):
        create_dna(ORG, TALENT, AUTHOR)
        update_dna(TALENT, ORG, "user-editor-002", {"persona": "bold"}, reason="Editor change")
        dna_effective = get_effective_dna(TALENT, ORG)
        assert dna_effective.author_id == "user-editor-002"


# =============================================================================
# Conflict Detection
# =============================================================================


@pytest.mark.unit
class TestConflictDetection:

    def test_no_conflicts_when_values_match(self):
        create_dna(ORG, TALENT, AUTHOR, {"negative_prompt": "blurry"})
        report = detect_conflicts(TALENT, ORG, {"negative_prompt": "blurry"})
        assert not report.has_conflicts

    def test_conflict_detected_flat_vs_canonical(self):
        create_dna(ORG, TALENT, AUTHOR, {"negative_prompt": "canonical value"})
        report = detect_conflicts(TALENT, ORG, {"negative_prompt": "different legacy"})
        assert report.has_conflicts
        assert report.conflicts[0]["field"] == "negative_prompt"
        assert report.conflicts[0]["resolution"] == ConflictResolution.UNRESOLVED.value

    def test_conflict_in_json_blob(self):
        create_dna(ORG, TALENT, AUTHOR, {"visual_style": "photo"})
        report = detect_conflicts(
            TALENT, ORG,
            legacy_flat={},
            legacy_json={"visual_style": "cartoon"},
        )
        assert report.has_conflicts

    def test_null_legacy_no_conflict(self):
        create_dna(ORG, TALENT, AUTHOR, {"negative_prompt": "something"})
        report = detect_conflicts(TALENT, ORG, {"negative_prompt": None})
        assert not report.has_conflicts

    def test_no_canonical_no_conflicts(self):
        """If no canonical exists, legacy can be adopted."""
        report = detect_conflicts("nonexistent", ORG, {"negative_prompt": "any"})
        assert not report.has_conflicts


# =============================================================================
# Concurrent Edits
# =============================================================================


@pytest.mark.unit
class TestConcurrentEdits:

    def test_expected_version_matches(self):
        create_dna(ORG, TALENT, AUTHOR)
        dna = update_dna(TALENT, ORG, AUTHOR, {"persona": "bold"}, expected_version=1)
        assert dna.version_count == 2

    def test_expected_version_mismatch_raises(self):
        create_dna(ORG, TALENT, AUTHOR)
        update_dna(TALENT, ORG, AUTHOR, {"persona": "v2"})
        with pytest.raises(ConcurrentEditConflict):
            update_dna(TALENT, ORG, "other-user", {"persona": "v2-conflict"}, expected_version=1)


# =============================================================================
# Rollback
# =============================================================================


@pytest.mark.unit
class TestRollback:

    def test_rollback_to_prior_version(self):
        create_dna(ORG, TALENT, AUTHOR, {"visual_style": "v1-style"})
        update_dna(TALENT, ORG, AUTHOR, {"visual_style": "v2-style"})
        dna = rollback_dna(TALENT, ORG, AUTHOR, target_version=1)

        assert dna.effective.visual_style == "v1-style"
        assert dna.version_count == 3  # Rollback creates a new version

    def test_rollback_nonexistent_version_raises(self):
        create_dna(ORG, TALENT, AUTHOR)
        with pytest.raises(VersionNotFound):
            rollback_dna(TALENT, ORG, AUTHOR, target_version=99)


# =============================================================================
# Cross-Tenant Isolation
# =============================================================================


@pytest.mark.unit
class TestCrossTenant:

    def test_cross_tenant_read_returns_none(self):
        create_dna(ORG, TALENT, AUTHOR)
        assert get_effective_dna(TALENT, OTHER_ORG) is None

    def test_cross_tenant_update_raises(self):
        create_dna(ORG, TALENT, AUTHOR)
        with pytest.raises(DNANotFound):
            update_dna(TALENT, OTHER_ORG, "hacker", {"persona": "evil"})

    def test_cross_tenant_rollback_raises(self):
        create_dna(ORG, TALENT, AUTHOR)
        with pytest.raises(DNANotFound):
            rollback_dna(TALENT, OTHER_ORG, "hacker", target_version=1)


# =============================================================================
# Legacy Adapter
# =============================================================================


@pytest.mark.unit
class TestLegacyAdapter:

    def test_read_legacy_format(self):
        create_dna(ORG, TALENT, AUTHOR, {
            "negative_prompt": "blurry",
            "visual_style": "photo",
            "trigger_words": ["ohwx"],
        })
        legacy = read_legacy_format(TALENT, ORG)
        assert legacy["negative_prompt"] == "blurry"
        assert legacy["visual_style"] == "photo"
        assert legacy["creative_dna"]["trigger_words"] == ["ohwx"]

    def test_read_legacy_no_record_empty(self):
        legacy = read_legacy_format("nonexistent", ORG)
        assert legacy == {}

    def test_write_from_legacy_creates_version(self):
        create_dna(ORG, TALENT, AUTHOR)
        dna = write_from_legacy(TALENT, ORG, "legacy-caller", {"persona": "updated via legacy"})
        assert dna.effective.persona == "updated via legacy"
        assert dna.version_count == 2


# =============================================================================
# Historical Generation Replay
# =============================================================================


@pytest.mark.unit
class TestHistoricalReplay:

    def test_generation_pins_version(self):
        create_dna(ORG, TALENT, AUTHOR, {"trigger_words": ["ohwx"]})
        v1 = get_dna_for_generation(TALENT, ORG, "job-001")
        assert v1 is not None

        # Update DNA after generation
        update_dna(TALENT, ORG, AUTHOR, {"trigger_words": ["ohwx", "v2"]})

        # Historical reference still points to v1
        ref = get_historical_dna("job-001")
        assert ref == v1.version_id

    def test_no_dna_returns_none(self):
        result = get_dna_for_generation("no-talent", ORG, "job-x")
        assert result is None


# =============================================================================
# Backfill
# =============================================================================


@pytest.mark.unit
class TestBackfill:

    def test_backfill_creates_from_legacy(self):
        dna = backfill_from_legacy(TALENT, ORG, AUTHOR, {
            "negative_prompt": "ugly",
            "visual_style": "cinematic",
            "hair_color": "blonde",
        })
        assert dna.effective.negative_prompt == "ugly"
        assert dna.effective.visual_style == "cinematic"
        assert dna.effective.appearance.get("hair_color") == "blonde"

    def test_backfill_flat_wins_over_json(self):
        dna = backfill_from_legacy(TALENT, ORG, AUTHOR,
            legacy_flat={"visual_style": "flat-value"},
            legacy_json={"visual_style": "json-value"},
        )
        assert dna.effective.visual_style == "flat-value"

    def test_backfill_skips_null_values(self):
        dna = backfill_from_legacy(TALENT, ORG, AUTHOR, {
            "negative_prompt": "real",
            "visual_style": None,
            "best_for": "",
        })
        assert dna.effective.negative_prompt == "real"
        assert dna.effective.visual_style == ""
        assert dna.effective.best_for == ""

    def test_backfill_existing_does_not_overwrite(self):
        create_dna(ORG, TALENT, AUTHOR, {"negative_prompt": "canonical"})
        dna = backfill_from_legacy(TALENT, ORG, AUTHOR, {"negative_prompt": "legacy"})
        # Canonical value preserved — legacy doesn't overwrite
        assert dna.effective.negative_prompt == "canonical"

    def test_backfill_fills_empty_canonical_fields(self):
        create_dna(ORG, TALENT, AUTHOR, {"negative_prompt": "existing"})
        dna = backfill_from_legacy(TALENT, ORG, AUTHOR, {"visual_style": "new from legacy"})
        assert dna.effective.visual_style == "new from legacy"
        assert dna.effective.negative_prompt == "existing"

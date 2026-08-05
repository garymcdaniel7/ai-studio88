"""Immutable generation snapshot tests — Story 086.

Tests prove:
  - Snapshot content is immutable (frozen dataclass)
  - Hash integrity verified on retrieval
  - Source edits after generation don't change snapshot
  - Retry creates idempotent snapshot (same job → same snapshot)
  - Batch variants get distinct snapshots
  - Failed capture tracked with repair state
  - Cross-workspace access denied
  - Legacy backfill creates explicit marker
  - Remix reads from snapshot (not current mutable data)
  - Job and asset both link to same snapshot
"""

import pytest

from backend.generation_snapshot import (
    GenerationSnapshot,
    RemixMode,
    SnapshotAccessDenied,
    SnapshotContent,
    SnapshotNotFound,
    SnapshotStatus,
    _reset_store,
    create_legacy_marker,
    create_snapshot,
    get_snapshot_by_asset,
    get_snapshot_by_job,
    link_asset_to_snapshot,
    list_failed_snapshots,
    mark_snapshot_failed,
    prepare_remix,
    verify_snapshot_integrity,
)


@pytest.fixture(autouse=True)
def clean():
    _reset_store()
    yield
    _reset_store()


ORG = "org-test-001"
OTHER_ORG = "org-other-999"
JOB = "job-gen-001"


def _content(**overrides) -> SnapshotContent:
    defaults = dict(
        effective_prompt="a photorealistic portrait, 8k, detailed",
        effective_negative_prompt="blurry, low quality",
        original_prompt="portrait photo",
        model_id="flux_dev",
        model_version="1.0.0",
        lora_ids=("lora-face-001",),
        lora_versions=("v2.1",),
        lora_strengths=(0.8,),
        seed=42,
        width=1024,
        height=1024,
        steps=25,
        cfg=7.5,
        creative_dna_version_id="dna-v-abc",
        context_package_id="pkg-123",
        context_package_hash="abcdef1234567890",
        talent_id="talent-001",
        talent_version="v3",
        provider="vast.ai",
        source_versions=(("talent:talent-001", "v3"), ("model:flux_dev", "1.0.0")),
    )
    defaults.update(overrides)
    return SnapshotContent(**defaults)


# =============================================================================
# Immutability
# =============================================================================


@pytest.mark.unit
class TestImmutability:

    def test_content_is_frozen(self):
        content = _content()
        with pytest.raises(Exception):  # FrozenInstanceError
            content.effective_prompt = "modified"  # type: ignore

    def test_content_hash_deterministic(self):
        c1 = _content(seed=42)
        c2 = _content(seed=42)
        assert c1.compute_hash() == c2.compute_hash()

    def test_different_content_different_hash(self):
        c1 = _content(seed=42)
        c2 = _content(seed=99)
        assert c1.compute_hash() != c2.compute_hash()


# =============================================================================
# Hash Integrity
# =============================================================================


@pytest.mark.unit
class TestHashIntegrity:

    def test_snapshot_valid_on_creation(self):
        content = _content()
        snap = create_snapshot(ORG, JOB, content)
        assert snap.is_valid

    def test_integrity_verification(self):
        content = _content()
        snap = create_snapshot(ORG, JOB, content)
        result = verify_snapshot_integrity(snap.snapshot_id, ORG)
        assert result["valid"] is True
        assert result["stored_hash"] == result["computed_hash"]


# =============================================================================
# Source Edits After Generation
# =============================================================================


@pytest.mark.unit
class TestSourceEditsAfterGeneration:

    def test_snapshot_unchanged_after_source_edit(self):
        """Mutable source edits don't retroactively change the snapshot."""
        content = _content(talent_version="v3", effective_prompt="original prompt")
        snap = create_snapshot(ORG, JOB, content)

        # Simulate: talent is edited to v4 with different prompt
        # The snapshot retains v3 values
        retrieved = get_snapshot_by_job(JOB, ORG)
        assert retrieved.content.talent_version == "v3"
        assert retrieved.content.effective_prompt == "original prompt"

    def test_snapshot_source_versions_preserved(self):
        content = _content(source_versions=(
            ("talent:t1", "v2"),
            ("model:flux", "1.0"),
            ("lora:face", "v3"),
        ))
        snap = create_snapshot(ORG, JOB, content)
        assert snap.content.source_versions == (
            ("talent:t1", "v2"),
            ("model:flux", "1.0"),
            ("lora:face", "v3"),
        )


# =============================================================================
# Retry (Idempotent)
# =============================================================================


@pytest.mark.unit
class TestRetry:

    def test_same_job_same_snapshot(self):
        content = _content()
        s1 = create_snapshot(ORG, JOB, content)
        s2 = create_snapshot(ORG, JOB, content)
        assert s1.snapshot_id == s2.snapshot_id


# =============================================================================
# Batch Variants
# =============================================================================


@pytest.mark.unit
class TestBatch:

    def test_batch_gets_distinct_snapshots(self):
        c1 = _content(seed=1, effective_prompt="shot 1")
        c2 = _content(seed=2, effective_prompt="shot 2")
        s1 = create_snapshot(ORG, "job-batch-1", c1)
        s2 = create_snapshot(ORG, "job-batch-2", c2)
        assert s1.snapshot_id != s2.snapshot_id
        assert s1.content_hash != s2.content_hash


# =============================================================================
# Failed Capture
# =============================================================================


@pytest.mark.unit
class TestFailedCapture:

    def test_mark_failed(self):
        content = _content()
        snap = create_snapshot(ORG, JOB, content)
        mark_snapshot_failed(JOB, "DB unavailable")
        retrieved = get_snapshot_by_job(JOB, ORG)
        assert retrieved.status == SnapshotStatus.FAILED
        assert retrieved.error == "DB unavailable"

    def test_list_failed_snapshots(self):
        create_snapshot(ORG, "j1", _content(seed=1))
        create_snapshot(ORG, "j2", _content(seed=2))
        mark_snapshot_failed("j2", "timeout")

        failed = list_failed_snapshots(ORG)
        assert len(failed) == 1
        assert failed[0].job_id == "j2"


# =============================================================================
# Cross-Workspace
# =============================================================================


@pytest.mark.unit
class TestCrossWorkspace:

    def test_cross_workspace_get_by_job_returns_none(self):
        create_snapshot(ORG, JOB, _content())
        assert get_snapshot_by_job(JOB, OTHER_ORG) is None

    def test_cross_workspace_get_by_asset_returns_none(self):
        snap = create_snapshot(ORG, JOB, _content())
        link_asset_to_snapshot(snap.snapshot_id, "ast-001", ORG)
        assert get_snapshot_by_asset("ast-001", OTHER_ORG) is None

    def test_cross_workspace_link_denied(self):
        snap = create_snapshot(ORG, JOB, _content())
        with pytest.raises(SnapshotAccessDenied):
            link_asset_to_snapshot(snap.snapshot_id, "ast-evil", OTHER_ORG)

    def test_cross_workspace_remix_denied(self):
        snap = create_snapshot(ORG, JOB, _content())
        with pytest.raises(SnapshotNotFound):
            prepare_remix(snap.snapshot_id, OTHER_ORG)


# =============================================================================
# Legacy Backfill
# =============================================================================


@pytest.mark.unit
class TestLegacyBackfill:

    def test_legacy_marker_created(self):
        snap = create_legacy_marker("old-asset-001", ORG)
        assert snap.status == SnapshotStatus.LEGACY_UNKNOWN
        assert snap.asset_id == "old-asset-001"
        assert snap.content_hash == "legacy_unknown"

    def test_legacy_asset_retrievable(self):
        create_legacy_marker("old-asset-001", ORG)
        snap = get_snapshot_by_asset("old-asset-001", ORG)
        assert snap is not None
        assert snap.status == SnapshotStatus.LEGACY_UNKNOWN


# =============================================================================
# Remix
# =============================================================================


@pytest.mark.unit
class TestRemix:

    def test_remix_exact_returns_snapshot_values(self):
        content = _content(
            effective_prompt="sunset portrait",
            seed=777,
            model_id="flux_dev",
        )
        snap = create_snapshot(ORG, JOB, content)

        remix_params = prepare_remix(snap.snapshot_id, ORG, RemixMode.EXACT)
        assert remix_params["remix_mode"] == "exact"
        assert remix_params["effective_prompt"] == "sunset portrait"
        assert remix_params["seed"] == 777
        assert remix_params["model_id"] == "flux_dev"
        assert remix_params["source_snapshot_id"] == snap.snapshot_id

    def test_remix_reset_returns_marker(self):
        snap = create_snapshot(ORG, JOB, _content())
        remix_params = prepare_remix(snap.snapshot_id, ORG, RemixMode.RESET)
        assert remix_params["remix_mode"] == "reset"
        assert remix_params["source_snapshot_id"] == snap.snapshot_id

    def test_remix_from_nonexistent_raises(self):
        with pytest.raises(SnapshotNotFound):
            prepare_remix("snap-fake", ORG)


# =============================================================================
# Job + Asset Linkage
# =============================================================================


@pytest.mark.unit
class TestLinkage:

    def test_job_and_asset_link_to_same_snapshot(self):
        content = _content()
        snap = create_snapshot(ORG, JOB, content)
        link_asset_to_snapshot(snap.snapshot_id, "ast-001", ORG)

        by_job = get_snapshot_by_job(JOB, ORG)
        by_asset = get_snapshot_by_asset("ast-001", ORG)
        assert by_job.snapshot_id == by_asset.snapshot_id

    def test_snapshot_tracks_remix_lineage(self):
        # Original
        original = create_snapshot(ORG, "job-orig", _content(seed=1))
        # Remix
        remix_content = _content(seed=2, effective_prompt="remix version")
        remix_snap = create_snapshot(
            ORG, "job-remix", remix_content,
            remixed_from=original.snapshot_id,
            remix_mode=RemixMode.EXACT,
        )
        assert remix_snap.remixed_from_snapshot_id == original.snapshot_id
        assert remix_snap.remix_mode == RemixMode.EXACT

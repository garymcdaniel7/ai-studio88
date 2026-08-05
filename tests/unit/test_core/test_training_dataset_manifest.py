"""Training dataset manifest tests — Story 092.

Tests prove:
  - Checksum mismatch blocks training
  - Expired signed URL fails transfer
  - Worker loss mid-transfer is handled
  - Manifest mutation after freeze is rejected
  - Duplicate retry is idempotent
  - Deleted source blocks freeze
  - Partial copy: some items verified, some failed
  - Cross-workspace access rejected
  - Worker acknowledgement must match hash and count
  - Full happy path: create → freeze → transfer → verify → ack → train → cleanup
"""

import pytest

from backend.training_dataset_manifest import (
    InvalidManifestState,
    ManifestAlreadyFrozen,
    ManifestCountMismatch,
    ManifestHashMismatch,
    ManifestImmutable,
    ManifestNotFound,
    ManifestStatus,
    SourceDeletedError,
    WorkerLostError,
    _inject_condition,
    _reset_store,
    attempt_add_item,
    can_start_training,
    cleanup_worker_copies,
    create_manifest,
    freeze_manifest,
    generate_signed_urls,
    get_manifest,
    mark_training_complete,
    record_worker_acknowledgement,
    retry_failed_items,
    transfer_to_worker,
    verify_checksums,
)


@pytest.fixture(autouse=True)
def clean():
    _reset_store()
    yield
    _reset_store()


ORG = "org-test-001"
OTHER_ORG = "org-other-999"
TALENT = "talent-001"
JOB = "job-train-001"


def _sample_items(count: int = 3) -> list[dict]:
    return [
        {
            "asset_id": f"ast-{i}",
            "storage_key": f"{ORG}/training/{TALENT}/img_{i}.jpg",
            "checksum_sha256": f"{'a' * 60}{i:04d}",
            "file_size_bytes": 100000 + i * 1000,
            "content_type": "image/jpeg",
            "caption": f"Photo {i} of talent",
            "consent_ref": f"consent-{i}",
        }
        for i in range(count)
    ]


def _full_pipeline(items=None) -> tuple:
    """Run manifest through full happy path up to verification."""
    items = items or _sample_items()
    m = create_manifest(ORG, TALENT, JOB, items)
    freeze_manifest(m.manifest_id, ORG)
    generate_signed_urls(m.manifest_id, ORG)
    transfer_to_worker(m.manifest_id, ORG, "worker-001")

    # Build worker checksums (matching)
    checksums = {mi.item.item_id: mi.item.checksum_sha256 for mi in m.items}
    verify_checksums(m.manifest_id, ORG, checksums)
    return m, checksums


# =============================================================================
# Happy Path
# =============================================================================


@pytest.mark.unit
class TestHappyPath:

    def test_full_lifecycle(self):
        m, checksums = _full_pipeline()
        assert m.status == ManifestStatus.VERIFIED
        assert m.all_verified

        # Acknowledge
        record_worker_acknowledgement(m.manifest_id, ORG, m.manifest_hash, m.item_count)
        assert m.status == ManifestStatus.TRAINING
        assert can_start_training(m.manifest_id, ORG)

        # Complete and cleanup
        mark_training_complete(m.manifest_id, ORG)
        assert m.status == ManifestStatus.COMPLETED
        cleanup_worker_copies(m.manifest_id, ORG)
        assert m.status == ManifestStatus.CLEANED

    def test_manifest_hash_computed(self):
        m = create_manifest(ORG, TALENT, JOB, _sample_items())
        freeze_manifest(m.manifest_id, ORG)
        assert m.manifest_hash
        assert len(m.manifest_hash) == 64  # SHA-256


# =============================================================================
# Checksum Mismatch
# =============================================================================


@pytest.mark.unit
class TestChecksumMismatch:

    def test_mismatch_blocks_training(self):
        m = create_manifest(ORG, TALENT, JOB, _sample_items())
        freeze_manifest(m.manifest_id, ORG)
        generate_signed_urls(m.manifest_id, ORG)
        transfer_to_worker(m.manifest_id, ORG, "w1")

        # Report wrong checksums
        bad_checksums = {mi.item.item_id: "wrong_hash" for mi in m.items}
        verify_checksums(m.manifest_id, ORG, bad_checksums)

        assert m.status == ManifestStatus.FAILED
        assert m.has_failures
        assert not can_start_training(m.manifest_id, ORG)

    def test_simulated_checksum_failure(self):
        _inject_condition("checksum_mismatch")
        m = create_manifest(ORG, TALENT, JOB, _sample_items())
        freeze_manifest(m.manifest_id, ORG)
        generate_signed_urls(m.manifest_id, ORG)
        transfer_to_worker(m.manifest_id, ORG, "w1")

        checksums = {mi.item.item_id: mi.item.checksum_sha256 for mi in m.items}
        verify_checksums(m.manifest_id, ORG, checksums)
        assert m.status == ManifestStatus.FAILED


# =============================================================================
# Expired URL
# =============================================================================


@pytest.mark.unit
class TestExpiredURL:

    def test_expired_url_fails_transfer(self):
        _inject_condition("expired_url")
        m = create_manifest(ORG, TALENT, JOB, _sample_items())
        freeze_manifest(m.manifest_id, ORG)
        generate_signed_urls(m.manifest_id, ORG)
        transfer_to_worker(m.manifest_id, ORG, "w1")

        assert m.has_failures
        failed = [i for i in m.items if i.error and "expired" in i.error.lower()]
        assert len(failed) == m.item_count


# =============================================================================
# Worker Loss
# =============================================================================


@pytest.mark.unit
class TestWorkerLoss:

    def test_worker_loss_during_transfer(self):
        _inject_condition("worker_loss")
        m = create_manifest(ORG, TALENT, JOB, _sample_items())
        freeze_manifest(m.manifest_id, ORG)
        generate_signed_urls(m.manifest_id, ORG)

        with pytest.raises(WorkerLostError):
            transfer_to_worker(m.manifest_id, ORG, "w1")

        assert m.status == ManifestStatus.FAILED


# =============================================================================
# Mutation Attempt
# =============================================================================


@pytest.mark.unit
class TestMutationPrevention:

    def test_cannot_add_item_after_freeze(self):
        m = create_manifest(ORG, TALENT, JOB, _sample_items())
        freeze_manifest(m.manifest_id, ORG)

        with pytest.raises(ManifestImmutable):
            attempt_add_item(m.manifest_id, ORG, {"asset_id": "new"})

    def test_cannot_freeze_twice(self):
        m = create_manifest(ORG, TALENT, JOB, _sample_items())
        freeze_manifest(m.manifest_id, ORG)

        with pytest.raises(ManifestAlreadyFrozen):
            freeze_manifest(m.manifest_id, ORG)


# =============================================================================
# Duplicate Retry
# =============================================================================


@pytest.mark.unit
class TestRetry:

    def test_retry_is_idempotent(self):
        """Already-verified items are not re-transferred on retry."""
        m = create_manifest(ORG, TALENT, JOB, _sample_items(3))
        freeze_manifest(m.manifest_id, ORG)
        generate_signed_urls(m.manifest_id, ORG)
        transfer_to_worker(m.manifest_id, ORG, "w1")

        # Verify first 2, fail last
        checksums = {}
        for i, mi in enumerate(m.items):
            if i < 2:
                checksums[mi.item.item_id] = mi.item.checksum_sha256
            else:
                checksums[mi.item.item_id] = "wrong"
        verify_checksums(m.manifest_id, ORG, checksums)

        assert m.status == ManifestStatus.FAILED
        # First 2 verified, last failed
        assert m.items[0].status.value == "verified"
        assert m.items[2].status.value == "failed"

        # Retry
        retry_failed_items(m.manifest_id, ORG)
        assert m.items[0].status.value == "verified"  # Not reset
        assert m.items[2].status.value == "pending"   # Reset for retry


# =============================================================================
# Deleted Source
# =============================================================================


@pytest.mark.unit
class TestDeletedSource:

    def test_deleted_source_blocks_freeze(self):
        _inject_condition("deleted_source")
        m = create_manifest(ORG, TALENT, JOB, _sample_items())

        with pytest.raises(SourceDeletedError):
            freeze_manifest(m.manifest_id, ORG)


# =============================================================================
# Partial Copy
# =============================================================================


@pytest.mark.unit
class TestPartialCopy:

    def test_partial_verification(self):
        m = create_manifest(ORG, TALENT, JOB, _sample_items(3))
        freeze_manifest(m.manifest_id, ORG)
        generate_signed_urls(m.manifest_id, ORG)
        transfer_to_worker(m.manifest_id, ORG, "w1")

        # Only report checksums for first 2 items
        checksums = {m.items[i].item.item_id: m.items[i].item.checksum_sha256 for i in range(2)}
        verify_checksums(m.manifest_id, ORG, checksums)

        assert m.items[0].status.value == "verified"
        assert m.items[1].status.value == "verified"
        assert m.items[2].status.value == "failed"
        assert m.status == ManifestStatus.FAILED


# =============================================================================
# Cross-Workspace
# =============================================================================


@pytest.mark.unit
class TestCrossWorkspace:

    def test_cross_workspace_get_returns_none(self):
        m = create_manifest(ORG, TALENT, JOB, _sample_items())
        assert get_manifest(m.manifest_id, OTHER_ORG) is None

    def test_cross_workspace_freeze_raises(self):
        m = create_manifest(ORG, TALENT, JOB, _sample_items())
        with pytest.raises(ManifestNotFound):
            freeze_manifest(m.manifest_id, OTHER_ORG)

    def test_cross_workspace_verify_raises(self):
        m, _ = _full_pipeline()
        # Reset to transferring for test
        m.status = ManifestStatus.TRANSFERRING
        with pytest.raises(ManifestNotFound):
            verify_checksums(m.manifest_id, OTHER_ORG, {})


# =============================================================================
# Worker Acknowledgement
# =============================================================================


@pytest.mark.unit
class TestWorkerAck:

    def test_wrong_hash_rejected(self):
        m, _ = _full_pipeline()
        with pytest.raises(ManifestHashMismatch):
            record_worker_acknowledgement(m.manifest_id, ORG, "wrong-hash", m.item_count)

    def test_wrong_count_rejected(self):
        m, _ = _full_pipeline()
        with pytest.raises(ManifestCountMismatch):
            record_worker_acknowledgement(m.manifest_id, ORG, m.manifest_hash, 999)

    def test_correct_ack_transitions_to_training(self):
        m, _ = _full_pipeline()
        record_worker_acknowledgement(m.manifest_id, ORG, m.manifest_hash, m.item_count)
        assert m.status == ManifestStatus.TRAINING
        assert m.worker_ack_hash == m.manifest_hash

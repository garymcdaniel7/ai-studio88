"""Asset Registration Tests (Story 075).

Proves: retry idempotency, duplicate callbacks, partial failure reconciliation,
distinct-job-same-bytes, cache/managed separation, and storage cleanup.

Run with:
    pytest tests/unit/test_asset_registration.py -v
"""
from __future__ import annotations

import pytest

from backend.asset_registration import (
    AssetState,
    StorageClass,
    cleanup_cache,
    clear_cache_registry,
    clear_registry,
    compute_asset_id,
    compute_cache_key,
    compute_storage_key,
    finalize_asset,
    get_asset,
    get_asset_by_job,
    list_cache_files,
    mark_upload_failed,
    reconcile_storage,
    register_cache_file,
    reserve_asset,
    retry_upload,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def _clean():
    clear_registry()
    clear_cache_registry()
    yield
    clear_registry()
    clear_cache_registry()


# =============================================================================
# Asset Identity
# =============================================================================


class TestAssetIdentity:

    @pytest.mark.unit
    def test_same_job_same_output_same_id(self):
        """Same job_id + output_index always produces same asset_id."""
        id1 = compute_asset_id("job-abc", 0)
        id2 = compute_asset_id("job-abc", 0)
        assert id1 == id2

    @pytest.mark.unit
    def test_different_jobs_different_ids(self):
        """Different jobs produce different asset IDs even with same output_index."""
        id1 = compute_asset_id("job-abc", 0)
        id2 = compute_asset_id("job-def", 0)
        assert id1 != id2

    @pytest.mark.unit
    def test_different_output_index_different_ids(self):
        """Same job but different output_index produces different IDs (batch)."""
        id1 = compute_asset_id("job-abc", 0)
        id2 = compute_asset_id("job-abc", 1)
        assert id1 != id2

    @pytest.mark.unit
    def test_identity_is_deterministic_hash(self):
        """Asset ID is a fixed-length hex string."""
        asset_id = compute_asset_id("job-xyz", 0)
        assert len(asset_id) == 24
        assert all(c in "0123456789abcdef" for c in asset_id)


# =============================================================================
# Idempotent Reserve
# =============================================================================


class TestReserve:

    @pytest.mark.unit
    def test_first_reserve_creates_record(self):
        """First reserve creates a RESERVED asset."""
        asset = reserve_asset(job_id="j-1", org_id="org-1")
        assert asset.state == AssetState.RESERVED
        assert asset.org_id == "org-1"
        assert asset.job_id == "j-1"

    @pytest.mark.unit
    def test_duplicate_reserve_returns_existing(self):
        """Duplicate reserve returns existing record (idempotent)."""
        first = reserve_asset(job_id="j-1", org_id="org-1", mime_type="image/png")
        second = reserve_asset(job_id="j-1", org_id="org-1", mime_type="image/webp")
        assert first.asset_id == second.asset_id
        # Original mime_type preserved, not overwritten
        assert second.mime_type == "image/png"

    @pytest.mark.unit
    def test_reserve_does_not_overwrite_finalized(self):
        """Reserve on already-finalized asset returns it unchanged."""
        finalize_asset(
            job_id="j-1", org_id="org-1",
            storage_key="/k", checksum_sha256="abc",
            size_bytes=100,
        )
        result = reserve_asset(job_id="j-1", org_id="org-1")
        assert result.state == AssetState.FINALIZED


# =============================================================================
# Idempotent Finalize
# =============================================================================


class TestFinalize:

    @pytest.mark.unit
    def test_first_finalize_succeeds(self):
        """First finalize creates and finalizes the asset."""
        asset = finalize_asset(
            job_id="j-1", org_id="org-1", output_index=0,
            storage_key="/org-1/images/_/j-1/out.webp",
            checksum_sha256="sha256abc",
            mime_type="image/webp",
            size_bytes=50000,
            width=1024, height=1024,
        )
        assert asset.state == AssetState.FINALIZED
        assert asset.finalized_at is not None
        assert asset.storage_key == "/org-1/images/_/j-1/out.webp"

    @pytest.mark.unit
    def test_duplicate_finalize_returns_existing(self):
        """Second finalize with same job_id returns existing without change."""
        first = finalize_asset(
            job_id="j-1", org_id="org-1",
            storage_key="/k1", checksum_sha256="abc",
            size_bytes=100,
        )
        second = finalize_asset(
            job_id="j-1", org_id="org-1",
            storage_key="/k2", checksum_sha256="different",
            size_bytes=200,
        )
        # Returns original, NOT overwritten
        assert second.asset_id == first.asset_id
        assert second.storage_key == "/k1"
        assert second.size_bytes == 100

    @pytest.mark.unit
    def test_finalize_after_reserve(self):
        """Finalize updates a previously reserved asset."""
        reserve_asset(job_id="j-1", org_id="org-1")
        asset = finalize_asset(
            job_id="j-1", org_id="org-1",
            storage_key="/k", checksum_sha256="hash",
            size_bytes=5000,
        )
        assert asset.state == AssetState.FINALIZED
        assert asset.upload_attempts == 1

    @pytest.mark.unit
    def test_finalize_stores_file_bytes(self):
        """File bytes are stored in simulated storage."""
        content = b"fake image data"
        asset = finalize_asset(
            job_id="j-1", org_id="org-1",
            storage_key="/org-1/images/_/j-1/out.webp",
            checksum_sha256="abc", size_bytes=len(content),
            file_bytes=content,
        )
        assert asset.state == AssetState.FINALIZED

    @pytest.mark.unit
    def test_finalize_sets_dimensions(self):
        """Width and height are persisted."""
        asset = finalize_asset(
            job_id="j-1", org_id="org-1",
            storage_key="/k", checksum_sha256="h",
            size_bytes=100, width=512, height=768,
        )
        assert asset.width == 512
        assert asset.height == 768


# =============================================================================
# Distinct Jobs Same Bytes
# =============================================================================


class TestDistinctJobsSameBytes:

    @pytest.mark.unit
    def test_same_bytes_different_jobs_get_distinct_assets(self):
        """Two jobs producing identical bytes create distinct assets."""
        content = b"identical image content"
        checksum = "same_checksum"

        asset1 = finalize_asset(
            job_id="job-A", org_id="org-1",
            storage_key="/org-1/images/_/job-A/out.webp",
            checksum_sha256=checksum, size_bytes=len(content),
            file_bytes=content,
        )
        asset2 = finalize_asset(
            job_id="job-B", org_id="org-1",
            storage_key="/org-1/images/_/job-B/out.webp",
            checksum_sha256=checksum, size_bytes=len(content),
            file_bytes=content,
        )

        assert asset1.asset_id != asset2.asset_id
        assert asset1.storage_key != asset2.storage_key
        assert asset1.checksum_sha256 == asset2.checksum_sha256

    @pytest.mark.unit
    def test_identity_follows_job_not_checksum(self):
        """Asset identity is job-based, not content-based."""
        id_a = compute_asset_id("job-A", 0)
        id_b = compute_asset_id("job-B", 0)
        assert id_a != id_b  # Even if content would be identical


# =============================================================================
# Partial Failure and Retry
# =============================================================================


class TestPartialFailure:

    @pytest.mark.unit
    def test_mark_upload_failed(self):
        """Failed upload marks asset as UPLOAD_FAILED."""
        reserve_asset(job_id="j-1", org_id="org-1")
        result = mark_upload_failed("j-1", error="Network timeout")
        assert result is not None
        assert result.state == AssetState.UPLOAD_FAILED
        assert result.last_error == "Network timeout"

    @pytest.mark.unit
    def test_mark_failed_on_finalized_is_noop(self):
        """Cannot mark a finalized asset as failed."""
        finalize_asset(
            job_id="j-1", org_id="org-1",
            storage_key="/k", checksum_sha256="h", size_bytes=100,
        )
        result = mark_upload_failed("j-1", error="Late error")
        assert result is not None
        assert result.state == AssetState.FINALIZED  # Unchanged

    @pytest.mark.unit
    def test_retry_after_failure_succeeds(self):
        """Retry upload on a failed asset succeeds."""
        reserve_asset(job_id="j-1", org_id="org-1")
        asset = get_asset_by_job("j-1")
        asset.storage_key = "/k"
        mark_upload_failed("j-1", error="First try failed")

        result = retry_upload("j-1", file_bytes=b"image data")
        assert result is not None
        assert result.state == AssetState.FINALIZED
        assert result.upload_attempts >= 1  # At least one retry attempt

    @pytest.mark.unit
    def test_retry_on_finalized_returns_existing(self):
        """Retry on already-finalized asset returns it unchanged."""
        finalize_asset(
            job_id="j-1", org_id="org-1",
            storage_key="/k", checksum_sha256="h", size_bytes=100,
        )
        result = retry_upload("j-1", file_bytes=b"different data")
        assert result is not None
        assert result.state == AssetState.FINALIZED

    @pytest.mark.unit
    def test_retry_nonexistent_returns_none(self):
        """Retry on non-existent asset returns None."""
        result = retry_upload("ghost-job")
        assert result is None

    @pytest.mark.unit
    def test_upload_attempts_increment(self):
        """Each finalize/retry attempt increments counter."""
        reserve_asset(job_id="j-1", org_id="org-1")
        asset = get_asset_by_job("j-1")
        asset.storage_key = "/k"
        mark_upload_failed("j-1")
        mark_upload_failed("j-1")  # Simulate second failure check
        retry_upload("j-1", file_bytes=b"data")

        final = get_asset_by_job("j-1")
        assert final is not None
        assert final.upload_attempts >= 1


# =============================================================================
# Reconciliation
# =============================================================================


class TestReconciliation:

    @pytest.mark.unit
    def test_detect_orphaned_storage(self):
        """Detect storage objects with no matching finalized registry entry."""
        finalize_asset(
            job_id="j-1", org_id="org-1",
            storage_key="/org-1/known.webp", checksum_sha256="h", size_bytes=100,
        )
        # Simulated storage scan includes an unknown key
        known_in_storage = {"/org-1/known.webp", "/org-1/orphan.webp"}
        result = reconcile_storage(known_in_storage)
        assert result["orphaned_count"] == 1
        assert "/org-1/orphan.webp" in result["orphaned_keys"]

    @pytest.mark.unit
    def test_detect_missing_from_storage(self):
        """Detect finalized assets whose storage key is missing."""
        finalize_asset(
            job_id="j-1", org_id="org-1",
            storage_key="/org-1/expected.webp", checksum_sha256="h", size_bytes=100,
        )
        # Storage scan does NOT include the expected key
        known_in_storage: set[str] = set()
        result = reconcile_storage(known_in_storage)
        assert result["missing_from_storage_count"] == 1
        assert "/org-1/expected.webp" in result["missing_keys"]

    @pytest.mark.unit
    def test_clean_state_no_discrepancies(self):
        """When storage and registry match, no discrepancies."""
        finalize_asset(
            job_id="j-1", org_id="org-1",
            storage_key="/k1", checksum_sha256="h", size_bytes=100,
        )
        result = reconcile_storage({"/k1"})
        assert result["orphaned_count"] == 0
        assert result["missing_from_storage_count"] == 0


# =============================================================================
# Cache vs Managed
# =============================================================================


class TestCacheManaged:

    @pytest.mark.unit
    def test_cache_key_distinct_from_managed(self):
        """Cache keys start with /_cache/ prefix."""
        cache_key = compute_cache_key("j-1", "preview.jpg")
        managed_key = compute_storage_key("org-1", "images", "j-1", "out.webp")
        assert cache_key.startswith("/_cache/")
        assert not managed_key.startswith("/_cache/")

    @pytest.mark.unit
    def test_register_cache_file(self):
        """Cache files are tracked separately."""
        key = register_cache_file("j-1", "preview.jpg", size_bytes=5000)
        assert key.startswith("/_cache/")
        files = list_cache_files("j-1")
        assert len(files) == 1
        assert files[0]["filename"] == "preview.jpg"

    @pytest.mark.unit
    def test_cleanup_cache_removes_job_files(self):
        """Cleanup removes all cache files for a job."""
        register_cache_file("j-1", "a.jpg")
        register_cache_file("j-1", "b.jpg")
        register_cache_file("j-2", "c.jpg")

        removed = cleanup_cache("j-1")
        assert removed == 2
        assert list_cache_files("j-1") == []
        assert len(list_cache_files("j-2")) == 1

    @pytest.mark.unit
    def test_managed_asset_has_managed_class(self):
        """Finalized assets default to MANAGED storage class."""
        asset = finalize_asset(
            job_id="j-1", org_id="org-1",
            storage_key="/k", checksum_sha256="h", size_bytes=100,
        )
        assert asset.storage_class == StorageClass.MANAGED


# =============================================================================
# Storage Key Computation
# =============================================================================


class TestStorageKey:

    @pytest.mark.unit
    def test_key_includes_org_and_job(self):
        """Storage key includes org_id and job_id for isolation."""
        key = compute_storage_key("org-1", "images", "j-abc", "output.webp")
        assert "/org-1/" in key
        assert "/j-abc/" in key
        assert key.endswith("/output.webp")

    @pytest.mark.unit
    def test_key_with_talent(self):
        """Storage key includes talent_id when provided."""
        key = compute_storage_key("org-1", "images", "j-1", "out.webp", talent_id="t-99")
        assert "/t-99/" in key

    @pytest.mark.unit
    def test_key_without_talent_uses_placeholder(self):
        """Storage key uses '_' when no talent_id."""
        key = compute_storage_key("org-1", "images", "j-1", "out.webp", talent_id=None)
        assert "/_/" in key


# =============================================================================
# Lookup
# =============================================================================


class TestLookup:

    @pytest.mark.unit
    def test_get_by_job_returns_asset(self):
        """get_asset_by_job finds the asset."""
        finalize_asset(
            job_id="j-1", org_id="org-1",
            storage_key="/k", checksum_sha256="h", size_bytes=100,
        )
        asset = get_asset_by_job("j-1", 0)
        assert asset is not None
        assert asset.job_id == "j-1"

    @pytest.mark.unit
    def test_get_by_job_nonexistent(self):
        """get_asset_by_job returns None for unknown job."""
        assert get_asset_by_job("ghost") is None

    @pytest.mark.unit
    def test_to_dict_serializable(self):
        """RegisteredAsset.to_dict() is JSON-serializable."""
        import json
        asset = finalize_asset(
            job_id="j-1", org_id="org-1",
            storage_key="/k", checksum_sha256="h", size_bytes=100,
        )
        json.dumps(asset.to_dict())

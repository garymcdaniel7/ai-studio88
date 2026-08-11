"""Provider analytics ingestion tests — Story 130.

Tests prove:
  - Deduplication: same metric+timestamp not stored twice
  - Historical correction creates new snapshot (not overwrite)
  - Deleted post: metrics flagged, not removed
  - Cross-tenant: other org's metrics invisible
  - Rate-limit resume: checkpoint tracks state
  - Pagination checkpoint saved/retrieved
  - Stale data flagged
  - Two-tenant isolation: each org sees only their own
  - Provenance preserved on every snapshot
  - Latest-only query returns most recent values
"""

import time

import pytest

from backend.analytics_ingestion import (
    IngestionStatus,
    MetricSource,
    ReconciliationState,
    _reset_store,
    can_resume,
    get_checkpoint,
    get_ingestion_summary,
    get_metric_history,
    get_metrics,
    ingest_correction,
    ingest_metrics,
    mark_post_deleted,
    mark_rate_limited,
    mark_stale,
    save_checkpoint,
)


@pytest.fixture(autouse=True)
def clean():
    _reset_store()
    yield
    _reset_store()


ORG = "org-test-001"
OTHER_ORG = "org-other-999"
ACCOUNT = "acc-ig-001"


def _sample_metrics(post_id: str = "post-001", ts: float = 1000.0) -> list[dict]:
    return [
        {"remote_content_id": post_id, "metric_name": "impressions", "metric_value": 5000, "provider_timestamp": ts},
        {"remote_content_id": post_id, "metric_name": "likes", "metric_value": 200, "provider_timestamp": ts},
        {"remote_content_id": post_id, "metric_name": "reach", "metric_value": 3000, "provider_timestamp": ts},
    ]


# =============================================================================
# Deduplication
# =============================================================================


@pytest.mark.unit
class TestDeduplication:

    def test_first_ingestion_stores_all(self):
        job = ingest_metrics(ORG, ACCOUNT, MetricSource.INSTAGRAM, _sample_metrics())
        assert job.snapshots_ingested == 3
        assert job.duplicates_skipped == 0

    def test_duplicate_ingestion_skipped(self):
        ingest_metrics(ORG, ACCOUNT, MetricSource.INSTAGRAM, _sample_metrics())
        job2 = ingest_metrics(ORG, ACCOUNT, MetricSource.INSTAGRAM, _sample_metrics())
        assert job2.snapshots_ingested == 0
        assert job2.duplicates_skipped == 3

    def test_different_timestamp_not_duplicate(self):
        ingest_metrics(ORG, ACCOUNT, MetricSource.INSTAGRAM, _sample_metrics(ts=1000.0))
        job2 = ingest_metrics(ORG, ACCOUNT, MetricSource.INSTAGRAM, _sample_metrics(ts=2000.0))
        assert job2.snapshots_ingested == 3  # New timestamp = new snapshots

    def test_different_post_not_duplicate(self):
        ingest_metrics(ORG, ACCOUNT, MetricSource.INSTAGRAM, _sample_metrics("post-A"))
        job2 = ingest_metrics(ORG, ACCOUNT, MetricSource.INSTAGRAM, _sample_metrics("post-B"))
        assert job2.snapshots_ingested == 3


# =============================================================================
# Historical Correction
# =============================================================================


@pytest.mark.unit
class TestHistoricalCorrection:

    def test_correction_creates_new_snapshot(self):
        ingest_metrics(ORG, ACCOUNT, MetricSource.INSTAGRAM, _sample_metrics())
        ingest_correction(ORG, ACCOUNT, MetricSource.INSTAGRAM,
                          "post-001", "impressions", 5500.0, 1000.0)

        history = get_metric_history(ORG, "post-001", "impressions")
        assert len(history) == 2  # Original + correction
        correction = [s for s in history if s.is_correction]
        assert len(correction) == 1
        assert correction[0].metric_value == 5500.0

    def test_correction_marked_reconciled(self):
        ingest_correction(ORG, ACCOUNT, MetricSource.INSTAGRAM,
                          "post-001", "likes", 250.0, 1000.0)
        metrics = get_metrics(ORG, remote_content_id="post-001", metric_name="likes")
        assert metrics[0].reconciliation_state == ReconciliationState.CORRECTED


# =============================================================================
# Deleted Post
# =============================================================================


@pytest.mark.unit
class TestDeletedPost:

    def test_deleted_post_metrics_flagged(self):
        ingest_metrics(ORG, ACCOUNT, MetricSource.INSTAGRAM, _sample_metrics())
        count = mark_post_deleted(ORG, "post-001", MetricSource.INSTAGRAM)
        assert count == 3

    def test_deleted_metrics_excluded_by_default(self):
        ingest_metrics(ORG, ACCOUNT, MetricSource.INSTAGRAM, _sample_metrics())
        mark_post_deleted(ORG, "post-001", MetricSource.INSTAGRAM)
        results = get_metrics(ORG, remote_content_id="post-001")
        assert len(results) == 0  # Excluded by default

    def test_deleted_metrics_available_with_flag(self):
        ingest_metrics(ORG, ACCOUNT, MetricSource.INSTAGRAM, _sample_metrics())
        mark_post_deleted(ORG, "post-001", MetricSource.INSTAGRAM)
        results = get_metrics(ORG, remote_content_id="post-001", include_deleted=True)
        assert len(results) == 3
        assert all(r.reconciliation_state == ReconciliationState.DELETED for r in results)


# =============================================================================
# Cross-Tenant Isolation
# =============================================================================


@pytest.mark.unit
class TestCrossTenant:

    def test_other_org_metrics_invisible(self):
        ingest_metrics(ORG, ACCOUNT, MetricSource.INSTAGRAM, _sample_metrics())
        results = get_metrics(OTHER_ORG)
        assert len(results) == 0

    def test_each_org_sees_own(self):
        ingest_metrics(ORG, "acc-1", MetricSource.INSTAGRAM, _sample_metrics("p1"))
        ingest_metrics(OTHER_ORG, "acc-2", MetricSource.TIKTOK, _sample_metrics("p2"))
        assert len(get_metrics(ORG)) == 3
        assert len(get_metrics(OTHER_ORG)) == 3

    def test_summary_scoped(self):
        ingest_metrics(ORG, ACCOUNT, MetricSource.INSTAGRAM, _sample_metrics())
        ingest_metrics(OTHER_ORG, "acc-x", MetricSource.TIKTOK, _sample_metrics("px"))
        summary = get_ingestion_summary(ORG)
        assert summary["total_snapshots"] == 3


# =============================================================================
# Rate-Limit Resume
# =============================================================================


@pytest.mark.unit
class TestRateLimitResume:

    def test_rate_limited_blocks_resume(self):
        save_checkpoint(ORG, ACCOUNT, MetricSource.INSTAGRAM, "cursor-abc", 50)
        mark_rate_limited(ACCOUNT, MetricSource.INSTAGRAM, time.time() + 3600)
        assert can_resume(ACCOUNT, MetricSource.INSTAGRAM) is False

    def test_rate_limit_expired_allows_resume(self):
        save_checkpoint(ORG, ACCOUNT, MetricSource.INSTAGRAM, "cursor-abc", 50)
        mark_rate_limited(ACCOUNT, MetricSource.INSTAGRAM, time.time() - 1)  # Expired
        assert can_resume(ACCOUNT, MetricSource.INSTAGRAM) is True

    def test_no_checkpoint_allows_resume(self):
        assert can_resume("new-account", MetricSource.INSTAGRAM) is True


# =============================================================================
# Pagination Checkpoint
# =============================================================================


@pytest.mark.unit
class TestPaginationCheckpoint:

    def test_checkpoint_saved(self):
        save_checkpoint(ORG, ACCOUNT, MetricSource.INSTAGRAM, "cursor-page2", 100)
        cp = get_checkpoint(ACCOUNT, MetricSource.INSTAGRAM)
        assert cp is not None
        assert cp.cursor == "cursor-page2"
        assert cp.items_fetched == 100

    def test_checkpoint_updated_on_progress(self):
        save_checkpoint(ORG, ACCOUNT, MetricSource.INSTAGRAM, "c1", 50)
        save_checkpoint(ORG, ACCOUNT, MetricSource.INSTAGRAM, "c2", 100)
        cp = get_checkpoint(ACCOUNT, MetricSource.INSTAGRAM)
        assert cp.cursor == "c2"
        assert cp.items_fetched == 100


# =============================================================================
# Stale Data
# =============================================================================


@pytest.mark.unit
class TestStaleData:

    def test_old_metrics_marked_stale(self):
        ingest_metrics(ORG, ACCOUNT, MetricSource.INSTAGRAM, _sample_metrics())
        # Mark all as stale if older than now
        count = mark_stale(ORG, ACCOUNT, MetricSource.INSTAGRAM, time.time() + 1)
        assert count == 3

    def test_fresh_metrics_not_stale(self):
        ingest_metrics(ORG, ACCOUNT, MetricSource.INSTAGRAM, _sample_metrics())
        count = mark_stale(ORG, ACCOUNT, MetricSource.INSTAGRAM, time.time() - 1000)
        assert count == 0


# =============================================================================
# Provenance
# =============================================================================


@pytest.mark.unit
class TestProvenance:

    def test_snapshot_has_full_provenance(self):
        ingest_metrics(ORG, ACCOUNT, MetricSource.INSTAGRAM, _sample_metrics(),
                       publication_receipt_id="rcpt-001", source_endpoint="/insights")
        metrics = get_metrics(ORG)
        for m in metrics:
            assert m.org_id == ORG
            assert m.account_id == ACCOUNT
            assert m.source == MetricSource.INSTAGRAM
            assert m.publication_receipt_id == "rcpt-001"
            assert m.source_endpoint == "/insights"
            assert m.raw_payload_hash  # Non-empty
            assert m.normalization_version == "v1.0"
            assert m.provider_timestamp == 1000.0
            assert m.ingestion_timestamp > 0


# =============================================================================
# Latest-Only Query
# =============================================================================


@pytest.mark.unit
class TestLatestOnly:

    def test_latest_only_returns_most_recent(self):
        ingest_metrics(ORG, ACCOUNT, MetricSource.INSTAGRAM,
                       [{"remote_content_id": "p1", "metric_name": "likes", "metric_value": 100, "provider_timestamp": 1000}])
        ingest_metrics(ORG, ACCOUNT, MetricSource.INSTAGRAM,
                       [{"remote_content_id": "p1", "metric_name": "likes", "metric_value": 150, "provider_timestamp": 2000}])

        latest = get_metrics(ORG, latest_only=True, metric_name="likes")
        assert len(latest) == 1
        assert latest[0].metric_value == 150

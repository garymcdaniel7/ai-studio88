"""Multi-platform publication tests — Story 128.

Tests prove:
  - Mixed outcomes: success/failure/unknown → PARTIAL or REQUIRES_RECONCILIATION
  - Unknown blocks retry (reconciliation required)
  - Selective retry only targets failed destinations
  - Duplicate callback idempotent (success not overwritten)
  - Cancel after partial success preserves succeeded
  - Credential revoked tracked separately
  - Tenant isolation
  - Aggregate correctly derived from children
  - Reconciliation resolves unknown
"""

import pytest

from backend.multi_platform_publish import (
    AggregateStatus,
    DestinationStatus,
    PublicationNotFound,
    ReconciliationRequired,
    RetryEligibility,
    RetryNotAllowed,
    _reset_store,
    cancel_destination,
    cancel_publication,
    create_publication,
    fail_destination,
    get_publication,
    get_publication_detail,
    mark_unknown,
    reconcile_destination,
    retry_destination,
    revoke_credential,
    start_destination,
    succeed_destination,
)


@pytest.fixture(autouse=True)
def clean():
    _reset_store()
    yield
    _reset_store()


ORG = "org-test-001"
OTHER_ORG = "org-other-999"


def _create_pub(platforms=None):
    platforms = platforms or ["instagram", "tiktok", "youtube"]
    return create_publication(ORG, "ci-001", [
        {"platform": p, "variant_id": f"var-{p}", "account_id": f"acc-{p}"}
        for p in platforms
    ])


# =============================================================================
# Mixed Outcomes
# =============================================================================


@pytest.mark.unit
class TestMixedOutcomes:

    def test_all_succeed_completed(self):
        pub = _create_pub()
        for p in ["instagram", "tiktok", "youtube"]:
            start_destination(pub.publication_id, p, ORG)
            succeed_destination(pub.publication_id, p, ORG, f"post-{p}")
        assert pub.aggregate_status == AggregateStatus.COMPLETED

    def test_all_failed(self):
        pub = _create_pub()
        for p in ["instagram", "tiktok", "youtube"]:
            start_destination(pub.publication_id, p, ORG)
            fail_destination(pub.publication_id, p, ORG, "rate limited")
        assert pub.aggregate_status == AggregateStatus.FAILED

    def test_mix_success_and_failure_partial(self):
        pub = _create_pub()
        start_destination(pub.publication_id, "instagram", ORG)
        succeed_destination(pub.publication_id, "instagram", ORG, "ig-post-1")
        start_destination(pub.publication_id, "tiktok", ORG)
        fail_destination(pub.publication_id, "tiktok", ORG, "auth error")
        start_destination(pub.publication_id, "youtube", ORG)
        succeed_destination(pub.publication_id, "youtube", ORG, "yt-post-1")
        assert pub.aggregate_status == AggregateStatus.PARTIAL

    def test_unknown_triggers_reconciliation(self):
        pub = _create_pub(["instagram", "tiktok"])
        start_destination(pub.publication_id, "instagram", ORG)
        succeed_destination(pub.publication_id, "instagram", ORG, "ig-1")
        start_destination(pub.publication_id, "tiktok", ORG)
        mark_unknown(pub.publication_id, "tiktok", ORG, "timeout")
        assert pub.aggregate_status == AggregateStatus.REQUIRES_RECONCILIATION


# =============================================================================
# Unknown Blocks Retry
# =============================================================================


@pytest.mark.unit
class TestUnknownBlocksRetry:

    def test_unknown_not_retryable(self):
        pub = _create_pub(["instagram"])
        start_destination(pub.publication_id, "instagram", ORG)
        mark_unknown(pub.publication_id, "instagram", ORG)
        with pytest.raises(ReconciliationRequired):
            retry_destination(pub.publication_id, "instagram", ORG)

    def test_unknown_retry_eligibility(self):
        pub = _create_pub(["tiktok"])
        start_destination(pub.publication_id, "tiktok", ORG)
        mark_unknown(pub.publication_id, "tiktok", ORG)
        dest = pub.destinations["tiktok"]
        assert dest.retry_eligibility == RetryEligibility.REQUIRES_RECONCILIATION


# =============================================================================
# Selective Retry
# =============================================================================


@pytest.mark.unit
class TestSelectiveRetry:

    def test_retry_only_failed(self):
        pub = _create_pub(["instagram", "tiktok"])
        start_destination(pub.publication_id, "instagram", ORG)
        succeed_destination(pub.publication_id, "instagram", ORG, "ig-1")
        start_destination(pub.publication_id, "tiktok", ORG)
        fail_destination(pub.publication_id, "tiktok", ORG, "rate limit")

        # Retry tiktok
        retry_destination(pub.publication_id, "tiktok", ORG)
        assert pub.destinations["tiktok"].status == DestinationStatus.PENDING
        # Instagram not affected
        assert pub.destinations["instagram"].status == DestinationStatus.SUCCEEDED

    def test_retry_succeeded_raises(self):
        pub = _create_pub(["instagram"])
        start_destination(pub.publication_id, "instagram", ORG)
        succeed_destination(pub.publication_id, "instagram", ORG, "ig-1")
        with pytest.raises(RetryNotAllowed):
            retry_destination(pub.publication_id, "instagram", ORG)

    def test_retry_resets_for_new_attempt(self):
        pub = _create_pub(["tiktok"])
        start_destination(pub.publication_id, "tiktok", ORG)
        fail_destination(pub.publication_id, "tiktok", ORG, "err")
        old_token = pub.destinations["tiktok"].attempt_token

        retry_destination(pub.publication_id, "tiktok", ORG)
        assert pub.destinations["tiktok"].attempt_token != old_token
        assert pub.destinations["tiktok"].provider_error is None


# =============================================================================
# Duplicate Callback (Idempotent)
# =============================================================================


@pytest.mark.unit
class TestDuplicateCallback:

    def test_duplicate_success_idempotent(self):
        pub = _create_pub(["instagram"])
        start_destination(pub.publication_id, "instagram", ORG)
        succeed_destination(pub.publication_id, "instagram", ORG, "ig-1")
        # Duplicate callback
        succeed_destination(pub.publication_id, "instagram", ORG, "ig-1-dup")
        # Original receipt preserved
        assert pub.destinations["instagram"].provider_post_id == "ig-1"

    def test_fail_after_success_ignored(self):
        pub = _create_pub(["instagram"])
        start_destination(pub.publication_id, "instagram", ORG)
        succeed_destination(pub.publication_id, "instagram", ORG, "ig-1")
        # Late failure callback — ignored
        fail_destination(pub.publication_id, "instagram", ORG, "late error")
        assert pub.destinations["instagram"].status == DestinationStatus.SUCCEEDED


# =============================================================================
# Cancel After Partial Success
# =============================================================================


@pytest.mark.unit
class TestCancelAfterPartial:

    def test_cancel_preserves_succeeded(self):
        pub = _create_pub(["instagram", "tiktok", "youtube"])
        start_destination(pub.publication_id, "instagram", ORG)
        succeed_destination(pub.publication_id, "instagram", ORG, "ig-1")
        # Cancel remaining
        cancel_publication(pub.publication_id, ORG)
        assert pub.destinations["instagram"].status == DestinationStatus.SUCCEEDED
        assert pub.destinations["tiktok"].status == DestinationStatus.CANCELLED
        assert pub.destinations["youtube"].status == DestinationStatus.CANCELLED

    def test_cancel_single_destination(self):
        pub = _create_pub(["instagram", "tiktok"])
        cancel_destination(pub.publication_id, "tiktok", ORG)
        assert pub.destinations["tiktok"].status == DestinationStatus.CANCELLED
        assert pub.destinations["instagram"].status == DestinationStatus.PENDING


# =============================================================================
# Credential Revoked
# =============================================================================


@pytest.mark.unit
class TestCredentialRevoked:

    def test_credential_revoked_tracked(self):
        pub = _create_pub(["instagram"])
        start_destination(pub.publication_id, "instagram", ORG)
        revoke_credential(pub.publication_id, "instagram", ORG)
        assert pub.destinations["instagram"].status == DestinationStatus.CREDENTIAL_REVOKED
        assert pub.destinations["instagram"].is_terminal

    def test_revoked_not_retryable(self):
        pub = _create_pub(["instagram"])
        start_destination(pub.publication_id, "instagram", ORG)
        revoke_credential(pub.publication_id, "instagram", ORG)
        with pytest.raises(RetryNotAllowed):
            retry_destination(pub.publication_id, "instagram", ORG)


# =============================================================================
# Reconciliation
# =============================================================================


@pytest.mark.unit
class TestReconciliation:

    def test_reconcile_unknown_to_succeeded(self):
        pub = _create_pub(["instagram"])
        start_destination(pub.publication_id, "instagram", ORG)
        mark_unknown(pub.publication_id, "instagram", ORG)
        reconcile_destination(pub.publication_id, "instagram", ORG,
                              DestinationStatus.SUCCEEDED, "ig-post-found")
        assert pub.destinations["instagram"].status == DestinationStatus.SUCCEEDED
        assert pub.destinations["instagram"].provider_post_id == "ig-post-found"
        assert pub.aggregate_status == AggregateStatus.COMPLETED

    def test_reconcile_unknown_to_failed(self):
        pub = _create_pub(["tiktok"])
        start_destination(pub.publication_id, "tiktok", ORG)
        mark_unknown(pub.publication_id, "tiktok", ORG)
        reconcile_destination(pub.publication_id, "tiktok", ORG, DestinationStatus.FAILED)
        assert pub.destinations["tiktok"].status == DestinationStatus.FAILED
        assert pub.aggregate_status == AggregateStatus.FAILED

    def test_reconcile_only_unknown(self):
        """Reconciliation only applies to UNKNOWN destinations."""
        pub = _create_pub(["instagram"])
        start_destination(pub.publication_id, "instagram", ORG)
        succeed_destination(pub.publication_id, "instagram", ORG, "ig-1")
        # Try to reconcile succeeded — no-op
        reconcile_destination(pub.publication_id, "instagram", ORG, DestinationStatus.FAILED)
        assert pub.destinations["instagram"].status == DestinationStatus.SUCCEEDED


# =============================================================================
# Tenant Isolation
# =============================================================================


@pytest.mark.unit
class TestTenantIsolation:

    def test_cross_tenant_get_none(self):
        pub = _create_pub()
        assert get_publication(pub.publication_id, OTHER_ORG) is None

    def test_cross_tenant_start_raises(self):
        pub = _create_pub()
        with pytest.raises(PublicationNotFound):
            start_destination(pub.publication_id, "instagram", OTHER_ORG)

    def test_cross_tenant_detail_none(self):
        pub = _create_pub()
        assert get_publication_detail(pub.publication_id, OTHER_ORG) is None


# =============================================================================
# Publication Detail
# =============================================================================


@pytest.mark.unit
class TestDetail:

    def test_detail_includes_per_destination(self):
        pub = _create_pub(["instagram", "tiktok"])
        start_destination(pub.publication_id, "instagram", ORG)
        succeed_destination(pub.publication_id, "instagram", ORG, "ig-1", cost_usd=0.01)
        start_destination(pub.publication_id, "tiktok", ORG)
        fail_destination(pub.publication_id, "tiktok", ORG, "timeout", "timeout")

        detail = get_publication_detail(pub.publication_id, ORG)
        assert detail["aggregate_status"] == "partial"
        assert detail["destinations"]["instagram"]["status"] == "succeeded"
        assert detail["destinations"]["instagram"]["cost_usd"] == 0.01
        assert detail["destinations"]["tiktok"]["status"] == "failed"
        assert detail["destinations"]["tiktok"]["error_category"] == "timeout"

"""Durable Publishing Jobs Tests (Story 127).

Proves: idempotency, credential revocation, receipt requirement,
duplicate prevention, cancellation, reconciliation, and worker claims.

Run with:
    pytest tests/unit/test_publishing_jobs.py -v
"""
from __future__ import annotations

import pytest

from backend.publishing_jobs import (
    ApprovalGateError,
    CredentialGateError,
    DuplicatePostError,
    PublishJobError,
    PublishJobState,
    PublishingJob,
    cancel_job,
    check_duplicate,
    claim_job,
    clear_store,
    compute_idempotency_key,
    create_publishing_job,
    finalize_failure,
    finalize_success,
    get_job,
    mark_reconciling,
    record_provider_request,
    start_execution,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def _clean():
    clear_store()
    yield
    clear_store()


def _create(**overrides) -> PublishingJob:
    defaults = {
        "org_id": "org-123",
        "user_id": "user-456",
        "content_item_id": "item-1",
        "content_version": 1,
        "content_hash": "hash-abc",
        "platform": "instagram",
        "account_id": "acct-ig-1",
        "destination_id": "dest-ig-page",
        "preflight_result_id": "pf-1",
        "approval_id": "app-1",
    }
    defaults.update(overrides)
    return create_publishing_job(**defaults)


# =============================================================================
# Idempotency
# =============================================================================


class TestIdempotency:

    @pytest.mark.unit
    def test_same_content_destination_returns_existing(self):
        """Same content+destination returns existing non-terminal job."""
        job1 = _create()
        job2 = _create()  # Same content+destination
        assert job1.job_id == job2.job_id

    @pytest.mark.unit
    def test_different_destination_creates_new(self):
        """Different destination creates new job."""
        job1 = _create(destination_id="dest-A")
        job2 = _create(destination_id="dest-B")
        assert job1.job_id != job2.job_id

    @pytest.mark.unit
    def test_different_version_creates_new(self):
        """Different content version creates new job (after previous terminal)."""
        job1 = _create(content_version=1)
        # Mark first as published so new version can create
        claim_job(job1.job_id, "w-1")
        start_execution(job1.job_id)
        finalize_success(job1.job_id, provider_receipt_id="rcpt-1")

        job2 = _create(content_version=2)
        assert job2.job_id != job1.job_id

    @pytest.mark.unit
    def test_idempotency_key_deterministic(self):
        """Same inputs produce same key."""
        k1 = compute_idempotency_key("item-1", 1, "dest-A", "instagram")
        k2 = compute_idempotency_key("item-1", 1, "dest-A", "instagram")
        assert k1 == k2
        assert len(k1) == 20

    @pytest.mark.unit
    def test_idempotency_key_changes_with_version(self):
        """Different version produces different key."""
        k1 = compute_idempotency_key("item-1", 1, "dest-A", "ig")
        k2 = compute_idempotency_key("item-1", 2, "dest-A", "ig")
        assert k1 != k2


# =============================================================================
# Credential Revocation
# =============================================================================


class TestCredentialGate:

    @pytest.mark.unit
    def test_valid_credential_allows_creation(self):
        """Valid credential allows job creation."""
        job = _create(credential_valid=True)
        assert job.state == PublishJobState.QUEUED

    @pytest.mark.unit
    def test_invalid_credential_blocks(self):
        """Invalid credential blocks job creation."""
        with pytest.raises(CredentialGateError) as exc_info:
            _create(credential_valid=False)
        assert exc_info.value.code == "CREDENTIAL_INVALID"

    @pytest.mark.unit
    def test_invalid_approval_blocks(self):
        """Stale approval blocks job creation."""
        with pytest.raises(ApprovalGateError) as exc_info:
            _create(approval_valid=False)
        assert exc_info.value.code == "APPROVAL_INVALID"

    @pytest.mark.unit
    def test_failed_preflight_blocks(self):
        """Failed preflight blocks job creation."""
        with pytest.raises(PublishJobError) as exc_info:
            _create(preflight_passed=False)
        assert exc_info.value.code == "PREFLIGHT_FAILED"


# =============================================================================
# Receipt Requirement
# =============================================================================


class TestReceiptRequirement:

    @pytest.mark.unit
    def test_success_requires_receipt(self):
        """Cannot finalize without provider_receipt_id."""
        job = _create()
        claim_job(job.job_id, "w-1")
        start_execution(job.job_id)
        with pytest.raises(PublishJobError) as exc_info:
            finalize_success(job.job_id, provider_receipt_id="")
        assert exc_info.value.code == "RECEIPT_REQUIRED"

    @pytest.mark.unit
    def test_success_with_receipt(self):
        """Finalization with receipt succeeds."""
        job = _create()
        claim_job(job.job_id, "w-1")
        start_execution(job.job_id)
        result = finalize_success(
            job.job_id,
            provider_receipt_id="ig-post-12345",
            provider_url="https://instagram.com/p/abc",
        )
        assert result.state == PublishJobState.PUBLISHED
        assert result.published_at is not None
        assert result.attempts[-1].provider_receipt_id == "ig-post-12345"

    @pytest.mark.unit
    def test_finalize_idempotent(self):
        """Finalizing already-published job is idempotent."""
        job = _create()
        claim_job(job.job_id, "w-1")
        start_execution(job.job_id)
        finalize_success(job.job_id, provider_receipt_id="rcpt")
        result = finalize_success(job.job_id, provider_receipt_id="rcpt-2")
        assert result.state == PublishJobState.PUBLISHED
        # Original receipt preserved
        assert result.attempts[-1].provider_receipt_id == "rcpt"


# =============================================================================
# Duplicate Prevention
# =============================================================================


class TestDuplicatePrevention:

    @pytest.mark.unit
    def test_check_duplicate_finds_active(self):
        """check_duplicate finds active job for same key."""
        job = _create()
        dup = check_duplicate(job.idempotency_key)
        assert dup is not None
        assert dup.job_id == job.job_id

    @pytest.mark.unit
    def test_check_duplicate_ignores_terminal(self):
        """check_duplicate ignores completed/cancelled jobs."""
        job = _create()
        claim_job(job.job_id, "w-1")
        start_execution(job.job_id)
        finalize_success(job.job_id, provider_receipt_id="rcpt")

        dup = check_duplicate(job.idempotency_key)
        assert dup is None  # Terminal — no active duplicate

    @pytest.mark.unit
    def test_no_duplicate_for_unknown_key(self):
        """Unknown key returns None."""
        assert check_duplicate("nonexistent-key") is None


# =============================================================================
# Cancellation
# =============================================================================


class TestCancellation:

    @pytest.mark.unit
    def test_cancel_queued(self):
        """Can cancel queued job."""
        job = _create()
        cancel_job(job.job_id, actor="user-1")
        assert job.state == PublishJobState.CANCELLED

    @pytest.mark.unit
    def test_cancel_claimed(self):
        """Can cancel claimed (not yet executing) job."""
        job = _create()
        claim_job(job.job_id, "w-1")
        cancel_job(job.job_id, actor="user-1")
        assert job.state == PublishJobState.CANCELLED

    @pytest.mark.unit
    def test_cannot_cancel_executing(self):
        """Cannot cancel once executing."""
        job = _create()
        claim_job(job.job_id, "w-1")
        start_execution(job.job_id)
        cancel_job(job.job_id, actor="user-1")
        assert job.state == PublishJobState.EXECUTING  # Unchanged

    @pytest.mark.unit
    def test_cannot_cancel_published(self):
        """Cannot cancel already-published job."""
        job = _create()
        claim_job(job.job_id, "w-1")
        start_execution(job.job_id)
        finalize_success(job.job_id, provider_receipt_id="rcpt")
        cancel_job(job.job_id, actor="user-1")
        assert job.state == PublishJobState.PUBLISHED  # Unchanged


# =============================================================================
# Reconciliation
# =============================================================================


class TestReconciliation:

    @pytest.mark.unit
    def test_mark_reconciling_on_timeout(self):
        """Unknown provider outcome → RECONCILING."""
        job = _create()
        claim_job(job.job_id, "w-1")
        start_execution(job.job_id)
        mark_reconciling(job.job_id)
        assert job.state == PublishJobState.RECONCILING
        assert job.attempts[-1].state == "timeout"

    @pytest.mark.unit
    def test_reconciling_can_be_resolved_to_success(self):
        """Reconciling job can be finalized after provider confirms."""
        job = _create()
        claim_job(job.job_id, "w-1")
        start_execution(job.job_id)
        mark_reconciling(job.job_id)

        # Provider confirms later
        start_execution(job.job_id)  # New attempt from reconciling
        finalize_success(job.job_id, provider_receipt_id="late-rcpt")
        assert job.state == PublishJobState.PUBLISHED

    @pytest.mark.unit
    def test_reconciling_terminal_not_affected(self):
        """Already-published job not affected by reconciliation."""
        job = _create()
        claim_job(job.job_id, "w-1")
        start_execution(job.job_id)
        finalize_success(job.job_id, provider_receipt_id="rcpt")
        mark_reconciling(job.job_id)
        assert job.state == PublishJobState.PUBLISHED  # Unchanged


# =============================================================================
# Worker Claims
# =============================================================================


class TestWorkerClaims:

    @pytest.mark.unit
    def test_claim_queued_job(self):
        """Worker can claim a queued job."""
        job = _create()
        result = claim_job(job.job_id, "worker-A")
        assert result is not None
        assert result.state == PublishJobState.CLAIMED
        assert result.worker_id == "worker-A"

    @pytest.mark.unit
    def test_cannot_claim_already_claimed(self):
        """Second worker cannot claim already-claimed job."""
        job = _create()
        claim_job(job.job_id, "worker-A")
        result = claim_job(job.job_id, "worker-B")
        assert result is None  # Not claimable

    @pytest.mark.unit
    def test_provider_request_id_recorded(self):
        """Provider request ID persisted on attempt."""
        job = _create()
        claim_job(job.job_id, "w-1")
        start_execution(job.job_id)
        record_provider_request(job.job_id, "ig-req-xyz")
        assert job.attempts[-1].provider_request_id == "ig-req-xyz"


# =============================================================================
# Retry Behavior
# =============================================================================


class TestRetry:

    @pytest.mark.unit
    def test_failure_returns_to_queue(self):
        """Failed attempt under max returns job to QUEUED for retry."""
        job = _create()
        claim_job(job.job_id, "w-1")
        start_execution(job.job_id)
        finalize_failure(job.job_id, error="Rate limited")
        assert job.state == PublishJobState.QUEUED
        assert job.worker_id is None
        assert len(job.attempts) == 1

    @pytest.mark.unit
    def test_max_attempts_marks_failed(self):
        """Reaching max_attempts marks job as FAILED."""
        job = _create()
        job.max_attempts = 2

        # Attempt 1
        claim_job(job.job_id, "w-1")
        start_execution(job.job_id)
        finalize_failure(job.job_id, error="err 1")
        # Attempt 2
        claim_job(job.job_id, "w-2")
        start_execution(job.job_id)
        finalize_failure(job.job_id, error="err 2")

        assert job.state == PublishJobState.FAILED
        assert len(job.attempts) == 2

    @pytest.mark.unit
    def test_job_serializable(self):
        """PublishingJob.to_dict() is JSON-serializable."""
        import json
        job = _create()
        claim_job(job.job_id, "w-1")
        start_execution(job.job_id)
        json.dumps(job.to_dict())

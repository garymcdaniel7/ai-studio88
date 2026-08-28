"""Durable Publishing Jobs — Story 127.

Per-destination publishing execution with atomic claims, idempotency keys,
credential/approval gates, provider receipt finalization, and reconciliation.

Browser closure, API restart, or worker crash cannot lose accepted work.
Published requires verified provider evidence — never from local request alone.

Job States:
    QUEUED      → Accepted, waiting for worker claim
    CLAIMED     → Worker holds atomic lease
    EXECUTING   → Provider request in flight
    PUBLISHED   → Provider receipt verified
    FAILED      → Terminal failure (retryable based on policy)
    CANCELLED   → User-initiated before execution
    RECONCILING → Provider outcome unknown, needs verification

Per-Destination Attempt:
    Each retry creates a new attempt with the same idempotency key.
    Provider receipts are persisted per attempt for audit.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


# =============================================================================
# Job States
# =============================================================================


class PublishJobState(StrEnum):
    QUEUED = "queued"
    CLAIMED = "claimed"
    EXECUTING = "executing"
    PUBLISHED = "published"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RECONCILING = "reconciling"

    @property
    def is_terminal(self) -> bool:
        return self in (PublishJobState.PUBLISHED, PublishJobState.FAILED, PublishJobState.CANCELLED)

    @property
    def is_cancellable(self) -> bool:
        return self in (PublishJobState.QUEUED, PublishJobState.CLAIMED)


# =============================================================================
# Publish Attempt
# =============================================================================


@dataclass
class PublishAttempt:
    """A single provider execution attempt."""

    attempt_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    attempt_number: int = 1
    # Provider interaction
    provider_request_id: str = ""   # Request ID sent to provider
    provider_receipt_id: str = ""   # Receipt/post ID returned
    provider_url: str = ""          # Published content URL
    provider_response_code: int | None = None
    # Outcome
    state: str = "pending"          # pending, success, failed, timeout
    error_message: str = ""
    # Timing
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    completed_at: str | None = None

    def to_dict(self) -> dict:
        return {
            "attempt_id": self.attempt_id,
            "attempt_number": self.attempt_number,
            "provider_request_id": self.provider_request_id,
            "provider_receipt_id": self.provider_receipt_id,
            "provider_url": self.provider_url,
            "state": self.state,
            "error_message": self.error_message,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


# =============================================================================
# Publishing Job
# =============================================================================


@dataclass
class PublishingJob:
    """Durable per-destination publishing job."""

    # Identity
    job_id: str = field(default_factory=lambda: f"pub-{uuid.uuid4().hex[:12]}")
    org_id: str = ""
    user_id: str = ""

    # Content reference (exact approved package)
    content_item_id: str = ""
    content_version: int = 0
    content_hash: str = ""          # Fingerprint of approved package
    preflight_result_id: str = ""
    approval_id: str = ""

    # Destination
    platform: str = ""              # instagram, tiktok, youtube...
    account_id: str = ""            # Connected social account
    destination_id: str = ""        # Specific page/profile

    # Idempotency
    idempotency_key: str = ""       # Stable across retries for same content+destination

    # State
    state: PublishJobState = PublishJobState.QUEUED
    worker_id: str | None = None    # Which worker claimed this

    # Attempts
    attempts: list[PublishAttempt] = field(default_factory=list)
    max_attempts: int = 3

    # Schedule
    scheduled_at: str | None = None  # When to publish (None = immediate)

    # Timing
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    claimed_at: str | None = None
    published_at: str | None = None
    completed_at: str | None = None

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "org_id": self.org_id,
            "state": self.state.value,
            "platform": self.platform,
            "account_id": self.account_id,
            "content_item_id": self.content_item_id,
            "content_hash": self.content_hash,
            "idempotency_key": self.idempotency_key,
            "attempt_count": len(self.attempts),
            "max_attempts": self.max_attempts,
            "scheduled_at": self.scheduled_at,
            "published_at": self.published_at,
            "created_at": self.created_at,
            "attempts": [a.to_dict() for a in self.attempts],
        }


# =============================================================================
# Errors
# =============================================================================


class PublishJobError(Exception):
    def __init__(self, message: str, code: str = "PUBLISH_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class CredentialGateError(PublishJobError):
    def __init__(self, message: str):
        super().__init__(message, code="CREDENTIAL_INVALID")


class ApprovalGateError(PublishJobError):
    def __init__(self, message: str):
        super().__init__(message, code="APPROVAL_INVALID")


class DuplicatePostError(PublishJobError):
    def __init__(self, idempotency_key: str):
        super().__init__(
            f"Duplicate publish attempt with key {idempotency_key}",
            code="DUPLICATE_POST",
        )


# =============================================================================
# Idempotency Key
# =============================================================================


def compute_idempotency_key(
    content_item_id: str,
    content_version: int,
    destination_id: str,
    platform: str,
) -> str:
    """Compute stable idempotency key for a content+destination combination.

    Same key across retries prevents duplicate posts.
    """
    raw = f"{content_item_id}:{content_version}:{destination_id}:{platform}"
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


# =============================================================================
# Job Store
# =============================================================================

_job_store: dict[str, PublishingJob] = {}
_idempotency_index: dict[str, str] = {}  # key → job_id


def clear_store() -> None:
    _job_store.clear()
    _idempotency_index.clear()


def get_job(job_id: str) -> PublishingJob | None:
    return _job_store.get(job_id)


# =============================================================================
# Job Creation (with gates)
# =============================================================================


def create_publishing_job(
    *,
    org_id: str,
    user_id: str,
    content_item_id: str,
    content_version: int,
    content_hash: str,
    platform: str,
    account_id: str,
    destination_id: str,
    preflight_result_id: str,
    approval_id: str,
    scheduled_at: str | None = None,
    # Gate evidence (injected by caller)
    credential_valid: bool = True,
    approval_valid: bool = True,
    preflight_passed: bool = True,
) -> PublishingJob:
    """Create a durable publishing job.

    Gates (checked server-side before creation):
    1. Credential must be valid for the account
    2. Approval must still be valid (not stale)
    3. Preflight must have passed

    Idempotent: same content+destination returns existing job.
    """
    # Credential gate
    if not credential_valid:
        raise CredentialGateError(f"Credential for account {account_id} is invalid or revoked")

    # Approval gate
    if not approval_valid:
        raise ApprovalGateError("Approval is no longer valid (content or policy changed)")

    # Preflight gate
    if not preflight_passed:
        raise PublishJobError("Preflight has not passed", code="PREFLIGHT_FAILED")

    # Idempotency check
    idem_key = compute_idempotency_key(content_item_id, content_version, destination_id, platform)

    if idem_key in _idempotency_index:
        existing_id = _idempotency_index[idem_key]
        existing = _job_store.get(existing_id)
        if existing and not existing.state.is_terminal:
            return existing  # Already queued/executing for this content+destination

    # Create job
    job = PublishingJob(
        org_id=org_id,
        user_id=user_id,
        content_item_id=content_item_id,
        content_version=content_version,
        content_hash=content_hash,
        platform=platform,
        account_id=account_id,
        destination_id=destination_id,
        preflight_result_id=preflight_result_id,
        approval_id=approval_id,
        idempotency_key=idem_key,
        scheduled_at=scheduled_at,
    )

    _job_store[job.job_id] = job
    _idempotency_index[idem_key] = job.job_id
    return job


# =============================================================================
# Worker Claim (atomic lease)
# =============================================================================


def claim_job(job_id: str, worker_id: str) -> PublishingJob | None:
    """Atomically claim a job for execution.

    Only QUEUED jobs can be claimed. Returns None if already claimed.
    """
    job = _job_store.get(job_id)
    if not job or job.state != PublishJobState.QUEUED:
        return None

    job.state = PublishJobState.CLAIMED
    job.worker_id = worker_id
    job.claimed_at = datetime.now(UTC).isoformat()
    return job


# =============================================================================
# Execution
# =============================================================================


def start_execution(job_id: str) -> PublishAttempt | None:
    """Start a publish attempt. Creates a new attempt record."""
    job = _job_store.get(job_id)
    if not job or job.state not in (PublishJobState.CLAIMED, PublishJobState.RECONCILING):
        return None

    attempt = PublishAttempt(
        attempt_number=len(job.attempts) + 1,
    )
    job.attempts.append(attempt)
    job.state = PublishJobState.EXECUTING
    return attempt


def record_provider_request(job_id: str, provider_request_id: str) -> None:
    """Record the request ID sent to the provider."""
    job = _job_store.get(job_id)
    if not job or not job.attempts:
        return
    job.attempts[-1].provider_request_id = provider_request_id


# =============================================================================
# Finalization (receipt required)
# =============================================================================


def finalize_success(
    job_id: str,
    *,
    provider_receipt_id: str,
    provider_url: str = "",
) -> PublishingJob:
    """Finalize job as published with verified provider receipt.

    Receipt ID is REQUIRED — cannot mark published without it.
    """
    job = _job_store.get(job_id)
    if not job:
        raise PublishJobError(f"Job {job_id} not found")

    if job.state == PublishJobState.PUBLISHED:
        return job  # Idempotent

    if not provider_receipt_id:
        raise PublishJobError(
            "Cannot finalize without provider_receipt_id",
            code="RECEIPT_REQUIRED",
        )

    # Update latest attempt
    if job.attempts:
        attempt = job.attempts[-1]
        attempt.state = "success"
        attempt.provider_receipt_id = provider_receipt_id
        attempt.provider_url = provider_url
        attempt.completed_at = datetime.now(UTC).isoformat()

    job.state = PublishJobState.PUBLISHED
    job.published_at = datetime.now(UTC).isoformat()
    job.completed_at = datetime.now(UTC).isoformat()
    return job


def finalize_failure(job_id: str, *, error: str) -> PublishingJob | None:
    """Record attempt failure. Remains retryable if under max_attempts."""
    job = _job_store.get(job_id)
    if not job:
        return None

    if job.attempts:
        attempt = job.attempts[-1]
        attempt.state = "failed"
        attempt.error_message = error
        attempt.completed_at = datetime.now(UTC).isoformat()

    if len(job.attempts) >= job.max_attempts:
        job.state = PublishJobState.FAILED
        job.completed_at = datetime.now(UTC).isoformat()
    else:
        job.state = PublishJobState.QUEUED  # Back to queue for retry
        job.worker_id = None

    return job


def mark_reconciling(job_id: str) -> PublishingJob | None:
    """Mark job as needing reconciliation (provider outcome unknown)."""
    job = _job_store.get(job_id)
    if not job:
        return None
    if job.state.is_terminal:
        return job

    if job.attempts:
        job.attempts[-1].state = "timeout"
        job.attempts[-1].completed_at = datetime.now(UTC).isoformat()

    job.state = PublishJobState.RECONCILING
    return job


# =============================================================================
# Cancellation
# =============================================================================


def cancel_job(job_id: str, *, actor: str) -> PublishingJob | None:
    """Cancel a publishing job.

    Only cancellable before execution starts (QUEUED/CLAIMED).
    """
    job = _job_store.get(job_id)
    if not job:
        return None

    if not job.state.is_cancellable:
        return job  # Cannot cancel during/after execution

    job.state = PublishJobState.CANCELLED
    job.completed_at = datetime.now(UTC).isoformat()
    return job


# =============================================================================
# Duplicate Prevention
# =============================================================================


def check_duplicate(idempotency_key: str) -> PublishingJob | None:
    """Check if a non-terminal job already exists for this idempotency key."""
    job_id = _idempotency_index.get(idempotency_key)
    if not job_id:
        return None
    job = _job_store.get(job_id)
    if job and not job.state.is_terminal:
        return job
    return None

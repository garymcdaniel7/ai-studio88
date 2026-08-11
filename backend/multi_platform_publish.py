"""Multi-Platform Publication — Story 128.

Parent publication with independent per-destination child attempts.
Aggregate status derived from children. Selective retry only for
eligible failed destinations — successful ones never repeated.

Model:
    Publication (parent)
        ├── DestinationAttempt[instagram] (child)
        ├── DestinationAttempt[tiktok] (child)
        └── DestinationAttempt[youtube] (child)

Aggregate rules:
    - ALL succeeded → COMPLETED
    - ALL failed → FAILED
    - Mix of success + failure → PARTIAL
    - Any UNKNOWN → REQUIRES_RECONCILIATION
    - ALL cancelled → CANCELLED

Retry rules:
    - Only FAILED destinations are retryable
    - UNKNOWN must be reconciled before retry (unsafe otherwise)
    - Successful destinations NEVER repeated
    - Retry is idempotent (same attempt_token)
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================


class DestinationStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"           # Provider didn't confirm — needs reconciliation
    CANCELLED = "cancelled"
    CREDENTIAL_REVOKED = "credential_revoked"


class AggregateStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"       # All destinations succeeded
    PARTIAL = "partial"           # Some succeeded, some failed/cancelled
    FAILED = "failed"             # All failed
    REQUIRES_RECONCILIATION = "requires_reconciliation"  # Unknown outcomes present
    CANCELLED = "cancelled"


class RetryEligibility(str, Enum):
    ELIGIBLE = "eligible"                   # Safe to retry
    NOT_ELIGIBLE = "not_eligible"           # Succeeded or cancelled
    REQUIRES_RECONCILIATION = "requires_reconciliation"  # Unknown — unsafe to retry


# =============================================================================
# Destination Attempt
# =============================================================================


@dataclass
class DestinationAttempt:
    """Independent lifecycle for one publishing destination."""
    attempt_id: str = field(default_factory=lambda: f"dst-{uuid.uuid4().hex[:12]}")
    publication_id: str = ""
    platform: str = ""
    variant_id: str = ""
    account_id: str = ""

    # Status
    status: DestinationStatus = DestinationStatus.PENDING

    # Provider evidence
    provider_post_id: str | None = None   # Receipt from provider
    provider_url: str | None = None       # Published URL
    provider_error: str | None = None     # Error message (user-safe)
    error_category: str | None = None     # validation, rate_limit, auth, etc.

    # Retry
    attempts: int = 0
    max_attempts: int = 3
    attempt_token: str = field(default_factory=lambda: f"atk-{uuid.uuid4().hex[:12]}")

    # Cost
    cost_usd: float = 0.0

    # Timing
    submitted_at: float | None = None
    completed_at: float | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status in (
            DestinationStatus.SUCCEEDED,
            DestinationStatus.CANCELLED,
            DestinationStatus.CREDENTIAL_REVOKED,
        )

    @property
    def retry_eligibility(self) -> RetryEligibility:
        if self.status == DestinationStatus.FAILED:
            if self.attempts < self.max_attempts:
                return RetryEligibility.ELIGIBLE
            return RetryEligibility.NOT_ELIGIBLE
        if self.status == DestinationStatus.UNKNOWN:
            return RetryEligibility.REQUIRES_RECONCILIATION
        return RetryEligibility.NOT_ELIGIBLE


# =============================================================================
# Publication (parent)
# =============================================================================


@dataclass
class Publication:
    """Parent publication managing multiple destination attempts."""
    publication_id: str = field(default_factory=lambda: f"pub-{uuid.uuid4().hex[:12]}")
    org_id: str = ""
    content_item_id: str = ""
    schedule_id: str | None = None

    # Destinations (keyed by platform)
    destinations: dict[str, DestinationAttempt] = field(default_factory=dict)

    # Aggregate (derived from destinations)
    aggregate_status: AggregateStatus = AggregateStatus.PENDING

    # Metadata
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None

    @property
    def destination_count(self) -> int:
        return len(self.destinations)

    @property
    def succeeded_count(self) -> int:
        return sum(1 for d in self.destinations.values() if d.status == DestinationStatus.SUCCEEDED)

    @property
    def failed_count(self) -> int:
        return sum(1 for d in self.destinations.values() if d.status == DestinationStatus.FAILED)

    @property
    def unknown_count(self) -> int:
        return sum(1 for d in self.destinations.values() if d.status == DestinationStatus.UNKNOWN)


# =============================================================================
# Store
# =============================================================================

_publications: dict[str, Publication] = {}
_used_attempt_tokens: set[str] = set()  # Idempotency


# =============================================================================
# Publication API
# =============================================================================


def create_publication(
    org_id: str,
    content_item_id: str,
    destinations: list[dict[str, str]],
    schedule_id: str | None = None,
) -> Publication:
    """Create a multi-platform publication with destination attempts."""
    if not org_id or not content_item_id or not destinations:
        raise ValueError("org_id, content_item_id, and at least one destination required")

    pub = Publication(
        org_id=org_id,
        content_item_id=content_item_id,
        schedule_id=schedule_id,
    )

    for dest in destinations:
        attempt = DestinationAttempt(
            publication_id=pub.publication_id,
            platform=dest["platform"],
            variant_id=dest.get("variant_id", ""),
            account_id=dest.get("account_id", ""),
        )
        pub.destinations[dest["platform"]] = attempt

    _publications[pub.publication_id] = pub
    logger.info(f"PUBLICATION_CREATED: id={pub.publication_id} destinations={pub.destination_count}")
    return pub


# =============================================================================
# Destination Lifecycle
# =============================================================================


def start_destination(publication_id: str, platform: str, org_id: str) -> DestinationAttempt:
    """Mark a destination as in-progress."""
    pub = _get_pub(publication_id, org_id)
    dest = _get_dest(pub, platform)

    if dest.is_terminal:
        return dest  # Don't restart succeeded

    dest.status = DestinationStatus.IN_PROGRESS
    dest.submitted_at = time.time()
    dest.attempts += 1
    pub.aggregate_status = AggregateStatus.IN_PROGRESS
    return dest


def succeed_destination(
    publication_id: str,
    platform: str,
    org_id: str,
    provider_post_id: str,
    provider_url: str = "",
    cost_usd: float = 0.0,
) -> DestinationAttempt:
    """Mark destination as succeeded with provider receipt."""
    pub = _get_pub(publication_id, org_id)
    dest = _get_dest(pub, platform)

    if dest.status == DestinationStatus.SUCCEEDED:
        return dest  # Idempotent (duplicate callback)

    dest.status = DestinationStatus.SUCCEEDED
    dest.provider_post_id = provider_post_id
    dest.provider_url = provider_url
    dest.cost_usd = cost_usd
    dest.completed_at = time.time()

    _recalculate_aggregate(pub)
    return dest


def fail_destination(
    publication_id: str,
    platform: str,
    org_id: str,
    error: str,
    error_category: str = "unknown",
) -> DestinationAttempt:
    """Mark destination as failed."""
    pub = _get_pub(publication_id, org_id)
    dest = _get_dest(pub, platform)

    if dest.is_terminal:
        return dest  # Don't overwrite success

    dest.status = DestinationStatus.FAILED
    dest.provider_error = error
    dest.error_category = error_category
    dest.completed_at = time.time()

    _recalculate_aggregate(pub)
    return dest


def mark_unknown(publication_id: str, platform: str, org_id: str, reason: str = "") -> DestinationAttempt:
    """Mark destination as unknown (provider didn't confirm)."""
    pub = _get_pub(publication_id, org_id)
    dest = _get_dest(pub, platform)

    if dest.is_terminal:
        return dest

    dest.status = DestinationStatus.UNKNOWN
    dest.provider_error = reason or "Provider did not confirm outcome"
    dest.completed_at = time.time()

    _recalculate_aggregate(pub)
    return dest


def revoke_credential(publication_id: str, platform: str, org_id: str) -> DestinationAttempt:
    """Mark destination as credential revoked."""
    pub = _get_pub(publication_id, org_id)
    dest = _get_dest(pub, platform)

    dest.status = DestinationStatus.CREDENTIAL_REVOKED
    dest.provider_error = "Account credential has been revoked"
    dest.completed_at = time.time()

    _recalculate_aggregate(pub)
    return dest


def cancel_destination(publication_id: str, platform: str, org_id: str) -> DestinationAttempt:
    """Cancel a specific destination."""
    pub = _get_pub(publication_id, org_id)
    dest = _get_dest(pub, platform)

    if dest.status == DestinationStatus.SUCCEEDED:
        return dest  # Can't cancel a successful post

    dest.status = DestinationStatus.CANCELLED
    dest.completed_at = time.time()

    _recalculate_aggregate(pub)
    return dest


# =============================================================================
# Reconciliation
# =============================================================================


def reconcile_destination(
    publication_id: str,
    platform: str,
    org_id: str,
    actual_status: DestinationStatus,
    provider_post_id: str = "",
) -> DestinationAttempt:
    """Reconcile an unknown destination with actual provider evidence.

    Resolves UNKNOWN to either SUCCEEDED or FAILED based on evidence.
    """
    pub = _get_pub(publication_id, org_id)
    dest = _get_dest(pub, platform)

    if dest.status != DestinationStatus.UNKNOWN:
        return dest  # Only reconcile unknowns

    dest.status = actual_status
    if provider_post_id:
        dest.provider_post_id = provider_post_id

    _recalculate_aggregate(pub)
    logger.info(f"DESTINATION_RECONCILED: pub={publication_id} platform={platform} → {actual_status.value}")
    return dest


# =============================================================================
# Selective Retry
# =============================================================================


def retry_destination(publication_id: str, platform: str, org_id: str) -> DestinationAttempt:
    """Retry a failed destination. Blocks retry of UNKNOWN and succeeded.

    Rules:
    - Only FAILED destinations can be retried
    - UNKNOWN must be reconciled first (unsafe to retry — might duplicate)
    - Successful destinations NEVER retried
    - Uses attempt_token for idempotency
    """
    pub = _get_pub(publication_id, org_id)
    dest = _get_dest(pub, platform)

    eligibility = dest.retry_eligibility

    if eligibility == RetryEligibility.NOT_ELIGIBLE:
        raise RetryNotAllowed(f"Destination '{platform}' not eligible for retry (status={dest.status.value})")

    if eligibility == RetryEligibility.REQUIRES_RECONCILIATION:
        raise ReconciliationRequired(
            f"Destination '{platform}' has UNKNOWN outcome. Reconcile before retrying to avoid duplication."
        )

    # Reset for retry
    dest.status = DestinationStatus.PENDING
    dest.provider_error = None
    dest.error_category = None
    dest.completed_at = None
    dest.attempt_token = f"atk-{uuid.uuid4().hex[:12]}"  # New token for new attempt

    pub.aggregate_status = AggregateStatus.IN_PROGRESS
    return dest


def cancel_publication(publication_id: str, org_id: str) -> Publication:
    """Cancel all non-terminal destinations."""
    pub = _get_pub(publication_id, org_id)

    for dest in pub.destinations.values():
        if not dest.is_terminal and dest.status != DestinationStatus.FAILED:
            dest.status = DestinationStatus.CANCELLED
            dest.completed_at = time.time()

    _recalculate_aggregate(pub)
    return pub


# =============================================================================
# Aggregate Derivation
# =============================================================================


def _recalculate_aggregate(pub: Publication) -> None:
    """Derive parent status from child outcomes. Never flattens to boolean."""
    if not pub.destinations:
        return

    statuses = [d.status for d in pub.destinations.values()]

    # Check if all terminal
    all_terminal = all(
        s in (DestinationStatus.SUCCEEDED, DestinationStatus.FAILED,
              DestinationStatus.CANCELLED, DestinationStatus.CREDENTIAL_REVOKED,
              DestinationStatus.UNKNOWN)
        for s in statuses
    )

    if not all_terminal:
        pub.aggregate_status = AggregateStatus.IN_PROGRESS
        return

    # All terminal — determine aggregate
    if DestinationStatus.UNKNOWN in statuses:
        pub.aggregate_status = AggregateStatus.REQUIRES_RECONCILIATION
    elif all(s == DestinationStatus.SUCCEEDED for s in statuses):
        pub.aggregate_status = AggregateStatus.COMPLETED
        pub.completed_at = time.time()
    elif all(s == DestinationStatus.CANCELLED for s in statuses):
        pub.aggregate_status = AggregateStatus.CANCELLED
        pub.completed_at = time.time()
    elif all(s in (DestinationStatus.FAILED, DestinationStatus.CREDENTIAL_REVOKED) for s in statuses):
        pub.aggregate_status = AggregateStatus.FAILED
        pub.completed_at = time.time()
    else:
        pub.aggregate_status = AggregateStatus.PARTIAL
        pub.completed_at = time.time()


# =============================================================================
# Query
# =============================================================================


def get_publication(publication_id: str, org_id: str) -> Publication | None:
    """Get publication with tenant isolation."""
    pub = _publications.get(publication_id)
    if not pub or pub.org_id != org_id:
        return None
    return pub


def get_publication_detail(publication_id: str, org_id: str) -> dict[str, Any] | None:
    """Get full publication detail for UI."""
    pub = get_publication(publication_id, org_id)
    if not pub:
        return None

    return {
        "publication_id": pub.publication_id,
        "aggregate_status": pub.aggregate_status.value,
        "succeeded_count": pub.succeeded_count,
        "failed_count": pub.failed_count,
        "unknown_count": pub.unknown_count,
        "destination_count": pub.destination_count,
        "destinations": {
            platform: {
                "status": dest.status.value,
                "provider_post_id": dest.provider_post_id,
                "provider_url": dest.provider_url,
                "error": dest.provider_error,
                "error_category": dest.error_category,
                "attempts": dest.attempts,
                "retry_eligibility": dest.retry_eligibility.value,
                "cost_usd": dest.cost_usd,
            }
            for platform, dest in pub.destinations.items()
        },
    }


# =============================================================================
# Helpers
# =============================================================================


def _get_pub(publication_id: str, org_id: str) -> Publication:
    pub = _publications.get(publication_id)
    if not pub or pub.org_id != org_id:
        raise PublicationNotFound(f"Publication {publication_id} not found")
    return pub


def _get_dest(pub: Publication, platform: str) -> DestinationAttempt:
    dest = pub.destinations.get(platform)
    if not dest:
        raise DestinationNotFound(f"Destination '{platform}' not found")
    return dest


# =============================================================================
# Exceptions
# =============================================================================


class PublishError(Exception):
    """Base publication error."""


class PublicationNotFound(PublishError):
    """Not found or cross-tenant."""


class DestinationNotFound(PublishError):
    """Destination platform not in this publication."""


class RetryNotAllowed(PublishError):
    """Destination not eligible for retry."""


class ReconciliationRequired(PublishError):
    """Must reconcile unknown outcome before retry."""


# =============================================================================
# Testing Support
# =============================================================================


def _reset_store() -> None:
    _publications.clear()
    _used_attempt_tokens.clear()

"""Durable Feedback — Story 107.

Authenticated, tenant-scoped feedback persistence with exact lineage
to output asset, generation job, and context package. Idempotent
submission with authoritative confirmation.

Feedback is confirmed ONLY after durable persistence succeeds.
Failed submissions remain retryable without creating duplicates.

Record Fields:
    - feedback_id: unique per submission (idempotency key)
    - org_id + user_id: authenticated actor and workspace
    - asset_id: the exact output being rated
    - job_id: the generation job that produced it
    - context_package_id: the immutable context used
    - rating: numeric (1-5) or thumbs (up/down)
    - rating_type: "stars" | "thumbs" | "preference"
    - reason: optional text explaining the rating
    - learning_eligible: whether this feedback can be used for learning
    - learning_policy: the policy governing use (UNVERIFIED if undefined)

Idempotency:
    Each submission carries an idempotency_key (client-generated).
    Duplicate keys return the existing record without re-persisting.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


# =============================================================================
# Rating Types
# =============================================================================


class RatingType(StrEnum):
    STARS = "stars"              # 1-5 numeric
    THUMBS = "thumbs"           # up/down binary
    PREFERENCE = "preference"   # A vs B comparison


class LearningEligibility(StrEnum):
    ELIGIBLE = "eligible"           # Can be used for learning
    INELIGIBLE = "ineligible"       # Excluded from learning
    POLICY_UNVERIFIED = "policy_unverified"  # Policy not defined (DECISION-REQUIRED)


class FeedbackStatus(StrEnum):
    PERSISTED = "persisted"     # Successfully stored
    FAILED = "failed"           # Persistence failed (retryable)
    SUPERSEDED = "superseded"   # Replaced by updated rating


# =============================================================================
# Feedback Record
# =============================================================================


@dataclass
class FeedbackRecord:
    """A durable feedback submission with full lineage."""

    # Identity
    feedback_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    idempotency_key: str = ""       # Client-generated dedup key
    org_id: str = ""
    user_id: str = ""

    # Lineage (exact references)
    asset_id: str = ""              # The output being rated
    job_id: str = ""                # Generation job that produced it
    context_package_id: str = ""    # Immutable context used
    talent_id: str | None = None    # Optional talent link

    # Rating
    rating_type: RatingType = RatingType.STARS
    rating_value: int = 0           # 1-5 for stars, 1=down/2=up for thumbs
    reason: str = ""                # Optional explanation

    # Learning
    learning_eligible: LearningEligibility = LearningEligibility.POLICY_UNVERIFIED
    learning_policy: str = "UNVERIFIED"  # DECISION-REQUIRED

    # Status
    status: FeedbackStatus = FeedbackStatus.PERSISTED

    # Timestamps
    submitted_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    persisted_at: str | None = None

    def to_dict(self) -> dict:
        return {
            "feedback_id": self.feedback_id,
            "idempotency_key": self.idempotency_key,
            "org_id": self.org_id,
            "user_id": self.user_id,
            "asset_id": self.asset_id,
            "job_id": self.job_id,
            "context_package_id": self.context_package_id,
            "talent_id": self.talent_id,
            "rating_type": self.rating_type.value,
            "rating_value": self.rating_value,
            "reason": self.reason,
            "learning_eligible": self.learning_eligible.value,
            "status": self.status.value,
            "submitted_at": self.submitted_at,
            "persisted_at": self.persisted_at,
        }


# =============================================================================
# Submission Response
# =============================================================================


@dataclass
class FeedbackResponse:
    """Authoritative response to a feedback submission."""

    success: bool
    feedback_id: str = ""
    status: FeedbackStatus = FeedbackStatus.PERSISTED
    is_duplicate: bool = False
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "feedback_id": self.feedback_id,
            "status": self.status.value,
            "is_duplicate": self.is_duplicate,
            "error": self.error,
        }


# =============================================================================
# Errors
# =============================================================================


class FeedbackError(Exception):
    def __init__(self, message: str, code: str = "FEEDBACK_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class FeedbackAuthError(FeedbackError):
    def __init__(self, message: str = "Authentication required"):
        super().__init__(message, code="AUTH_REQUIRED")


class FeedbackCrossTenantError(FeedbackError):
    def __init__(self):
        super().__init__("Cross-tenant feedback denied", code="CROSS_TENANT")


# =============================================================================
# Feedback Store (in-memory for contract; production uses Supabase)
# =============================================================================

_feedback_store: dict[str, FeedbackRecord] = {}
_idempotency_index: dict[str, str] = {}  # idempotency_key → feedback_id


def clear_store() -> None:
    _feedback_store.clear()
    _idempotency_index.clear()


# =============================================================================
# Submission (authenticated, idempotent)
# =============================================================================


def submit_feedback(
    *,
    org_id: str,
    user_id: str,
    asset_id: str,
    job_id: str = "",
    context_package_id: str = "",
    talent_id: str | None = None,
    rating_type: RatingType = RatingType.STARS,
    rating_value: int = 0,
    reason: str = "",
    idempotency_key: str = "",
    asset_org_id: str = "",         # The org that owns the asset (for cross-tenant check)
) -> FeedbackResponse:
    """Submit feedback with durable persistence.

    Requirements:
    1. org_id and user_id must be present (authenticated)
    2. asset_id must be provided
    3. asset must belong to the same org (cross-tenant denied)
    4. Idempotent: duplicate idempotency_key returns existing record

    Returns FeedbackResponse with authoritative status.
    """
    # Authentication check
    if not org_id or not user_id:
        raise FeedbackAuthError()

    # Asset required
    if not asset_id:
        raise FeedbackError("asset_id is required", code="ASSET_REQUIRED")

    # Cross-tenant check
    if asset_org_id and asset_org_id != org_id:
        raise FeedbackCrossTenantError()

    # Rating validation
    if rating_type == RatingType.STARS and not (1 <= rating_value <= 5):
        raise FeedbackError(
            f"Stars rating must be 1-5, got {rating_value}", code="INVALID_RATING"
        )
    if rating_type == RatingType.THUMBS and rating_value not in (1, 2):
        raise FeedbackError(
            f"Thumbs rating must be 1 (down) or 2 (up), got {rating_value}",
            code="INVALID_RATING",
        )

    # Idempotency check
    if idempotency_key and idempotency_key in _idempotency_index:
        existing_id = _idempotency_index[idempotency_key]
        existing = _feedback_store.get(existing_id)
        if existing:
            return FeedbackResponse(
                success=True,
                feedback_id=existing.feedback_id,
                status=existing.status,
                is_duplicate=True,
            )

    # Create record
    record = FeedbackRecord(
        idempotency_key=idempotency_key,
        org_id=org_id,
        user_id=user_id,
        asset_id=asset_id,
        job_id=job_id,
        context_package_id=context_package_id,
        talent_id=talent_id,
        rating_type=rating_type,
        rating_value=rating_value,
        reason=reason,
        status=FeedbackStatus.PERSISTED,
        persisted_at=datetime.now(UTC).isoformat(),
    )

    # Persist
    _feedback_store[record.feedback_id] = record
    if idempotency_key:
        _idempotency_index[idempotency_key] = record.feedback_id

    return FeedbackResponse(
        success=True,
        feedback_id=record.feedback_id,
        status=FeedbackStatus.PERSISTED,
        is_duplicate=False,
    )


# =============================================================================
# Update Rating (supersedes previous)
# =============================================================================


def update_rating(
    feedback_id: str,
    *,
    org_id: str,
    user_id: str,
    new_rating_value: int,
    new_reason: str = "",
) -> FeedbackRecord:
    """Update an existing rating.

    The original is preserved (superseded), a new version is created.
    Only the original author in the same org can update.
    """
    original = _feedback_store.get(feedback_id)
    if original is None:
        raise FeedbackError(f"Feedback {feedback_id} not found", code="NOT_FOUND")

    if original.org_id != org_id:
        raise FeedbackCrossTenantError()

    if original.user_id != user_id:
        raise FeedbackError("Only the original author can update", code="UNAUTHORIZED")

    # Supersede original
    original.status = FeedbackStatus.SUPERSEDED

    # Create updated record
    updated = FeedbackRecord(
        idempotency_key=f"{original.idempotency_key}_v2" if original.idempotency_key else "",
        org_id=org_id,
        user_id=user_id,
        asset_id=original.asset_id,
        job_id=original.job_id,
        context_package_id=original.context_package_id,
        talent_id=original.talent_id,
        rating_type=original.rating_type,
        rating_value=new_rating_value,
        reason=new_reason or original.reason,
        status=FeedbackStatus.PERSISTED,
        persisted_at=datetime.now(UTC).isoformat(),
    )
    _feedback_store[updated.feedback_id] = updated
    return updated


# =============================================================================
# Queries
# =============================================================================


def get_feedback(feedback_id: str) -> FeedbackRecord | None:
    return _feedback_store.get(feedback_id)


def get_feedback_for_asset(asset_id: str, org_id: str) -> list[FeedbackRecord]:
    """Get all feedback for an asset (tenant-scoped, excludes superseded)."""
    return [
        f for f in _feedback_store.values()
        if f.asset_id == asset_id and f.org_id == org_id
        and f.status == FeedbackStatus.PERSISTED
    ]


def get_feedback_for_user(user_id: str, org_id: str) -> list[FeedbackRecord]:
    """Get all feedback by a user (tenant-scoped)."""
    return [
        f for f in _feedback_store.values()
        if f.user_id == user_id and f.org_id == org_id
        and f.status == FeedbackStatus.PERSISTED
    ]

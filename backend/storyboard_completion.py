"""Storyboard Shot Completion — Story 076.

A storyboard shot is only marked complete when a verified persisted asset
exists. Transient states (running, buffered, in-memory only) never count
as completion.

Design:
    - Shot status: pending → generating → complete | failed | cancelled
    - Complete requires: asset_id + storage_verified = True
    - Retry resets shot to pending (clears prior failed state)
    - Cancel clears shot (no partial completion claim)
    - Storyboard-level completion requires ALL shots complete
    - Cross-tenant: shots scoped to org_id

Verification chain:
    1. Generation job completes → asset registered in storage
    2. Storage key verified (B2 object exists)
    3. Shot marked complete with verified asset reference
    4. Storyboard-level progress recalculated

Never mark complete from:
    - Job status alone (job "completed" doesn't mean asset persisted)
    - Base64 in-memory output (transient, not durable)
    - Frontend callback (client state is untrusted)
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


class ShotStatus(str, Enum):
    """Shot lifecycle states."""
    PENDING = "pending"           # Not yet started
    GENERATING = "generating"     # Job submitted, waiting for output
    COMPLETE = "complete"         # Verified persisted asset exists
    FAILED = "failed"             # Generation failed (retryable)
    CANCELLED = "cancelled"       # User cancelled


class StoryboardStatus(str, Enum):
    """Storyboard-level status derived from shot states."""
    DRAFT = "draft"               # Not all shots have prompts
    READY = "ready"               # All shots have prompts, none started
    IN_PROGRESS = "in_progress"   # Some shots generating/complete
    COMPLETE = "complete"         # ALL shots have verified assets
    PARTIAL = "partial"           # Some complete, some failed/cancelled


# =============================================================================
# Data Structures
# =============================================================================


@dataclass
class VerifiedAsset:
    """Proof that an asset is persisted and verified."""
    asset_id: str
    storage_key: str
    storage_verified: bool = False  # B2 HEAD check passed
    verified_at: float | None = None
    content_type: str = ""
    file_size_bytes: int = 0


@dataclass
class StoryboardShot:
    """A single shot in a storyboard with completion tracking."""
    shot_id: str = field(default_factory=lambda: f"shot-{uuid.uuid4().hex[:10]}")
    storyboard_id: str = ""
    org_id: str = ""
    shot_index: int = 0
    prompt: str = ""
    status: ShotStatus = ShotStatus.PENDING

    # Generation tracking
    job_id: str | None = None
    attempt_count: int = 0

    # Completion evidence (only set when status == COMPLETE)
    verified_asset: VerifiedAsset | None = None

    # Timing
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    failed_at: float | None = None

    # Error
    error: str | None = None

    @property
    def is_complete(self) -> bool:
        """Complete ONLY when a verified persisted asset exists."""
        return (
            self.status == ShotStatus.COMPLETE
            and self.verified_asset is not None
            and self.verified_asset.storage_verified
        )

    @property
    def is_terminal(self) -> bool:
        return self.status in (ShotStatus.COMPLETE, ShotStatus.CANCELLED)


@dataclass
class Storyboard:
    """Storyboard with shot completion tracking."""
    storyboard_id: str = field(default_factory=lambda: f"sb-{uuid.uuid4().hex[:10]}")
    org_id: str = ""
    name: str = ""
    shots: list[StoryboardShot] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    @property
    def status(self) -> StoryboardStatus:
        """Derive storyboard status from shot states."""
        if not self.shots:
            return StoryboardStatus.DRAFT

        statuses = {s.status for s in self.shots}

        if all(s.is_complete for s in self.shots):
            return StoryboardStatus.COMPLETE

        if ShotStatus.GENERATING in statuses or ShotStatus.COMPLETE in statuses:
            if ShotStatus.FAILED in statuses or ShotStatus.CANCELLED in statuses:
                return StoryboardStatus.PARTIAL
            return StoryboardStatus.IN_PROGRESS

        if all(s.prompt for s in self.shots) and statuses == {ShotStatus.PENDING}:
            return StoryboardStatus.READY

        return StoryboardStatus.DRAFT

    @property
    def completion_pct(self) -> int:
        if not self.shots:
            return 0
        complete = sum(1 for s in self.shots if s.is_complete)
        return int((complete / len(self.shots)) * 100)

    @property
    def complete_count(self) -> int:
        return sum(1 for s in self.shots if s.is_complete)

    @property
    def total_count(self) -> int:
        return len(self.shots)


# =============================================================================
# Store
# =============================================================================

_storyboards: dict[str, Storyboard] = {}


# =============================================================================
# Storyboard Management
# =============================================================================


def create_storyboard(
    org_id: str,
    name: str,
    shots: list[dict[str, Any]],
) -> Storyboard:
    """Create a storyboard with shots."""
    if not org_id:
        raise ValueError("org_id is required")

    sb = Storyboard(org_id=org_id, name=name)

    for i, shot_data in enumerate(shots):
        shot = StoryboardShot(
            storyboard_id=sb.storyboard_id,
            org_id=org_id,
            shot_index=i,
            prompt=shot_data.get("prompt", ""),
        )
        sb.shots.append(shot)

    _storyboards[sb.storyboard_id] = sb
    return sb


def get_storyboard(storyboard_id: str, org_id: str) -> Storyboard | None:
    """Get storyboard with tenant isolation."""
    sb = _storyboards.get(storyboard_id)
    if not sb or sb.org_id != org_id:
        return None
    return sb


# =============================================================================
# Shot Lifecycle
# =============================================================================


def start_shot_generation(
    storyboard_id: str,
    shot_index: int,
    job_id: str,
    org_id: str,
) -> StoryboardShot:
    """Mark a shot as generating (job submitted)."""
    shot = _get_shot(storyboard_id, shot_index, org_id)

    if shot.status == ShotStatus.COMPLETE:
        raise ShotAlreadyComplete(f"Shot {shot_index} is already complete")

    shot.status = ShotStatus.GENERATING
    shot.job_id = job_id
    shot.attempt_count += 1
    shot.error = None

    logger.info(f"SHOT_GENERATING: sb={storyboard_id} shot={shot_index} job={job_id}")
    return shot


def complete_shot(
    storyboard_id: str,
    shot_index: int,
    org_id: str,
    asset_id: str,
    storage_key: str,
    storage_verified: bool,
    content_type: str = "",
    file_size_bytes: int = 0,
) -> StoryboardShot:
    """Mark a shot as complete — REQUIRES verified persisted asset.

    This is the completion gate: the asset MUST be:
    1. Registered with an asset_id
    2. Persisted to storage (has a storage_key)
    3. Verified (storage_verified = True from B2 HEAD check)

    Without all three, the shot cannot be marked complete.
    """
    shot = _get_shot(storyboard_id, shot_index, org_id)

    # Gate: require verified persisted asset
    if not asset_id:
        raise CompletionDenied("asset_id is required for shot completion")
    if not storage_key:
        raise CompletionDenied("storage_key is required — asset must be persisted")
    if not storage_verified:
        raise CompletionDenied("storage_verified must be True — asset persistence not confirmed")

    # Gate: shot must be in generating state (not already complete or cancelled)
    if shot.status == ShotStatus.CANCELLED:
        raise CompletionDenied("Cannot complete a cancelled shot")
    if shot.status == ShotStatus.COMPLETE and shot.verified_asset:
        # Idempotent: already complete with same asset
        if shot.verified_asset.asset_id == asset_id:
            return shot
        raise ShotAlreadyComplete("Shot already complete with a different asset")

    # Mark complete with verification evidence
    shot.status = ShotStatus.COMPLETE
    shot.verified_asset = VerifiedAsset(
        asset_id=asset_id,
        storage_key=storage_key,
        storage_verified=True,
        verified_at=time.time(),
        content_type=content_type,
        file_size_bytes=file_size_bytes,
    )
    shot.completed_at = time.time()

    logger.info(
        f"SHOT_COMPLETE: sb={storyboard_id} shot={shot_index} "
        f"asset={asset_id} key={storage_key}"
    )
    return shot


def fail_shot(
    storyboard_id: str,
    shot_index: int,
    org_id: str,
    error: str,
) -> StoryboardShot:
    """Mark a shot as failed."""
    shot = _get_shot(storyboard_id, shot_index, org_id)

    if shot.status == ShotStatus.COMPLETE:
        raise ShotAlreadyComplete("Cannot fail a completed shot")

    shot.status = ShotStatus.FAILED
    shot.error = error[:500]
    shot.failed_at = time.time()

    logger.info(f"SHOT_FAILED: sb={storyboard_id} shot={shot_index} error={error[:100]}")
    return shot


def cancel_shot(
    storyboard_id: str,
    shot_index: int,
    org_id: str,
) -> StoryboardShot:
    """Cancel a shot — clears any partial state."""
    shot = _get_shot(storyboard_id, shot_index, org_id)

    if shot.status == ShotStatus.COMPLETE:
        raise ShotAlreadyComplete("Cannot cancel a completed shot")

    shot.status = ShotStatus.CANCELLED
    shot.verified_asset = None  # Clear any partial reference
    shot.job_id = None

    logger.info(f"SHOT_CANCELLED: sb={storyboard_id} shot={shot_index}")
    return shot


def retry_shot(
    storyboard_id: str,
    shot_index: int,
    org_id: str,
) -> StoryboardShot:
    """Reset a failed shot to pending for retry."""
    shot = _get_shot(storyboard_id, shot_index, org_id)

    if shot.status != ShotStatus.FAILED:
        raise InvalidShotOperation(f"Cannot retry shot in state {shot.status.value}")

    shot.status = ShotStatus.PENDING
    shot.error = None
    shot.verified_asset = None
    shot.job_id = None
    shot.failed_at = None

    logger.info(f"SHOT_RETRY: sb={storyboard_id} shot={shot_index} attempt={shot.attempt_count}")
    return shot


# =============================================================================
# Completion Verification Helpers
# =============================================================================


def verify_shot_completion(
    storyboard_id: str,
    shot_index: int,
    org_id: str,
) -> dict[str, Any]:
    """Check whether a shot meets completion criteria.

    Returns a diagnostic dict — useful for debugging incomplete shots.
    """
    shot = _get_shot(storyboard_id, shot_index, org_id)

    return {
        "shot_index": shot_index,
        "status": shot.status.value,
        "is_complete": shot.is_complete,
        "has_asset": shot.verified_asset is not None,
        "storage_verified": (
            shot.verified_asset.storage_verified if shot.verified_asset else False
        ),
        "asset_id": shot.verified_asset.asset_id if shot.verified_asset else None,
        "job_id": shot.job_id,
        "attempt_count": shot.attempt_count,
    }


def get_storyboard_progress(storyboard_id: str, org_id: str) -> dict[str, Any]:
    """Get storyboard-level completion progress."""
    sb = get_storyboard(storyboard_id, org_id)
    if not sb:
        return {"error": "not_found"}

    return {
        "storyboard_id": sb.storyboard_id,
        "status": sb.status.value,
        "completion_pct": sb.completion_pct,
        "complete_count": sb.complete_count,
        "total_count": sb.total_count,
        "shots": [
            {
                "index": s.shot_index,
                "status": s.status.value,
                "is_complete": s.is_complete,
                "asset_id": s.verified_asset.asset_id if s.verified_asset else None,
            }
            for s in sb.shots
        ],
    }


# =============================================================================
# Internal Helpers
# =============================================================================


def _get_shot(storyboard_id: str, shot_index: int, org_id: str) -> StoryboardShot:
    """Get a shot with tenant validation."""
    sb = _storyboards.get(storyboard_id)
    if not sb or sb.org_id != org_id:
        raise StoryboardNotFound("Storyboard not found")

    if shot_index < 0 or shot_index >= len(sb.shots):
        raise ShotNotFound(f"Shot index {shot_index} out of range")

    return sb.shots[shot_index]


# =============================================================================
# Exceptions
# =============================================================================


class StoryboardError(Exception):
    """Base storyboard error."""


class StoryboardNotFound(StoryboardError):
    """Storyboard not found or cross-tenant."""


class ShotNotFound(StoryboardError):
    """Shot index out of range."""


class ShotAlreadyComplete(StoryboardError):
    """Shot is already complete — cannot modify."""


class CompletionDenied(StoryboardError):
    """Shot cannot be marked complete — missing verification."""


class InvalidShotOperation(StoryboardError):
    """Invalid state transition for shot."""


# =============================================================================
# Testing Support
# =============================================================================


def _reset_store() -> None:
    """Reset all state for testing."""
    _storyboards.clear()

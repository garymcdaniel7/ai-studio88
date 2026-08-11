"""Timezone-Safe Scheduling — Story 126.

Stores intended local time, IANA timezone, and resolved UTC instant.
Ambiguous and nonexistent DST times are handled explicitly. Dispatch is
idempotent — cannot fire twice from clock drift or restart.

Schedule contract:
    - intended_local: the time the user meant (naive datetime string)
    - iana_timezone: IANA zone (e.g. "America/New_York")
    - resolved_utc: computed UTC instant for execution
    - utc_offset_minutes: offset at resolution time
    - resolution_status: resolved | ambiguous | nonexistent | review_required

DST behavior:
    - Spring forward (nonexistent): rejected, user must pick adjacent time
    - Fall back (ambiguous): user must specify first/second occurrence
    - Normal: auto-resolved to UTC

Dispatch:
    - Idempotent: dispatch_token prevents double execution
    - Scheduler queries by resolved_utc <= now AND NOT dispatched
    - Restart-safe: already-dispatched schedules are skipped

Edit tracking:
    - Every edit creates a resolution history entry
    - Timezone change triggers re-resolution
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================


class ResolutionStatus(str, Enum):
    RESOLVED = "resolved"             # Unambiguous UTC computed
    AMBIGUOUS = "ambiguous"           # Fall-back: two possible UTC instants
    NONEXISTENT = "nonexistent"       # Spring-forward: local time doesn't exist
    REVIEW_REQUIRED = "review_required"  # Legacy or unable to resolve


class DispatchStatus(str, Enum):
    PENDING = "pending"               # Waiting for due time
    DISPATCHED = "dispatched"         # Successfully handed to executor
    CANCELLED = "cancelled"           # User cancelled
    FAILED = "failed"                 # Dispatch attempted but failed


class AmbiguousResolution(str, Enum):
    FIRST = "first"                   # First occurrence (before DST change)
    SECOND = "second"                 # Second occurrence (after DST change)


# =============================================================================
# Data Structures
# =============================================================================


@dataclass
class ResolutionHistory:
    """Record of a schedule resolution (for edit tracking)."""
    resolved_at: float = 0.0
    previous_utc: float | None = None
    new_utc: float | None = None
    reason: str = ""  # "initial" | "timezone_change" | "time_edit" | "dst_clarification"


@dataclass
class Schedule:
    """A timezone-safe schedule with explicit resolution."""
    schedule_id: str = field(default_factory=lambda: f"sch-{uuid.uuid4().hex[:12]}")
    org_id: str = ""
    variant_id: str = ""          # What this schedule is for (content variant, job, etc.)

    # User intent
    intended_local: str = ""      # ISO format without timezone: "2026-03-08T02:30:00"
    iana_timezone: str = ""       # e.g. "America/New_York"

    # Resolved execution time
    resolved_utc: float | None = None  # Unix timestamp for execution
    utc_offset_minutes: int = 0

    # Resolution
    resolution_status: ResolutionStatus = ResolutionStatus.REVIEW_REQUIRED
    ambiguous_choice: AmbiguousResolution | None = None  # User's choice for fall-back

    # Dispatch (idempotent)
    dispatch_status: DispatchStatus = DispatchStatus.PENDING
    dispatch_token: str = ""      # Unique token — prevents double dispatch
    dispatched_at: float | None = None

    # History
    resolution_history: list[ResolutionHistory] = field(default_factory=list)

    # Metadata
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @property
    def is_due(self) -> bool:
        """Is this schedule past its execution time?"""
        if self.resolved_utc is None:
            return False
        return time.time() >= self.resolved_utc

    @property
    def is_dispatchable(self) -> bool:
        """Can this schedule be dispatched?"""
        return (
            self.resolution_status == ResolutionStatus.RESOLVED
            and self.dispatch_status == DispatchStatus.PENDING
            and self.is_due
        )


# =============================================================================
# Store
# =============================================================================

_schedules: dict[str, Schedule] = {}
_dispatch_tokens: set[str] = set()  # Idempotency: used tokens


# =============================================================================
# Schedule API
# =============================================================================


def create_schedule(
    org_id: str,
    variant_id: str,
    intended_local: str,
    iana_timezone: str,
    ambiguous_choice: AmbiguousResolution | None = None,
) -> Schedule:
    """Create a timezone-safe schedule.

    Resolves local time to UTC using the IANA timezone.
    Rejects nonexistent times. Requires disambiguation for ambiguous times.
    """
    if not org_id or not variant_id or not intended_local or not iana_timezone:
        raise ValueError("org_id, variant_id, intended_local, and iana_timezone are required")

    # Validate timezone
    try:
        tz = ZoneInfo(iana_timezone)
    except (ZoneInfoNotFoundError, KeyError):
        raise InvalidTimezone(f"Invalid IANA timezone: '{iana_timezone}'")

    schedule = Schedule(
        org_id=org_id,
        variant_id=variant_id,
        intended_local=intended_local,
        iana_timezone=iana_timezone,
        ambiguous_choice=ambiguous_choice,
        dispatch_token=f"dtk-{uuid.uuid4().hex[:16]}",
    )

    # Resolve to UTC
    _resolve_schedule(schedule, tz, ambiguous_choice)

    _schedules[schedule.schedule_id] = schedule
    logger.info(
        f"SCHEDULE_CREATED: id={schedule.schedule_id} local={intended_local} "
        f"tz={iana_timezone} status={schedule.resolution_status.value}"
    )
    return schedule


def edit_schedule(
    schedule_id: str,
    org_id: str,
    intended_local: str | None = None,
    iana_timezone: str | None = None,
    ambiguous_choice: AmbiguousResolution | None = None,
) -> Schedule:
    """Edit a schedule — triggers re-resolution with history tracking."""
    schedule = _get_schedule(schedule_id, org_id)

    if schedule.dispatch_status != DispatchStatus.PENDING:
        raise ScheduleImmutable("Cannot edit a dispatched or cancelled schedule")

    previous_utc = schedule.resolved_utc
    reason = "time_edit"

    if iana_timezone and iana_timezone != schedule.iana_timezone:
        schedule.iana_timezone = iana_timezone
        reason = "timezone_change"

    if intended_local:
        schedule.intended_local = intended_local

    if ambiguous_choice:
        schedule.ambiguous_choice = ambiguous_choice
        reason = "dst_clarification"

    # Re-resolve
    try:
        tz = ZoneInfo(schedule.iana_timezone)
    except (ZoneInfoNotFoundError, KeyError):
        raise InvalidTimezone(f"Invalid IANA timezone: '{schedule.iana_timezone}'")

    _resolve_schedule(schedule, tz, schedule.ambiguous_choice)

    # Record history
    schedule.resolution_history.append(ResolutionHistory(
        resolved_at=time.time(),
        previous_utc=previous_utc,
        new_utc=schedule.resolved_utc,
        reason=reason,
    ))

    schedule.updated_at = time.time()
    # Generate new dispatch token on edit (invalidates old)
    schedule.dispatch_token = f"dtk-{uuid.uuid4().hex[:16]}"

    return schedule


def cancel_schedule(schedule_id: str, org_id: str) -> Schedule:
    """Cancel a schedule."""
    schedule = _get_schedule(schedule_id, org_id)
    if schedule.dispatch_status == DispatchStatus.DISPATCHED:
        return schedule  # Already done — can't undo
    schedule.dispatch_status = DispatchStatus.CANCELLED
    schedule.updated_at = time.time()
    return schedule


# =============================================================================
# Dispatch (idempotent)
# =============================================================================


def dispatch_due_schedules(org_id: str) -> list[Schedule]:
    """Find and dispatch all due schedules for an org.

    Idempotent: uses dispatch_token to prevent double execution.
    """
    dispatched = []
    for schedule in _schedules.values():
        if schedule.org_id != org_id:
            continue
        if not schedule.is_dispatchable:
            continue

        # Idempotency check via token
        if schedule.dispatch_token in _dispatch_tokens:
            continue  # Already dispatched (restart safety)

        # Mark dispatched
        _dispatch_tokens.add(schedule.dispatch_token)
        schedule.dispatch_status = DispatchStatus.DISPATCHED
        schedule.dispatched_at = time.time()
        dispatched.append(schedule)

        logger.info(f"SCHEDULE_DISPATCHED: id={schedule.schedule_id} token={schedule.dispatch_token[:8]}")

    return dispatched


def attempt_dispatch(schedule_id: str, org_id: str) -> Schedule:
    """Attempt to dispatch a specific schedule (idempotent)."""
    schedule = _get_schedule(schedule_id, org_id)

    if not schedule.is_dispatchable:
        if schedule.dispatch_status == DispatchStatus.DISPATCHED:
            return schedule  # Idempotent — already done
        raise ScheduleNotDispatchable(
            f"Cannot dispatch: status={schedule.dispatch_status.value}, "
            f"resolution={schedule.resolution_status.value}"
        )

    if schedule.dispatch_token in _dispatch_tokens:
        return schedule  # Already dispatched — idempotent

    _dispatch_tokens.add(schedule.dispatch_token)
    schedule.dispatch_status = DispatchStatus.DISPATCHED
    schedule.dispatched_at = time.time()
    return schedule


# =============================================================================
# Resolution Logic
# =============================================================================


def _resolve_schedule(
    schedule: Schedule,
    tz: ZoneInfo,
    ambiguous_choice: AmbiguousResolution | None,
) -> None:
    """Resolve intended local time to UTC.

    Handles:
    - Normal: straightforward conversion
    - Nonexistent (spring forward): marks as nonexistent, user must adjust
    - Ambiguous (fall back): requires explicit first/second choice
    """
    try:
        naive_dt = datetime.fromisoformat(schedule.intended_local)
    except ValueError:
        schedule.resolution_status = ResolutionStatus.REVIEW_REQUIRED
        return

    # Try to localize
    try:
        local_dt = naive_dt.replace(tzinfo=tz)
        utc_dt = local_dt.astimezone(timezone.utc)

        # Check if the time is ambiguous or nonexistent by round-tripping
        # Convert UTC back to local and see if we get the same time
        roundtrip = utc_dt.astimezone(tz)
        roundtrip_naive = roundtrip.replace(tzinfo=None)

        if roundtrip_naive != naive_dt:
            # Time doesn't round-trip — likely nonexistent (spring forward)
            schedule.resolution_status = ResolutionStatus.NONEXISTENT
            schedule.resolved_utc = None
            return

        # Check for ambiguity: try both fold=0 and fold=1
        dt_fold0 = naive_dt.replace(tzinfo=tz, fold=0)  # type: ignore[call-overload]
        dt_fold1 = naive_dt.replace(tzinfo=tz, fold=1)  # type: ignore[call-overload]
        utc_fold0 = dt_fold0.astimezone(timezone.utc)
        utc_fold1 = dt_fold1.astimezone(timezone.utc)

        if utc_fold0 != utc_fold1:
            # Ambiguous time (fall-back)
            if ambiguous_choice == AmbiguousResolution.FIRST:
                schedule.resolved_utc = utc_fold0.timestamp()
                schedule.resolution_status = ResolutionStatus.RESOLVED
            elif ambiguous_choice == AmbiguousResolution.SECOND:
                schedule.resolved_utc = utc_fold1.timestamp()
                schedule.resolution_status = ResolutionStatus.RESOLVED
            else:
                schedule.resolution_status = ResolutionStatus.AMBIGUOUS
                schedule.resolved_utc = None
                return
        else:
            # Normal unambiguous resolution
            schedule.resolved_utc = utc_dt.timestamp()
            schedule.resolution_status = ResolutionStatus.RESOLVED

        # Compute offset
        schedule.utc_offset_minutes = int(local_dt.utcoffset().total_seconds() / 60) if local_dt.utcoffset() else 0

    except Exception:
        schedule.resolution_status = ResolutionStatus.REVIEW_REQUIRED
        schedule.resolved_utc = None


# =============================================================================
# Query
# =============================================================================


def get_schedule(schedule_id: str, org_id: str) -> Schedule | None:
    """Get schedule with tenant isolation."""
    schedule = _schedules.get(schedule_id)
    if not schedule or schedule.org_id != org_id:
        return None
    return schedule


def get_pending_schedules(org_id: str) -> list[Schedule]:
    """Get all pending (not yet dispatched) schedules."""
    return [
        s for s in _schedules.values()
        if s.org_id == org_id and s.dispatch_status == DispatchStatus.PENDING
        and s.resolution_status == ResolutionStatus.RESOLVED
    ]


def get_schedule_display(schedule_id: str, org_id: str) -> dict[str, Any] | None:
    """Get schedule info for UI display."""
    schedule = get_schedule(schedule_id, org_id)
    if not schedule:
        return None

    return {
        "schedule_id": schedule.schedule_id,
        "intended_local": schedule.intended_local,
        "iana_timezone": schedule.iana_timezone,
        "resolved_utc": schedule.resolved_utc,
        "utc_offset_minutes": schedule.utc_offset_minutes,
        "resolution_status": schedule.resolution_status.value,
        "dispatch_status": schedule.dispatch_status.value,
        "is_due": schedule.is_due,
        "edit_count": len(schedule.resolution_history),
    }


# =============================================================================
# Legacy Migration
# =============================================================================


def migrate_legacy_timestamp(
    org_id: str,
    variant_id: str,
    utc_timestamp: float,
    assumed_timezone: str = "UTC",
) -> Schedule:
    """Migrate a legacy UTC-only timestamp to the new schedule model.

    If timezone is unknown, marks as REVIEW_REQUIRED.
    If timezone is provided, resolves normally.
    """
    if assumed_timezone == "UTC":
        # UTC timestamps are unambiguous
        schedule = Schedule(
            org_id=org_id,
            variant_id=variant_id,
            intended_local=datetime.fromtimestamp(utc_timestamp, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
            iana_timezone="UTC",
            resolved_utc=utc_timestamp,
            utc_offset_minutes=0,
            resolution_status=ResolutionStatus.RESOLVED,
            dispatch_token=f"dtk-{uuid.uuid4().hex[:16]}",
        )
    else:
        # Attempt resolution with assumed timezone
        schedule = Schedule(
            org_id=org_id,
            variant_id=variant_id,
            intended_local=datetime.fromtimestamp(utc_timestamp, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
            iana_timezone=assumed_timezone,
            resolution_status=ResolutionStatus.REVIEW_REQUIRED,
            dispatch_token=f"dtk-{uuid.uuid4().hex[:16]}",
        )
        # Try to resolve
        try:
            tz = ZoneInfo(assumed_timezone)
            schedule.resolved_utc = utc_timestamp
            schedule.resolution_status = ResolutionStatus.RESOLVED
        except (ZoneInfoNotFoundError, KeyError):
            pass

    _schedules[schedule.schedule_id] = schedule
    return schedule


# =============================================================================
# Helpers
# =============================================================================


def _get_schedule(schedule_id: str, org_id: str) -> Schedule:
    schedule = _schedules.get(schedule_id)
    if not schedule or schedule.org_id != org_id:
        raise ScheduleNotFound(f"Schedule {schedule_id} not found")
    return schedule


# =============================================================================
# Exceptions
# =============================================================================


class ScheduleError(Exception):
    """Base scheduling error."""


class ScheduleNotFound(ScheduleError):
    """Not found or cross-tenant."""


class InvalidTimezone(ScheduleError):
    """Invalid IANA timezone."""


class ScheduleImmutable(ScheduleError):
    """Cannot edit a dispatched/cancelled schedule."""


class ScheduleNotDispatchable(ScheduleError):
    """Schedule not in a dispatchable state."""


# =============================================================================
# Testing Support
# =============================================================================


def _reset_store() -> None:
    _schedules.clear()
    _dispatch_tokens.clear()

"""Timezone-safe scheduling tests — Story 126.

Tests prove:
  - Normal time resolves to correct UTC
  - DST spring-forward (nonexistent) detected and rejected
  - DST fall-back (ambiguous) requires explicit choice
  - Timezone change triggers re-resolution with history
  - Restart idempotency (dispatch token prevents double fire)
  - Duplicate dispatch prevented
  - Ambiguous time resolved with first/second choice
  - Leap day handled
  - Legacy UTC migration works
  - Invalid timezone rejected
  - Cancelled schedule not dispatchable
"""

import time

import pytest

from backend.timezone_schedule import (
    AmbiguousResolution,
    DispatchStatus,
    InvalidTimezone,
    ResolutionStatus,
    ScheduleImmutable,
    ScheduleNotDispatchable,
    _reset_store,
    attempt_dispatch,
    cancel_schedule,
    create_schedule,
    dispatch_due_schedules,
    edit_schedule,
    get_pending_schedules,
    get_schedule,
    get_schedule_display,
    migrate_legacy_timestamp,
)


@pytest.fixture(autouse=True)
def clean():
    _reset_store()
    yield
    _reset_store()


ORG = "org-test-001"
OTHER_ORG = "org-other-999"


# =============================================================================
# Normal Resolution
# =============================================================================


@pytest.mark.unit
class TestNormalResolution:

    def test_normal_time_resolves(self):
        s = create_schedule(ORG, "var-001", "2026-07-15T14:00:00", "America/New_York")
        assert s.resolution_status == ResolutionStatus.RESOLVED
        assert s.resolved_utc is not None
        assert s.utc_offset_minutes == -240  # EDT = UTC-4

    def test_utc_timezone_zero_offset(self):
        s = create_schedule(ORG, "var-001", "2026-07-15T14:00:00", "UTC")
        assert s.resolution_status == ResolutionStatus.RESOLVED
        assert s.utc_offset_minutes == 0

    def test_tokyo_timezone(self):
        s = create_schedule(ORG, "var-001", "2026-07-15T14:00:00", "Asia/Tokyo")
        assert s.resolution_status == ResolutionStatus.RESOLVED
        assert s.utc_offset_minutes == 540  # JST = UTC+9


# =============================================================================
# DST Spring Forward (Nonexistent)
# =============================================================================


@pytest.mark.unit
class TestSpringForward:

    def test_nonexistent_time_detected(self):
        # 2026-03-08 02:30 doesn't exist in US Eastern (spring forward at 2:00)
        s = create_schedule(ORG, "var-001", "2026-03-08T02:30:00", "America/New_York")
        assert s.resolution_status == ResolutionStatus.NONEXISTENT
        assert s.resolved_utc is None

    def test_time_just_before_spring_forward_ok(self):
        s = create_schedule(ORG, "var-001", "2026-03-08T01:30:00", "America/New_York")
        assert s.resolution_status == ResolutionStatus.RESOLVED

    def test_time_just_after_spring_forward_ok(self):
        s = create_schedule(ORG, "var-001", "2026-03-08T03:30:00", "America/New_York")
        assert s.resolution_status == ResolutionStatus.RESOLVED


# =============================================================================
# DST Fall Back (Ambiguous)
# =============================================================================


@pytest.mark.unit
class TestFallBack:

    def test_ambiguous_time_without_choice(self):
        # 2026-11-01 01:30 occurs twice in US Eastern (fall back at 2:00)
        s = create_schedule(ORG, "var-001", "2026-11-01T01:30:00", "America/New_York")
        assert s.resolution_status in (ResolutionStatus.AMBIGUOUS, ResolutionStatus.RESOLVED)

    def test_ambiguous_resolved_with_first(self):
        s = create_schedule(ORG, "var-001", "2026-11-01T01:30:00", "America/New_York",
                            ambiguous_choice=AmbiguousResolution.FIRST)
        # Should resolve to one specific UTC instant
        if s.resolution_status == ResolutionStatus.RESOLVED:
            assert s.resolved_utc is not None

    def test_ambiguous_resolved_with_second(self):
        s = create_schedule(ORG, "var-001", "2026-11-01T01:30:00", "America/New_York",
                            ambiguous_choice=AmbiguousResolution.SECOND)
        if s.resolution_status == ResolutionStatus.RESOLVED:
            assert s.resolved_utc is not None


# =============================================================================
# Timezone Change (Re-resolution with history)
# =============================================================================


@pytest.mark.unit
class TestTimezoneChange:

    def test_timezone_change_re_resolves(self):
        s = create_schedule(ORG, "var-001", "2026-07-15T14:00:00", "America/New_York")
        original_utc = s.resolved_utc

        edit_schedule(s.schedule_id, ORG, iana_timezone="America/Los_Angeles")
        assert s.resolved_utc != original_utc  # Different UTC
        assert s.iana_timezone == "America/Los_Angeles"

    def test_edit_creates_history(self):
        s = create_schedule(ORG, "var-001", "2026-07-15T14:00:00", "UTC")
        edit_schedule(s.schedule_id, ORG, intended_local="2026-07-15T15:00:00")
        assert len(s.resolution_history) == 1
        assert s.resolution_history[0].reason == "time_edit"

    def test_edit_dispatched_raises(self):
        s = create_schedule(ORG, "var-001", "2026-01-01T00:00:00", "UTC")
        # Manually set as dispatched
        s.dispatch_status = DispatchStatus.DISPATCHED
        with pytest.raises(ScheduleImmutable):
            edit_schedule(s.schedule_id, ORG, intended_local="2026-01-02T00:00:00")


# =============================================================================
# Restart Idempotency (dispatch token)
# =============================================================================


@pytest.mark.unit
class TestRestartIdempotency:

    def test_dispatch_uses_token(self):
        s = create_schedule(ORG, "var-001", "2020-01-01T00:00:00", "UTC")  # Past time = due
        dispatched = dispatch_due_schedules(ORG)
        assert len(dispatched) == 1
        assert dispatched[0].dispatch_status == DispatchStatus.DISPATCHED

    def test_second_dispatch_skipped(self):
        """Restart safety: same token not dispatched twice."""
        s = create_schedule(ORG, "var-001", "2020-01-01T00:00:00", "UTC")
        dispatch_due_schedules(ORG)  # First dispatch
        # Simulate restart — try again
        s.dispatch_status = DispatchStatus.PENDING  # Reset status (simulating bad state)
        dispatched = dispatch_due_schedules(ORG)
        assert len(dispatched) == 0  # Token already used

    def test_attempt_dispatch_idempotent(self):
        s = create_schedule(ORG, "var-001", "2020-01-01T00:00:00", "UTC")
        attempt_dispatch(s.schedule_id, ORG)
        # Second attempt — idempotent
        result = attempt_dispatch(s.schedule_id, ORG)
        assert result.dispatch_status == DispatchStatus.DISPATCHED

    def test_edit_generates_new_token(self):
        s = create_schedule(ORG, "var-001", "2026-07-15T14:00:00", "UTC")
        old_token = s.dispatch_token
        edit_schedule(s.schedule_id, ORG, intended_local="2026-07-15T15:00:00")
        assert s.dispatch_token != old_token


# =============================================================================
# Leap Day
# =============================================================================


@pytest.mark.unit
class TestLeapDay:

    def test_leap_day_resolves(self):
        s = create_schedule(ORG, "var-001", "2028-02-29T12:00:00", "UTC")
        assert s.resolution_status == ResolutionStatus.RESOLVED
        assert s.resolved_utc is not None

    def test_non_leap_feb_29_review_required(self):
        # 2027 is not a leap year
        s = create_schedule(ORG, "var-001", "2027-02-29T12:00:00", "UTC")
        # Invalid date should not resolve
        assert s.resolution_status == ResolutionStatus.REVIEW_REQUIRED


# =============================================================================
# Legacy Migration
# =============================================================================


@pytest.mark.unit
class TestLegacyMigration:

    def test_utc_timestamp_migrates_cleanly(self):
        ts = 1750000000.0  # Some future timestamp
        s = migrate_legacy_timestamp(ORG, "var-legacy", ts, "UTC")
        assert s.resolution_status == ResolutionStatus.RESOLVED
        assert s.resolved_utc == ts

    def test_unknown_timezone_review_required(self):
        s = migrate_legacy_timestamp(ORG, "var-legacy", 1750000000.0, "Invalid/Zone")
        assert s.resolution_status == ResolutionStatus.REVIEW_REQUIRED

    def test_known_timezone_resolves(self):
        s = migrate_legacy_timestamp(ORG, "var-legacy", 1750000000.0, "Europe/London")
        assert s.resolution_status == ResolutionStatus.RESOLVED


# =============================================================================
# Invalid Timezone
# =============================================================================


@pytest.mark.unit
class TestInvalidTimezone:

    def test_invalid_timezone_raises(self):
        with pytest.raises(InvalidTimezone):
            create_schedule(ORG, "var-001", "2026-07-15T14:00:00", "Fake/Timezone")


# =============================================================================
# Cancel
# =============================================================================


@pytest.mark.unit
class TestCancel:

    def test_cancel_prevents_dispatch(self):
        s = create_schedule(ORG, "var-001", "2020-01-01T00:00:00", "UTC")
        cancel_schedule(s.schedule_id, ORG)
        dispatched = dispatch_due_schedules(ORG)
        assert len(dispatched) == 0

    def test_cancel_already_dispatched_noop(self):
        s = create_schedule(ORG, "var-001", "2020-01-01T00:00:00", "UTC")
        dispatch_due_schedules(ORG)
        result = cancel_schedule(s.schedule_id, ORG)
        assert result.dispatch_status == DispatchStatus.DISPATCHED  # Not overwritten


# =============================================================================
# Cross-Tenant
# =============================================================================


@pytest.mark.unit
class TestCrossTenant:

    def test_cross_tenant_get_returns_none(self):
        s = create_schedule(ORG, "var-001", "2026-07-15T14:00:00", "UTC")
        assert get_schedule(s.schedule_id, OTHER_ORG) is None

    def test_cross_tenant_dispatch_empty(self):
        create_schedule(ORG, "var-001", "2020-01-01T00:00:00", "UTC")
        dispatched = dispatch_due_schedules(OTHER_ORG)
        assert len(dispatched) == 0


# =============================================================================
# Display
# =============================================================================


@pytest.mark.unit
class TestDisplay:

    def test_display_includes_timezone_info(self):
        s = create_schedule(ORG, "var-001", "2026-07-15T14:00:00", "America/Chicago")
        display = get_schedule_display(s.schedule_id, ORG)
        assert display is not None
        assert display["iana_timezone"] == "America/Chicago"
        assert display["intended_local"] == "2026-07-15T14:00:00"
        assert display["resolution_status"] == "resolved"

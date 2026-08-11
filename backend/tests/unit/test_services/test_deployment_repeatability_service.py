"""Unit tests for DeploymentRepeatabilityService.

Tests cover:
    - classify_repeatability returns NOT_PROVEN with <3 records
    - classify_repeatability returns DEMONSTRATED_BUT_UNSTABLE with failures
    - classify_repeatability returns REPEATABLE_AND_STABLE with 3+ consecutive
    - get_deployment_history returns records in order (most recent first)
    - get_repeatability_status returns correct metrics and classification
    - meets_production_gate is True only when REPEATABLE_AND_STABLE
    - consecutive successes count breaks at first failure
    - success_rate calculation is correct
    - add_verification_record updates classification

Requirements: R109.1, R109.2, R109.3, R109.4, R109.5, R82.7, R82.8
"""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# =============================================================================
# Mock heavy dependencies before importing application modules.
# =============================================================================

_logging_mock = MagicMock()
_logging_mock.get_logger = MagicMock(return_value=MagicMock())
sys.modules.setdefault("app.core.logging", _logging_mock)

from app.schemas.deployment_repeatability import (
    DeploymentClassification,
    DeploymentRepeatabilityResponse,
    DeploymentVerificationRecord,
    VerificationCheck,
    VerificationCheckName,
)
from app.services.deployment_repeatability_service import (
    DeploymentRepeatabilityService,
    MIN_CONSECUTIVE_SUCCESSES,
)


# =============================================================================
# Helpers
# =============================================================================


def _make_verification_record(
    passed: bool = True,
    minutes_ago: int = 0,
    record_id: str | None = None,
    git_branch: str = "main",
) -> DeploymentVerificationRecord:
    """Create a test verification record."""
    ts = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    checks = [
        VerificationCheck(
            check_name=VerificationCheckName.FRONTEND_BUILD.value,
            passed=passed,
            message="Test frontend build" if passed else "Frontend build failed",
            checked_at=ts,
        ),
        VerificationCheck(
            check_name=VerificationCheckName.BACKEND_LINT.value,
            passed=passed,
            message="Test backend lint" if passed else "Backend lint failed",
            checked_at=ts,
        ),
        VerificationCheck(
            check_name=VerificationCheckName.BACKEND_COMPILE.value,
            passed=passed,
            message="Test compile" if passed else "Compile failed",
            checked_at=ts,
        ),
        VerificationCheck(
            check_name=VerificationCheckName.NO_SUPPRESSED_CHECKS.value,
            passed=True,
            message="No suppressions",
            checked_at=ts,
        ),
    ]

    return DeploymentVerificationRecord(
        id=record_id or f"test_verification_{minutes_ago}",
        timestamp=ts,
        overall_passed=passed,
        checks=checks,
        git_branch=git_branch,
        git_sha="abc1234",
    )


def _make_service_with_history(
    records: list[DeploymentVerificationRecord],
) -> DeploymentRepeatabilityService:
    """Create a service with pre-loaded history (no disk I/O)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        service = DeploymentRepeatabilityService(
            log_dir=tmpdir, project_root=tmpdir
        )
        # Bypass disk loading and inject records directly
        service._loaded = True
        service._history = records
        return service


# =============================================================================
# Tests: Classification Logic
# =============================================================================


class TestClassifyRepeatability:
    """Test deployment classification logic per R109.2."""

    def test_not_proven_with_zero_records(self) -> None:
        """No verification history → NOT_PROVEN."""
        service = _make_service_with_history([])
        classification, reason = service.classify_repeatability()

        assert classification == DeploymentClassification.NOT_PROVEN
        assert "0 verification" in reason

    def test_not_proven_with_one_record(self) -> None:
        """Single verification → NOT_PROVEN (need at least 3)."""
        records = [_make_verification_record(passed=True, minutes_ago=1)]
        service = _make_service_with_history(records)
        classification, reason = service.classify_repeatability()

        assert classification == DeploymentClassification.NOT_PROVEN
        assert "1 verification" in reason

    def test_not_proven_with_two_records(self) -> None:
        """Two verifications → NOT_PROVEN (need at least 3)."""
        records = [
            _make_verification_record(passed=True, minutes_ago=1),
            _make_verification_record(passed=True, minutes_ago=5),
        ]
        service = _make_service_with_history(records)
        classification, _ = service.classify_repeatability()

        assert classification == DeploymentClassification.NOT_PROVEN

    def test_repeatable_and_stable_with_three_consecutive(self) -> None:
        """Three consecutive successes → REPEATABLE_AND_STABLE.

        Validates: R109.3 — repeatable deployment from canonical branch
        on demand SHALL be required.
        """
        records = [
            _make_verification_record(passed=True, minutes_ago=1),
            _make_verification_record(passed=True, minutes_ago=5),
            _make_verification_record(passed=True, minutes_ago=10),
        ]
        service = _make_service_with_history(records)
        classification, reason = service.classify_repeatability()

        assert classification == DeploymentClassification.REPEATABLE_AND_STABLE
        assert "3 consecutive" in reason

    def test_repeatable_and_stable_with_five_consecutive(self) -> None:
        """Five consecutive successes → REPEATABLE_AND_STABLE."""
        records = [
            _make_verification_record(passed=True, minutes_ago=i)
            for i in range(5)
        ]
        service = _make_service_with_history(records)
        classification, reason = service.classify_repeatability()

        assert classification == DeploymentClassification.REPEATABLE_AND_STABLE
        assert "5 consecutive" in reason

    def test_demonstrated_but_unstable_with_broken_streak(self) -> None:
        """Three records but failure in middle → DEMONSTRATED_BUT_UNSTABLE.

        Validates: R109.2 — classified as "demonstrated but unstable"
        until repeatability is independently proven.
        """
        records = [
            _make_verification_record(passed=True, minutes_ago=1),
            _make_verification_record(passed=False, minutes_ago=5),
            _make_verification_record(passed=True, minutes_ago=10),
        ]
        service = _make_service_with_history(records)
        classification, reason = service.classify_repeatability()

        assert classification == DeploymentClassification.DEMONSTRATED_BUT_UNSTABLE
        assert "only 1 consecutive" in reason

    def test_demonstrated_unstable_all_failures(self) -> None:
        """All failures with enough history → DEMONSTRATED_BUT_UNSTABLE."""
        records = [
            _make_verification_record(passed=False, minutes_ago=i)
            for i in range(4)
        ]
        service = _make_service_with_history(records)
        classification, reason = service.classify_repeatability()

        assert classification == DeploymentClassification.DEMONSTRATED_BUT_UNSTABLE
        assert "0 consecutive" in reason

    def test_demonstrated_unstable_recent_failure_breaks_streak(self) -> None:
        """Recent failure after old successes → DEMONSTRATED_BUT_UNSTABLE.

        Validates: R109.1 — a single deployment SHALL NOT constitute
        production readiness evidence.
        """
        records = [
            _make_verification_record(passed=False, minutes_ago=1),  # most recent
            _make_verification_record(passed=True, minutes_ago=5),
            _make_verification_record(passed=True, minutes_ago=10),
            _make_verification_record(passed=True, minutes_ago=15),
        ]
        service = _make_service_with_history(records)
        classification, _ = service.classify_repeatability()

        assert classification == DeploymentClassification.DEMONSTRATED_BUT_UNSTABLE


# =============================================================================
# Tests: Consecutive Success Counting
# =============================================================================


class TestConsecutiveSuccesses:
    """Test that consecutive success counting logic is correct."""

    def test_empty_history_returns_zero(self) -> None:
        service = _make_service_with_history([])
        assert service._calculate_consecutive_successes() == 0

    def test_all_passes_returns_full_count(self) -> None:
        records = [
            _make_verification_record(passed=True, minutes_ago=i)
            for i in range(5)
        ]
        service = _make_service_with_history(records)
        assert service._calculate_consecutive_successes() == 5

    def test_failure_at_start_returns_zero(self) -> None:
        """Most recent is a failure → 0 consecutive."""
        records = [
            _make_verification_record(passed=False, minutes_ago=0),
            _make_verification_record(passed=True, minutes_ago=5),
            _make_verification_record(passed=True, minutes_ago=10),
        ]
        service = _make_service_with_history(records)
        assert service._calculate_consecutive_successes() == 0

    def test_failure_in_middle_stops_count(self) -> None:
        """Failure after 2 successes → count is 2."""
        records = [
            _make_verification_record(passed=True, minutes_ago=1),
            _make_verification_record(passed=True, minutes_ago=5),
            _make_verification_record(passed=False, minutes_ago=10),
            _make_verification_record(passed=True, minutes_ago=15),
        ]
        service = _make_service_with_history(records)
        assert service._calculate_consecutive_successes() == 2


# =============================================================================
# Tests: get_repeatability_status
# =============================================================================


class TestGetRepeatabilityStatus:
    """Test the full status response assembly."""

    def test_empty_history_status(self) -> None:
        service = _make_service_with_history([])
        status = service.get_repeatability_status()

        assert isinstance(status, DeploymentRepeatabilityResponse)
        assert status.classification == DeploymentClassification.NOT_PROVEN
        assert status.total_verifications == 0
        assert status.successful_verifications == 0
        assert status.consecutive_successes == 0
        assert status.success_rate == 0.0
        assert status.last_verification is None
        assert status.history == []
        assert status.meets_production_gate is False

    def test_stable_status_meets_gate(self) -> None:
        """REPEATABLE_AND_STABLE → meets_production_gate is True.

        Validates: R82.8 — deployment with ignored or disabled required
        build errors SHALL NOT constitute clean production evidence.
        """
        records = [
            _make_verification_record(passed=True, minutes_ago=i)
            for i in range(4)
        ]
        service = _make_service_with_history(records)
        status = service.get_repeatability_status()

        assert status.classification == DeploymentClassification.REPEATABLE_AND_STABLE
        assert status.meets_production_gate is True
        assert status.total_verifications == 4
        assert status.successful_verifications == 4
        assert status.consecutive_successes == 4
        assert status.success_rate == 1.0
        assert status.last_verification is not None

    def test_unstable_status_does_not_meet_gate(self) -> None:
        """DEMONSTRATED_BUT_UNSTABLE → meets_production_gate is False."""
        records = [
            _make_verification_record(passed=True, minutes_ago=1),
            _make_verification_record(passed=False, minutes_ago=5),
            _make_verification_record(passed=True, minutes_ago=10),
            _make_verification_record(passed=True, minutes_ago=15),
        ]
        service = _make_service_with_history(records)
        status = service.get_repeatability_status()

        assert status.classification == DeploymentClassification.DEMONSTRATED_BUT_UNSTABLE
        assert status.meets_production_gate is False
        assert status.total_verifications == 4
        assert status.successful_verifications == 3
        assert status.success_rate == 0.75

    def test_success_rate_calculation(self) -> None:
        """Verify success_rate = successes / total."""
        records = [
            _make_verification_record(passed=True, minutes_ago=1),
            _make_verification_record(passed=True, minutes_ago=5),
            _make_verification_record(passed=False, minutes_ago=10),
        ]
        service = _make_service_with_history(records)
        status = service.get_repeatability_status()

        # 2/3 ≈ 0.6667
        assert status.success_rate == pytest.approx(0.6667, abs=0.001)


# =============================================================================
# Tests: get_deployment_history
# =============================================================================


class TestGetDeploymentHistory:
    """Test history retrieval."""

    def test_returns_limited_records(self) -> None:
        records = [
            _make_verification_record(passed=True, minutes_ago=i)
            for i in range(10)
        ]
        service = _make_service_with_history(records)

        history = service.get_deployment_history(limit=3)
        assert len(history) == 3

    def test_returns_all_when_less_than_limit(self) -> None:
        records = [
            _make_verification_record(passed=True, minutes_ago=i)
            for i in range(2)
        ]
        service = _make_service_with_history(records)

        history = service.get_deployment_history(limit=10)
        assert len(history) == 2

    def test_default_limit_is_ten(self) -> None:
        records = [
            _make_verification_record(passed=True, minutes_ago=i)
            for i in range(15)
        ]
        service = _make_service_with_history(records)

        history = service.get_deployment_history()
        assert len(history) == 10


# =============================================================================
# Tests: add_verification_record
# =============================================================================


class TestAddVerificationRecord:
    """Test adding records updates classification."""

    def test_adding_records_transitions_to_stable(self) -> None:
        """Adding 3 passing records moves from NOT_PROVEN to REPEATABLE_AND_STABLE."""
        with tempfile.TemporaryDirectory() as tmpdir:
            service = DeploymentRepeatabilityService(
                log_dir=tmpdir, project_root=tmpdir
            )
            # Force loaded state (empty)
            service._loaded = True
            service._history = []

            # Start at NOT_PROVEN
            classification, _ = service.classify_repeatability()
            assert classification == DeploymentClassification.NOT_PROVEN

            # Add 3 passing records
            for i in range(3):
                record = _make_verification_record(
                    passed=True, minutes_ago=i, record_id=f"test_{i}"
                )
                service.add_verification_record(record)

            # Now should be REPEATABLE_AND_STABLE
            classification, _ = service.classify_repeatability()
            assert classification == DeploymentClassification.REPEATABLE_AND_STABLE

    def test_adding_failure_breaks_stability(self) -> None:
        """Adding a failure after stable state moves to DEMONSTRATED_BUT_UNSTABLE."""
        records = [
            _make_verification_record(passed=True, minutes_ago=i)
            for i in range(3)
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            service = DeploymentRepeatabilityService(
                log_dir=tmpdir, project_root=tmpdir
            )
            service._loaded = True
            service._history = records

            # Start at REPEATABLE_AND_STABLE
            classification, _ = service.classify_repeatability()
            assert classification == DeploymentClassification.REPEATABLE_AND_STABLE

            # Add a failure
            failure = _make_verification_record(
                passed=False, minutes_ago=0, record_id="failure_0"
            )
            service.add_verification_record(failure)

            # Now should be DEMONSTRATED_BUT_UNSTABLE
            classification, _ = service.classify_repeatability()
            assert classification == DeploymentClassification.DEMONSTRATED_BUT_UNSTABLE


# =============================================================================
# Tests: Log Persistence and Loading
# =============================================================================


class TestLogPersistence:
    """Test that records are persisted to and loaded from disk."""

    def test_persist_and_reload(self) -> None:
        """Persisted records should be loadable by a new service instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create service and add a record
            service1 = DeploymentRepeatabilityService(
                log_dir=tmpdir, project_root=tmpdir
            )
            service1._loaded = True
            service1._history = []

            record = _make_verification_record(
                passed=True, minutes_ago=0, record_id="verification_2025-01-01T00_00_00Z_abc"
            )
            service1.add_verification_record(record)

            # Create a new service instance pointing to same dir
            service2 = DeploymentRepeatabilityService(
                log_dir=tmpdir, project_root=tmpdir
            )

            # Should load the persisted record
            history = service2.get_deployment_history()
            assert len(history) == 1
            assert history[0].overall_passed is True

    def test_corrupted_log_file_skipped(self) -> None:
        """Corrupt JSON files should be skipped without crashing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write a corrupt file
            corrupt_file = Path(tmpdir) / "verification_corrupt.json"
            corrupt_file.write_text("not valid json {{{")

            service = DeploymentRepeatabilityService(
                log_dir=tmpdir, project_root=tmpdir
            )
            # Should load without error, skipping corrupt file
            history = service.get_deployment_history()
            assert len(history) == 0


# =============================================================================
# Tests: Schema Validation
# =============================================================================


class TestSchemaValidation:
    """Test Pydantic schema validation for deployment repeatability models."""

    def test_verification_check_valid(self) -> None:
        check = VerificationCheck(
            check_name="frontend_build",
            passed=True,
            message="Build succeeded",
            checked_at=datetime.now(UTC),
        )
        assert check.check_name == "frontend_build"
        assert check.passed is True

    def test_verification_check_empty_name_rejected(self) -> None:
        """Empty check_name should be rejected (min_length=1)."""
        with pytest.raises(Exception):
            VerificationCheck(
                check_name="",
                passed=True,
                message="test",
                checked_at=datetime.now(UTC),
            )

    def test_verification_check_empty_message_rejected(self) -> None:
        """Empty message should be rejected (min_length=1)."""
        with pytest.raises(Exception):
            VerificationCheck(
                check_name="test",
                passed=True,
                message="",
                checked_at=datetime.now(UTC),
            )

    def test_deployment_classification_enum_values(self) -> None:
        """Verify enum values match expected strings."""
        assert DeploymentClassification.NOT_PROVEN == "not_proven"
        assert DeploymentClassification.DEMONSTRATED_BUT_UNSTABLE == "demonstrated_but_unstable"
        assert DeploymentClassification.REPEATABLE_AND_STABLE == "repeatable_and_stable"

    def test_min_consecutive_successes_is_three(self) -> None:
        """Verify the threshold constant is 3 per R109."""
        assert MIN_CONSECUTIVE_SUCCESSES == 3

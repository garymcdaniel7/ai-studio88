"""Unit tests for PerformanceVerificationService.

Tests the performance verification framework including:
- Target definitions (all R76 targets present with correct thresholds)
- Category filtering
- verify_targets_met() comparison logic (pass/fail/skipped/error)
- get_optimization_recommendations() for failed targets
- EXPLAIN ANALYZE query suggestions (R76.6)
- Priority computation based on overshoot

No I/O, no DB — pure unit tests with no external dependencies.

Validates: Requirements R76.1, R76.2, R76.3, R76.4, R76.5, R76.6
"""

from __future__ import annotations

import pytest

from app.services.performance_verification_service import (
    ALL_PERFORMANCE_TARGETS,
    PerformanceCategory,
    PerformanceMeasurement,
    PerformanceTarget,
    PerformanceVerificationService,
    VerificationStatus,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def service() -> PerformanceVerificationService:
    """Create a fresh PerformanceVerificationService instance."""
    return PerformanceVerificationService()


# =============================================================================
# Target Definition Tests
# =============================================================================


@pytest.mark.unit
class TestTargetDefinitions:
    """Tests that all R76 performance targets are correctly defined."""

    def test_all_targets_present(self) -> None:
        """All 14 performance targets should be defined."""
        assert len(ALL_PERFORMANCE_TARGETS) == 14

    def test_all_targets_have_required_fields(self) -> None:
        """Every target must have name, target_ms, category, requirement_id, description."""
        for target in ALL_PERFORMANCE_TARGETS:
            assert target.name, f"Target missing name"
            assert target.target_ms > 0, f"Target {target.name} has invalid target_ms"
            assert isinstance(target.category, PerformanceCategory)
            assert target.requirement_id.startswith("R76.")
            assert target.description

    def test_unique_target_names(self) -> None:
        """All target names must be unique."""
        names = [t.name for t in ALL_PERFORMANCE_TARGETS]
        assert len(names) == len(set(names))

    def test_r76_1_navigation_targets(self) -> None:
        """R76.1: Page navigation (100ms), fresh data (500ms), thumbnails (200ms)."""
        r76_1_targets = [t for t in ALL_PERFORMANCE_TARGETS if t.requirement_id == "R76.1"]
        assert len(r76_1_targets) == 3

        by_name = {t.name: t for t in r76_1_targets}
        assert by_name["page_navigation_cached"].target_ms == 100.0
        assert by_name["fresh_data_load"].target_ms == 500.0
        assert by_name["image_thumbnail_cdn"].target_ms == 200.0

    def test_r76_2_talent_project_targets(self) -> None:
        """R76.2: Talent detail (300ms), talent list (500ms), project detail (500ms)."""
        r76_2_targets = [t for t in ALL_PERFORMANCE_TARGETS if t.requirement_id == "R76.2"]
        assert len(r76_2_targets) == 3

        by_name = {t.name: t for t in r76_2_targets}
        assert by_name["talent_detail_load"].target_ms == 300.0
        assert by_name["talent_list_load"].target_ms == 500.0
        assert by_name["project_detail_load"].target_ms == 500.0

    def test_r76_3_brain_chat_targets(self) -> None:
        """R76.3: First token (2000ms), mode switch (100ms)."""
        r76_3_targets = [t for t in ALL_PERFORMANCE_TARGETS if t.requirement_id == "R76.3"]
        assert len(r76_3_targets) == 2

        by_name = {t.name: t for t in r76_3_targets}
        assert by_name["brain_first_token"].target_ms == 2000.0
        assert by_name["brain_mode_switch"].target_ms == 100.0

    def test_r76_4_generation_targets(self) -> None:
        """R76.4: Job submission (2000ms), status poll (200ms), realtime (1000ms)."""
        r76_4_targets = [t for t in ALL_PERFORMANCE_TARGETS if t.requirement_id == "R76.4"]
        assert len(r76_4_targets) == 3

        by_name = {t.name: t for t in r76_4_targets}
        assert by_name["job_submission"].target_ms == 2000.0
        assert by_name["job_status_poll"].target_ms == 200.0
        assert by_name["realtime_event_delivery"].target_ms == 1000.0

    def test_r76_5_admin_targets(self) -> None:
        """R76.5: Fleet status (1000ms), cost summary (1000ms), capabilities (500ms)."""
        r76_5_targets = [t for t in ALL_PERFORMANCE_TARGETS if t.requirement_id == "R76.5"]
        assert len(r76_5_targets) == 3

        by_name = {t.name: t for t in r76_5_targets}
        assert by_name["fleet_status_load"].target_ms == 1000.0
        assert by_name["cost_summary_load"].target_ms == 1000.0
        assert by_name["capability_registry_load"].target_ms == 500.0


# =============================================================================
# Service Method Tests
# =============================================================================


@pytest.mark.unit
class TestGetTargets:
    """Tests for PerformanceVerificationService.get_targets()."""

    def test_returns_all_targets(self, service: PerformanceVerificationService) -> None:
        """get_targets() should return all defined targets."""
        targets = service.get_targets()
        assert len(targets) == 14
        assert all(isinstance(t, PerformanceTarget) for t in targets)

    def test_returns_copy(self, service: PerformanceVerificationService) -> None:
        """get_targets() should return a new list (not the internal reference)."""
        targets_a = service.get_targets()
        targets_b = service.get_targets()
        assert targets_a is not targets_b

    def test_filter_by_category(self, service: PerformanceVerificationService) -> None:
        """get_targets_by_category() should filter correctly."""
        nav_targets = service.get_targets_by_category(PerformanceCategory.NAVIGATION)
        assert len(nav_targets) == 1
        assert all(t.category == PerformanceCategory.NAVIGATION for t in nav_targets)

        admin_targets = service.get_targets_by_category(PerformanceCategory.ADMIN)
        assert len(admin_targets) == 3
        assert all(t.category == PerformanceCategory.ADMIN for t in admin_targets)


# =============================================================================
# Verification Logic Tests
# =============================================================================


@pytest.mark.unit
class TestVerifyTargetsMet:
    """Tests for PerformanceVerificationService.verify_targets_met()."""

    def test_passing_measurement(self, service: PerformanceVerificationService) -> None:
        """Measurement below target should produce PASSED status."""
        measurements = [
            PerformanceMeasurement(
                target_name="talent_list_load",
                measured_ms=250.0,
                status=VerificationStatus.PASSED,
            ),
        ]
        results = service.verify_targets_met(measurements)
        assert results["talent_list_load"].status == VerificationStatus.PASSED
        assert "PASS" in results["talent_list_load"].detail

    def test_failing_measurement(self, service: PerformanceVerificationService) -> None:
        """Measurement above target should produce FAILED status."""
        measurements = [
            PerformanceMeasurement(
                target_name="talent_list_load",
                measured_ms=750.0,
                status=VerificationStatus.PASSED,  # Pre-verification status
            ),
        ]
        results = service.verify_targets_met(measurements)
        assert results["talent_list_load"].status == VerificationStatus.FAILED
        assert "FAIL" in results["talent_list_load"].detail

    def test_exact_threshold_passes(
        self, service: PerformanceVerificationService
    ) -> None:
        """Measurement exactly at target should PASS (less-than-or-equal)."""
        measurements = [
            PerformanceMeasurement(
                target_name="talent_list_load",
                measured_ms=500.0,
                status=VerificationStatus.PASSED,
            ),
        ]
        results = service.verify_targets_met(measurements)
        assert results["talent_list_load"].status == VerificationStatus.PASSED

    def test_skipped_measurement_preserved(
        self, service: PerformanceVerificationService
    ) -> None:
        """Skipped measurements should retain SKIPPED status."""
        measurements = [
            PerformanceMeasurement(
                target_name="page_navigation_cached",
                measured_ms=None,
                status=VerificationStatus.SKIPPED,
                detail="Not measurable via API",
            ),
        ]
        results = service.verify_targets_met(measurements)
        assert results["page_navigation_cached"].status == VerificationStatus.SKIPPED

    def test_error_measurement_preserved(
        self, service: PerformanceVerificationService
    ) -> None:
        """Error measurements should retain ERROR status."""
        measurements = [
            PerformanceMeasurement(
                target_name="talent_list_load",
                measured_ms=None,
                status=VerificationStatus.ERROR,
                detail="Connection refused",
            ),
        ]
        results = service.verify_targets_met(measurements)
        assert results["talent_list_load"].status == VerificationStatus.ERROR

    def test_unknown_target_returns_error(
        self, service: PerformanceVerificationService
    ) -> None:
        """Unknown target names should produce ERROR status."""
        measurements = [
            PerformanceMeasurement(
                target_name="nonexistent_target",
                measured_ms=100.0,
                status=VerificationStatus.PASSED,
            ),
        ]
        results = service.verify_targets_met(measurements)
        assert results["nonexistent_target"].status == VerificationStatus.ERROR
        assert "Unknown target" in results["nonexistent_target"].detail

    def test_none_measured_ms_skipped(
        self, service: PerformanceVerificationService
    ) -> None:
        """Measurement with None ms but PASSED status should be treated as SKIPPED."""
        measurements = [
            PerformanceMeasurement(
                target_name="talent_list_load",
                measured_ms=None,
                status=VerificationStatus.PASSED,
            ),
        ]
        results = service.verify_targets_met(measurements)
        assert results["talent_list_load"].status == VerificationStatus.SKIPPED

    def test_multiple_measurements(
        self, service: PerformanceVerificationService
    ) -> None:
        """Multiple measurements should all be verified independently."""
        measurements = [
            PerformanceMeasurement(
                target_name="talent_list_load",
                measured_ms=250.0,
                status=VerificationStatus.PASSED,
            ),
            PerformanceMeasurement(
                target_name="job_status_poll",
                measured_ms=350.0,
                status=VerificationStatus.PASSED,
            ),
            PerformanceMeasurement(
                target_name="fleet_status_load",
                measured_ms=None,
                status=VerificationStatus.SKIPPED,
            ),
        ]
        results = service.verify_targets_met(measurements)
        assert results["talent_list_load"].status == VerificationStatus.PASSED
        assert results["job_status_poll"].status == VerificationStatus.FAILED
        assert results["fleet_status_load"].status == VerificationStatus.SKIPPED


# =============================================================================
# Optimization Recommendations Tests
# =============================================================================


@pytest.mark.unit
class TestOptimizationRecommendations:
    """Tests for get_optimization_recommendations() (R76.6)."""

    def test_no_recommendations_when_all_pass(
        self, service: PerformanceVerificationService
    ) -> None:
        """Passing measurements should produce no recommendations."""
        measurements = [
            PerformanceMeasurement(
                target_name="talent_list_load",
                measured_ms=200.0,
                status=VerificationStatus.PASSED,
            ),
        ]
        recs = service.get_optimization_recommendations(measurements)
        assert len(recs) == 0

    def test_recommendations_for_failed_target(
        self, service: PerformanceVerificationService
    ) -> None:
        """Failed measurement should produce a recommendation."""
        measurements = [
            PerformanceMeasurement(
                target_name="talent_list_load",
                measured_ms=800.0,
                status=VerificationStatus.FAILED,
            ),
        ]
        recs = service.get_optimization_recommendations(measurements)
        assert len(recs) == 1
        assert recs[0].target_name == "talent_list_load"
        assert recs[0].category == PerformanceCategory.DATA_LOADING

    def test_explain_analyze_query_present_for_db_targets(
        self, service: PerformanceVerificationService
    ) -> None:
        """DB-related targets should include EXPLAIN ANALYZE query (R76.6)."""
        measurements = [
            PerformanceMeasurement(
                target_name="talent_list_load",
                measured_ms=800.0,
                status=VerificationStatus.FAILED,
            ),
        ]
        recs = service.get_optimization_recommendations(measurements)
        assert recs[0].explain_analyze_query is not None
        assert "EXPLAIN ANALYZE" in recs[0].explain_analyze_query

    def test_no_explain_query_for_client_side_targets(
        self, service: PerformanceVerificationService
    ) -> None:
        """Client-side targets should not have EXPLAIN ANALYZE queries."""
        measurements = [
            PerformanceMeasurement(
                target_name="brain_first_token",
                measured_ms=3500.0,
                status=VerificationStatus.FAILED,
            ),
        ]
        recs = service.get_optimization_recommendations(measurements)
        assert len(recs) == 1
        assert recs[0].explain_analyze_query is None

    def test_priority_high_for_large_overshoot(
        self, service: PerformanceVerificationService
    ) -> None:
        """Target exceeded by >5x should be HIGH priority."""
        measurements = [
            PerformanceMeasurement(
                target_name="job_status_poll",
                measured_ms=1500.0,  # 7.5x over 200ms target
                status=VerificationStatus.FAILED,
            ),
        ]
        recs = service.get_optimization_recommendations(measurements)
        assert recs[0].priority == "HIGH"

    def test_priority_medium_for_moderate_overshoot(
        self, service: PerformanceVerificationService
    ) -> None:
        """Target exceeded by 2-5x should be MEDIUM priority."""
        measurements = [
            PerformanceMeasurement(
                target_name="talent_list_load",
                measured_ms=1200.0,  # 2.4x over 500ms target
                status=VerificationStatus.FAILED,
            ),
        ]
        recs = service.get_optimization_recommendations(measurements)
        assert recs[0].priority == "MEDIUM"

    def test_priority_low_for_slight_overshoot(
        self, service: PerformanceVerificationService
    ) -> None:
        """Target exceeded by <2x should be LOW priority."""
        measurements = [
            PerformanceMeasurement(
                target_name="talent_list_load",
                measured_ms=600.0,  # 1.2x over 500ms target
                status=VerificationStatus.FAILED,
            ),
        ]
        recs = service.get_optimization_recommendations(measurements)
        assert recs[0].priority == "LOW"

    def test_skipped_measurements_produce_no_recommendations(
        self, service: PerformanceVerificationService
    ) -> None:
        """Skipped/error measurements should not generate recommendations."""
        measurements = [
            PerformanceMeasurement(
                target_name="talent_list_load",
                measured_ms=None,
                status=VerificationStatus.SKIPPED,
            ),
            PerformanceMeasurement(
                target_name="job_status_poll",
                measured_ms=None,
                status=VerificationStatus.ERROR,
            ),
        ]
        recs = service.get_optimization_recommendations(measurements)
        assert len(recs) == 0

    def test_multiple_failed_targets_get_individual_recommendations(
        self, service: PerformanceVerificationService
    ) -> None:
        """Each failed target should get its own recommendation."""
        measurements = [
            PerformanceMeasurement(
                target_name="talent_list_load",
                measured_ms=800.0,
                status=VerificationStatus.FAILED,
            ),
            PerformanceMeasurement(
                target_name="cost_summary_load",
                measured_ms=2000.0,
                status=VerificationStatus.FAILED,
            ),
        ]
        recs = service.get_optimization_recommendations(measurements)
        assert len(recs) == 2
        target_names = {r.target_name for r in recs}
        assert "talent_list_load" in target_names
        assert "cost_summary_load" in target_names


# =============================================================================
# Async Performance Check Tests (Framework Mode)
# =============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
class TestRunApiPerformanceCheck:
    """Tests for run_api_performance_check() in framework mode."""

    async def test_no_client_returns_all_skipped(
        self, service: PerformanceVerificationService
    ) -> None:
        """Without a client, all measurements should be SKIPPED."""
        measurements = await service.run_api_performance_check(client=None)
        assert len(measurements) == 14
        assert all(m.status == VerificationStatus.SKIPPED for m in measurements)

    async def test_non_api_targets_always_skipped(
        self, service: PerformanceVerificationService
    ) -> None:
        """Targets without endpoints should always be SKIPPED regardless of client."""
        # Even with None client, verify the reason differs
        measurements = await service.run_api_performance_check(client=None)
        non_api = [m for m in measurements if "not measurable via API" in m.detail]
        # page_navigation_cached, image_thumbnail_cdn, brain_mode_switch, realtime_event_delivery
        assert len(non_api) == 4

    async def test_subset_targets(
        self, service: PerformanceVerificationService
    ) -> None:
        """Passing a subset of targets should only measure those targets."""
        subset = [
            t
            for t in ALL_PERFORMANCE_TARGETS
            if t.category == PerformanceCategory.ADMIN
        ]
        measurements = await service.run_api_performance_check(
            client=None, targets=subset
        )
        assert len(measurements) == 3
        target_names = {m.target_name for m in measurements}
        assert "fleet_status_load" in target_names
        assert "cost_summary_load" in target_names
        assert "capability_registry_load" in target_names

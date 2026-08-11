"""Unit tests for Capacity Telemetry and Graceful Degradation.

Tests the CapacityTelemetryService covering:
- Request rate tracking (sliding window)
- Active user tracking with TTL
- Brain stream management
- Queue management (enqueue, dequeue, position, cancellation)
- Queue position and wait time estimation
- Admission control (accept, queue, reject_budget)
- Degradation level assessment
- Capacity snapshot generation
- Tenant-scoped queue status

Validates: Requirements R90.1, R90.2, R90.3, R90.4
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from backend.infrastructure.capacity_telemetry import (
    ACTIVE_USER_TTL_SECONDS,
    REQUEST_RATE_WINDOW_SECONDS,
    CapacitySnapshot,
    CapacityTelemetryService,
    DegradationLevel,
    QueueDecision,
    QueueEntry,
    QueuePositionInfo,
    WorkloadClass,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def service() -> CapacityTelemetryService:
    """Create a fresh CapacityTelemetryService for each test."""
    return CapacityTelemetryService(
        max_queue_depth=10,
        workload_concurrency_limits={
            "image_generation": 3,
            "video_generation": 2,
            "interactive_language": 5,
        },
    )


@pytest.fixture
def populated_service(service: CapacityTelemetryService) -> CapacityTelemetryService:
    """Service with some active state for degradation tests."""
    # Register some active users
    service.register_active_user("user-1")
    service.register_active_user("user-2")
    # Register some active jobs
    service.register_active_job("runpod")
    service.register_active_job("vast")
    service.register_active_job("vast")
    # Set GPU utilization
    service.update_gpu_utilization(0.5)
    # Set compute liability
    service.update_compute_liability(15.50)
    return service


# =============================================================================
# Request Rate Tracking
# =============================================================================


@pytest.mark.unit
class TestRequestRateTracking:
    """Tests for API request rate calculation with sliding window."""

    def test_initial_rate_is_zero(self, service: CapacityTelemetryService) -> None:
        """No requests recorded means zero rate."""
        assert service.get_request_rate() == 0.0

    def test_single_request_gives_rate(self, service: CapacityTelemetryService) -> None:
        """One request in a 60-second window gives 1.0 rpm."""
        service.record_request()
        rate = service.get_request_rate()
        assert rate == 1.0

    def test_multiple_requests_accumulate(self, service: CapacityTelemetryService) -> None:
        """Multiple requests in window accumulate correctly."""
        for _ in range(10):
            service.record_request()
        rate = service.get_request_rate()
        assert rate == 10.0

    def test_old_requests_pruned(self, service: CapacityTelemetryService) -> None:
        """Requests outside the window are pruned from rate calculation."""
        # Manually inject old timestamps
        old_time = time.time() - REQUEST_RATE_WINDOW_SECONDS - 10
        service._request_timestamps.append(old_time)
        service._request_timestamps.append(old_time - 5)

        # Record one fresh request
        service.record_request()

        # Only the fresh one should count
        rate = service.get_request_rate()
        assert rate == 1.0


# =============================================================================
# Active Users
# =============================================================================


@pytest.mark.unit
class TestActiveUsers:
    """Tests for active user tracking with TTL-based expiration."""

    def test_initial_count_is_zero(self, service: CapacityTelemetryService) -> None:
        assert service.get_active_user_count() == 0

    def test_register_user_increments_count(self, service: CapacityTelemetryService) -> None:
        service.register_active_user("user-1")
        assert service.get_active_user_count() == 1

    def test_duplicate_user_not_double_counted(
        self, service: CapacityTelemetryService
    ) -> None:
        service.register_active_user("user-1")
        service.register_active_user("user-1")
        assert service.get_active_user_count() == 1

    def test_multiple_users_counted(self, service: CapacityTelemetryService) -> None:
        service.register_active_user("user-1")
        service.register_active_user("user-2")
        service.register_active_user("user-3")
        assert service.get_active_user_count() == 3

    def test_expired_users_pruned(self, service: CapacityTelemetryService) -> None:
        """Users with activity older than TTL are pruned."""
        # Inject an expired user
        expired_time = time.time() - ACTIVE_USER_TTL_SECONDS - 10
        service._active_users["old-user"] = expired_time

        # Add a current user
        service.register_active_user("current-user")

        # Only current user should count
        assert service.get_active_user_count() == 1


# =============================================================================
# Brain Streams
# =============================================================================


@pytest.mark.unit
class TestBrainStreams:
    """Tests for Brain/LLM streaming connection tracking."""

    def test_initial_count_is_zero(self, service: CapacityTelemetryService) -> None:
        assert service.get_brain_stream_count() == 0

    def test_register_stream(self, service: CapacityTelemetryService) -> None:
        service.register_brain_stream("stream-1")
        assert service.get_brain_stream_count() == 1

    def test_unregister_stream(self, service: CapacityTelemetryService) -> None:
        service.register_brain_stream("stream-1")
        service.unregister_brain_stream("stream-1")
        assert service.get_brain_stream_count() == 0

    def test_unregister_nonexistent_stream_is_safe(
        self, service: CapacityTelemetryService
    ) -> None:
        """Unregistering a stream that doesn't exist should not raise."""
        service.unregister_brain_stream("nonexistent")
        assert service.get_brain_stream_count() == 0


# =============================================================================
# Realtime Connections
# =============================================================================


@pytest.mark.unit
class TestRealtimeConnections:
    """Tests for realtime connection count management."""

    def test_initial_count_is_zero(self, service: CapacityTelemetryService) -> None:
        assert service.get_realtime_connections() == 0

    def test_update_count(self, service: CapacityTelemetryService) -> None:
        service.update_realtime_connections(42)
        assert service.get_realtime_connections() == 42

    def test_negative_count_clamped_to_zero(
        self, service: CapacityTelemetryService
    ) -> None:
        service.update_realtime_connections(-5)
        assert service.get_realtime_connections() == 0


# =============================================================================
# Queue Management
# =============================================================================


@pytest.mark.unit
class TestQueueManagement:
    """Tests for workload queue operations."""

    def test_initial_queue_depth_all_zero(self, service: CapacityTelemetryService) -> None:
        depths = service.get_queue_depth()
        for depth in depths.values():
            assert depth == 0

    def test_enqueue_job_returns_position(self, service: CapacityTelemetryService) -> None:
        entry = QueueEntry(
            job_id="job-1",
            org_id="org-1",
            workload_class=WorkloadClass.IMAGE_GENERATION,
        )
        position_info = service.enqueue_job(entry)
        assert position_info.position == 1

    def test_multiple_enqueues_increment_position(
        self, service: CapacityTelemetryService
    ) -> None:
        for i in range(3):
            entry = QueueEntry(
                job_id=f"job-{i}",
                org_id="org-1",
                workload_class=WorkloadClass.IMAGE_GENERATION,
            )
            info = service.enqueue_job(entry)
            assert info.position == i + 1

    def test_dequeue_returns_fifo(self, service: CapacityTelemetryService) -> None:
        """Dequeue returns jobs in FIFO order."""
        for i in range(3):
            entry = QueueEntry(
                job_id=f"job-{i}",
                org_id="org-1",
                workload_class=WorkloadClass.IMAGE_GENERATION,
            )
            service.enqueue_job(entry)

        first = service.dequeue_job(WorkloadClass.IMAGE_GENERATION)
        assert first is not None
        assert first.job_id == "job-0"

    def test_dequeue_empty_queue_returns_none(
        self, service: CapacityTelemetryService
    ) -> None:
        result = service.dequeue_job(WorkloadClass.IMAGE_GENERATION)
        assert result is None

    def test_remove_job_from_queue(self, service: CapacityTelemetryService) -> None:
        entry = QueueEntry(
            job_id="job-cancel",
            org_id="org-1",
            workload_class=WorkloadClass.IMAGE_GENERATION,
        )
        service.enqueue_job(entry)
        assert service.remove_job_from_queue("job-cancel") is True
        assert service.get_total_queue_depth() == 0

    def test_remove_nonexistent_job_returns_false(
        self, service: CapacityTelemetryService
    ) -> None:
        assert service.remove_job_from_queue("nonexistent") is False

    def test_get_queue_position_for_queued_job(
        self, service: CapacityTelemetryService
    ) -> None:
        for i in range(3):
            entry = QueueEntry(
                job_id=f"job-{i}",
                org_id="org-1",
                workload_class=WorkloadClass.IMAGE_GENERATION,
            )
            service.enqueue_job(entry)

        pos = service.get_queue_position("job-1")
        assert pos is not None
        assert pos.position == 2

    def test_get_queue_position_not_found(
        self, service: CapacityTelemetryService
    ) -> None:
        assert service.get_queue_position("nonexistent") is None

    def test_queue_depth_per_workload_class(
        self, service: CapacityTelemetryService
    ) -> None:
        """Queue depth is tracked independently per workload class."""
        service.enqueue_job(
            QueueEntry(
                job_id="img-1",
                org_id="org-1",
                workload_class=WorkloadClass.IMAGE_GENERATION,
            )
        )
        service.enqueue_job(
            QueueEntry(
                job_id="vid-1",
                org_id="org-1",
                workload_class=WorkloadClass.VIDEO_GENERATION,
            )
        )

        depths = service.get_queue_depth()
        assert depths["image_generation"] == 1
        assert depths["video_generation"] == 1
        assert depths["training"] == 0


# =============================================================================
# Queue Position and Wait Time Estimation
# =============================================================================


@pytest.mark.unit
class TestWaitTimeEstimation:
    """Tests for queue position and wait time estimation (R90.1)."""

    def test_wait_estimate_provided_for_reliable_classes(
        self, service: CapacityTelemetryService
    ) -> None:
        """Image generation has reliable estimates when active jobs exist."""
        service.register_active_job(WorkloadClass.IMAGE_GENERATION.value)
        entry = QueueEntry(
            job_id="job-1",
            org_id="org-1",
            workload_class=WorkloadClass.IMAGE_GENERATION,
        )
        info = service.enqueue_job(entry)
        # Should have a reliable estimate since we have active jobs
        assert info.reliable is True
        assert info.estimated_wait_seconds is not None

    def test_wait_estimate_unreliable_for_training(
        self, service: CapacityTelemetryService
    ) -> None:
        """Training workloads have unreliable estimates (high variance)."""
        entry = QueueEntry(
            job_id="job-1",
            org_id="org-1",
            workload_class=WorkloadClass.TRAINING,
        )
        info = service.enqueue_job(entry)
        # Training is always unreliable due to high variance
        assert info.reliable is False

    def test_wait_estimate_unreliable_for_video(
        self, service: CapacityTelemetryService
    ) -> None:
        """Video generation has unreliable estimates (high variance)."""
        entry = QueueEntry(
            job_id="job-1",
            org_id="org-1",
            workload_class=WorkloadClass.VIDEO_GENERATION,
        )
        info = service.enqueue_job(entry)
        assert info.reliable is False


# =============================================================================
# Active Jobs
# =============================================================================


@pytest.mark.unit
class TestActiveJobs:
    """Tests for active job counting per provider."""

    def test_initial_active_jobs_empty(self, service: CapacityTelemetryService) -> None:
        assert service.get_active_jobs() == {}
        assert service.get_total_active_jobs() == 0

    def test_register_active_job(self, service: CapacityTelemetryService) -> None:
        service.register_active_job("runpod")
        assert service.get_active_jobs()["runpod"] == 1

    def test_unregister_active_job(self, service: CapacityTelemetryService) -> None:
        service.register_active_job("runpod")
        service.unregister_active_job("runpod")
        assert service.get_active_jobs()["runpod"] == 0

    def test_unregister_below_zero_clamped(
        self, service: CapacityTelemetryService
    ) -> None:
        service.unregister_active_job("runpod")
        assert service.get_active_jobs().get("runpod", 0) == 0

    def test_total_active_across_providers(
        self, service: CapacityTelemetryService
    ) -> None:
        service.register_active_job("runpod")
        service.register_active_job("runpod")
        service.register_active_job("vast")
        assert service.get_total_active_jobs() == 3


# =============================================================================
# GPU Utilization
# =============================================================================


@pytest.mark.unit
class TestGPUUtilization:
    """Tests for GPU utilization tracking."""

    def test_initial_utilization_zero(self, service: CapacityTelemetryService) -> None:
        assert service.get_gpu_utilization() == 0.0

    def test_update_utilization(self, service: CapacityTelemetryService) -> None:
        service.update_gpu_utilization(0.75)
        assert service.get_gpu_utilization() == 0.75

    def test_utilization_clamped_to_range(
        self, service: CapacityTelemetryService
    ) -> None:
        service.update_gpu_utilization(1.5)
        assert service.get_gpu_utilization() == 1.0

        service.update_gpu_utilization(-0.5)
        assert service.get_gpu_utilization() == 0.0


# =============================================================================
# Compute Liability
# =============================================================================


@pytest.mark.unit
class TestComputeLiability:
    """Tests for platform compute liability tracking."""

    def test_initial_liability_zero(self, service: CapacityTelemetryService) -> None:
        assert service.get_compute_liability() == 0.0

    def test_update_liability(self, service: CapacityTelemetryService) -> None:
        service.update_compute_liability(25.50)
        assert service.get_compute_liability() == 25.50

    def test_negative_liability_clamped(
        self, service: CapacityTelemetryService
    ) -> None:
        service.update_compute_liability(-10.0)
        assert service.get_compute_liability() == 0.0


# =============================================================================
# Degradation Level Assessment
# =============================================================================


@pytest.mark.unit
class TestDegradationAssessment:
    """Tests for system degradation level assessment (R90.2)."""

    def test_normal_when_idle(self, service: CapacityTelemetryService) -> None:
        """Empty system reports NORMAL degradation."""
        assert service.assess_degradation_level() == DegradationLevel.NORMAL

    @patch(
        "backend.infrastructure.capacity_telemetry.CapacityTelemetryService._check_budget_exceeded"
    )
    def test_critical_when_budget_exceeded(
        self, mock_budget: object, service: CapacityTelemetryService
    ) -> None:
        """Budget exceeded triggers CRITICAL degradation."""
        mock_budget.return_value = True  # type: ignore[attr-defined]
        assert service.assess_degradation_level() == DegradationLevel.CRITICAL

    def test_elevated_when_high_gpu_utilization(
        self, service: CapacityTelemetryService
    ) -> None:
        """High GPU utilization triggers ELEVATED degradation."""
        service.update_gpu_utilization(0.85)
        assert service.assess_degradation_level() == DegradationLevel.ELEVATED

    def test_elevated_when_queues_building(
        self, service: CapacityTelemetryService
    ) -> None:
        """Significant queue depth triggers ELEVATED."""
        for i in range(6):
            service.enqueue_job(
                QueueEntry(
                    job_id=f"job-{i}",
                    org_id="org-1",
                    workload_class=WorkloadClass.BATCH,
                )
            )
        assert service.assess_degradation_level() == DegradationLevel.ELEVATED

    def test_degraded_when_generation_capacity_exhausted(
        self, service: CapacityTelemetryService
    ) -> None:
        """Generation at limit with queue → DEGRADED (read-only nav stays usable)."""
        # Fill up image generation active jobs to the limit (3)
        for _ in range(3):
            service.register_active_job(WorkloadClass.IMAGE_GENERATION.value)

        # Add a queued image job
        service.enqueue_job(
            QueueEntry(
                job_id="waiting-job",
                org_id="org-1",
                workload_class=WorkloadClass.IMAGE_GENERATION,
            )
        )

        assert service.assess_degradation_level() == DegradationLevel.DEGRADED


# =============================================================================
# Admission Control
# =============================================================================


@pytest.mark.unit
class TestAdmissionControl:
    """Tests for job admission control (R90.1: queue not reject)."""

    @patch(
        "backend.infrastructure.capacity_telemetry.CapacityTelemetryService._check_budget_exceeded"
    )
    def test_reject_budget_when_exceeded(
        self, mock_budget: object, service: CapacityTelemetryService
    ) -> None:
        """Budget exceeded returns REJECT_BUDGET (402 in router)."""
        mock_budget.return_value = True  # type: ignore[attr-defined]
        decision = service.evaluate_admission("image_generation", "org-1")
        assert decision == QueueDecision.REJECT_BUDGET

    def test_accept_when_capacity_available(
        self, service: CapacityTelemetryService
    ) -> None:
        """Under concurrency limit returns ACCEPT."""
        decision = service.evaluate_admission("image_generation", "org-1")
        assert decision == QueueDecision.ACCEPT

    def test_queue_when_at_capacity(self, service: CapacityTelemetryService) -> None:
        """At concurrency limit returns QUEUE (not reject per R90.1)."""
        # Fill to image_generation limit (3)
        for _ in range(3):
            service.register_active_job("image_generation")

        decision = service.evaluate_admission("image_generation", "org-1")
        assert decision == QueueDecision.QUEUE

    def test_accept_unknown_workload_class(
        self, service: CapacityTelemetryService
    ) -> None:
        """Unknown workload class is accepted (don't block on classification)."""
        decision = service.evaluate_admission("unknown_class", "org-1")
        assert decision == QueueDecision.ACCEPT

    def test_queue_even_at_max_depth(self, service: CapacityTelemetryService) -> None:
        """Even at max queue depth, queue rather than reject per R90.1."""
        # Fill active to limit
        for _ in range(3):
            service.register_active_job("image_generation")

        # Fill queue to max depth
        for i in range(10):
            service.enqueue_job(
                QueueEntry(
                    job_id=f"job-{i}",
                    org_id="org-1",
                    workload_class=WorkloadClass.IMAGE_GENERATION,
                )
            )

        # Should still queue (not reject)
        decision = service.evaluate_admission("image_generation", "org-1")
        assert decision == QueueDecision.QUEUE


# =============================================================================
# Capacity Snapshot
# =============================================================================


@pytest.mark.unit
class TestCapacitySnapshot:
    """Tests for the capacity snapshot aggregation."""

    def test_snapshot_returns_all_metrics(
        self, populated_service: CapacityTelemetryService
    ) -> None:
        """Snapshot includes all required telemetry metrics."""
        snapshot = populated_service.get_capacity_snapshot()

        assert isinstance(snapshot, CapacitySnapshot)
        assert snapshot.active_users == 2
        assert snapshot.gpu_utilization == 0.5
        assert snapshot.platform_compute_liability == 15.50
        assert snapshot.active_jobs["runpod"] == 1
        assert snapshot.active_jobs["vast"] == 2
        assert snapshot.degradation_level == DegradationLevel.NORMAL
        assert snapshot.timestamp is not None

    def test_snapshot_serialization(
        self, populated_service: CapacityTelemetryService
    ) -> None:
        """Snapshot.to_dict() produces a JSON-serializable dict."""
        snapshot = populated_service.get_capacity_snapshot()
        data = snapshot.to_dict()

        assert "active_users" in data
        assert "api_request_rate" in data
        assert "brain_streams" in data
        assert "realtime_connections" in data
        assert "queue_depth" in data
        assert "active_jobs" in data
        assert "gpu_utilization" in data
        assert "platform_compute_liability" in data
        assert "degradation_level" in data
        assert "timestamp" in data
        # degradation_level should be the string value, not the enum
        assert data["degradation_level"] == "normal"


# =============================================================================
# Tenant-Scoped Queue Status
# =============================================================================


@pytest.mark.unit
class TestTenantScopedQueueStatus:
    """Tests for org-specific queue status (tenant scoping)."""

    def test_org_queue_empty(self, service: CapacityTelemetryService) -> None:
        """Empty org queue returns zero items."""
        status = service.get_org_queue_status("org-1")
        assert status["total_queued"] == 0
        assert status["queued_jobs"] == []

    def test_org_queue_shows_only_own_jobs(
        self, service: CapacityTelemetryService
    ) -> None:
        """Org queue status only shows jobs belonging to that org."""
        service.enqueue_job(
            QueueEntry(
                job_id="job-org1",
                org_id="org-1",
                workload_class=WorkloadClass.IMAGE_GENERATION,
            )
        )
        service.enqueue_job(
            QueueEntry(
                job_id="job-org2",
                org_id="org-2",
                workload_class=WorkloadClass.IMAGE_GENERATION,
            )
        )

        status_org1 = service.get_org_queue_status("org-1")
        assert status_org1["total_queued"] == 1
        assert status_org1["queued_jobs"][0]["job_id"] == "job-org1"

        status_org2 = service.get_org_queue_status("org-2")
        assert status_org2["total_queued"] == 1
        assert status_org2["queued_jobs"][0]["job_id"] == "job-org2"


# =============================================================================
# Singleton
# =============================================================================


@pytest.mark.unit
class TestSingleton:
    """Tests for the module-level singleton pattern."""

    def test_get_capacity_service_returns_same_instance(self) -> None:
        """get_capacity_service() returns the same singleton."""
        from backend.infrastructure.capacity_telemetry import get_capacity_service

        # Reset singleton for test isolation
        import backend.infrastructure.capacity_telemetry as module

        module._service = None

        svc1 = get_capacity_service()
        svc2 = get_capacity_service()
        assert svc1 is svc2

        # Clean up
        module._service = None

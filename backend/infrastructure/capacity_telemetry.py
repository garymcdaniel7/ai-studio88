"""Capacity Telemetry and Graceful Degradation — System load monitoring and overload handling.

Tracks platform capacity metrics and provides graceful degradation when
generation resources are exhausted. Queues work on overload rather than
rejecting (unless budget exceeded).

Validates: Requirements R90.1, R90.2, R90.3, R90.4

Metrics tracked:
    - active_users: Currently authenticated users with recent activity
    - api_request_rate: Requests per minute across API gateway
    - brain_streams: Active Brain/LLM streaming connections
    - realtime_connections: Active Supabase Realtime subscriptions
    - queue_depth: Jobs waiting per workload class
    - active_jobs: Running jobs per provider
    - gpu_utilization: Aggregate GPU usage percentage
    - platform_compute_liability: Total committed cost for in-flight jobs

Graceful degradation:
    - When generation capacity exhausted: read-only navigation remains usable
    - New generation requests are QUEUED (not rejected with 503)
    - Budget-exceeded requests get 402 Payment Required
    - Queue position + estimated wait time provided where reliable
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

REQUEST_RATE_WINDOW_SECONDS = 60
"""Time window for API request rate calculation."""

ACTIVE_USER_TTL_SECONDS = 300
"""Users with activity within this window count as active."""

DEFAULT_MAX_QUEUE_DEPTH = 100
"""Maximum queue depth before new submissions are rejected."""

DEFAULT_WORKLOAD_CONCURRENCY_LIMIT = 10
"""Default concurrent job limit per workload class."""


# =============================================================================
# Enums
# =============================================================================


class WorkloadClass(str, Enum):
    """Independently schedulable capacity categories."""

    INTERACTIVE_LANGUAGE = "interactive_language"
    IMAGE_GENERATION = "image_generation"
    VIDEO_GENERATION = "video_generation"
    TRAINING = "training"
    VOICE_AUDIO = "voice_audio"
    BATCH = "batch"
    PRODUCTION_STAGES = "production_stages"
    PUBLISHING = "publishing"


class DegradationLevel(str, Enum):
    """System degradation levels — drives UI behavior.

    NORMAL: All systems operational.
    ELEVATED: Some workload queues are building, minor delays expected.
    DEGRADED: Generation capacity exhausted; read-only navigation operational.
    CRITICAL: Budget exceeded or system failure; new compute requests rejected.
    """

    NORMAL = "normal"
    ELEVATED = "elevated"
    DEGRADED = "degraded"
    CRITICAL = "critical"


class QueueDecision(str, Enum):
    """Decision for incoming work requests."""

    ACCEPT = "accept"
    QUEUE = "queue"
    REJECT_BUDGET = "reject_budget"


# =============================================================================
# Data Models
# =============================================================================


@dataclass
class QueueEntry:
    """A queued work item waiting for capacity."""

    job_id: str
    org_id: str
    workload_class: WorkloadClass
    queued_at: float = field(default_factory=time.time)
    priority: int = 5
    estimated_duration_seconds: float = 60.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize for API response."""
        return {
            "job_id": self.job_id,
            "org_id": self.org_id,
            "workload_class": self.workload_class.value,
            "queued_at": datetime.fromtimestamp(self.queued_at, tz=UTC).isoformat(),
            "priority": self.priority,
            "estimated_duration_seconds": self.estimated_duration_seconds,
        }


@dataclass
class QueuePositionInfo:
    """Position and wait time estimate for a queued job."""

    position: int
    estimated_wait_seconds: float | None
    reliable: bool

    def to_dict(self) -> dict[str, Any]:
        """Serialize for API response."""
        return {
            "position": self.position,
            "estimated_wait_seconds": self.estimated_wait_seconds,
            "reliable": self.reliable,
        }


@dataclass
class CapacitySnapshot:
    """Point-in-time capture of all capacity metrics."""

    active_users: int
    api_request_rate: float
    brain_streams: int
    realtime_connections: int
    queue_depth: dict[str, int]
    active_jobs: dict[str, int]
    gpu_utilization: float
    platform_compute_liability: float
    degradation_level: DegradationLevel
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize for API response."""
        return {
            "active_users": self.active_users,
            "api_request_rate": self.api_request_rate,
            "brain_streams": self.brain_streams,
            "realtime_connections": self.realtime_connections,
            "queue_depth": self.queue_depth,
            "active_jobs": self.active_jobs,
            "gpu_utilization": self.gpu_utilization,
            "platform_compute_liability": self.platform_compute_liability,
            "degradation_level": self.degradation_level.value,
            "timestamp": self.timestamp,
        }


# =============================================================================
# Capacity Telemetry Service
# =============================================================================


class CapacityTelemetryService:
    """Collects system metrics and manages graceful degradation.

    Central service for capacity management. Tracks load across the platform,
    determines degradation level, and provides queue-or-reject decisions for
    incoming work.

    Usage:
        service = CapacityTelemetryService()
        service.record_request()
        service.register_active_user("user-id-123")
        snapshot = service.get_capacity_snapshot()
        decision = service.evaluate_admission("image_generation", "org-id")
    """

    def __init__(
        self,
        max_queue_depth: int = DEFAULT_MAX_QUEUE_DEPTH,
        workload_concurrency_limits: dict[str, int] | None = None,
    ) -> None:
        # Request rate tracking (sliding window)
        self._request_timestamps: deque[float] = deque()

        # Active users (user_id → last_activity_timestamp)
        self._active_users: dict[str, float] = {}

        # Brain streams (stream_id → start_time)
        self._brain_streams: dict[str, float] = {}

        # Realtime connections count (updated externally)
        self._realtime_connections: int = 0

        # Queue per workload class
        self._queues: dict[WorkloadClass, deque[QueueEntry]] = {
            wc: deque() for wc in WorkloadClass
        }

        # Active jobs per provider
        self._active_jobs: dict[str, int] = {}

        # GPU utilization (0.0 - 1.0, updated by worker health reports)
        self._gpu_utilization: float = 0.0

        # Platform compute liability (USD committed to in-flight jobs)
        self._platform_compute_liability: float = 0.0

        # Configuration
        self._max_queue_depth = max_queue_depth
        self._workload_concurrency_limits: dict[str, int] = (
            workload_concurrency_limits or {}
        )

    # ─── Request Rate Tracking ────────────────────────────────────────────

    def record_request(self) -> None:
        """Record an API request for rate calculation."""
        now = time.time()
        self._request_timestamps.append(now)
        self._prune_old_requests(now)

    def get_request_rate(self) -> float:
        """Get current requests per minute within the sliding window."""
        now = time.time()
        self._prune_old_requests(now)
        count = len(self._request_timestamps)
        return round(count * (60.0 / REQUEST_RATE_WINDOW_SECONDS), 1)

    def _prune_old_requests(self, now: float) -> None:
        """Remove request timestamps outside the rate window."""
        cutoff = now - REQUEST_RATE_WINDOW_SECONDS
        while self._request_timestamps and self._request_timestamps[0] < cutoff:
            self._request_timestamps.popleft()

    # ─── Active Users ─────────────────────────────────────────────────────

    def register_active_user(self, user_id: str) -> None:
        """Mark a user as active (call on each authenticated request)."""
        self._active_users[user_id] = time.time()

    def get_active_user_count(self) -> int:
        """Count users with activity within the TTL window."""
        now = time.time()
        cutoff = now - ACTIVE_USER_TTL_SECONDS
        # Prune expired users
        expired = [uid for uid, ts in self._active_users.items() if ts < cutoff]
        for uid in expired:
            del self._active_users[uid]
        return len(self._active_users)

    # ─── Brain Streams ────────────────────────────────────────────────────

    def register_brain_stream(self, stream_id: str) -> None:
        """Register a new Brain/LLM streaming connection."""
        self._brain_streams[stream_id] = time.time()

    def unregister_brain_stream(self, stream_id: str) -> None:
        """Unregister a Brain stream on completion or disconnect."""
        self._brain_streams.pop(stream_id, None)

    def get_brain_stream_count(self) -> int:
        """Get count of active Brain streams."""
        return len(self._brain_streams)

    # ─── Realtime Connections ─────────────────────────────────────────────

    def update_realtime_connections(self, count: int) -> None:
        """Update the current realtime connection count (set by external probe)."""
        self._realtime_connections = max(0, count)

    def get_realtime_connections(self) -> int:
        """Get current realtime connection count."""
        return self._realtime_connections

    # ─── Queue Management ─────────────────────────────────────────────────

    def enqueue_job(self, entry: QueueEntry) -> QueuePositionInfo:
        """Add a job to the appropriate workload queue.

        Returns:
            Queue position information with estimated wait time.
        """
        queue = self._queues[entry.workload_class]
        queue.append(entry)
        position = len(queue)
        wait_estimate = self._estimate_wait_time(entry.workload_class, position)
        reliable = self._is_wait_estimate_reliable(entry.workload_class)

        logger.info(
            "job_queued",
            extra={
                "job_id": entry.job_id,
                "org_id": entry.org_id,
                "workload_class": entry.workload_class.value,
                "position": position,
                "estimated_wait_seconds": wait_estimate,
            },
        )

        return QueuePositionInfo(
            position=position,
            estimated_wait_seconds=wait_estimate if reliable else None,
            reliable=reliable,
        )

    def dequeue_job(self, workload_class: WorkloadClass) -> QueueEntry | None:
        """Remove and return the next job from a workload queue.

        Returns:
            The next QueueEntry or None if queue is empty.
        """
        queue = self._queues[workload_class]
        if queue:
            return queue.popleft()
        return None

    def remove_job_from_queue(self, job_id: str) -> bool:
        """Remove a specific job from its queue (e.g., on cancellation).

        Returns:
            True if found and removed, False otherwise.
        """
        for queue in self._queues.values():
            for i, entry in enumerate(queue):
                if entry.job_id == job_id:
                    del queue[i]
                    return True
        return False

    def get_queue_depth(self, workload_class: WorkloadClass | None = None) -> dict[str, int]:
        """Get queue depth per workload class, or for a specific class.

        Returns:
            Dict mapping workload class name → queue depth.
        """
        if workload_class:
            return {workload_class.value: len(self._queues[workload_class])}
        return {wc.value: len(q) for wc, q in self._queues.items()}

    def get_total_queue_depth(self) -> int:
        """Get total jobs queued across all workload classes."""
        return sum(len(q) for q in self._queues.values())

    def get_queue_position(self, job_id: str) -> QueuePositionInfo | None:
        """Get queue position and wait estimate for a specific job.

        Returns:
            QueuePositionInfo if found, None if not in any queue.
        """
        for wc, queue in self._queues.items():
            for i, entry in enumerate(queue):
                if entry.job_id == job_id:
                    position = i + 1
                    reliable = self._is_wait_estimate_reliable(wc)
                    wait = self._estimate_wait_time(wc, position) if reliable else None
                    return QueuePositionInfo(
                        position=position,
                        estimated_wait_seconds=wait,
                        reliable=reliable,
                    )
        return None

    def _estimate_wait_time(
        self, workload_class: WorkloadClass, position: int
    ) -> float:
        """Estimate wait time based on position and average job duration.

        Uses a simple model: (position / concurrency_limit) * avg_duration.
        """
        concurrency = self._get_concurrency_limit(workload_class)
        # Default average durations per workload class (seconds)
        avg_durations: dict[WorkloadClass, float] = {
            WorkloadClass.INTERACTIVE_LANGUAGE: 5.0,
            WorkloadClass.IMAGE_GENERATION: 30.0,
            WorkloadClass.VIDEO_GENERATION: 120.0,
            WorkloadClass.TRAINING: 1800.0,
            WorkloadClass.VOICE_AUDIO: 15.0,
            WorkloadClass.BATCH: 60.0,
            WorkloadClass.PRODUCTION_STAGES: 90.0,
            WorkloadClass.PUBLISHING: 10.0,
        }
        avg_duration = avg_durations.get(workload_class, 60.0)
        # Batches of jobs run concurrently
        batches_ahead = max(1, (position - 1)) / max(1, concurrency)
        return round(batches_ahead * avg_duration, 1)

    def _is_wait_estimate_reliable(self, workload_class: WorkloadClass) -> bool:
        """Determine if wait time estimates are reliable for a workload class.

        Estimates are unreliable when:
        - No historical job completion data
        - Queue is empty (no baseline)
        - Workload class has high variance (training, video)
        """
        high_variance_classes = {
            WorkloadClass.TRAINING,
            WorkloadClass.VIDEO_GENERATION,
        }
        if workload_class in high_variance_classes:
            return False
        # If we have active jobs for this class, estimates are more reliable
        active = self._active_jobs.get(workload_class.value, 0)
        return active > 0 or len(self._queues[workload_class]) > 0

    def _get_concurrency_limit(self, workload_class: WorkloadClass) -> int:
        """Get the concurrency limit for a workload class."""
        return self._workload_concurrency_limits.get(
            workload_class.value, DEFAULT_WORKLOAD_CONCURRENCY_LIMIT
        )

    # ─── Active Jobs ──────────────────────────────────────────────────────

    def register_active_job(self, provider: str) -> None:
        """Increment active job count for a provider."""
        self._active_jobs[provider] = self._active_jobs.get(provider, 0) + 1

    def unregister_active_job(self, provider: str) -> None:
        """Decrement active job count for a provider."""
        current = self._active_jobs.get(provider, 0)
        self._active_jobs[provider] = max(0, current - 1)

    def get_active_jobs(self) -> dict[str, int]:
        """Get active job counts per provider."""
        return dict(self._active_jobs)

    def get_total_active_jobs(self) -> int:
        """Get total active jobs across all providers."""
        return sum(self._active_jobs.values())

    # ─── GPU Utilization ──────────────────────────────────────────────────

    def update_gpu_utilization(self, utilization: float) -> None:
        """Update GPU utilization (0.0 to 1.0). Called by worker health reports."""
        self._gpu_utilization = max(0.0, min(1.0, utilization))

    def get_gpu_utilization(self) -> float:
        """Get current GPU utilization as a fraction (0.0 to 1.0)."""
        return self._gpu_utilization

    # ─── Compute Liability ────────────────────────────────────────────────

    def update_compute_liability(self, liability_usd: float) -> None:
        """Update platform compute liability (total USD committed to in-flight jobs)."""
        self._platform_compute_liability = max(0.0, liability_usd)

    def get_compute_liability(self) -> float:
        """Get current platform compute liability in USD."""
        return self._platform_compute_liability

    # ─── Degradation Assessment ───────────────────────────────────────────

    def assess_degradation_level(self) -> DegradationLevel:
        """Determine current system degradation level.

        Returns:
            NORMAL: All capacity available, no queuing.
            ELEVATED: Some queues are building, minor delays expected.
            DEGRADED: Generation capacity exhausted, read-only navigation operational.
            CRITICAL: Budget exceeded or system failure.
        """
        total_queue = self.get_total_queue_depth()
        gpu_util = self._gpu_utilization

        # Check budget via cost tracker
        budget_exceeded = self._check_budget_exceeded()
        if budget_exceeded:
            return DegradationLevel.CRITICAL

        # Generation-specific: check if ANY generation class is at capacity with queue
        image_active = self._active_jobs.get(WorkloadClass.IMAGE_GENERATION.value, 0)
        image_limit = self._get_concurrency_limit(WorkloadClass.IMAGE_GENERATION)
        image_queue = len(self._queues[WorkloadClass.IMAGE_GENERATION])

        video_active = self._active_jobs.get(WorkloadClass.VIDEO_GENERATION.value, 0)
        video_limit = self._get_concurrency_limit(WorkloadClass.VIDEO_GENERATION)
        video_queue = len(self._queues[WorkloadClass.VIDEO_GENERATION])

        # DEGRADED: generation capacity exhausted (active at limit + queue building)
        image_exhausted = image_active >= image_limit and image_queue > 0
        video_exhausted = video_active >= video_limit and video_queue > 0
        if image_exhausted or video_exhausted:
            return DegradationLevel.DEGRADED

        # ELEVATED: high GPU utilization or significant queuing
        if gpu_util > 0.8 or total_queue > 5:
            return DegradationLevel.ELEVATED

        return DegradationLevel.NORMAL

    def _check_budget_exceeded(self) -> bool:
        """Check if the platform budget is exceeded via CostTracker."""
        try:
            from backend.infrastructure.cost_intelligence import get_cost_tracker

            tracker = get_cost_tracker()
            budget = tracker.check_budget()
            return not budget["within_budget"]
        except Exception:
            return False

    # ─── Admission Control ────────────────────────────────────────────────

    def evaluate_admission(
        self,
        workload_class_value: str,
        org_id: str,
    ) -> QueueDecision:
        """Decide whether to accept, queue, or reject an incoming work request.

        Per R90.1: Queue on overload rather than reject (unless budget exceeded).
        Per R90.2: Budget-exceeded gets 402 (reject), capacity-exceeded gets queued.

        Args:
            workload_class_value: The workload class string (e.g., "image_generation").
            org_id: The requesting organization's ID.

        Returns:
            QueueDecision indicating what to do with the request.
        """
        # Budget check first — reject with 402 if exceeded
        if self._check_budget_exceeded():
            return QueueDecision.REJECT_BUDGET

        # Check if workload class has capacity
        try:
            workload_class = WorkloadClass(workload_class_value)
        except ValueError:
            # Unknown workload class — accept (don't block on classification)
            return QueueDecision.ACCEPT

        concurrency_limit = self._get_concurrency_limit(workload_class)
        active = self._active_jobs.get(workload_class_value, 0)
        queue_depth = len(self._queues[workload_class])

        # If active jobs are below the limit, accept immediately
        if active < concurrency_limit:
            return QueueDecision.ACCEPT

        # If queue is full, still queue (don't reject) per R90.1
        # Only reject if queue exceeds max depth as a safety valve
        if queue_depth >= self._max_queue_depth:
            # Even at max queue, we queue rather than reject per requirement
            # but log a warning
            logger.warning(
                "queue_at_max_depth",
                extra={
                    "workload_class": workload_class_value,
                    "queue_depth": queue_depth,
                    "max_depth": self._max_queue_depth,
                    "org_id": org_id,
                },
            )

        return QueueDecision.QUEUE

    # ─── Capacity Snapshot ────────────────────────────────────────────────

    def get_capacity_snapshot(self) -> CapacitySnapshot:
        """Capture a point-in-time snapshot of all capacity metrics.

        Returns:
            CapacitySnapshot with all tracked metrics.
        """
        return CapacitySnapshot(
            active_users=self.get_active_user_count(),
            api_request_rate=self.get_request_rate(),
            brain_streams=self.get_brain_stream_count(),
            realtime_connections=self.get_realtime_connections(),
            queue_depth=self.get_queue_depth(),
            active_jobs=self.get_active_jobs(),
            gpu_utilization=self.get_gpu_utilization(),
            platform_compute_liability=self.get_compute_liability(),
            degradation_level=self.assess_degradation_level(),
            timestamp=datetime.now(UTC).isoformat(),
        )

    # ─── Tenant-Scoped Metrics ────────────────────────────────────────────

    def get_org_queue_status(self, org_id: str) -> dict[str, Any]:
        """Get queue status for a specific organization.

        Returns queue positions and wait times for all queued jobs belonging
        to the given org_id.
        """
        org_entries: list[dict[str, Any]] = []
        for wc, queue in self._queues.items():
            for i, entry in enumerate(queue):
                if entry.org_id == org_id:
                    reliable = self._is_wait_estimate_reliable(wc)
                    wait = self._estimate_wait_time(wc, i + 1) if reliable else None
                    org_entries.append({
                        "job_id": entry.job_id,
                        "workload_class": wc.value,
                        "position": i + 1,
                        "estimated_wait_seconds": wait,
                        "reliable": reliable,
                        "queued_at": datetime.fromtimestamp(
                            entry.queued_at, tz=UTC
                        ).isoformat(),
                    })
        return {
            "org_id": org_id,
            "queued_jobs": org_entries,
            "total_queued": len(org_entries),
        }


# =============================================================================
# Module-level singleton
# =============================================================================

_service: CapacityTelemetryService | None = None


def get_capacity_service() -> CapacityTelemetryService:
    """Get or create the global CapacityTelemetryService singleton."""
    global _service
    if _service is None:
        _service = CapacityTelemetryService()
    return _service

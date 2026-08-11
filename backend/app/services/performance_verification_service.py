"""Performance verification service — defines performance targets and measures compliance.

Implements a framework for defining, measuring, and verifying platform performance
against the targets specified in R76 (Product-Level Performance Requirements).

Key operations:
    - Define performance targets as typed constants
    - Run API performance checks (framework for measuring endpoint response times)
    - Verify measurements against targets (pass/fail per target)
    - Generate optimization recommendations for failing targets

Validates: Requirements R76.1, R76.2, R76.3, R76.4, R76.5, R76.6
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from app.core.logging import get_logger

if TYPE_CHECKING:
    import httpx

logger = get_logger(__name__)


# =============================================================================
# Constants — Performance Targets from R76
# =============================================================================


class PerformanceCategory(str, Enum):
    """Categories of performance targets per R76."""

    NAVIGATION = "navigation"
    DATA_LOADING = "data_loading"
    BRAIN_CHAT = "brain_chat"
    GENERATION = "generation"
    ADMIN = "admin"
    REALTIME = "realtime"


@dataclass(frozen=True)
class PerformanceTarget:
    """A single performance target with threshold and metadata.

    Attributes:
        name: Human-readable target name.
        target_ms: Maximum acceptable latency in milliseconds.
        category: Which R76 category this target belongs to.
        requirement_id: Traceability to the specific R76 acceptance criterion.
        description: Detailed explanation of what is being measured.
        endpoint: Optional API endpoint used for measurement.
        is_async: Whether this operation is inherently async (not interactive).
    """

    name: str
    target_ms: float
    category: PerformanceCategory
    requirement_id: str
    description: str
    endpoint: str | None = None
    is_async: bool = False


# R76.1 — Navigation and data loading targets
TARGET_PAGE_NAVIGATION_CACHED = PerformanceTarget(
    name="page_navigation_cached",
    target_ms=100.0,
    category=PerformanceCategory.NAVIGATION,
    requirement_id="R76.1",
    description="Page navigation with cached data renders within 100ms",
)

TARGET_FRESH_DATA_LOAD = PerformanceTarget(
    name="fresh_data_load",
    target_ms=500.0,
    category=PerformanceCategory.DATA_LOADING,
    requirement_id="R76.1",
    description="Fresh data load completes within 500ms for lists under 100 items",
    endpoint="/api/v1/talents",
)

TARGET_IMAGE_THUMBNAIL_CDN = PerformanceTarget(
    name="image_thumbnail_cdn",
    target_ms=200.0,
    category=PerformanceCategory.DATA_LOADING,
    requirement_id="R76.1",
    description="Image thumbnails load within 200ms from CDN",
)

# R76.2 — Talent and project query targets
TARGET_TALENT_DETAIL = PerformanceTarget(
    name="talent_detail_load",
    target_ms=300.0,
    category=PerformanceCategory.DATA_LOADING,
    requirement_id="R76.2",
    description="Single talent detail loads within 300ms",
    endpoint="/api/v1/talents/{id}",
)

TARGET_TALENT_LIST = PerformanceTarget(
    name="talent_list_load",
    target_ms=500.0,
    category=PerformanceCategory.DATA_LOADING,
    requirement_id="R76.2",
    description="Talent list (20 items) loads within 500ms",
    endpoint="/api/v1/talents?limit=20",
)

TARGET_PROJECT_DETAIL = PerformanceTarget(
    name="project_detail_load",
    target_ms=500.0,
    category=PerformanceCategory.DATA_LOADING,
    requirement_id="R76.2",
    description="Project detail with counts loads within 500ms",
    endpoint="/api/v1/projects/{id}",
)

# R76.3 — Brain/chat targets
TARGET_BRAIN_FIRST_TOKEN = PerformanceTarget(
    name="brain_first_token",
    target_ms=2000.0,
    category=PerformanceCategory.BRAIN_CHAT,
    requirement_id="R76.3",
    description="Brain first token appears within 2 seconds of submission",
    endpoint="/api/v1/brain/chat",
)

TARGET_BRAIN_MODE_SWITCH = PerformanceTarget(
    name="brain_mode_switch",
    target_ms=100.0,
    category=PerformanceCategory.BRAIN_CHAT,
    requirement_id="R76.3",
    description="Mode switching takes effect within 100ms",
)

# R76.4 — Generation targets
TARGET_JOB_SUBMISSION = PerformanceTarget(
    name="job_submission",
    target_ms=2000.0,
    category=PerformanceCategory.GENERATION,
    requirement_id="R76.4",
    description="Job submission returns HTTP 202 within 2 seconds",
    endpoint="/api/v1/jobs",
)

TARGET_JOB_STATUS_POLL = PerformanceTarget(
    name="job_status_poll",
    target_ms=200.0,
    category=PerformanceCategory.GENERATION,
    requirement_id="R76.4",
    description="Job status polling returns within 200ms",
    endpoint="/api/v1/jobs/{id}",
)

TARGET_REALTIME_EVENT_DELIVERY = PerformanceTarget(
    name="realtime_event_delivery",
    target_ms=1000.0,
    category=PerformanceCategory.REALTIME,
    requirement_id="R76.4",
    description=(
        "Realtime event delivery latency under 1 second "
        "from state change to client receipt"
    ),
)

# R76.5 — Admin dashboard targets
TARGET_FLEET_STATUS = PerformanceTarget(
    name="fleet_status_load",
    target_ms=1000.0,
    category=PerformanceCategory.ADMIN,
    requirement_id="R76.5",
    description="Fleet status loads within 1 second",
    endpoint="/api/v1/infrastructure/fleet/status",
)

TARGET_COST_SUMMARY = PerformanceTarget(
    name="cost_summary_load",
    target_ms=1000.0,
    category=PerformanceCategory.ADMIN,
    requirement_id="R76.5",
    description="Cost summary loads within 1 second",
    endpoint="/api/v1/costs/summary",
)

TARGET_CAPABILITY_REGISTRY = PerformanceTarget(
    name="capability_registry_load",
    target_ms=500.0,
    category=PerformanceCategory.ADMIN,
    requirement_id="R76.5",
    description="Capability registry loads within 500ms",
    endpoint="/api/v1/capabilities",
)

# All targets collected for iteration
ALL_PERFORMANCE_TARGETS: list[PerformanceTarget] = [
    TARGET_PAGE_NAVIGATION_CACHED,
    TARGET_FRESH_DATA_LOAD,
    TARGET_IMAGE_THUMBNAIL_CDN,
    TARGET_TALENT_DETAIL,
    TARGET_TALENT_LIST,
    TARGET_PROJECT_DETAIL,
    TARGET_BRAIN_FIRST_TOKEN,
    TARGET_BRAIN_MODE_SWITCH,
    TARGET_JOB_SUBMISSION,
    TARGET_JOB_STATUS_POLL,
    TARGET_REALTIME_EVENT_DELIVERY,
    TARGET_FLEET_STATUS,
    TARGET_COST_SUMMARY,
    TARGET_CAPABILITY_REGISTRY,
]


# =============================================================================
# Measurement Results
# =============================================================================


class VerificationStatus(str, Enum):
    """Pass/fail status for a performance verification check."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class PerformanceMeasurement:
    """Result of measuring a single performance target.

    Attributes:
        target_name: Name of the target being measured.
        measured_ms: Actual measured latency in milliseconds (None if skipped).
        status: Pass/fail/skipped/error.
        detail: Additional context about the measurement.
    """

    target_name: str
    measured_ms: float | None
    status: VerificationStatus
    detail: str = ""


@dataclass
class OptimizationRecommendation:
    """A recommendation for improving a failing performance target.

    Attributes:
        target_name: Which target this recommendation addresses.
        category: Performance category.
        recommendation: Human-readable action to take.
        explain_analyze_query: Suggested EXPLAIN ANALYZE query if DB-related.
        priority: HIGH / MEDIUM / LOW based on how far over target.
    """

    target_name: str
    category: PerformanceCategory
    recommendation: str
    explain_analyze_query: str | None = None
    priority: str = "MEDIUM"


# =============================================================================
# Service
# =============================================================================


# EXPLAIN ANALYZE templates for common slow-query scenarios
_EXPLAIN_TEMPLATES: dict[str, str] = {
    "talent_list_load": (
        "EXPLAIN ANALYZE SELECT * FROM ai_talent "
        "WHERE org_id = '<org_id>' AND deleted_at IS NULL "
        "ORDER BY created_at DESC LIMIT 20 OFFSET 0;"
    ),
    "talent_detail_load": (
        "EXPLAIN ANALYZE SELECT * FROM ai_talent "
        "WHERE id = '<talent_id>' AND org_id = '<org_id>';"
    ),
    "project_detail_load": (
        "EXPLAIN ANALYZE SELECT p.*, "
        "(SELECT count(*) FROM content_jobs WHERE project_id = p.id) as job_count "
        "FROM projects p WHERE p.id = '<project_id>' AND p.org_id = '<org_id>';"
    ),
    "job_status_poll": (
        "EXPLAIN ANALYZE SELECT * FROM content_jobs "
        "WHERE id = '<job_id>' AND org_id = '<org_id>';"
    ),
    "fleet_status_load": (
        "EXPLAIN ANALYZE SELECT w.*, "
        "(SELECT count(*) FROM content_jobs WHERE worker_id = w.id AND status = 'running') "
        "as active_jobs FROM workers w WHERE org_id = '<org_id>';"
    ),
    "cost_summary_load": (
        "EXPLAIN ANALYZE SELECT date_trunc('day', created_at) as day, "
        "sum(cost_usd) as total FROM content_jobs "
        "WHERE org_id = '<org_id>' AND created_at > now() - interval '30 days' "
        "GROUP BY day ORDER BY day;"
    ),
    "capability_registry_load": (
        "EXPLAIN ANALYZE SELECT * FROM capability_registry "
        "ORDER BY name;"
    ),
    "fresh_data_load": (
        "EXPLAIN ANALYZE SELECT * FROM ai_talent "
        "WHERE org_id = '<org_id>' AND deleted_at IS NULL "
        "ORDER BY created_at DESC LIMIT 100;"
    ),
}

# Recommendations for non-DB targets
_NON_DB_RECOMMENDATIONS: dict[str, str] = {
    "page_navigation_cached": (
        "Ensure SWR caching is configured with stale-while-revalidate. "
        "Use Next.js prefetching for navigation links. "
        "Verify CDN cache headers are set for static assets."
    ),
    "image_thumbnail_cdn": (
        "Verify B2_CDN_URL is configured and CDN cache-control headers "
        "are set (max-age=31536000 for immutable assets). "
        "Use WebP format with appropriate quality settings."
    ),
    "brain_first_token": (
        "Check Ollama model loading time. Ensure model is pre-loaded "
        "(not cold-started per request). Consider reducing context window "
        "size or using a smaller model for initial response."
    ),
    "brain_mode_switch": (
        "Mode switching should be a client-side state change only. "
        "Verify no API call is made during mode switch. "
        "If server validation needed, ensure it is a lightweight check."
    ),
    "job_submission": (
        "Job submission should return 202 immediately after enqueueing. "
        "Verify no synchronous validation that hits external services. "
        "Cost estimation should be cached or computed from local data."
    ),
    "realtime_event_delivery": (
        "Verify Supabase Realtime subscription is active. "
        "Check that job status updates are written with minimal latency. "
        "Consider reducing transaction commit interval for status changes."
    ),
}


class PerformanceVerificationService:
    """Service for defining, measuring, and verifying platform performance targets.

    Provides the framework for R76 compliance verification. Does not run live
    benchmarks directly but defines the measurement contract and comparison logic.

    Validates: R76.1, R76.2, R76.3, R76.4, R76.5, R76.6
    """

    def __init__(self, base_url: str = "http://localhost:8000") -> None:
        self._base_url = base_url

    def get_targets(self) -> list[PerformanceTarget]:
        """Return all defined performance targets.

        Returns the complete set of R76-defined targets with their
        thresholds, categories, and requirement traceability.
        """
        return list(ALL_PERFORMANCE_TARGETS)

    def get_targets_by_category(
        self, category: PerformanceCategory
    ) -> list[PerformanceTarget]:
        """Return performance targets filtered by category."""
        return [t for t in ALL_PERFORMANCE_TARGETS if t.category == category]

    async def run_api_performance_check(
        self,
        client: "httpx.AsyncClient | None" = None,
        targets: list[PerformanceTarget] | None = None,
    ) -> list[PerformanceMeasurement]:
        """Measure key endpoint response times against targets.

        If no client is provided, returns SKIPPED measurements (framework mode).
        When a client is provided, times actual HTTP calls to measurable endpoints.

        Args:
            client: Optional httpx.AsyncClient for making real requests.
            targets: Optional subset of targets to measure. Defaults to all.

        Returns:
            List of PerformanceMeasurement results.
        """
        check_targets = targets or ALL_PERFORMANCE_TARGETS
        measurements: list[PerformanceMeasurement] = []

        for target in check_targets:
            if target.endpoint is None:
                # Non-API targets (client-side navigation, CDN, realtime)
                measurements.append(
                    PerformanceMeasurement(
                        target_name=target.name,
                        measured_ms=None,
                        status=VerificationStatus.SKIPPED,
                        detail=(
                            f"Target '{target.name}' is not measurable via API call "
                            f"(requires client-side or infrastructure measurement)"
                        ),
                    )
                )
                continue

            if client is None:
                measurements.append(
                    PerformanceMeasurement(
                        target_name=target.name,
                        measured_ms=None,
                        status=VerificationStatus.SKIPPED,
                        detail="No HTTP client provided; measurement skipped",
                    )
                )
                continue

            # Measure actual endpoint response time
            measurement = await self._measure_endpoint(client, target)
            measurements.append(measurement)

        return measurements

    async def _measure_endpoint(
        self,
        client: "httpx.AsyncClient",
        target: PerformanceTarget,
    ) -> PerformanceMeasurement:
        """Time a single endpoint request.

        Uses time.perf_counter for high-resolution measurement.
        """
        url = f"{self._base_url}{target.endpoint}"

        try:
            start = time.perf_counter()
            if target.name == "job_submission":
                response = await client.post(url, json={})
            else:
                response = await client.get(url)
            elapsed_ms = (time.perf_counter() - start) * 1000.0

            # Determine pass/fail based on target
            if response.status_code >= 500:
                return PerformanceMeasurement(
                    target_name=target.name,
                    measured_ms=elapsed_ms,
                    status=VerificationStatus.ERROR,
                    detail=f"Server error: HTTP {response.status_code}",
                )

            status = (
                VerificationStatus.PASSED
                if elapsed_ms <= target.target_ms
                else VerificationStatus.FAILED
            )
            return PerformanceMeasurement(
                target_name=target.name,
                measured_ms=elapsed_ms,
                status=status,
                detail=(
                    f"Measured {elapsed_ms:.1f}ms vs target {target.target_ms}ms"
                ),
            )

        except Exception as exc:
            logger.warning(
                "performance_measurement_error",
                target=target.name,
                endpoint=target.endpoint,
                error=str(exc),
            )
            return PerformanceMeasurement(
                target_name=target.name,
                measured_ms=None,
                status=VerificationStatus.ERROR,
                detail=f"Measurement failed: {exc}",
            )

    def verify_targets_met(
        self,
        measurements: list[PerformanceMeasurement],
    ) -> dict[str, PerformanceMeasurement]:
        """Check measurements against targets and return pass/fail per target.

        For each measurement, compares the measured_ms against the corresponding
        target's threshold. Skipped/error measurements retain their original status.

        Returns:
            Dict keyed by target_name with the verified PerformanceMeasurement.
        """
        target_map = {t.name: t for t in ALL_PERFORMANCE_TARGETS}
        results: dict[str, PerformanceMeasurement] = {}

        for measurement in measurements:
            target = target_map.get(measurement.target_name)

            if target is None:
                results[measurement.target_name] = PerformanceMeasurement(
                    target_name=measurement.target_name,
                    measured_ms=measurement.measured_ms,
                    status=VerificationStatus.ERROR,
                    detail="Unknown target — no matching definition found",
                )
                continue

            if measurement.status in (
                VerificationStatus.SKIPPED,
                VerificationStatus.ERROR,
            ):
                results[measurement.target_name] = measurement
                continue

            if measurement.measured_ms is None:
                results[measurement.target_name] = PerformanceMeasurement(
                    target_name=measurement.target_name,
                    measured_ms=None,
                    status=VerificationStatus.SKIPPED,
                    detail="No measurement value available",
                )
                continue

            passed = measurement.measured_ms <= target.target_ms
            results[measurement.target_name] = PerformanceMeasurement(
                target_name=measurement.target_name,
                measured_ms=measurement.measured_ms,
                status=(
                    VerificationStatus.PASSED if passed else VerificationStatus.FAILED
                ),
                detail=(
                    f"{'PASS' if passed else 'FAIL'}: "
                    f"{measurement.measured_ms:.1f}ms vs target {target.target_ms}ms"
                ),
            )

        return results

    def get_optimization_recommendations(
        self,
        measurements: list[PerformanceMeasurement],
    ) -> list[OptimizationRecommendation]:
        """Generate optimization recommendations for targets that fail.

        For DB-related targets, suggests EXPLAIN ANALYZE queries (R76.6).
        For non-DB targets, provides architectural recommendations.

        Args:
            measurements: List of measurements (typically from verify_targets_met).

        Returns:
            List of recommendations for failed targets only.
        """
        target_map = {t.name: t for t in ALL_PERFORMANCE_TARGETS}
        recommendations: list[OptimizationRecommendation] = []

        for measurement in measurements:
            if measurement.status != VerificationStatus.FAILED:
                continue

            target = target_map.get(measurement.target_name)
            if target is None:
                continue

            # Determine priority based on how far over target
            priority = self._compute_priority(measurement.measured_ms, target.target_ms)

            # Get EXPLAIN ANALYZE query if available
            explain_query = _EXPLAIN_TEMPLATES.get(measurement.target_name)

            # Get non-DB recommendation if available
            non_db_rec = _NON_DB_RECOMMENDATIONS.get(measurement.target_name)

            recommendation_text = self._build_recommendation(
                target, measurement, explain_query, non_db_rec
            )

            recommendations.append(
                OptimizationRecommendation(
                    target_name=measurement.target_name,
                    category=target.category,
                    recommendation=recommendation_text,
                    explain_analyze_query=explain_query,
                    priority=priority,
                )
            )

        return recommendations

    @staticmethod
    def _compute_priority(measured_ms: float | None, target_ms: float) -> str:
        """Determine recommendation priority based on overshoot factor."""
        if measured_ms is None:
            return "MEDIUM"

        ratio = measured_ms / target_ms
        if ratio > 5.0:
            return "HIGH"
        elif ratio > 2.0:
            return "MEDIUM"
        else:
            return "LOW"

    @staticmethod
    def _build_recommendation(
        target: PerformanceTarget,
        measurement: PerformanceMeasurement,
        explain_query: str | None,
        non_db_rec: str | None,
    ) -> str:
        """Build a human-readable recommendation string."""
        parts: list[str] = []

        overshoot = ""
        if measurement.measured_ms is not None:
            overshoot = (
                f" (measured {measurement.measured_ms:.0f}ms, "
                f"target {target.target_ms:.0f}ms)"
            )

        parts.append(f"Target '{target.name}' exceeds threshold{overshoot}.")

        if explain_query:
            parts.append(
                f"Run EXPLAIN ANALYZE to identify query bottlenecks: {explain_query}"
            )

        if non_db_rec:
            parts.append(non_db_rec)

        if not explain_query and not non_db_rec:
            parts.append(
                "Investigate endpoint handler for blocking operations, "
                "N+1 queries, or missing indexes."
            )

        return " ".join(parts)

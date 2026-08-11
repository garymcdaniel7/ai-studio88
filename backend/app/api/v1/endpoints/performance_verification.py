"""Performance Verification API Endpoints.

Routes:
    GET  /api/v1/performance/targets → 200 (all defined performance targets)
    POST /api/v1/performance/verify  → 200 (run verification checks and return results)

Provides the framework for measuring and reporting platform performance
against the targets defined in R76. The verify endpoint runs available
API-level checks and returns pass/fail with optimization recommendations.

Validates: Requirements R76.1, R76.2, R76.3, R76.4, R76.5, R76.6
"""

from __future__ import annotations

from fastapi import APIRouter, Query, status

from app.schemas.performance_verification import (
    OptimizationRecommendationResponse,
    PerformanceCategorySchema,
    PerformanceMeasurementResponse,
    PerformanceTargetListResponse,
    PerformanceTargetResponse,
    PerformanceVerificationResponse,
    PerformanceVerificationSummary,
    VerificationStatusSchema,
)
from app.services.performance_verification_service import (
    PerformanceCategory,
    PerformanceVerificationService,
    VerificationStatus,
)

router = APIRouter(prefix="/performance", tags=["performance"])

# Service instance (stateless, no DB dependency)
_service = PerformanceVerificationService()


@router.get(
    "/targets",
    response_model=PerformanceTargetListResponse,
    status_code=status.HTTP_200_OK,
    summary="List all performance targets",
    description=(
        "Returns all defined performance targets with their thresholds, "
        "categories, and requirement traceability. These targets are derived "
        "from R76 acceptance criteria."
    ),
)
async def list_performance_targets(
    category: PerformanceCategorySchema | None = Query(
        default=None,
        description="Filter targets by category",
    ),
) -> PerformanceTargetListResponse:
    """List all defined performance targets with optional category filter.

    Requirements: R76.1, R76.2, R76.3, R76.4, R76.5
    """
    targets = _service.get_targets()

    if category is not None:
        targets = [
            t for t in targets if t.category.value == category.value
        ]

    items = [
        PerformanceTargetResponse(
            name=t.name,
            target_ms=t.target_ms,
            category=PerformanceCategorySchema(t.category.value),
            requirement_id=t.requirement_id,
            description=t.description,
            endpoint=t.endpoint,
            is_async=t.is_async,
        )
        for t in targets
    ]

    categories = sorted(set(t.category for t in items))

    return PerformanceTargetListResponse(
        items=items,
        total=len(items),
        categories=categories,
    )


@router.post(
    "/verify",
    response_model=PerformanceVerificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Run performance verification checks",
    description=(
        "Runs available performance measurements against defined targets. "
        "Returns pass/fail for each target and EXPLAIN ANALYZE recommendations "
        "for any failing targets (R76.6). "
        "Note: without a live HTTP client, API targets will be marked SKIPPED."
    ),
)
async def verify_performance(
    category: PerformanceCategorySchema | None = Query(
        default=None,
        description="Optionally restrict verification to a single category",
    ),
) -> PerformanceVerificationResponse:
    """Run performance verification and return results with recommendations.

    In framework mode (no external HTTP client), API-dependent targets
    are marked SKIPPED. Non-API targets (client-side, CDN, realtime)
    are always SKIPPED as they require infrastructure-level measurement.

    Requirements: R76.1, R76.2, R76.3, R76.4, R76.5, R76.6
    """
    targets = _service.get_targets()

    if category is not None:
        targets = [
            t for t in targets if t.category.value == category.value
        ]

    # Run checks without a live client (framework mode)
    measurements = await _service.run_api_performance_check(
        client=None, targets=targets
    )

    # Verify against thresholds
    verified = _service.verify_targets_met(measurements)

    # Generate recommendations for failures
    failed_measurements = [
        m for m in verified.values() if m.status == VerificationStatus.FAILED
    ]
    recommendations = _service.get_optimization_recommendations(failed_measurements)

    # Build target lookup for response
    target_map = {t.name: t for t in targets}

    # Build response
    measurement_responses = [
        PerformanceMeasurementResponse(
            target_name=m.target_name,
            measured_ms=m.measured_ms,
            target_ms=target_map[m.target_name].target_ms,
            status=VerificationStatusSchema(m.status.value),
            detail=m.detail,
        )
        for m in verified.values()
        if m.target_name in target_map
    ]

    recommendation_responses = [
        OptimizationRecommendationResponse(
            target_name=r.target_name,
            category=PerformanceCategorySchema(r.category.value),
            recommendation=r.recommendation,
            explain_analyze_query=r.explain_analyze_query,
            priority=r.priority,
        )
        for r in recommendations
    ]

    # Compute summary
    passed_count = sum(
        1 for m in verified.values() if m.status == VerificationStatus.PASSED
    )
    failed_count = sum(
        1 for m in verified.values() if m.status == VerificationStatus.FAILED
    )
    skipped_count = sum(
        1 for m in verified.values() if m.status == VerificationStatus.SKIPPED
    )
    error_count = sum(
        1 for m in verified.values() if m.status == VerificationStatus.ERROR
    )

    overall = (
        VerificationStatusSchema.PASSED
        if failed_count == 0 and error_count == 0
        else VerificationStatusSchema.FAILED
    )

    summary = PerformanceVerificationSummary(
        total_targets=len(verified),
        passed=passed_count,
        failed=failed_count,
        skipped=skipped_count,
        errors=error_count,
        overall_status=overall,
    )

    return PerformanceVerificationResponse(
        measurements=measurement_responses,
        summary=summary,
        recommendations=recommendation_responses,
    )

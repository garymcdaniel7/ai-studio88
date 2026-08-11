"""Social Analytics API Router.

Provides endpoints for social intelligence: accounts, content, metrics,
watchlists, derived insights, experiments, and sync operations.

All endpoints require authentication and enforce tenant isolation.
Missing metrics are represented as UNAVAILABLE — values are never fabricated.

Validates: Requirements R107.2, R107.3, R107.4, R107.10, R43.11, R43.12
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, status

from app.core.dependencies import DBSessionDep, PaginationDep, TenantContextDep
from app.core.logging import get_logger
from backend.social_analytics.schemas import (
    DerivedInsightListResponse,
    DerivedInsightResponse,
    ExperimentCreate,
    ExperimentListResponse,
    ExperimentResponse,
    SocialAccountListResponse,
    SocialAccountResponse,
    SocialContentListResponse,
    SocialContentResponse,
    SocialMetricListResponse,
    SocialMetricSnapshotResponse,
    SyncStatusResponse,
    SyncTriggerRequest,
    WatchlistCreate,
    WatchlistListResponse,
    WatchlistMemberResponse,
    WatchlistResponse,
)
from backend.social_analytics.service import SocialAnalyticsService

logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/v1/social",
    tags=["social-analytics"],
)


# =============================================================================
# Social Accounts
# =============================================================================


@router.get(
    "/accounts",
    response_model=SocialAccountListResponse,
    summary="List connected social accounts",
)
async def list_social_accounts(
    tenant: TenantContextDep,
    db: DBSessionDep,
    pagination: PaginationDep,
    platform: str | None = Query(default=None, description="Filter by platform"),
) -> SocialAccountListResponse:
    """List connected social platform accounts for the workspace.

    Returns paginated accounts with sync state and capabilities.
    Scoped to the authenticated user's organisation.
    """
    service = SocialAnalyticsService(db)
    items, total = await service.list_accounts(
        org_id=tenant.org_id,
        platform=platform,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return SocialAccountListResponse(
        items=[SocialAccountResponse.model_validate(a) for a in items],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


# =============================================================================
# Social Content
# =============================================================================


@router.get(
    "/content",
    response_model=SocialContentListResponse,
    summary="List social content items",
)
async def list_social_content(
    tenant: TenantContextDep,
    db: DBSessionDep,
    pagination: PaginationDep,
    platform: str | None = Query(default=None, description="Filter by platform"),
    account_id: UUID | None = Query(default=None, description="Filter by account"),
    talent_id: UUID | None = Query(default=None, description="Filter by talent"),
    content_type: str | None = Query(
        default=None, description="Filter by content type"
    ),
) -> SocialContentListResponse:
    """List social content items (posts) for the workspace.

    Returns paginated content linked to social accounts, optionally
    filtered by platform, account, talent, or content type.
    """
    service = SocialAnalyticsService(db)
    items, total = await service.list_content(
        org_id=tenant.org_id,
        platform=platform,
        account_id=account_id,
        talent_id=talent_id,
        content_type=content_type,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return SocialContentListResponse(
        items=[SocialContentResponse.model_validate(c) for c in items],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


# =============================================================================
# Metrics
# =============================================================================


@router.get(
    "/metrics",
    response_model=SocialMetricListResponse,
    summary="List social metric snapshots",
)
async def list_social_metrics(
    tenant: TenantContextDep,
    db: DBSessionDep,
    pagination: PaginationDep,
    account_id: UUID | None = Query(
        default=None, description="Filter by social account"
    ),
    content_id: UUID | None = Query(
        default=None, description="Filter by content item"
    ),
    provenance: str | None = Query(
        default=None,
        description=(
            "Filter by data provenance: FIRST_PARTY_CONNECTED, "
            "PUBLIC_PLATFORM_DATA, THIRD_PARTY_DATA, USER_IMPORTED, "
            "DERIVED_ANALYSIS"
        ),
    ),
) -> SocialMetricListResponse:
    """List metric observation snapshots for the workspace.

    Metrics represent point-in-time observations of social performance.
    Each snapshot carries provenance metadata indicating data origin.
    Missing metrics are represented as UNAVAILABLE — values are never
    fabricated.

    Data provenance values:
        - FIRST_PARTY_CONNECTED: From authorized platform connections (highest trust)
        - PUBLIC_PLATFORM_DATA: Publicly available metrics
        - THIRD_PARTY_DATA: Approved intelligence providers
        - USER_IMPORTED: Manually provided by user
        - DERIVED_ANALYSIS: Calculated from other sources
    """
    service = SocialAnalyticsService(db)
    items, total = await service.list_metrics(
        org_id=tenant.org_id,
        account_id=account_id,
        content_id=content_id,
        provenance=provenance,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return SocialMetricListResponse(
        items=[SocialMetricSnapshotResponse.model_validate(m) for m in items],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


# =============================================================================
# Watchlists
# =============================================================================


@router.get(
    "/watchlists",
    response_model=WatchlistListResponse,
    summary="List competitive watchlists",
)
async def list_watchlists(
    tenant: TenantContextDep,
    db: DBSessionDep,
    pagination: PaginationDep,
) -> WatchlistListResponse:
    """List all watchlists for competitive/market intelligence.

    Watchlists organize tracked entities (creators, brands, competitors,
    topics, hashtags) for ongoing monitoring.
    """
    service = SocialAnalyticsService(db)
    items, total = await service.list_watchlists(
        org_id=tenant.org_id,
        limit=pagination.limit,
        offset=pagination.offset,
    )

    # Eagerly load members for each watchlist
    watchlist_responses = []
    for watchlist in items:
        members = await service.get_watchlist_members(
            org_id=tenant.org_id,
            watchlist_id=watchlist.id,
        )
        resp = WatchlistResponse(
            id=watchlist.id,
            org_id=watchlist.org_id,
            name=watchlist.name,
            description=watchlist.description,
            category=watchlist.category,
            created_at=watchlist.created_at,
            updated_at=watchlist.updated_at,
            members=[WatchlistMemberResponse.model_validate(m) for m in members],
        )
        watchlist_responses.append(resp)

    return WatchlistListResponse(
        items=watchlist_responses,
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.post(
    "/watchlists",
    response_model=WatchlistResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a competitive watchlist",
)
async def create_watchlist(
    data: WatchlistCreate,
    tenant: TenantContextDep,
    db: DBSessionDep,
) -> WatchlistResponse:
    """Create a new watchlist for competitive/market intelligence.

    Optionally include initial members (creators, brands, hashtags, etc.)
    in the creation request.
    """
    service = SocialAnalyticsService(db)
    watchlist = await service.create_watchlist(
        org_id=tenant.org_id,
        data=data,
    )

    # Load members for response
    members = await service.get_watchlist_members(
        org_id=tenant.org_id,
        watchlist_id=watchlist.id,
    )

    return WatchlistResponse(
        id=watchlist.id,
        org_id=watchlist.org_id,
        name=watchlist.name,
        description=watchlist.description,
        category=watchlist.category,
        created_at=watchlist.created_at,
        updated_at=watchlist.updated_at,
        members=[WatchlistMemberResponse.model_validate(m) for m in members],
    )


# =============================================================================
# Intelligence (Derived Insights)
# =============================================================================


@router.get(
    "/intelligence",
    response_model=DerivedInsightListResponse,
    summary="List derived intelligence insights",
)
async def list_intelligence(
    tenant: TenantContextDep,
    db: DBSessionDep,
    pagination: PaginationDep,
    insight_type: str | None = Query(
        default=None,
        description="Filter by insight type: trend, anomaly, recommendation, pattern, comparison",
    ),
) -> DerivedInsightListResponse:
    """List derived analytics insights for the workspace.

    Insights are generated from observed metrics and carry provenance
    metadata. DERIVED_ANALYSIS provenance is never misrepresented as
    FIRST_PARTY_CONNECTED.

    Insight types:
        - trend: Directional movement in metrics
        - anomaly: Unexpected metric changes
        - recommendation: Actionable content suggestions
        - pattern: Recurring behavioral patterns
        - comparison: Cross-entity or cross-period comparisons
    """
    service = SocialAnalyticsService(db)
    items, total = await service.list_insights(
        org_id=tenant.org_id,
        insight_type=insight_type,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return DerivedInsightListResponse(
        items=[DerivedInsightResponse.model_validate(i) for i in items],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


# =============================================================================
# Experiments
# =============================================================================


@router.get(
    "/experiments",
    response_model=ExperimentListResponse,
    summary="List content experiments",
)
async def list_experiments(
    tenant: TenantContextDep,
    db: DBSessionDep,
    pagination: PaginationDep,
    experiment_status: str | None = Query(
        default=None,
        alias="status",
        description="Filter by status: draft, active, observing, completed, cancelled",
    ),
) -> ExperimentListResponse:
    """List content experiments (A/B tests) for the workspace.

    Experiments track hypothesis, variants, target metrics, and results
    for data-driven content strategy optimization.
    """
    service = SocialAnalyticsService(db)
    items, total = await service.list_experiments(
        org_id=tenant.org_id,
        status=experiment_status,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return ExperimentListResponse(
        items=[ExperimentResponse.model_validate(e) for e in items],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.post(
    "/experiments",
    response_model=ExperimentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a content experiment",
)
async def create_experiment(
    data: ExperimentCreate,
    tenant: TenantContextDep,
    db: DBSessionDep,
) -> ExperimentResponse:
    """Create a new content experiment (A/B test).

    Experiments start in 'draft' status and can be activated when
    content variants are published and observation begins.
    """
    service = SocialAnalyticsService(db)
    experiment = await service.create_experiment(
        org_id=tenant.org_id,
        data=data,
    )
    return ExperimentResponse.model_validate(experiment)


# =============================================================================
# Sync
# =============================================================================


@router.post(
    "/sync",
    response_model=SyncStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger manual metrics sync",
)
async def trigger_sync(
    data: SyncTriggerRequest,
    tenant: TenantContextDep,
    db: DBSessionDep,
) -> SyncStatusResponse:
    """Trigger a manual metrics sync for connected social accounts.

    Queues sync operations for the specified accounts (or all accounts
    if no filter provided). The sync runs asynchronously.

    Returns 202 Accepted with the number of accounts queued.
    """
    service = SocialAnalyticsService(db)
    message, accounts_queued = await service.trigger_sync(
        org_id=tenant.org_id,
        data=data,
    )
    return SyncStatusResponse(
        status="queued" if accounts_queued > 0 else "no_accounts",
        message=message,
        accounts_queued=accounts_queued,
    )

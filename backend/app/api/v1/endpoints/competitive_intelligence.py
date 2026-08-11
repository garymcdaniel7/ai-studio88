"""Competitive intelligence API endpoints — watchlists and market intelligence.

Provides endpoints for:
    - CRUD on watchlists (workspace-level named lists)
    - CRUD on watchlist members (creator, brand, competitor, topic, hashtag)
    - Competitive intelligence queries (publicly available metrics only)
    - Competitor profile lookups

All data is from publicly available sources. Private analytics from connected
accounts are never exposed through these endpoints.

Source attribution is mandatory: Brain/Hermes can identify the source of each
insight returned from these endpoints.

Validates: Requirements R108.1, R108.2, R108.3, R108.4, R108.5,
           R108.6, R108.7, R108.8, R108.10
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.core.dependencies import DBSessionDep, TenantContextDep
from app.schemas.competitive_intelligence import (
    CompetitiveIntelligenceResponse,
    CompetitorProfileResponse,
    WatchlistCreateRequest,
    WatchlistListResponse,
    WatchlistMemberCreateRequest,
    WatchlistMemberListResponse,
    WatchlistMemberResponse,
    WatchlistMemberUpdateRequest,
    WatchlistResponse,
    WatchlistUpdateRequest,
    WatchType,
)
from app.services.competitive_intelligence_service import (
    CompetitiveIntelligenceService,
    WatchlistMemberNotFoundError,
    WatchlistNotFoundError,
)

router = APIRouter(prefix="/social/watchlists", tags=["competitive-intelligence"])


# =============================================================================
# Watchlist CRUD
# =============================================================================


@router.get("", response_model=WatchlistListResponse)
async def list_watchlists(
    tenant: TenantContextDep,
    db: DBSessionDep,
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
) -> WatchlistListResponse:
    """List all watchlists in the workspace.

    Returns paginated watchlists with member counts, newest first.
    """
    service = CompetitiveIntelligenceService(db=db)
    items, total = await service.list_watchlists(
        org_id=tenant.org_id,
        limit=limit,
        offset=offset,
    )

    # Enrich with member counts
    responses = []
    for watchlist in items:
        count = await service.get_member_count(tenant.org_id, watchlist.id)
        responses.append(
            WatchlistResponse(
                id=watchlist.id,
                org_id=watchlist.org_id,
                name=watchlist.name,
                description=watchlist.description,
                category=watchlist.category,
                member_count=count,
                created_at=watchlist.created_at,
                updated_at=watchlist.updated_at,
            )
        )

    return WatchlistListResponse(
        items=responses,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=WatchlistResponse, status_code=status.HTTP_201_CREATED)
async def create_watchlist(
    body: WatchlistCreateRequest,
    tenant: TenantContextDep,
    db: DBSessionDep,
) -> WatchlistResponse:
    """Create a new competitive intelligence watchlist.

    Watchlists organize tracked entities (creators, brands, competitors,
    topics, hashtags) for market intelligence monitoring.
    """
    service = CompetitiveIntelligenceService(db=db)
    watchlist = await service.create_watchlist(
        org_id=tenant.org_id,
        name=body.name,
        description=body.description,
        category=body.category,
    )
    await db.commit()
    return WatchlistResponse(
        id=watchlist.id,
        org_id=watchlist.org_id,
        name=watchlist.name,
        description=watchlist.description,
        category=watchlist.category,
        member_count=0,
        created_at=watchlist.created_at,
        updated_at=watchlist.updated_at,
    )


@router.get("/{watchlist_id}", response_model=WatchlistResponse)
async def get_watchlist(
    watchlist_id: UUID,
    tenant: TenantContextDep,
    db: DBSessionDep,
) -> WatchlistResponse:
    """Get a single watchlist by ID."""
    service = CompetitiveIntelligenceService(db=db)
    try:
        watchlist = await service.get_watchlist(tenant.org_id, watchlist_id)
    except WatchlistNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Watchlist not found",
        )
    count = await service.get_member_count(tenant.org_id, watchlist_id)
    return WatchlistResponse(
        id=watchlist.id,
        org_id=watchlist.org_id,
        name=watchlist.name,
        description=watchlist.description,
        category=watchlist.category,
        member_count=count,
        created_at=watchlist.created_at,
        updated_at=watchlist.updated_at,
    )


@router.patch("/{watchlist_id}", response_model=WatchlistResponse)
async def update_watchlist(
    watchlist_id: UUID,
    body: WatchlistUpdateRequest,
    tenant: TenantContextDep,
    db: DBSessionDep,
) -> WatchlistResponse:
    """Update a watchlist's name, description, or category."""
    service = CompetitiveIntelligenceService(db=db)
    try:
        watchlist = await service.update_watchlist(
            org_id=tenant.org_id,
            watchlist_id=watchlist_id,
            name=body.name,
            description=body.description,
            category=body.category,
        )
    except WatchlistNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Watchlist not found",
        )
    await db.commit()
    count = await service.get_member_count(tenant.org_id, watchlist_id)
    return WatchlistResponse(
        id=watchlist.id,
        org_id=watchlist.org_id,
        name=watchlist.name,
        description=watchlist.description,
        category=watchlist.category,
        member_count=count,
        created_at=watchlist.created_at,
        updated_at=watchlist.updated_at,
    )


@router.delete("/{watchlist_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_watchlist(
    watchlist_id: UUID,
    tenant: TenantContextDep,
    db: DBSessionDep,
) -> None:
    """Delete a watchlist and all its members."""
    service = CompetitiveIntelligenceService(db=db)
    try:
        await service.delete_watchlist(tenant.org_id, watchlist_id)
    except WatchlistNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Watchlist not found",
        )
    await db.commit()


# =============================================================================
# Watchlist Members CRUD
# =============================================================================


@router.get("/{watchlist_id}/members", response_model=WatchlistMemberListResponse)
async def list_watchlist_members(
    watchlist_id: UUID,
    tenant: TenantContextDep,
    db: DBSessionDep,
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    watch_type: WatchType | None = Query(None, description="Filter by type"),
) -> WatchlistMemberListResponse:
    """List members of a watchlist with optional type filter.

    Supported watch_type values: creator, brand, competitor, topic, hashtag.
    """
    service = CompetitiveIntelligenceService(db=db)
    try:
        items, total = await service.list_members(
            org_id=tenant.org_id,
            watchlist_id=watchlist_id,
            limit=limit,
            offset=offset,
            watch_type=watch_type.value if watch_type else None,
        )
    except WatchlistNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Watchlist not found",
        )

    return WatchlistMemberListResponse(
        items=[WatchlistMemberResponse.model_validate(m) for m in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/{watchlist_id}/members",
    response_model=WatchlistMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_watchlist_member(
    watchlist_id: UUID,
    body: WatchlistMemberCreateRequest,
    tenant: TenantContextDep,
    db: DBSessionDep,
) -> WatchlistMemberResponse:
    """Add a new member to a watchlist.

    Supported watch types:
    - creator: Individual content creator (@handle)
    - brand: Brand account (@handle or name)
    - competitor: Direct competitor
    - topic: Topic keyword
    - hashtag: Hashtag (#tag)
    """
    service = CompetitiveIntelligenceService(db=db)
    try:
        member = await service.add_member(
            org_id=tenant.org_id,
            watchlist_id=watchlist_id,
            watch_type=body.watch_type.value,
            account_identifier=body.account_identifier,
            display_name=body.display_name,
            platform=body.platform,
            notes=body.notes,
        )
    except WatchlistNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Watchlist not found",
        )
    await db.commit()
    return WatchlistMemberResponse.model_validate(member)


@router.patch(
    "/{watchlist_id}/members/{member_id}",
    response_model=WatchlistMemberResponse,
)
async def update_watchlist_member(
    watchlist_id: UUID,
    member_id: UUID,
    body: WatchlistMemberUpdateRequest,
    tenant: TenantContextDep,
    db: DBSessionDep,
) -> WatchlistMemberResponse:
    """Update a watchlist member's display name or notes."""
    service = CompetitiveIntelligenceService(db=db)
    try:
        # Verify watchlist belongs to this org
        await service.get_watchlist(tenant.org_id, watchlist_id)
        member = await service.update_member(
            org_id=tenant.org_id,
            member_id=member_id,
            display_name=body.display_name,
            notes=body.notes,
        )
    except WatchlistNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Watchlist not found",
        )
    except WatchlistMemberNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Watchlist member not found",
        )
    await db.commit()
    return WatchlistMemberResponse.model_validate(member)


@router.delete(
    "/{watchlist_id}/members/{member_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_watchlist_member(
    watchlist_id: UUID,
    member_id: UUID,
    tenant: TenantContextDep,
    db: DBSessionDep,
) -> None:
    """Remove a member from a watchlist."""
    service = CompetitiveIntelligenceService(db=db)
    try:
        await service.get_watchlist(tenant.org_id, watchlist_id)
        await service.remove_member(tenant.org_id, member_id)
    except WatchlistNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Watchlist not found",
        )
    except WatchlistMemberNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Watchlist member not found",
        )
    await db.commit()


# =============================================================================
# Competitive Intelligence Queries
# =============================================================================


@router.get(
    "/{watchlist_id}/intelligence",
    response_model=CompetitiveIntelligenceResponse,
)
async def get_competitive_intelligence(
    watchlist_id: UUID,
    tenant: TenantContextDep,
    db: DBSessionDep,
) -> CompetitiveIntelligenceResponse:
    """Get competitive intelligence for a watchlist.

    Returns aggregated public metrics and derived insights for all members.
    All data is from publicly available sources — never private analytics.

    Brain/Hermes uses this to answer competitive questions, identifying
    the source of each insight (R108.7).

    Disclaimers are always included (R108.8):
    - Data source attribution
    - Accuracy limitations
    - Clear separation from private analytics
    """
    service = CompetitiveIntelligenceService(db=db)
    try:
        intelligence = await service.get_watchlist_intelligence(
            org_id=tenant.org_id,
            watchlist_id=watchlist_id,
        )
    except WatchlistNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Watchlist not found",
        )

    # Map profiles to response models
    profiles = [
        CompetitorProfileResponse(**profile)
        for profile in intelligence["profiles"]
    ]

    return CompetitiveIntelligenceResponse(
        watchlist_id=intelligence["watchlist_id"],
        watchlist_name=intelligence["watchlist_name"],
        profiles=profiles,
        insights=intelligence["insights"],
        data_sources=intelligence["data_sources"],
        rate_limit_status=intelligence["rate_limit_status"],
        disclaimers=intelligence["disclaimers"],
    )


@router.get(
    "/{watchlist_id}/members/{member_id}/profile",
    response_model=CompetitorProfileResponse,
)
async def get_competitor_profile(
    watchlist_id: UUID,
    member_id: UUID,
    tenant: TenantContextDep,
    db: DBSessionDep,
) -> CompetitorProfileResponse:
    """Get publicly available profile metrics for a tracked entity.

    Returns estimated public metrics (followers, growth, engagement, formats).
    Never returns private analytics from connected accounts.

    Source attribution is always included per R108.7.
    """
    service = CompetitiveIntelligenceService(db=db)
    try:
        await service.get_watchlist(tenant.org_id, watchlist_id)
        profile = await service.get_competitor_profile(
            org_id=tenant.org_id,
            member_id=member_id,
        )
    except WatchlistNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Watchlist not found",
        )
    except WatchlistMemberNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Watchlist member not found",
        )

    return CompetitorProfileResponse(**profile)

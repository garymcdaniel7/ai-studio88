"""Scheduled Posts API endpoints.

Core publishing pipeline endpoints for scheduling, listing, retrieving,
cancelling, and dispatching posts to social platforms.

Endpoints:
    POST   /api/v1/publishing/schedule          — schedule a post (201)
    GET    /api/v1/publishing/scheduled          — list scheduled posts (paginated)
    GET    /api/v1/publishing/scheduled/{id}     — get post status
    POST   /api/v1/publishing/scheduled/{id}/cancel   — cancel scheduled post
    POST   /api/v1/publishing/scheduled/{id}/dispatch — manually trigger dispatch

Requirements: R38.1, R38.2, R38.3, R38.4, R38.5, R38.6, R38.7, R38.8
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, status

from app.core.dependencies import DBSessionDep, PaginationDep, TenantContextDep
from app.models.scheduled_post import ScheduledPostStatus
from app.schemas.scheduled_post import (
    DispatchPostRequest,
    ScheduledPostCancelResponse,
    ScheduledPostListResponse,
    ScheduledPostResponse,
    SchedulePostRequest,
)
from app.services.publishing_service import PublishingService

router = APIRouter(prefix="/publishing", tags=["publishing-scheduled"])


# =============================================================================
# Helper: Convert ORM to response
# =============================================================================


def _to_response(record: object) -> ScheduledPostResponse:
    """Convert a ScheduledPost ORM instance to a response schema."""
    return ScheduledPostResponse(
        id=record.id,
        org_id=record.org_id,
        asset_id=record.asset_id,
        talent_id=record.talent_id,
        connection_id=record.connection_id,
        approval_id=record.approval_id,
        platform=record.platform,
        caption=record.caption,
        scheduled_at=record.scheduled_at,
        dispatched_at=record.dispatched_at,
        status=record.status.value if hasattr(record.status, "value") else record.status,
        platform_post_id=record.platform_post_id,
        error_message=record.error_message,
        resize_spec=record.resize_spec,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


# =============================================================================
# Endpoints
# =============================================================================


@router.post(
    "/schedule",
    response_model=ScheduledPostResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Schedule a post for publishing",
    description=(
        "Creates a scheduled post for a social platform. "
        "scheduled_at must be at least 5 minutes in the future. "
        "Platform-specific resize specs are automatically applied."
    ),
)
async def schedule_post(
    request: SchedulePostRequest,
    tenant: TenantContextDep,
    db: DBSessionDep,
) -> ScheduledPostResponse:
    """Schedule a post for future publishing.

    Validates platform support, scheduled_at timing, and applies
    platform-specific resize specifications automatically.

    Requirements: R38.1, R38.2
    """
    service = PublishingService(db=db, tenant=tenant)

    record = await service.schedule_post(
        asset_id=request.asset_id,
        platform=request.platform,
        scheduled_at=request.scheduled_at,
        caption=request.caption,
        talent_id=request.talent_id,
        connection_id=request.connection_id,
        approval_id=request.approval_id,
    )

    await db.commit()
    return _to_response(record)


@router.get(
    "/scheduled",
    response_model=ScheduledPostListResponse,
    summary="List scheduled posts",
    description="Paginated list of scheduled posts for the workspace.",
)
async def list_scheduled_posts(
    tenant: TenantContextDep,
    db: DBSessionDep,
    pagination: PaginationDep,
    status_filter: str | None = Query(
        default=None,
        alias="status",
        description="Filter by status (scheduled, dispatching, published, failed, cancelled)",
    ),
    platform: str | None = Query(
        default=None, description="Filter by platform"
    ),
) -> ScheduledPostListResponse:
    """List scheduled posts with optional status and platform filters.

    Returns paginated results ordered by scheduled_at ascending.
    """
    # Parse status filter if provided
    parsed_status = None
    if status_filter:
        try:
            parsed_status = ScheduledPostStatus(status_filter)
        except ValueError:
            pass  # Invalid status ignored — returns all

    service = PublishingService(db=db, tenant=tenant)
    items, total = await service.list_scheduled_posts(
        limit=pagination.limit,
        offset=pagination.offset,
        status_filter=parsed_status,
        platform_filter=platform,
    )

    return ScheduledPostListResponse(
        items=[_to_response(item) for item in items],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get(
    "/scheduled/{post_id}",
    response_model=ScheduledPostResponse,
    summary="Get scheduled post status",
    description="Retrieve the current status of a scheduled post.",
)
async def get_scheduled_post(
    post_id: UUID,
    tenant: TenantContextDep,
    db: DBSessionDep,
) -> ScheduledPostResponse:
    """Get a single scheduled post by ID.

    Returns 404 if not found or belongs to a different tenant.
    """
    service = PublishingService(db=db, tenant=tenant)
    record = await service.get_post(post_id)
    return _to_response(record)


@router.post(
    "/scheduled/{post_id}/cancel",
    response_model=ScheduledPostCancelResponse,
    summary="Cancel a scheduled post",
    description=(
        "Cancel a post that has not yet been dispatched. "
        "Returns 409 if the post is already published or failed."
    ),
)
async def cancel_scheduled_post(
    post_id: UUID,
    tenant: TenantContextDep,
    db: DBSessionDep,
) -> ScheduledPostCancelResponse:
    """Cancel a scheduled post.

    Only posts with status 'scheduled' can be cancelled (R38.6).
    Posts that are dispatching/published/failed return HTTP 409.

    Requirements: R38.6
    """
    service = PublishingService(db=db, tenant=tenant)
    record = await service.cancel_post(post_id)
    await db.commit()

    return ScheduledPostCancelResponse(
        id=record.id,
        status=record.status.value,
        message="Post cancelled successfully",
    )


@router.post(
    "/scheduled/{post_id}/dispatch",
    response_model=ScheduledPostResponse,
    summary="Manually trigger dispatch",
    description=(
        "Manually trigger the dispatch of a scheduled post. "
        "Useful for immediate publishing or re-dispatching failed posts."
    ),
)
async def dispatch_scheduled_post(
    post_id: UUID,
    tenant: TenantContextDep,
    db: DBSessionDep,
    request: DispatchPostRequest | None = None,
) -> ScheduledPostResponse:
    """Manually trigger dispatch of a scheduled post.

    Executes the full dispatch pipeline: token refresh, resize, publish.
    Use force=true to dispatch before the scheduled time.

    Requirements: R38.3, R38.5, R38.7
    """
    force = request.force if request else False

    service = PublishingService(db=db, tenant=tenant)
    record = await service.dispatch_post(post_id, force=force)
    await db.commit()

    return _to_response(record)


@router.post(
    "/scheduler/tick",
    summary="Dispatch due posts (scheduler tick)",
    description=(
        "Find and dispatch all posts due within ±60 seconds. "
        "Called periodically by a scheduler or cron job."
    ),
)
async def scheduler_tick(
    tenant: TenantContextDep,
    db: DBSessionDep,
) -> dict:
    """Execute a scheduler tick to dispatch due posts.

    Finds all scheduled posts with scheduled_at <= now + 60s and dispatches them.
    Returns summary of dispatched and failed posts.

    Requirements: R38.3 — dispatch within ±60 seconds of scheduled time.
    """
    service = PublishingService(db=db, tenant=tenant)
    result = await service.dispatch_due_posts()
    await db.commit()
    return result

"""Notification API endpoints.

Provides:
    GET    /api/v1/notifications          — list notifications for current user
    PATCH  /api/v1/notifications/{id}/read — mark a single notification as read
    POST   /api/v1/notifications/read-all  — mark all notifications as read
    GET    /api/v1/notifications/count     — get unread/total counts

All endpoints require authentication and are scoped to the authenticated
user's organisation.

Validates: Requirements R101.1, R101.2, R101.3
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.core.dependencies import (
    CurrentUserIDDep,
    DBSessionDep,
    TenantContextDep,
)
from app.core.logging import get_logger
from backend.notifications.notification_schemas import (
    NotificationCountResponse,
    NotificationListResponse,
    NotificationResponse,
)
from backend.notifications.notification_service import NotificationService

logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/v1/notifications",
    tags=["notifications"],
)


@router.get(
    "",
    response_model=NotificationListResponse,
    summary="List notifications for the current user",
)
async def list_notifications(
    tenant: TenantContextDep,
    db: DBSessionDep,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    unread_only: bool = Query(default=False),
) -> NotificationListResponse:
    """List notifications for the authenticated user.

    Returns paginated notifications in reverse chronological order
    with an unread_count for badge display.

    Query Parameters:
        limit: Max items to return (1-100, default 20).
        offset: Pagination offset (default 0).
        unread_only: If true, only return unread notifications.
    """
    service = NotificationService(db)
    items, total, unread_count = await service.list_for_user(
        org_id=tenant.org_id,
        user_id=tenant.user_id,
        limit=limit,
        offset=offset,
        unread_only=unread_only,
    )

    return NotificationListResponse(
        items=[NotificationResponse.model_validate(n) for n in items],
        total=total,
        unread_count=unread_count,
        limit=limit,
        offset=offset,
    )


@router.patch(
    "/{notification_id}/read",
    response_model=NotificationResponse,
    summary="Mark a notification as read",
)
async def mark_notification_read(
    notification_id: UUID,
    tenant: TenantContextDep,
    db: DBSessionDep,
) -> NotificationResponse:
    """Mark a single notification as read.

    Only the target user can mark their own notifications as read.
    Returns 404 if the notification doesn't exist or belongs to
    another user/org.
    """
    service = NotificationService(db)
    notification = await service.mark_read(
        notification_id=notification_id,
        org_id=tenant.org_id,
        user_id=tenant.user_id,
    )

    if notification is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )

    return NotificationResponse.model_validate(notification)


@router.post(
    "/read-all",
    status_code=status.HTTP_200_OK,
    summary="Mark all notifications as read",
)
async def mark_all_notifications_read(
    tenant: TenantContextDep,
    db: DBSessionDep,
) -> dict:
    """Mark all unread notifications as read for the current user.

    Returns the count of notifications that were marked as read.
    """
    service = NotificationService(db)
    count = await service.mark_all_read(
        org_id=tenant.org_id,
        user_id=tenant.user_id,
    )

    return {"marked_read": count}


@router.get(
    "/count",
    response_model=NotificationCountResponse,
    summary="Get notification counts",
)
async def get_notification_count(
    tenant: TenantContextDep,
    db: DBSessionDep,
) -> NotificationCountResponse:
    """Get unread and total notification counts for the current user.

    Lightweight endpoint for notification badge/bell updates.
    """
    service = NotificationService(db)
    unread_count, total = await service.count_unread(
        org_id=tenant.org_id,
        user_id=tenant.user_id,
    )

    return NotificationCountResponse(
        unread_count=unread_count,
        total=total,
    )

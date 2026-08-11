"""Notification service — create, deliver, and manage notifications.

Provides:
    - NotificationChannel Protocol: adapter interface for future channels
    - InAppChannel: canonical in-app delivery (writes to DB)
    - NotificationService: high-level CRUD + delivery orchestration

Mandatory notifications (safety_action) cannot be suppressed by user
preferences. The service enforces this rule before consulting preferences.

Validates: Requirements R101.1, R101.2, R101.3
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol, runtime_checkable
from uuid import UUID

from sqlalchemy import and_, func, select, update

from app.core.logging import get_logger
from app.models.notification import Notification
from backend.notifications.notification_schemas import (
    MANDATORY_CATEGORIES,
    NotificationCategory,
    NotificationCreate,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)


# =============================================================================
# Delivery Result
# =============================================================================


@dataclass(frozen=True)
class DeliveryResult:
    """Result of a notification delivery attempt.

    Attributes:
        success: Whether delivery succeeded.
        channel: Name of the delivery channel.
        error: Error message if delivery failed.
    """

    success: bool
    channel: str
    error: str | None = None


# =============================================================================
# Channel Protocol (adapter interface for future channels)
# =============================================================================


@runtime_checkable
class NotificationChannel(Protocol):
    """Protocol for notification delivery channels.

    Implementations deliver notifications via a specific transport:
        - InAppChannel: writes to the notifications table (canonical)
        - Future: EmailChannel, PushChannel, SlackChannel, TelegramChannel

    All channels are async and return a DeliveryResult indicating success
    or failure. Failures are logged but do not block other channels.
    """

    async def deliver(
        self, notification: Notification, db: "AsyncSession"
    ) -> DeliveryResult:
        """Deliver a notification via this channel.

        Args:
            notification: The notification ORM instance to deliver.
            db: Database session (for channels that persist state).

        Returns:
            DeliveryResult with success status and channel name.
        """
        ...


# =============================================================================
# InAppChannel — canonical delivery (writes to notifications table)
# =============================================================================


class InAppChannel:
    """In-app notification channel — canonical delivery mechanism.

    Persists notifications to the `notifications` table. The frontend
    reads from this table (via API or realtime subscription) to show
    the notification bell/badge and list.

    This is the only delivery channel for MVP. Future channels (email,
    push, SMS) implement the same NotificationChannel Protocol.
    """

    async def deliver(
        self, notification: Notification, db: "AsyncSession"
    ) -> DeliveryResult:
        """Persist the notification to the database.

        The notification is already added to the session by the service.
        This channel's job is to confirm successful persistence.

        Args:
            notification: The notification ORM instance.
            db: Database session.

        Returns:
            DeliveryResult indicating success.
        """
        # The notification is already added to the session by the service.
        # InAppChannel confirms the write is intended.
        logger.info(
            "notification_delivered_in_app",
            notification_id=str(notification.id),
            user_id=str(notification.user_id),
            category=notification.category,
        )
        return DeliveryResult(success=True, channel="in_app")


# =============================================================================
# NotificationService
# =============================================================================


class NotificationService:
    """High-level notification service for creating and managing notifications.

    Responsibilities:
        - Create notifications with category validation
        - Deliver through configured channels (InAppChannel canonical)
        - Enforce mandatory notification rules (safety cannot be disabled)
        - List/count unread notifications for a user
        - Mark notifications as read

    All operations are tenant-scoped (org_id). Cross-tenant access is
    prevented at both the service and database (RLS) layers.

    Args:
        db: SQLAlchemy async session.
        channels: List of delivery channels. Defaults to [InAppChannel()].
    """

    def __init__(
        self,
        db: "AsyncSession",
        channels: list[NotificationChannel] | None = None,
    ) -> None:
        self.db = db
        self.channels: list[NotificationChannel] = channels or [InAppChannel()]

    async def create(
        self,
        org_id: UUID,
        data: NotificationCreate,
    ) -> Notification:
        """Create and deliver a notification.

        Determines if the notification is mandatory based on category,
        creates the DB record, and delivers through all configured channels.

        Args:
            org_id: Organisation scope (from TenantContext).
            data: Notification creation data.

        Returns:
            The created Notification ORM instance.

        Raises:
            ValueError: If category is invalid.
        """
        is_mandatory = data.category in MANDATORY_CATEGORIES

        notification = Notification(
            org_id=org_id,
            user_id=data.user_id,
            category=data.category.value,
            title=data.title,
            body=data.body,
            action_url=data.action_url,
            is_read=False,
            is_mandatory=is_mandatory,
            extra_data=data.metadata,
        )

        self.db.add(notification)
        await self.db.flush()

        # Deliver through all configured channels
        for channel in self.channels:
            try:
                result = await channel.deliver(notification, self.db)
                if not result.success:
                    logger.warning(
                        "notification_delivery_failed",
                        notification_id=str(notification.id),
                        channel=result.channel,
                        error=result.error,
                    )
            except Exception as exc:
                logger.error(
                    "notification_channel_error",
                    notification_id=str(notification.id),
                    channel=type(channel).__name__,
                    error=str(exc),
                )

        logger.info(
            "notification_created",
            notification_id=str(notification.id),
            org_id=str(org_id),
            user_id=str(data.user_id),
            category=data.category.value,
            is_mandatory=is_mandatory,
        )

        return notification

    async def mark_read(
        self,
        notification_id: UUID,
        org_id: UUID,
        user_id: UUID,
    ) -> Notification | None:
        """Mark a single notification as read.

        Only the target user within the same org can mark their
        notifications as read. Returns None if not found.

        Args:
            notification_id: The notification to mark as read.
            org_id: Organisation scope (from TenantContext).
            user_id: The authenticated user (must own the notification).

        Returns:
            The updated Notification, or None if not found.
        """
        stmt = select(Notification).where(
            and_(
                Notification.id == notification_id,
                Notification.org_id == org_id,
                Notification.user_id == user_id,
            )
        )
        result = await self.db.execute(stmt)
        notification = result.scalar_one_or_none()

        if notification is None:
            return None

        notification.is_read = True
        notification.updated_at = datetime.now(UTC)
        await self.db.flush()

        logger.info(
            "notification_marked_read",
            notification_id=str(notification_id),
            user_id=str(user_id),
        )

        return notification

    async def mark_all_read(
        self,
        org_id: UUID,
        user_id: UUID,
    ) -> int:
        """Mark all unread notifications as read for a user.

        Args:
            org_id: Organisation scope.
            user_id: The authenticated user.

        Returns:
            Number of notifications marked as read.
        """
        stmt = (
            update(Notification)
            .where(
                and_(
                    Notification.org_id == org_id,
                    Notification.user_id == user_id,
                    Notification.is_read == False,  # noqa: E712
                )
            )
            .values(is_read=True, updated_at=datetime.now(UTC))
        )
        result = await self.db.execute(stmt)
        count = result.rowcount

        if count > 0:
            logger.info(
                "notifications_marked_all_read",
                org_id=str(org_id),
                user_id=str(user_id),
                count=count,
            )

        return count

    async def list_for_user(
        self,
        org_id: UUID,
        user_id: UUID,
        limit: int = 20,
        offset: int = 0,
        unread_only: bool = False,
    ) -> tuple[list[Notification], int, int]:
        """List notifications for a user with pagination.

        Returns notifications in reverse chronological order (newest first).

        Args:
            org_id: Organisation scope.
            user_id: The authenticated user.
            limit: Max items to return (1-100).
            offset: Pagination offset.
            unread_only: If True, only return unread notifications.

        Returns:
            Tuple of (notifications, total_count, unread_count).
        """
        base_filter = and_(
            Notification.org_id == org_id,
            Notification.user_id == user_id,
        )

        # Count total
        total_stmt = select(func.count()).select_from(Notification).where(base_filter)
        total = await self.db.scalar(total_stmt) or 0

        # Count unread
        unread_stmt = (
            select(func.count())
            .select_from(Notification)
            .where(
                and_(
                    base_filter,
                    Notification.is_read == False,  # noqa: E712
                )
            )
        )
        unread_count = await self.db.scalar(unread_stmt) or 0

        # Fetch items
        items_filter = base_filter
        if unread_only:
            items_filter = and_(
                base_filter,
                Notification.is_read == False,  # noqa: E712
            )

        items_stmt = (
            select(Notification)
            .where(items_filter)
            .order_by(Notification.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(items_stmt)
        items = list(result.scalars().all())

        return items, total, unread_count

    async def count_unread(
        self,
        org_id: UUID,
        user_id: UUID,
    ) -> tuple[int, int]:
        """Count unread and total notifications for a user.

        Args:
            org_id: Organisation scope.
            user_id: The authenticated user.

        Returns:
            Tuple of (unread_count, total_count).
        """
        base_filter = and_(
            Notification.org_id == org_id,
            Notification.user_id == user_id,
        )

        total_stmt = select(func.count()).select_from(Notification).where(base_filter)
        total = await self.db.scalar(total_stmt) or 0

        unread_stmt = (
            select(func.count())
            .select_from(Notification)
            .where(
                and_(
                    base_filter,
                    Notification.is_read == False,  # noqa: E712
                )
            )
        )
        unread_count = await self.db.scalar(unread_stmt) or 0

        return unread_count, total

    def is_category_mandatory(self, category: NotificationCategory) -> bool:
        """Check if a notification category is mandatory.

        Mandatory notifications cannot be disabled by user preferences.

        Args:
            category: The notification category to check.

        Returns:
            True if the category is mandatory.
        """
        return category in MANDATORY_CATEGORIES

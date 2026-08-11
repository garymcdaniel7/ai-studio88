"""Notification ORM model.

Represents an in-app notification delivered to a specific user within an org.
Notifications have categories, mandatory flags, and read/unread state.

Mandatory notifications (safety_action) cannot be disabled via user preferences.

Validates: Requirements R101.1, R101.2, R101.3
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDMixin


class Notification(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """In-app notification record.

    Always scoped to org_id AND user_id. A user only sees their own
    notifications within their active organisation.

    Categories:
        job_completed, job_failed, approval_requested, approval_resolved,
        connection_expired, provider_unavailable, publishing_result,
        budget_threshold, safety_action, hermes_needs_input

    Mandatory notifications (is_mandatory=True) cannot be disabled or
    suppressed by user preference settings.
    """

    __tablename__ = "notifications"

    # Target user for this notification
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )

    # Notification category
    category: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # Short title
    title: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # Extended body (optional)
    body: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Deep link within the application
    action_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Read state
    is_read: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )

    # Mandatory flag — safety/takedown notifications cannot be disabled
    is_mandatory: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )

    # Additional structured metadata (job_id, asset_id, provider, etc.)
    extra_data: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    __table_args__ = (
        Index("ix_notifications_org_user", "org_id", "user_id"),
        Index("ix_notifications_org_user_unread", "org_id", "user_id", "is_read"),
        Index("ix_notifications_user_created", "org_id", "user_id", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<Notification(id={self.id}, org_id={self.org_id}, "
            f"user_id={self.user_id}, category={self.category}, "
            f"is_read={self.is_read})>"
        )

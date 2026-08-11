"""ScheduledPost ORM model.

Represents a post scheduled for publishing to a social platform.
Tracks lifecycle from scheduling → dispatch → published/failed/cancelled.

Bound to an approved publishing package via approval_id FK.
Platform-specific resize specs stored as JSONB for flexibility.

Requirements: R38.1, R38.2, R38.3, R38.4, R38.5, R38.6, R38.7, R38.8
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDMixin


class ScheduledPostStatus(str, enum.Enum):
    """Lifecycle states for a scheduled post."""

    SCHEDULED = "scheduled"
    DISPATCHING = "dispatching"
    PUBLISHED = "published"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ScheduledPost(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """A post scheduled for publishing to a social platform.

    Lifecycle:
        scheduled → dispatching → published
        scheduled → dispatching → failed
        scheduled → cancelled

    The resize_spec JSONB stores platform-specific dimensions applied
    before dispatch (e.g., {"width": 1080, "height": 1920, "aspect": "9:16"}).

    Requirements: R38.1, R38.2, R38.3, R38.4, R38.5, R38.6, R38.7, R38.8
    """

    __tablename__ = "scheduled_posts"

    # References
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    talent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    connection_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, doc="FK to social_connections or connections hub"
    )
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, doc="FK to publishing_approved_packages"
    )

    # Platform details
    platform: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )
    caption: Mapped[str] = mapped_column(
        Text, nullable=False, default=""
    )

    # Scheduling
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    dispatched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Status tracking
    status: Mapped[ScheduledPostStatus] = mapped_column(
        Enum(ScheduledPostStatus, name="scheduled_post_status", native_enum=False),
        nullable=False,
        default=ScheduledPostStatus.SCHEDULED,
        index=True,
    )

    # Platform result
    platform_post_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, doc="External post ID from the platform"
    )
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )

    # Resize configuration
    resize_spec: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, doc="Platform-specific resize dimensions"
    )

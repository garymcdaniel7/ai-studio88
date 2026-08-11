"""Feature Rollout ORM model.

Platform-level configuration table for feature rollout controls.
This table does NOT have org_id (not tenant-scoped) and does NOT have
RLS — it is a platform-level entity managed exclusively by Platform
Operators with Platform Configuration capability.

Validates: Requirements R106.1, R106.2, R106.3, R19.9, R19.10
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDMixin, TimestampMixin


class FeatureRollout(Base, UUIDMixin, TimestampMixin):
    """Feature rollout rule — controls capability availability per scope.

    Each row represents a single rollout rule that enables or disables
    a capability for a specific scope/target combination. Rules are
    evaluated in priority order: global first, then narrower scopes.

    Evaluation logic:
        1. Check global rules — if a global DISABLED rule exists, capability
           is blocked everywhere.
        2. Check narrower scopes (plan, workspace, cohort, user, workload,
           provider) — if a matching DISABLED rule exists for the context,
           capability is blocked for that context.
        3. Expired rules (expires_at < now()) are treated as inactive.

    NOT tenant-scoped — platform-level entity.
    """

    __tablename__ = "feature_rollouts"

    capability_name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        index=True,
        comment="Name of the capability being controlled",
    )
    rollout_scope: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Scope: global, plan, workspace, cohort, user, workload, provider",
    )
    scope_target: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Target identifier for the scope. NULL for global scope.",
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="true",
        comment="Whether the capability is enabled (true) or disabled (false)",
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When this rule expires. NULL = permanent until deleted.",
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        comment="User ID of the operator who created this rule",
    )

    def __repr__(self) -> str:
        return (
            f"<FeatureRollout(capability={self.capability_name!r}, "
            f"scope={self.rollout_scope!r}, target={self.scope_target!r}, "
            f"enabled={self.enabled})>"
        )

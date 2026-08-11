"""Compute Availability ORM models.

Platform-level configuration tables for compute availability state
management. These tables do NOT have org_id (not tenant-scoped) and
do NOT have RLS — they are platform-level entities managed exclusively
by Platform Operators with Founder Authority.

Validates: Requirements R86.1, R86.3, R86.5
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDMixin


class ComputeAvailabilityConfig(Base, UUIDMixin):
    """Compute availability state log — append-only history.

    Each row represents a state change. The latest row (by changed_at)
    is the current state. This supports audit trail and rollback.

    NOT tenant-scoped — platform-level entity.
    """

    __tablename__ = "compute_availability_config"

    state: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="disabled, selective, or enabled",
    )
    changed_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        comment="User ID of the operator who changed state",
    )
    reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Optional reason for the state change",
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class ComputeSelectiveGrant(Base, UUIDMixin):
    """Selective compute access grant.

    When compute availability is in SELECTIVE mode, these records
    determine which workspaces/plans/cohorts/workloads/providers
    are granted access to platform-managed compute.

    Grant types:
        - workspace: grant_target is an org_id UUID string
        - plan: grant_target is a plan name (e.g., 'pro', 'enterprise')
        - cohort: grant_target is a cohort identifier
        - workload: grant_target is a workload class name
        - provider: grant_target is a provider name
        - promotion: grant_target is a promotion identifier (time-limited)

    NOT tenant-scoped — platform-level entity.
    """

    __tablename__ = "compute_selective_grants"

    grant_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="workspace, plan, cohort, workload, provider, promotion",
    )
    grant_target: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Target identifier (org_id, plan_name, cohort_id, etc.)",
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="NULL = permanent until revoked",
    )
    granted_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        comment="User ID of the operator who created the grant",
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="NULL = active grant",
    )
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="User ID of the operator who revoked",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

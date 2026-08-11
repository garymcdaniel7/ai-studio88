"""Support Session ORM model.

Represents time-limited, scope-limited access sessions that Platform
Operators use to view or act on tenant workspace data for support purposes.

Session lifecycle: REQUESTED → APPROVED → ACTIVE → EXPIRED/ENDED/REVOKED

Key design constraints:
    - Auto-expires at expires_at — never becomes permanent membership
    - Revocable immediately by Founder or approving operator
    - Scope-limited: operator can only access permitted_surfaces and
      perform permitted_actions
    - Prefer operational metadata (job status, cost, config) over
      creative content (images, prompts, DNA)
    - Full audit trail via platform_operator_actions
    - Does NOT grant RLS bypass — queries filtered through
      support-session-scoped views

This is a PLATFORM-LEVEL entity — no TenantMixin. Access is restricted
to authenticated Platform Operators with tenant_access_escalation or
founder_authority capability.

Validates: Requirements R33.8, R33.9, R97.5, R97.6, A2-006
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class SupportSessionStatus(enum.StrEnum):
    """Support session lifecycle statuses.

    Flow: REQUESTED → APPROVED → ACTIVE → EXPIRED/COMPLETED/REVOKED
    """

    REQUESTED = "requested"
    APPROVED = "approved"
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    COMPLETED = "completed"


# Valid status transitions
VALID_STATUS_TRANSITIONS: dict[SupportSessionStatus, set[SupportSessionStatus]] = {
    SupportSessionStatus.REQUESTED: {
        SupportSessionStatus.APPROVED,
        SupportSessionStatus.REVOKED,
    },
    SupportSessionStatus.APPROVED: {
        SupportSessionStatus.ACTIVE,
        SupportSessionStatus.REVOKED,
    },
    SupportSessionStatus.ACTIVE: {
        SupportSessionStatus.EXPIRED,
        SupportSessionStatus.REVOKED,
        SupportSessionStatus.COMPLETED,
    },
    SupportSessionStatus.EXPIRED: set(),
    SupportSessionStatus.REVOKED: set(),
    SupportSessionStatus.COMPLETED: set(),
}


class SupportSession(Base, UUIDMixin, TimestampMixin):
    """Time-limited support session for Platform Operator tenant access.

    Platform Operators request elevated access to a specific workspace.
    Sessions are:
    - Time-limited (auto-expire at expires_at)
    - Scope-limited (permitted_surfaces + permitted_actions)
    - Fully auditable (all actions logged to platform_operator_actions)
    - Immediately revocable

    NOT tenant-scoped (no TenantMixin). Platform-level entity accessible
    only to Platform Operators with escalation capabilities.
    """

    __tablename__ = "support_sessions"

    operator_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        comment="Platform Operator requesting/holding the session",
    )

    target_org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        comment="Organization/workspace being accessed",
    )

    reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Documented reason for elevated access",
    )

    requested_capabilities: Mapped[list[str] | None] = mapped_column(
        ARRAY(Text),
        nullable=True,
        comment="Capabilities the operator asked for",
    )

    approved_capabilities: Mapped[list[str] | None] = mapped_column(
        ARRAY(Text),
        nullable=True,
        comment="Capabilities actually granted (may be subset)",
    )

    permitted_surfaces: Mapped[list[str] | None] = mapped_column(
        ARRAY(Text),
        nullable=True,
        comment="Data surfaces accessible: talent_metadata, job_history, cost_records, etc.",
    )

    permitted_actions: Mapped[list[str] | None] = mapped_column(
        ARRAY(Text),
        nullable=True,
        comment="Actions allowed: view, pause_job, revoke_connection, etc.",
    )

    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Operator who approved the escalation",
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="When the session was created/requested",
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Auto-expiration timestamp",
    )

    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Explicit early termination timestamp",
    )

    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="requested",
        comment="Session lifecycle status",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('requested', 'approved', 'active', 'expired', 'revoked', 'completed')",
            name="ck_support_sessions_status",
        ),
        Index("ix_support_sessions_operator", "operator_user_id"),
        Index("ix_support_sessions_org", "target_org_id"),
    )

    @property
    def is_terminal(self) -> bool:
        """Whether the session is in a terminal (non-modifiable) state."""
        return self.status in (
            SupportSessionStatus.EXPIRED.value,
            SupportSessionStatus.REVOKED.value,
            SupportSessionStatus.COMPLETED.value,
        )

    def can_transition_to(self, new_status: SupportSessionStatus) -> bool:
        """Check if a status transition is valid.

        Args:
            new_status: The desired target status.

        Returns:
            True if the transition is allowed.
        """
        try:
            current = SupportSessionStatus(self.status)
        except ValueError:
            return False
        return new_status in VALID_STATUS_TRANSITIONS.get(current, set())

    def __repr__(self) -> str:
        return (
            f"<SupportSession(id={self.id}, operator={self.operator_user_id}, "
            f"target_org={self.target_org_id}, status={self.status})>"
        )

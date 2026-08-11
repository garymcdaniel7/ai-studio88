"""RightsCase ORM model.

Represents a rights/takedown complaint case managed by Platform Operators.
Cases track the full lifecycle from intake through resolution, with CSAM
auto-escalation and legal hold support.

Case lifecycle:
    RECEIVED → TRIAGED → ACTION_REQUIRED/NO_ACTION →
    RESTRICTED/REMOVED/RESOLVED → CLOSED
    With APPEALED branch: APPEALED → RE_REVIEWED → CLOSED

Key design constraints:
    - Platform-level entity — NO TenantMixin (not tenant-scoped)
    - Access restricted to Platform Operators with safety_and_rights capability
    - CSAM cases auto-escalate to critical priority + immediate restriction
    - actions_taken is append-only JSONB for tamper-evident audit
    - Legal holds prevent permanent deletion of affected content

This is a PLATFORM-LEVEL entity. Access is via explicit privileged paths
with service-role queries, NOT tenant RLS.

Validates: Requirements R40.1, R40.2, R40.3, R40.4, R40.5, R40.7, R40.8,
           R40.9, A2-005
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, Index, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class RightsCaseType(enum.StrEnum):
    """Types of rights/takedown complaints."""

    COPYRIGHT = "copyright"
    TRADEMARK = "trademark"
    LIKENESS = "likeness"
    PRIVACY = "privacy"
    ILLEGAL = "illegal"
    CSAM = "csam"
    OTHER = "other"


class RightsCaseStatus(enum.StrEnum):
    """Rights case lifecycle statuses.

    Flow:
        RECEIVED → TRIAGED → ACTION_REQUIRED/NO_ACTION →
        RESTRICTED/REMOVED/RESOLVED → CLOSED
        APPEALED → RE_REVIEWED → CLOSED
    """

    RECEIVED = "received"
    TRIAGED = "triaged"
    ACTION_REQUIRED = "action_required"
    NO_ACTION = "no_action"
    RESTRICTED = "restricted"
    REMOVED = "removed"
    RESOLVED = "resolved"
    APPEALED = "appealed"
    RE_REVIEWED = "re_reviewed"
    CLOSED = "closed"


class RightsCasePriority(enum.StrEnum):
    """Priority levels for rights cases."""

    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


# Valid status transitions for the case lifecycle
VALID_STATUS_TRANSITIONS: dict[RightsCaseStatus, set[RightsCaseStatus]] = {
    RightsCaseStatus.RECEIVED: {
        RightsCaseStatus.TRIAGED,
    },
    RightsCaseStatus.TRIAGED: {
        RightsCaseStatus.ACTION_REQUIRED,
        RightsCaseStatus.NO_ACTION,
    },
    RightsCaseStatus.ACTION_REQUIRED: {
        RightsCaseStatus.RESTRICTED,
        RightsCaseStatus.REMOVED,
        RightsCaseStatus.RESOLVED,
    },
    RightsCaseStatus.NO_ACTION: {
        RightsCaseStatus.CLOSED,
    },
    RightsCaseStatus.RESTRICTED: {
        RightsCaseStatus.CLOSED,
        RightsCaseStatus.APPEALED,
    },
    RightsCaseStatus.REMOVED: {
        RightsCaseStatus.CLOSED,
        RightsCaseStatus.APPEALED,
    },
    RightsCaseStatus.RESOLVED: {
        RightsCaseStatus.CLOSED,
        RightsCaseStatus.APPEALED,
    },
    RightsCaseStatus.APPEALED: {
        RightsCaseStatus.RE_REVIEWED,
    },
    RightsCaseStatus.RE_REVIEWED: {
        RightsCaseStatus.CLOSED,
        RightsCaseStatus.RESTRICTED,
        RightsCaseStatus.REMOVED,
        RightsCaseStatus.RESOLVED,
    },
    RightsCaseStatus.CLOSED: set(),
}


class RightsCase(Base, UUIDMixin, TimestampMixin):
    """A rights/takedown complaint case.

    Platform Operators manage cases through the lifecycle: receiving
    reports, triaging, taking action (restrict/remove), and resolving.

    NOT tenant-scoped (no TenantMixin). Platform-level entity accessible
    only to Platform Operators with safety_and_rights capability.

    CSAM cases auto-escalate to critical priority and trigger immediate
    content restriction.
    """

    __tablename__ = "rights_cases"

    case_type: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="copyright, trademark, likeness, privacy, illegal, csam, other",
    )

    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="received",
        comment="Case lifecycle status",
    )

    priority: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="normal",
        comment="critical, high, normal, low",
    )

    reporter_contact: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Reporter email, name (encrypted at rest)",
    )

    target_org_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Workspace containing reported content",
    )

    target_talent_ids: Mapped[list[uuid.UUID] | None] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=True,
        comment="Talent IDs referenced in the complaint",
    )

    target_asset_ids: Mapped[list[uuid.UUID] | None] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=True,
        comment="Asset IDs referenced in the complaint",
    )

    reported_urls: Mapped[list[str] | None] = mapped_column(
        ARRAY(Text),
        nullable=True,
        comment="URLs reported in the complaint",
    )

    evidence_refs: Mapped[list[dict]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="'[]'::jsonb",
        comment="References to stored evidence documents",
    )

    assigned_operator: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Platform Operator handling this case",
    )

    actions_taken: Mapped[list[dict]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="'[]'::jsonb",
        comment="Append-only audit trail of actions taken",
    )

    resolution: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Final resolution description",
    )

    appeal_state: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Appeal metadata if case was appealed",
    )

    legal_hold_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
        comment="Prevents permanent deletion of affected content",
    )

    __table_args__ = (
        CheckConstraint(
            "case_type IN ('copyright', 'trademark', 'likeness', 'privacy', "
            "'illegal', 'csam', 'other')",
            name="ck_rights_cases_case_type",
        ),
        CheckConstraint(
            "status IN ('received', 'triaged', 'action_required', 'no_action', "
            "'restricted', 'removed', 'resolved', 'appealed', 're_reviewed', 'closed')",
            name="ck_rights_cases_status",
        ),
        CheckConstraint(
            "priority IN ('critical', 'high', 'normal', 'low')",
            name="ck_rights_cases_priority",
        ),
        Index("ix_rights_cases_status", "status"),
        Index("ix_rights_cases_org", "target_org_id"),
        Index("ix_rights_cases_priority", "priority", "status"),
    )

    @property
    def is_terminal(self) -> bool:
        """Whether the case is in a terminal (closed) state."""
        return self.status == RightsCaseStatus.CLOSED.value

    def can_transition_to(self, new_status: RightsCaseStatus) -> bool:
        """Check if a status transition is valid.

        Args:
            new_status: The desired target status.

        Returns:
            True if the transition is allowed.
        """
        try:
            current = RightsCaseStatus(self.status)
        except ValueError:
            return False
        return new_status in VALID_STATUS_TRANSITIONS.get(current, set())

    def __repr__(self) -> str:
        return (
            f"<RightsCase(id={self.id}, case_type={self.case_type}, "
            f"status={self.status}, priority={self.priority})>"
        )

"""Agent Activity ORM model — user-facing activity feed.

Records what Brain/Hermes did on behalf of the user in human-readable form.
This is separate from engineering/debug logs and system observability data.

Activity types:
    - recommendation: Brain suggested an action
    - tool_call: A tool was invoked via MCP/Hermes
    - job_dispatch: A GPU job or background task was dispatched
    - approval_request: An approval was requested from the user
    - connection_use: An external connection was used
    - change_made: A mutation was applied to user data
    - failure: An action failed
    - cost_incurred: Cost was charged for an operation

Validates: Requirements R99.1, R99.2, R99.3, R99.4, R30.15
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, Index, Numeric, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, UUIDMixin


class ActivityType(str, enum.Enum):
    """Types of agent activity recorded in the feed.

    Each type corresponds to a category of action that Brain/Hermes
    performed or attempted on behalf of the user.
    """

    RECOMMENDATION = "recommendation"
    TOOL_CALL = "tool_call"
    JOB_DISPATCH = "job_dispatch"
    APPROVAL_REQUEST = "approval_request"
    CONNECTION_USE = "connection_use"
    CHANGE_MADE = "change_made"
    FAILURE = "failure"
    COST_INCURRED = "cost_incurred"


class AgentActivity(Base, UUIDMixin, TenantMixin):
    """User-facing record of what Brain/Hermes did on their behalf.

    Each entry answers "What did Brain/Hermes do?" in plain language.
    Scoped to (org_id, user_id) — users only see their own activity
    unless workspace policy explicitly shares it (R99.3).

    Separate from platform_operator_actions (which are audit/engineering records)
    and from system logs (which are debug/observability). This is the
    human-readable activity feed (R99.2).
    """

    __tablename__ = "agent_activity"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    activity_type: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    detail: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    outcome: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    cost_usd: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=10, scale=4),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "activity_type IN ("
            "'recommendation', 'tool_call', 'job_dispatch', "
            "'approval_request', 'connection_use', 'change_made', "
            "'failure', 'cost_incurred'"
            ")",
            name="ck_agent_activity_type",
        ),
        Index(
            "ix_agent_activity_org_user_created",
            "org_id",
            "user_id",
            text("created_at DESC"),
        ),
        Index(
            "ix_agent_activity_org_type",
            "org_id",
            "activity_type",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<AgentActivity(id={self.id}, org_id={self.org_id}, "
            f"user_id={self.user_id}, type={self.activity_type}, "
            f"outcome={self.outcome})>"
        )

"""Agent Activity Service — user-facing activity feed management.

Records and retrieves human-readable activity entries showing what
Brain/Hermes did on behalf of the user. This service is separate from
engineering/debug logs and system observability (R99.2).

All operations are tenant-isolated (org_id) and user-scoped (user_id).
Users only see their own activity unless workspace policy explicitly
shares it (R99.3).

Validates: Requirements R99.1, R99.2, R99.3, R99.4, R30.15
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_activity import ActivityType, AgentActivity

logger = structlog.get_logger(__name__)


# =============================================================================
# Exceptions
# =============================================================================


class AgentActivityServiceError(Exception):
    """Base exception for AgentActivityService operations."""

    def __init__(self, message: str, code: str = "ACTIVITY_ERROR") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class InvalidActivityTypeError(AgentActivityServiceError):
    """Raised when an activity type is not in the valid set."""

    def __init__(self, activity_type: str) -> None:
        valid = [t.value for t in ActivityType]
        super().__init__(
            message=(
                f"Invalid activity_type '{activity_type}'. "
                f"Valid values: {valid}"
            ),
            code="INVALID_ACTIVITY_TYPE",
        )


# =============================================================================
# Service
# =============================================================================


VALID_ACTIVITY_TYPES: frozenset[str] = frozenset(t.value for t in ActivityType)


class AgentActivityService:
    """Service for recording and querying user-facing agent activity.

    All methods enforce tenant isolation via org_id and scope activity
    to the requesting user_id.

    Methods:
        log_activity: Record a new activity entry
        list_activity: Paginated list filtered to user's activity

    Requirements covered: R99.1, R99.2, R99.3, R99.4, R30.15
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialize with an async database session.

        Args:
            db: SQLAlchemy async session (injected via Depends).
        """
        self.db = db

    async def log_activity(
        self,
        org_id: UUID,
        user_id: UUID,
        activity_type: str,
        summary: str,
        session_id: UUID | None = None,
        detail: dict[str, Any] | None = None,
        outcome: str | None = None,
        cost_usd: Decimal | float | None = None,
    ) -> AgentActivity:
        """Record a new agent activity entry.

        This is the primary write method. Called by Brain/Hermes/AIOS
        whenever an action is performed on behalf of the user.

        Args:
            org_id: Organization scope (tenant isolation).
            user_id: User on whose behalf the activity occurred.
            activity_type: One of the valid ActivityType values.
            summary: Human-readable description of what happened.
            session_id: Optional Brain conversation session ID.
            detail: Optional structured JSONB detail about the activity.
            outcome: Optional outcome (success, failure, pending).
            cost_usd: Optional cost incurred for this activity.

        Returns:
            The created AgentActivity record.

        Raises:
            InvalidActivityTypeError: If activity_type is not valid.
        """
        if activity_type not in VALID_ACTIVITY_TYPES:
            raise InvalidActivityTypeError(activity_type)

        # Convert float to Decimal if needed
        cost_decimal: Decimal | None = None
        if cost_usd is not None:
            cost_decimal = (
                Decimal(str(cost_usd))
                if not isinstance(cost_usd, Decimal)
                else cost_usd
            )

        activity = AgentActivity(
            org_id=org_id,
            user_id=user_id,
            session_id=session_id,
            activity_type=activity_type,
            summary=summary,
            detail=detail,
            outcome=outcome,
            cost_usd=cost_decimal,
        )

        self.db.add(activity)
        await self.db.flush()

        logger.info(
            "agent_activity_logged",
            activity_id=str(activity.id),
            org_id=str(org_id),
            user_id=str(user_id),
            activity_type=activity_type,
            outcome=outcome,
        )

        return activity

    async def list_activity(
        self,
        org_id: UUID,
        user_id: UUID,
        limit: int = 20,
        offset: int = 0,
        activity_type: str | None = None,
    ) -> tuple[list[AgentActivity], int]:
        """List agent activity for the authenticated user (paginated).

        Always scoped to (org_id, user_id) per R99.3. Results are
        returned newest-first (created_at DESC).

        Args:
            org_id: Organization scope (from JWT).
            user_id: User whose activity to list (from JWT).
            limit: Maximum items to return (1-100, default 20).
            offset: Pagination offset (default 0).
            activity_type: Optional filter by activity type.

        Returns:
            Tuple of (list of AgentActivity records, total count).

        Raises:
            InvalidActivityTypeError: If activity_type filter is not valid.
        """
        if activity_type is not None and activity_type not in VALID_ACTIVITY_TYPES:
            raise InvalidActivityTypeError(activity_type)

        # Base filter: tenant + user isolation
        base_filter = [
            AgentActivity.org_id == org_id,
            AgentActivity.user_id == user_id,
        ]

        if activity_type is not None:
            base_filter.append(AgentActivity.activity_type == activity_type)

        # Count query
        count_stmt = select(func.count()).select_from(AgentActivity).where(*base_filter)
        total = await self.db.scalar(count_stmt) or 0

        # Data query
        stmt = (
            select(AgentActivity)
            .where(*base_filter)
            .order_by(AgentActivity.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(stmt)
        items = list(result.scalars().all())

        return items, total

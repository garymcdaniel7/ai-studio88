"""Support Session Service — time-limited tenant access for Platform Operators.

Manages the lifecycle of support sessions: requesting, approving,
revoking, validity checking, and scope enforcement.

Key design constraints:
    - Sessions auto-expire at expires_at (configurable max 4 hours)
    - Revocable immediately by Founder or approving operator
    - Scope-limited: operator can only access permitted_surfaces
      and perform permitted_actions
    - Full audit trail: all actions logged to platform_operator_actions
    - Does NOT grant RLS bypass

Session lifecycle: REQUESTED → APPROVED → ACTIVE → EXPIRED/COMPLETED/REVOKED

Validates: Requirements R33.8, R33.9, R97.5, R97.6, A2-006
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.platform_operator import CapabilityGroup
from app.models.support_session import (
    SupportSession,
    SupportSessionStatus,
    VALID_STATUS_TRANSITIONS,
)

logger = get_logger(__name__)

# Default maximum session duration (4 hours)
DEFAULT_MAX_DURATION_MINUTES = 240

# Default session duration if not specified
DEFAULT_DURATION_MINUTES = 60


# =============================================================================
# Exceptions
# =============================================================================


class SupportSessionError(Exception):
    """Base exception for SupportSessionService operations."""

    def __init__(self, message: str, code: str = "SUPPORT_SESSION_ERROR") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class SessionNotFoundError(SupportSessionError):
    """Raised when a support session is not found."""

    def __init__(self, session_id: UUID) -> None:
        super().__init__(
            message=f"Support session not found: {session_id}",
            code="SESSION_NOT_FOUND",
        )


class SessionExpiredError(SupportSessionError):
    """Raised when attempting to use an expired session."""

    def __init__(self, session_id: UUID) -> None:
        super().__init__(
            message=f"Support session has expired: {session_id}",
            code="SUPPORT_SESSION_EXPIRED",
        )


class InvalidTransitionError(SupportSessionError):
    """Raised when an invalid status transition is attempted."""

    def __init__(
        self, session_id: UUID, current_status: str, target_status: str,
    ) -> None:
        super().__init__(
            message=(
                f"Cannot transition session {session_id} "
                f"from '{current_status}' to '{target_status}'"
            ),
            code="INVALID_SESSION_TRANSITION",
        )


class SessionNotActiveError(SupportSessionError):
    """Raised when an operation requires an active session but it is not."""

    def __init__(self, session_id: UUID, current_status: str) -> None:
        super().__init__(
            message=(
                f"Support session {session_id} is not active "
                f"(current status: {current_status})"
            ),
            code="SESSION_NOT_ACTIVE",
        )


class ScopeViolationError(SupportSessionError):
    """Raised when an action or surface access violates session scope."""

    def __init__(
        self,
        session_id: UUID,
        violation_type: str,
        attempted: str,
        permitted: list[str],
    ) -> None:
        super().__init__(
            message=(
                f"Scope violation on session {session_id}: "
                f"attempted {violation_type} '{attempted}' not in permitted "
                f"set {permitted}"
            ),
            code="SESSION_SCOPE_VIOLATION",
        )


# =============================================================================
# Service
# =============================================================================


class SupportSessionService:
    """Service for managing Platform Operator support sessions.

    Handles the full lifecycle: request, approve, activate, revoke,
    complete, and validity/scope checks.

    All state-changing methods also log audit actions via the platform
    operator actions table (caller is responsible for passing the
    PlatformOperatorService to log_action).

    Args:
        db: SQLAlchemy async session.

    Validates: R33.8, R33.9, R97.5, R97.6, A2-006
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # =========================================================================
    # Create / Request
    # =========================================================================

    async def request_session(
        self,
        operator_user_id: UUID,
        target_org_id: UUID,
        reason: str,
        requested_capabilities: list[str] | None = None,
        permitted_surfaces: list[str] | None = None,
        permitted_actions: list[str] | None = None,
        duration_minutes: int = DEFAULT_DURATION_MINUTES,
    ) -> SupportSession:
        """Request a new support session for a target workspace.

        Creates a session in REQUESTED status. The session must be
        approved before it can be used.

        Args:
            operator_user_id: The Platform Operator requesting access.
            target_org_id: The target workspace/organization.
            reason: Documented reason for access (min 10 chars).
            requested_capabilities: Capabilities needed.
            permitted_surfaces: Data surfaces to access.
            permitted_actions: Actions to perform.
            duration_minutes: Requested duration (5-240 minutes).

        Returns:
            The created SupportSession in REQUESTED status.
        """
        # Clamp duration to maximum
        duration_minutes = max(5, min(duration_minutes, DEFAULT_MAX_DURATION_MINUTES))

        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=duration_minutes)

        session = SupportSession(
            operator_user_id=operator_user_id,
            target_org_id=target_org_id,
            reason=reason,
            requested_capabilities=requested_capabilities,
            permitted_surfaces=permitted_surfaces,
            permitted_actions=permitted_actions,
            started_at=now,
            expires_at=expires_at,
            status=SupportSessionStatus.REQUESTED.value,
        )
        self._db.add(session)
        await self._db.flush()

        logger.info(
            "support_session_requested",
            session_id=str(session.id),
            operator_user_id=str(operator_user_id),
            target_org_id=str(target_org_id),
            duration_minutes=duration_minutes,
        )

        return session

    # =========================================================================
    # Approve
    # =========================================================================

    async def approve_session(
        self,
        session_id: UUID,
        approved_by: UUID,
        approved_capabilities: list[str] | None = None,
        permitted_surfaces: list[str] | None = None,
        permitted_actions: list[str] | None = None,
    ) -> SupportSession:
        """Approve a pending support session and transition to ACTIVE.

        The approver may restrict the granted capabilities, surfaces,
        and actions to a subset of what was requested.

        Args:
            session_id: The session to approve.
            approved_by: The operator approving (must have escalation cap).
            approved_capabilities: Capabilities to grant (None = all requested).
            permitted_surfaces: Override surfaces (None = use requested).
            permitted_actions: Override actions (None = use requested).

        Returns:
            The approved and activated SupportSession.

        Raises:
            SessionNotFoundError: If session does not exist.
            InvalidTransitionError: If session is not in REQUESTED status.
        """
        session = await self.get_session(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)

        if not session.can_transition_to(SupportSessionStatus.APPROVED):
            raise InvalidTransitionError(
                session_id, session.status, SupportSessionStatus.APPROVED.value,
            )

        # Set approved capabilities (may be subset of requested)
        session.approved_by = approved_by
        session.approved_capabilities = (
            approved_capabilities
            if approved_capabilities is not None
            else session.requested_capabilities
        )

        # Override surfaces/actions if approver specifies restrictions
        if permitted_surfaces is not None:
            session.permitted_surfaces = permitted_surfaces
        if permitted_actions is not None:
            session.permitted_actions = permitted_actions

        # Transition directly to ACTIVE (approved + active in one step)
        session.status = SupportSessionStatus.ACTIVE.value
        await self._db.flush()

        logger.info(
            "support_session_approved",
            session_id=str(session_id),
            approved_by=str(approved_by),
            approved_capabilities=session.approved_capabilities,
            permitted_surfaces=session.permitted_surfaces,
            permitted_actions=session.permitted_actions,
        )

        return session

    # =========================================================================
    # Revoke / End
    # =========================================================================

    async def revoke_session(
        self,
        session_id: UUID,
        revoked_by: UUID,
        reason: str = "",
    ) -> SupportSession:
        """Immediately revoke a support session.

        Can be called on any non-terminal session (REQUESTED, APPROVED,
        or ACTIVE). Takes effect immediately.

        Args:
            session_id: The session to revoke.
            revoked_by: The operator revoking (Founder or approving operator).
            reason: Optional reason for revocation.

        Returns:
            The revoked SupportSession.

        Raises:
            SessionNotFoundError: If session does not exist.
            InvalidTransitionError: If session is already terminal.
        """
        session = await self.get_session(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)

        if not session.can_transition_to(SupportSessionStatus.REVOKED):
            raise InvalidTransitionError(
                session_id, session.status, SupportSessionStatus.REVOKED.value,
            )

        session.status = SupportSessionStatus.REVOKED.value
        session.ended_at = datetime.now(UTC)
        await self._db.flush()

        logger.info(
            "support_session_revoked",
            session_id=str(session_id),
            revoked_by=str(revoked_by),
            reason=reason,
        )

        return session

    async def complete_session(
        self,
        session_id: UUID,
    ) -> SupportSession:
        """Mark an active session as completed by the operator.

        Called when the operator finishes their support work and
        voluntarily ends the session.

        Args:
            session_id: The session to complete.

        Returns:
            The completed SupportSession.

        Raises:
            SessionNotFoundError: If session does not exist.
            InvalidTransitionError: If session is not ACTIVE.
        """
        session = await self.get_session(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)

        if not session.can_transition_to(SupportSessionStatus.COMPLETED):
            raise InvalidTransitionError(
                session_id, session.status, SupportSessionStatus.COMPLETED.value,
            )

        session.status = SupportSessionStatus.COMPLETED.value
        session.ended_at = datetime.now(UTC)
        await self._db.flush()

        logger.info(
            "support_session_completed",
            session_id=str(session_id),
            operator_user_id=str(session.operator_user_id),
        )

        return session

    # =========================================================================
    # Validity and Scope Checks
    # =========================================================================

    async def check_session_valid(self, session_id: UUID) -> bool:
        """Check if a support session is currently valid.

        A session is valid if:
        - It exists
        - Its status is ACTIVE
        - It has not passed expires_at

        If the session has expired but status is still ACTIVE,
        this method will auto-transition it to EXPIRED.

        Args:
            session_id: The session to check.

        Returns:
            True if the session is active and not expired.
        """
        session = await self.get_session(session_id)
        if session is None:
            return False

        if session.status != SupportSessionStatus.ACTIVE.value:
            return False

        # Auto-expire check
        now = datetime.now(UTC)
        if now >= session.expires_at:
            session.status = SupportSessionStatus.EXPIRED.value
            session.ended_at = now
            await self._db.flush()

            logger.info(
                "support_session_auto_expired",
                session_id=str(session_id),
                expires_at=session.expires_at.isoformat(),
            )
            return False

        return True

    async def get_permitted_scope(
        self, session_id: UUID,
    ) -> tuple[list[str], list[str]] | None:
        """Get the permitted surfaces and actions for a session.

        Only returns scope for sessions that are currently valid
        (ACTIVE and not expired).

        Args:
            session_id: The session to check.

        Returns:
            Tuple of (permitted_surfaces, permitted_actions) if valid,
            None if the session is invalid/expired.
        """
        is_valid = await self.check_session_valid(session_id)
        if not is_valid:
            return None

        session = await self.get_session(session_id)
        if session is None:
            return None

        surfaces = session.permitted_surfaces or []
        actions = session.permitted_actions or []
        return surfaces, actions

    def check_surface_permitted(
        self,
        session: SupportSession,
        surface: str,
    ) -> bool:
        """Check if a specific data surface is permitted in the session.

        Args:
            session: The support session to check.
            surface: The data surface being accessed.

        Returns:
            True if permitted, False if not.
        """
        if session.permitted_surfaces is None:
            # If no surfaces specified, nothing is permitted
            return False
        return surface in session.permitted_surfaces

    def check_action_permitted(
        self,
        session: SupportSession,
        action: str,
    ) -> bool:
        """Check if a specific action is permitted in the session.

        Args:
            session: The support session to check.
            action: The action being attempted.

        Returns:
            True if permitted, False if not.
        """
        if session.permitted_actions is None:
            # If no actions specified, nothing is permitted
            return False
        return action in session.permitted_actions

    # =========================================================================
    # Query
    # =========================================================================

    async def get_session(self, session_id: UUID) -> SupportSession | None:
        """Get a support session by its primary key.

        Args:
            session_id: The support_sessions.id.

        Returns:
            The SupportSession or None if not found.
        """
        stmt = select(SupportSession).where(SupportSession.id == session_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_sessions(
        self,
        limit: int = 20,
        offset: int = 0,
        operator_user_id: UUID | None = None,
        target_org_id: UUID | None = None,
        status: str | None = None,
    ) -> tuple[list[SupportSession], int]:
        """List support sessions with optional filters.

        Args:
            limit: Max items to return (1-100, default 20).
            offset: Pagination offset.
            operator_user_id: Filter by requesting operator.
            target_org_id: Filter by target organization.
            status: Filter by session status.

        Returns:
            Tuple of (session list, total count).
        """
        limit = max(1, min(limit, 100))
        offset = max(0, offset)

        filters = []
        if operator_user_id is not None:
            filters.append(SupportSession.operator_user_id == operator_user_id)
        if target_org_id is not None:
            filters.append(SupportSession.target_org_id == target_org_id)
        if status is not None:
            filters.append(SupportSession.status == status)

        # Count
        count_stmt = (
            select(func.count())
            .select_from(SupportSession)
            .where(*filters)
        )
        total = await self._db.scalar(count_stmt) or 0

        # Items
        stmt = (
            select(SupportSession)
            .where(*filters)
            .order_by(SupportSession.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._db.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    async def get_active_sessions_for_operator(
        self, operator_user_id: UUID,
    ) -> list[SupportSession]:
        """Get all active sessions for a specific operator.

        Includes auto-expiry check — sessions past expires_at will
        be transitioned to EXPIRED.

        Args:
            operator_user_id: The operator to query.

        Returns:
            List of currently active (non-expired) sessions.
        """
        stmt = select(SupportSession).where(
            and_(
                SupportSession.operator_user_id == operator_user_id,
                SupportSession.status == SupportSessionStatus.ACTIVE.value,
            )
        )
        result = await self._db.execute(stmt)
        sessions = list(result.scalars().all())

        # Auto-expire any that have passed their expiration
        now = datetime.now(UTC)
        active_sessions = []
        for session in sessions:
            if now >= session.expires_at:
                session.status = SupportSessionStatus.EXPIRED.value
                session.ended_at = now
                logger.info(
                    "support_session_auto_expired",
                    session_id=str(session.id),
                )
            else:
                active_sessions.append(session)

        if len(active_sessions) != len(sessions):
            await self._db.flush()

        return active_sessions

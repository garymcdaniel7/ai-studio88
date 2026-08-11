"""Platform Operator Service — capability-based operator management.

Manages Platform Operator lifecycle: granting capabilities, revoking
access, checking capabilities, and logging all operator actions.

Key design constraints:
    - Platform-level (no org_id scoping on operators themselves)
    - Only one active operator record per user (partial unique index)
    - Founder Authority implicitly includes all capabilities
    - ALL actions are logged with full audit trail
    - Revoking creates a historical record (never deletes)

Validates: Requirements R33.5, R33.6, R33.7, R33.9, R97.1-R97.6
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.platform_operator import (
    CapabilityGroup,
    PlatformOperator,
    PlatformOperatorAction,
)

logger = get_logger(__name__)


# =============================================================================
# Exceptions
# =============================================================================


class PlatformOperatorError(Exception):
    """Base exception for PlatformOperatorService operations."""

    def __init__(self, message: str, code: str = "OPERATOR_ERROR") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class OperatorNotFoundError(PlatformOperatorError):
    """Raised when an operator record is not found."""

    def __init__(self, identifier: str) -> None:
        super().__init__(
            message=f"Platform operator not found: {identifier}",
            code="OPERATOR_NOT_FOUND",
        )


class OperatorAlreadyExistsError(PlatformOperatorError):
    """Raised when a user already has an active operator record."""

    def __init__(self, user_id: UUID) -> None:
        super().__init__(
            message=(
                f"User {user_id} already has an active operator record. "
                "Revoke existing access before granting new capabilities."
            ),
            code="OPERATOR_ALREADY_EXISTS",
        )


class InvalidCapabilityError(PlatformOperatorError):
    """Raised when an invalid capability is referenced."""

    def __init__(self, capability: str) -> None:
        valid = [c.value for c in CapabilityGroup]
        super().__init__(
            message=(
                f"Invalid capability group: '{capability}'. "
                f"Valid groups: {valid}"
            ),
            code="INVALID_CAPABILITY",
        )


class InsufficientCapabilityError(PlatformOperatorError):
    """Raised when an operator lacks the required capability."""

    def __init__(self, required: str, operator_user_id: UUID) -> None:
        super().__init__(
            message=(
                f"Operator {operator_user_id} lacks required capability: "
                f"'{required}'"
            ),
            code="INSUFFICIENT_CAPABILITY",
        )


# =============================================================================
# Service
# =============================================================================


class PlatformOperatorService:
    """Service for managing Platform Operator capability grants and actions.

    All methods that modify state also log an audit action. The service
    does NOT perform authentication — callers must verify the requesting
    user is an authenticated operator with appropriate grants.

    Args:
        db: SQLAlchemy async session.

    Validates: R33.5, R33.6, R33.7, R33.9, R97.1-R97.6
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # =========================================================================
    # Grant / Revoke
    # =========================================================================

    async def grant_capabilities(
        self,
        user_id: UUID,
        capability_grants: list[str],
        granted_by: UUID,
    ) -> PlatformOperator:
        """Grant Platform Operator capabilities to a user.

        Creates a new operator record. Only one active record per user
        is allowed (enforced by partial unique index).

        Args:
            user_id: The user to grant capabilities to.
            capability_grants: List of capability group names.
            granted_by: The operator (typically Founder) granting access.

        Returns:
            The created PlatformOperator record.

        Raises:
            OperatorAlreadyExistsError: If user already has active grant.
            InvalidCapabilityError: If any capability name is invalid.
        """
        # Validate all capability names
        valid_capabilities = {c.value for c in CapabilityGroup}
        for cap in capability_grants:
            if cap not in valid_capabilities:
                raise InvalidCapabilityError(cap)

        # Check for existing active operator record
        existing = await self._get_active_operator_by_user(user_id)
        if existing is not None:
            raise OperatorAlreadyExistsError(user_id)

        operator = PlatformOperator(
            user_id=user_id,
            capability_grants=capability_grants,
            granted_by=granted_by,
            granted_at=datetime.now(UTC),
        )
        self._db.add(operator)

        try:
            await self._db.flush()
        except IntegrityError as exc:
            await self._db.rollback()
            raise OperatorAlreadyExistsError(user_id) from exc

        # Log the grant action
        await self.log_action(
            operator_user_id=granted_by,
            capability_used=CapabilityGroup.FOUNDER_AUTHORITY.value,
            action_type="grant_capabilities",
            action_detail={
                "target_user_id": str(user_id),
                "capabilities_granted": capability_grants,
            },
        )

        logger.info(
            "platform_operator_granted",
            user_id=str(user_id),
            capabilities=capability_grants,
            granted_by=str(granted_by),
        )

        return operator

    async def revoke(
        self,
        operator_id: UUID,
        revoked_by: UUID,
    ) -> PlatformOperator:
        """Revoke an operator's capabilities by setting revoked_at.

        The operator record is NOT deleted — it becomes a historical
        record with revoked_at timestamp for audit purposes.

        Args:
            operator_id: The platform_operators.id to revoke.
            revoked_by: The operator performing the revocation.

        Returns:
            The revoked PlatformOperator record.

        Raises:
            OperatorNotFoundError: If operator record not found.
        """
        operator = await self.get_operator(operator_id)
        if operator is None:
            raise OperatorNotFoundError(str(operator_id))

        if operator.revoked_at is not None:
            raise PlatformOperatorError(
                message=f"Operator {operator_id} is already revoked",
                code="OPERATOR_ALREADY_REVOKED",
            )

        operator.revoked_at = datetime.now(UTC)
        await self._db.flush()

        # Log the revocation action
        await self.log_action(
            operator_user_id=revoked_by,
            capability_used=CapabilityGroup.FOUNDER_AUTHORITY.value,
            action_type="revoke_capabilities",
            action_detail={
                "target_operator_id": str(operator_id),
                "target_user_id": str(operator.user_id),
                "revoked_capabilities": operator.capability_grants,
            },
        )

        logger.info(
            "platform_operator_revoked",
            operator_id=str(operator_id),
            user_id=str(operator.user_id),
            revoked_by=str(revoked_by),
        )

        return operator

    # =========================================================================
    # Query
    # =========================================================================

    async def get_operator(self, operator_id: UUID) -> PlatformOperator | None:
        """Get a Platform Operator record by its primary key.

        Args:
            operator_id: The platform_operators.id.

        Returns:
            The PlatformOperator or None if not found.
        """
        stmt = select(PlatformOperator).where(PlatformOperator.id == operator_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_operator_by_user(self, user_id: UUID) -> PlatformOperator | None:
        """Get the active (non-revoked) operator record for a user.

        Args:
            user_id: The user to look up.

        Returns:
            The active PlatformOperator or None if user is not an operator.
        """
        return await self._get_active_operator_by_user(user_id)

    async def list_operators(
        self,
        limit: int = 20,
        offset: int = 0,
        include_revoked: bool = False,
    ) -> tuple[list[PlatformOperator], int]:
        """List Platform Operators with pagination.

        Args:
            limit: Max items to return (1-100, default 20).
            offset: Pagination offset.
            include_revoked: If True, include revoked operator records.

        Returns:
            Tuple of (operator list, total count).
        """
        limit = max(1, min(limit, 100))
        offset = max(0, offset)

        base_filter = []
        if not include_revoked:
            base_filter.append(PlatformOperator.revoked_at.is_(None))

        # Count
        count_stmt = (
            select(func.count())
            .select_from(PlatformOperator)
            .where(*base_filter)
        )
        total = await self._db.scalar(count_stmt) or 0

        # Items
        stmt = (
            select(PlatformOperator)
            .where(*base_filter)
            .order_by(PlatformOperator.granted_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._db.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    # =========================================================================
    # Capability Checking
    # =========================================================================

    async def check_capability(
        self,
        user_id: UUID,
        required_capability: str,
    ) -> bool:
        """Check if a user has a specific Platform Operator capability.

        Founder Authority implicitly includes all capabilities.

        Args:
            user_id: The user to check.
            required_capability: The capability group name required.

        Returns:
            True if the user has the capability (directly or via Founder).
        """
        operator = await self._get_active_operator_by_user(user_id)
        if operator is None:
            return False
        return operator.has_capability(required_capability)

    # =========================================================================
    # Audit Logging
    # =========================================================================

    async def log_action(
        self,
        operator_user_id: UUID,
        capability_used: str,
        action_type: str,
        target_org_id: UUID | None = None,
        action_detail: dict | None = None,
    ) -> PlatformOperatorAction:
        """Log a Platform Operator action to the audit trail.

        Every operator action MUST be logged per R33.9 and R97.6.
        This method is append-only — records are never updated or deleted.

        Args:
            operator_user_id: The operator who performed the action.
            capability_used: Which capability group authorized it.
            action_type: Type of action performed.
            target_org_id: Target tenant (if tenant-scoped action).
            action_detail: Structured detail about the action.

        Returns:
            The created PlatformOperatorAction record.
        """
        action = PlatformOperatorAction(
            operator_user_id=operator_user_id,
            capability_used=capability_used,
            target_org_id=target_org_id,
            action_type=action_type,
            action_detail=action_detail,
        )
        self._db.add(action)
        await self._db.flush()

        logger.info(
            "platform_operator_action_logged",
            operator_user_id=str(operator_user_id),
            capability_used=capability_used,
            action_type=action_type,
            target_org_id=str(target_org_id) if target_org_id else None,
        )

        return action

    # =========================================================================
    # Internal Helpers
    # =========================================================================

    async def _get_active_operator_by_user(
        self, user_id: UUID,
    ) -> PlatformOperator | None:
        """Get the active (non-revoked) operator for a user.

        Uses the partial unique index guarantee: at most one active
        record per user_id.
        """
        stmt = select(PlatformOperator).where(
            and_(
                PlatformOperator.user_id == user_id,
                PlatformOperator.revoked_at.is_(None),
            )
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

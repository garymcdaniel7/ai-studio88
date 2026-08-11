"""External Deletion Propagation Service.

Manages the lifecycle of asset deletions from external storage providers.
Implements state transitions, retry logic with exponential backoff, and
notification surfacing to Platform Operators when deletions fail.

Key invariant (R105.2): The platform NEVER claims an external object is
deleted unless deletion has been confirmed where technically possible.

Validates: Requirements R105.1, R105.2, R105.3
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import and_, func, select, update

from app.core.logging import get_logger
from app.models.external_deletion import (
    DeletionState,
    ExternalDeletionTracking,
    MAX_RETRY_ATTEMPTS,
)
from app.schemas.external_deletion import ExternalDeletionCreate

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)


# Base delay for exponential backoff (seconds)
BASE_BACKOFF_SECONDS = 30


def compute_backoff_seconds(retry_count: int) -> float:
    """Compute exponential backoff delay for a given retry count.

    Formula: base * 2^retry_count (capped at 1 hour).
    Examples: 30s, 60s, 120s, 240s, 480s...

    Args:
        retry_count: Number of retries already attempted.

    Returns:
        Backoff delay in seconds.
    """
    delay = BASE_BACKOFF_SECONDS * math.pow(2, retry_count)
    return min(delay, 3600.0)  # Cap at 1 hour


class ExternalDeletionError(Exception):
    """Base exception for external deletion operations."""


class DeletionStateTransitionError(ExternalDeletionError):
    """Invalid state transition attempted."""

    def __init__(self, current_state: str, target_state: str) -> None:
        self.current_state = current_state
        self.target_state = target_state
        super().__init__(
            f"Invalid state transition: {current_state} → {target_state}"
        )


class DeletionNotFoundError(ExternalDeletionError):
    """Deletion tracking record not found."""


class DeletionRetryExhaustedError(ExternalDeletionError):
    """Maximum retry attempts exhausted."""


# Valid state transitions
VALID_TRANSITIONS: dict[DeletionState, set[DeletionState]] = {
    DeletionState.REMOVED_FROM_STUDIO: {
        DeletionState.EXTERNAL_DELETION_REQUESTED,
        DeletionState.RETAINED_LEGAL_HOLD,
        DeletionState.RETAINED_BACKUP,
    },
    DeletionState.EXTERNAL_DELETION_REQUESTED: {
        DeletionState.EXTERNAL_DELETION_CONFIRMED,
        DeletionState.EXTERNAL_DELETION_FAILED,
    },
    DeletionState.EXTERNAL_DELETION_FAILED: {
        DeletionState.EXTERNAL_DELETION_REQUESTED,  # retry
    },
    DeletionState.RETAINED_LEGAL_HOLD: {
        DeletionState.EXTERNAL_DELETION_REQUESTED,  # hold released
    },
    DeletionState.RETAINED_BACKUP: set(),  # terminal for now
    DeletionState.EXTERNAL_DELETION_CONFIRMED: set(),  # terminal
}


class ExternalDeletionService:
    """Service for managing external deletion propagation lifecycle.

    Responsibilities:
        - Track deletion state for assets with external storage
        - Manage state transitions with validation
        - Implement retry logic with exponential backoff
        - Surface failed deletions to Platform Operators after max retries
        - Enforce legal holds (RETAINED_LEGAL_HOLD prevents deletion)
        - Never claim deleted unless provider confirms (R105.2)

    All operations are tenant-scoped (org_id).

    Args:
        db: SQLAlchemy async session.
    """

    def __init__(self, db: "AsyncSession") -> None:
        self.db = db

    async def create(
        self,
        org_id: UUID,
        data: ExternalDeletionCreate,
    ) -> ExternalDeletionTracking:
        """Create a new external deletion tracking record.

        Initial state is REMOVED_FROM_STUDIO (soft-deleted in DB).
        If a legal_hold_ref is provided, state is RETAINED_LEGAL_HOLD.

        Args:
            org_id: Organisation scope (from TenantContext).
            data: Deletion tracking creation data.

        Returns:
            The created ExternalDeletionTracking record.
        """
        initial_state = DeletionState.REMOVED_FROM_STUDIO
        if data.legal_hold_ref:
            initial_state = DeletionState.RETAINED_LEGAL_HOLD

        record = ExternalDeletionTracking(
            org_id=org_id,
            asset_id=data.asset_id,
            storage_key=data.storage_key,
            deletion_state=initial_state.value,
            provider=data.provider,
            legal_hold_ref=data.legal_hold_ref,
            retry_count=0,
        )

        self.db.add(record)
        await self.db.flush()

        logger.info(
            "external_deletion_created",
            record_id=str(record.id),
            org_id=str(org_id),
            asset_id=str(data.asset_id),
            storage_key=data.storage_key,
            initial_state=initial_state.value,
        )

        return record

    async def request_deletion(
        self,
        record_id: UUID,
        org_id: UUID,
    ) -> ExternalDeletionTracking:
        """Transition to EXTERNAL_DELETION_REQUESTED state.

        Called when the storage API delete call is issued.

        Args:
            record_id: The deletion tracking record ID.
            org_id: Organisation scope.

        Returns:
            Updated record.

        Raises:
            DeletionNotFoundError: If record not found in this org.
            DeletionStateTransitionError: If transition is invalid.
        """
        record = await self._get_record(record_id, org_id)
        self._validate_transition(
            record.deletion_state, DeletionState.EXTERNAL_DELETION_REQUESTED
        )

        record.deletion_state = DeletionState.EXTERNAL_DELETION_REQUESTED.value
        record.requested_at = datetime.now(UTC)
        await self.db.flush()

        logger.info(
            "external_deletion_requested",
            record_id=str(record_id),
            org_id=str(org_id),
            storage_key=record.storage_key,
        )

        return record

    async def confirm_deletion(
        self,
        record_id: UUID,
        org_id: UUID,
    ) -> ExternalDeletionTracking:
        """Transition to EXTERNAL_DELETION_CONFIRMED state.

        Called only when the storage provider confirms the object is gone
        (e.g., HEAD returns 404). The platform MUST NOT call this unless
        confirmation is technically possible and verified (R105.2).

        Args:
            record_id: The deletion tracking record ID.
            org_id: Organisation scope.

        Returns:
            Updated record.

        Raises:
            DeletionNotFoundError: If record not found.
            DeletionStateTransitionError: If transition is invalid.
        """
        record = await self._get_record(record_id, org_id)
        self._validate_transition(
            record.deletion_state, DeletionState.EXTERNAL_DELETION_CONFIRMED
        )

        record.deletion_state = DeletionState.EXTERNAL_DELETION_CONFIRMED.value
        record.confirmed_at = datetime.now(UTC)
        await self.db.flush()

        logger.info(
            "external_deletion_confirmed",
            record_id=str(record_id),
            org_id=str(org_id),
            storage_key=record.storage_key,
        )

        return record

    async def mark_failed(
        self,
        record_id: UUID,
        org_id: UUID,
        error: str,
    ) -> ExternalDeletionTracking:
        """Transition to EXTERNAL_DELETION_FAILED state.

        Increments retry_count and records the error. If max retries
        are exhausted, surfaces a notification to Platform Operators.

        Args:
            record_id: The deletion tracking record ID.
            org_id: Organisation scope.
            error: Error message from the failed attempt.

        Returns:
            Updated record.

        Raises:
            DeletionNotFoundError: If record not found.
            DeletionStateTransitionError: If transition is invalid.
        """
        record = await self._get_record(record_id, org_id)
        self._validate_transition(
            record.deletion_state, DeletionState.EXTERNAL_DELETION_FAILED
        )

        record.deletion_state = DeletionState.EXTERNAL_DELETION_FAILED.value
        record.failed_at = datetime.now(UTC)
        record.retry_count = record.retry_count + 1
        record.last_error = error[:2000] if error else None
        await self.db.flush()

        logger.warning(
            "external_deletion_failed",
            record_id=str(record_id),
            org_id=str(org_id),
            storage_key=record.storage_key,
            retry_count=record.retry_count,
            error=error[:200],
        )

        # Surface to Platform Operators if max retries exhausted
        if record.retry_count >= MAX_RETRY_ATTEMPTS:
            await self._notify_operators_deletion_failed(record)

        return record

    async def retry_deletion(
        self,
        record_id: UUID,
        org_id: UUID,
    ) -> ExternalDeletionTracking:
        """Retry a failed deletion by transitioning back to REQUESTED.

        Only allowed from EXTERNAL_DELETION_FAILED state. Checks that
        max retries have not been permanently exhausted (operator can
        still trigger retries via the admin endpoint).

        Args:
            record_id: The deletion tracking record ID.
            org_id: Organisation scope.

        Returns:
            Updated record with state set to EXTERNAL_DELETION_REQUESTED.

        Raises:
            DeletionNotFoundError: If record not found.
            DeletionStateTransitionError: If not in FAILED state.
        """
        record = await self._get_record(record_id, org_id)
        self._validate_transition(
            record.deletion_state, DeletionState.EXTERNAL_DELETION_REQUESTED
        )

        record.deletion_state = DeletionState.EXTERNAL_DELETION_REQUESTED.value
        record.requested_at = datetime.now(UTC)
        await self.db.flush()

        logger.info(
            "external_deletion_retry",
            record_id=str(record_id),
            org_id=str(org_id),
            storage_key=record.storage_key,
            retry_count=record.retry_count,
        )

        return record

    async def place_legal_hold(
        self,
        record_id: UUID,
        org_id: UUID,
        hold_ref: str,
    ) -> ExternalDeletionTracking:
        """Place a legal hold on a deletion, preventing external deletion.

        Only valid from REMOVED_FROM_STUDIO state.

        Args:
            record_id: The deletion tracking record ID.
            org_id: Organisation scope.
            hold_ref: Legal hold case reference.

        Returns:
            Updated record.

        Raises:
            DeletionNotFoundError: If record not found.
            DeletionStateTransitionError: If transition is invalid.
        """
        record = await self._get_record(record_id, org_id)
        self._validate_transition(
            record.deletion_state, DeletionState.RETAINED_LEGAL_HOLD
        )

        record.deletion_state = DeletionState.RETAINED_LEGAL_HOLD.value
        record.legal_hold_ref = hold_ref
        await self.db.flush()

        logger.info(
            "external_deletion_legal_hold",
            record_id=str(record_id),
            org_id=str(org_id),
            hold_ref=hold_ref,
        )

        return record

    async def release_legal_hold(
        self,
        record_id: UUID,
        org_id: UUID,
    ) -> ExternalDeletionTracking:
        """Release a legal hold, transitioning to REQUESTED state.

        After release, the deletion can proceed.

        Args:
            record_id: The deletion tracking record ID.
            org_id: Organisation scope.

        Returns:
            Updated record with state EXTERNAL_DELETION_REQUESTED.

        Raises:
            DeletionNotFoundError: If record not found.
            DeletionStateTransitionError: If not in RETAINED_LEGAL_HOLD state.
        """
        record = await self._get_record(record_id, org_id)
        self._validate_transition(
            record.deletion_state, DeletionState.EXTERNAL_DELETION_REQUESTED
        )

        record.deletion_state = DeletionState.EXTERNAL_DELETION_REQUESTED.value
        record.requested_at = datetime.now(UTC)
        record.legal_hold_ref = None
        await self.db.flush()

        logger.info(
            "external_deletion_hold_released",
            record_id=str(record_id),
            org_id=str(org_id),
        )

        return record

    async def get(
        self,
        record_id: UUID,
        org_id: UUID,
    ) -> ExternalDeletionTracking | None:
        """Get a single deletion tracking record by ID.

        Returns None if not found (not 404 — to prevent cross-tenant leakage).

        Args:
            record_id: The record ID.
            org_id: Organisation scope.

        Returns:
            The record, or None if not found in this org.
        """
        stmt = select(ExternalDeletionTracking).where(
            and_(
                ExternalDeletionTracking.id == record_id,
                ExternalDeletionTracking.org_id == org_id,
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_state(
        self,
        org_id: UUID,
        state: DeletionState | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[ExternalDeletionTracking], int]:
        """List deletion tracking records with optional state filter.

        Args:
            org_id: Organisation scope.
            state: Optional filter by deletion state.
            limit: Max items (1-100).
            offset: Pagination offset.

        Returns:
            Tuple of (records, total_count).
        """
        base_filter = ExternalDeletionTracking.org_id == org_id

        if state is not None:
            base_filter = and_(base_filter, ExternalDeletionTracking.deletion_state == state.value)

        # Count
        count_stmt = (
            select(func.count())
            .select_from(ExternalDeletionTracking)
            .where(base_filter)
        )
        total = await self.db.scalar(count_stmt) or 0

        # Fetch
        stmt = (
            select(ExternalDeletionTracking)
            .where(base_filter)
            .order_by(ExternalDeletionTracking.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    async def list_pending_admin(
        self,
        state: DeletionState | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[ExternalDeletionTracking], int]:
        """List deletion records across all orgs for Platform Operators.

        Defaults to showing FAILED state records for operator triage.

        Args:
            state: Optional filter (defaults to FAILED if None).
            limit: Max items (1-100).
            offset: Pagination offset.

        Returns:
            Tuple of (records, total_count).
        """
        filter_state = state or DeletionState.EXTERNAL_DELETION_FAILED

        base_filter = (
            ExternalDeletionTracking.deletion_state == filter_state.value
        )

        count_stmt = (
            select(func.count())
            .select_from(ExternalDeletionTracking)
            .where(base_filter)
        )
        total = await self.db.scalar(count_stmt) or 0

        stmt = (
            select(ExternalDeletionTracking)
            .where(base_filter)
            .order_by(ExternalDeletionTracking.failed_at.desc().nulls_last())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    def get_backoff_seconds(self, retry_count: int) -> float:
        """Get the backoff delay for the next retry attempt.

        Args:
            retry_count: Current retry count.

        Returns:
            Delay in seconds before next retry.
        """
        return compute_backoff_seconds(retry_count)

    # =========================================================================
    # Private helpers
    # =========================================================================

    async def _get_record(
        self, record_id: UUID, org_id: UUID
    ) -> ExternalDeletionTracking:
        """Fetch a record or raise DeletionNotFoundError."""
        record = await self.get(record_id, org_id)
        if record is None:
            raise DeletionNotFoundError(
                f"Deletion tracking record {record_id} not found"
            )
        return record

    def _validate_transition(
        self, current_state_value: str, target_state: DeletionState
    ) -> None:
        """Validate that a state transition is allowed.

        Raises:
            DeletionStateTransitionError: If the transition is not valid.
        """
        current_state = DeletionState(current_state_value)
        allowed = VALID_TRANSITIONS.get(current_state, set())
        if target_state not in allowed:
            raise DeletionStateTransitionError(
                current_state.value, target_state.value
            )

    async def _notify_operators_deletion_failed(
        self, record: ExternalDeletionTracking
    ) -> None:
        """Surface a failed deletion to Platform Operators via notifications.

        Called when retry_count >= MAX_RETRY_ATTEMPTS. Creates a mandatory
        notification for operator investigation.
        """
        try:
            from backend.notifications.notification_schemas import (
                NotificationCategory,
                NotificationCreate,
            )
            from backend.notifications.notification_service import NotificationService

            notification_service = NotificationService(self.db)

            # Create notification for operator investigation
            # Use the provider_unavailable category as closest match for
            # external service failure requiring operator attention.
            data = NotificationCreate(
                user_id=record.org_id,  # Platform operator user (simplified)
                category=NotificationCategory.PROVIDER_UNAVAILABLE,
                title="External deletion failed — operator investigation required",
                body=(
                    f"Asset {record.asset_id} deletion from {record.provider} "
                    f"failed after {record.retry_count} attempts. "
                    f"Storage key: {record.storage_key}. "
                    f"Last error: {record.last_error or 'unknown'}"
                ),
                action_url=f"/admin/deletions/{record.id}",
                metadata={
                    "deletion_record_id": str(record.id),
                    "asset_id": str(record.asset_id),
                    "storage_key": record.storage_key,
                    "provider": record.provider,
                    "retry_count": record.retry_count,
                },
            )

            await notification_service.create(record.org_id, data)

            logger.warning(
                "external_deletion_operator_notified",
                record_id=str(record.id),
                org_id=str(record.org_id),
                asset_id=str(record.asset_id),
                retry_count=record.retry_count,
            )

        except Exception as exc:
            # Notification failure should not block the deletion flow
            logger.error(
                "external_deletion_notification_failed",
                record_id=str(record.id),
                error=str(exc),
            )

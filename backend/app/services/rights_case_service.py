"""Rights Case Service — takedown and rights complaint case management.

Manages the full lifecycle of rights/takedown cases: intake, triage,
action, resolution, appeal, and closure.

Key design constraints:
    - CSAM cases auto-escalate to critical priority + immediate restriction
    - actions_taken is append-only (tamper-evident audit trail)
    - Legal holds prevent permanent deletion of affected content
    - Platform-level entity — no tenant RLS, operator access only
    - Case status transitions follow defined lifecycle graph

Case lifecycle:
    RECEIVED → TRIAGED → ACTION_REQUIRED/NO_ACTION →
    RESTRICTED/REMOVED/RESOLVED → CLOSED
    With APPEALED branch: APPEALED → RE_REVIEWED → CLOSED

Validates: Requirements R40.1, R40.2, R40.3, R40.4, R40.5, R40.7, R40.8,
           R40.9, A2-005
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.rights_case import (
    RightsCase,
    RightsCasePriority,
    RightsCaseStatus,
    RightsCaseType,
    VALID_STATUS_TRANSITIONS,
)

logger = get_logger(__name__)


# =============================================================================
# Exceptions
# =============================================================================


class RightsCaseError(Exception):
    """Base exception for RightsCaseService operations."""

    def __init__(self, message: str, code: str = "RIGHTS_CASE_ERROR") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class CaseNotFoundError(RightsCaseError):
    """Raised when a rights case is not found."""

    def __init__(self, case_id: UUID) -> None:
        super().__init__(
            message=f"Rights case not found: {case_id}",
            code="CASE_NOT_FOUND",
        )


class InvalidCaseTransitionError(RightsCaseError):
    """Raised when an invalid status transition is attempted."""

    def __init__(
        self, case_id: UUID, current_status: str, target_status: str,
    ) -> None:
        super().__init__(
            message=(
                f"Cannot transition case {case_id} "
                f"from '{current_status}' to '{target_status}'"
            ),
            code="INVALID_CASE_TRANSITION",
        )


class CaseClosedError(RightsCaseError):
    """Raised when attempting to modify a closed case."""

    def __init__(self, case_id: UUID) -> None:
        super().__init__(
            message=f"Rights case {case_id} is closed and cannot be modified",
            code="CASE_CLOSED",
        )


# =============================================================================
# Service
# =============================================================================


class RightsCaseService:
    """Service for managing rights/takedown complaint cases.

    Handles the full lifecycle: intake, triage, action, resolution,
    appeal, and closure. Includes CSAM auto-escalation logic.

    Args:
        db: SQLAlchemy async session.

    Validates: R40.1, R40.2, R40.3, R40.4, R40.5, R40.7, R40.8, R40.9, A2-005
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # =========================================================================
    # Intake (Public)
    # =========================================================================

    async def create_case(
        self,
        case_type: str,
        reporter_contact: dict | None = None,
        content_url_or_id: str | None = None,
        description: str | None = None,
        evidence_urls: list[str] | None = None,
        target_org_id: UUID | None = None,
        target_talent_ids: list[UUID] | None = None,
        target_asset_ids: list[UUID] | None = None,
    ) -> RightsCase:
        """Create a new rights/takedown case from an incoming report.

        If the case_type is 'csam', auto-escalates to critical priority
        and sets status to 'action_required' (bypassing normal triage).

        Args:
            case_type: Type of complaint (copyright, trademark, etc.).
            reporter_contact: Reporter email/name JSON.
            content_url_or_id: URL or asset ID of reported content.
            description: Description of the complaint.
            evidence_urls: Optional list of evidence URLs.
            target_org_id: Workspace containing reported content.
            target_talent_ids: Talent IDs referenced.
            target_asset_ids: Asset IDs referenced.

        Returns:
            The created RightsCase with status 'received' (or escalated).
        """
        # Build reported_urls from content_url_or_id + evidence
        reported_urls: list[str] = []
        if content_url_or_id:
            reported_urls.append(content_url_or_id)

        # Build evidence_refs from evidence_urls
        evidence_refs: list[dict] = []
        if evidence_urls:
            for url in evidence_urls:
                evidence_refs.append({
                    "url": url,
                    "submitted_at": datetime.now(UTC).isoformat(),
                    "type": "reporter_submitted",
                })

        # Determine initial status and priority
        is_csam = case_type == RightsCaseType.CSAM.value
        initial_status = (
            RightsCaseStatus.ACTION_REQUIRED.value
            if is_csam
            else RightsCaseStatus.RECEIVED.value
        )
        initial_priority = (
            RightsCasePriority.CRITICAL.value
            if is_csam
            else RightsCasePriority.NORMAL.value
        )

        # Build initial actions_taken entry
        actions_taken: list[dict] = [{
            "action_type": "case_created",
            "actor": "system",
            "timestamp": datetime.now(UTC).isoformat(),
            "description": description or "",
        }]

        if is_csam:
            actions_taken.append({
                "action_type": "csam_auto_escalation",
                "actor": "system",
                "timestamp": datetime.now(UTC).isoformat(),
                "description": (
                    "CSAM case auto-escalated to critical priority "
                    "and immediate action_required status"
                ),
            })

        case = RightsCase(
            case_type=case_type,
            status=initial_status,
            priority=initial_priority,
            reporter_contact=reporter_contact,
            target_org_id=target_org_id,
            target_talent_ids=target_talent_ids,
            target_asset_ids=target_asset_ids,
            reported_urls=reported_urls if reported_urls else None,
            evidence_refs=evidence_refs,
            actions_taken=actions_taken,
            legal_hold_active=is_csam,  # CSAM cases get immediate legal hold
        )

        self._db.add(case)
        await self._db.flush()

        logger.info(
            "rights_case_created",
            case_id=str(case.id),
            case_type=case_type,
            priority=initial_priority,
            csam_escalated=is_csam,
        )

        return case

    # =========================================================================
    # Update (Platform Operator)
    # =========================================================================

    async def update_case(
        self,
        case_id: UUID,
        operator_id: UUID,
        status: str | None = None,
        priority: str | None = None,
        assigned_operator: UUID | None = None,
        resolution: str | None = None,
        legal_hold_active: bool | None = None,
        action_note: str | None = None,
    ) -> RightsCase:
        """Update a rights case (Platform Operator action).

        Validates status transitions, appends to actions_taken audit trail,
        and enforces the case lifecycle.

        Args:
            case_id: The case to update.
            operator_id: The Platform Operator performing the update.
            status: New status (validated transition).
            priority: New priority level.
            assigned_operator: Assign to an operator.
            resolution: Resolution description.
            legal_hold_active: Enable/disable legal hold.
            action_note: Note to append to actions_taken.

        Returns:
            The updated RightsCase.

        Raises:
            CaseNotFoundError: If case does not exist.
            CaseClosedError: If case is already closed.
            InvalidCaseTransitionError: If status transition is invalid.
        """
        case = await self.get_case(case_id)
        if case is None:
            raise CaseNotFoundError(case_id)

        if case.is_terminal:
            raise CaseClosedError(case_id)

        # Build the action record for audit trail
        action_record: dict = {
            "actor": str(operator_id),
            "timestamp": datetime.now(UTC).isoformat(),
        }

        # Validate and apply status transition
        if status is not None:
            target_status = RightsCaseStatus(status)
            if not case.can_transition_to(target_status):
                raise InvalidCaseTransitionError(
                    case_id, case.status, status,
                )
            action_record["action_type"] = "status_change"
            action_record["prior_status"] = case.status
            action_record["new_status"] = status
            case.status = status

        # Apply priority change
        if priority is not None:
            action_record.setdefault("action_type", "update")
            action_record["prior_priority"] = case.priority
            action_record["new_priority"] = priority
            case.priority = priority

        # Apply assignment
        if assigned_operator is not None:
            action_record.setdefault("action_type", "assignment")
            action_record["assigned_to"] = str(assigned_operator)
            case.assigned_operator = assigned_operator

        # Apply resolution
        if resolution is not None:
            action_record.setdefault("action_type", "resolution_set")
            case.resolution = resolution

        # Apply legal hold change
        if legal_hold_active is not None:
            action_record.setdefault("action_type", "legal_hold_change")
            action_record["legal_hold_active"] = legal_hold_active
            case.legal_hold_active = legal_hold_active

        # Add optional action note
        if action_note:
            action_record["note"] = action_note

        # Ensure action_type is set
        action_record.setdefault("action_type", "update")

        # Append to actions_taken (append-only audit trail per R40.9)
        current_actions = list(case.actions_taken) if case.actions_taken else []
        current_actions.append(action_record)
        case.actions_taken = current_actions

        await self._db.flush()

        logger.info(
            "rights_case_updated",
            case_id=str(case_id),
            operator_id=str(operator_id),
            action_type=action_record.get("action_type"),
            new_status=status,
        )

        return case

    # =========================================================================
    # Appeal
    # =========================================================================

    async def submit_appeal(
        self,
        case_id: UUID,
        appellant_email: str,
        reason: str,
        evidence_urls: list[str] | None = None,
    ) -> RightsCase:
        """Submit an appeal for a rights case (R40.7).

        Can only appeal cases that are in RESTRICTED, REMOVED, or RESOLVED
        status (cases where action was taken).

        Args:
            case_id: The case to appeal.
            appellant_email: Appellant's contact email.
            reason: Reason for the appeal.
            evidence_urls: Optional supporting evidence.

        Returns:
            The updated RightsCase with APPEALED status.

        Raises:
            CaseNotFoundError: If case does not exist.
            InvalidCaseTransitionError: If case cannot be appealed.
        """
        case = await self.get_case(case_id)
        if case is None:
            raise CaseNotFoundError(case_id)

        target_status = RightsCaseStatus.APPEALED
        if not case.can_transition_to(target_status):
            raise InvalidCaseTransitionError(
                case_id, case.status, target_status.value,
            )

        # Build appeal action record
        appeal_record: dict = {
            "action_type": "appeal_submitted",
            "actor": "appellant",
            "timestamp": datetime.now(UTC).isoformat(),
            "appellant_email": appellant_email,
            "reason": reason,
        }
        if evidence_urls:
            appeal_record["evidence_urls"] = evidence_urls

        # Append to actions_taken
        current_actions = list(case.actions_taken) if case.actions_taken else []
        current_actions.append(appeal_record)
        case.actions_taken = current_actions

        # Transition status
        case.status = target_status.value
        case.appeal_state = "pending_review"

        await self._db.flush()

        logger.info(
            "rights_case_appealed",
            case_id=str(case_id),
            appellant_email=appellant_email,
        )

        return case

    # =========================================================================
    # Query
    # =========================================================================

    async def get_case(self, case_id: UUID) -> RightsCase | None:
        """Get a rights case by its primary key.

        Args:
            case_id: The rights_cases.id.

        Returns:
            The RightsCase or None if not found.
        """
        stmt = select(RightsCase).where(RightsCase.id == case_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_cases(
        self,
        limit: int = 20,
        offset: int = 0,
        status: str | None = None,
        priority: str | None = None,
        case_type: str | None = None,
        target_org_id: UUID | None = None,
        assigned_operator: UUID | None = None,
    ) -> tuple[list[RightsCase], int]:
        """List rights cases with optional filters.

        Args:
            limit: Max items to return (1-100, default 20).
            offset: Pagination offset.
            status: Filter by case status.
            priority: Filter by priority.
            case_type: Filter by complaint type.
            target_org_id: Filter by target organization.
            assigned_operator: Filter by assigned operator.

        Returns:
            Tuple of (case list, total count).
        """
        limit = max(1, min(limit, 100))
        offset = max(0, offset)

        filters = []
        if status is not None:
            filters.append(RightsCase.status == status)
        if priority is not None:
            filters.append(RightsCase.priority == priority)
        if case_type is not None:
            filters.append(RightsCase.case_type == case_type)
        if target_org_id is not None:
            filters.append(RightsCase.target_org_id == target_org_id)
        if assigned_operator is not None:
            filters.append(RightsCase.assigned_operator == assigned_operator)

        # Count
        count_stmt = (
            select(func.count())
            .select_from(RightsCase)
            .where(*filters)
        )
        total = await self._db.scalar(count_stmt) or 0

        # Items
        stmt = (
            select(RightsCase)
            .where(*filters)
            .order_by(RightsCase.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._db.execute(stmt)
        items = list(result.scalars().all())

        return items, total

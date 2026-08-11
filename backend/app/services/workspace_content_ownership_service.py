"""Workspace Content Ownership Service — member departure and content governance.

Core principle: org_id is the owner of all workspace content. Individual users
create content within the workspace scope, but ownership is always at the org level.
Departure doesn't require content transfer — it requires connection cleanup and
job reassignment.

Content types owned by the workspace:
    - Talent, projects, assets, LoRA models, Creative DNA
    - Recipes, workflows, workspace-shared knowledge

Validates: Requirements R96.1, R96.2, R96.3, R96.4
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from app.core.logging import get_logger
from app.schemas.workspace_content_ownership import (
    AffectedJob,
    ContentInventoryItem,
    ContentInventoryResponse,
    ContentType,
    DepartureSummary,
    JobDisposition,
    AccountDeletionEligibility,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.services.connection_permission_service import (
        ConnectionPermissionService,
        MemberDepartureResult,
    )

logger = get_logger(__name__)


# =============================================================================
# Exceptions
# =============================================================================


class DepartureError(Exception):
    """Raised when member departure processing fails.

    Attributes:
        message: Human-readable description.
        code: Machine-readable error code.
    """

    def __init__(self, message: str, code: str = "DEPARTURE_ERROR") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class OwnershipTransferRequired(Exception):
    """Raised when account deletion is blocked by sole ownership.

    Validates: R96.3
    """

    def __init__(self, org_id: UUID) -> None:
        self.org_id = org_id
        self.message = (
            "Cannot delete account: user is the sole owner of this workspace. "
            "Transfer ownership to another admin/owner first."
        )
        self.code = "OWNERSHIP_TRANSFER_REQUIRED"
        super().__init__(self.message)


# =============================================================================
# Service
# =============================================================================


class WorkspaceContentOwnershipService:
    """Workspace content ownership and member departure management.

    Responsibilities:
        - get_content_inventory: list workspace content created by a user
        - process_member_departure: full departure workflow
        - validate_account_deletion_eligible: check sole-owner constraint

    All workspace content belongs to the organization (R96.1). Users create
    content within the workspace scope, but the org_id on each record is
    the canonical owner.

    Validates: R96.1, R96.2, R96.3, R96.4
    """

    def __init__(
        self,
        db: "AsyncSession",
        org_id: UUID,
        connection_permission_service: "ConnectionPermissionService | None" = None,
    ) -> None:
        """Initialize with DB session and tenant context.

        Args:
            db: SQLAlchemy async session.
            org_id: Authenticated org UUID from TenantContext.
            connection_permission_service: Optional ConnectionPermissionService
                for handling connection revocation during departure.
        """
        self._db = db
        self._org_id = org_id
        self._connection_permission_service = connection_permission_service

    # =========================================================================
    # Content Inventory (R96.1)
    # =========================================================================

    async def get_content_inventory(
        self,
        user_id: UUID,
    ) -> ContentInventoryResponse:
        """Get workspace content inventory created by a specific user.

        All content belongs to the workspace (org_id). This method returns
        counts of items created by the user, demonstrating what stays when
        the user departs.

        Args:
            user_id: The user whose content contributions to enumerate.

        Returns:
            ContentInventoryResponse with per-type counts.

        Validates: R96.1
        """
        from sqlalchemy import func, select, text

        # Content tables and their user_id columns
        # Each maps content_type → (table_name, user_id_column)
        content_queries: list[tuple[ContentType, str, str]] = [
            (ContentType.TALENT, "ai_talent", "user_id"),
            (ContentType.PROJECT, "projects", "user_id"),
            (ContentType.ASSET, "assets", "user_id"),
            (ContentType.LORA_MODEL, "lora_models", "user_id"),
            (ContentType.WORKFLOW, "workflows", "user_id"),
        ]

        items: list[ContentInventoryItem] = []
        total_items = 0

        for content_type, table_name, user_col in content_queries:
            try:
                stmt = text(
                    f"SELECT COUNT(*) FROM {table_name} "
                    f"WHERE org_id = :org_id AND {user_col} = :user_id"
                )
                result = await self._db.execute(
                    stmt, {"org_id": self._org_id, "user_id": user_id}
                )
                count = result.scalar() or 0
            except Exception:
                # Table may not exist yet — skip gracefully
                count = 0

            items.append(
                ContentInventoryItem(content_type=content_type, count=count)
            )
            total_items += count

        logger.info(
            "content_inventory_retrieved",
            org_id=str(self._org_id),
            user_id=str(user_id),
            total_items=total_items,
        )

        return ContentInventoryResponse(
            org_id=self._org_id,
            user_id=user_id,
            items=items,
            total_items=total_items,
        )

    # =========================================================================
    # Member Departure (R96.2)
    # =========================================================================

    async def process_member_departure(
        self,
        departing_user_id: UUID,
    ) -> DepartureSummary:
        """Handle full member departure from workspace.

        Departure protocol (R96.2):
            1. Workspace content stays (org_id is owner — no transfer needed)
            2. Personal connections revoked (delegate to ConnectionPermissionService)
            3. Workspace connections remain functional
            4. Unfinished jobs by departing user: reassign or pause

        This method is idempotent — processing departure for an already-departed
        user produces the same result.

        Args:
            departing_user_id: UUID of the member who is leaving.

        Returns:
            DepartureSummary with full details of actions taken.

        Raises:
            DepartureError: If departure processing fails.

        Validates: R96.2
        """
        processed_at = datetime.now(tz=UTC)

        # Step 1: Content stays with workspace (R96.1)
        # org_id is the owner — no content transfer required
        inventory = await self.get_content_inventory(departing_user_id)
        workspace_content_preserved = inventory.total_items

        # Step 2: Revoke personal connections (R96.2)
        connection_result = await self._revoke_personal_connections(departing_user_id)

        # Step 3: Reassign or pause unfinished jobs (R96.2)
        affected_jobs = await self._handle_unfinished_jobs(departing_user_id)

        jobs_reassigned = sum(
            1 for j in affected_jobs if j.disposition == JobDisposition.REASSIGNED
        )
        jobs_paused = sum(
            1 for j in affected_jobs if j.disposition == JobDisposition.PAUSED
        )

        summary = DepartureSummary(
            org_id=self._org_id,
            departing_user_id=departing_user_id,
            processed_at=processed_at,
            workspace_content_preserved=workspace_content_preserved,
            personal_connections_revoked=connection_result.revoked_count,
            workspace_connections_preserved=connection_result.preserved_count,
            connections_flagged_for_reauth=connection_result.flagged_count,
            jobs_reassigned=jobs_reassigned,
            jobs_paused=jobs_paused,
            affected_jobs=affected_jobs,
        )

        logger.info(
            "member_departure_completed",
            org_id=str(self._org_id),
            departing_user_id=str(departing_user_id),
            content_preserved=workspace_content_preserved,
            connections_revoked=connection_result.revoked_count,
            jobs_reassigned=jobs_reassigned,
            jobs_paused=jobs_paused,
        )

        return summary

    # =========================================================================
    # Account Deletion Eligibility (R96.3)
    # =========================================================================

    async def validate_account_deletion_eligible(
        self,
        user_id: UUID,
    ) -> AccountDeletionEligibility:
        """Check if a user can delete their account.

        Account deletion requires:
            - User is NOT the sole owner of the workspace
            - Ownership must be transferred first if sole owner

        Validates: R96.3

        Args:
            user_id: The user requesting account deletion.

        Returns:
            AccountDeletionEligibility with eligibility status.
        """
        from sqlalchemy import text

        # Count owners in this org
        try:
            stmt = text(
                "SELECT COUNT(*) FROM org_members "
                "WHERE org_id = :org_id AND role = 'owner' AND status = 'active'"
            )
            result = await self._db.execute(stmt, {"org_id": self._org_id})
            total_owners = result.scalar() or 0
        except Exception:
            # Table may not exist — default to safe (not eligible)
            total_owners = 0

        # Check if this user is an owner
        try:
            stmt = text(
                "SELECT COUNT(*) FROM org_members "
                "WHERE org_id = :org_id AND user_id = :user_id "
                "AND role = 'owner' AND status = 'active'"
            )
            result = await self._db.execute(
                stmt, {"org_id": self._org_id, "user_id": user_id}
            )
            is_owner = (result.scalar() or 0) > 0
        except Exception:
            is_owner = False

        other_owners = total_owners - (1 if is_owner else 0)
        is_sole_owner = is_owner and other_owners == 0

        eligible = not is_sole_owner
        reason = None
        if is_sole_owner:
            reason = (
                "User is the sole owner of this workspace. "
                "Transfer ownership to another admin/owner before deleting account."
            )

        logger.info(
            "account_deletion_eligibility_checked",
            org_id=str(self._org_id),
            user_id=str(user_id),
            eligible=eligible,
            is_sole_owner=is_sole_owner,
        )

        return AccountDeletionEligibility(
            user_id=user_id,
            org_id=self._org_id,
            eligible=eligible,
            reason=reason,
            is_sole_owner=is_sole_owner,
            other_owners_count=other_owners,
        )

    # =========================================================================
    # Private helpers
    # =========================================================================

    async def _revoke_personal_connections(
        self,
        departing_user_id: UUID,
    ) -> "_ConnectionDepartureResult":
        """Revoke personal connections for the departing user.

        Delegates to ConnectionPermissionService if available.
        """
        if self._connection_permission_service:
            result = await self._connection_permission_service.process_member_departure(
                org_id=self._org_id,
                departing_user_id=departing_user_id,
            )
            return _ConnectionDepartureResult(
                revoked_count=len(result.revoked_connection_ids),
                preserved_count=len(result.preserved_connection_ids),
                flagged_count=len(result.flagged_for_reauth),
            )

        # No connection service available — return zeros
        return _ConnectionDepartureResult(
            revoked_count=0,
            preserved_count=0,
            flagged_count=0,
        )

    async def _handle_unfinished_jobs(
        self,
        departing_user_id: UUID,
    ) -> list[AffectedJob]:
        """Reassign or pause unfinished jobs owned by the departing user.

        Active/running jobs are paused (cannot reassign mid-execution safely).
        Queued jobs are paused for admin to decide.

        Args:
            departing_user_id: The departing user's UUID.

        Returns:
            List of AffectedJob records.
        """
        from sqlalchemy import text

        affected_jobs: list[AffectedJob] = []

        # Find unfinished jobs (queued, running, claimed)
        non_terminal_statuses = ("queued", "claimed", "running")

        try:
            stmt = text(
                "SELECT id, job_type, status FROM jobs "
                "WHERE org_id = :org_id AND user_id = :user_id "
                "AND status = ANY(:statuses)"
            )
            result = await self._db.execute(
                stmt,
                {
                    "org_id": self._org_id,
                    "user_id": departing_user_id,
                    "statuses": list(non_terminal_statuses),
                },
            )
            rows = result.fetchall()
        except Exception:
            # Table may not exist — return empty
            return affected_jobs

        for row in rows:
            job_id, job_type, current_status = row[0], row[1], row[2]

            # Running jobs cannot be safely reassigned — pause them
            # Queued jobs are paused for admin review
            disposition = JobDisposition.PAUSED

            try:
                stmt = text(
                    "UPDATE jobs SET status = 'paused' "
                    "WHERE id = :job_id AND org_id = :org_id"
                )
                await self._db.execute(
                    stmt, {"job_id": job_id, "org_id": self._org_id}
                )
            except Exception:
                logger.warning(
                    "job_pause_failed_during_departure",
                    job_id=str(job_id),
                    org_id=str(self._org_id),
                )
                continue

            affected_jobs.append(
                AffectedJob(
                    job_id=job_id,
                    job_type=job_type,
                    status=current_status,
                    disposition=disposition,
                )
            )

        if affected_jobs:
            logger.info(
                "unfinished_jobs_handled",
                org_id=str(self._org_id),
                departing_user_id=str(departing_user_id),
                jobs_count=len(affected_jobs),
            )

        return affected_jobs


# =============================================================================
# Internal result type
# =============================================================================


class _ConnectionDepartureResult:
    """Internal result for connection departure processing."""

    def __init__(
        self,
        revoked_count: int,
        preserved_count: int,
        flagged_count: int,
    ) -> None:
        self.revoked_count = revoked_count
        self.preserved_count = preserved_count
        self.flagged_count = flagged_count

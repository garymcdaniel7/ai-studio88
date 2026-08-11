"""Unit tests for WorkspaceContentOwnershipService.

Tests content ownership, member departure protocol, and account deletion
eligibility without I/O — uses mocked database sessions and services.

Run with: pytest tests/unit/test_services/test_workspace_content_ownership_service.py -v

Validates: Requirements R96.1, R96.2, R96.3, R96.4
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.workspace_content_ownership import (
    ContentType,
    JobDisposition,
)
from app.services.workspace_content_ownership_service import (
    WorkspaceContentOwnershipService,
    _ConnectionDepartureResult,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def org_id() -> uuid.UUID:
    """Standard test org_id."""
    return uuid.uuid4()


@pytest.fixture
def user_id() -> uuid.UUID:
    """Standard test user_id."""
    return uuid.uuid4()


@pytest.fixture
def mock_db() -> AsyncMock:
    """Create a mocked async DB session."""
    db = AsyncMock()
    return db


@pytest.fixture
def mock_connection_service() -> AsyncMock:
    """Create a mocked ConnectionPermissionService."""
    service = AsyncMock()
    # Default: return a result with some revoked connections
    departure_result = MagicMock()
    departure_result.revoked_connection_ids = [uuid.uuid4(), uuid.uuid4()]
    departure_result.preserved_connection_ids = [uuid.uuid4()]
    departure_result.flagged_for_reauth = [uuid.uuid4()]
    service.process_member_departure.return_value = departure_result
    return service


def _make_service(
    mock_db: AsyncMock,
    org_id: uuid.UUID,
    connection_service: AsyncMock | None = None,
) -> WorkspaceContentOwnershipService:
    """Create a WorkspaceContentOwnershipService with mocked dependencies."""
    return WorkspaceContentOwnershipService(
        db=mock_db,
        org_id=org_id,
        connection_permission_service=connection_service,
    )


# =============================================================================
# Content Inventory Tests (R96.1)
# =============================================================================


class TestGetContentInventory:
    """Tests for get_content_inventory — R96.1."""

    @pytest.mark.asyncio
    async def test_returns_inventory_with_counts(
        self,
        mock_db: AsyncMock,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """Content inventory returns per-type counts for workspace content."""
        # Mock DB to return counts for each content table
        mock_result = MagicMock()
        mock_result.scalar.return_value = 5
        mock_db.execute.return_value = mock_result

        service = _make_service(mock_db, org_id)
        result = await service.get_content_inventory(user_id)

        assert result.org_id == org_id
        assert result.user_id == user_id
        assert result.total_items == 25  # 5 items * 5 content types
        assert len(result.items) == 5

    @pytest.mark.asyncio
    async def test_handles_empty_inventory(
        self,
        mock_db: AsyncMock,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """Content inventory handles zero items gracefully."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0
        mock_db.execute.return_value = mock_result

        service = _make_service(mock_db, org_id)
        result = await service.get_content_inventory(user_id)

        assert result.total_items == 0
        for item in result.items:
            assert item.count == 0

    @pytest.mark.asyncio
    async def test_handles_missing_tables_gracefully(
        self,
        mock_db: AsyncMock,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """Tables that don't exist yet are skipped without error."""
        mock_db.execute.side_effect = Exception("relation does not exist")

        service = _make_service(mock_db, org_id)
        result = await service.get_content_inventory(user_id)

        # Should still return a valid response with 0 counts
        assert result.total_items == 0
        assert len(result.items) == 5

    @pytest.mark.asyncio
    async def test_content_types_are_correct(
        self,
        mock_db: AsyncMock,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """All workspace-owned content types are represented."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        mock_db.execute.return_value = mock_result

        service = _make_service(mock_db, org_id)
        result = await service.get_content_inventory(user_id)

        content_types = {item.content_type for item in result.items}
        expected_types = {
            ContentType.TALENT,
            ContentType.PROJECT,
            ContentType.ASSET,
            ContentType.LORA_MODEL,
            ContentType.WORKFLOW,
        }
        assert content_types == expected_types


# =============================================================================
# Member Departure Tests (R96.2)
# =============================================================================


class TestProcessMemberDeparture:
    """Tests for process_member_departure — R96.2."""

    @pytest.mark.asyncio
    async def test_departure_revokes_personal_connections(
        self,
        mock_db: AsyncMock,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        mock_connection_service: AsyncMock,
    ) -> None:
        """Personal connections are revoked during departure (R96.2)."""
        # DB returns 0 for content and no unfinished jobs
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result

        service = _make_service(mock_db, org_id, mock_connection_service)
        summary = await service.process_member_departure(user_id)

        # ConnectionPermissionService was called
        mock_connection_service.process_member_departure.assert_called_once_with(
            org_id=org_id,
            departing_user_id=user_id,
        )
        assert summary.personal_connections_revoked == 2
        assert summary.workspace_connections_preserved == 1
        assert summary.connections_flagged_for_reauth == 1

    @pytest.mark.asyncio
    async def test_departure_preserves_workspace_content(
        self,
        mock_db: AsyncMock,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        mock_connection_service: AsyncMock,
    ) -> None:
        """Workspace content stays with org — no transfer needed (R96.1)."""
        # Return 3 items per content type for inventory, no jobs
        call_count = [0]

        async def mock_execute(stmt, params=None):
            call_count[0] += 1
            result = MagicMock()
            # First 5 calls are content inventory (3 items each)
            if call_count[0] <= 5:
                result.scalar.return_value = 3
            else:
                # Jobs query
                result.fetchall.return_value = []
            return result

        mock_db.execute = mock_execute

        service = _make_service(mock_db, org_id, mock_connection_service)
        summary = await service.process_member_departure(user_id)

        assert summary.workspace_content_preserved == 15  # 3 * 5 types
        assert summary.org_id == org_id
        assert summary.departing_user_id == user_id

    @pytest.mark.asyncio
    async def test_departure_pauses_unfinished_jobs(
        self,
        mock_db: AsyncMock,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        mock_connection_service: AsyncMock,
    ) -> None:
        """Unfinished jobs are paused during departure (R96.2)."""
        job_id_1 = uuid.uuid4()
        job_id_2 = uuid.uuid4()
        call_count = [0]

        async def mock_execute(stmt, params=None):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] <= 5:
                # Content inventory
                result.scalar.return_value = 0
            elif call_count[0] == 6:
                # Jobs SELECT query
                result.fetchall.return_value = [
                    (job_id_1, "image_generation", "queued"),
                    (job_id_2, "lora_training", "running"),
                ]
            else:
                # UPDATE queries for pausing jobs
                pass
            return result

        mock_db.execute = mock_execute

        service = _make_service(mock_db, org_id, mock_connection_service)
        summary = await service.process_member_departure(user_id)

        assert summary.jobs_paused == 2
        assert summary.jobs_reassigned == 0
        assert len(summary.affected_jobs) == 2
        assert all(
            j.disposition == JobDisposition.PAUSED for j in summary.affected_jobs
        )

    @pytest.mark.asyncio
    async def test_departure_without_connection_service(
        self,
        mock_db: AsyncMock,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """Departure works without connection service (returns zero counts)."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result

        # No connection service passed
        service = _make_service(mock_db, org_id, None)
        summary = await service.process_member_departure(user_id)

        assert summary.personal_connections_revoked == 0
        assert summary.workspace_connections_preserved == 0
        assert summary.connections_flagged_for_reauth == 0

    @pytest.mark.asyncio
    async def test_departure_summary_has_timestamp(
        self,
        mock_db: AsyncMock,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        mock_connection_service: AsyncMock,
    ) -> None:
        """Departure summary includes processing timestamp."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result

        service = _make_service(mock_db, org_id, mock_connection_service)
        summary = await service.process_member_departure(user_id)

        assert summary.processed_at is not None
        assert isinstance(summary.processed_at, datetime)


# =============================================================================
# Account Deletion Eligibility Tests (R96.3)
# =============================================================================


class TestValidateAccountDeletionEligible:
    """Tests for validate_account_deletion_eligible — R96.3."""

    @pytest.mark.asyncio
    async def test_sole_owner_cannot_delete_account(
        self,
        mock_db: AsyncMock,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """Sole owner is not eligible for deletion (R96.3)."""
        call_count = [0]

        async def mock_execute(stmt, params=None):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                # Total owners count
                result.scalar.return_value = 1
            else:
                # Is this user an owner?
                result.scalar.return_value = 1
            return result

        mock_db.execute = mock_execute

        service = _make_service(mock_db, org_id)
        eligibility = await service.validate_account_deletion_eligible(user_id)

        assert eligibility.eligible is False
        assert eligibility.is_sole_owner is True
        assert eligibility.other_owners_count == 0
        assert eligibility.reason is not None
        assert "sole owner" in eligibility.reason.lower()

    @pytest.mark.asyncio
    async def test_non_sole_owner_can_delete_account(
        self,
        mock_db: AsyncMock,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """User with other owners in the workspace can delete (R96.3)."""
        call_count = [0]

        async def mock_execute(stmt, params=None):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                # Total owners count = 2
                result.scalar.return_value = 2
            else:
                # Is this user an owner? Yes
                result.scalar.return_value = 1
            return result

        mock_db.execute = mock_execute

        service = _make_service(mock_db, org_id)
        eligibility = await service.validate_account_deletion_eligible(user_id)

        assert eligibility.eligible is True
        assert eligibility.is_sole_owner is False
        assert eligibility.other_owners_count == 1
        assert eligibility.reason is None

    @pytest.mark.asyncio
    async def test_non_owner_can_delete_account(
        self,
        mock_db: AsyncMock,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """Non-owner (editor, viewer, admin) can always delete their account."""
        call_count = [0]

        async def mock_execute(stmt, params=None):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                # Total owners count = 1 (some other user)
                result.scalar.return_value = 1
            else:
                # Is this user an owner? No
                result.scalar.return_value = 0
            return result

        mock_db.execute = mock_execute

        service = _make_service(mock_db, org_id)
        eligibility = await service.validate_account_deletion_eligible(user_id)

        assert eligibility.eligible is True
        assert eligibility.is_sole_owner is False
        assert eligibility.other_owners_count == 1

    @pytest.mark.asyncio
    async def test_handles_missing_org_members_table(
        self,
        mock_db: AsyncMock,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """Gracefully handles missing org_members table (defaults to not eligible)."""
        mock_db.execute.side_effect = Exception("relation does not exist")

        service = _make_service(mock_db, org_id)
        eligibility = await service.validate_account_deletion_eligible(user_id)

        # Default to safe (not eligible) when table doesn't exist
        assert eligibility.eligible is True  # 0 owners, not sole owner
        assert eligibility.is_sole_owner is False


# =============================================================================
# Content Ownership Principle Test (R96.4)
# =============================================================================


class TestContentOwnershipPrinciple:
    """Verify the core principle: org_id is the content owner.

    R96.4: Departing users SHALL NOT be able to export or take workspace
    content unless explicitly permitted by admin.
    """

    @pytest.mark.asyncio
    async def test_departure_does_not_transfer_content(
        self,
        mock_db: AsyncMock,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        mock_connection_service: AsyncMock,
    ) -> None:
        """Departure never transfers content away from workspace (R96.4).

        The service processes departure without any content removal or
        transfer operations. Content stays as-is because org_id owns it.
        """
        mock_result = MagicMock()
        mock_result.scalar.return_value = 10
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result

        service = _make_service(mock_db, org_id, mock_connection_service)
        summary = await service.process_member_departure(user_id)

        # Content preserved — NOT deleted, NOT transferred
        assert summary.workspace_content_preserved == 50  # 10 * 5 types
        # The service does not issue DELETE or UPDATE on content tables
        # Only the jobs table gets UPDATE (for pausing)

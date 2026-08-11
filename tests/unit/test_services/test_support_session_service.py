"""Unit tests for the Support Session Service.

Tests cover:
    - R33.8: Time-limited elevated access (audited, expiring)
    - R33.9: All operator actions logged
    - R97.5: No unrestricted permanent access
    - R97.6: All actions logged
    - A2-006: Tenant support session architecture

No I/O, no DB — AsyncSession is fully mocked.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.support_session import (
    SupportSession,
    SupportSessionStatus,
    VALID_STATUS_TRANSITIONS,
)
from app.services.support_session_service import (
    DEFAULT_DURATION_MINUTES,
    DEFAULT_MAX_DURATION_MINUTES,
    InvalidTransitionError,
    ScopeViolationError,
    SessionExpiredError,
    SessionNotActiveError,
    SessionNotFoundError,
    SupportSessionError,
    SupportSessionService,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_db() -> AsyncMock:
    """Create a mock AsyncSession for unit tests."""
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock()
    db.scalar = AsyncMock()
    return db


@pytest.fixture
def service(mock_db: AsyncMock) -> SupportSessionService:
    """Create a SupportSessionService with mocked DB."""
    return SupportSessionService(db=mock_db)


@pytest.fixture
def operator_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def target_org_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def approver_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def session_id() -> uuid.UUID:
    return uuid.uuid4()


def _make_session(
    session_id: uuid.UUID | None = None,
    operator_user_id: uuid.UUID | None = None,
    target_org_id: uuid.UUID | None = None,
    status: str = SupportSessionStatus.REQUESTED.value,
    expires_at: datetime | None = None,
    permitted_surfaces: list[str] | None = None,
    permitted_actions: list[str] | None = None,
    approved_by: uuid.UUID | None = None,
    approved_capabilities: list[str] | None = None,
    requested_capabilities: list[str] | None = None,
) -> SupportSession:
    """Create a mock SupportSession object for testing."""
    session = SupportSession()
    session.id = session_id or uuid.uuid4()
    session.operator_user_id = operator_user_id or uuid.uuid4()
    session.target_org_id = target_org_id or uuid.uuid4()
    session.reason = "Test support reason"
    session.status = status
    session.started_at = datetime.now(UTC)
    session.expires_at = expires_at or (datetime.now(UTC) + timedelta(hours=1))
    session.ended_at = None
    session.permitted_surfaces = permitted_surfaces
    session.permitted_actions = permitted_actions
    session.approved_by = approved_by
    session.approved_capabilities = approved_capabilities
    session.requested_capabilities = requested_capabilities
    session.created_at = datetime.now(UTC)
    session.updated_at = datetime.now(UTC)
    return session


# =============================================================================
# Tests: request_session
# =============================================================================


@pytest.mark.unit
class TestRequestSession:
    """Test support session creation/request."""

    @pytest.mark.asyncio
    async def test_request_session_creates_with_requested_status(
        self,
        service: SupportSessionService,
        mock_db: AsyncMock,
        operator_id: uuid.UUID,
        target_org_id: uuid.UUID,
    ) -> None:
        """A new session starts in REQUESTED status."""
        session = await service.request_session(
            operator_user_id=operator_id,
            target_org_id=target_org_id,
            reason="Customer reporting job failures",
            requested_capabilities=["tenant_support"],
            permitted_surfaces=["job_history", "cost_records"],
            permitted_actions=["view"],
            duration_minutes=60,
        )

        assert session.status == SupportSessionStatus.REQUESTED.value
        assert session.operator_user_id == operator_id
        assert session.target_org_id == target_org_id
        assert session.reason == "Customer reporting job failures"
        assert session.requested_capabilities == ["tenant_support"]
        assert session.permitted_surfaces == ["job_history", "cost_records"]
        assert session.permitted_actions == ["view"]
        mock_db.add.assert_called_once()
        mock_db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_request_session_clamps_duration_to_max(
        self,
        service: SupportSessionService,
        mock_db: AsyncMock,
        operator_id: uuid.UUID,
        target_org_id: uuid.UUID,
    ) -> None:
        """Duration is clamped to max 240 minutes."""
        session = await service.request_session(
            operator_user_id=operator_id,
            target_org_id=target_org_id,
            reason="Extended investigation needed",
            duration_minutes=500,  # Exceeds max
        )

        # expires_at should be ~240 minutes from start
        delta = session.expires_at - session.started_at
        assert delta <= timedelta(minutes=DEFAULT_MAX_DURATION_MINUTES + 1)

    @pytest.mark.asyncio
    async def test_request_session_clamps_duration_to_min(
        self,
        service: SupportSessionService,
        mock_db: AsyncMock,
        operator_id: uuid.UUID,
        target_org_id: uuid.UUID,
    ) -> None:
        """Duration is clamped to min 5 minutes."""
        session = await service.request_session(
            operator_user_id=operator_id,
            target_org_id=target_org_id,
            reason="Quick check on configuration",
            duration_minutes=1,  # Below min
        )

        delta = session.expires_at - session.started_at
        assert delta >= timedelta(minutes=5)

    @pytest.mark.asyncio
    async def test_request_session_default_duration(
        self,
        service: SupportSessionService,
        mock_db: AsyncMock,
        operator_id: uuid.UUID,
        target_org_id: uuid.UUID,
    ) -> None:
        """Default duration is 60 minutes."""
        session = await service.request_session(
            operator_user_id=operator_id,
            target_org_id=target_org_id,
            reason="Routine support check",
        )

        delta = session.expires_at - session.started_at
        # Allow small timing variance
        assert timedelta(minutes=59) <= delta <= timedelta(minutes=61)


# =============================================================================
# Tests: approve_session
# =============================================================================


@pytest.mark.unit
class TestApproveSession:
    """Test support session approval."""

    @pytest.mark.asyncio
    async def test_approve_transitions_to_active(
        self,
        service: SupportSessionService,
        mock_db: AsyncMock,
        approver_id: uuid.UUID,
    ) -> None:
        """Approving a REQUESTED session transitions it to ACTIVE."""
        pending = _make_session(
            status=SupportSessionStatus.REQUESTED.value,
            requested_capabilities=["tenant_support"],
            permitted_surfaces=["job_history"],
            permitted_actions=["view"],
        )

        # Mock get_session to return the pending session
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = pending
        mock_db.execute.return_value = mock_result

        result = await service.approve_session(
            session_id=pending.id,
            approved_by=approver_id,
        )

        assert result.status == SupportSessionStatus.ACTIVE.value
        assert result.approved_by == approver_id
        assert result.approved_capabilities == ["tenant_support"]
        mock_db.flush.assert_awaited()

    @pytest.mark.asyncio
    async def test_approve_restricts_capabilities(
        self,
        service: SupportSessionService,
        mock_db: AsyncMock,
        approver_id: uuid.UUID,
    ) -> None:
        """Approver can grant a subset of requested capabilities."""
        pending = _make_session(
            status=SupportSessionStatus.REQUESTED.value,
            requested_capabilities=["tenant_support", "platform_observe"],
            permitted_surfaces=["job_history", "cost_records", "talent_metadata"],
            permitted_actions=["view", "pause_job"],
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = pending
        mock_db.execute.return_value = mock_result

        result = await service.approve_session(
            session_id=pending.id,
            approved_by=approver_id,
            approved_capabilities=["tenant_support"],
            permitted_surfaces=["job_history", "cost_records"],
            permitted_actions=["view"],
        )

        assert result.approved_capabilities == ["tenant_support"]
        assert result.permitted_surfaces == ["job_history", "cost_records"]
        assert result.permitted_actions == ["view"]

    @pytest.mark.asyncio
    async def test_approve_not_found_raises(
        self,
        service: SupportSessionService,
        mock_db: AsyncMock,
        approver_id: uuid.UUID,
        session_id: uuid.UUID,
    ) -> None:
        """Approving a non-existent session raises SessionNotFoundError."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(SessionNotFoundError):
            await service.approve_session(
                session_id=session_id,
                approved_by=approver_id,
            )

    @pytest.mark.asyncio
    async def test_approve_already_active_raises(
        self,
        service: SupportSessionService,
        mock_db: AsyncMock,
        approver_id: uuid.UUID,
    ) -> None:
        """Approving an already-active session raises InvalidTransitionError."""
        active = _make_session(status=SupportSessionStatus.ACTIVE.value)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = active
        mock_db.execute.return_value = mock_result

        with pytest.raises(InvalidTransitionError):
            await service.approve_session(
                session_id=active.id,
                approved_by=approver_id,
            )

    @pytest.mark.asyncio
    async def test_approve_revoked_session_raises(
        self,
        service: SupportSessionService,
        mock_db: AsyncMock,
        approver_id: uuid.UUID,
    ) -> None:
        """Approving a revoked session raises InvalidTransitionError."""
        revoked = _make_session(status=SupportSessionStatus.REVOKED.value)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = revoked
        mock_db.execute.return_value = mock_result

        with pytest.raises(InvalidTransitionError):
            await service.approve_session(
                session_id=revoked.id,
                approved_by=approver_id,
            )


# =============================================================================
# Tests: revoke_session
# =============================================================================


@pytest.mark.unit
class TestRevokeSession:
    """Test support session revocation."""

    @pytest.mark.asyncio
    async def test_revoke_active_session(
        self,
        service: SupportSessionService,
        mock_db: AsyncMock,
    ) -> None:
        """Revoking an active session transitions to REVOKED."""
        active = _make_session(status=SupportSessionStatus.ACTIVE.value)
        revoker = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = active
        mock_db.execute.return_value = mock_result

        result = await service.revoke_session(
            session_id=active.id,
            revoked_by=revoker,
            reason="No longer needed",
        )

        assert result.status == SupportSessionStatus.REVOKED.value
        assert result.ended_at is not None

    @pytest.mark.asyncio
    async def test_revoke_requested_session(
        self,
        service: SupportSessionService,
        mock_db: AsyncMock,
    ) -> None:
        """Revoking a REQUESTED session (before approval) works."""
        requested = _make_session(status=SupportSessionStatus.REQUESTED.value)
        revoker = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = requested
        mock_db.execute.return_value = mock_result

        result = await service.revoke_session(
            session_id=requested.id,
            revoked_by=revoker,
        )

        assert result.status == SupportSessionStatus.REVOKED.value

    @pytest.mark.asyncio
    async def test_revoke_already_expired_raises(
        self,
        service: SupportSessionService,
        mock_db: AsyncMock,
    ) -> None:
        """Revoking an already-expired session raises InvalidTransitionError."""
        expired = _make_session(status=SupportSessionStatus.EXPIRED.value)
        revoker = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = expired
        mock_db.execute.return_value = mock_result

        with pytest.raises(InvalidTransitionError):
            await service.revoke_session(
                session_id=expired.id,
                revoked_by=revoker,
            )

    @pytest.mark.asyncio
    async def test_revoke_not_found_raises(
        self,
        service: SupportSessionService,
        mock_db: AsyncMock,
    ) -> None:
        """Revoking a non-existent session raises SessionNotFoundError."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(SessionNotFoundError):
            await service.revoke_session(
                session_id=uuid.uuid4(),
                revoked_by=uuid.uuid4(),
            )


# =============================================================================
# Tests: complete_session
# =============================================================================


@pytest.mark.unit
class TestCompleteSession:
    """Test support session completion."""

    @pytest.mark.asyncio
    async def test_complete_active_session(
        self,
        service: SupportSessionService,
        mock_db: AsyncMock,
    ) -> None:
        """Completing an active session transitions to COMPLETED."""
        active = _make_session(status=SupportSessionStatus.ACTIVE.value)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = active
        mock_db.execute.return_value = mock_result

        result = await service.complete_session(session_id=active.id)

        assert result.status == SupportSessionStatus.COMPLETED.value
        assert result.ended_at is not None

    @pytest.mark.asyncio
    async def test_complete_requested_session_raises(
        self,
        service: SupportSessionService,
        mock_db: AsyncMock,
    ) -> None:
        """Cannot complete a session that isn't active yet."""
        requested = _make_session(status=SupportSessionStatus.REQUESTED.value)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = requested
        mock_db.execute.return_value = mock_result

        with pytest.raises(InvalidTransitionError):
            await service.complete_session(session_id=requested.id)


# =============================================================================
# Tests: check_session_valid
# =============================================================================


@pytest.mark.unit
class TestCheckSessionValid:
    """Test session validity checks including auto-expiry."""

    @pytest.mark.asyncio
    async def test_active_non_expired_is_valid(
        self,
        service: SupportSessionService,
        mock_db: AsyncMock,
    ) -> None:
        """An active session not past expires_at is valid."""
        active = _make_session(
            status=SupportSessionStatus.ACTIVE.value,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = active
        mock_db.execute.return_value = mock_result

        result = await service.check_session_valid(active.id)
        assert result is True

    @pytest.mark.asyncio
    async def test_expired_session_auto_transitions(
        self,
        service: SupportSessionService,
        mock_db: AsyncMock,
    ) -> None:
        """A session past expires_at auto-transitions to EXPIRED."""
        expired_time = datetime.now(UTC) - timedelta(minutes=5)
        session = _make_session(
            status=SupportSessionStatus.ACTIVE.value,
            expires_at=expired_time,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = session
        mock_db.execute.return_value = mock_result

        result = await service.check_session_valid(session.id)

        assert result is False
        assert session.status == SupportSessionStatus.EXPIRED.value
        assert session.ended_at is not None
        mock_db.flush.assert_awaited()

    @pytest.mark.asyncio
    async def test_non_existent_session_is_invalid(
        self,
        service: SupportSessionService,
        mock_db: AsyncMock,
    ) -> None:
        """A non-existent session returns False."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await service.check_session_valid(uuid.uuid4())
        assert result is False

    @pytest.mark.asyncio
    async def test_requested_session_is_not_valid(
        self,
        service: SupportSessionService,
        mock_db: AsyncMock,
    ) -> None:
        """A REQUESTED (not yet active) session is not valid."""
        requested = _make_session(status=SupportSessionStatus.REQUESTED.value)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = requested
        mock_db.execute.return_value = mock_result

        result = await service.check_session_valid(requested.id)
        assert result is False

    @pytest.mark.asyncio
    async def test_revoked_session_is_not_valid(
        self,
        service: SupportSessionService,
        mock_db: AsyncMock,
    ) -> None:
        """A REVOKED session is not valid."""
        revoked = _make_session(status=SupportSessionStatus.REVOKED.value)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = revoked
        mock_db.execute.return_value = mock_result

        result = await service.check_session_valid(revoked.id)
        assert result is False


# =============================================================================
# Tests: get_permitted_scope
# =============================================================================


@pytest.mark.unit
class TestGetPermittedScope:
    """Test scope retrieval for active sessions."""

    @pytest.mark.asyncio
    async def test_returns_scope_for_valid_session(
        self,
        service: SupportSessionService,
        mock_db: AsyncMock,
    ) -> None:
        """Returns permitted surfaces and actions for a valid session."""
        active = _make_session(
            status=SupportSessionStatus.ACTIVE.value,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            permitted_surfaces=["job_history", "cost_records"],
            permitted_actions=["view", "pause_job"],
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = active
        mock_db.execute.return_value = mock_result

        result = await service.get_permitted_scope(active.id)

        assert result is not None
        surfaces, actions = result
        assert surfaces == ["job_history", "cost_records"]
        assert actions == ["view", "pause_job"]

    @pytest.mark.asyncio
    async def test_returns_none_for_expired_session(
        self,
        service: SupportSessionService,
        mock_db: AsyncMock,
    ) -> None:
        """Returns None for an expired session (zero access)."""
        expired_time = datetime.now(UTC) - timedelta(minutes=5)
        session = _make_session(
            status=SupportSessionStatus.ACTIVE.value,
            expires_at=expired_time,
            permitted_surfaces=["job_history"],
            permitted_actions=["view"],
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = session
        mock_db.execute.return_value = mock_result

        result = await service.get_permitted_scope(session.id)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_empty_lists_when_no_scope_set(
        self,
        service: SupportSessionService,
        mock_db: AsyncMock,
    ) -> None:
        """Returns empty lists if no surfaces/actions were specified."""
        active = _make_session(
            status=SupportSessionStatus.ACTIVE.value,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            permitted_surfaces=None,
            permitted_actions=None,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = active
        mock_db.execute.return_value = mock_result

        result = await service.get_permitted_scope(active.id)
        assert result is not None
        surfaces, actions = result
        assert surfaces == []
        assert actions == []


# =============================================================================
# Tests: check_surface_permitted / check_action_permitted
# =============================================================================


@pytest.mark.unit
class TestScopeChecks:
    """Test scope boundary enforcement for surfaces and actions."""

    def test_surface_permitted_when_in_list(
        self,
        service: SupportSessionService,
    ) -> None:
        """Surface access allowed when surface is in permitted_surfaces."""
        session = _make_session(
            permitted_surfaces=["job_history", "cost_records"],
        )

        assert service.check_surface_permitted(session, "job_history") is True
        assert service.check_surface_permitted(session, "cost_records") is True

    def test_surface_denied_when_not_in_list(
        self,
        service: SupportSessionService,
    ) -> None:
        """Surface access denied when surface is NOT in permitted_surfaces."""
        session = _make_session(
            permitted_surfaces=["job_history"],
        )

        assert service.check_surface_permitted(session, "talent_metadata") is False
        assert service.check_surface_permitted(session, "creative_content") is False

    def test_surface_denied_when_none(
        self,
        service: SupportSessionService,
    ) -> None:
        """Surface access denied when permitted_surfaces is None."""
        session = _make_session(permitted_surfaces=None)

        assert service.check_surface_permitted(session, "job_history") is False

    def test_action_permitted_when_in_list(
        self,
        service: SupportSessionService,
    ) -> None:
        """Action allowed when action is in permitted_actions."""
        session = _make_session(
            permitted_actions=["view", "pause_job"],
        )

        assert service.check_action_permitted(session, "view") is True
        assert service.check_action_permitted(session, "pause_job") is True

    def test_action_denied_when_not_in_list(
        self,
        service: SupportSessionService,
    ) -> None:
        """Action denied when action is NOT in permitted_actions."""
        session = _make_session(
            permitted_actions=["view"],
        )

        assert service.check_action_permitted(session, "delete") is False
        assert service.check_action_permitted(session, "modify") is False

    def test_action_denied_when_none(
        self,
        service: SupportSessionService,
    ) -> None:
        """Action denied when permitted_actions is None."""
        session = _make_session(permitted_actions=None)

        assert service.check_action_permitted(session, "view") is False


# =============================================================================
# Tests: Status Transition Model
# =============================================================================


@pytest.mark.unit
class TestStatusTransitions:
    """Test the session status transition model."""

    def test_requested_can_transition_to_approved(self) -> None:
        session = _make_session(status=SupportSessionStatus.REQUESTED.value)
        assert session.can_transition_to(SupportSessionStatus.APPROVED) is True

    def test_requested_can_transition_to_revoked(self) -> None:
        session = _make_session(status=SupportSessionStatus.REQUESTED.value)
        assert session.can_transition_to(SupportSessionStatus.REVOKED) is True

    def test_requested_cannot_transition_to_active(self) -> None:
        """REQUESTED cannot go directly to ACTIVE (must be approved first)."""
        session = _make_session(status=SupportSessionStatus.REQUESTED.value)
        assert session.can_transition_to(SupportSessionStatus.ACTIVE) is False

    def test_active_can_transition_to_expired(self) -> None:
        session = _make_session(status=SupportSessionStatus.ACTIVE.value)
        assert session.can_transition_to(SupportSessionStatus.EXPIRED) is True

    def test_active_can_transition_to_revoked(self) -> None:
        session = _make_session(status=SupportSessionStatus.ACTIVE.value)
        assert session.can_transition_to(SupportSessionStatus.REVOKED) is True

    def test_active_can_transition_to_completed(self) -> None:
        session = _make_session(status=SupportSessionStatus.ACTIVE.value)
        assert session.can_transition_to(SupportSessionStatus.COMPLETED) is True

    def test_expired_is_terminal(self) -> None:
        """EXPIRED is a terminal state — no further transitions."""
        session = _make_session(status=SupportSessionStatus.EXPIRED.value)
        assert session.is_terminal is True
        for target in SupportSessionStatus:
            assert session.can_transition_to(target) is False

    def test_revoked_is_terminal(self) -> None:
        """REVOKED is a terminal state — no further transitions."""
        session = _make_session(status=SupportSessionStatus.REVOKED.value)
        assert session.is_terminal is True
        for target in SupportSessionStatus:
            assert session.can_transition_to(target) is False

    def test_completed_is_terminal(self) -> None:
        """COMPLETED is a terminal state — no further transitions."""
        session = _make_session(status=SupportSessionStatus.COMPLETED.value)
        assert session.is_terminal is True
        for target in SupportSessionStatus:
            assert session.can_transition_to(target) is False


# =============================================================================
# Tests: list_sessions
# =============================================================================


@pytest.mark.unit
class TestListSessions:
    """Test session listing and pagination."""

    @pytest.mark.asyncio
    async def test_list_returns_paginated_results(
        self,
        service: SupportSessionService,
        mock_db: AsyncMock,
    ) -> None:
        """List returns items with total count."""
        sessions = [_make_session(), _make_session()]
        mock_db.scalar.return_value = 2

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = sessions
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        items, total = await service.list_sessions(limit=20, offset=0)

        assert total == 2
        assert len(items) == 2

    @pytest.mark.asyncio
    async def test_list_clamps_limit(
        self,
        service: SupportSessionService,
        mock_db: AsyncMock,
    ) -> None:
        """Limit is clamped to [1, 100]."""
        mock_db.scalar.return_value = 0
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        # Should not raise even with extreme values
        await service.list_sessions(limit=500, offset=0)
        await service.list_sessions(limit=-5, offset=0)

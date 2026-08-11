"""Unit tests for the External Deletion Propagation Service.

Tests state transitions, retry logic, exponential backoff computation,
legal hold enforcement, and operator notification on exhausted retries.

No I/O — all DB operations are mocked.

Requirements: R105.1, R105.2, R105.3
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.models.external_deletion import (
    DeletionState,
    ExternalDeletionTracking,
    MAX_RETRY_ATTEMPTS,
)
from app.schemas.external_deletion import (
    ExternalDeletionCreate,
    ExternalDeletionListResponse,
    ExternalDeletionResponse,
    ExternalDeletionRetryResponse,
)
from app.services.external_deletion_service import (
    BASE_BACKOFF_SECONDS,
    DeletionNotFoundError,
    DeletionRetryExhaustedError,
    DeletionStateTransitionError,
    ExternalDeletionService,
    VALID_TRANSITIONS,
    compute_backoff_seconds,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def org_id() -> UUID:
    """Standard org_id for tests."""
    return uuid4()


@pytest.fixture
def asset_id() -> UUID:
    """Standard asset_id for tests."""
    return uuid4()


@pytest.fixture
def mock_db() -> AsyncMock:
    """Mock AsyncSession that simulates flush/execute/scalar calls."""
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock()
    db.scalar = AsyncMock()
    return db


@pytest.fixture
def service(mock_db: AsyncMock) -> ExternalDeletionService:
    """ExternalDeletionService with mocked DB."""
    return ExternalDeletionService(mock_db)


def _make_record(
    org_id: UUID,
    asset_id: UUID,
    state: DeletionState = DeletionState.REMOVED_FROM_STUDIO,
    retry_count: int = 0,
    **kwargs,
) -> ExternalDeletionTracking:
    """Helper to create a mock ExternalDeletionTracking record."""
    record = MagicMock(spec=ExternalDeletionTracking)
    record.id = uuid4()
    record.org_id = org_id
    record.asset_id = asset_id
    record.storage_key = f"{org_id}/assets/{asset_id}/output.webp"
    record.deletion_state = state.value
    record.provider = "b2"
    record.requested_at = None
    record.confirmed_at = None
    record.failed_at = None
    record.retry_count = retry_count
    record.last_error = None
    record.legal_hold_ref = None
    record.created_at = datetime.now(UTC)
    record.updated_at = datetime.now(UTC)
    for key, value in kwargs.items():
        setattr(record, key, value)
    return record


# =============================================================================
# DeletionState Enum Tests
# =============================================================================


@pytest.mark.unit
class TestDeletionStateEnum:
    """Tests for the DeletionState enum values."""

    def test_all_states_defined(self) -> None:
        """All 6 required deletion states exist."""
        expected = {
            "removed_from_studio",
            "external_deletion_requested",
            "external_deletion_confirmed",
            "external_deletion_failed",
            "retained_legal_hold",
            "retained_backup",
        }
        actual = {s.value for s in DeletionState}
        assert actual == expected

    def test_state_string_values(self) -> None:
        """State values are lowercase snake_case strings."""
        for state in DeletionState:
            assert state.value == state.value.lower()
            assert " " not in state.value


# =============================================================================
# Valid Transitions Tests
# =============================================================================


@pytest.mark.unit
class TestValidTransitions:
    """Tests for the state transition map."""

    def test_removed_can_transition_to_requested(self) -> None:
        """REMOVED_FROM_STUDIO → EXTERNAL_DELETION_REQUESTED is valid."""
        allowed = VALID_TRANSITIONS[DeletionState.REMOVED_FROM_STUDIO]
        assert DeletionState.EXTERNAL_DELETION_REQUESTED in allowed

    def test_removed_can_transition_to_legal_hold(self) -> None:
        """REMOVED_FROM_STUDIO → RETAINED_LEGAL_HOLD is valid."""
        allowed = VALID_TRANSITIONS[DeletionState.REMOVED_FROM_STUDIO]
        assert DeletionState.RETAINED_LEGAL_HOLD in allowed

    def test_removed_can_transition_to_backup(self) -> None:
        """REMOVED_FROM_STUDIO → RETAINED_BACKUP is valid."""
        allowed = VALID_TRANSITIONS[DeletionState.REMOVED_FROM_STUDIO]
        assert DeletionState.RETAINED_BACKUP in allowed

    def test_requested_can_transition_to_confirmed(self) -> None:
        """EXTERNAL_DELETION_REQUESTED → EXTERNAL_DELETION_CONFIRMED is valid."""
        allowed = VALID_TRANSITIONS[DeletionState.EXTERNAL_DELETION_REQUESTED]
        assert DeletionState.EXTERNAL_DELETION_CONFIRMED in allowed

    def test_requested_can_transition_to_failed(self) -> None:
        """EXTERNAL_DELETION_REQUESTED → EXTERNAL_DELETION_FAILED is valid."""
        allowed = VALID_TRANSITIONS[DeletionState.EXTERNAL_DELETION_REQUESTED]
        assert DeletionState.EXTERNAL_DELETION_FAILED in allowed

    def test_failed_can_transition_to_requested(self) -> None:
        """EXTERNAL_DELETION_FAILED → EXTERNAL_DELETION_REQUESTED (retry) is valid."""
        allowed = VALID_TRANSITIONS[DeletionState.EXTERNAL_DELETION_FAILED]
        assert DeletionState.EXTERNAL_DELETION_REQUESTED in allowed

    def test_legal_hold_can_transition_to_requested(self) -> None:
        """RETAINED_LEGAL_HOLD → EXTERNAL_DELETION_REQUESTED is valid (hold released)."""
        allowed = VALID_TRANSITIONS[DeletionState.RETAINED_LEGAL_HOLD]
        assert DeletionState.EXTERNAL_DELETION_REQUESTED in allowed

    def test_confirmed_is_terminal(self) -> None:
        """EXTERNAL_DELETION_CONFIRMED has no outbound transitions."""
        allowed = VALID_TRANSITIONS[DeletionState.EXTERNAL_DELETION_CONFIRMED]
        assert allowed == set()

    def test_backup_is_terminal(self) -> None:
        """RETAINED_BACKUP has no outbound transitions."""
        allowed = VALID_TRANSITIONS[DeletionState.RETAINED_BACKUP]
        assert allowed == set()


# =============================================================================
# Backoff Computation Tests
# =============================================================================


@pytest.mark.unit
class TestBackoffComputation:
    """Tests for exponential backoff calculation."""

    def test_first_retry_is_base(self) -> None:
        """First retry uses base delay (30s)."""
        assert compute_backoff_seconds(0) == BASE_BACKOFF_SECONDS

    def test_second_retry_doubles(self) -> None:
        """Second retry doubles the delay."""
        assert compute_backoff_seconds(1) == BASE_BACKOFF_SECONDS * 2

    def test_third_retry_quadruples(self) -> None:
        """Third retry quadruples base delay."""
        assert compute_backoff_seconds(2) == BASE_BACKOFF_SECONDS * 4

    def test_capped_at_one_hour(self) -> None:
        """Backoff is capped at 3600 seconds (1 hour)."""
        # 30 * 2^7 = 3840, should be capped to 3600
        assert compute_backoff_seconds(7) == 3600.0

    def test_very_high_retry_count_stays_capped(self) -> None:
        """Even extremely high retry counts stay at 1 hour cap."""
        assert compute_backoff_seconds(100) == 3600.0


# =============================================================================
# Service.create() Tests
# =============================================================================


@pytest.mark.unit
class TestExternalDeletionServiceCreate:
    """Tests for ExternalDeletionService.create()."""

    @pytest.mark.asyncio
    async def test_create_sets_initial_state(
        self, service: ExternalDeletionService, mock_db: AsyncMock, org_id: UUID, asset_id: UUID
    ) -> None:
        """Creating a record sets REMOVED_FROM_STUDIO as initial state."""
        data = ExternalDeletionCreate(
            asset_id=asset_id,
            storage_key=f"{org_id}/assets/{asset_id}/output.webp",
            provider="b2",
        )

        record = await service.create(org_id, data)

        mock_db.add.assert_called_once()
        mock_db.flush.assert_awaited_once()
        assert record.deletion_state == DeletionState.REMOVED_FROM_STUDIO.value
        assert record.retry_count == 0

    @pytest.mark.asyncio
    async def test_create_with_legal_hold_sets_retained_state(
        self, service: ExternalDeletionService, mock_db: AsyncMock, org_id: UUID, asset_id: UUID
    ) -> None:
        """Creating with legal_hold_ref sets RETAINED_LEGAL_HOLD state."""
        data = ExternalDeletionCreate(
            asset_id=asset_id,
            storage_key=f"{org_id}/assets/{asset_id}/output.webp",
            provider="b2",
            legal_hold_ref="CASE-2024-001",
        )

        record = await service.create(org_id, data)

        assert record.deletion_state == DeletionState.RETAINED_LEGAL_HOLD.value
        assert record.legal_hold_ref == "CASE-2024-001"

    @pytest.mark.asyncio
    async def test_create_sets_org_id(
        self, service: ExternalDeletionService, mock_db: AsyncMock, org_id: UUID, asset_id: UUID
    ) -> None:
        """Created record has correct org_id for tenant isolation."""
        data = ExternalDeletionCreate(
            asset_id=asset_id,
            storage_key="test/key.webp",
            provider="b2",
        )

        record = await service.create(org_id, data)

        assert record.org_id == org_id


# =============================================================================
# Service.request_deletion() Tests
# =============================================================================


@pytest.mark.unit
class TestExternalDeletionServiceRequestDeletion:
    """Tests for ExternalDeletionService.request_deletion()."""

    @pytest.mark.asyncio
    async def test_request_deletion_transitions_from_removed(
        self, service: ExternalDeletionService, mock_db: AsyncMock, org_id: UUID, asset_id: UUID
    ) -> None:
        """Requesting deletion transitions from REMOVED_FROM_STUDIO to REQUESTED."""
        record = _make_record(org_id, asset_id, DeletionState.REMOVED_FROM_STUDIO)
        record_id = record.id

        # Mock the _get_record lookup
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = record
        mock_db.execute.return_value = mock_result

        result = await service.request_deletion(record_id, org_id)

        assert result.deletion_state == DeletionState.EXTERNAL_DELETION_REQUESTED.value
        assert result.requested_at is not None

    @pytest.mark.asyncio
    async def test_request_deletion_from_confirmed_raises(
        self, service: ExternalDeletionService, mock_db: AsyncMock, org_id: UUID, asset_id: UUID
    ) -> None:
        """Cannot request deletion from CONFIRMED state (terminal)."""
        record = _make_record(org_id, asset_id, DeletionState.EXTERNAL_DELETION_CONFIRMED)
        record_id = record.id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = record
        mock_db.execute.return_value = mock_result

        with pytest.raises(DeletionStateTransitionError):
            await service.request_deletion(record_id, org_id)


# =============================================================================
# Service.confirm_deletion() Tests
# =============================================================================


@pytest.mark.unit
class TestExternalDeletionServiceConfirmDeletion:
    """Tests for ExternalDeletionService.confirm_deletion()."""

    @pytest.mark.asyncio
    async def test_confirm_only_from_requested_state(
        self, service: ExternalDeletionService, mock_db: AsyncMock, org_id: UUID, asset_id: UUID
    ) -> None:
        """Confirmation only valid from EXTERNAL_DELETION_REQUESTED state."""
        record = _make_record(org_id, asset_id, DeletionState.EXTERNAL_DELETION_REQUESTED)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = record
        mock_db.execute.return_value = mock_result

        result = await service.confirm_deletion(record.id, org_id)

        assert result.deletion_state == DeletionState.EXTERNAL_DELETION_CONFIRMED.value
        assert result.confirmed_at is not None

    @pytest.mark.asyncio
    async def test_confirm_from_removed_raises(
        self, service: ExternalDeletionService, mock_db: AsyncMock, org_id: UUID, asset_id: UUID
    ) -> None:
        """Cannot confirm deletion from REMOVED_FROM_STUDIO (must request first)."""
        record = _make_record(org_id, asset_id, DeletionState.REMOVED_FROM_STUDIO)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = record
        mock_db.execute.return_value = mock_result

        with pytest.raises(DeletionStateTransitionError):
            await service.confirm_deletion(record.id, org_id)


# =============================================================================
# Service.mark_failed() Tests
# =============================================================================


@pytest.mark.unit
class TestExternalDeletionServiceMarkFailed:
    """Tests for ExternalDeletionService.mark_failed()."""

    @pytest.mark.asyncio
    async def test_mark_failed_increments_retry_count(
        self, service: ExternalDeletionService, mock_db: AsyncMock, org_id: UUID, asset_id: UUID
    ) -> None:
        """Marking as failed increments the retry counter."""
        record = _make_record(
            org_id, asset_id, DeletionState.EXTERNAL_DELETION_REQUESTED, retry_count=2
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = record
        mock_db.execute.return_value = mock_result

        result = await service.mark_failed(record.id, org_id, "Connection timeout")

        assert result.deletion_state == DeletionState.EXTERNAL_DELETION_FAILED.value
        assert result.retry_count == 3
        assert result.last_error == "Connection timeout"
        assert result.failed_at is not None

    @pytest.mark.asyncio
    async def test_mark_failed_truncates_long_error(
        self, service: ExternalDeletionService, mock_db: AsyncMock, org_id: UUID, asset_id: UUID
    ) -> None:
        """Error messages are truncated to 2000 characters."""
        record = _make_record(
            org_id, asset_id, DeletionState.EXTERNAL_DELETION_REQUESTED, retry_count=0
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = record
        mock_db.execute.return_value = mock_result

        long_error = "x" * 5000
        result = await service.mark_failed(record.id, org_id, long_error)

        assert len(result.last_error) == 2000

    @pytest.mark.asyncio
    async def test_mark_failed_notifies_operators_at_max_retries(
        self, service: ExternalDeletionService, mock_db: AsyncMock, org_id: UUID, asset_id: UUID
    ) -> None:
        """When retry_count reaches MAX_RETRY_ATTEMPTS, operators are notified."""
        record = _make_record(
            org_id,
            asset_id,
            DeletionState.EXTERNAL_DELETION_REQUESTED,
            retry_count=MAX_RETRY_ATTEMPTS - 1,  # Will become MAX after increment
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = record
        mock_db.execute.return_value = mock_result

        with patch.object(
            service, "_notify_operators_deletion_failed", new_callable=AsyncMock
        ) as mock_notify:
            await service.mark_failed(record.id, org_id, "B2 API error")
            mock_notify.assert_awaited_once_with(record)

    @pytest.mark.asyncio
    async def test_mark_failed_does_not_notify_below_max(
        self, service: ExternalDeletionService, mock_db: AsyncMock, org_id: UUID, asset_id: UUID
    ) -> None:
        """Operators are NOT notified when retry_count < MAX_RETRY_ATTEMPTS."""
        record = _make_record(
            org_id,
            asset_id,
            DeletionState.EXTERNAL_DELETION_REQUESTED,
            retry_count=1,  # Will become 2, well below max
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = record
        mock_db.execute.return_value = mock_result

        with patch.object(
            service, "_notify_operators_deletion_failed", new_callable=AsyncMock
        ) as mock_notify:
            await service.mark_failed(record.id, org_id, "Transient error")
            mock_notify.assert_not_awaited()


# =============================================================================
# Service.retry_deletion() Tests
# =============================================================================


@pytest.mark.unit
class TestExternalDeletionServiceRetryDeletion:
    """Tests for ExternalDeletionService.retry_deletion()."""

    @pytest.mark.asyncio
    async def test_retry_transitions_failed_to_requested(
        self, service: ExternalDeletionService, mock_db: AsyncMock, org_id: UUID, asset_id: UUID
    ) -> None:
        """Retrying transitions FAILED → REQUESTED."""
        record = _make_record(org_id, asset_id, DeletionState.EXTERNAL_DELETION_FAILED)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = record
        mock_db.execute.return_value = mock_result

        result = await service.retry_deletion(record.id, org_id)

        assert result.deletion_state == DeletionState.EXTERNAL_DELETION_REQUESTED.value
        assert result.requested_at is not None

    @pytest.mark.asyncio
    async def test_retry_from_confirmed_raises(
        self, service: ExternalDeletionService, mock_db: AsyncMock, org_id: UUID, asset_id: UUID
    ) -> None:
        """Cannot retry from CONFIRMED (terminal state)."""
        record = _make_record(org_id, asset_id, DeletionState.EXTERNAL_DELETION_CONFIRMED)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = record
        mock_db.execute.return_value = mock_result

        with pytest.raises(DeletionStateTransitionError):
            await service.retry_deletion(record.id, org_id)

    @pytest.mark.asyncio
    async def test_retry_not_found_raises(
        self, service: ExternalDeletionService, mock_db: AsyncMock, org_id: UUID, asset_id: UUID
    ) -> None:
        """Retrying a non-existent record raises DeletionNotFoundError."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(DeletionNotFoundError):
            await service.retry_deletion(uuid4(), org_id)


# =============================================================================
# Service.place_legal_hold() Tests
# =============================================================================


@pytest.mark.unit
class TestExternalDeletionServiceLegalHold:
    """Tests for legal hold placement and release."""

    @pytest.mark.asyncio
    async def test_place_hold_from_removed(
        self, service: ExternalDeletionService, mock_db: AsyncMock, org_id: UUID, asset_id: UUID
    ) -> None:
        """Legal hold can be placed from REMOVED_FROM_STUDIO."""
        record = _make_record(org_id, asset_id, DeletionState.REMOVED_FROM_STUDIO)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = record
        mock_db.execute.return_value = mock_result

        result = await service.place_legal_hold(record.id, org_id, "CASE-123")

        assert result.deletion_state == DeletionState.RETAINED_LEGAL_HOLD.value
        assert result.legal_hold_ref == "CASE-123"

    @pytest.mark.asyncio
    async def test_release_hold_transitions_to_requested(
        self, service: ExternalDeletionService, mock_db: AsyncMock, org_id: UUID, asset_id: UUID
    ) -> None:
        """Releasing a hold transitions to EXTERNAL_DELETION_REQUESTED."""
        record = _make_record(
            org_id, asset_id, DeletionState.RETAINED_LEGAL_HOLD,
            legal_hold_ref="CASE-123"
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = record
        mock_db.execute.return_value = mock_result

        result = await service.release_legal_hold(record.id, org_id)

        assert result.deletion_state == DeletionState.EXTERNAL_DELETION_REQUESTED.value
        assert result.legal_hold_ref is None
        assert result.requested_at is not None

    @pytest.mark.asyncio
    async def test_place_hold_from_requested_raises(
        self, service: ExternalDeletionService, mock_db: AsyncMock, org_id: UUID, asset_id: UUID
    ) -> None:
        """Cannot place hold from REQUESTED state (already in progress)."""
        record = _make_record(org_id, asset_id, DeletionState.EXTERNAL_DELETION_REQUESTED)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = record
        mock_db.execute.return_value = mock_result

        with pytest.raises(DeletionStateTransitionError):
            await service.place_legal_hold(record.id, org_id, "CASE-999")


# =============================================================================
# Service.get() / Tenant Isolation Tests
# =============================================================================


@pytest.mark.unit
class TestExternalDeletionServiceGet:
    """Tests for service.get() tenant isolation."""

    @pytest.mark.asyncio
    async def test_get_returns_none_for_wrong_org(
        self, service: ExternalDeletionService, mock_db: AsyncMock, org_id: UUID
    ) -> None:
        """get() returns None when org_id doesn't match (prevents cross-tenant leakage)."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await service.get(uuid4(), org_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_returns_record_for_matching_org(
        self, service: ExternalDeletionService, mock_db: AsyncMock, org_id: UUID, asset_id: UUID
    ) -> None:
        """get() returns the record when org_id matches."""
        record = _make_record(org_id, asset_id)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = record
        mock_db.execute.return_value = mock_result

        result = await service.get(record.id, org_id)

        assert result is not None
        assert result.org_id == org_id


# =============================================================================
# Invariant Tests (R105.2 — never claim deleted without confirmation)
# =============================================================================


@pytest.mark.unit
class TestDeletionInvariants:
    """Tests verifying R105.2: never claim deleted without confirmation."""

    def test_confirmed_requires_requested_first(self) -> None:
        """CONFIRMED can only be reached from REQUESTED (not directly from REMOVED)."""
        # REMOVED_FROM_STUDIO cannot transition directly to CONFIRMED
        allowed_from_removed = VALID_TRANSITIONS[DeletionState.REMOVED_FROM_STUDIO]
        assert DeletionState.EXTERNAL_DELETION_CONFIRMED not in allowed_from_removed

    def test_no_shortcut_to_confirmed(self) -> None:
        """Only EXTERNAL_DELETION_REQUESTED can transition to CONFIRMED."""
        for state, allowed in VALID_TRANSITIONS.items():
            if state == DeletionState.EXTERNAL_DELETION_REQUESTED:
                continue
            assert DeletionState.EXTERNAL_DELETION_CONFIRMED not in allowed, (
                f"State {state.value} should not transition to CONFIRMED"
            )

    def test_max_retry_attempts_is_positive(self) -> None:
        """MAX_RETRY_ATTEMPTS constant is a positive integer."""
        assert MAX_RETRY_ATTEMPTS > 0
        assert isinstance(MAX_RETRY_ATTEMPTS, int)


# =============================================================================
# Schema Validation Tests
# =============================================================================


@pytest.mark.unit
class TestExternalDeletionSchemas:
    """Tests for Pydantic schema validation."""

    def test_create_schema_requires_asset_id(self) -> None:
        """ExternalDeletionCreate requires asset_id."""
        with pytest.raises(Exception):
            ExternalDeletionCreate(
                storage_key="test/key.webp",
                provider="b2",
            )

    def test_create_schema_requires_storage_key(self) -> None:
        """ExternalDeletionCreate requires storage_key."""
        with pytest.raises(Exception):
            ExternalDeletionCreate(
                asset_id=uuid4(),
                provider="b2",
            )

    def test_create_schema_rejects_empty_storage_key(self) -> None:
        """ExternalDeletionCreate rejects empty storage_key."""
        with pytest.raises(Exception):
            ExternalDeletionCreate(
                asset_id=uuid4(),
                storage_key="",
                provider="b2",
            )

    def test_create_schema_defaults_provider_to_b2(self) -> None:
        """ExternalDeletionCreate defaults provider to 'b2'."""
        data = ExternalDeletionCreate(
            asset_id=uuid4(),
            storage_key="test/key.webp",
        )
        assert data.provider == "b2"

    def test_create_schema_legal_hold_optional(self) -> None:
        """ExternalDeletionCreate allows None legal_hold_ref."""
        data = ExternalDeletionCreate(
            asset_id=uuid4(),
            storage_key="test/key.webp",
        )
        assert data.legal_hold_ref is None

    def test_retry_response_schema(self) -> None:
        """ExternalDeletionRetryResponse validates correctly."""
        response = ExternalDeletionRetryResponse(
            id=uuid4(),
            deletion_state=DeletionState.EXTERNAL_DELETION_REQUESTED,
            retry_count=3,
            message="Retry initiated",
        )
        assert response.retry_count == 3
        assert response.deletion_state == DeletionState.EXTERNAL_DELETION_REQUESTED

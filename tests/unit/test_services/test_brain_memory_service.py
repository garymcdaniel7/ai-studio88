"""Unit tests for the Brain Memory Service.

Tests cover: R29.6 (provenance tracking), R29.7 (no silent promotion),
R29.8 (INFERRED/SUGGESTED require confidence), R29.11 (provenance hierarchy ordering).

No I/O, no DB — AsyncSession is fully mocked.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.brain_memory import BrainUserMemory
from app.services.brain_memory_service import (
    PROVENANCE_HIERARCHY,
    VALID_PROVENANCES,
    BrainMemoryService,
    BrainMemoryServiceError,
    InvalidProvenanceError,
    MemoryNotFoundError,
    MissingConfidenceError,
    ProvenanceDowngradeError,
    validate_provenance_transition,
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
    return db


@pytest.fixture
def service(mock_db: AsyncMock) -> BrainMemoryService:
    """Create a BrainMemoryService with mocked DB."""
    return BrainMemoryService(db=mock_db)


@pytest.fixture
def sample_org_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_memory_id() -> uuid.UUID:
    return uuid.uuid4()


# =============================================================================
# Tests: PROVENANCE_HIERARCHY and validate_provenance_transition
# =============================================================================


@pytest.mark.unit
class TestProvenanceHierarchy:
    """Test provenance hierarchy constants and validation."""

    def test_hierarchy_has_five_levels(self) -> None:
        """Provenance hierarchy contains exactly 5 levels."""
        assert len(PROVENANCE_HIERARCHY) == 5

    def test_hierarchy_ordering(self) -> None:
        """USER_CONFIRMED is highest, SUGGESTED is lowest."""
        assert PROVENANCE_HIERARCHY["USER_CONFIRMED"] > PROVENANCE_HIERARCHY["OBSERVED"]
        assert PROVENANCE_HIERARCHY["OBSERVED"] > PROVENANCE_HIERARCHY["IMPORTED"]
        assert PROVENANCE_HIERARCHY["IMPORTED"] > PROVENANCE_HIERARCHY["INFERRED"]
        assert PROVENANCE_HIERARCHY["INFERRED"] > PROVENANCE_HIERARCHY["SUGGESTED"]

    def test_valid_provenances_matches_hierarchy_keys(self) -> None:
        """VALID_PROVENANCES contains all hierarchy keys."""
        assert VALID_PROVENANCES == frozenset(PROVENANCE_HIERARCHY.keys())


@pytest.mark.unit
class TestValidateProvenanceTransition:
    """Test provenance transition validation — R29.7 (no silent promotion)."""

    def test_upgrade_is_valid(self) -> None:
        """Upgrading provenance (INFERRED → USER_CONFIRMED) is allowed."""
        assert validate_provenance_transition("INFERRED", "USER_CONFIRMED") is True

    def test_same_level_is_valid(self) -> None:
        """Keeping the same provenance level is allowed."""
        assert validate_provenance_transition("OBSERVED", "OBSERVED") is True

    def test_downgrade_is_invalid(self) -> None:
        """Downgrading provenance (USER_CONFIRMED → SUGGESTED) is rejected."""
        assert validate_provenance_transition("USER_CONFIRMED", "SUGGESTED") is False

    def test_all_upgrades_valid(self) -> None:
        """Every transition from lower to higher is valid."""
        assert validate_provenance_transition("SUGGESTED", "INFERRED") is True
        assert validate_provenance_transition("SUGGESTED", "IMPORTED") is True
        assert validate_provenance_transition("SUGGESTED", "OBSERVED") is True
        assert validate_provenance_transition("SUGGESTED", "USER_CONFIRMED") is True
        assert validate_provenance_transition("INFERRED", "IMPORTED") is True
        assert validate_provenance_transition("INFERRED", "OBSERVED") is True
        assert validate_provenance_transition("IMPORTED", "OBSERVED") is True
        assert validate_provenance_transition("OBSERVED", "USER_CONFIRMED") is True

    def test_all_downgrades_invalid(self) -> None:
        """Every transition from higher to lower is invalid."""
        assert validate_provenance_transition("USER_CONFIRMED", "OBSERVED") is False
        assert validate_provenance_transition("USER_CONFIRMED", "IMPORTED") is False
        assert validate_provenance_transition("USER_CONFIRMED", "INFERRED") is False
        assert validate_provenance_transition("USER_CONFIRMED", "SUGGESTED") is False
        assert validate_provenance_transition("OBSERVED", "IMPORTED") is False
        assert validate_provenance_transition("OBSERVED", "INFERRED") is False
        assert validate_provenance_transition("IMPORTED", "INFERRED") is False
        assert validate_provenance_transition("IMPORTED", "SUGGESTED") is False

    def test_invalid_old_provenance_raises(self) -> None:
        """Invalid old provenance raises InvalidProvenanceError."""
        with pytest.raises(InvalidProvenanceError):
            validate_provenance_transition("INVALID", "USER_CONFIRMED")

    def test_invalid_new_provenance_raises(self) -> None:
        """Invalid new provenance raises InvalidProvenanceError."""
        with pytest.raises(InvalidProvenanceError):
            validate_provenance_transition("OBSERVED", "BOGUS")


# =============================================================================
# Tests: create_memory
# =============================================================================


@pytest.mark.unit
class TestCreateMemory:
    """Test memory creation — R29.6, R29.8."""

    @pytest.mark.asyncio
    async def test_create_user_confirmed_memory(
        self, service: BrainMemoryService, mock_db: AsyncMock,
        sample_org_id: uuid.UUID, sample_user_id: uuid.UUID,
    ) -> None:
        """USER_CONFIRMED memory can be created without confidence."""
        result = await service.create_memory(
            org_id=sample_org_id,
            user_id=sample_user_id,
            memory_type="preference",
            content={"key": "style", "value": "minimalist"},
            provenance="USER_CONFIRMED",
        )

        assert result.org_id == sample_org_id
        assert result.user_id == sample_user_id
        assert result.memory_type == "preference"
        assert result.provenance == "USER_CONFIRMED"
        assert result.is_active is True
        assert result.confidence is None
        mock_db.add.assert_called_once()
        mock_db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_observed_memory(
        self, service: BrainMemoryService, mock_db: AsyncMock,
        sample_org_id: uuid.UUID, sample_user_id: uuid.UUID,
    ) -> None:
        """OBSERVED memory can be created without confidence."""
        result = await service.create_memory(
            org_id=sample_org_id,
            user_id=sample_user_id,
            memory_type="pattern",
            content={"pattern": "prefers_landscape"},
            provenance="OBSERVED",
        )

        assert result.provenance == "OBSERVED"
        assert result.confidence is None

    @pytest.mark.asyncio
    async def test_create_inferred_requires_confidence(
        self, service: BrainMemoryService,
        sample_org_id: uuid.UUID, sample_user_id: uuid.UUID,
    ) -> None:
        """INFERRED provenance without confidence raises MissingConfidenceError (R29.8)."""
        with pytest.raises(MissingConfidenceError) as exc_info:
            await service.create_memory(
                org_id=sample_org_id,
                user_id=sample_user_id,
                memory_type="pattern",
                content={"inferred": "likes_warm_tones"},
                provenance="INFERRED",
            )
        assert "confidence" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_create_suggested_requires_confidence(
        self, service: BrainMemoryService,
        sample_org_id: uuid.UUID, sample_user_id: uuid.UUID,
    ) -> None:
        """SUGGESTED provenance without confidence raises MissingConfidenceError (R29.8)."""
        with pytest.raises(MissingConfidenceError):
            await service.create_memory(
                org_id=sample_org_id,
                user_id=sample_user_id,
                memory_type="suggestion",
                content={"suggestion": "try_portrait_mode"},
                provenance="SUGGESTED",
            )

    @pytest.mark.asyncio
    async def test_create_inferred_with_confidence_succeeds(
        self, service: BrainMemoryService, mock_db: AsyncMock,
        sample_org_id: uuid.UUID, sample_user_id: uuid.UUID,
    ) -> None:
        """INFERRED with confidence score is accepted."""
        result = await service.create_memory(
            org_id=sample_org_id,
            user_id=sample_user_id,
            memory_type="pattern",
            content={"inferred": "prefers_cinematic"},
            provenance="INFERRED",
            confidence=0.85,
        )

        assert result.provenance == "INFERRED"
        assert result.confidence == Decimal("0.85")

    @pytest.mark.asyncio
    async def test_create_suggested_with_confidence_succeeds(
        self, service: BrainMemoryService, mock_db: AsyncMock,
        sample_org_id: uuid.UUID, sample_user_id: uuid.UUID,
    ) -> None:
        """SUGGESTED with confidence score is accepted."""
        result = await service.create_memory(
            org_id=sample_org_id,
            user_id=sample_user_id,
            memory_type="suggestion",
            content={"suggestion": "add_lighting"},
            provenance="SUGGESTED",
            confidence=Decimal("0.60"),
        )

        assert result.provenance == "SUGGESTED"
        assert result.confidence == Decimal("0.60")

    @pytest.mark.asyncio
    async def test_create_with_invalid_provenance_raises(
        self, service: BrainMemoryService,
        sample_org_id: uuid.UUID, sample_user_id: uuid.UUID,
    ) -> None:
        """Invalid provenance value raises InvalidProvenanceError."""
        with pytest.raises(InvalidProvenanceError) as exc_info:
            await service.create_memory(
                org_id=sample_org_id,
                user_id=sample_user_id,
                memory_type="preference",
                content={"key": "value"},
                provenance="HALLUCINATED",
            )
        assert "HALLUCINATED" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_create_with_source_conversation(
        self, service: BrainMemoryService, mock_db: AsyncMock,
        sample_org_id: uuid.UUID, sample_user_id: uuid.UUID,
    ) -> None:
        """Memory can reference source conversation."""
        conv_id = uuid.uuid4()
        result = await service.create_memory(
            org_id=sample_org_id,
            user_id=sample_user_id,
            memory_type="correction",
            content={"correction": "name_spelling"},
            provenance="USER_CONFIRMED",
            source_conversation_id=conv_id,
        )

        assert result.source_conversation_id == conv_id


# =============================================================================
# Tests: get_memory
# =============================================================================


@pytest.mark.unit
class TestGetMemory:
    """Test memory retrieval with tenant + user scoping."""

    @pytest.mark.asyncio
    async def test_get_existing_memory(
        self, service: BrainMemoryService, mock_db: AsyncMock,
        sample_org_id: uuid.UUID, sample_user_id: uuid.UUID,
        sample_memory_id: uuid.UUID,
    ) -> None:
        """Returns memory when found for correct org/user."""
        mock_memory = MagicMock(spec=BrainUserMemory)
        mock_memory.id = sample_memory_id
        mock_memory.org_id = sample_org_id
        mock_memory.user_id = sample_user_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_memory
        mock_db.execute.return_value = mock_result

        result = await service.get_memory(sample_memory_id, sample_org_id, sample_user_id)
        assert result == mock_memory

    @pytest.mark.asyncio
    async def test_get_nonexistent_memory_raises(
        self, service: BrainMemoryService, mock_db: AsyncMock,
        sample_org_id: uuid.UUID, sample_user_id: uuid.UUID,
    ) -> None:
        """Raises MemoryNotFoundError when memory does not exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(MemoryNotFoundError) as exc_info:
            await service.get_memory(uuid.uuid4(), sample_org_id, sample_user_id)
        assert exc_info.value.code == "MEMORY_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_get_wrong_org_returns_not_found(
        self, service: BrainMemoryService, mock_db: AsyncMock,
        sample_user_id: uuid.UUID, sample_memory_id: uuid.UUID,
    ) -> None:
        """Memory in different org returns MemoryNotFoundError (not 403)."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        wrong_org = uuid.uuid4()
        with pytest.raises(MemoryNotFoundError):
            await service.get_memory(sample_memory_id, wrong_org, sample_user_id)


# =============================================================================
# Tests: update_memory
# =============================================================================


@pytest.mark.unit
class TestUpdateMemory:
    """Test memory updates — provenance upgrade enforcement (R29.7)."""

    @pytest.mark.asyncio
    async def test_upgrade_provenance_succeeds(
        self, service: BrainMemoryService, mock_db: AsyncMock,
        sample_org_id: uuid.UUID, sample_user_id: uuid.UUID,
        sample_memory_id: uuid.UUID,
    ) -> None:
        """Upgrading from INFERRED to USER_CONFIRMED is allowed."""
        mock_memory = MagicMock(spec=BrainUserMemory)
        mock_memory.id = sample_memory_id
        mock_memory.org_id = sample_org_id
        mock_memory.user_id = sample_user_id
        mock_memory.provenance = "INFERRED"
        mock_memory.content = {"old": "data"}
        mock_memory.is_active = True

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_memory
        mock_db.execute.return_value = mock_result

        result = await service.update_memory(
            memory_id=sample_memory_id,
            org_id=sample_org_id,
            user_id=sample_user_id,
            provenance="USER_CONFIRMED",
        )

        assert result.provenance == "USER_CONFIRMED"

    @pytest.mark.asyncio
    async def test_downgrade_provenance_raises(
        self, service: BrainMemoryService, mock_db: AsyncMock,
        sample_org_id: uuid.UUID, sample_user_id: uuid.UUID,
        sample_memory_id: uuid.UUID,
    ) -> None:
        """Downgrading from USER_CONFIRMED to SUGGESTED is rejected (R29.7)."""
        mock_memory = MagicMock(spec=BrainUserMemory)
        mock_memory.id = sample_memory_id
        mock_memory.org_id = sample_org_id
        mock_memory.user_id = sample_user_id
        mock_memory.provenance = "USER_CONFIRMED"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_memory
        mock_db.execute.return_value = mock_result

        with pytest.raises(ProvenanceDowngradeError) as exc_info:
            await service.update_memory(
                memory_id=sample_memory_id,
                org_id=sample_org_id,
                user_id=sample_user_id,
                provenance="SUGGESTED",
            )
        assert "downgrade" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_update_content_only(
        self, service: BrainMemoryService, mock_db: AsyncMock,
        sample_org_id: uuid.UUID, sample_user_id: uuid.UUID,
        sample_memory_id: uuid.UUID,
    ) -> None:
        """Updating content without changing provenance succeeds."""
        mock_memory = MagicMock(spec=BrainUserMemory)
        mock_memory.id = sample_memory_id
        mock_memory.org_id = sample_org_id
        mock_memory.user_id = sample_user_id
        mock_memory.provenance = "OBSERVED"
        mock_memory.content = {"old": "value"}
        mock_memory.is_active = True

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_memory
        mock_db.execute.return_value = mock_result

        new_content = {"updated": "content"}
        result = await service.update_memory(
            memory_id=sample_memory_id,
            org_id=sample_org_id,
            user_id=sample_user_id,
            content=new_content,
        )

        assert result.content == new_content

    @pytest.mark.asyncio
    async def test_update_invalid_provenance_raises(
        self, service: BrainMemoryService, mock_db: AsyncMock,
        sample_org_id: uuid.UUID, sample_user_id: uuid.UUID,
        sample_memory_id: uuid.UUID,
    ) -> None:
        """Update with invalid provenance raises InvalidProvenanceError."""
        mock_memory = MagicMock(spec=BrainUserMemory)
        mock_memory.id = sample_memory_id
        mock_memory.org_id = sample_org_id
        mock_memory.user_id = sample_user_id
        mock_memory.provenance = "SUGGESTED"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_memory
        mock_db.execute.return_value = mock_result

        with pytest.raises(InvalidProvenanceError):
            await service.update_memory(
                memory_id=sample_memory_id,
                org_id=sample_org_id,
                user_id=sample_user_id,
                provenance="NOT_REAL",
            )


# =============================================================================
# Tests: deactivate_memory
# =============================================================================


@pytest.mark.unit
class TestDeactivateMemory:
    """Test soft-disable of memory items."""

    @pytest.mark.asyncio
    async def test_deactivate_sets_inactive(
        self, service: BrainMemoryService, mock_db: AsyncMock,
        sample_org_id: uuid.UUID, sample_user_id: uuid.UUID,
        sample_memory_id: uuid.UUID,
    ) -> None:
        """Deactivating sets is_active=False."""
        mock_memory = MagicMock(spec=BrainUserMemory)
        mock_memory.id = sample_memory_id
        mock_memory.org_id = sample_org_id
        mock_memory.user_id = sample_user_id
        mock_memory.provenance = "USER_CONFIRMED"
        mock_memory.is_active = True

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_memory
        mock_db.execute.return_value = mock_result

        result = await service.deactivate_memory(
            sample_memory_id, sample_org_id, sample_user_id
        )

        assert result.is_active is False


# =============================================================================
# Tests: delete_memory
# =============================================================================


@pytest.mark.unit
class TestDeleteMemory:
    """Test hard-delete of memory items."""

    @pytest.mark.asyncio
    async def test_delete_existing_memory(
        self, service: BrainMemoryService, mock_db: AsyncMock,
        sample_org_id: uuid.UUID, sample_user_id: uuid.UUID,
        sample_memory_id: uuid.UUID,
    ) -> None:
        """Deleting existing memory executes delete statement."""
        mock_memory = MagicMock(spec=BrainUserMemory)
        mock_memory.id = sample_memory_id
        mock_memory.org_id = sample_org_id
        mock_memory.user_id = sample_user_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_memory
        mock_db.execute.return_value = mock_result

        await service.delete_memory(sample_memory_id, sample_org_id, sample_user_id)

        # execute called twice: once for get_memory SELECT, once for DELETE
        assert mock_db.execute.await_count == 2
        assert mock_db.flush.await_count == 1

    @pytest.mark.asyncio
    async def test_delete_nonexistent_raises(
        self, service: BrainMemoryService, mock_db: AsyncMock,
        sample_org_id: uuid.UUID, sample_user_id: uuid.UUID,
    ) -> None:
        """Deleting nonexistent memory raises MemoryNotFoundError."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(MemoryNotFoundError):
            await service.delete_memory(uuid.uuid4(), sample_org_id, sample_user_id)


# =============================================================================
# Tests: list_user_memory
# =============================================================================


@pytest.mark.unit
class TestListUserMemory:
    """Test memory listing with filters."""

    @pytest.mark.asyncio
    async def test_list_returns_results(
        self, service: BrainMemoryService, mock_db: AsyncMock,
        sample_org_id: uuid.UUID, sample_user_id: uuid.UUID,
    ) -> None:
        """List returns memory items from the database."""
        mock_items = [MagicMock(spec=BrainUserMemory), MagicMock(spec=BrainUserMemory)]
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_items
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        results = await service.list_user_memory(sample_org_id, sample_user_id)
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_list_empty_returns_empty(
        self, service: BrainMemoryService, mock_db: AsyncMock,
        sample_org_id: uuid.UUID, sample_user_id: uuid.UUID,
    ) -> None:
        """List with no matching items returns empty sequence."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        results = await service.list_user_memory(sample_org_id, sample_user_id)
        assert len(results) == 0


# =============================================================================
# Tests: get_active_memory_for_context
# =============================================================================


@pytest.mark.unit
class TestGetActiveMemoryForContext:
    """Test context retrieval — R29.11 (provenance-ordered for injection)."""

    @pytest.mark.asyncio
    async def test_returns_active_memory(
        self, service: BrainMemoryService, mock_db: AsyncMock,
        sample_org_id: uuid.UUID, sample_user_id: uuid.UUID,
    ) -> None:
        """Active memory items are returned for context injection."""
        mock_items = [MagicMock(spec=BrainUserMemory)]
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_items
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        results = await service.get_active_memory_for_context(
            sample_org_id, sample_user_id
        )
        assert len(results) == 1
        mock_db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_respects_limit(
        self, service: BrainMemoryService, mock_db: AsyncMock,
        sample_org_id: uuid.UUID, sample_user_id: uuid.UUID,
    ) -> None:
        """Custom limit is passed through to the query."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        await service.get_active_memory_for_context(
            sample_org_id, sample_user_id, limit=5
        )
        # Verify the query was executed (limit is embedded in the SQL)
        mock_db.execute.assert_awaited_once()


# =============================================================================
# Tests: Exception hierarchy
# =============================================================================


@pytest.mark.unit
class TestExceptions:
    """Test exception class structure."""

    def test_base_error_has_message_and_code(self) -> None:
        """BrainMemoryServiceError carries message and code."""
        err = BrainMemoryServiceError("test error", "TEST_CODE")
        assert err.message == "test error"
        assert err.code == "TEST_CODE"
        assert str(err) == "test error"

    def test_memory_not_found_inherits_base(self) -> None:
        """MemoryNotFoundError is a BrainMemoryServiceError."""
        err = MemoryNotFoundError(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())
        assert isinstance(err, BrainMemoryServiceError)
        assert err.code == "MEMORY_NOT_FOUND"

    def test_invalid_provenance_includes_value(self) -> None:
        """InvalidProvenanceError message includes the bad value."""
        err = InvalidProvenanceError("BOGUS")
        assert "BOGUS" in err.message

    def test_provenance_downgrade_includes_both_levels(self) -> None:
        """ProvenanceDowngradeError message includes current and requested."""
        err = ProvenanceDowngradeError("USER_CONFIRMED", "SUGGESTED")
        assert "USER_CONFIRMED" in err.message
        assert "SUGGESTED" in err.message

    def test_missing_confidence_includes_provenance(self) -> None:
        """MissingConfidenceError message includes the provenance level."""
        err = MissingConfidenceError("INFERRED")
        assert "INFERRED" in err.message

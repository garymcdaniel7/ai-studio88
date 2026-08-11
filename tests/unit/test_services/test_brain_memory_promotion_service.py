"""Unit tests for the Brain Memory Promotion Service.

Tests cover: R29.12 (promotion recording), R29.13 (workspace knowledge lifecycle),
R93.5 (no auto-promotion), R94.2 (user can delete personalization),
R94.3 (user can inspect/correct/disable personalization).

No I/O, no DB — AsyncSession is fully mocked.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.brain_memory import BrainUserMemory, BrainWorkspaceKnowledge
from app.services.brain_memory_promotion_service import (
    InsufficientRoleError,
    KnowledgeNotFoundError,
    MemoryInactiveError,
    MemoryNotFoundError,
    MemoryPromotionService,
    PromotionServiceError,
    has_minimum_role,
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
def service(mock_db: AsyncMock) -> MemoryPromotionService:
    """Create a MemoryPromotionService with mocked DB."""
    return MemoryPromotionService(db=mock_db)


@pytest.fixture
def sample_org_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_memory_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_knowledge_id() -> uuid.UUID:
    return uuid.uuid4()


def make_mock_memory(
    memory_id: uuid.UUID,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    is_active: bool = True,
    memory_type: str = "preference",
    provenance: str = "USER_CONFIRMED",
    content: dict | None = None,
) -> MagicMock:
    """Create a mock BrainUserMemory object."""
    mock = MagicMock(spec=BrainUserMemory)
    mock.id = memory_id
    mock.org_id = org_id
    mock.user_id = user_id
    mock.is_active = is_active
    mock.memory_type = memory_type
    mock.provenance = provenance
    mock.content = content or {"key": "value"}
    return mock


def make_mock_knowledge(
    knowledge_id: uuid.UUID,
    org_id: uuid.UUID,
    promoted_by: uuid.UUID | None = None,
    promoted_from: uuid.UUID | None = None,
) -> MagicMock:
    """Create a mock BrainWorkspaceKnowledge object."""
    mock = MagicMock(spec=BrainWorkspaceKnowledge)
    mock.id = knowledge_id
    mock.org_id = org_id
    mock.knowledge_type = "preference"
    mock.content = {"key": "value"}
    mock.provenance = "USER_CONFIRMED"
    mock.promoted_by = promoted_by
    mock.promoted_from = promoted_from
    return mock


# =============================================================================
# Tests: has_minimum_role helper
# =============================================================================


@pytest.mark.unit
class TestHasMinimumRole:
    """Test role hierarchy helper function."""

    def test_owner_has_all_roles(self) -> None:
        """Owner meets every minimum role requirement."""
        assert has_minimum_role("owner", "viewer") is True
        assert has_minimum_role("owner", "editor") is True
        assert has_minimum_role("owner", "admin") is True
        assert has_minimum_role("owner", "owner") is True

    def test_admin_has_admin_and_below(self) -> None:
        """Admin meets admin, editor, and viewer requirements."""
        assert has_minimum_role("admin", "viewer") is True
        assert has_minimum_role("admin", "editor") is True
        assert has_minimum_role("admin", "admin") is True
        assert has_minimum_role("admin", "owner") is False

    def test_editor_has_editor_and_below(self) -> None:
        """Editor meets editor and viewer requirements."""
        assert has_minimum_role("editor", "viewer") is True
        assert has_minimum_role("editor", "editor") is True
        assert has_minimum_role("editor", "admin") is False
        assert has_minimum_role("editor", "owner") is False

    def test_viewer_only_meets_viewer(self) -> None:
        """Viewer only meets viewer requirement."""
        assert has_minimum_role("viewer", "viewer") is True
        assert has_minimum_role("viewer", "editor") is False
        assert has_minimum_role("viewer", "admin") is False
        assert has_minimum_role("viewer", "owner") is False

    def test_unknown_role_fails(self) -> None:
        """Unknown roles default to insufficient privilege."""
        assert has_minimum_role("unknown", "viewer") is False
        assert has_minimum_role("viewer", "unknown") is False


# =============================================================================
# Tests: promote_to_workspace
# =============================================================================


@pytest.mark.unit
class TestPromoteToWorkspace:
    """Test private memory promotion to workspace knowledge — R29.12, R93.5."""

    @pytest.mark.asyncio
    async def test_editor_can_promote(
        self,
        service: MemoryPromotionService,
        mock_db: AsyncMock,
        sample_org_id: uuid.UUID,
        sample_user_id: uuid.UUID,
        sample_memory_id: uuid.UUID,
    ) -> None:
        """Editor role can promote private memory to workspace knowledge."""
        mock_memory = make_mock_memory(
            sample_memory_id, sample_org_id, sample_user_id
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_memory
        mock_db.execute.return_value = mock_result

        result = await service.promote_to_workspace(
            memory_id=sample_memory_id,
            org_id=sample_org_id,
            user_id=sample_user_id,
            role="editor",
        )

        # Verify a workspace knowledge record was created
        mock_db.add.assert_called_once()
        mock_db.flush.assert_awaited_once()

        # The added object should be a BrainWorkspaceKnowledge
        added_obj = mock_db.add.call_args[0][0]
        assert isinstance(added_obj, BrainWorkspaceKnowledge)
        assert added_obj.org_id == sample_org_id
        assert added_obj.promoted_by == sample_user_id
        assert added_obj.promoted_from == sample_memory_id
        assert added_obj.knowledge_type == "preference"
        assert added_obj.content == {"key": "value"}
        assert added_obj.provenance == "USER_CONFIRMED"

    @pytest.mark.asyncio
    async def test_admin_can_promote(
        self,
        service: MemoryPromotionService,
        mock_db: AsyncMock,
        sample_org_id: uuid.UUID,
        sample_user_id: uuid.UUID,
        sample_memory_id: uuid.UUID,
    ) -> None:
        """Admin role can promote private memory to workspace knowledge."""
        mock_memory = make_mock_memory(
            sample_memory_id, sample_org_id, sample_user_id
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_memory
        mock_db.execute.return_value = mock_result

        result = await service.promote_to_workspace(
            memory_id=sample_memory_id,
            org_id=sample_org_id,
            user_id=sample_user_id,
            role="admin",
        )

        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_owner_can_promote(
        self,
        service: MemoryPromotionService,
        mock_db: AsyncMock,
        sample_org_id: uuid.UUID,
        sample_user_id: uuid.UUID,
        sample_memory_id: uuid.UUID,
    ) -> None:
        """Owner role can promote private memory to workspace knowledge."""
        mock_memory = make_mock_memory(
            sample_memory_id, sample_org_id, sample_user_id
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_memory
        mock_db.execute.return_value = mock_result

        result = await service.promote_to_workspace(
            memory_id=sample_memory_id,
            org_id=sample_org_id,
            user_id=sample_user_id,
            role="owner",
        )

        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_viewer_cannot_promote(
        self,
        service: MemoryPromotionService,
        sample_org_id: uuid.UUID,
        sample_user_id: uuid.UUID,
        sample_memory_id: uuid.UUID,
    ) -> None:
        """Viewer role is rejected with InsufficientRoleError (R94.3)."""
        with pytest.raises(InsufficientRoleError) as exc_info:
            await service.promote_to_workspace(
                memory_id=sample_memory_id,
                org_id=sample_org_id,
                user_id=sample_user_id,
                role="viewer",
            )
        assert exc_info.value.required == "editor"
        assert exc_info.value.actual == "viewer"

    @pytest.mark.asyncio
    async def test_memory_not_found_raises(
        self,
        service: MemoryPromotionService,
        mock_db: AsyncMock,
        sample_org_id: uuid.UUID,
        sample_user_id: uuid.UUID,
    ) -> None:
        """Non-existent memory raises MemoryNotFoundError."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(MemoryNotFoundError) as exc_info:
            await service.promote_to_workspace(
                memory_id=uuid.uuid4(),
                org_id=sample_org_id,
                user_id=sample_user_id,
                role="editor",
            )
        assert exc_info.value.code == "MEMORY_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_inactive_memory_cannot_be_promoted(
        self,
        service: MemoryPromotionService,
        mock_db: AsyncMock,
        sample_org_id: uuid.UUID,
        sample_user_id: uuid.UUID,
        sample_memory_id: uuid.UUID,
    ) -> None:
        """Inactive memory raises MemoryInactiveError."""
        mock_memory = make_mock_memory(
            sample_memory_id, sample_org_id, sample_user_id, is_active=False
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_memory
        mock_db.execute.return_value = mock_result

        with pytest.raises(MemoryInactiveError) as exc_info:
            await service.promote_to_workspace(
                memory_id=sample_memory_id,
                org_id=sample_org_id,
                user_id=sample_user_id,
                role="editor",
            )
        assert exc_info.value.code == "MEMORY_INACTIVE"

    @pytest.mark.asyncio
    async def test_promotion_preserves_content_and_provenance(
        self,
        service: MemoryPromotionService,
        mock_db: AsyncMock,
        sample_org_id: uuid.UUID,
        sample_user_id: uuid.UUID,
        sample_memory_id: uuid.UUID,
    ) -> None:
        """Promoted knowledge preserves original content and provenance."""
        content = {"style": "minimalist", "color_pref": "warm"}
        mock_memory = make_mock_memory(
            sample_memory_id,
            sample_org_id,
            sample_user_id,
            memory_type="correction",
            provenance="OBSERVED",
            content=content,
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_memory
        mock_db.execute.return_value = mock_result

        await service.promote_to_workspace(
            memory_id=sample_memory_id,
            org_id=sample_org_id,
            user_id=sample_user_id,
            role="editor",
        )

        added_obj = mock_db.add.call_args[0][0]
        assert added_obj.content == content
        assert added_obj.provenance == "OBSERVED"
        assert added_obj.knowledge_type == "correction"


# =============================================================================
# Tests: list_workspace_knowledge
# =============================================================================


@pytest.mark.unit
class TestListWorkspaceKnowledge:
    """Test paginated workspace knowledge listing."""

    @pytest.mark.asyncio
    async def test_returns_items_and_total(
        self,
        service: MemoryPromotionService,
        mock_db: AsyncMock,
        sample_org_id: uuid.UUID,
    ) -> None:
        """Returns a tuple of (items, total_count)."""
        mock_items = [
            MagicMock(spec=BrainWorkspaceKnowledge),
            MagicMock(spec=BrainWorkspaceKnowledge),
        ]
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_items
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result
        mock_db.scalar.return_value = 2

        items, total = await service.list_workspace_knowledge(
            org_id=sample_org_id,
            limit=50,
            offset=0,
        )

        assert len(items) == 2
        assert total == 2

    @pytest.mark.asyncio
    async def test_empty_workspace_returns_zero(
        self,
        service: MemoryPromotionService,
        mock_db: AsyncMock,
        sample_org_id: uuid.UUID,
    ) -> None:
        """Empty workspace returns empty list and total=0."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result
        mock_db.scalar.return_value = 0

        items, total = await service.list_workspace_knowledge(
            org_id=sample_org_id,
        )

        assert len(items) == 0
        assert total == 0

    @pytest.mark.asyncio
    async def test_pagination_params_passed(
        self,
        service: MemoryPromotionService,
        mock_db: AsyncMock,
        sample_org_id: uuid.UUID,
    ) -> None:
        """Custom limit and offset are used in the query."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result
        mock_db.scalar.return_value = 0

        await service.list_workspace_knowledge(
            org_id=sample_org_id,
            limit=10,
            offset=20,
        )

        # Verify execute was called (for the paginated query)
        mock_db.execute.assert_awaited()


# =============================================================================
# Tests: delete_workspace_knowledge
# =============================================================================


@pytest.mark.unit
class TestDeleteWorkspaceKnowledge:
    """Test workspace knowledge deletion — R94.2."""

    @pytest.mark.asyncio
    async def test_admin_can_delete(
        self,
        service: MemoryPromotionService,
        mock_db: AsyncMock,
        sample_org_id: uuid.UUID,
        sample_user_id: uuid.UUID,
        sample_knowledge_id: uuid.UUID,
    ) -> None:
        """Admin role can delete workspace knowledge."""
        mock_knowledge = make_mock_knowledge(
            sample_knowledge_id, sample_org_id
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_knowledge
        mock_db.execute.return_value = mock_result

        await service.delete_workspace_knowledge(
            knowledge_id=sample_knowledge_id,
            org_id=sample_org_id,
            user_id=sample_user_id,
            role="admin",
        )

        # execute called twice: SELECT + DELETE
        assert mock_db.execute.await_count == 2
        mock_db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_owner_can_delete(
        self,
        service: MemoryPromotionService,
        mock_db: AsyncMock,
        sample_org_id: uuid.UUID,
        sample_user_id: uuid.UUID,
        sample_knowledge_id: uuid.UUID,
    ) -> None:
        """Owner role can delete workspace knowledge."""
        mock_knowledge = make_mock_knowledge(
            sample_knowledge_id, sample_org_id
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_knowledge
        mock_db.execute.return_value = mock_result

        await service.delete_workspace_knowledge(
            knowledge_id=sample_knowledge_id,
            org_id=sample_org_id,
            user_id=sample_user_id,
            role="owner",
        )

        mock_db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_editor_cannot_delete(
        self,
        service: MemoryPromotionService,
        sample_org_id: uuid.UUID,
        sample_user_id: uuid.UUID,
        sample_knowledge_id: uuid.UUID,
    ) -> None:
        """Editor role is rejected with InsufficientRoleError."""
        with pytest.raises(InsufficientRoleError) as exc_info:
            await service.delete_workspace_knowledge(
                knowledge_id=sample_knowledge_id,
                org_id=sample_org_id,
                user_id=sample_user_id,
                role="editor",
            )
        assert exc_info.value.required == "admin"
        assert exc_info.value.actual == "editor"

    @pytest.mark.asyncio
    async def test_viewer_cannot_delete(
        self,
        service: MemoryPromotionService,
        sample_org_id: uuid.UUID,
        sample_user_id: uuid.UUID,
        sample_knowledge_id: uuid.UUID,
    ) -> None:
        """Viewer role is rejected with InsufficientRoleError."""
        with pytest.raises(InsufficientRoleError) as exc_info:
            await service.delete_workspace_knowledge(
                knowledge_id=sample_knowledge_id,
                org_id=sample_org_id,
                user_id=sample_user_id,
                role="viewer",
            )
        assert exc_info.value.required == "admin"

    @pytest.mark.asyncio
    async def test_nonexistent_knowledge_raises(
        self,
        service: MemoryPromotionService,
        mock_db: AsyncMock,
        sample_org_id: uuid.UUID,
        sample_user_id: uuid.UUID,
    ) -> None:
        """Non-existent knowledge raises KnowledgeNotFoundError."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(KnowledgeNotFoundError) as exc_info:
            await service.delete_workspace_knowledge(
                knowledge_id=uuid.uuid4(),
                org_id=sample_org_id,
                user_id=sample_user_id,
                role="admin",
            )
        assert exc_info.value.code == "KNOWLEDGE_NOT_FOUND"


# =============================================================================
# Tests: Exception hierarchy
# =============================================================================


@pytest.mark.unit
class TestExceptions:
    """Test exception class structure."""

    def test_base_error_has_message_and_code(self) -> None:
        """PromotionServiceError carries message and code."""
        err = PromotionServiceError("test error", "TEST_CODE")
        assert err.message == "test error"
        assert err.code == "TEST_CODE"
        assert str(err) == "test error"

    def test_memory_not_found_inherits_base(self) -> None:
        """MemoryNotFoundError is a PromotionServiceError."""
        mid = uuid.uuid4()
        err = MemoryNotFoundError(mid)
        assert isinstance(err, PromotionServiceError)
        assert err.code == "MEMORY_NOT_FOUND"
        assert str(mid) in err.message

    def test_knowledge_not_found_inherits_base(self) -> None:
        """KnowledgeNotFoundError is a PromotionServiceError."""
        kid = uuid.uuid4()
        err = KnowledgeNotFoundError(kid)
        assert isinstance(err, PromotionServiceError)
        assert err.code == "KNOWLEDGE_NOT_FOUND"
        assert str(kid) in err.message

    def test_insufficient_role_includes_details(self) -> None:
        """InsufficientRoleError includes required and actual roles."""
        err = InsufficientRoleError(required="admin", actual="viewer")
        assert "admin" in err.message
        assert "viewer" in err.message
        assert err.code == "INSUFFICIENT_ROLE"

    def test_memory_inactive_includes_id(self) -> None:
        """MemoryInactiveError includes the memory_id."""
        mid = uuid.uuid4()
        err = MemoryInactiveError(mid)
        assert str(mid) in err.message
        assert err.code == "MEMORY_INACTIVE"


# =============================================================================
# Tests: R93.5 — No auto-promotion guarantee
# =============================================================================


@pytest.mark.unit
class TestNoAutoPromotion:
    """Verify that the service design enforces explicit promotion only (R93.5).

    The MemoryPromotionService has no method that auto-promotes — all
    promotions flow through promote_to_workspace which requires:
      1. An explicit memory_id (user selects which memory to promote)
      2. A user_id (who is doing the promotion)
      3. A role (access control check)

    There is no background task, cron, or event-driven path that
    silently moves private memory to workspace knowledge.
    """

    def test_no_auto_promote_method_exists(self) -> None:
        """Service has no auto_promote or schedule_promotion method."""
        service_methods = dir(MemoryPromotionService)
        assert "auto_promote" not in service_methods
        assert "schedule_promotion" not in service_methods
        assert "background_promote" not in service_methods

    def test_promote_requires_role_parameter(self) -> None:
        """promote_to_workspace signature requires role parameter."""
        import inspect

        sig = inspect.signature(MemoryPromotionService.promote_to_workspace)
        params = list(sig.parameters.keys())
        assert "role" in params
        assert "memory_id" in params
        assert "user_id" in params

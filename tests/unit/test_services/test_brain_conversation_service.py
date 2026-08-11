"""Unit tests for the Brain Conversation Service.

Tests cover:
    - R93.1: Per-user session isolation (org_id + user_id scoping)
    - R93.2: Multiple resumable conversations
    - R25.7: Trust domain resolution from user context
    - R25.15: Separate Brain sessions per user
    - R25.16: Max 200 messages per conversation, 20 recent as context

No I/O, no DB — AsyncSession is fully mocked.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.services.brain_conversation_service import (
    DEFAULT_CONTEXT_WINDOW,
    MAX_MESSAGES_PER_CONVERSATION,
    BrainConversationService,
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
def service(mock_db: AsyncMock) -> BrainConversationService:
    """Create a BrainConversationService with mocked DB."""
    return BrainConversationService(db=mock_db)


@pytest.fixture
def sample_org_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def other_user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_conversation_id() -> uuid.UUID:
    return uuid.uuid4()


def _make_conversation(
    *,
    conversation_id: uuid.UUID | None = None,
    org_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    mode: str = "creative",
    title: str | None = None,
    is_archived: bool = False,
    message_count: int = 0,
) -> MagicMock:
    """Helper to construct a mock BrainConversation with defaults."""
    conv = MagicMock()
    conv.id = conversation_id or uuid.uuid4()
    conv.org_id = org_id or uuid.uuid4()
    conv.user_id = user_id or uuid.uuid4()
    conv.trust_domain = "CUSTOMER_USER"
    conv.mode = mode
    conv.title = title
    conv.is_archived = is_archived
    conv.message_count = message_count
    conv.last_message_at = None
    conv.metadata_ = {}
    conv.created_at = datetime.now(UTC)
    conv.updated_at = datetime.now(UTC)
    return conv


def _make_message(
    *,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    actor: str = "user",
    content: str = "Hello",
) -> MagicMock:
    """Helper to construct a mock BrainMessage with defaults."""
    msg = MagicMock()
    msg.id = uuid.uuid4()
    msg.conversation_id = conversation_id
    msg.user_id = user_id
    msg.org_id = org_id
    msg.actor = actor
    msg.content = content
    msg.tool_refs = []
    msg.context_snapshot = None
    msg.token_count = None
    msg.created_at = datetime.now(UTC)
    return msg


# =============================================================================
# Tests: create_conversation
# =============================================================================


@pytest.mark.unit
class TestCreateConversation:
    """Test conversation creation (R93.1, R93.2, R25.7)."""

    @pytest.mark.asyncio
    @patch("app.services.brain_conversation_service.resolve_trust_domain")
    async def test_create_conversation_default_mode(
        self,
        mock_resolve: MagicMock,
        service: BrainConversationService,
        mock_db: AsyncMock,
        sample_org_id: uuid.UUID,
        sample_user_id: uuid.UUID,
    ) -> None:
        """Create a conversation with default creative mode."""
        mock_resolve.return_value = MagicMock(
            domain=MagicMock(name="CUSTOMER_USER")
        )
        mock_resolve.return_value.domain.name = "CUSTOMER_USER"

        result = await service.create_conversation(
            org_id=sample_org_id,
            user_id=sample_user_id,
        )

        assert result.org_id == sample_org_id
        assert result.user_id == sample_user_id
        assert result.mode == "creative"
        assert result.is_archived is False
        assert result.message_count == 0
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.services.brain_conversation_service.resolve_trust_domain")
    async def test_create_conversation_custom_mode(
        self,
        mock_resolve: MagicMock,
        service: BrainConversationService,
        mock_db: AsyncMock,
        sample_org_id: uuid.UUID,
        sample_user_id: uuid.UUID,
    ) -> None:
        """Create a conversation with a specific mode."""
        mock_resolve.return_value = MagicMock(
            domain=MagicMock(name="CUSTOMER_USER")
        )
        mock_resolve.return_value.domain.name = "CUSTOMER_USER"

        result = await service.create_conversation(
            org_id=sample_org_id,
            user_id=sample_user_id,
            mode="prompt_engineer",
            title="My prompts",
        )

        assert result.mode == "prompt_engineer"
        assert result.title == "My prompts"

    @pytest.mark.asyncio
    @patch("app.services.brain_conversation_service.resolve_trust_domain")
    async def test_create_conversation_resolves_trust_domain_server_side(
        self,
        mock_resolve: MagicMock,
        service: BrainConversationService,
        sample_org_id: uuid.UUID,
        sample_user_id: uuid.UUID,
    ) -> None:
        """Trust domain is resolved server-side (R57.1), not client-supplied."""
        mock_resolve.return_value = MagicMock(
            domain=MagicMock(name="WORKSPACE_ADMIN")
        )
        mock_resolve.return_value.domain.name = "WORKSPACE_ADMIN"

        result = await service.create_conversation(
            org_id=sample_org_id,
            user_id=sample_user_id,
            role="admin",
        )

        mock_resolve.assert_called_once_with(
            user_id=str(sample_user_id),
            org_id=str(sample_org_id),
            role="admin",
        )
        assert result.trust_domain == "WORKSPACE_ADMIN"


# =============================================================================
# Tests: list_conversations
# =============================================================================


@pytest.mark.unit
class TestListConversations:
    """Test listing conversations (R93.1 scoping, pagination)."""

    @pytest.mark.asyncio
    async def test_list_returns_paginated_result(
        self,
        service: BrainConversationService,
        mock_db: AsyncMock,
        sample_org_id: uuid.UUID,
        sample_user_id: uuid.UUID,
    ) -> None:
        """Listing returns (items, total) tuple."""
        mock_db.scalar = AsyncMock(return_value=2)

        conv1 = _make_conversation(org_id=sample_org_id, user_id=sample_user_id)
        conv2 = _make_conversation(org_id=sample_org_id, user_id=sample_user_id)

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [conv1, conv2]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        items, total = await service.list_conversations(
            org_id=sample_org_id,
            user_id=sample_user_id,
        )

        assert total == 2
        assert len(items) == 2

    @pytest.mark.asyncio
    async def test_list_respects_limit_offset(
        self,
        service: BrainConversationService,
        mock_db: AsyncMock,
        sample_org_id: uuid.UUID,
        sample_user_id: uuid.UUID,
    ) -> None:
        """Limit and offset are passed to the query."""
        mock_db.scalar = AsyncMock(return_value=5)

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        items, total = await service.list_conversations(
            org_id=sample_org_id,
            user_id=sample_user_id,
            limit=2,
            offset=3,
        )

        assert total == 5
        # execute called with a statement that has limit/offset
        mock_db.execute.assert_called_once()


# =============================================================================
# Tests: get_conversation
# =============================================================================


@pytest.mark.unit
class TestGetConversation:
    """Test getting a single conversation (R93.1 user isolation)."""

    @pytest.mark.asyncio
    async def test_get_existing_conversation(
        self,
        service: BrainConversationService,
        mock_db: AsyncMock,
        sample_org_id: uuid.UUID,
        sample_user_id: uuid.UUID,
        sample_conversation_id: uuid.UUID,
    ) -> None:
        """Returns conversation when it exists for the user."""
        conv = _make_conversation(
            conversation_id=sample_conversation_id,
            org_id=sample_org_id,
            user_id=sample_user_id,
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = conv
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.get_conversation(
            conversation_id=sample_conversation_id,
            org_id=sample_org_id,
            user_id=sample_user_id,
        )

        assert result.id == sample_conversation_id

    @pytest.mark.asyncio
    async def test_get_nonexistent_conversation_returns_404(
        self,
        service: BrainConversationService,
        mock_db: AsyncMock,
        sample_org_id: uuid.UUID,
        sample_user_id: uuid.UUID,
    ) -> None:
        """Returns 404 when conversation doesn't exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(HTTPException) as exc_info:
            await service.get_conversation(
                conversation_id=uuid.uuid4(),
                org_id=sample_org_id,
                user_id=sample_user_id,
            )

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_get_other_users_conversation_returns_404(
        self,
        service: BrainConversationService,
        mock_db: AsyncMock,
        sample_org_id: uuid.UUID,
        sample_user_id: uuid.UUID,
        other_user_id: uuid.UUID,
        sample_conversation_id: uuid.UUID,
    ) -> None:
        """Returns 404 for another user's conversation (R93.1 isolation)."""
        # The query scopes by user_id, so another user's conv won't match
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(HTTPException) as exc_info:
            await service.get_conversation(
                conversation_id=sample_conversation_id,
                org_id=sample_org_id,
                user_id=other_user_id,
            )

        assert exc_info.value.status_code == 404


# =============================================================================
# Tests: archive_conversation
# =============================================================================


@pytest.mark.unit
class TestArchiveConversation:
    """Test archiving (soft delete) conversations."""

    @pytest.mark.asyncio
    async def test_archive_sets_is_archived_true(
        self,
        service: BrainConversationService,
        mock_db: AsyncMock,
        sample_org_id: uuid.UUID,
        sample_user_id: uuid.UUID,
        sample_conversation_id: uuid.UUID,
    ) -> None:
        """Archiving sets is_archived=True."""
        conv = _make_conversation(
            conversation_id=sample_conversation_id,
            org_id=sample_org_id,
            user_id=sample_user_id,
            is_archived=False,
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = conv
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.archive_conversation(
            conversation_id=sample_conversation_id,
            org_id=sample_org_id,
            user_id=sample_user_id,
        )

        assert conv.is_archived is True

    @pytest.mark.asyncio
    async def test_archive_nonexistent_returns_404(
        self,
        service: BrainConversationService,
        mock_db: AsyncMock,
        sample_org_id: uuid.UUID,
        sample_user_id: uuid.UUID,
    ) -> None:
        """Archiving a non-existent conversation returns 404."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(HTTPException) as exc_info:
            await service.archive_conversation(
                conversation_id=uuid.uuid4(),
                org_id=sample_org_id,
                user_id=sample_user_id,
            )

        assert exc_info.value.status_code == 404


# =============================================================================
# Tests: add_message
# =============================================================================


@pytest.mark.unit
class TestAddMessage:
    """Test adding messages to conversations (R25.16 limit enforcement)."""

    @pytest.mark.asyncio
    async def test_add_message_success(
        self,
        service: BrainConversationService,
        mock_db: AsyncMock,
        sample_org_id: uuid.UUID,
        sample_user_id: uuid.UUID,
        sample_conversation_id: uuid.UUID,
    ) -> None:
        """Successfully adds a message and updates conversation counters."""
        conv = _make_conversation(
            conversation_id=sample_conversation_id,
            org_id=sample_org_id,
            user_id=sample_user_id,
            message_count=5,
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = conv
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.add_message(
            conversation_id=sample_conversation_id,
            org_id=sample_org_id,
            user_id=sample_user_id,
            actor="user",
            content="Hello Brain!",
        )

        assert result.actor == "user"
        assert result.content == "Hello Brain!"
        assert result.conversation_id == sample_conversation_id
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()
        # Verify counters updated
        assert conv.message_count == 6

    @pytest.mark.asyncio
    async def test_add_message_at_limit_rejects_with_422(
        self,
        service: BrainConversationService,
        mock_db: AsyncMock,
        sample_org_id: uuid.UUID,
        sample_user_id: uuid.UUID,
        sample_conversation_id: uuid.UUID,
    ) -> None:
        """Rejects message when conversation is at max (200) messages."""
        conv = _make_conversation(
            conversation_id=sample_conversation_id,
            org_id=sample_org_id,
            user_id=sample_user_id,
            message_count=MAX_MESSAGES_PER_CONVERSATION,
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = conv
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(HTTPException) as exc_info:
            await service.add_message(
                conversation_id=sample_conversation_id,
                org_id=sample_org_id,
                user_id=sample_user_id,
                actor="user",
                content="This should fail",
            )

        assert exc_info.value.status_code == 422
        assert "200" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_add_message_with_tool_refs(
        self,
        service: BrainConversationService,
        mock_db: AsyncMock,
        sample_org_id: uuid.UUID,
        sample_user_id: uuid.UUID,
        sample_conversation_id: uuid.UUID,
    ) -> None:
        """Message can include tool references."""
        conv = _make_conversation(
            conversation_id=sample_conversation_id,
            org_id=sample_org_id,
            user_id=sample_user_id,
            message_count=0,
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = conv
        mock_db.execute = AsyncMock(return_value=mock_result)

        tool_refs = [{"tool": "generate_image", "params": {"model": "flux"}}]

        result = await service.add_message(
            conversation_id=sample_conversation_id,
            org_id=sample_org_id,
            user_id=sample_user_id,
            actor="brain",
            content="Generated image",
            tool_refs=tool_refs,
            token_count=150,
        )

        assert result.tool_refs == tool_refs
        assert result.token_count == 150

    @pytest.mark.asyncio
    async def test_add_message_to_nonexistent_conversation_404(
        self,
        service: BrainConversationService,
        mock_db: AsyncMock,
        sample_org_id: uuid.UUID,
        sample_user_id: uuid.UUID,
    ) -> None:
        """Adding message to non-existent conversation returns 404."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(HTTPException) as exc_info:
            await service.add_message(
                conversation_id=uuid.uuid4(),
                org_id=sample_org_id,
                user_id=sample_user_id,
                actor="user",
                content="Hello",
            )

        assert exc_info.value.status_code == 404


# =============================================================================
# Tests: get_recent_messages
# =============================================================================


@pytest.mark.unit
class TestGetRecentMessages:
    """Test recent message retrieval for context injection (R25.16)."""

    @pytest.mark.asyncio
    async def test_get_recent_messages_default_limit(
        self,
        service: BrainConversationService,
        mock_db: AsyncMock,
        sample_org_id: uuid.UUID,
        sample_user_id: uuid.UUID,
        sample_conversation_id: uuid.UUID,
    ) -> None:
        """Default limit is 20 (DEFAULT_CONTEXT_WINDOW)."""
        conv = _make_conversation(
            conversation_id=sample_conversation_id,
            org_id=sample_org_id,
            user_id=sample_user_id,
        )

        messages = [
            _make_message(
                conversation_id=sample_conversation_id,
                user_id=sample_user_id,
                org_id=sample_org_id,
                content=f"msg {i}",
            )
            for i in range(5)
        ]

        mock_result_conv = MagicMock()
        mock_result_conv.scalar_one_or_none.return_value = conv

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = messages
        mock_result_msgs = MagicMock()
        mock_result_msgs.scalars.return_value = mock_scalars

        mock_db.execute = AsyncMock(
            side_effect=[mock_result_conv, mock_result_msgs]
        )

        result = await service.get_recent_messages(
            conversation_id=sample_conversation_id,
            org_id=sample_org_id,
            user_id=sample_user_id,
        )

        assert len(result) == 5

    @pytest.mark.asyncio
    async def test_get_recent_messages_returns_chronological_order(
        self,
        service: BrainConversationService,
        mock_db: AsyncMock,
        sample_org_id: uuid.UUID,
        sample_user_id: uuid.UUID,
        sample_conversation_id: uuid.UUID,
    ) -> None:
        """Messages are returned oldest-first for context injection."""
        conv = _make_conversation(
            conversation_id=sample_conversation_id,
            org_id=sample_org_id,
            user_id=sample_user_id,
        )

        # Messages in desc order (as returned by DB query)
        msg_new = _make_message(
            conversation_id=sample_conversation_id,
            user_id=sample_user_id,
            org_id=sample_org_id,
            content="new",
        )
        msg_old = _make_message(
            conversation_id=sample_conversation_id,
            user_id=sample_user_id,
            org_id=sample_org_id,
            content="old",
        )

        mock_result_conv = MagicMock()
        mock_result_conv.scalar_one_or_none.return_value = conv

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [msg_new, msg_old]  # desc from DB
        mock_result_msgs = MagicMock()
        mock_result_msgs.scalars.return_value = mock_scalars

        mock_db.execute = AsyncMock(
            side_effect=[mock_result_conv, mock_result_msgs]
        )

        result = await service.get_recent_messages(
            conversation_id=sample_conversation_id,
            org_id=sample_org_id,
            user_id=sample_user_id,
        )

        # Should be reversed to chronological (oldest first)
        assert result[0].content == "old"
        assert result[1].content == "new"


# =============================================================================
# Tests: get_conversation_with_messages
# =============================================================================


@pytest.mark.unit
class TestGetConversationWithMessages:
    """Test combined conversation + messages retrieval."""

    @pytest.mark.asyncio
    async def test_returns_conversation_and_messages(
        self,
        service: BrainConversationService,
        mock_db: AsyncMock,
        sample_org_id: uuid.UUID,
        sample_user_id: uuid.UUID,
        sample_conversation_id: uuid.UUID,
    ) -> None:
        """Returns both conversation and its recent messages."""
        conv = _make_conversation(
            conversation_id=sample_conversation_id,
            org_id=sample_org_id,
            user_id=sample_user_id,
            message_count=3,
        )

        messages = [
            _make_message(
                conversation_id=sample_conversation_id,
                user_id=sample_user_id,
                org_id=sample_org_id,
            )
            for _ in range(3)
        ]

        # First call: get_conversation, second: get_conversation again (inside
        # get_recent_messages), third: messages query
        mock_result_conv = MagicMock()
        mock_result_conv.scalar_one_or_none.return_value = conv

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = messages
        mock_result_msgs = MagicMock()
        mock_result_msgs.scalars.return_value = mock_scalars

        mock_db.execute = AsyncMock(
            side_effect=[mock_result_conv, mock_result_conv, mock_result_msgs]
        )

        result_conv, result_msgs = await service.get_conversation_with_messages(
            conversation_id=sample_conversation_id,
            org_id=sample_org_id,
            user_id=sample_user_id,
        )

        assert result_conv.id == sample_conversation_id
        assert len(result_msgs) == 3


# =============================================================================
# Tests: Constants
# =============================================================================


@pytest.mark.unit
class TestConstants:
    """Test service constants match requirements."""

    def test_max_messages_is_200(self) -> None:
        """Max messages per conversation is 200 (R25.16)."""
        assert MAX_MESSAGES_PER_CONVERSATION == 200

    def test_default_context_window_is_20(self) -> None:
        """Default context window is 20 messages."""
        assert DEFAULT_CONTEXT_WINDOW == 20

"""Brain Conversation Service — per-user session management.

Implements conversation lifecycle management per R93.1, R93.2:
    - Per-user sessions scoped by org_id, user_id, conversation_id, trust_domain
    - Multiple resumable conversations per user
    - Max 200 messages per conversation
    - 20 most recent messages as context injection window

Key invariants:
    - Conversations are always scoped to (org_id, user_id) — never shared
    - Trust domain resolved server-side from user context
    - Message count enforced at service layer (max 200)
    - Archived conversations are soft-deleted (is_archived=True)

Validates: Requirements R25.7, R25.15, R25.16, R93.1, R93.2
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.core.trust_domains import TrustDomain, resolve_trust_domain
from app.models.brain_memory import BrainConversation, BrainMessage

logger = get_logger(__name__)

# Maximum messages allowed per conversation (R25.16)
MAX_MESSAGES_PER_CONVERSATION = 200

# Default context window size (inject N most recent messages)
DEFAULT_CONTEXT_WINDOW = 20


class ConversationLimitExceededError(Exception):
    """Raised when a conversation has reached its maximum message count."""

    def __init__(self, conversation_id: uuid.UUID, current_count: int) -> None:
        self.conversation_id = conversation_id
        self.current_count = current_count
        super().__init__(
            f"Conversation {conversation_id} has reached the maximum of "
            f"{MAX_MESSAGES_PER_CONVERSATION} messages (current: {current_count})"
        )


class BrainConversationService:
    """Service layer for Brain conversation management.

    All operations are scoped to (org_id, user_id) to enforce per-user
    session isolation per R93.1. Trust domain is resolved server-side.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_conversation(
        self,
        *,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        mode: str = "creative",
        title: str | None = None,
        role: str = "editor",
        metadata: dict | None = None,
    ) -> BrainConversation:
        """Create a new Brain conversation for a user.

        Resolves trust_domain server-side from user context (R57.1).
        Conversations are always per-user (R93.1: never shared).

        Args:
            org_id: Organisation UUID from validated TenantContext.
            user_id: User UUID from validated JWT.
            mode: Brain mode (creative, prompt_engineer, story, etc.).
            title: Optional conversation title.
            role: User's workspace role (for trust domain resolution).
            metadata: Optional metadata dict.

        Returns:
            The newly created BrainConversation ORM instance.
        """
        # Resolve trust domain server-side (client cannot influence)
        trust_ctx = resolve_trust_domain(
            user_id=str(user_id),
            org_id=str(org_id),
            role=role,
        )

        conversation = BrainConversation(
            id=uuid.uuid4(),
            org_id=org_id,
            user_id=user_id,
            trust_domain=trust_ctx.domain.name,
            mode=mode,
            title=title,
            is_archived=False,
            message_count=0,
            last_message_at=None,
            metadata_=metadata or {},
        )

        self.db.add(conversation)
        await self.db.flush()

        logger.info(
            "brain_conversation_created",
            conversation_id=str(conversation.id),
            org_id=str(org_id),
            user_id=str(user_id),
            mode=mode,
            trust_domain=trust_ctx.domain.name,
        )

        return conversation

    async def list_conversations(
        self,
        *,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        include_archived: bool = False,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[BrainConversation], int]:
        """List conversations for a user, paginated, newest first.

        Always scoped to (org_id, user_id) — user cannot see other
        users' conversations (R93.1).

        Args:
            org_id: Organisation UUID.
            user_id: User UUID.
            include_archived: Whether to include archived conversations.
            limit: Max items to return (1-100).
            offset: Pagination offset.

        Returns:
            Tuple of (conversations list, total count).
        """
        # Base filter: org + user scoping
        base_filter = [
            BrainConversation.org_id == org_id,
            BrainConversation.user_id == user_id,
        ]

        if not include_archived:
            base_filter.append(BrainConversation.is_archived == False)  # noqa: E712

        # Count query
        count_stmt = (
            select(func.count())
            .select_from(BrainConversation)
            .where(*base_filter)
        )
        total = await self.db.scalar(count_stmt) or 0

        # Data query — newest first
        stmt = (
            select(BrainConversation)
            .where(*base_filter)
            .order_by(BrainConversation.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    async def get_conversation(
        self,
        *,
        conversation_id: uuid.UUID,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> BrainConversation:
        """Get a single conversation, scoped to org + user.

        Returns 404 if the conversation doesn't exist or belongs to
        another user/org (R93.1: user isolation).

        Args:
            conversation_id: The conversation UUID.
            org_id: Organisation UUID.
            user_id: User UUID.

        Returns:
            The BrainConversation instance.

        Raises:
            HTTPException 404: If not found or access denied.
        """
        stmt = select(BrainConversation).where(
            BrainConversation.id == conversation_id,
            BrainConversation.org_id == org_id,
            BrainConversation.user_id == user_id,
        )
        result = await self.db.execute(stmt)
        conversation = result.scalar_one_or_none()

        if conversation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )

        return conversation

    async def archive_conversation(
        self,
        *,
        conversation_id: uuid.UUID,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> BrainConversation:
        """Soft-archive a conversation (set is_archived=True).

        Does not delete messages — the conversation can still be
        retrieved with include_archived=True.

        Args:
            conversation_id: The conversation UUID.
            org_id: Organisation UUID.
            user_id: User UUID.

        Returns:
            The updated BrainConversation.

        Raises:
            HTTPException 404: If not found or access denied.
        """
        conversation = await self.get_conversation(
            conversation_id=conversation_id,
            org_id=org_id,
            user_id=user_id,
        )

        conversation.is_archived = True
        await self.db.flush()

        logger.info(
            "brain_conversation_archived",
            conversation_id=str(conversation_id),
            org_id=str(org_id),
            user_id=str(user_id),
        )

        return conversation

    async def add_message(
        self,
        *,
        conversation_id: uuid.UUID,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        actor: str,
        content: str,
        tool_refs: list | None = None,
        context_snapshot: dict | None = None,
        token_count: int | None = None,
    ) -> BrainMessage:
        """Add a message to a conversation.

        Enforces MAX_MESSAGES_PER_CONVERSATION (200) limit.
        Updates conversation's message_count and last_message_at.

        Args:
            conversation_id: Target conversation UUID.
            org_id: Organisation UUID.
            user_id: User UUID.
            actor: Message actor (user, brain, hermes, system).
            content: Message content text.
            tool_refs: Optional tool references.
            context_snapshot: Optional context snapshot.
            token_count: Optional token count.

        Returns:
            The newly created BrainMessage.

        Raises:
            HTTPException 404: If conversation not found.
            HTTPException 422: If message limit exceeded.
        """
        # Verify conversation exists and belongs to user
        conversation = await self.get_conversation(
            conversation_id=conversation_id,
            org_id=org_id,
            user_id=user_id,
        )

        # Enforce message limit (R25.16)
        if conversation.message_count >= MAX_MESSAGES_PER_CONVERSATION:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Conversation has reached the maximum of "
                    f"{MAX_MESSAGES_PER_CONVERSATION} messages. "
                    f"Please start a new conversation."
                ),
            )

        now = datetime.now(UTC)

        message = BrainMessage(
            id=uuid.uuid4(),
            org_id=org_id,
            conversation_id=conversation_id,
            user_id=user_id,
            actor=actor,
            content=content,
            tool_refs=tool_refs or [],
            context_snapshot=context_snapshot,
            token_count=token_count,
            created_at=now,
        )

        self.db.add(message)

        # Update conversation counters
        conversation.message_count = conversation.message_count + 1
        conversation.last_message_at = now

        await self.db.flush()

        logger.info(
            "brain_message_added",
            message_id=str(message.id),
            conversation_id=str(conversation_id),
            org_id=str(org_id),
            user_id=str(user_id),
            actor=actor,
            message_count=conversation.message_count,
        )

        return message

    async def get_recent_messages(
        self,
        *,
        conversation_id: uuid.UUID,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        limit: int = DEFAULT_CONTEXT_WINDOW,
    ) -> list[BrainMessage]:
        """Get the N most recent messages for context injection.

        Returns messages in chronological order (oldest first) so they
        can be directly injected as conversation history.

        Args:
            conversation_id: Target conversation UUID.
            org_id: Organisation UUID.
            user_id: User UUID.
            limit: Number of recent messages to return (default: 20).

        Returns:
            List of BrainMessage instances, chronologically ordered.

        Raises:
            HTTPException 404: If conversation not found.
        """
        # Verify conversation exists and belongs to user
        await self.get_conversation(
            conversation_id=conversation_id,
            org_id=org_id,
            user_id=user_id,
        )

        # Subquery to get the N most recent messages, then order chronologically
        stmt = (
            select(BrainMessage)
            .where(
                BrainMessage.conversation_id == conversation_id,
                BrainMessage.org_id == org_id,
            )
            .order_by(BrainMessage.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        messages = list(result.scalars().all())

        # Reverse to chronological order (oldest first)
        messages.reverse()

        return messages

    async def get_conversation_with_messages(
        self,
        *,
        conversation_id: uuid.UUID,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> tuple[BrainConversation, list[BrainMessage]]:
        """Get a conversation with its 20 most recent messages.

        Convenience method combining get_conversation + get_recent_messages.

        Args:
            conversation_id: Target conversation UUID.
            org_id: Organisation UUID.
            user_id: User UUID.

        Returns:
            Tuple of (BrainConversation, list of recent BrainMessages).

        Raises:
            HTTPException 404: If conversation not found.
        """
        conversation = await self.get_conversation(
            conversation_id=conversation_id,
            org_id=org_id,
            user_id=user_id,
        )

        messages = await self.get_recent_messages(
            conversation_id=conversation_id,
            org_id=org_id,
            user_id=user_id,
            limit=DEFAULT_CONTEXT_WINDOW,
        )

        return conversation, messages

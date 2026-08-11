"""Brain Memory 4-Layer Architecture ORM models.

Defines the persistence layer for the Brain memory system:
    - BrainUserMemory: Per-user private memory with provenance tracking
    - BrainWorkspaceKnowledge: Workspace-level knowledge promoted from users
    - BrainConversation: Per-user conversation sessions (multi-mode)
    - BrainMessage: Messages within conversations

The provenance hierarchy ensures LLM output is never silently promoted
to canonical truth:
    USER_CONFIRMED > OBSERVED > IMPORTED > INFERRED > SUGGESTED

Validates: Requirements R93.1, R94.1, R29.1
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDMixin


class BrainUserMemory(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """Per-user private memory with provenance tracking.

    Memory entries are always scoped to (org_id, user_id). They represent
    learned preferences, observed patterns, imported context, or AI-inferred
    facts about the user's style and working patterns.

    Provenance hierarchy (highest trust → lowest):
        USER_CONFIRMED — User explicitly stated or confirmed
        OBSERVED — Derived from repeated user behavior
        IMPORTED — Brought in from external source
        INFERRED — AI-inferred from conversation patterns
        SUGGESTED — AI suggestion, not yet validated
    """

    __tablename__ = "brain_user_memory"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    memory_type: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    content: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )
    provenance: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=3, scale=2),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    source_conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "provenance IN ("
            "'USER_CONFIRMED', 'OBSERVED', 'IMPORTED', 'INFERRED', 'SUGGESTED'"
            ")",
            name="ck_brain_user_memory_provenance",
        ),
        Index("ix_brain_user_memory_org_user", "org_id", "user_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<BrainUserMemory(id={self.id}, org_id={self.org_id}, "
            f"user_id={self.user_id}, type={self.memory_type}, "
            f"provenance={self.provenance})>"
        )


class BrainWorkspaceKnowledge(Base, UUIDMixin, TenantMixin):
    """Workspace-level knowledge promoted from user memory.

    Knowledge items are shared across all users in a workspace.
    They can originate from user-private memory (via explicit promotion)
    or be created directly at the workspace level.

    Only users with appropriate roles can promote private memory to
    workspace knowledge.
    """

    __tablename__ = "brain_workspace_knowledge"

    knowledge_type: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    content: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )
    promoted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    promoted_from: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brain_user_memory.id", ondelete="SET NULL"),
        nullable=True,
    )
    provenance: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_brain_workspace_knowledge_org_id", "org_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<BrainWorkspaceKnowledge(id={self.id}, org_id={self.org_id}, "
            f"type={self.knowledge_type}, provenance={self.provenance})>"
        )


class BrainConversation(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """Per-user conversation session with mode and trust domain.

    Conversations are always per-user (R93.1: never shared across users).
    Each conversation operates in a specific Brain mode and trust domain.

    Trust domains control what memory/context is accessible:
        CUSTOMER_USER — Standard user conversations
        WORKSPACE — Workspace-scoped shared context
        FOUNDER_PRIVATE — Founder-only context (never leaks to customers)
        PLATFORM — Platform operator context
        SERVICE — Service-to-service
        SYSTEM — Internal system context
    """

    __tablename__ = "brain_conversations"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    trust_domain: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="CUSTOMER_USER",
    )
    mode: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="creative",
    )
    title: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    is_archived: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    message_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    # Relationship to messages
    messages: Mapped[list["BrainMessage"]] = relationship(
        "BrainMessage",
        back_populates="conversation",
        lazy="raise",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index(
            "ix_brain_conversations_org_user_created",
            "org_id",
            "user_id",
            text("created_at DESC"),
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<BrainConversation(id={self.id}, org_id={self.org_id}, "
            f"user_id={self.user_id}, mode={self.mode}, "
            f"messages={self.message_count})>"
        )


class BrainMessage(Base, UUIDMixin, TenantMixin):
    """Message within a Brain conversation.

    Each message records the actor (user, brain, hermes, or system),
    the content, any tool references, and an optional context snapshot
    for debugging/reproducibility.
    """

    __tablename__ = "brain_messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brain_conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    actor: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    tool_refs: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
    context_snapshot: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    token_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationship back to conversation
    conversation: Mapped["BrainConversation"] = relationship(
        "BrainConversation",
        back_populates="messages",
        lazy="raise",
    )

    __table_args__ = (
        CheckConstraint(
            "actor IN ('user', 'brain', 'hermes', 'system')",
            name="ck_brain_messages_actor",
        ),
        Index(
            "ix_brain_messages_conversation_created",
            "conversation_id",
            "created_at",
        ),
        Index("ix_brain_messages_org_id", "org_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<BrainMessage(id={self.id}, conversation_id={self.conversation_id}, "
            f"actor={self.actor})>"
        )

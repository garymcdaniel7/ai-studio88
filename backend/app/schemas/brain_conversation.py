"""Pydantic schemas for Brain conversation management.

Defines request/response models for:
    - Creating conversations
    - Listing conversations (paginated)
    - Adding messages to conversations
    - Retrieving conversation with recent messages

Validates: Requirements R93.1, R93.2, R25.7, R25.15, R25.16
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.base import BaseSchema


# =============================================================================
# Request Schemas
# =============================================================================


class ConversationCreateRequest(BaseSchema):
    """Request to create a new Brain conversation."""

    mode: str = Field(
        default="creative",
        min_length=1,
        max_length=50,
        description="Brain mode: creative, prompt_engineer, story, production, research, image_analyzer",
    )
    title: str | None = Field(
        default=None,
        max_length=200,
        description="Optional conversation title",
    )
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Optional metadata for the conversation",
    )


class MessageCreateRequest(BaseSchema):
    """Request to add a message to a conversation."""

    actor: str = Field(
        ...,
        pattern="^(user|brain|hermes|system)$",
        description="Message actor: user, brain, hermes, or system",
    )
    content: str = Field(
        ...,
        min_length=1,
        max_length=100_000,
        description="Message content",
    )
    tool_refs: list[dict[str, Any]] | None = Field(
        default=None,
        description="Optional tool references used in this message",
    )
    context_snapshot: dict[str, Any] | None = Field(
        default=None,
        description="Optional context snapshot for debugging/reproducibility",
    )
    token_count: int | None = Field(
        default=None,
        ge=0,
        description="Optional token count for the message",
    )


# =============================================================================
# Response Schemas
# =============================================================================


class ConversationResponse(BaseSchema):
    """Response for a single Brain conversation."""

    id: UUID
    org_id: UUID
    user_id: UUID
    trust_domain: str
    mode: str
    title: str | None = None
    is_archived: bool
    message_count: int
    last_message_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, alias="metadata_")
    created_at: datetime
    updated_at: datetime


class MessageResponse(BaseSchema):
    """Response for a single Brain message."""

    id: UUID
    conversation_id: UUID
    user_id: UUID
    actor: str
    content: str
    tool_refs: list[dict[str, Any]] = Field(default_factory=list)
    context_snapshot: dict[str, Any] | None = None
    token_count: int | None = None
    created_at: datetime


class ConversationWithMessagesResponse(BaseSchema):
    """Response for a conversation with its recent messages."""

    conversation: ConversationResponse
    messages: list[MessageResponse]


class ConversationListResponse(BaseSchema):
    """Paginated list of conversations."""

    items: list[ConversationResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)

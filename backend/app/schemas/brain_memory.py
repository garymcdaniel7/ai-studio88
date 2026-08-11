"""Pydantic schemas for Brain memory management and workspace promotion.

Defines request/response models for:
    - Listing user private memory items
    - Updating/deactivating private memory
    - Promoting private memory to workspace knowledge
    - Listing/managing workspace knowledge

Validates: Requirements R29.12, R29.13, R93.5, R94.2, R94.3
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema


# =============================================================================
# Request Schemas
# =============================================================================


class MemoryUpdateRequest(BaseSchema):
    """Request to update a private memory item."""

    content: dict[str, Any] | None = Field(
        default=None,
        description="Updated memory content (JSONB)",
    )
    is_active: bool | None = Field(
        default=None,
        description="Set active state (False = disable without deleting)",
    )


class MemoryPromoteRequest(BaseSchema):
    """Request to promote a private memory item to workspace knowledge.

    The promote action is always explicit — private memory never
    auto-promotes to workspace knowledge (R93.5).
    """

    # No fields required — the memory_id comes from the URL path.
    # The promote endpoint simply requires the user to have editor+ role.
    pass


# =============================================================================
# Response Schemas
# =============================================================================


class UserMemoryResponse(BaseSchema):
    """Response for a single user private memory item."""

    id: UUID
    org_id: UUID
    user_id: UUID
    memory_type: str
    content: dict[str, Any]
    provenance: str
    confidence: Decimal | None = None
    is_active: bool
    source_conversation_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class UserMemoryListResponse(BaseSchema):
    """Paginated list of user memory items."""

    items: list[UserMemoryResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class WorkspaceKnowledgeResponse(BaseSchema):
    """Response for a single workspace knowledge item."""

    id: UUID
    org_id: UUID
    knowledge_type: str
    content: dict[str, Any]
    provenance: str
    promoted_by: UUID | None = None
    promoted_from: UUID | None = None
    created_at: datetime


class WorkspaceKnowledgeListResponse(BaseSchema):
    """Paginated list of workspace knowledge items."""

    items: list[WorkspaceKnowledgeResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class PromotionResponse(BaseSchema):
    """Response after successful promotion to workspace knowledge.

    Records: promoted_by, promoted_from, timestamp (R29.12).
    """

    id: UUID
    org_id: UUID
    knowledge_type: str
    content: dict[str, Any]
    provenance: str
    promoted_by: UUID
    promoted_from: UUID
    created_at: datetime

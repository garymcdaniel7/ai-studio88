"""Brain Conversation API endpoints.

Provides CRUD operations for Brain conversations:
    - GET  /brain/conversations           — list user's conversations
    - POST /brain/conversations           — create a new conversation
    - GET  /brain/conversations/{id}      — get conversation with recent messages
    - DELETE /brain/conversations/{id}    — archive (soft delete)
    - POST /brain/conversations/{id}/messages — add a message

All endpoints are scoped to the authenticated user (R93.1: per-user
isolation — one user cannot see/access another user's conversations).

Validates: Requirements R25.7, R25.15, R25.16, R93.1, R93.2
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, status

from app.core.dependencies import DBSessionDep, TenantContextDep
from app.schemas.brain_conversation import (
    ConversationCreateRequest,
    ConversationListResponse,
    ConversationResponse,
    ConversationWithMessagesResponse,
    MessageCreateRequest,
    MessageResponse,
)
from app.services.brain_conversation_service import BrainConversationService

router = APIRouter(prefix="/brain/conversations", tags=["brain"])


# =============================================================================
# Endpoints
# =============================================================================


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    tenant: TenantContextDep,
    db: DBSessionDep,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    include_archived: bool = Query(False),
) -> ConversationListResponse:
    """List the authenticated user's Brain conversations.

    Returns paginated conversations, newest first. By default only
    active (non-archived) conversations are returned.

    Scoped to (org_id, user_id) — user cannot see other users' conversations.
    """
    service = BrainConversationService(db=db)
    items, total = await service.list_conversations(
        org_id=tenant.org_id,
        user_id=tenant.user_id,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return ConversationListResponse(
        items=[ConversationResponse.model_validate(c) for c in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    body: ConversationCreateRequest,
    tenant: TenantContextDep,
    db: DBSessionDep,
) -> ConversationResponse:
    """Create a new Brain conversation for the authenticated user.

    Trust domain is resolved server-side from user context — the client
    cannot influence it. Conversations are per-user (R93.1).
    """
    service = BrainConversationService(db=db)
    conversation = await service.create_conversation(
        org_id=tenant.org_id,
        user_id=tenant.user_id,
        mode=body.mode,
        title=body.title,
        role=tenant.role.value,
        metadata=body.metadata,
    )
    return ConversationResponse.model_validate(conversation)


@router.get("/{conversation_id}", response_model=ConversationWithMessagesResponse)
async def get_conversation(
    conversation_id: UUID,
    tenant: TenantContextDep,
    db: DBSessionDep,
) -> ConversationWithMessagesResponse:
    """Get a conversation with its 20 most recent messages.

    Returns 404 if the conversation doesn't exist or belongs to another user.
    Messages are returned in chronological order (oldest first).
    """
    service = BrainConversationService(db=db)
    conversation, messages = await service.get_conversation_with_messages(
        conversation_id=conversation_id,
        org_id=tenant.org_id,
        user_id=tenant.user_id,
    )
    return ConversationWithMessagesResponse(
        conversation=ConversationResponse.model_validate(conversation),
        messages=[MessageResponse.model_validate(m) for m in messages],
    )


@router.delete(
    "/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def archive_conversation(
    conversation_id: UUID,
    tenant: TenantContextDep,
    db: DBSessionDep,
) -> None:
    """Archive a Brain conversation (soft delete).

    The conversation is not permanently deleted — it can still be
    retrieved with include_archived=True. Returns 404 if not found
    or belongs to another user.
    """
    service = BrainConversationService(db=db)
    await service.archive_conversation(
        conversation_id=conversation_id,
        org_id=tenant.org_id,
        user_id=tenant.user_id,
    )


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_message(
    conversation_id: UUID,
    body: MessageCreateRequest,
    tenant: TenantContextDep,
    db: DBSessionDep,
) -> MessageResponse:
    """Add a message to a Brain conversation.

    Rejects with 422 if the conversation has reached the 200 message limit.
    Returns 404 if the conversation doesn't exist or belongs to another user.
    """
    service = BrainConversationService(db=db)
    message = await service.add_message(
        conversation_id=conversation_id,
        org_id=tenant.org_id,
        user_id=tenant.user_id,
        actor=body.actor,
        content=body.content,
        tool_refs=body.tool_refs,
        context_snapshot=body.context_snapshot,
        token_count=body.token_count,
    )
    return MessageResponse.model_validate(message)

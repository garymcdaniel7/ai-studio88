"""Brain Memory API endpoints — private memory and workspace knowledge management.

Provides endpoints for:
    - GET  /brain/memory                      — list user's private memory items
    - PATCH /brain/memory/{memory_id}         — update/deactivate personal memory
    - DELETE /brain/memory/{memory_id}        — delete personal memory
    - POST /brain/memory/{memory_id}/promote  — promote to workspace knowledge
    - GET  /brain/knowledge                   — list workspace knowledge
    - DELETE /brain/knowledge/{knowledge_id}  — delete workspace knowledge (admin+)

All memory endpoints are scoped to authenticated user (R93.5, R94.2, R94.3).
Promotion is always explicit — private memory never auto-promotes (R93.5).

Validates: Requirements R29.12, R29.13, R93.5, R94.2, R94.3
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.core.dependencies import DBSessionDep, TenantContextDep
from app.schemas.brain_memory import (
    MemoryUpdateRequest,
    PromotionResponse,
    UserMemoryListResponse,
    UserMemoryResponse,
    WorkspaceKnowledgeListResponse,
    WorkspaceKnowledgeResponse,
)
from app.services.brain_memory_promotion_service import (
    InsufficientRoleError,
    KnowledgeNotFoundError,
    MemoryInactiveError,
    MemoryNotFoundError,
    MemoryPromotionService,
)
from app.services.brain_memory_service import (
    BrainMemoryService,
    InvalidProvenanceError,
    MemoryNotFoundError as ServiceMemoryNotFoundError,
    ProvenanceDowngradeError,
)

router = APIRouter(prefix="/brain", tags=["brain-memory"])


# =============================================================================
# Private Memory Endpoints
# =============================================================================


@router.get("/memory", response_model=UserMemoryListResponse)
async def list_user_memory(
    tenant: TenantContextDep,
    db: DBSessionDep,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    memory_type: str | None = Query(None, description="Filter by memory type"),
    active_only: bool = Query(True, description="Only return active items"),
) -> UserMemoryListResponse:
    """List the authenticated user's private memory items.

    Returns paginated memory items, newest first. Users can inspect
    all their durable personalization data (R94.2).

    Scoped to (org_id, user_id) — user cannot see other users' memory.
    """
    service = BrainMemoryService(db=db)
    items = await service.list_user_memory(
        org_id=tenant.org_id,
        user_id=tenant.user_id,
        memory_type=memory_type,
        active_only=active_only,
        limit=limit,
    )
    return UserMemoryListResponse(
        items=[UserMemoryResponse.model_validate(m) for m in items],
        total=len(items),
        limit=limit,
        offset=offset,
    )


@router.patch("/memory/{memory_id}", response_model=UserMemoryResponse)
async def update_memory(
    memory_id: UUID,
    body: MemoryUpdateRequest,
    tenant: TenantContextDep,
    db: DBSessionDep,
) -> UserMemoryResponse:
    """Update or deactivate a personal memory item.

    Users can correct content or disable any durable personalization (R94.3).
    Provenance can only be upgraded, never downgraded.
    """
    service = BrainMemoryService(db=db)
    try:
        result = await service.update_memory(
            memory_id=memory_id,
            org_id=tenant.org_id,
            user_id=tenant.user_id,
            content=body.content,
            is_active=body.is_active,
        )
    except ServiceMemoryNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory item not found",
        )
    except ProvenanceDowngradeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.message,
        )
    except InvalidProvenanceError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.message,
        )

    return UserMemoryResponse.model_validate(result)


@router.delete(
    "/memory/{memory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_memory(
    memory_id: UUID,
    tenant: TenantContextDep,
    db: DBSessionDep,
) -> None:
    """Delete a personal memory item permanently.

    Users can delete any of their durable personalization data (R94.3).
    Returns 404 if not found or belongs to another user.
    """
    service = BrainMemoryService(db=db)
    try:
        await service.delete_memory(
            memory_id=memory_id,
            org_id=tenant.org_id,
            user_id=tenant.user_id,
        )
    except ServiceMemoryNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory item not found",
        )


# =============================================================================
# Promotion Endpoint
# =============================================================================


@router.post(
    "/memory/{memory_id}/promote",
    response_model=PromotionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def promote_memory_to_workspace(
    memory_id: UUID,
    tenant: TenantContextDep,
    db: DBSessionDep,
) -> PromotionResponse:
    """Promote a private memory item to workspace knowledge.

    This is an EXPLICIT user action (R93.5) — private memory never
    auto-promotes. Requires editor+ role. Records promotion metadata:
    promoted_by, promoted_from, timestamp (R29.12).

    Returns 403 if user lacks editor+ role.
    Returns 404 if memory not found for this user.
    Returns 422 if memory is inactive.
    """
    promotion_service = MemoryPromotionService(db=db)
    try:
        knowledge = await promotion_service.promote_to_workspace(
            memory_id=memory_id,
            org_id=tenant.org_id,
            user_id=tenant.user_id,
            role=tenant.role.value,
        )
    except InsufficientRoleError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions. Requires editor role or above.",
        )
    except MemoryNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory item not found",
        )
    except MemoryInactiveError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Inactive memory cannot be promoted. Re-activate it first.",
        )

    return PromotionResponse.model_validate(knowledge)


# =============================================================================
# Workspace Knowledge Endpoints
# =============================================================================


@router.get("/knowledge", response_model=WorkspaceKnowledgeListResponse)
async def list_workspace_knowledge(
    tenant: TenantContextDep,
    db: DBSessionDep,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> WorkspaceKnowledgeListResponse:
    """List workspace knowledge items (shared across all workspace users).

    Returns paginated knowledge items, newest first. All workspace
    users can view workspace knowledge.
    """
    promotion_service = MemoryPromotionService(db=db)
    items, total = await promotion_service.list_workspace_knowledge(
        org_id=tenant.org_id,
        limit=limit,
        offset=offset,
    )
    return WorkspaceKnowledgeListResponse(
        items=[WorkspaceKnowledgeResponse.model_validate(k) for k in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.delete(
    "/knowledge/{knowledge_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_workspace_knowledge(
    knowledge_id: UUID,
    tenant: TenantContextDep,
    db: DBSessionDep,
) -> None:
    """Delete a workspace knowledge item.

    Requires owner or admin role (R94.2). Returns 403 if insufficient
    permissions, 404 if not found.
    """
    promotion_service = MemoryPromotionService(db=db)
    try:
        await promotion_service.delete_workspace_knowledge(
            knowledge_id=knowledge_id,
            org_id=tenant.org_id,
            user_id=tenant.user_id,
            role=tenant.role.value,
        )
    except InsufficientRoleError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions. Requires admin role or above.",
        )
    except KnowledgeNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace knowledge item not found",
        )

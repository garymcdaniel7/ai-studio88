"""Talent API endpoints with RBAC enforcement.

Full CRUD for AI Talent with:
    - Identity classification (FICTIONAL, REAL_PERSON_SELF, REAL_PERSON_AUTHORIZED)
    - Soft-delete (sets deleted_at, excluded from queries)
    - Typed relationships between talents
    - LoRA model associations (max 5 per talent)

Role enforcement:
    - GET: Viewer role sufficient
    - POST/PATCH: Editor role required
    - DELETE: Admin role required (sensitive resource)

Requirements: R3.1-R3.6, R10.1, R10.4, R10.5, R10.6, R10.7, R10.8
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, status

from app.core.dependencies import DBSessionDep
from app.core.rbac import AdminDep, EditorDep, ViewerDep
from app.schemas.talent import (
    TalentCreate,
    TalentListResponse,
    TalentLoraCreate,
    TalentLoraListResponse,
    TalentLoraResponse,
    TalentLoraUpdate,
    TalentRelationshipCreate,
    TalentRelationshipListResponse,
    TalentRelationshipResponse,
    TalentResponse,
    TalentUpdate,
)
from app.services.talent_service import TalentService

router = APIRouter(prefix="/talent", tags=["talent"])


# =============================================================================
# Talent CRUD
# =============================================================================


@router.get("", response_model=TalentListResponse)
async def list_talent(
    tenant: ViewerDep,
    db: DBSessionDep,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    is_active: bool | None = Query(None),
    talent_type: str | None = Query(None),
) -> TalentListResponse:
    """List AI Talent for the authenticated workspace.

    Requires: VIEWER role (any authenticated member).
    """
    service = TalentService(db=db, org_id=tenant.org_id)
    items, total = await service.list_talent(
        limit=limit,
        offset=offset,
        is_active=is_active,
        talent_type=talent_type,
    )
    return TalentListResponse(
        items=[TalentResponse.model_validate(t) for t in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{talent_id}", response_model=TalentResponse)
async def get_talent(
    talent_id: UUID,
    tenant: ViewerDep,
    db: DBSessionDep,
) -> TalentResponse:
    """Get a single AI Talent by ID.

    Requires: VIEWER role.
    Returns 404 if not found or belongs to different org.
    """
    service = TalentService(db=db, org_id=tenant.org_id)
    talent = await service.get_talent(talent_id)
    return TalentResponse.model_validate(talent)


@router.post("", response_model=TalentResponse, status_code=status.HTTP_201_CREATED)
async def create_talent(
    body: TalentCreate,
    tenant: EditorDep,
    db: DBSessionDep,
) -> TalentResponse:
    """Create a new AI Talent.

    Requires: EDITOR role (viewers are blocked from mutations).
    org_id is set automatically from the authenticated context.
    """
    service = TalentService(db=db, org_id=tenant.org_id)
    talent = await service.create_talent(
        name=body.name,
        description=body.description,
        talent_type=body.talent_type.value if body.talent_type else None,
        identity_classification=(
            body.identity_classification.value if body.identity_classification else None
        ),
        is_active=body.is_active,
    )
    return TalentResponse.model_validate(talent)


@router.patch("/{talent_id}", response_model=TalentResponse)
async def update_talent(
    talent_id: UUID,
    body: TalentUpdate,
    tenant: EditorDep,
    db: DBSessionDep,
) -> TalentResponse:
    """Update an existing AI Talent.

    Requires: EDITOR role.
    Returns 404 if not found or cross-tenant.
    """
    service = TalentService(db=db, org_id=tenant.org_id)
    update_data = body.model_dump(exclude_unset=True)

    # Convert enums to their values for storage
    if "talent_type" in update_data and update_data["talent_type"] is not None:
        update_data["talent_type"] = update_data["talent_type"].value
    if (
        "identity_classification" in update_data
        and update_data["identity_classification"] is not None
    ):
        update_data["identity_classification"] = update_data[
            "identity_classification"
        ].value

    talent = await service.update_talent(talent_id, **update_data)
    return TalentResponse.model_validate(talent)


@router.delete("/{talent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_talent(
    talent_id: UUID,
    tenant: AdminDep,
    db: DBSessionDep,
) -> None:
    """Soft-delete an AI Talent.

    Requires: ADMIN role (sensitive resource — editors cannot delete talent).
    The record is soft-deleted (sets deleted_at), not permanently removed.
    Returns 404 if not found or cross-tenant.

    Requirements: R3.4 (editor blocked from DELETE on talent), R10.6
    """
    service = TalentService(db=db, org_id=tenant.org_id)
    await service.soft_delete_talent(talent_id)


# =============================================================================
# Talent Relationships (R10.7)
# =============================================================================


@router.post(
    "/{talent_id}/relationships",
    response_model=TalentRelationshipResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_relationship(
    talent_id: UUID,
    body: TalentRelationshipCreate,
    tenant: EditorDep,
    db: DBSessionDep,
) -> TalentRelationshipResponse:
    """Create a typed relationship from this talent to another.

    Requires: EDITOR role.
    Both source and target talent must exist in the same org.
    Unique constraint on (source, target, type).
    """
    service = TalentService(db=db, org_id=tenant.org_id)
    relationship = await service.create_relationship(
        source_talent_id=talent_id,
        target_talent_id=body.target_talent_id,
        relationship_type=body.relationship_type.value,
        metadata=body.metadata,
    )
    return TalentRelationshipResponse.model_validate(relationship)


@router.get(
    "/{talent_id}/relationships",
    response_model=TalentRelationshipListResponse,
)
async def list_relationships(
    talent_id: UUID,
    tenant: ViewerDep,
    db: DBSessionDep,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> TalentRelationshipListResponse:
    """List relationships where this talent is the source.

    Requires: VIEWER role.
    """
    service = TalentService(db=db, org_id=tenant.org_id)
    items, total = await service.list_relationships(
        talent_id=talent_id, limit=limit, offset=offset
    )
    return TalentRelationshipListResponse(
        items=[TalentRelationshipResponse.model_validate(r) for r in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.delete(
    "/{talent_id}/relationships/{relationship_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_relationship(
    talent_id: UUID,
    relationship_id: UUID,
    tenant: EditorDep,
    db: DBSessionDep,
) -> None:
    """Delete a relationship.

    Requires: EDITOR role.
    """
    service = TalentService(db=db, org_id=tenant.org_id)
    await service.delete_relationship(talent_id, relationship_id)


# =============================================================================
# Talent LoRA Associations (R10.8)
# =============================================================================


@router.post(
    "/{talent_id}/loras",
    response_model=TalentLoraResponse,
    status_code=status.HTTP_201_CREATED,
)
async def assign_lora(
    talent_id: UUID,
    body: TalentLoraCreate,
    tenant: EditorDep,
    db: DBSessionDep,
) -> TalentLoraResponse:
    """Assign a LoRA model to this talent.

    Requires: EDITOR role.
    Max 5 LoRAs per talent.
    """
    service = TalentService(db=db, org_id=tenant.org_id)
    lora_assoc = await service.assign_lora(
        talent_id=talent_id,
        lora_model_id=body.lora_model_id,
        type=body.type.value,
        strength=body.strength,
        always_on=body.always_on,
    )
    return TalentLoraResponse.model_validate(lora_assoc)


@router.get(
    "/{talent_id}/loras",
    response_model=TalentLoraListResponse,
)
async def list_loras(
    talent_id: UUID,
    tenant: ViewerDep,
    db: DBSessionDep,
) -> TalentLoraListResponse:
    """List LoRAs associated with this talent.

    Requires: VIEWER role.
    """
    service = TalentService(db=db, org_id=tenant.org_id)
    items, total = await service.list_loras(talent_id)
    return TalentLoraListResponse(
        items=[TalentLoraResponse.model_validate(l) for l in items],
        total=total,
    )


@router.patch(
    "/{talent_id}/loras/{lora_id}",
    response_model=TalentLoraResponse,
)
async def update_lora(
    talent_id: UUID,
    lora_id: UUID,
    body: TalentLoraUpdate,
    tenant: EditorDep,
    db: DBSessionDep,
) -> TalentLoraResponse:
    """Update a LoRA association (strength, type, always_on).

    Requires: EDITOR role.
    """
    service = TalentService(db=db, org_id=tenant.org_id)
    update_data = body.model_dump(exclude_unset=True)

    # Convert enums to their values
    if "type" in update_data and update_data["type"] is not None:
        update_data["type"] = update_data["type"].value

    lora_assoc = await service.update_lora(talent_id, lora_id, **update_data)
    return TalentLoraResponse.model_validate(lora_assoc)


@router.delete(
    "/{talent_id}/loras/{lora_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_lora(
    talent_id: UUID,
    lora_id: UUID,
    tenant: EditorDep,
    db: DBSessionDep,
) -> None:
    """Remove a LoRA association from this talent.

    Requires: EDITOR role.
    """
    service = TalentService(db=db, org_id=tenant.org_id)
    await service.remove_lora(talent_id, lora_id)

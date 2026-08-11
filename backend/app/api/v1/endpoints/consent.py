"""Consent API endpoints.

Provides CRUD + revocation for consent records:
    - GET  /api/v1/consent       — list workspace consent records (paginated)
    - POST /api/v1/consent       — create a consent record
    - PUT  /api/v1/consent/{id}  — update mutable fields
    - POST /api/v1/consent/{id}/revoke — revoke (preserves audit trail)

Consent is a first-class subsystem — versioned, scoped, revocable, auditable.
Fictional talent exemption: FICTIONAL identity_classification doesn't require
consent for generation (enforced at governance layer, not here).

Requirements: R10.2, R10.3, A2-004
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, status

from app.core.dependencies import DBSessionDep, TenantContextDep
from app.core.rbac import EditorDep, ViewerDep
from app.schemas.consent import (
    ConsentCreateRequest,
    ConsentListResponse,
    ConsentResponse,
    ConsentRevokeRequest,
    ConsentUpdateRequest,
)
from app.services.consent_service import ConsentService

router = APIRouter(prefix="/consent", tags=["consent"])


# =============================================================================
# Helper to build response from ORM model
# =============================================================================


def _to_response(record: object) -> ConsentResponse:
    """Convert a ConsentRecord ORM instance to a response schema."""
    return ConsentResponse(
        id=record.id,
        org_id=record.org_id,
        talent_id=record.talent_id,
        scopes=record.scopes,
        evidence_type=record.evidence_type,
        evidence_url=record.evidence_url,
        grantor_identity=record.grantor_identity,
        granted_at=record.granted_at,
        expires_at=record.expires_at,
        revoked_at=record.revoked_at,
        revocation_reason=record.revocation_reason,
        restrictions=record.restrictions,
        provenance=record.provenance,
        version=record.version,
        verification_state=record.verification_state,
        is_active=record.is_active,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


# =============================================================================
# Endpoints
# =============================================================================


@router.get("", response_model=ConsentListResponse)
async def list_consent(
    tenant: ViewerDep,
    db: DBSessionDep,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    talent_id: UUID | None = Query(None, description="Filter by talent UUID"),
    scope: str | None = Query(None, description="Filter by consent scope"),
    active_only: bool = Query(False, description="Only show active (non-revoked, non-expired) records"),
) -> ConsentListResponse:
    """List consent records for the authenticated workspace.

    Returns paginated consent records with optional filters.
    Requires: VIEWER role (any authenticated member can read).

    Requirements: R10.2, A2-004
    """
    service = ConsentService(db=db, tenant=tenant)
    items, total = await service.list_consent(
        limit=limit,
        offset=offset,
        talent_id=talent_id,
        scope=scope,
        active_only=active_only,
    )
    return ConsentListResponse(
        items=[_to_response(r) for r in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=ConsentResponse, status_code=status.HTTP_201_CREATED)
async def create_consent(
    body: ConsentCreateRequest,
    tenant: EditorDep,
    db: DBSessionDep,
) -> ConsentResponse:
    """Create a new consent record.

    Requires: EDITOR role (viewers cannot create consent records).
    org_id is set automatically from the authenticated context.
    Version is auto-incremented per talent.

    Requirements: R10.2, R10.3, A2-004
    """
    service = ConsentService(db=db, tenant=tenant)
    record = await service.create_consent(
        talent_id=body.talent_id,
        scopes=[s.value for s in body.scopes],
        provenance=body.provenance.value,
        evidence_type=body.evidence_type.value if body.evidence_type else None,
        evidence_url=body.evidence_url,
        grantor_identity=body.grantor_identity,
        granted_at=body.granted_at,
        expires_at=body.expires_at,
        restrictions=body.restrictions,
        verification_state=body.verification_state.value,
    )
    return _to_response(record)


@router.put("/{consent_id}", response_model=ConsentResponse)
async def update_consent(
    consent_id: UUID,
    body: ConsentUpdateRequest,
    tenant: EditorDep,
    db: DBSessionDep,
) -> ConsentResponse:
    """Update mutable fields on a consent record.

    Core fields (talent_id, scopes, granted_at, provenance) are immutable.
    Only evidence, expiry, restrictions, and verification_state can change.

    Requires: EDITOR role.
    Returns 404 if not found or cross-tenant.
    Returns 400 if record is already revoked.

    Requirements: R10.3, A2-004
    """
    service = ConsentService(db=db, tenant=tenant)
    update_data = body.model_dump(exclude_unset=True)

    # Convert enums to their string values
    if "evidence_type" in update_data and update_data["evidence_type"] is not None:
        update_data["evidence_type"] = update_data["evidence_type"].value
    if "verification_state" in update_data and update_data["verification_state"] is not None:
        update_data["verification_state"] = update_data["verification_state"].value

    record = await service.update_consent(consent_id, **update_data)
    return _to_response(record)


@router.post("/{consent_id}/revoke", response_model=ConsentResponse)
async def revoke_consent(
    consent_id: UUID,
    body: ConsentRevokeRequest,
    tenant: EditorDep,
    db: DBSessionDep,
) -> ConsentResponse:
    """Revoke a consent record.

    Revocation prevents FUTURE use but does NOT falsify historical
    audit records. The record remains with revoked_at timestamp.

    Requires: EDITOR role.
    Returns 404 if not found or cross-tenant.
    Returns 400 if already revoked.

    Requirements: R10.2, R10.3, A2-004
    """
    service = ConsentService(db=db, tenant=tenant)
    record = await service.revoke_consent(consent_id, body.revocation_reason)
    return _to_response(record)

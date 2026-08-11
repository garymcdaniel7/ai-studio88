"""Dataset Manifests API endpoints.

Provides immutable dataset manifest management for training:
    - POST /api/v1/training/manifests      — create an immutable manifest (201)
    - GET  /api/v1/training/manifests      — list manifests (paginated)
    - GET  /api/v1/training/manifests/{id} — get a single manifest
    - POST /api/v1/training/manifests/{id}/verify — verify manifest integrity
    - POST /api/v1/training/manifests/compare     — compare two manifests

Dataset manifests are immutable — once created, no update or delete endpoint
exists. Verification detects deleted files and revoked consent.

Requirements: R61.1, R61.2, R61.3, R61.4, R61.5, R61.6
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, status

from app.core.dependencies import DBSessionDep, TenantContextDep
from app.core.rbac import EditorDep, ViewerDep
from app.schemas.dataset_manifest import (
    DatasetManifestCreateRequest,
    DatasetManifestListResponse,
    DatasetManifestResponse,
    ManifestComparisonResult,
    ManifestFileResponse,
    ManifestVerificationResult,
)
from app.services.dataset_manifest_service import DatasetManifestService

router = APIRouter(prefix="/training/manifests", tags=["training-manifests"])


# =============================================================================
# Helper to build response from ORM model
# =============================================================================


def _to_response(manifest: object) -> DatasetManifestResponse:
    """Convert a DatasetManifest ORM instance to a response schema."""
    return DatasetManifestResponse(
        id=manifest.id,
        org_id=manifest.org_id,
        version=manifest.version,
        talent_id=manifest.talent_id,
        manifest_files=[
            ManifestFileResponse(**f) for f in manifest.manifest_files
        ],
        consent_record_ids=manifest.consent_record_ids or [],
        total_file_count=manifest.total_file_count,
        total_size_bytes=manifest.total_size_bytes,
        is_valid=manifest.is_valid,
        invalidated_at=manifest.invalidated_at,
        invalidation_reason=manifest.invalidation_reason,
        created_by=manifest.created_by,
        created_at=manifest.created_at,
        updated_at=manifest.updated_at,
    )


# =============================================================================
# Endpoints
# =============================================================================


@router.post("", response_model=DatasetManifestResponse, status_code=status.HTTP_201_CREATED)
async def create_manifest(
    body: DatasetManifestCreateRequest,
    tenant: EditorDep,
    db: DBSessionDep,
) -> DatasetManifestResponse:
    """Create an immutable dataset manifest.

    Validates consent records, talent existence, and file references
    before creating the manifest. Once created, the manifest is never
    modified.

    Requires: EDITOR role.

    Requirements: R61.1, R61.2
    """
    service = DatasetManifestService(db=db, tenant=tenant)
    manifest = await service.create_manifest(data=body)
    return _to_response(manifest)


@router.get("", response_model=DatasetManifestListResponse)
async def list_manifests(
    tenant: ViewerDep,
    db: DBSessionDep,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    talent_id: UUID | None = Query(None, description="Filter by talent UUID"),
) -> DatasetManifestListResponse:
    """List dataset manifests for the authenticated workspace.

    Returns paginated manifests with optional talent filter.
    Requires: VIEWER role (any authenticated member can read).

    Requirements: R61.1
    """
    service = DatasetManifestService(db=db, tenant=tenant)
    items, total = await service.list_manifests(
        limit=limit,
        offset=offset,
        talent_id=talent_id,
    )
    return DatasetManifestListResponse(
        items=[_to_response(m) for m in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{manifest_id}", response_model=DatasetManifestResponse)
async def get_manifest(
    manifest_id: UUID,
    tenant: ViewerDep,
    db: DBSessionDep,
) -> DatasetManifestResponse:
    """Get a single dataset manifest by ID.

    Requires: VIEWER role.
    Returns 404 if not found or cross-tenant.

    Requirements: R61.1
    """
    service = DatasetManifestService(db=db, tenant=tenant)
    manifest = await service.get_manifest(manifest_id)
    return _to_response(manifest)


@router.post("/{manifest_id}/verify", response_model=ManifestVerificationResult)
async def verify_manifest(
    manifest_id: UUID,
    tenant: EditorDep,
    db: DBSessionDep,
) -> ManifestVerificationResult:
    """Verify a dataset manifest for integrity and consent validity.

    Checks all files still exist in storage and all consent records
    are still active. If verification fails, the training job MUST
    be rejected before starting paid GPU work.

    Requires: EDITOR role.
    Returns 404 if manifest not found.

    Requirements: R61.4, R61.5
    """
    service = DatasetManifestService(db=db, tenant=tenant)
    return await service.verify_manifest(manifest_id)


@router.post("/compare", response_model=ManifestComparisonResult)
async def compare_manifests(
    manifest_a_id: UUID = Query(description="First manifest UUID (older)"),
    manifest_b_id: UUID = Query(description="Second manifest UUID (newer)"),
    tenant: ViewerDep = ...,
    db: DBSessionDep = ...,
) -> ManifestComparisonResult:
    """Compare two dataset manifest versions.

    Shows what files were added, removed, or changed between two
    manifest versions.

    Requires: VIEWER role.
    Returns 404 if either manifest not found.

    Requirements: R61.6
    """
    service = DatasetManifestService(db=db, tenant=tenant)
    return await service.compare_manifests(manifest_a_id, manifest_b_id)

"""Workspace Disclosure Configuration API endpoints.

Provides disclosure hook management for publishing:
    - GET  /api/v1/publishing/disclosure-config    — get workspace config
    - PUT  /api/v1/publishing/disclosure-config    — update workspace config
    - POST /api/v1/publishing/disclosure-preview   — preview disclosures for a post

Disclosure hooks are evaluated at publish time to determine what
disclosures (AI labeling, sponsorship, C2PA, platform-specific) must be
included in published content.

Requirements: R80.1, R80.2, R80.3, R80.4, R80.5, R80.6
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.core.dependencies import DBSessionDep, TenantContextDep
from app.core.rbac import AdminDep, ViewerDep
from app.schemas.disclosure_config import (
    DisclosureConfigResponse,
    DisclosureConfigUpdateRequest,
    DisclosurePreviewRequest,
    DisclosurePreviewResponse,
)
from app.services.disclosure_hook_service import DisclosureHookService

router = APIRouter(prefix="/publishing", tags=["publishing-disclosure"])


# =============================================================================
# Endpoints
# =============================================================================


@router.get(
    "/disclosure-config",
    response_model=DisclosureConfigResponse,
    summary="Get workspace disclosure configuration",
    description=(
        "Returns the current disclosure hook configuration for the workspace. "
        "Creates a default configuration (all disabled) if none exists."
    ),
)
async def get_disclosure_config(
    tenant: ViewerDep,
    db: DBSessionDep,
) -> DisclosureConfigResponse:
    """Get the workspace disclosure configuration.

    Any authenticated workspace member can read the disclosure config.

    Requirements: R80.3
    """
    service = DisclosureHookService(db=db, tenant=tenant)
    config = await service.get_config()
    await db.commit()

    return DisclosureConfigResponse(
        id=config.id,
        org_id=config.org_id,
        ai_disclosure_enabled=config.ai_disclosure_enabled,
        ai_disclosure_text=config.ai_disclosure_text,
        sponsorship_disclosure_enabled=config.sponsorship_disclosure_enabled,
        sponsorship_text=config.sponsorship_text,
        disclosure_tags=config.disclosure_tags,
        platform_requirements=config.platform_requirements,
        c2pa_enabled=config.c2pa_enabled,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


@router.put(
    "/disclosure-config",
    response_model=DisclosureConfigResponse,
    summary="Update workspace disclosure configuration",
    description=(
        "Updates the disclosure hook configuration for the workspace. "
        "Only provided fields are updated. Requires ADMIN role."
    ),
)
async def update_disclosure_config(
    request: DisclosureConfigUpdateRequest,
    tenant: AdminDep,
    db: DBSessionDep,
) -> DisclosureConfigResponse:
    """Update the workspace disclosure configuration.

    Requires ADMIN role — disclosure policy affects all publishing.

    Requirements: R80.2, R80.3
    """
    service = DisclosureHookService(db=db, tenant=tenant)
    config = await service.update_config(request)
    await db.commit()

    return DisclosureConfigResponse(
        id=config.id,
        org_id=config.org_id,
        ai_disclosure_enabled=config.ai_disclosure_enabled,
        ai_disclosure_text=config.ai_disclosure_text,
        sponsorship_disclosure_enabled=config.sponsorship_disclosure_enabled,
        sponsorship_text=config.sponsorship_text,
        disclosure_tags=config.disclosure_tags,
        platform_requirements=config.platform_requirements,
        c2pa_enabled=config.c2pa_enabled,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


@router.post(
    "/disclosure-preview",
    response_model=DisclosurePreviewResponse,
    summary="Preview disclosures for a post",
    description=(
        "Shows the user exactly what disclosures will be attached to a post "
        "before publishing. Does not persist anything — purely read-only."
    ),
)
async def preview_disclosures(
    request: DisclosurePreviewRequest,
    tenant: TenantContextDep,
    db: DBSessionDep,
) -> DisclosurePreviewResponse:
    """Preview what disclosures would be applied to a post.

    Any authenticated member can preview disclosures. This helps users
    understand what will be added to their content before publishing.

    Requirements: R80.5
    """
    service = DisclosureHookService(db=db, tenant=tenant)
    preview = await service.preview_disclosures(
        platform=request.platform,
        caption=request.caption,
        is_sponsored=request.is_sponsored,
        asset_id=request.asset_id,
    )
    await db.commit()

    return preview

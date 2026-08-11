"""Workspace Privacy Restrictions endpoints.

Routes:
    GET  /api/v1/workspace/privacy  → 200 (current privacy restrictions)
    PUT  /api/v1/workspace/privacy  → 200 (replace all privacy restrictions)

Access: ADMIN or above for PUT, VIEWER or above for GET.
These endpoints are tenant-scoped — each workspace manages its own
privacy restrictions.

Validates: Requirements R103.1, R103.2, R103.3
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status

from app.core.dependencies import DBSessionDep
from app.core.rbac import AdminDep, ViewerDep
from app.schemas.workspace_privacy import (
    WorkspacePrivacyConfigResponse,
    WorkspacePrivacyConfigUpdate,
    WorkspacePrivacyRestrictionResponse,
)
from app.services.workspace_privacy_service import (
    InvalidRestrictionTypeError,
    PrivacyRestriction,
    WorkspacePrivacyService,
)

router = APIRouter(prefix="/workspace", tags=["workspace"])


# =============================================================================
# Helpers
# =============================================================================

_EPOCH = datetime(2020, 1, 1, tzinfo=timezone.utc)


def _restriction_to_response(r: PrivacyRestriction) -> WorkspacePrivacyRestrictionResponse:
    """Convert a PrivacyRestriction dataclass to a response schema."""
    return WorkspacePrivacyRestrictionResponse(
        id=r.id,
        org_id=r.org_id,
        restriction_type=r.restriction_type,
        restriction_target=r.restriction_target,
        allowed_providers=r.allowed_providers,
        denied_providers=r.denied_providers,
        created_at=r.created_at or _EPOCH,
        updated_at=r.updated_at or _EPOCH,
    )


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/privacy", response_model=WorkspacePrivacyConfigResponse)
async def get_workspace_privacy(
    tenant: ViewerDep,
    db: DBSessionDep,
) -> WorkspacePrivacyConfigResponse:
    """Get the current workspace privacy restrictions.

    Returns all active privacy restrictions for this workspace.
    An empty restrictions list means no privacy restrictions are active
    (any provider can be used).

    Requires: VIEWER role or above.

    Requirements: R103.1
    """
    service = WorkspacePrivacyService(db=db)
    restrictions = await service.get_restrictions(org_id=tenant.org_id)

    return WorkspacePrivacyConfigResponse(
        org_id=tenant.org_id,
        restrictions=[_restriction_to_response(r) for r in restrictions],
    )


@router.put("/privacy", response_model=WorkspacePrivacyConfigResponse)
async def update_workspace_privacy(
    body: WorkspacePrivacyConfigUpdate,
    tenant: AdminDep,
    db: DBSessionDep,
) -> WorkspacePrivacyConfigResponse:
    """Replace all workspace privacy restrictions.

    This is a full replacement operation. Existing restrictions are
    deleted and replaced with the provided list. To remove all
    restrictions, send an empty list.

    Restriction types:
    - local_models_only: Only local LLM providers (Ollama, LM Studio)
    - customer_compute_only: No platform-managed GPU compute
    - approved_llm_only: Only whitelisted LLM providers
    - no_external_llm_for_project: Project-scoped local-only LLM
    - approved_storage_only: Only whitelisted storage providers
    - talent_provider_restriction: Per-talent provider rules
    - project_privacy: Project-scoped combined privacy settings

    Brain/Hermes, LLM routing, job dispatch, and all execution paths
    check these restrictions. If a restriction prevents fulfilling a
    request, the system returns PRIVACY_POLICY_BLOCKED (403) rather
    than silently violating the policy.

    Requires: ADMIN role or above.

    Requirements: R103.1, R103.2, R103.3
    """
    service = WorkspacePrivacyService(db=db)

    # Convert Pydantic models to dicts for the service
    restriction_dicts = [
        {
            "restriction_type": r.restriction_type.value,
            "restriction_target": r.restriction_target,
            "allowed_providers": r.allowed_providers,
            "denied_providers": r.denied_providers,
        }
        for r in body.restrictions
    ]

    try:
        new_restrictions = await service.set_restrictions(
            org_id=tenant.org_id,
            restrictions=restriction_dicts,
        )
    except InvalidRestrictionTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    return WorkspacePrivacyConfigResponse(
        org_id=tenant.org_id,
        restrictions=[_restriction_to_response(r) for r in new_restrictions],
    )

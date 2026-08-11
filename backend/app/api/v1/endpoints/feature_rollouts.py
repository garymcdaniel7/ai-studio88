"""Platform Admin — Feature Rollout endpoints.

Routes:
    GET    /api/v1/admin/feature-rollouts      → 200 (list active rollouts)
    POST   /api/v1/admin/feature-rollouts      → 201 (create rollout rule)
    DELETE /api/v1/admin/feature-rollouts/{id}  → 204 (delete rollout rule)

Access: Platform Operators with Platform Configuration capability only.
These endpoints are NOT tenant-scoped — they manage platform-level config.

No code deployment is required for state changes. Creating or deleting
a rollout rule immediately affects capability availability.

Validates: Requirements R106.1, R106.2, R106.3, R19.9, R19.10
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.core.dependencies import DBSessionDep
from app.core.rbac import OwnerDep
from app.schemas.feature_rollout import (
    FeatureRolloutCreate,
    FeatureRolloutListResponse,
    FeatureRolloutResponse,
)
from app.services.feature_rollout_db_service import FeatureRolloutDBService

router = APIRouter(
    prefix="/api/v1/admin/feature-rollouts",
    tags=["platform-admin"],
)


# =============================================================================
# Endpoints
# =============================================================================


@router.get("", response_model=FeatureRolloutListResponse)
async def list_feature_rollouts(
    tenant: OwnerDep,
    db: DBSessionDep,
    capability_name: str | None = Query(
        default=None,
        description="Filter by capability name",
    ),
) -> FeatureRolloutListResponse:
    """List all active feature rollout rules.

    Returns non-expired rollout rules, optionally filtered by capability
    name. Results ordered by created_at descending.

    Requires: OWNER role (Platform Configuration capability).

    Requirements: R106.1
    """
    service = FeatureRolloutDBService(db=db)
    rollouts = await service.list_rollouts(capability_name=capability_name)

    items = [
        FeatureRolloutResponse(
            id=r.id,
            capability_name=r.capability_name,
            rollout_scope=r.rollout_scope,
            scope_target=r.scope_target,
            enabled=r.enabled,
            expires_at=r.expires_at,
            created_by=r.created_by,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in rollouts
    ]

    return FeatureRolloutListResponse(
        items=items,
        total=len(items),
        limit=100,
        offset=0,
    )


@router.post(
    "",
    response_model=FeatureRolloutResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_feature_rollout(
    body: FeatureRolloutCreate,
    tenant: OwnerDep,
    db: DBSessionDep,
) -> FeatureRolloutResponse:
    """Create a feature rollout rule.

    Creates a new rollout rule controlling whether a capability is
    enabled or disabled for a specific scope/target. The change takes
    effect immediately without code deployment.

    Scopes:
        - global: Affects all workspaces/users
        - plan: Affects workspaces on a specific plan tier
        - workspace: Affects a specific workspace (by org_id)
        - cohort: Affects users in a specific cohort
        - user: Affects a specific user
        - workload: Affects a specific workload type
        - provider: Affects a specific provider

    Requires: OWNER role (Platform Configuration capability).

    Requirements: R106.1, R106.2, R19.10
    """
    # Validate that non-global scopes have a target
    if body.rollout_scope != "global" and not body.scope_target:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="scope_target is required for non-global rollout scopes",
            headers={"X-Error-Code": "VALIDATION_ERROR"},
        )

    service = FeatureRolloutDBService(db=db)
    rollout = await service.create_rollout(
        capability_name=body.capability_name,
        scope=body.rollout_scope.value,
        target=body.scope_target,
        enabled=body.enabled,
        created_by=tenant.user_id,
        expires_at=body.expires_at,
    )
    await db.commit()

    return FeatureRolloutResponse(
        id=rollout.id,
        capability_name=rollout.capability_name,
        rollout_scope=rollout.rollout_scope,
        scope_target=rollout.scope_target,
        enabled=rollout.enabled,
        expires_at=rollout.expires_at,
        created_by=rollout.created_by,
        created_at=rollout.created_at,
        updated_at=rollout.updated_at,
    )


@router.delete(
    "/{rollout_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_feature_rollout(
    rollout_id: UUID,
    tenant: OwnerDep,
    db: DBSessionDep,
) -> None:
    """Delete a feature rollout rule.

    Permanently removes the rollout rule. If the rule was disabling a
    capability, the capability becomes accessible again immediately.

    Requires: OWNER role (Platform Configuration capability).

    Requirements: R106.1
    """
    service = FeatureRolloutDBService(db=db)
    deleted = await service.delete_rollout(rollout_id=rollout_id)
    await db.commit()

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feature rollout not found",
            headers={"X-Error-Code": "NOT_FOUND"},
        )

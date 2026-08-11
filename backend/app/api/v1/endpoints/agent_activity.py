"""Agent Activity Feed API endpoint.

Provides the user-facing agent activity history answering "What did
Brain/Hermes do?" — scoped to the requesting user's sessions and workspace.

Separate from engineering/debug logs and system observability data (R99.2).

Validates: Requirements R99.1, R99.2, R99.3, R99.4, R30.15
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.core.dependencies import DBSessionDep, TenantContextDep
from app.schemas.agent_activity import (
    ActivityTypeEnum,
    AgentActivityListResponse,
    AgentActivityResponse,
)
from app.services.agent_activity_service import (
    AgentActivityService,
    InvalidActivityTypeError,
)

router = APIRouter(prefix="/brain", tags=["brain-activity"])


@router.get("/activity", response_model=AgentActivityListResponse)
async def list_agent_activity(
    tenant: TenantContextDep,
    db: DBSessionDep,
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    activity_type: ActivityTypeEnum | None = Query(
        None, description="Filter by activity type"
    ),
) -> AgentActivityListResponse:
    """List agent activity for the authenticated user.

    Returns a paginated, newest-first feed of what Brain/Hermes did on
    behalf of the user. Each entry includes timestamp, action type,
    outcome (success/failure/pending), and cost if applicable.

    Scoped to (org_id, user_id) — users cannot see other users' activity
    unless workspace policy explicitly shares it (R99.3).
    """
    service = AgentActivityService(db=db)

    try:
        items, total = await service.list_activity(
            org_id=tenant.org_id,
            user_id=tenant.user_id,
            limit=limit,
            offset=offset,
            activity_type=activity_type.value if activity_type else None,
        )
    except InvalidActivityTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.message,
        )

    return AgentActivityListResponse(
        items=[AgentActivityResponse.model_validate(a) for a in items],
        total=total,
        limit=limit,
        offset=offset,
    )

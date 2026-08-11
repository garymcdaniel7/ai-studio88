"""Platform Admin — Operator, Support Session, and Rights Case endpoints.

Routes:
    GET    /platform-admin/operators                     → 200 (list operators)
    POST   /platform-admin/operators                     → 201 (grant capabilities)
    DELETE /platform-admin/operators/{id}                → 204 (revoke)
    GET    /platform-admin/support-sessions              → 200 (list sessions)
    POST   /platform-admin/support-sessions              → 201 (request session)
    POST   /platform-admin/support-sessions/{id}/approve → 200 (approve)
    POST   /platform-admin/support-sessions/{id}/revoke  → 200 (revoke session)
    GET    /platform-admin/rights-cases                  → 200 (list cases)
    GET    /platform-admin/rights-cases/{id}             → 200 (get case)
    PATCH  /platform-admin/rights-cases/{id}             → 200 (update case)

Access: Platform Operators ONLY — non-operators receive 404 (not 403).
These endpoints are NOT tenant-scoped — they manage platform-level state.

All actions are logged with full audit trail: actor, capability used,
target tenant (if applicable), action type, and timestamp.

Validates: Requirements R33.9, R33.10, R40.3, R40.4, R40.5, R40.8, A2-005
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.dependencies import CurrentUserIDDep, DBSessionDep, PaginationDep
from app.core.logging import get_logger
from app.models.platform_operator import CapabilityGroup, PlatformOperator
from app.schemas.platform_operator import (
    PlatformOperatorCreate,
    PlatformOperatorListResponse,
    PlatformOperatorResponse,
)
from app.schemas.support_session import (
    SupportSessionApprove,
    SupportSessionListResponse,
    SupportSessionRequest,
    SupportSessionResponse,
    SupportSessionRevoke,
)
from app.services.platform_operator_service import (
    InsufficientCapabilityError,
    OperatorAlreadyExistsError,
    OperatorNotFoundError,
    PlatformOperatorService,
)
from app.schemas.rights_case import (
    RightsCaseListResponse,
    RightsCaseResponse,
    RightsCaseUpdateRequest,
)
from app.services.rights_case_service import (
    CaseClosedError,
    CaseNotFoundError,
    InvalidCaseTransitionError,
    RightsCaseService,
)
from app.services.support_session_service import (
    InvalidTransitionError,
    SessionNotFoundError,
    SupportSessionService,
)

logger = get_logger(__name__)


# =============================================================================
# Platform Operator Dependency — returns 404 for non-operators
# =============================================================================


async def require_platform_operator(
    user_id: CurrentUserIDDep,
    db: DBSessionDep,
) -> PlatformOperator:
    """Verify the requesting user is an active Platform Operator.

    Returns 404 (NOT FOUND) for non-operators — this makes the entire
    /platform-admin/* surface invisible to users without capability grants.
    Per R33.10: the route must appear non-existent to unauthorized users.

    Returns:
        The active PlatformOperator record for the requesting user.

    Raises:
        HTTPException 404: If user is not an active Platform Operator.
    """
    service = PlatformOperatorService(db=db)
    operator = await service.get_operator_by_user(user_id)
    if operator is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found",
        )
    return operator


PlatformOperatorDep = Annotated[PlatformOperator, Depends(require_platform_operator)]


def _require_capability(
    operator: PlatformOperator,
    required: CapabilityGroup,
) -> None:
    """Check that an operator has a required capability.

    Raises 404 (hiding the surface) rather than 403 to avoid revealing
    the existence of admin routes to operators without sufficient access.

    Args:
        operator: The authenticated Platform Operator.
        required: The capability group required.

    Raises:
        HTTPException 404: If operator lacks the capability.
    """
    if not operator.has_capability(required):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found",
        )


# =============================================================================
# Router
# =============================================================================

router = APIRouter(
    prefix="/platform-admin",
    tags=["platform-admin"],
)


# =============================================================================
# Operator Endpoints
# =============================================================================


@router.get(
    "/operators",
    response_model=PlatformOperatorListResponse,
)
async def list_operators(
    operator: PlatformOperatorDep,
    db: DBSessionDep,
    pagination: PaginationDep,
    include_revoked: bool = False,
) -> PlatformOperatorListResponse:
    """List all Platform Operators.

    Returns a paginated list of operators, optionally including revoked
    records. Requires at least Platform Observe capability.

    Requirements: R33.9, R33.10
    """
    _require_capability(operator, CapabilityGroup.PLATFORM_OBSERVE)

    service = PlatformOperatorService(db=db)
    items, total = await service.list_operators(
        limit=pagination.limit,
        offset=pagination.offset,
        include_revoked=include_revoked,
    )

    # Log the action
    await service.log_action(
        operator_user_id=operator.user_id,
        capability_used=CapabilityGroup.PLATFORM_OBSERVE.value,
        action_type="list_operators",
        action_detail={"include_revoked": include_revoked},
    )

    return PlatformOperatorListResponse(
        items=[
            PlatformOperatorResponse(
                id=op.id,
                user_id=op.user_id,
                capability_grants=op.capability_grants,
                granted_by=op.granted_by,
                granted_at=op.granted_at,
                revoked_at=op.revoked_at,
                created_at=op.created_at,
                updated_at=op.updated_at,
            )
            for op in items
        ],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.post(
    "/operators",
    response_model=PlatformOperatorResponse,
    status_code=status.HTTP_201_CREATED,
)
async def grant_operator(
    body: PlatformOperatorCreate,
    operator: PlatformOperatorDep,
    db: DBSessionDep,
) -> PlatformOperatorResponse:
    """Grant Platform Operator capabilities to a user.

    Only operators with Founder Authority can grant capabilities.
    A user can have at most one active operator record — revoke the
    existing record before granting new capabilities.

    Requirements: R33.9, R33.10
    """
    _require_capability(operator, CapabilityGroup.FOUNDER_AUTHORITY)

    service = PlatformOperatorService(db=db)
    try:
        new_operator = await service.grant_capabilities(
            user_id=body.user_id,
            capability_grants=[c.value for c in body.capability_grants],
            granted_by=operator.user_id,
        )
    except OperatorAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=exc.message,
            headers={"X-Error-Code": exc.code},
        ) from exc

    return PlatformOperatorResponse(
        id=new_operator.id,
        user_id=new_operator.user_id,
        capability_grants=new_operator.capability_grants,
        granted_by=new_operator.granted_by,
        granted_at=new_operator.granted_at,
        revoked_at=new_operator.revoked_at,
        created_at=new_operator.created_at,
        updated_at=new_operator.updated_at,
    )


@router.delete(
    "/operators/{operator_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_operator(
    operator_id: UUID,
    operator: PlatformOperatorDep,
    db: DBSessionDep,
) -> None:
    """Revoke a Platform Operator's capabilities.

    The operator record is soft-deleted (revoked_at set) — the
    historical record is preserved for audit purposes. Only operators
    with Founder Authority can revoke capabilities.

    Requirements: R33.9, R33.10
    """
    _require_capability(operator, CapabilityGroup.FOUNDER_AUTHORITY)

    service = PlatformOperatorService(db=db)
    try:
        await service.revoke(
            operator_id=operator_id,
            revoked_by=operator.user_id,
        )
    except OperatorNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Platform operator not found",
            headers={"X-Error-Code": "OPERATOR_NOT_FOUND"},
        )


# =============================================================================
# Support Session Endpoints
# =============================================================================


@router.get(
    "/support-sessions",
    response_model=SupportSessionListResponse,
)
async def list_support_sessions(
    operator: PlatformOperatorDep,
    db: DBSessionDep,
    pagination: PaginationDep,
    session_status: str | None = None,
    target_org_id: UUID | None = None,
) -> SupportSessionListResponse:
    """List support sessions.

    Returns a paginated list of support sessions, optionally filtered
    by status and/or target organization. Requires Tenant Support
    capability.

    Requirements: R33.9
    """
    _require_capability(operator, CapabilityGroup.TENANT_SUPPORT)

    service = SupportSessionService(db=db)
    items, total = await service.list_sessions(
        limit=pagination.limit,
        offset=pagination.offset,
        status=session_status,
        target_org_id=target_org_id,
    )

    # Log the action
    op_service = PlatformOperatorService(db=db)
    await op_service.log_action(
        operator_user_id=operator.user_id,
        capability_used=CapabilityGroup.TENANT_SUPPORT.value,
        action_type="list_support_sessions",
        target_org_id=target_org_id,
        action_detail={"status_filter": session_status},
    )

    return SupportSessionListResponse(
        items=[
            SupportSessionResponse(
                id=s.id,
                operator_user_id=s.operator_user_id,
                target_org_id=s.target_org_id,
                reason=s.reason,
                requested_capabilities=s.requested_capabilities,
                approved_capabilities=s.approved_capabilities,
                permitted_surfaces=s.permitted_surfaces,
                permitted_actions=s.permitted_actions,
                approved_by=s.approved_by,
                started_at=s.started_at,
                expires_at=s.expires_at,
                ended_at=s.ended_at,
                status=s.status,
                created_at=s.created_at,
                updated_at=s.updated_at,
            )
            for s in items
        ],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.post(
    "/support-sessions",
    response_model=SupportSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def request_support_session(
    body: SupportSessionRequest,
    operator: PlatformOperatorDep,
    db: DBSessionDep,
) -> SupportSessionResponse:
    """Request a new support session for a target workspace.

    Creates a session in REQUESTED status. The session must be approved
    by a Founder or operator with escalation capability before it can
    be used. Requires Tenant Access Escalation capability.

    Requirements: R33.8, R33.9
    """
    _require_capability(operator, CapabilityGroup.TENANT_ACCESS_ESCALATION)

    service = SupportSessionService(db=db)
    session = await service.request_session(
        operator_user_id=operator.user_id,
        target_org_id=body.target_org_id,
        reason=body.reason,
        requested_capabilities=body.requested_capabilities,
        permitted_surfaces=body.permitted_surfaces,
        permitted_actions=body.permitted_actions,
        duration_minutes=body.duration_minutes,
    )

    # Log the action
    op_service = PlatformOperatorService(db=db)
    await op_service.log_action(
        operator_user_id=operator.user_id,
        capability_used=CapabilityGroup.TENANT_ACCESS_ESCALATION.value,
        action_type="request_support_session",
        target_org_id=body.target_org_id,
        action_detail={
            "session_id": str(session.id),
            "reason": body.reason,
            "duration_minutes": body.duration_minutes,
        },
    )

    return SupportSessionResponse(
        id=session.id,
        operator_user_id=session.operator_user_id,
        target_org_id=session.target_org_id,
        reason=session.reason,
        requested_capabilities=session.requested_capabilities,
        approved_capabilities=session.approved_capabilities,
        permitted_surfaces=session.permitted_surfaces,
        permitted_actions=session.permitted_actions,
        approved_by=session.approved_by,
        started_at=session.started_at,
        expires_at=session.expires_at,
        ended_at=session.ended_at,
        status=session.status,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


@router.post(
    "/support-sessions/{session_id}/approve",
    response_model=SupportSessionResponse,
)
async def approve_support_session(
    session_id: UUID,
    body: SupportSessionApprove,
    operator: PlatformOperatorDep,
    db: DBSessionDep,
) -> SupportSessionResponse:
    """Approve a pending support session.

    The approver may restrict capabilities, surfaces, and actions to a
    subset of what was requested. Requires Founder Authority.

    Requirements: R33.8, R33.9
    """
    _require_capability(operator, CapabilityGroup.FOUNDER_AUTHORITY)

    service = SupportSessionService(db=db)
    try:
        session = await service.approve_session(
            session_id=session_id,
            approved_by=operator.user_id,
            approved_capabilities=body.approved_capabilities,
            permitted_surfaces=body.permitted_surfaces,
            permitted_actions=body.permitted_actions,
        )
    except SessionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Support session not found",
            headers={"X-Error-Code": "SESSION_NOT_FOUND"},
        )
    except InvalidTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=exc.message,
            headers={"X-Error-Code": exc.code},
        ) from exc

    # Log the action
    op_service = PlatformOperatorService(db=db)
    await op_service.log_action(
        operator_user_id=operator.user_id,
        capability_used=CapabilityGroup.FOUNDER_AUTHORITY.value,
        action_type="approve_support_session",
        target_org_id=session.target_org_id,
        action_detail={
            "session_id": str(session_id),
            "approved_capabilities": session.approved_capabilities,
        },
    )

    return SupportSessionResponse(
        id=session.id,
        operator_user_id=session.operator_user_id,
        target_org_id=session.target_org_id,
        reason=session.reason,
        requested_capabilities=session.requested_capabilities,
        approved_capabilities=session.approved_capabilities,
        permitted_surfaces=session.permitted_surfaces,
        permitted_actions=session.permitted_actions,
        approved_by=session.approved_by,
        started_at=session.started_at,
        expires_at=session.expires_at,
        ended_at=session.ended_at,
        status=session.status,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


@router.post(
    "/support-sessions/{session_id}/revoke",
    response_model=SupportSessionResponse,
)
async def revoke_support_session(
    session_id: UUID,
    body: SupportSessionRevoke,
    operator: PlatformOperatorDep,
    db: DBSessionDep,
) -> SupportSessionResponse:
    """Revoke a support session immediately.

    Can be called on any non-terminal session (REQUESTED, APPROVED,
    or ACTIVE). Takes effect immediately. Requires Founder Authority
    or Tenant Support capability.

    Requirements: R33.8, R33.9
    """
    # Allow revocation with either Founder Authority or Tenant Support
    if not (
        operator.has_capability(CapabilityGroup.FOUNDER_AUTHORITY)
        or operator.has_capability(CapabilityGroup.TENANT_SUPPORT)
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found",
        )

    service = SupportSessionService(db=db)
    try:
        session = await service.revoke_session(
            session_id=session_id,
            revoked_by=operator.user_id,
            reason=body.reason,
        )
    except SessionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Support session not found",
            headers={"X-Error-Code": "SESSION_NOT_FOUND"},
        )
    except InvalidTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=exc.message,
            headers={"X-Error-Code": exc.code},
        ) from exc

    # Determine which capability was used for audit
    cap_used = (
        CapabilityGroup.FOUNDER_AUTHORITY.value
        if operator.has_capability(CapabilityGroup.FOUNDER_AUTHORITY)
        else CapabilityGroup.TENANT_SUPPORT.value
    )

    # Log the action
    op_service = PlatformOperatorService(db=db)
    await op_service.log_action(
        operator_user_id=operator.user_id,
        capability_used=cap_used,
        action_type="revoke_support_session",
        target_org_id=session.target_org_id,
        action_detail={
            "session_id": str(session_id),
            "reason": body.reason,
        },
    )

    return SupportSessionResponse(
        id=session.id,
        operator_user_id=session.operator_user_id,
        target_org_id=session.target_org_id,
        reason=session.reason,
        requested_capabilities=session.requested_capabilities,
        approved_capabilities=session.approved_capabilities,
        permitted_surfaces=session.permitted_surfaces,
        permitted_actions=session.permitted_actions,
        approved_by=session.approved_by,
        started_at=session.started_at,
        expires_at=session.expires_at,
        ended_at=session.ended_at,
        status=session.status,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


# =============================================================================
# Rights Case Endpoints
# =============================================================================


@router.get(
    "/rights-cases",
    response_model=RightsCaseListResponse,
)
async def list_rights_cases(
    operator: PlatformOperatorDep,
    db: DBSessionDep,
    pagination: PaginationDep,
    case_status: str | None = None,
    case_priority: str | None = None,
    case_type: str | None = None,
    target_org_id: UUID | None = None,
    assigned_to: UUID | None = None,
) -> RightsCaseListResponse:
    """List rights/takedown cases with optional filters.

    Returns a paginated list of cases, filterable by status, priority,
    type, target org, and assigned operator. Requires Safety & Rights
    capability.

    Requirements: R40.3, R40.8, A2-005
    """
    _require_capability(operator, CapabilityGroup.SAFETY_AND_RIGHTS)

    service = RightsCaseService(db=db)
    items, total = await service.list_cases(
        limit=pagination.limit,
        offset=pagination.offset,
        status=case_status,
        priority=case_priority,
        case_type=case_type,
        target_org_id=target_org_id,
        assigned_operator=assigned_to,
    )

    # Log the action
    op_service = PlatformOperatorService(db=db)
    await op_service.log_action(
        operator_user_id=operator.user_id,
        capability_used=CapabilityGroup.SAFETY_AND_RIGHTS.value,
        action_type="list_rights_cases",
        action_detail={
            "status_filter": case_status,
            "priority_filter": case_priority,
            "type_filter": case_type,
        },
    )

    return RightsCaseListResponse(
        items=[
            RightsCaseResponse(
                id=c.id,
                case_type=c.case_type,
                status=c.status,
                priority=c.priority,
                reporter_contact=c.reporter_contact,
                target_org_id=c.target_org_id,
                target_talent_ids=c.target_talent_ids,
                target_asset_ids=c.target_asset_ids,
                reported_urls=c.reported_urls,
                evidence_refs=c.evidence_refs,
                assigned_operator=c.assigned_operator,
                actions_taken=c.actions_taken,
                resolution=c.resolution,
                appeal_state=c.appeal_state,
                legal_hold_active=c.legal_hold_active,
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
            for c in items
        ],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get(
    "/rights-cases/{case_id}",
    response_model=RightsCaseResponse,
)
async def get_rights_case(
    case_id: UUID,
    operator: PlatformOperatorDep,
    db: DBSessionDep,
) -> RightsCaseResponse:
    """Get a single rights case by ID.

    Requires Safety & Rights capability.

    Requirements: R40.3, R40.8, A2-005
    """
    _require_capability(operator, CapabilityGroup.SAFETY_AND_RIGHTS)

    service = RightsCaseService(db=db)
    case = await service.get_case(case_id)
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rights case not found",
            headers={"X-Error-Code": "CASE_NOT_FOUND"},
        )

    return RightsCaseResponse(
        id=case.id,
        case_type=case.case_type,
        status=case.status,
        priority=case.priority,
        reporter_contact=case.reporter_contact,
        target_org_id=case.target_org_id,
        target_talent_ids=case.target_talent_ids,
        target_asset_ids=case.target_asset_ids,
        reported_urls=case.reported_urls,
        evidence_refs=case.evidence_refs,
        assigned_operator=case.assigned_operator,
        actions_taken=case.actions_taken,
        resolution=case.resolution,
        appeal_state=case.appeal_state,
        legal_hold_active=case.legal_hold_active,
        created_at=case.created_at,
        updated_at=case.updated_at,
    )


@router.patch(
    "/rights-cases/{case_id}",
    response_model=RightsCaseResponse,
)
async def update_rights_case(
    case_id: UUID,
    body: RightsCaseUpdateRequest,
    operator: PlatformOperatorDep,
    db: DBSessionDep,
) -> RightsCaseResponse:
    """Update a rights case (status transition, assignment, resolution).

    Only Platform Operators with Safety & Rights capability can update cases.
    Status transitions are validated against the case lifecycle graph.
    All changes are appended to the tamper-evident actions_taken audit trail.

    Requirements: R40.3, R40.4, R40.5, R40.8, R40.9, A2-005
    """
    _require_capability(operator, CapabilityGroup.SAFETY_AND_RIGHTS)

    service = RightsCaseService(db=db)

    try:
        case = await service.update_case(
            case_id=case_id,
            operator_id=operator.user_id,
            status=body.status.value if body.status else None,
            priority=body.priority.value if body.priority else None,
            assigned_operator=body.assigned_operator,
            resolution=body.resolution,
            legal_hold_active=body.legal_hold_active,
            action_note=body.action_note,
        )
    except CaseNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rights case not found",
            headers={"X-Error-Code": "CASE_NOT_FOUND"},
        )
    except CaseClosedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=exc.message,
            headers={"X-Error-Code": exc.code},
        ) from exc
    except InvalidCaseTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=exc.message,
            headers={"X-Error-Code": exc.code},
        ) from exc

    # Log the action
    op_service = PlatformOperatorService(db=db)
    await op_service.log_action(
        operator_user_id=operator.user_id,
        capability_used=CapabilityGroup.SAFETY_AND_RIGHTS.value,
        action_type="update_rights_case",
        target_org_id=case.target_org_id,
        action_detail={
            "case_id": str(case_id),
            "new_status": body.status.value if body.status else None,
            "new_priority": body.priority.value if body.priority else None,
        },
    )

    return RightsCaseResponse(
        id=case.id,
        case_type=case.case_type,
        status=case.status,
        priority=case.priority,
        reporter_contact=case.reporter_contact,
        target_org_id=case.target_org_id,
        target_talent_ids=case.target_talent_ids,
        target_asset_ids=case.target_asset_ids,
        reported_urls=case.reported_urls,
        evidence_refs=case.evidence_refs,
        assigned_operator=case.assigned_operator,
        actions_taken=case.actions_taken,
        resolution=case.resolution,
        appeal_state=case.appeal_state,
        legal_hold_active=case.legal_hold_active,
        created_at=case.created_at,
        updated_at=case.updated_at,
    )

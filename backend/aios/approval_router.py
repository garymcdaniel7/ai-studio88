"""AIOS Approval Router — REST endpoints for the governance approval workflow.

Endpoints:
    GET  /aios/v1/approvals           — List pending approvals for the org
    GET  /aios/v1/approvals/{id}      — Get a specific approval
    POST /aios/v1/approvals/{id}/approve — Approve a pending approval
    POST /aios/v1/approvals/{id}/reject  — Reject a pending approval
    POST /aios/v1/approvals/expire       — Expire stale approvals (admin)

All endpoints require authentication and enforce tenant isolation.

Validates: Requirements R30.1, R30.2, R30.3, R30.4, R30.5, R30.6, R30.7
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.aios.approval_service import (
    ApprovalAlreadyResolvedError,
    ApprovalExpiredError,
    ApprovalNotFoundError,
    ApprovalService,
    InsufficientRoleError,
    APPROVAL_REQUIRED_ACTIONS,
    COST_APPROVAL_THRESHOLD_USD,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/aios/v1/approvals", tags=["aios-approvals"])


# =============================================================================
# Request / Response Schemas
# =============================================================================


class ApproveRequest(BaseModel):
    """Request body for approving a pending approval."""

    approver_user_id: str = Field(..., min_length=1, description="UUID of the approver")
    org_id: str = Field(..., min_length=1, description="Organization UUID")
    approver_role: str = Field(
        default="editor",
        description="Role of the approver (editor, admin, or owner)",
    )


class RejectRequest(BaseModel):
    """Request body for rejecting a pending approval."""

    rejecter_user_id: str = Field(..., min_length=1, description="UUID of the rejecter")
    org_id: str = Field(..., min_length=1, description="Organization UUID")
    rejecter_role: str = Field(
        default="editor",
        description="Role of the rejecter (editor, admin, or owner)",
    )
    reason: str = Field(default="", description="Optional rejection reason")


class ListApprovalsParams(BaseModel):
    """Query parameters for listing approvals."""

    org_id: str = Field(..., min_length=1, description="Organization UUID")


# =============================================================================
# Endpoints
# =============================================================================


@router.get("")
def list_approvals(org_id: str) -> dict[str, Any]:
    """List pending approvals for a workspace.

    Automatically expires stale approvals (past 24h) on read.

    Query Params:
        org_id: Organization UUID (required)

    Returns:
        items: List of pending approval records
        total: Count of pending approvals
    """
    if not org_id:
        raise HTTPException(status_code=422, detail="org_id is required")

    pending = ApprovalService.list_pending(org_id)
    return {
        "items": [a.to_dict() for a in pending],
        "total": len(pending),
    }


@router.get("/config")
def get_approval_config() -> dict[str, Any]:
    """Get the current approval configuration.

    Returns the set of actions that always require approval
    and the cost threshold.
    """
    return {
        "approval_required_actions": sorted(APPROVAL_REQUIRED_ACTIONS),
        "cost_approval_threshold_usd": COST_APPROVAL_THRESHOLD_USD,
    }


@router.get("/{approval_id}")
def get_approval(approval_id: str, org_id: str) -> dict[str, Any]:
    """Get a specific approval by ID (tenant-scoped).

    Query Params:
        org_id: Organization UUID (required)

    Returns:
        The approval record, or 404 if not found for this org.
    """
    if not org_id:
        raise HTTPException(status_code=422, detail="org_id is required")

    approval = ApprovalService.get(approval_id, org_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")

    return approval.to_dict()


@router.post("/{approval_id}/approve")
def approve_approval(approval_id: str, body: ApproveRequest) -> dict[str, Any]:
    """Approve a pending approval.

    Validates:
        - Approval exists and belongs to the given org
        - Approver has editor+ role
        - Approval is still pending (not expired/resolved)

    Returns:
        The updated approval record with APPROVED status.

    Errors:
        404: Approval not found in this workspace
        403: Insufficient role
        410: Approval expired
        409: Approval already resolved
    """
    try:
        approval = ApprovalService.approve(
            approval_id=approval_id,
            approver_user_id=body.approver_user_id,
            org_id=body.org_id,
            approver_role=body.approver_role,
        )
        return {
            "status": "approved",
            "approval": approval.to_dict(),
        }
    except ApprovalNotFoundError:
        raise HTTPException(status_code=404, detail="Approval not found")
    except InsufficientRoleError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ApprovalExpiredError:
        raise HTTPException(
            status_code=410, detail="Approval expired (24h limit exceeded)"
        )
    except ApprovalAlreadyResolvedError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/{approval_id}/reject")
def reject_approval(approval_id: str, body: RejectRequest) -> dict[str, Any]:
    """Reject a pending approval.

    Validates:
        - Approval exists and belongs to the given org
        - Rejecter has editor+ role
        - Approval is still pending (not expired/resolved)

    Returns:
        The updated approval record with REJECTED status.

    Errors:
        404: Approval not found in this workspace
        403: Insufficient role
        410: Approval expired
        409: Approval already resolved
    """
    try:
        approval = ApprovalService.reject(
            approval_id=approval_id,
            rejecter_user_id=body.rejecter_user_id,
            org_id=body.org_id,
            rejecter_role=body.rejecter_role,
            reason=body.reason,
        )
        return {
            "status": "rejected",
            "approval": approval.to_dict(),
        }
    except ApprovalNotFoundError:
        raise HTTPException(status_code=404, detail="Approval not found")
    except InsufficientRoleError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ApprovalExpiredError:
        raise HTTPException(
            status_code=410, detail="Approval expired (24h limit exceeded)"
        )
    except ApprovalAlreadyResolvedError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/expire")
def expire_stale_approvals() -> dict[str, Any]:
    """Expire all stale pending approvals past their expires_at time.

    This is an administrative endpoint intended to be called
    periodically by a background task or admin action.

    Returns:
        expired_count: Number of approvals expired
        expired_ids: List of expired approval IDs
    """
    expired = ApprovalService.expire_stale()
    return {
        "expired_count": len(expired),
        "expired_ids": [a.id for a in expired],
    }

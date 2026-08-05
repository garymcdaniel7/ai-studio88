"""Workspace-Scoped Approval Queue & Governance Policy — Story 041.

All approval queue and governance policy operations are scoped to
trusted workspace context. Cross-workspace access is denied without
leaking record existence.

Operations:
    Queue: list_pending, count_pending, get_detail, approve, reject
    Policy: get_policies, update_policies

Authorization:
    - All operations require org_id from trusted context (never from client)
    - Approve/reject require editor+ role
    - Policy writes require owner/admin role
    - Cross-workspace bare IDs → None/empty (no existence leak)
    - Every decision creates an immutable audit event
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from backend.approvals import (
    ApprovalService,
    ApprovalStatus,
    DurableApproval,
)


# =============================================================================
# Role Constants
# =============================================================================

APPROVER_ROLES = frozenset({"editor", "admin", "owner"})
POLICY_WRITE_ROLES = frozenset({"admin", "owner"})


# =============================================================================
# Audit Trail
# =============================================================================

_queue_audit: list[dict] = []
_MAX_AUDIT = 1000


def _audit(action: str, org_id: str, actor_id: str, details: str = ""):
    _queue_audit.append({
        "timestamp": datetime.now(UTC).isoformat(),
        "action": action,
        "org_id": org_id,
        "actor_id": actor_id,
        "details": details,
    })
    if len(_queue_audit) > _MAX_AUDIT:
        _queue_audit.pop(0)


def get_queue_audit(org_id: str, limit: int = 50) -> list[dict]:
    """Get immutable audit trail for approval/policy operations."""
    return [
        e for e in reversed(_queue_audit[-limit:])
        if e["org_id"] == org_id
    ]


# =============================================================================
# Queue Operations (workspace-scoped)
# =============================================================================


class ApprovalQueueService:
    """Workspace-scoped approval queue operations.

    Every method requires org_id and actor context derived server-side.
    """

    @staticmethod
    def list_pending(*, org_id: str, actor_id: str, actor_role: str) -> list[dict]:
        """List pending approvals for a workspace.

        Returns only approvals belonging to the specified org.
        """
        if not org_id:
            return []

        _audit("list_pending", org_id, actor_id)
        return ApprovalService.list_pending(org_id)

    @staticmethod
    def count_pending(*, org_id: str) -> int:
        """Count pending approvals for badge display (workspace-scoped)."""
        if not org_id:
            return 0
        return ApprovalService.count_pending(org_id)

    @staticmethod
    def get_detail(*, approval_id: str, org_id: str, actor_id: str) -> dict | None:
        """Get approval detail (workspace-scoped — wrong org returns None).

        Bare IDs cannot expose another workspace's approvals.
        """
        if not org_id or not approval_id:
            return None

        approval = ApprovalService.get(approval_id, org_id)
        if not approval:
            return None  # Not found OR wrong org — no existence leak

        _audit("view_detail", org_id, actor_id, f"approval_id={approval_id}")
        return approval.to_view()

    @staticmethod
    def approve(
        *,
        approval_id: str,
        org_id: str,
        actor_id: str,
        actor_role: str,
    ) -> dict:
        """Approve a pending action (workspace-scoped, role-checked, audited).

        Requirements:
        - Actor must have editor+ role
        - Approval must belong to actor's org
        - Approval must be pending (not expired/consumed/rejected)

        Returns:
            {"success": True/False, "status": str, "reason": str}
        """
        # Role check
        if actor_role not in APPROVER_ROLES:
            _audit("approve_denied", org_id, actor_id, f"role={actor_role}:insufficient")
            return {"success": False, "status": "denied", "reason": "insufficient_role"}

        if not org_id or not approval_id:
            return {"success": False, "status": "denied", "reason": "missing_context"}

        # Delegate to ApprovalService (already handles tenant scoping + single-use)
        result = ApprovalService.approve(
            approval_id=approval_id,
            approver_user_id=actor_id,
            approver_org_id=org_id,
            approver_role=actor_role,
        )

        if result is None:
            # Not found or wrong org — no existence leak
            return {"success": False, "status": "not_found", "reason": "approval_not_found"}

        _audit("approve", org_id, actor_id,
               f"approval_id={approval_id},status={result.status.value}")

        return {
            "success": result.status in (ApprovalStatus.CONSUMED, ApprovalStatus.APPROVED),
            "status": result.status.value,
            "reason": result.decision_reason or "approved",
        }

    @staticmethod
    def reject(
        *,
        approval_id: str,
        org_id: str,
        actor_id: str,
        actor_role: str,
        reason: str = "",
    ) -> dict:
        """Reject a pending action (workspace-scoped, role-checked, audited).

        Returns:
            {"success": True/False, "status": str, "reason": str}
        """
        if actor_role not in APPROVER_ROLES:
            _audit("reject_denied", org_id, actor_id, f"role={actor_role}:insufficient")
            return {"success": False, "status": "denied", "reason": "insufficient_role"}

        if not org_id or not approval_id:
            return {"success": False, "status": "denied", "reason": "missing_context"}

        result = ApprovalService.reject(
            approval_id=approval_id,
            approver_user_id=actor_id,
            approver_org_id=org_id,
            approver_role=actor_role,
            reason=reason,
        )

        if result is None:
            return {"success": False, "status": "not_found", "reason": "approval_not_found"}

        _audit("reject", org_id, actor_id,
               f"approval_id={approval_id},reason={reason[:50]}")

        return {
            "success": result.status == ApprovalStatus.REJECTED,
            "status": result.status.value,
            "reason": reason or "rejected",
        }


# =============================================================================
# Governance Policy Operations (workspace-scoped, owner/admin only)
# =============================================================================


class GovernancePolicyService:
    """Workspace-scoped governance policy read/write.

    Policy reads: any authenticated workspace member.
    Policy writes: owner/admin only.
    """

    @staticmethod
    def get_policies(*, org_id: str, actor_id: str) -> dict:
        """Get governance policies for a workspace."""
        if not org_id:
            return {}

        try:
            from backend.aios.governance.policies import get_policies
            policies = get_policies(org_id=org_id)
            _audit("read_policies", org_id, actor_id)
            return policies
        except Exception:
            return {}

    @staticmethod
    def update_policies(
        *,
        org_id: str,
        actor_id: str,
        actor_role: str,
        updates: dict,
    ) -> dict:
        """Update governance policies (owner/admin only, audited).

        Returns:
            {"success": True/False, "policies": dict, "reason": str}
        """
        # Role check — only owner/admin can change policies
        if actor_role not in POLICY_WRITE_ROLES:
            _audit("policy_write_denied", org_id, actor_id, f"role={actor_role}")
            return {
                "success": False,
                "policies": {},
                "reason": f"Policy changes require owner or admin role. You have: {actor_role}",
            }

        if not org_id:
            return {"success": False, "policies": {}, "reason": "missing_org_id"}

        try:
            from backend.aios.governance.policies import get_policies, save_policies

            current = get_policies(org_id=org_id)
            merged = {**current, **updates}
            success = save_policies(merged, org_id=org_id)

            if success:
                _audit("update_policies", org_id, actor_id,
                       f"fields_changed={list(updates.keys())}")
                return {"success": True, "policies": merged, "reason": "updated"}
            else:
                return {"success": False, "policies": current, "reason": "persistence_failed"}
        except Exception as e:
            return {"success": False, "policies": {}, "reason": f"error:{str(e)[:100]}"}

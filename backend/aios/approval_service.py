"""AIOS Approval Service — Governance-boundary approval workflow.

Implements Requirements R30.1 through R30.7:
    - R30.1: Approval model for high-risk AI-initiated side effects
    - R30.2: Action classification (which actions always require approval)
    - R30.3: 24-hour expiry for unresolved approvals
    - R30.4: Approve/reject lifecycle with resolved_by tracking
    - R30.5: Tenant-scoped isolation (org_id on every record)
    - R30.6: Approver role enforcement (editor+ required)
    - R30.7: Audit trail for all approval decisions

Actions that ALWAYS require approval:
    - delete_permanent: Hard-delete any resource
    - spend_over_threshold: Estimated cost > $5
    - launch_workers_bulk: Launch 3+ GPU workers simultaneously
    - publish_social: Publish to external social platforms
    - clone_voice: Voice cloning operations
    - destructive_tool: Any tool classified as "destructive" by GovernanceBoundary

Lifecycle:
    create → pending → approve/reject/expire

Invariants:
    - Approvals expire after 24 hours without action
    - Expired approvals cannot be approved or rejected
    - Only users with editor+ role can approve/reject
    - Cross-tenant approval access returns None (no existence leak)
    - All state transitions are auditable
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

DEFAULT_EXPIRY_HOURS: int = 24

# Roles permitted to approve/reject
APPROVER_ROLES: frozenset[str] = frozenset({"editor", "admin", "owner"})

# Actions that ALWAYS require approval regardless of cost
APPROVAL_REQUIRED_ACTIONS: frozenset[str] = frozenset({
    "delete_permanent",
    "spend_over_threshold",
    "launch_workers_bulk",
    "publish_social",
    "clone_voice",
    "destructive_tool",
})

# Cost threshold above which approval is automatically required
COST_APPROVAL_THRESHOLD_USD: float = 5.0


# =============================================================================
# Status Enum
# =============================================================================


class PendingApprovalStatus(str, Enum):
    """Approval lifecycle states."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"

    @property
    def is_terminal(self) -> bool:
        """Whether this state is final (no further transitions)."""
        return self in (
            PendingApprovalStatus.APPROVED,
            PendingApprovalStatus.REJECTED,
            PendingApprovalStatus.EXPIRED,
        )

    @property
    def is_actionable(self) -> bool:
        """Whether this approval can still be approved/rejected."""
        return self == PendingApprovalStatus.PENDING


# =============================================================================
# Approval Record
# =============================================================================


@dataclass
class PendingApproval:
    """A pending approval record awaiting human decision."""

    id: str
    org_id: str
    requesting_user_id: str
    action_type: str
    estimated_cost_usd: float | None
    parameters: dict[str, Any]
    status: PendingApprovalStatus = PendingApprovalStatus.PENDING
    resolved_by: str | None = None
    resolved_at: str | None = None
    rejection_reason: str | None = None
    expires_at: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def is_expired(self) -> bool:
        """Check if approval has passed its expiry time."""
        if not self.expires_at:
            return False
        try:
            exp = datetime.fromisoformat(self.expires_at)
            return datetime.now(UTC) > exp
        except (ValueError, TypeError):
            return False

    def to_dict(self) -> dict[str, Any]:
        """Serialize for API response (safe — no secrets in parameters)."""
        return {
            "id": self.id,
            "org_id": self.org_id,
            "requesting_user_id": self.requesting_user_id,
            "action_type": self.action_type,
            "estimated_cost_usd": self.estimated_cost_usd,
            "parameters": self.parameters,
            "status": self.status.value,
            "resolved_by": self.resolved_by,
            "resolved_at": self.resolved_at,
            "rejection_reason": self.rejection_reason,
            "expires_at": self.expires_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "is_expired": self.is_expired,
        }


# =============================================================================
# Errors
# =============================================================================


class ApprovalNotFoundError(Exception):
    """Raised when an approval record cannot be found for the org."""


class ApprovalExpiredError(Exception):
    """Raised when attempting to act on an expired approval."""


class ApprovalAlreadyResolvedError(Exception):
    """Raised when attempting to approve/reject a non-pending approval."""


class InsufficientRoleError(Exception):
    """Raised when the user lacks editor+ role for approval actions."""


# =============================================================================
# In-memory store (production: Supabase pending_approvals table)
# =============================================================================

_approval_store: dict[str, PendingApproval] = {}
_store_lock = threading.Lock()
_audit_log: list[dict[str, Any]] = []
_MAX_AUDIT_ENTRIES: int = 2000


def _make_approval_id() -> str:
    """Generate a UUID-like approval ID."""
    return str(uuid.uuid4())


def _audit(
    action: str,
    approval_id: str,
    actor: str,
    org_id: str,
    details: str = "",
) -> None:
    """Record an audit entry for an approval action."""
    entry = {
        "timestamp": datetime.now(UTC).isoformat(),
        "action": action,
        "approval_id": approval_id,
        "actor": actor,
        "org_id": org_id,
        "details": details,
    }
    _audit_log.append(entry)
    if len(_audit_log) > _MAX_AUDIT_ENTRIES:
        _audit_log.pop(0)
    logger.info(
        "APPROVAL_AUDIT: action=%s approval_id=%s actor=%s org=%s details=%s",
        action,
        approval_id,
        actor,
        org_id[:8] + "..." if len(org_id) > 8 else org_id,
        details,
    )


# =============================================================================
# Approval Service
# =============================================================================


class ApprovalService:
    """Service for managing the governance approval workflow.

    All methods are tenant-scoped and enforce org_id isolation.
    In-memory storage for the initial implementation; production
    version will persist to the pending_approvals Supabase table.
    """

    @staticmethod
    def requires_approval(action_type: str, estimated_cost_usd: float = 0.0) -> bool:
        """Determine if an action requires approval.

        Returns True if:
            - action_type is in APPROVAL_REQUIRED_ACTIONS, OR
            - estimated_cost_usd exceeds COST_APPROVAL_THRESHOLD_USD

        Args:
            action_type: The type of action being requested.
            estimated_cost_usd: Estimated cost of the action.

        Returns:
            True if approval is required.
        """
        if action_type in APPROVAL_REQUIRED_ACTIONS:
            return True
        if estimated_cost_usd > COST_APPROVAL_THRESHOLD_USD:
            return True
        return False

    @staticmethod
    def create_approval(
        org_id: str,
        user_id: str,
        action_type: str,
        estimated_cost_usd: float | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> PendingApproval:
        """Create a new pending approval record.

        Sets expires_at to now + 24 hours.

        Args:
            org_id: Workspace that owns this approval.
            user_id: User requesting the action.
            action_type: Type of action requiring approval.
            estimated_cost_usd: Estimated cost (None if not applicable).
            parameters: Action parameters (sanitized — must not contain secrets).

        Returns:
            The created PendingApproval in PENDING status.

        Raises:
            ValueError: If org_id or user_id is empty.
        """
        if not org_id:
            raise ValueError("org_id is required")
        if not user_id:
            raise ValueError("user_id is required")
        if not action_type:
            raise ValueError("action_type is required")

        now = datetime.now(UTC)
        expires_at = (now + timedelta(hours=DEFAULT_EXPIRY_HOURS)).isoformat()

        approval = PendingApproval(
            id=_make_approval_id(),
            org_id=org_id,
            requesting_user_id=user_id,
            action_type=action_type,
            estimated_cost_usd=estimated_cost_usd,
            parameters=parameters or {},
            expires_at=expires_at,
            created_at=now.isoformat(),
            updated_at=now.isoformat(),
        )

        with _store_lock:
            _approval_store[approval.id] = approval

        _audit("create", approval.id, user_id, org_id, f"action_type={action_type}")
        return approval

    @staticmethod
    def approve(
        approval_id: str,
        approver_user_id: str,
        org_id: str,
        approver_role: str = "editor",
    ) -> PendingApproval:
        """Approve a pending approval.

        Validates:
            - Approval exists and belongs to the given org
            - Approver has editor+ role
            - Approval is still pending (not expired/resolved)
            - Approval has not expired

        Args:
            approval_id: ID of the approval to approve.
            approver_user_id: User performing the approval.
            org_id: Must match the approval's org_id.
            approver_role: Role of the approver (must be editor+).

        Returns:
            Updated PendingApproval with APPROVED status.

        Raises:
            ApprovalNotFoundError: If approval doesn't exist for this org.
            InsufficientRoleError: If approver role is insufficient.
            ApprovalExpiredError: If approval has expired.
            ApprovalAlreadyResolvedError: If approval is not pending.
        """
        with _store_lock:
            approval = _approval_store.get(approval_id)

        if not approval or approval.org_id != org_id:
            raise ApprovalNotFoundError(
                f"Approval {approval_id} not found in this workspace"
            )

        # Role check
        if approver_role.lower() not in APPROVER_ROLES:
            raise InsufficientRoleError(
                f"Role '{approver_role}' insufficient — editor+ required"
            )

        # Auto-expire if past deadline
        if approval.is_expired:
            approval.status = PendingApprovalStatus.EXPIRED
            approval.updated_at = datetime.now(UTC).isoformat()
            _audit("auto_expired", approval_id, "system", org_id)
            raise ApprovalExpiredError("Approval expired before decision")

        # Must be pending
        if not approval.status.is_actionable:
            raise ApprovalAlreadyResolvedError(
                f"Approval already resolved with status: {approval.status.value}"
            )

        # Mark approved
        now = datetime.now(UTC).isoformat()
        approval.status = PendingApprovalStatus.APPROVED
        approval.resolved_by = approver_user_id
        approval.resolved_at = now
        approval.updated_at = now

        _audit("approve", approval_id, approver_user_id, org_id)
        return approval

    @staticmethod
    def reject(
        approval_id: str,
        rejecter_user_id: str,
        org_id: str,
        rejecter_role: str = "editor",
        reason: str = "",
    ) -> PendingApproval:
        """Reject a pending approval.

        Args:
            approval_id: ID of the approval to reject.
            rejecter_user_id: User performing the rejection.
            org_id: Must match the approval's org_id.
            rejecter_role: Role of the rejecter (must be editor+).
            reason: Optional reason for rejection.

        Returns:
            Updated PendingApproval with REJECTED status.

        Raises:
            ApprovalNotFoundError: If approval doesn't exist for this org.
            InsufficientRoleError: If rejecter role is insufficient.
            ApprovalExpiredError: If approval has expired.
            ApprovalAlreadyResolvedError: If approval is not pending.
        """
        with _store_lock:
            approval = _approval_store.get(approval_id)

        if not approval or approval.org_id != org_id:
            raise ApprovalNotFoundError(
                f"Approval {approval_id} not found in this workspace"
            )

        # Role check
        if rejecter_role.lower() not in APPROVER_ROLES:
            raise InsufficientRoleError(
                f"Role '{rejecter_role}' insufficient — editor+ required"
            )

        # Auto-expire if past deadline
        if approval.is_expired:
            approval.status = PendingApprovalStatus.EXPIRED
            approval.updated_at = datetime.now(UTC).isoformat()
            _audit("auto_expired", approval_id, "system", org_id)
            raise ApprovalExpiredError("Approval expired before decision")

        # Must be pending
        if not approval.status.is_actionable:
            raise ApprovalAlreadyResolvedError(
                f"Approval already resolved with status: {approval.status.value}"
            )

        # Mark rejected
        now = datetime.now(UTC).isoformat()
        approval.status = PendingApprovalStatus.REJECTED
        approval.resolved_by = rejecter_user_id
        approval.resolved_at = now
        approval.rejection_reason = reason
        approval.updated_at = now

        _audit(
            "reject", approval_id, rejecter_user_id, org_id,
            f"reason={reason}" if reason else "",
        )
        return approval

    @staticmethod
    def expire_stale() -> list[PendingApproval]:
        """Mark all expired pending approvals as EXPIRED.

        This is intended to be called periodically (e.g., by a background task)
        to clean up approvals that were never resolved.

        Returns:
            List of approvals that were transitioned to EXPIRED.
        """
        expired: list[PendingApproval] = []
        now = datetime.now(UTC)

        with _store_lock:
            for approval in _approval_store.values():
                if approval.status != PendingApprovalStatus.PENDING:
                    continue
                if approval.is_expired:
                    approval.status = PendingApprovalStatus.EXPIRED
                    approval.updated_at = now.isoformat()
                    expired.append(approval)
                    _audit(
                        "auto_expired", approval.id, "system", approval.org_id,
                    )

        return expired

    @staticmethod
    def list_pending(org_id: str) -> list[PendingApproval]:
        """List all pending approvals for a workspace.

        Automatically expires stale approvals on read.

        Args:
            org_id: Workspace to query.

        Returns:
            List of pending approvals (not expired, not resolved).
        """
        results: list[PendingApproval] = []
        now = datetime.now(UTC)

        with _store_lock:
            for approval in _approval_store.values():
                if approval.org_id != org_id:
                    continue
                if approval.status != PendingApprovalStatus.PENDING:
                    continue
                # Auto-expire on read
                if approval.is_expired:
                    approval.status = PendingApprovalStatus.EXPIRED
                    approval.updated_at = now.isoformat()
                    continue
                results.append(approval)

        return results

    @staticmethod
    def get(approval_id: str, org_id: str) -> PendingApproval | None:
        """Get a single approval by ID (tenant-scoped).

        Returns None if not found or wrong org (no existence leak).
        """
        with _store_lock:
            approval = _approval_store.get(approval_id)

        if not approval or approval.org_id != org_id:
            return None

        # Auto-expire on read
        if (
            approval.status == PendingApprovalStatus.PENDING
            and approval.is_expired
        ):
            approval.status = PendingApprovalStatus.EXPIRED
            approval.updated_at = datetime.now(UTC).isoformat()

        return approval

    @staticmethod
    def get_audit(org_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """Get approval audit trail for a workspace."""
        entries = [
            e for e in reversed(_audit_log)
            if e.get("org_id") == org_id
        ]
        return entries[:limit]


# =============================================================================
# Store Reset (testing only)
# =============================================================================


def _reset_store() -> None:
    """Reset in-memory store and audit log. FOR TESTING ONLY."""
    with _store_lock:
        _approval_store.clear()
    _audit_log.clear()

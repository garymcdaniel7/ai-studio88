"""Durable Single-Use Approval System — Story 035.

Every approval is:
    1. Persisted before being visible to any client
    2. Bound to exactly one ActionCommand (via command_id)
    3. Argument-locked (SHA256 hash of canonical parameters)
    4. Time-limited (default 24h expiry)
    5. Single-use (status → consumed after execution, never re-usable)
    6. Authorized (approver must have editor+ role in the command's org)
    7. Auditable (approver_user_id, timestamps, decision recorded)

Flow:
    create_approval(command) → [persisted] → visible to approvers
    approve(id, approver) → verify auth + expiry + binding → execute command → consumed
    reject(id, approver, reason) → final, no execution

Security invariants:
    - No approval is shown unless persisted (create raises on persistence failure)
    - Changed arguments invalidate the approval (argument_hash mismatch)
    - Expired approvals cannot execute
    - Consumed/rejected/expired approvals cannot be re-approved
    - Cross-tenant approval IDs return None (no existence leak)
    - Duplicate approve clicks return the existing result (idempotent)
"""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any


# =============================================================================
# Types
# =============================================================================


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    CONSUMED = "consumed"  # Approved AND executed (terminal, single-use)
    REJECTED = "rejected"
    EXPIRED = "expired"
    INVALIDATED = "invalidated"  # Arguments changed after creation

    @property
    def is_terminal(self) -> bool:
        return self in (
            ApprovalStatus.CONSUMED,
            ApprovalStatus.REJECTED,
            ApprovalStatus.EXPIRED,
            ApprovalStatus.INVALIDATED,
        )

    @property
    def is_actionable(self) -> bool:
        return self == ApprovalStatus.PENDING


DEFAULT_EXPIRY_HOURS = 24
APPROVER_ROLES = {"editor", "admin", "owner"}


# =============================================================================
# Approval Record
# =============================================================================


@dataclass
class DurableApproval:
    """A durable, single-use approval bound to one exact action."""

    id: str
    command_id: str  # Bound ActionCommand
    org_id: str
    requesting_user_id: str
    session_id: str
    tool: str
    argument_hash: str  # SHA256 of canonical JSON parameters
    estimated_cost_usd: float
    status: ApprovalStatus = ApprovalStatus.PENDING
    # Expiry
    expires_at: str = ""
    # Decision
    approver_user_id: str | None = None
    decision_reason: str = ""
    # Execution linkage
    execution_command_id: str | None = None  # The command that was dispatched
    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    decided_at: str | None = None
    executed_at: str | None = None
    # Metadata
    display_summary: str = ""  # Human-readable action description
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_view(self) -> dict:
        """Client-safe view (no raw parameters, no secrets)."""
        return {
            "id": self.id,
            "command_id": self.command_id,
            "tool": self.tool,
            "display_summary": self.display_summary,
            "estimated_cost_usd": self.estimated_cost_usd,
            "status": self.status.value,
            "is_expired": self._is_expired(),
            "expires_at": self.expires_at,
            "approver_user_id": self.approver_user_id,
            "decision_reason": self.decision_reason,
            "created_at": self.created_at,
            "decided_at": self.decided_at,
            "is_terminal": self.status.is_terminal,
        }

    def _is_expired(self) -> bool:
        if not self.expires_at:
            return False
        try:
            exp = datetime.fromisoformat(self.expires_at)
            return datetime.now(UTC) > exp
        except (ValueError, TypeError):
            return False


# =============================================================================
# Argument Hashing
# =============================================================================


def compute_argument_hash(parameters: dict) -> str:
    """Compute SHA256 of canonicalized parameters.

    Used to detect if arguments were mutated between creation and execution.
    """
    canonical = json.dumps(parameters, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:32]


# =============================================================================
# Approval Store (in-memory, production: Supabase)
# =============================================================================

_approval_store: dict[str, DurableApproval] = {}
_store_lock = threading.Lock()
_approval_audit: list[dict] = []


def _make_approval_id() -> str:
    return f"apr-{secrets.token_hex(10)}"


def _audit(action: str, approval_id: str, actor: str, org_id: str, details: str = ""):
    _approval_audit.append({
        "timestamp": datetime.now(UTC).isoformat(),
        "action": action,
        "approval_id": approval_id,
        "actor": actor,
        "org_id": org_id,
        "details": details,
    })
    if len(_approval_audit) > 1000:
        _approval_audit.pop(0)


# =============================================================================
# Approval Service
# =============================================================================


class PersistenceError(Exception):
    """Raised when approval cannot be persisted (blocks display)."""
    pass


class ApprovalService:
    """Durable single-use approval management."""

    @staticmethod
    def create(
        *,
        command_id: str,
        org_id: str,
        requesting_user_id: str,
        session_id: str,
        tool: str,
        parameters: dict,
        estimated_cost_usd: float = 0.0,
        display_summary: str = "",
        expiry_hours: int = DEFAULT_EXPIRY_HOURS,
    ) -> DurableApproval:
        """Create a durable approval.

        RAISES PersistenceError if storage fails — the approval MUST NOT be
        shown to users unless this succeeds.
        """
        if not org_id:
            raise ValueError("org_id required")
        if not command_id:
            raise ValueError("command_id required")

        argument_hash = compute_argument_hash(parameters)
        expires_at = (datetime.now(UTC) + timedelta(hours=expiry_hours)).isoformat()

        approval = DurableApproval(
            id=_make_approval_id(),
            command_id=command_id,
            org_id=org_id,
            requesting_user_id=requesting_user_id,
            session_id=session_id,
            tool=tool,
            argument_hash=argument_hash,
            estimated_cost_usd=estimated_cost_usd,
            expires_at=expires_at,
            display_summary=display_summary or f"{tool} (${estimated_cost_usd:.2f})",
        )

        # Persist — MUST succeed or raise
        with _store_lock:
            try:
                _approval_store[approval.id] = approval
            except Exception as e:
                raise PersistenceError(f"Failed to persist approval: {e}")

        _audit("create", approval.id, requesting_user_id, org_id, f"tool={tool}")
        return approval

    @staticmethod
    def approve(
        *,
        approval_id: str,
        approver_user_id: str,
        approver_org_id: str,
        approver_role: str,
        current_parameters: dict | None = None,
    ) -> DurableApproval | None:
        """Approve a pending approval and trigger execution.

        Checks:
        1. Approval exists and belongs to approver's org
        2. Approver has sufficient role (editor+)
        3. Approval is still pending (not expired/consumed/rejected)
        4. Arguments haven't changed (if current_parameters provided)
        5. Not expired

        On success: transitions to CONSUMED via ActionCommandService.
        Idempotent: duplicate approve on already-consumed returns existing.
        """
        with _store_lock:
            approval = _approval_store.get(approval_id)

        if not approval:
            return None

        # Tenant check — cross-org returns None (no existence leak)
        if approval.org_id != approver_org_id:
            return None

        # Role check
        if approver_role.lower() not in APPROVER_ROLES:
            _audit("approve_denied", approval_id, approver_user_id, approver_org_id,
                   f"insufficient_role:{approver_role}")
            return None

        # Idempotent: already consumed = return as-is (duplicate click)
        if approval.status == ApprovalStatus.CONSUMED:
            return approval

        # Terminal check — can't approve rejected/invalidated
        if approval.status.is_terminal:
            return approval  # Return current state, don't re-process

        # Expiry check
        if approval._is_expired():
            approval.status = ApprovalStatus.EXPIRED
            _audit("expired", approval_id, "system", approval.org_id)
            return approval

        # Must be pending
        if not approval.status.is_actionable:
            return approval

        # Argument binding check
        if current_parameters is not None:
            current_hash = compute_argument_hash(current_parameters)
            if current_hash != approval.argument_hash:
                approval.status = ApprovalStatus.INVALIDATED
                _audit("invalidated", approval_id, approver_user_id, approver_org_id,
                       "argument_hash_mismatch")
                return approval

        # All checks pass — approve and execute
        approval.status = ApprovalStatus.APPROVED
        approval.approver_user_id = approver_user_id
        approval.decided_at = datetime.now(UTC).isoformat()

        # Execute via ActionCommandService (at-most-once via idempotency)
        try:
            from backend.action_commands import ActionCommandService

            cmd = ActionCommandService.approve(approval.command_id)
            if cmd:
                approval.execution_command_id = cmd.id
                approval.executed_at = datetime.now(UTC).isoformat()
                approval.status = ApprovalStatus.CONSUMED
            else:
                # Command not found or not in approval_required state
                approval.status = ApprovalStatus.INVALIDATED
                approval.decision_reason = "bound_command_not_found_or_already_processed"
        except Exception as e:
            approval.decision_reason = f"execution_error:{str(e)[:100]}"
            # Don't mark consumed — execution failed
            approval.status = ApprovalStatus.APPROVED  # Stays approved but not consumed

        _audit("approve", approval_id, approver_user_id, approver_org_id,
               f"status={approval.status.value}")
        return approval

    @staticmethod
    def reject(
        *,
        approval_id: str,
        approver_user_id: str,
        approver_org_id: str,
        approver_role: str,
        reason: str = "",
    ) -> DurableApproval | None:
        """Reject a pending approval. Terminal — cannot be undone."""
        with _store_lock:
            approval = _approval_store.get(approval_id)

        if not approval:
            return None

        if approval.org_id != approver_org_id:
            return None

        if approver_role.lower() not in APPROVER_ROLES:
            return None

        if approval.status.is_terminal:
            return approval

        if not approval.status.is_actionable:
            return approval

        approval.status = ApprovalStatus.REJECTED
        approval.approver_user_id = approver_user_id
        approval.decision_reason = reason or "Rejected"
        approval.decided_at = datetime.now(UTC).isoformat()

        # Also reject the bound command
        try:
            from backend.action_commands import ActionCommandService
            ActionCommandService.reject(approval.command_id, reason)
        except Exception:
            pass

        _audit("reject", approval_id, approver_user_id, approver_org_id, reason)
        return approval

    @staticmethod
    def get(approval_id: str, org_id: str) -> DurableApproval | None:
        """Get an approval (tenant-scoped — wrong org returns None)."""
        approval = _approval_store.get(approval_id)
        if not approval or approval.org_id != org_id:
            return None
        # Auto-expire on read
        if approval.status == ApprovalStatus.PENDING and approval._is_expired():
            approval.status = ApprovalStatus.EXPIRED
        return approval

    @staticmethod
    def list_pending(org_id: str) -> list[dict]:
        """List pending approvals for a workspace (auto-expires stale ones)."""
        results = []
        now = datetime.now(UTC)
        for approval in _approval_store.values():
            if approval.org_id != org_id:
                continue
            if approval.status == ApprovalStatus.PENDING:
                if approval._is_expired():
                    approval.status = ApprovalStatus.EXPIRED
                else:
                    results.append(approval.to_view())
        return results

    @staticmethod
    def count_pending(org_id: str) -> int:
        """Count pending approvals for badge display."""
        return len(ApprovalService.list_pending(org_id))

    @staticmethod
    def get_audit(org_id: str, limit: int = 50) -> list[dict]:
        """Get approval audit trail for a workspace."""
        return [
            e for e in reversed(_approval_audit[-limit:])
            if e.get("org_id") == org_id
        ]

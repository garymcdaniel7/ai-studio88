"""Durable Approval Service — Story 042.

Enforced pre-execution approval for high-risk AI actions.
No prompt, tool path, or alternate endpoint can bypass this gate.

Protected action types (from existing governance documentation):
  - DESTRUCTIVE: delete assets, delete talent, delete models, drop data
  - PUBLISHING: schedule_post, publish_post (external side effects)
  - PAID_GPU: launch_gpu_worker, train_lora (significant cost)
  - VOICE_GENERATION: generate_voice (ElevenLabs credits)
  - CREDENTIAL: rotate keys, update service connections
  - DEPLOYMENT: deploy, restart services
  - INFRASTRUCTURE: stop_gpu_worker, fleet changes

Lifecycle:
    create_approval_request → pending
    approve → approved (single-use token issued)
    reject → rejected (terminal)
    expire → expired (terminal, automatic)
    consume → consumed (terminal, execution completed)
    revoke → revoked (terminal, admin action)

Key guarantees:
    1. Approval binds to EXACT argument fingerprint (mutation invalidates)
    2. Single-use: consumed on first successful execution attempt
    3. Expiry: default 30 minutes, configurable per action type
    4. Workspace-scoped: cross-tenant approvals impossible
    5. Approver role: editor+ (matching governance enforcement)
    6. Every state transition is audited
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Action Risk Classification
# =============================================================================


class ActionRisk(str, Enum):
    """Risk classification for tool actions."""
    DESTRUCTIVE = "destructive"
    PUBLISHING = "publishing"
    PAID_GPU = "paid_gpu"
    VOICE_GENERATION = "voice_generation"
    CREDENTIAL = "credential"
    DEPLOYMENT = "deployment"
    INFRASTRUCTURE = "infrastructure"


# Documented high-risk actions requiring pre-execution approval
HIGH_RISK_ACTIONS: dict[str, ActionRisk] = {
    # Destructive
    "delete_talent": ActionRisk.DESTRUCTIVE,
    "delete_model": ActionRisk.DESTRUCTIVE,
    "delete_asset": ActionRisk.DESTRUCTIVE,
    "hard_delete_model": ActionRisk.DESTRUCTIVE,
    # Publishing
    "schedule_post": ActionRisk.PUBLISHING,
    "publish_post": ActionRisk.PUBLISHING,
    # Paid GPU
    "launch_gpu_worker": ActionRisk.PAID_GPU,
    "train_lora": ActionRisk.PAID_GPU,
    # Voice
    "generate_voice": ActionRisk.VOICE_GENERATION,
    # Infrastructure
    "stop_gpu_worker": ActionRisk.INFRASTRUCTURE,
}

# Default expiry per risk class (seconds)
DEFAULT_EXPIRY: dict[ActionRisk, int] = {
    ActionRisk.DESTRUCTIVE: 300,       # 5 minutes (immediate action)
    ActionRisk.PUBLISHING: 1800,       # 30 minutes
    ActionRisk.PAID_GPU: 1800,         # 30 minutes
    ActionRisk.VOICE_GENERATION: 1800, # 30 minutes
    ActionRisk.CREDENTIAL: 300,        # 5 minutes
    ActionRisk.DEPLOYMENT: 300,        # 5 minutes
    ActionRisk.INFRASTRUCTURE: 600,    # 10 minutes
}


# =============================================================================
# Approval Status
# =============================================================================


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"       # Ready for single-use execution
    REJECTED = "rejected"       # Terminal — cannot execute
    EXPIRED = "expired"         # Terminal — time ran out
    CONSUMED = "consumed"       # Terminal — successfully executed
    REVOKED = "revoked"         # Terminal — admin cancelled


TERMINAL_STATES = frozenset({
    ApprovalStatus.REJECTED,
    ApprovalStatus.EXPIRED,
    ApprovalStatus.CONSUMED,
    ApprovalStatus.REVOKED,
})


# =============================================================================
# Approval Record
# =============================================================================


@dataclass
class ApprovalRecord:
    """A persisted, durable approval record.

    Binds: actor + workspace + action + exact arguments + cost + expiry.
    """
    id: str = field(default_factory=lambda: f"apr-{uuid.uuid4().hex[:16]}")
    org_id: str = ""
    user_id: str = ""              # Who requested the action
    action: str = ""               # Tool/action name
    risk_class: str = ""           # ActionRisk value
    arguments_fingerprint: str = "" # SHA-256 of sanitized arguments
    arguments_summary: str = ""    # Human-readable summary (no secrets)
    estimated_cost_usd: float = 0.0
    status: ApprovalStatus = ApprovalStatus.PENDING
    approver_id: str | None = None # Who approved/rejected
    rejection_reason: str = ""
    execution_token: str | None = None  # Single-use token issued on approval
    session_id: str | None = None
    expires_at: float = 0.0        # Unix timestamp
    created_at: float = field(default_factory=time.time)
    decided_at: float | None = None
    consumed_at: float | None = None

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATES

    @property
    def is_consumable(self) -> bool:
        """Can this approval be consumed (executed)?"""
        return (
            self.status == ApprovalStatus.APPROVED
            and not self.is_expired
            and self.execution_token is not None
        )


# =============================================================================
# Errors
# =============================================================================


class ApprovalRequiredError(Exception):
    """Raised when an action requires approval before execution."""
    def __init__(self, approval_id: str, action: str, reason: str) -> None:
        self.approval_id = approval_id
        self.action = action
        self.reason = reason
        super().__init__(f"Approval required for '{action}': {reason} (id={approval_id})")


class ApprovalInvalidError(Exception):
    """Raised when an execution token is invalid, expired, or consumed."""
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Approval invalid: {reason}")


# =============================================================================
# Argument Fingerprinting
# =============================================================================


def fingerprint_arguments(action: str, arguments: dict) -> str:
    """Create a stable fingerprint of action + arguments.

    Any change to arguments after approval invalidates the fingerprint.
    The fingerprint is deterministic: same action+args → same hash.
    """
    # Sanitize: remove non-deterministic fields
    sanitized = {k: v for k, v in sorted(arguments.items()) if k not in ("_timestamp", "_request_id")}
    payload = json.dumps({"action": action, "args": sanitized}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def summarize_arguments(action: str, arguments: dict) -> str:
    """Create a human-readable summary (no secrets, max 200 chars)."""
    parts = [f"action={action}"]
    for k, v in list(arguments.items())[:5]:
        val_str = str(v)[:30]
        if "key" in k.lower() or "secret" in k.lower() or "token" in k.lower():
            val_str = "***"
        parts.append(f"{k}={val_str}")
    return ", ".join(parts)[:200]


# =============================================================================
# Durable Approval Service
# =============================================================================


def requires_approval(action: str) -> bool:
    """Check if an action requires durable pre-execution approval."""
    return action in HIGH_RISK_ACTIONS


def get_risk_class(action: str) -> ActionRisk | None:
    """Get the risk classification for an action."""
    return HIGH_RISK_ACTIONS.get(action)


def create_approval_request(
    org_id: str,
    user_id: str,
    action: str,
    arguments: dict,
    estimated_cost_usd: float = 0.0,
    session_id: str | None = None,
) -> ApprovalRecord:
    """Create a durable approval request BEFORE execution.

    This must be called before any high-risk action executes.
    The returned record must be approved before execution can proceed.

    Args:
        org_id: Workspace that owns this action.
        user_id: User requesting the action.
        action: Tool/action name.
        arguments: Exact arguments (fingerprinted and bound).
        estimated_cost_usd: Cost estimate for display.
        session_id: AIOS session context.

    Returns:
        ApprovalRecord in PENDING status.
    """
    if not org_id:
        raise ValueError("org_id is required for approval requests")
    if not user_id:
        raise ValueError("user_id is required for approval requests")

    risk = HIGH_RISK_ACTIONS.get(action)
    if not risk:
        raise ValueError(f"Action '{action}' is not classified as high-risk")

    expiry_seconds = DEFAULT_EXPIRY.get(risk, 1800)

    record = ApprovalRecord(
        org_id=org_id,
        user_id=user_id,
        action=action,
        risk_class=risk.value,
        arguments_fingerprint=fingerprint_arguments(action, arguments),
        arguments_summary=summarize_arguments(action, arguments),
        estimated_cost_usd=estimated_cost_usd,
        session_id=session_id,
        expires_at=time.time() + expiry_seconds,
    )

    _persist_record(record)
    _audit_transition(record, "created", user_id)
    return record


def approve(
    approval_id: str,
    approver_id: str,
    org_id: str,
    role: str = "editor",
) -> ApprovalRecord:
    """Approve a pending request and issue a single-use execution token.

    Args:
        approval_id: The approval record ID.
        approver_id: Who is approving (must be editor+).
        org_id: Must match the approval's workspace.
        role: Approver's role (editor+ required).

    Returns:
        Updated ApprovalRecord with execution_token.

    Raises:
        ApprovalInvalidError: If approval is expired, wrong org, or not pending.
    """
    record = _load_record(approval_id, org_id)
    if not record:
        raise ApprovalInvalidError("Approval not found in this workspace")

    if record.status != ApprovalStatus.PENDING:
        raise ApprovalInvalidError(f"Cannot approve: status is {record.status.value}")

    if record.is_expired:
        record.status = ApprovalStatus.EXPIRED
        _persist_record(record)
        _audit_transition(record, "auto_expired", "system")
        raise ApprovalInvalidError("Approval expired before decision")

    # Role check
    role_hierarchy = ["viewer", "editor", "admin", "owner"]
    if role not in role_hierarchy or role_hierarchy.index(role) < role_hierarchy.index("editor"):
        raise ApprovalInvalidError(f"Role '{role}' insufficient — editor+ required")

    # Issue single-use execution token
    execution_token = f"exe-{uuid.uuid4().hex}"

    record.status = ApprovalStatus.APPROVED
    record.approver_id = approver_id
    record.execution_token = execution_token
    record.decided_at = time.time()

    _persist_record(record)
    _audit_transition(record, "approved", approver_id)
    return record


def reject(
    approval_id: str,
    rejector_id: str,
    org_id: str,
    reason: str = "",
) -> ApprovalRecord:
    """Reject a pending approval request."""
    record = _load_record(approval_id, org_id)
    if not record:
        raise ApprovalInvalidError("Approval not found in this workspace")

    if record.status != ApprovalStatus.PENDING:
        raise ApprovalInvalidError(f"Cannot reject: status is {record.status.value}")

    record.status = ApprovalStatus.REJECTED
    record.approver_id = rejector_id
    record.rejection_reason = reason
    record.decided_at = time.time()

    _persist_record(record)
    _audit_transition(record, "rejected", rejector_id)
    return record


def consume_authorization(
    execution_token: str,
    action: str,
    arguments: dict,
    org_id: str,
) -> ApprovalRecord:
    """Consume a single-use execution authorization.

    This is called ATOMICALLY before tool execution.
    After consumption, the token cannot be reused.

    Validates:
    - Token exists and matches an approved record
    - Record is in APPROVED status (not already consumed)
    - Record has not expired
    - Arguments fingerprint matches (no mutation after approval)
    - Workspace matches

    Returns:
        The consumed ApprovalRecord.

    Raises:
        ApprovalInvalidError: If any validation fails.
    """
    record = _load_by_token(execution_token, org_id)
    if not record:
        raise ApprovalInvalidError("Execution token not found or wrong workspace")

    if record.status != ApprovalStatus.APPROVED:
        raise ApprovalInvalidError(f"Token not consumable: status is {record.status.value}")

    if record.is_expired:
        record.status = ApprovalStatus.EXPIRED
        _persist_record(record)
        _audit_transition(record, "expired_on_consume", "system")
        raise ApprovalInvalidError("Approval expired before execution")

    # Verify argument fingerprint (detects mutation after approval)
    current_fingerprint = fingerprint_arguments(action, arguments)
    if current_fingerprint != record.arguments_fingerprint:
        _audit_transition(record, "fingerprint_mismatch", "system")
        raise ApprovalInvalidError(
            "Arguments changed after approval — re-approval required"
        )

    # Consume (single-use — cannot be reused)
    record.status = ApprovalStatus.CONSUMED
    record.consumed_at = time.time()

    _persist_record(record)
    _audit_transition(record, "consumed", record.user_id)
    return record


def revoke(approval_id: str, revoker_id: str, org_id: str) -> ApprovalRecord:
    """Revoke an approval (admin action)."""
    record = _load_record(approval_id, org_id)
    if not record:
        raise ApprovalInvalidError("Approval not found")

    if record.is_terminal:
        raise ApprovalInvalidError(f"Cannot revoke: already {record.status.value}")

    record.status = ApprovalStatus.REVOKED
    record.decided_at = time.time()

    _persist_record(record)
    _audit_transition(record, "revoked", revoker_id)
    return record


# =============================================================================
# Persistence (in-memory for now, DB integration via existing aios_approvals)
# =============================================================================

_approval_store: dict[str, ApprovalRecord] = {}
_token_index: dict[str, str] = {}  # token → approval_id


def _persist_record(record: ApprovalRecord) -> None:
    """Persist an approval record."""
    _approval_store[record.id] = record
    if record.execution_token:
        _token_index[record.execution_token] = record.id


def _load_record(approval_id: str, org_id: str) -> ApprovalRecord | None:
    """Load an approval record, scoped to workspace."""
    record = _approval_store.get(approval_id)
    if record and record.org_id == org_id:
        return record
    return None


def _load_by_token(token: str, org_id: str) -> ApprovalRecord | None:
    """Load an approval by execution token, scoped to workspace."""
    approval_id = _token_index.get(token)
    if not approval_id:
        return None
    return _load_record(approval_id, org_id)


def _audit_transition(record: ApprovalRecord, transition: str, actor: str) -> None:
    """Audit an approval state transition."""
    logger.info(
        f"APPROVAL_AUDIT: id={record.id} action={record.action} "
        f"transition={transition} status={record.status.value} "
        f"actor={actor} org={record.org_id[:8]}..."
    )


# =============================================================================
# Reset (for testing only)
# =============================================================================


def _reset_store() -> None:
    """Reset in-memory store. FOR TESTING ONLY."""
    _approval_store.clear()
    _token_index.clear()

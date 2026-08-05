"""Fail-Safe Governance Decision Contract — Story 025.

This module is the SINGLE authoritative entry point for governance decisions.
Every action that has side effects MUST pass through evaluate_action() before
execution. The decision is explicit, auditable, and fail-closed for high-risk.

Design principles:
    1. High-risk actions FAIL CLOSED on any dependency error
    2. Read-only actions may continue in DEGRADED mode with disclosure
    3. Every decision has an explicit state (never implicit allow)
    4. Audit persistence failure BLOCKS high-risk execution
    5. No exception path converts a verification failure into allowed=true

Risk Classes:
    READ_ONLY      — chat, listing, status checks (degraded-mode allowed)
    LOW_RISK       — reversible mutations with no cost (edit name, update settings)
    PAID           — triggers GPU spend or API cost
    DESTRUCTIVE    — deletes data, revokes credentials
    PUBLISHING     — external side effects (social posts, webhooks)
    CREDENTIAL     — creates/rotates/accesses secrets
    MODEL_ACTIVATE — promotes a model to production use
    INFRASTRUCTURE — launches/stops GPU instances, modifies workers

Decision States:
    ALLOWED              — all checks passed, action may proceed
    DENIED               — policy explicitly forbids this action
    APPROVAL_REQUIRED    — action needs human review before execution
    GOVERNANCE_UNAVAILABLE — a required check failed/timed out (fail-closed)
    BUDGET_EXCEEDED      — cost would exceed configured limits
    AUDIT_FAILURE        — audit persistence failed (blocks high-risk only)
    DEGRADED_ALLOWED     — read-only permitted but governance is impaired
"""

from __future__ import annotations

import uuid as _uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


# =============================================================================
# Risk Classification
# =============================================================================


class RiskClass(str, Enum):
    """Operation risk classification."""

    READ_ONLY = "read_only"
    LOW_RISK = "low_risk"
    PAID = "paid"
    DESTRUCTIVE = "destructive"
    PUBLISHING = "publishing"
    CREDENTIAL = "credential"
    MODEL_ACTIVATE = "model_activate"
    INFRASTRUCTURE = "infrastructure"

    @property
    def requires_fail_closed(self) -> bool:
        """Whether this risk class must deny on governance failure."""
        return self in (
            RiskClass.PAID,
            RiskClass.DESTRUCTIVE,
            RiskClass.PUBLISHING,
            RiskClass.CREDENTIAL,
            RiskClass.MODEL_ACTIVATE,
            RiskClass.INFRASTRUCTURE,
        )

    @property
    def allows_degraded(self) -> bool:
        """Whether this risk class can proceed in degraded mode."""
        return self in (RiskClass.READ_ONLY, RiskClass.LOW_RISK)


class DecisionState(str, Enum):
    """Explicit governance decision outcome."""

    ALLOWED = "allowed"
    DENIED = "denied"
    APPROVAL_REQUIRED = "approval_required"
    GOVERNANCE_UNAVAILABLE = "governance_unavailable"
    BUDGET_EXCEEDED = "budget_exceeded"
    AUDIT_FAILURE = "audit_failure"
    DEGRADED_ALLOWED = "degraded_allowed"

    @property
    def permits_execution(self) -> bool:
        """Whether this decision allows the action to proceed."""
        return self in (DecisionState.ALLOWED, DecisionState.DEGRADED_ALLOWED)


# =============================================================================
# Governance Decision Record
# =============================================================================


@dataclass(frozen=True)
class GovernanceDecision:
    """Immutable record of a governance decision.

    Every action evaluation produces one of these. It is:
    - Explicit (never ambiguous)
    - Auditable (has correlation ID, actor, timestamp)
    - Non-leaking (no secrets in reason or metadata)
    """

    state: DecisionState
    risk_class: RiskClass
    reason: str
    action: str
    actor_user_id: str
    org_id: str
    request_id: str = field(default_factory=lambda: f"gov-{_uuid.uuid4().hex[:12]}")
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    estimated_cost_usd: float = 0.0
    failed_dependencies: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        """Whether execution may proceed."""
        return self.state.permits_execution

    @property
    def is_degraded(self) -> bool:
        """Whether this is a degraded-mode allowance."""
        return self.state == DecisionState.DEGRADED_ALLOWED

    def to_dict(self) -> dict:
        """Serialize for API response (safe — no secrets)."""
        return {
            "state": self.state.value,
            "allowed": self.allowed,
            "risk_class": self.risk_class.value,
            "reason": self.reason,
            "action": self.action,
            "request_id": self.request_id,
            "timestamp": self.timestamp,
            "estimated_cost_usd": self.estimated_cost_usd,
            "is_degraded": self.is_degraded,
            "failed_dependencies": self.failed_dependencies,
        }


# =============================================================================
# Audit Persistence
# =============================================================================

_governance_audit: list[dict] = []
_MAX_AUDIT = 2000


class AuditPersistenceError(Exception):
    """Raised when audit cannot be persisted for a high-risk action."""
    pass


def _persist_audit(decision: GovernanceDecision) -> bool:
    """Persist a governance decision to the audit trail.

    Returns True on success. For high-risk actions, failure to persist
    MUST block execution (caller checks this).
    """
    entry = {
        "request_id": decision.request_id,
        "timestamp": decision.timestamp,
        "state": decision.state.value,
        "risk_class": decision.risk_class.value,
        "action": decision.action,
        "actor_user_id": decision.actor_user_id,
        "org_id": decision.org_id,
        "reason": decision.reason,
        "estimated_cost_usd": decision.estimated_cost_usd,
        "failed_dependencies": decision.failed_dependencies,
        "allowed": decision.allowed,
    }

    try:
        _governance_audit.append(entry)
        if len(_governance_audit) > _MAX_AUDIT:
            _governance_audit.pop(0)
        return True
    except Exception:
        return False


def get_governance_audit(org_id: str | None = None, limit: int = 50) -> list[dict]:
    """Get recent governance decisions for audit review."""
    entries = _governance_audit if not org_id else [
        e for e in _governance_audit if e.get("org_id") == org_id
    ]
    return list(reversed(entries[-limit:]))


# =============================================================================
# Dependency Check Results
# =============================================================================


@dataclass
class DependencyResult:
    """Result of checking a governance dependency."""

    name: str
    available: bool
    error: str = ""


def _check_policy_availability(org_id: str | None) -> DependencyResult:
    """Check if policy service is reachable."""
    try:
        from backend.aios.governance.policies import get_policies
        policies = get_policies(org_id=org_id)
        if policies:
            return DependencyResult(name="policy", available=True)
        return DependencyResult(name="policy", available=False, error="empty_response")
    except Exception as e:
        return DependencyResult(name="policy", available=False, error=str(e)[:100])


def _check_budget_availability(org_id: str | None) -> DependencyResult:
    """Check if budget service is reachable."""
    try:
        from backend.infrastructure.cost_intelligence import get_cost_tracker
        tracker = get_cost_tracker()
        _ = tracker.get_today_total()
        return DependencyResult(name="budget", available=True)
    except Exception as e:
        return DependencyResult(name="budget", available=False, error=str(e)[:100])


def _check_audit_availability() -> DependencyResult:
    """Check if audit persistence is available."""
    # In-memory audit is always available; production would check DB
    return DependencyResult(name="audit", available=True)


# =============================================================================
# Core Evaluation Function
# =============================================================================


def evaluate_action(
    *,
    action: str,
    risk_class: RiskClass,
    actor_user_id: str,
    org_id: str,
    estimated_cost_usd: float = 0.0,
    metadata: dict[str, Any] | None = None,
) -> GovernanceDecision:
    """Evaluate whether an action may proceed.

    This is the SINGLE entry point for all governance decisions.
    It checks dependencies, applies risk-appropriate rules, persists
    the decision for audit, and returns an explicit outcome.

    Args:
        action: What is being attempted (e.g., "launch_gpu", "delete_asset").
        risk_class: Classification of the operation.
        actor_user_id: Who is attempting the action.
        org_id: Which workspace.
        estimated_cost_usd: Expected cost (for budget checks).
        metadata: Additional context (never includes secrets).

    Returns:
        GovernanceDecision — always explicit, never ambiguous.
    """
    failed_deps: list[str] = []

    # -------------------------------------------------------------------------
    # Step 1: Check required dependencies based on risk class
    # -------------------------------------------------------------------------

    if risk_class.requires_fail_closed:
        # High-risk: ALL dependencies must be available
        policy_check = _check_policy_availability(org_id)
        if not policy_check.available:
            failed_deps.append(f"policy:{policy_check.error}")

        if estimated_cost_usd > 0:
            budget_check = _check_budget_availability(org_id)
            if not budget_check.available:
                failed_deps.append(f"budget:{budget_check.error}")

        audit_check = _check_audit_availability()
        if not audit_check.available:
            failed_deps.append(f"audit:{audit_check.error}")

        # If ANY required dependency is unavailable → fail closed
        if failed_deps:
            decision = GovernanceDecision(
                state=DecisionState.GOVERNANCE_UNAVAILABLE,
                risk_class=risk_class,
                reason=f"Required governance dependency unavailable: {', '.join(failed_deps)}",
                action=action,
                actor_user_id=actor_user_id,
                org_id=org_id,
                estimated_cost_usd=estimated_cost_usd,
                failed_dependencies=failed_deps,
                metadata=metadata or {},
            )
            _persist_audit(decision)  # Best-effort for unavailable decisions
            return decision

    # -------------------------------------------------------------------------
    # Step 2: Load policies and evaluate
    # -------------------------------------------------------------------------

    try:
        from backend.aios.governance.policies import get_policies
        policies = get_policies(org_id=org_id)
    except Exception:
        policies = None

    if policies is None and risk_class.requires_fail_closed:
        decision = GovernanceDecision(
            state=DecisionState.GOVERNANCE_UNAVAILABLE,
            risk_class=risk_class,
            reason="Policy evaluation failed — cannot determine authorization",
            action=action,
            actor_user_id=actor_user_id,
            org_id=org_id,
            estimated_cost_usd=estimated_cost_usd,
            failed_dependencies=["policy:load_failed"],
            metadata=metadata or {},
        )
        _persist_audit(decision)
        return decision

    # -------------------------------------------------------------------------
    # Step 3: Budget check for paid actions
    # -------------------------------------------------------------------------

    if risk_class == RiskClass.PAID and estimated_cost_usd > 0 and policies:
        max_auto = float(policies.get("max_auto_spend_usd", 5.0))
        daily_budget = float(policies.get("budget_daily_usd", 20.0))

        # Check single-action cost limit
        if estimated_cost_usd > max_auto:
            decision = GovernanceDecision(
                state=DecisionState.APPROVAL_REQUIRED,
                risk_class=risk_class,
                reason=f"Cost ${estimated_cost_usd:.2f} exceeds auto-approve limit ${max_auto:.2f}",
                action=action,
                actor_user_id=actor_user_id,
                org_id=org_id,
                estimated_cost_usd=estimated_cost_usd,
                metadata=metadata or {},
            )
            _persist_audit(decision)
            return decision

        # Check daily budget (fail-closed on check failure)
        try:
            from backend.infrastructure.cost_intelligence import get_cost_tracker
            tracker = get_cost_tracker()
            today_spend = tracker.get_today_total()
            if today_spend + estimated_cost_usd > daily_budget:
                decision = GovernanceDecision(
                    state=DecisionState.BUDGET_EXCEEDED,
                    risk_class=risk_class,
                    reason=f"Daily budget ${daily_budget:.2f} would be exceeded (spent: ${today_spend:.2f})",
                    action=action,
                    actor_user_id=actor_user_id,
                    org_id=org_id,
                    estimated_cost_usd=estimated_cost_usd,
                    metadata=metadata or {},
                )
                _persist_audit(decision)
                return decision
        except Exception as e:
            # Budget check FAILED → fail-closed for paid actions
            decision = GovernanceDecision(
                state=DecisionState.GOVERNANCE_UNAVAILABLE,
                risk_class=risk_class,
                reason="Budget verification unavailable — paid action denied",
                action=action,
                actor_user_id=actor_user_id,
                org_id=org_id,
                estimated_cost_usd=estimated_cost_usd,
                failed_dependencies=[f"budget:{str(e)[:50]}"],
                metadata=metadata or {},
            )
            _persist_audit(decision)
            return decision

    # -------------------------------------------------------------------------
    # Step 4: Policy-based approval requirements
    # -------------------------------------------------------------------------

    if policies:
        # Check specific policy rules
        if risk_class == RiskClass.DESTRUCTIVE and policies.get("require_delete_approval", True):
            decision = GovernanceDecision(
                state=DecisionState.APPROVAL_REQUIRED,
                risk_class=risk_class,
                reason="Destructive action requires human approval per workspace policy",
                action=action,
                actor_user_id=actor_user_id,
                org_id=org_id,
                estimated_cost_usd=estimated_cost_usd,
                metadata=metadata or {},
            )
            _persist_audit(decision)
            return decision

        if risk_class == RiskClass.PUBLISHING and policies.get("require_publish_approval", True):
            decision = GovernanceDecision(
                state=DecisionState.APPROVAL_REQUIRED,
                risk_class=risk_class,
                reason="Publishing requires human approval per workspace policy",
                action=action,
                actor_user_id=actor_user_id,
                org_id=org_id,
                estimated_cost_usd=estimated_cost_usd,
                metadata=metadata or {},
            )
            _persist_audit(decision)
            return decision

        if risk_class == RiskClass.INFRASTRUCTURE and policies.get("auto_approve_gpu_launch") is False:
            decision = GovernanceDecision(
                state=DecisionState.APPROVAL_REQUIRED,
                risk_class=risk_class,
                reason="Infrastructure action requires approval per workspace policy",
                action=action,
                actor_user_id=actor_user_id,
                org_id=org_id,
                estimated_cost_usd=estimated_cost_usd,
                metadata=metadata or {},
            )
            _persist_audit(decision)
            return decision

    # -------------------------------------------------------------------------
    # Step 5: Audit persistence (blocking for high-risk)
    # -------------------------------------------------------------------------

    # For read-only/low-risk with unavailable policies → degraded mode
    if risk_class.allows_degraded and policies is None:
        decision = GovernanceDecision(
            state=DecisionState.DEGRADED_ALLOWED,
            risk_class=risk_class,
            reason="Governance policies unavailable — proceeding in degraded mode",
            action=action,
            actor_user_id=actor_user_id,
            org_id=org_id,
            estimated_cost_usd=estimated_cost_usd,
            failed_dependencies=["policy:unavailable"],
            metadata=metadata or {},
        )
        if not _persist_audit(decision):
            # Even for low-risk, log the failure
            pass
        return decision

    # -------------------------------------------------------------------------
    # Step 6: All checks passed → ALLOWED
    # -------------------------------------------------------------------------

    decision = GovernanceDecision(
        state=DecisionState.ALLOWED,
        risk_class=risk_class,
        reason="All governance checks passed",
        action=action,
        actor_user_id=actor_user_id,
        org_id=org_id,
        estimated_cost_usd=estimated_cost_usd,
        metadata=metadata or {},
    )

    # Persist audit — if this fails for high-risk, BLOCK
    audit_ok = _persist_audit(decision)
    if not audit_ok and risk_class.requires_fail_closed:
        return GovernanceDecision(
            state=DecisionState.AUDIT_FAILURE,
            risk_class=risk_class,
            reason="Audit persistence failed — high-risk action blocked",
            action=action,
            actor_user_id=actor_user_id,
            org_id=org_id,
            estimated_cost_usd=estimated_cost_usd,
            failed_dependencies=["audit:persistence_failed"],
            metadata=metadata or {},
        )

    return decision


# =============================================================================
# Action → Risk Class Mapping
# =============================================================================

# Known action → risk class mappings. Unknown actions default to PAID (fail-closed).
ACTION_RISK_MAP: dict[str, RiskClass] = {
    # Read-only
    "chat": RiskClass.READ_ONLY,
    "list_assets": RiskClass.READ_ONLY,
    "list_jobs": RiskClass.READ_ONLY,
    "get_status": RiskClass.READ_ONLY,
    "list_models": RiskClass.READ_ONLY,
    "search": RiskClass.READ_ONLY,
    "get_history": RiskClass.READ_ONLY,
    # Low-risk
    "update_profile": RiskClass.LOW_RISK,
    "rename_project": RiskClass.LOW_RISK,
    "edit_caption": RiskClass.LOW_RISK,
    "update_settings": RiskClass.LOW_RISK,
    # Paid
    "generate_image": RiskClass.PAID,
    "generate_video": RiskClass.PAID,
    "train_lora": RiskClass.PAID,
    "run_generation": RiskClass.PAID,
    "render_video": RiskClass.PAID,
    # Destructive
    "delete_asset": RiskClass.DESTRUCTIVE,
    "delete_project": RiskClass.DESTRUCTIVE,
    "delete_talent": RiskClass.DESTRUCTIVE,
    "delete_dataset": RiskClass.DESTRUCTIVE,
    "delete_model": RiskClass.DESTRUCTIVE,
    "cancel_job": RiskClass.DESTRUCTIVE,
    # Publishing
    "publish_post": RiskClass.PUBLISHING,
    "schedule_publication": RiskClass.PUBLISHING,
    "send_webhook": RiskClass.PUBLISHING,
    # Credential
    "store_credential": RiskClass.CREDENTIAL,
    "rotate_credential": RiskClass.CREDENTIAL,
    "revoke_credential": RiskClass.CREDENTIAL,
    # Model activation
    "promote_lora": RiskClass.MODEL_ACTIVATE,
    "activate_model": RiskClass.MODEL_ACTIVATE,
    # Infrastructure
    "launch_gpu": RiskClass.INFRASTRUCTURE,
    "stop_gpu": RiskClass.INFRASTRUCTURE,
    "launch_worker": RiskClass.INFRASTRUCTURE,
    "pause_worker": RiskClass.INFRASTRUCTURE,
}


def classify_action(action: str) -> RiskClass:
    """Classify an action by risk. Unknown actions default to PAID (fail-closed).

    UNVERIFIED: Actions not in the map are conservatively classified as PAID.
    New actions should be explicitly added to ACTION_RISK_MAP.
    """
    return ACTION_RISK_MAP.get(action, RiskClass.PAID)

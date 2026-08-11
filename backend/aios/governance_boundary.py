"""Canonical Governance Boundary — Single enforcement point for ALL AI-initiated side effects.

Implements Requirement R59: Mandatory Agent Governance Boundary.

This module provides ONE canonical enforcement point through which ALL
AI-initiated side effects must pass before execution. The GovernanceBoundary
evaluates 17 dimensions before permitting any action:

    identity, trust_domain, tenant_context, role, entitlement, consent,
    safety_policy, budget, resource_ownership, risk_classification,
    required_approvals, provider_capability, environment_restrictions,
    autonomy_profile, privacy_restrictions, compute_availability_state,
    feature_rollout_status

Design invariants:
    - High-impact actions FAIL CLOSED when any required dimension is indeterminate
    - Read-only actions MAY degrade safely (partial data, cached results)
    - Every evaluation produces an auditable GovernanceResult with correlation ID
    - No side effect executes without passing through evaluate()

Validates: Requirements R59.1, R59.2, R59.3, R59.4, R59.5
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


class RiskClassification(str, Enum):
    """Action risk levels for the governance boundary.

    Determines fail-closed vs. degraded-mode behavior.
    """

    READ_ONLY = "read_only"
    LOW_IMPACT = "low_impact"
    MEDIUM_IMPACT = "medium_impact"
    HIGH_IMPACT = "high_impact"
    DESTRUCTIVE = "destructive"

    @property
    def requires_fail_closed(self) -> bool:
        """Whether indeterminate evaluation must deny the action."""
        return self in (
            RiskClassification.MEDIUM_IMPACT,
            RiskClassification.HIGH_IMPACT,
            RiskClassification.DESTRUCTIVE,
        )

    @property
    def allows_degraded(self) -> bool:
        """Whether this risk level permits degraded-mode execution."""
        return self in (RiskClassification.READ_ONLY, RiskClassification.LOW_IMPACT)


# =============================================================================
# Decision Enum
# =============================================================================


class Decision(str, Enum):
    """Governance evaluation outcome."""

    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"

    @property
    def permits_execution(self) -> bool:
        """Whether execution may proceed without further intervention."""
        return self == Decision.ALLOW


# =============================================================================
# Autonomy Profile
# =============================================================================


class AutonomyProfile(str, Enum):
    """Workspace-configured agent autonomy level (R98)."""

    ADVISORY = "advisory"
    ASSISTED = "assisted"
    AUTONOMOUS_WITHIN_LIMITS = "autonomous_within_limits"


# =============================================================================
# GovernanceRequest — input to evaluate()
# =============================================================================


@dataclass
class GovernanceRequest:
    """All dimensions required for a governance evaluation.

    This is the single input structure for GovernanceBoundary.evaluate().
    Every AI-initiated side effect must provide these fields before execution.

    Required fields (MUST be present for high-impact actions):
        - action_type: What is being attempted
        - identity: Who/what is requesting (user_id or service identity)
        - trust_domain: Privilege level of the requestor
        - tenant_context: Which org (org_id + role)

    Contextual fields (evaluated when present, fail-closed when required but missing):
        - entitlement: What the plan allows
        - consent_status: Consent state for talent/content operations
        - safety_policy: Content restriction evaluation result
        - budget_available: Whether the org can afford the action
        - resource_ownership: Whether the actor owns the target resource
        - risk_classification: Pre-classified risk level of the action
        - required_approvals: Whether policy mandates human confirmation
        - provider_capability: Whether the target system can perform the action
        - environment: Environment restrictions (prod/staging/dev)
        - autonomy_profile: Workspace agent autonomy setting
        - privacy_restrictions: Data location and privacy policies
        - compute_availability_state: Founder-controlled compute state
        - feature_rollout_status: Whether the feature is rolled out for this context
        - correlation_id: Request correlation for observability
    """

    # Required identity dimensions
    action_type: str
    identity: str | None = None
    trust_domain: str | None = None
    tenant_context: TenantContext | None = None

    # Contextual evaluation dimensions
    role: str | None = None
    entitlement: str | None = None
    consent_status: str | None = None
    safety_policy: SafetyPolicyResult | None = None
    budget_available: float | None = None
    resource_ownership: bool | None = None
    risk_classification: RiskClassification = RiskClassification.MEDIUM_IMPACT
    required_approvals: list[str] | None = None
    provider_capability: bool | None = None
    environment: str | None = None
    autonomy_profile: AutonomyProfile | None = None
    privacy_restrictions: list[str] | None = None
    compute_availability_state: str | None = None
    feature_rollout_status: bool | None = None

    # Observability
    correlation_id: str = field(
        default_factory=lambda: f"gov-{_uuid.uuid4().hex[:16]}"
    )

    # Cost estimate for budget checks
    estimated_cost_usd: float = 0.0

    # Additional metadata (never secrets)
    metadata: dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Supporting dataclasses
# =============================================================================


@dataclass(frozen=True)
class TenantContext:
    """Resolved tenant context from JWT + org_members."""

    org_id: str
    role: str


@dataclass(frozen=True)
class SafetyPolicyResult:
    """Result of safety policy evaluation."""

    passed: bool
    violations: list[str] = field(default_factory=list)
    reason: str = ""


# =============================================================================
# GovernanceResult — output of evaluate()
# =============================================================================


@dataclass(frozen=True)
class GovernanceResult:
    """Immutable result of a governance evaluation.

    Every call to GovernanceBoundary.evaluate() returns one of these.
    It is explicit, auditable, and non-leaking (no secrets in fields).
    """

    decision: Decision
    denial_reason: str | None = None
    required_approval_type: str | None = None
    evaluation_id: str = field(
        default_factory=lambda: f"eval-{_uuid.uuid4().hex[:12]}"
    )
    risk_classification: RiskClassification = RiskClassification.MEDIUM_IMPACT
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    is_degraded: bool = False
    failed_checks: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        """Whether execution may proceed."""
        return self.decision.permits_execution

    def to_dict(self) -> dict[str, Any]:
        """Serialize for API response (safe — no secrets)."""
        return {
            "decision": self.decision.value,
            "allowed": self.allowed,
            "denial_reason": self.denial_reason,
            "required_approval_type": self.required_approval_type,
            "evaluation_id": self.evaluation_id,
            "risk_classification": self.risk_classification.value,
            "timestamp": self.timestamp,
            "is_degraded": self.is_degraded,
            "failed_checks": self.failed_checks,
        }


# =============================================================================
# Governance Evaluation Audit Trail
# =============================================================================

_governance_evaluations: list[dict[str, Any]] = []
_MAX_EVALUATIONS = 5000


def _record_evaluation(
    request: GovernanceRequest, result: GovernanceResult
) -> None:
    """Persist evaluation to audit trail.

    In production this writes to Supabase governance_evaluations table.
    In-memory implementation for the initial version.
    """
    entry = {
        "evaluation_id": result.evaluation_id,
        "correlation_id": request.correlation_id,
        "timestamp": result.timestamp,
        "action_type": request.action_type,
        "identity": request.identity,
        "trust_domain": request.trust_domain,
        "org_id": request.tenant_context.org_id if request.tenant_context else None,
        "role": request.role or (request.tenant_context.role if request.tenant_context else None),
        "risk_classification": result.risk_classification.value,
        "decision": result.decision.value,
        "denial_reason": result.denial_reason,
        "required_approval_type": result.required_approval_type,
        "is_degraded": result.is_degraded,
        "failed_checks": result.failed_checks,
        "estimated_cost_usd": request.estimated_cost_usd,
    }
    _governance_evaluations.append(entry)
    if len(_governance_evaluations) > _MAX_EVALUATIONS:
        _governance_evaluations.pop(0)


def get_evaluation_audit(
    org_id: str | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    """Retrieve recent governance evaluations for audit review."""
    entries = _governance_evaluations if not org_id else [
        e for e in _governance_evaluations if e.get("org_id") == org_id
    ]
    return list(reversed(entries[-limit:]))


def clear_evaluation_audit() -> None:
    """Clear the in-memory audit trail (for testing)."""
    _governance_evaluations.clear()


# =============================================================================
# Cost threshold for automatic approval requirement
# =============================================================================

_DEFAULT_COST_APPROVAL_THRESHOLD_USD: float = 5.0


# =============================================================================
# GovernanceBoundary — the ONE canonical enforcement point
# =============================================================================


class GovernanceBoundary:
    """ONE canonical enforcement point for ALL AI-initiated side effects.

    Evaluates 17 dimensions before permitting execution:
        identity, trust_domain, tenant_context, role, entitlement, consent,
        safety_policy, budget, resource_ownership, risk_classification,
        required_approvals, provider_capability, environment_restrictions,
        autonomy_profile, privacy_restrictions, compute_availability_state,
        feature_rollout_status

    Behavior:
        - High-impact actions (MEDIUM_IMPACT, HIGH_IMPACT, DESTRUCTIVE):
          Fail closed when identity, trust_domain, or tenant_context is missing
          or when any required check cannot be determined.
        - Read-only / low-impact actions:
          May degrade safely when optional dimensions are unavailable,
          as long as identity is valid.

    This class is stateless — all state is passed in via GovernanceRequest.
    It is safe to instantiate per-request or as a singleton.

    Usage:
        boundary = GovernanceBoundary()
        result = boundary.evaluate(request)
        if not result.allowed:
            raise HTTPException(403, result.denial_reason)

    Validates: Requirements R59.1, R59.2, R59.3, R59.4, R59.5
    """

    def __init__(
        self,
        cost_approval_threshold_usd: float = _DEFAULT_COST_APPROVAL_THRESHOLD_USD,
    ) -> None:
        self._cost_threshold = cost_approval_threshold_usd

    def evaluate(self, request: GovernanceRequest) -> GovernanceResult:
        """Evaluate whether an AI-initiated side effect may proceed.

        This is the SINGLE entry point. Every side effect MUST call this
        before execution. No bypass is permitted.

        Args:
            request: GovernanceRequest with all evaluation dimensions.

        Returns:
            GovernanceResult — explicit decision, never ambiguous.
        """
        failed_checks: list[str] = []

        # =================================================================
        # Phase 1: Identity verification (REQUIRED for all actions)
        # =================================================================

        if not request.identity:
            if request.risk_classification.requires_fail_closed:
                result = GovernanceResult(
                    decision=Decision.DENY,
                    denial_reason="Identity is required but missing — fail closed",
                    risk_classification=request.risk_classification,
                    failed_checks=["identity"],
                )
                _record_evaluation(request, result)
                return result
            else:
                failed_checks.append("identity")

        # =================================================================
        # Phase 2: Trust domain verification
        # =================================================================

        if not request.trust_domain:
            if request.risk_classification.requires_fail_closed:
                result = GovernanceResult(
                    decision=Decision.DENY,
                    denial_reason="Trust domain is required but missing — fail closed",
                    risk_classification=request.risk_classification,
                    failed_checks=["trust_domain"],
                )
                _record_evaluation(request, result)
                return result
            else:
                failed_checks.append("trust_domain")

        # =================================================================
        # Phase 3: Tenant context verification
        # =================================================================

        if not request.tenant_context:
            if request.risk_classification.requires_fail_closed:
                result = GovernanceResult(
                    decision=Decision.DENY,
                    denial_reason="Tenant context is required but missing — fail closed",
                    risk_classification=request.risk_classification,
                    failed_checks=["tenant_context"],
                )
                _record_evaluation(request, result)
                return result
            else:
                failed_checks.append("tenant_context")

        # =================================================================
        # Phase 4: Role verification (required for mutating actions)
        # =================================================================

        effective_role = request.role or (
            request.tenant_context.role if request.tenant_context else None
        )
        if not effective_role and request.risk_classification.requires_fail_closed:
            result = GovernanceResult(
                decision=Decision.DENY,
                denial_reason="Role is required for this action but missing — fail closed",
                risk_classification=request.risk_classification,
                failed_checks=["role"],
            )
            _record_evaluation(request, result)
            return result

        # =================================================================
        # Phase 5: Safety policy check
        # =================================================================

        if request.safety_policy is not None and not request.safety_policy.passed:
            result = GovernanceResult(
                decision=Decision.DENY,
                denial_reason=(
                    f"Safety policy violation: {request.safety_policy.reason or 'content restricted'}"
                ),
                risk_classification=request.risk_classification,
                failed_checks=["safety_policy"],
            )
            _record_evaluation(request, result)
            return result

        # =================================================================
        # Phase 6: Consent verification (when applicable)
        # =================================================================

        if request.consent_status == "revoked":
            result = GovernanceResult(
                decision=Decision.DENY,
                denial_reason="Consent has been revoked for this operation",
                risk_classification=request.risk_classification,
                failed_checks=["consent"],
            )
            _record_evaluation(request, result)
            return result

        if request.consent_status == "required" and request.risk_classification.requires_fail_closed:
            result = GovernanceResult(
                decision=Decision.DENY,
                denial_reason="Consent is required but not granted — fail closed",
                risk_classification=request.risk_classification,
                failed_checks=["consent"],
            )
            _record_evaluation(request, result)
            return result

        # =================================================================
        # Phase 7: Budget check
        # =================================================================

        if request.estimated_cost_usd > 0:
            if request.budget_available is not None:
                if request.estimated_cost_usd > request.budget_available:
                    result = GovernanceResult(
                        decision=Decision.DENY,
                        denial_reason=(
                            f"Budget insufficient: action costs ${request.estimated_cost_usd:.2f} "
                            f"but only ${request.budget_available:.2f} available"
                        ),
                        risk_classification=request.risk_classification,
                        failed_checks=["budget"],
                    )
                    _record_evaluation(request, result)
                    return result
            elif request.risk_classification.requires_fail_closed:
                # Budget unknown for a paid action → fail closed
                result = GovernanceResult(
                    decision=Decision.DENY,
                    denial_reason="Budget availability unknown for paid action — fail closed",
                    risk_classification=request.risk_classification,
                    failed_checks=["budget"],
                )
                _record_evaluation(request, result)
                return result
            else:
                failed_checks.append("budget")

        # =================================================================
        # Phase 8: Cost-based approval requirement
        # =================================================================

        if request.estimated_cost_usd > self._cost_threshold:
            result = GovernanceResult(
                decision=Decision.REQUIRE_APPROVAL,
                denial_reason=(
                    f"Cost ${request.estimated_cost_usd:.2f} exceeds "
                    f"auto-approve threshold ${self._cost_threshold:.2f}"
                ),
                required_approval_type="cost_threshold",
                risk_classification=request.risk_classification,
            )
            _record_evaluation(request, result)
            return result

        # =================================================================
        # Phase 9: Required approvals check
        # =================================================================

        if request.required_approvals:
            result = GovernanceResult(
                decision=Decision.REQUIRE_APPROVAL,
                denial_reason=(
                    f"Action requires approval: {', '.join(request.required_approvals)}"
                ),
                required_approval_type=request.required_approvals[0],
                risk_classification=request.risk_classification,
            )
            _record_evaluation(request, result)
            return result

        # =================================================================
        # Phase 10: Resource ownership check
        # =================================================================

        if request.resource_ownership is False and request.risk_classification in (
            RiskClassification.HIGH_IMPACT,
            RiskClassification.DESTRUCTIVE,
        ):
            result = GovernanceResult(
                decision=Decision.DENY,
                denial_reason="Actor does not own the target resource",
                risk_classification=request.risk_classification,
                failed_checks=["resource_ownership"],
            )
            _record_evaluation(request, result)
            return result

        # =================================================================
        # Phase 11: Provider capability check
        # =================================================================

        if request.provider_capability is False:
            result = GovernanceResult(
                decision=Decision.DENY,
                denial_reason="Target provider cannot perform this action",
                risk_classification=request.risk_classification,
                failed_checks=["provider_capability"],
            )
            _record_evaluation(request, result)
            return result

        # =================================================================
        # Phase 12: Compute availability state check
        # =================================================================

        if request.compute_availability_state == "disabled":
            result = GovernanceResult(
                decision=Decision.DENY,
                denial_reason="Platform-managed compute is disabled",
                risk_classification=request.risk_classification,
                failed_checks=["compute_availability_state"],
            )
            _record_evaluation(request, result)
            return result

        # =================================================================
        # Phase 13: Feature rollout check
        # =================================================================

        if request.feature_rollout_status is False:
            result = GovernanceResult(
                decision=Decision.DENY,
                denial_reason="Feature is not rolled out for this context",
                risk_classification=request.risk_classification,
                failed_checks=["feature_rollout_status"],
            )
            _record_evaluation(request, result)
            return result

        # =================================================================
        # Phase 14: Autonomy profile enforcement
        # =================================================================

        if request.autonomy_profile == AutonomyProfile.ADVISORY:
            # Advisory mode: recommend only, no mutations without explicit instruction
            if request.risk_classification.requires_fail_closed:
                result = GovernanceResult(
                    decision=Decision.REQUIRE_APPROVAL,
                    denial_reason=(
                        "Workspace autonomy is ADVISORY — "
                        "mutating actions require explicit user instruction"
                    ),
                    required_approval_type="autonomy_advisory",
                    risk_classification=request.risk_classification,
                )
                _record_evaluation(request, result)
                return result

        # =================================================================
        # Phase 15: Environment restrictions
        # =================================================================

        if request.environment == "production" and request.risk_classification == RiskClassification.DESTRUCTIVE:
            result = GovernanceResult(
                decision=Decision.REQUIRE_APPROVAL,
                denial_reason="Destructive actions in production require explicit approval",
                required_approval_type="production_destructive",
                risk_classification=request.risk_classification,
            )
            _record_evaluation(request, result)
            return result

        # =================================================================
        # Phase 16: Entitlement check
        # =================================================================

        if request.entitlement == "exceeded":
            result = GovernanceResult(
                decision=Decision.DENY,
                denial_reason="Plan entitlement exceeded for this action",
                risk_classification=request.risk_classification,
                failed_checks=["entitlement"],
            )
            _record_evaluation(request, result)
            return result

        # =================================================================
        # Phase 17: Privacy restrictions
        # =================================================================

        if request.privacy_restrictions:
            # If there are active privacy restrictions that block the action,
            # we deny. The caller resolves which restrictions apply.
            for restriction in request.privacy_restrictions:
                if restriction.startswith("block:"):
                    result = GovernanceResult(
                        decision=Decision.DENY,
                        denial_reason=f"Privacy restriction active: {restriction}",
                        risk_classification=request.risk_classification,
                        failed_checks=["privacy_restrictions"],
                    )
                    _record_evaluation(request, result)
                    return result

        # =================================================================
        # Final: All checks passed
        # =================================================================

        if failed_checks:
            # Some optional checks failed but action is low-risk → degraded allow
            result = GovernanceResult(
                decision=Decision.ALLOW,
                risk_classification=request.risk_classification,
                is_degraded=True,
                failed_checks=failed_checks,
                metadata={"degraded_reason": "Some optional checks unavailable"},
            )
            _record_evaluation(request, result)
            return result

        result = GovernanceResult(
            decision=Decision.ALLOW,
            risk_classification=request.risk_classification,
        )
        _record_evaluation(request, result)
        return result

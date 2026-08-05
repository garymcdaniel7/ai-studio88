"""Unified Governance Enforcement Boundary — Story 034.

ONE mandatory policy-enforcement point for ALL side-effecting AI actions.
Every tool invocation path (AIOS execution, Hermes tools, MCP server) MUST
call enforce_governance() before executing side effects.

Contract:
    1. Caller provides: action, parameters, execution context
    2. Enforcement checks: membership, role, budget, consent, approval policy
    3. Returns: GovernanceDecision (allow, deny, or require_approval)
    4. Every decision is audited with full context

Side-effecting tools (MUST be governed):
    generate_image, generate_video, train_lora, generate_voice,
    create_talent, schedule_post, launch_gpu_worker, stop_gpu_worker

Read-only tools (bypass governance, explicitly allowed):
    search_talent, get_talent_dna, search_assets, search_knowledge,
    check_platform_health, get_fleet_status, get_worker_status,
    check_generation_pipeline, get_cost_summary, estimate_cost,
    get_training_status, get_uat_results, diagnose_service, recommend_workflow,
    auto_configure_generation, run_uat_tests, get_talent_knowledge,
    search_knowledge_graph, get_story_context, continue_story
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Action Classification
# =============================================================================


class ActionEffect(str, Enum):
    """Classification of tool side effects."""
    SIDE_EFFECT = "side_effect"  # Costs money, mutates data, or publishes
    READ_ONLY = "read_only"      # No side effects, safe to execute freely


# Authoritative classification of every known tool
TOOL_EFFECTS: dict[str, ActionEffect] = {
    # Side-effecting (MUST be governed)
    "generate_image": ActionEffect.SIDE_EFFECT,
    "generate_video": ActionEffect.SIDE_EFFECT,
    "train_lora": ActionEffect.SIDE_EFFECT,
    "generate_voice": ActionEffect.SIDE_EFFECT,
    "create_talent": ActionEffect.SIDE_EFFECT,
    "schedule_post": ActionEffect.SIDE_EFFECT,
    "publish_post": ActionEffect.SIDE_EFFECT,
    "launch_gpu_worker": ActionEffect.SIDE_EFFECT,
    "stop_gpu_worker": ActionEffect.SIDE_EFFECT,

    # Read-only (governance bypass explicitly allowed)
    "search_talent": ActionEffect.READ_ONLY,
    "get_talent_dna": ActionEffect.READ_ONLY,
    "get_talent_knowledge": ActionEffect.READ_ONLY,
    "search_assets": ActionEffect.READ_ONLY,
    "search_knowledge": ActionEffect.READ_ONLY,
    "search_knowledge_graph": ActionEffect.READ_ONLY,
    "check_platform_health": ActionEffect.READ_ONLY,
    "get_fleet_status": ActionEffect.READ_ONLY,
    "get_worker_status": ActionEffect.READ_ONLY,
    "check_generation_pipeline": ActionEffect.READ_ONLY,
    "get_cost_summary": ActionEffect.READ_ONLY,
    "estimate_cost": ActionEffect.READ_ONLY,
    "get_training_status": ActionEffect.READ_ONLY,
    "get_uat_results": ActionEffect.READ_ONLY,
    "run_uat_tests": ActionEffect.READ_ONLY,
    "diagnose_service": ActionEffect.READ_ONLY,
    "recommend_workflow": ActionEffect.READ_ONLY,
    "auto_configure_generation": ActionEffect.READ_ONLY,
    "check_gpu_status": ActionEffect.READ_ONLY,
    "get_story_context": ActionEffect.READ_ONLY,
    "continue_story": ActionEffect.READ_ONLY,
}

# Tools that are ALWAYS side-effecting and must NEVER skip governance
GOVERNED_TOOLS = frozenset(
    tool for tool, effect in TOOL_EFFECTS.items()
    if effect == ActionEffect.SIDE_EFFECT
)

# Tools that are explicitly safe to run without governance
READ_ONLY_TOOLS = frozenset(
    tool for tool, effect in TOOL_EFFECTS.items()
    if effect == ActionEffect.READ_ONLY
)


# =============================================================================
# Governance Decision Contract
# =============================================================================


class GovernanceOutcome(str, Enum):
    """Possible outcomes of a governance check."""
    ALLOW = "allow"               # Proceed immediately (within policy)
    DENY = "deny"                 # Blocked by policy (insufficient role, budget, etc.)
    REQUIRE_APPROVAL = "require_approval"  # Queue for human approval
    BYPASS_READ_ONLY = "bypass_read_only"  # Read-only tool, no governance needed


@dataclass(frozen=True)
class GovernanceDecision:
    """The result of a governance enforcement check.

    Every decision is immutable and auditable.
    """
    outcome: GovernanceOutcome
    tool: str
    actor_id: str
    org_id: str
    reason: str
    policy_version: str = ""
    arguments_hash: str = ""
    estimated_cost_usd: float = 0.0
    request_id: str = field(default_factory=lambda: f"gov-{uuid.uuid4().hex[:12]}")
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome.value,
            "tool": self.tool,
            "actor_id": self.actor_id,
            "org_id": self.org_id,
            "reason": self.reason,
            "policy_version": self.policy_version,
            "arguments_hash": self.arguments_hash,
            "estimated_cost_usd": self.estimated_cost_usd,
            "request_id": self.request_id,
            "timestamp": self.timestamp,
        }


# =============================================================================
# Enforcement Errors
# =============================================================================


class GovernanceBlockedError(Exception):
    """Raised when governance denies an action."""

    def __init__(self, decision: GovernanceDecision) -> None:
        self.decision = decision
        super().__init__(f"Governance DENIED: {decision.tool} — {decision.reason}")


class GovernanceApprovalRequired(Exception):
    """Raised when governance requires human approval before proceeding."""

    def __init__(self, decision: GovernanceDecision) -> None:
        self.decision = decision
        super().__init__(f"Approval required: {decision.tool} — {decision.reason}")


# =============================================================================
# The Enforcement Boundary
# =============================================================================


def compute_arguments_hash(tool: str, parameters: dict) -> str:
    """Compute a stable hash of tool + arguments for replay detection."""
    content = json.dumps({"tool": tool, "params": parameters}, sort_keys=True, default=str)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def enforce_governance(
    tool: str,
    parameters: dict,
    actor_id: str,
    org_id: str,
    role: str = "editor",
    estimated_cost_usd: float = 0.0,
    session_id: str | None = None,
    source: str = "unknown",
) -> GovernanceDecision:
    """THE mandatory governance enforcement point.

    Every side-effecting tool invocation MUST call this BEFORE execution.
    Read-only tools receive an immediate BYPASS_READ_ONLY decision.

    Args:
        tool: Tool name being invoked.
        parameters: Tool arguments (hashed for audit, not stored raw).
        actor_id: The user/agent triggering the action.
        org_id: The workspace this action belongs to.
        role: Actor's role (viewer/editor/admin/owner).
        estimated_cost_usd: Estimated cost of this action.
        session_id: AIOS session (for linking to approval queue).
        source: Where this call originates (hermes/mcp/aios/ui).

    Returns:
        GovernanceDecision with outcome and audit context.

    Raises:
        GovernanceBlockedError: If action is denied.
        GovernanceApprovalRequired: If human approval needed.
    """
    args_hash = compute_arguments_hash(tool, parameters)

    # ─── Unknown tools are DENIED by default (fail-safe) ─────────────────
    if tool not in TOOL_EFFECTS:
        decision = GovernanceDecision(
            outcome=GovernanceOutcome.DENY,
            tool=tool,
            actor_id=actor_id,
            org_id=org_id,
            reason=f"Unknown tool '{tool}' — not registered in governance",
            arguments_hash=args_hash,
        )
        _audit_decision(decision, source)
        raise GovernanceBlockedError(decision)

    # ─── Read-only tools bypass governance (explicitly safe) ─────────────
    if TOOL_EFFECTS[tool] == ActionEffect.READ_ONLY:
        decision = GovernanceDecision(
            outcome=GovernanceOutcome.BYPASS_READ_ONLY,
            tool=tool,
            actor_id=actor_id,
            org_id=org_id,
            reason="Read-only tool — no governance required",
            arguments_hash=args_hash,
        )
        # Don't audit every read-only call (too noisy)
        return decision

    # ─── Side-effecting tool: full governance check ──────────────────────

    # 1. Validate actor and workspace
    if not actor_id:
        decision = GovernanceDecision(
            outcome=GovernanceOutcome.DENY,
            tool=tool,
            actor_id=actor_id or "unknown",
            org_id=org_id or "unknown",
            reason="Missing actor identity — cannot authorize action",
            arguments_hash=args_hash,
        )
        _audit_decision(decision, source)
        raise GovernanceBlockedError(decision)

    if not org_id:
        decision = GovernanceDecision(
            outcome=GovernanceOutcome.DENY,
            tool=tool,
            actor_id=actor_id,
            org_id="unknown",
            reason="Missing workspace context — cannot authorize action",
            arguments_hash=args_hash,
        )
        _audit_decision(decision, source)
        raise GovernanceBlockedError(decision)

    # 2. Check role authorization (viewer cannot execute side effects)
    role_hierarchy = ["viewer", "editor", "admin", "owner"]
    if role not in role_hierarchy or role_hierarchy.index(role) < role_hierarchy.index("editor"):
        decision = GovernanceDecision(
            outcome=GovernanceOutcome.DENY,
            tool=tool,
            actor_id=actor_id,
            org_id=org_id,
            reason=f"Role '{role}' insufficient — side effects require editor+",
            arguments_hash=args_hash,
        )
        _audit_decision(decision, source)
        raise GovernanceBlockedError(decision)

    # 3. Load workspace governance policies
    policies = _load_policies(org_id)
    policy_version = str(hash(frozenset(policies.items())) % 100000)

    # 4. Check if this tool requires approval per policy
    requires_approval, approval_reason = _check_approval_required(
        tool, policies, estimated_cost_usd
    )

    if requires_approval:
        decision = GovernanceDecision(
            outcome=GovernanceOutcome.REQUIRE_APPROVAL,
            tool=tool,
            actor_id=actor_id,
            org_id=org_id,
            reason=approval_reason,
            policy_version=policy_version,
            arguments_hash=args_hash,
            estimated_cost_usd=estimated_cost_usd,
        )
        _audit_decision(decision, source)
        raise GovernanceApprovalRequired(decision)

    # 5. Approved — allow execution
    decision = GovernanceDecision(
        outcome=GovernanceOutcome.ALLOW,
        tool=tool,
        actor_id=actor_id,
        org_id=org_id,
        reason="Auto-approved per governance policy",
        policy_version=policy_version,
        arguments_hash=args_hash,
        estimated_cost_usd=estimated_cost_usd,
    )
    _audit_decision(decision, source)
    return decision


# =============================================================================
# Policy Checks
# =============================================================================


def _load_policies(org_id: str) -> dict:
    """Load governance policies for a workspace."""
    try:
        from backend.aios.governance.policies import get_policies
        return get_policies(org_id=org_id)
    except Exception:
        # Fail-safe: if policies can't be loaded, use restrictive defaults
        from backend.governance_policy import POLICY_DEFAULTS
        return POLICY_DEFAULTS


def _check_approval_required(
    tool: str,
    policies: dict,
    estimated_cost_usd: float,
) -> tuple[bool, str]:
    """Check if a tool requires human approval under current policies.

    Returns (requires_approval, reason).
    """
    # Generation tools
    if tool in ("generate_image", "generate_video"):
        if not policies.get("auto_approve_generation", True):
            return True, "Generation requires approval per workspace policy"

    # Training tools
    if tool == "train_lora":
        if not policies.get("auto_approve_training", False):
            return True, "Training requires approval per workspace policy"

    # GPU infrastructure
    if tool in ("launch_gpu_worker", "stop_gpu_worker"):
        if not policies.get("auto_approve_gpu_launch", False):
            return True, "GPU operations require approval per workspace policy"
        if policies.get("require_gpu_approval", False):
            return True, "GPU operations require approval (require_gpu_approval=true)"

    # Publishing
    if tool == "schedule_post":
        if policies.get("require_publish_approval", True):
            return True, "Publishing requires approval per workspace policy"

    # Voice generation
    if tool == "generate_voice":
        # Voice uses ElevenLabs credits — treat like generation
        if not policies.get("auto_approve_generation", True):
            return True, "Voice generation requires approval per workspace policy"

    # Budget gate — any tool exceeding max_auto_spend
    max_auto = float(policies.get("max_auto_spend_usd", 5.0))
    if estimated_cost_usd > max_auto:
        return True, (
            f"Estimated cost ${estimated_cost_usd:.3f} exceeds "
            f"auto-approval limit ${max_auto:.2f}"
        )

    return False, ""


# =============================================================================
# Audit Trail
# =============================================================================


def _audit_decision(decision: GovernanceDecision, source: str) -> None:
    """Record a governance decision for audit trail."""
    try:
        from backend.database import supabase
        supabase.table("aios_decisions").insert({
            "session_id": None,
            "decision_type": f"governance_{decision.outcome.value}",
            "provider": source,
            "model": decision.tool,
            "input_summary": f"tool={decision.tool} hash={decision.arguments_hash}",
            "output_summary": decision.reason[:200],
            "latency_ms": 0,
            "cost_usd": decision.estimated_cost_usd,
            "mode": "governance",
            "confidence": 1.0,
            "reasoning": decision.reason,
            "metadata": {
                "actor_id": decision.actor_id,
                "org_id": decision.org_id,
                "policy_version": decision.policy_version,
                "request_id": decision.request_id,
                "source": source,
            },
        }).execute()
    except Exception as e:
        # Audit failure must not block governance decisions
        logger.error(f"Governance audit failed: {e}")


# =============================================================================
# Convenience: Check-only (no raise)
# =============================================================================


def is_governed(tool: str) -> bool:
    """Check if a tool requires governance enforcement."""
    return tool in GOVERNED_TOOLS


def is_read_only(tool: str) -> bool:
    """Check if a tool is explicitly classified as read-only."""
    return tool in READ_ONLY_TOOLS


def classify_tool(tool: str) -> ActionEffect | None:
    """Get the effect classification of a tool. None if unknown."""
    return TOOL_EFFECTS.get(tool)

"""Governance Middleware — intercepts proposed actions and enforces policies.

Called after the council produces decisions.
For every proposed action:
1. Load governance policies for this user/org
2. Check authority matrix (requires_approval?)
3. Check budget (enough remaining?)
4. If approved: mark as auto-approved
5. If needs review: enqueue to aios_approvals, mark as pending

Returns the same action list with approval_status populated.
"""

from __future__ import annotations

import logging

from backend.aios.council.base import AuthorityLevel, ProposedAction

logger = logging.getLogger(__name__)


def apply_governance(
    actions: list[ProposedAction],
    session_id: str = "",
    user_id: str | None = None,
    org_id: str | None = None,
    agent_authority: AuthorityLevel = AuthorityLevel.RECOMMEND,
) -> dict:
    """Apply governance rules to a list of proposed actions.

    Returns:
        {
            auto_approved: list of actions cleared to execute,
            pending_approval: list of approval records queued for review,
            blocked: list of actions blocked (budget exceeded or invalid),
        }
    """
    from backend.aios.governance.authority import requires_approval
    from backend.aios.governance.policies import get_policies
    from backend.aios.governance.queue import enqueue_approval

    policies = get_policies(user_id=user_id, org_id=org_id)

    auto_approved = []
    pending_approval = []
    blocked = []

    # Check daily budget remaining
    budget_ok = _check_daily_budget(policies, org_id)

    for action in actions:
        # Budget exhausted — block all spending actions
        if not budget_ok and action.estimated_cost_usd > 0:
            blocked.append({
                "tool": action.tool,
                "reason": "Daily budget exhausted",
                "estimated_cost_usd": action.estimated_cost_usd,
            })
            continue

        # Apply authority + policy check
        needs_review, reason = requires_approval(
            tool=action.tool,
            agent_authority=agent_authority,
            estimated_cost=action.estimated_cost_usd,
            governance_policies=policies,
        )

        if needs_review:
            # Enqueue for human review
            approval = enqueue_approval(
                session_id=session_id,
                tool=action.tool,
                parameters=action.parameters,
                reasoning=f"{action.reasoning} | Approval required: {reason}",
                estimated_cost_usd=action.estimated_cost_usd,
                estimated_time_seconds=action.estimated_time_seconds,
                org_id=org_id,
            )
            pending_approval.append({
                "approval_id": approval.get("id"),
                "tool": action.tool,
                "reason": reason,
                "estimated_cost_usd": action.estimated_cost_usd,
                "estimated_time_seconds": action.estimated_time_seconds,
            })
        else:
            auto_approved.append({
                "tool": action.tool,
                "parameters": action.parameters,
                "reasoning": action.reasoning,
                "estimated_cost_usd": action.estimated_cost_usd,
            })

    return {
        "auto_approved": auto_approved,
        "pending_approval": pending_approval,
        "blocked": blocked,
        "policies_applied": {
            "max_auto_spend_usd": policies.get("max_auto_spend_usd"),
            "auto_approve_generation": policies.get("auto_approve_generation"),
            "require_publish_approval": policies.get("require_publish_approval"),
        },
    }


def _check_daily_budget(policies: dict, org_id: str | None = None) -> bool:
    """Check if we're still within today's budget."""
    daily_budget = float(policies.get("budget_daily_usd", 20.0))
    if daily_budget <= 0:
        return True  # No budget set = unlimited

    try:
        from backend.infrastructure.cost_intelligence import get_cost_tracker

        tracker = get_cost_tracker()
        today_spend = tracker.get_today_total()
        return today_spend < daily_budget
    except Exception:
        return True  # If we can't check, allow (fail open)

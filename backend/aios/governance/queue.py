"""Approval Queue — pending actions awaiting human confirmation.

When an action requires human approval:
1. Action stored in aios_approvals table (status=pending)
2. User notified (UI badge count, future: push/email)
3. User reviews at /aios/v1/approvals
4. User approves/rejects → action executed or discarded
5. Decision logged for audit

Table: aios_approvals
"""

from __future__ import annotations

import logging
import uuid

logger = logging.getLogger(__name__)


def _db():
    from backend.database import supabase
    return supabase


def enqueue_approval(
    session_id: str,
    tool: str,
    parameters: dict,
    reasoning: str,
    estimated_cost_usd: float = 0.0,
    estimated_time_seconds: float = 0.0,
    agent: str = "",
    org_id: str | None = None,
    strict: bool = False,
) -> dict:
    """Store a pending action for human review.

    Returns the approval record.

    Args:
        strict: When True, raise if the record could not be persisted.
            Callers that report an approval_id back to a client should set
            this — otherwise a failed insert returns a local record whose
            id exists nowhere, and the client is told to review an approval
            that no human can see. Defaults to False to preserve the
            existing best-effort behavior for internal callers.
    """
    record = {
        "id": uuid.uuid4().hex[:16],
        "session_id": session_id,
        "org_id": org_id,
        "tool": tool,
        "parameters": parameters,
        "reasoning": reasoning,
        "estimated_cost_usd": estimated_cost_usd,
        "estimated_time_seconds": estimated_time_seconds,
        "proposed_by_agent": agent,
        "status": "pending",
    }

    try:
        result = _db().table("aios_approvals").insert(record).execute()
        if not result.data:
            raise RuntimeError("approval insert returned no rows")
        return result.data[0]
    except Exception as e:
        logger.warning(f"Failed to enqueue approval: {e}")
        if strict:
            raise
        return record


def get_pending_approvals(session_id: str | None = None, org_id: str | None = None) -> list[dict]:
    """List pending approvals for a user/org."""
    try:
        query = (
            _db().table("aios_approvals")
            .select("*")
            .eq("status", "pending")
            .order("created_at", desc=True)
        )
        if session_id:
            query = query.eq("session_id", session_id)
        if org_id:
            query = query.eq("org_id", org_id)
        return query.execute().data or []
    except Exception:
        return []


def approve_action(approval_id: str) -> dict:
    """Mark an approval as approved.

    Returns the approval record. Caller should then execute the action.
    """
    try:
        result = _db().table("aios_approvals").update({
            "status": "approved",
            "decided_at": "now()",
        }).eq("id", approval_id).execute()
        return result.data[0] if result.data else {}
    except Exception as e:
        logger.warning(f"Failed to approve action {approval_id}: {e}")
        return {}


def reject_action(approval_id: str, reason: str = "") -> dict:
    """Mark an approval as rejected."""
    try:
        result = _db().table("aios_approvals").update({
            "status": "rejected",
            "rejection_reason": reason,
            "decided_at": "now()",
        }).eq("id", approval_id).execute()
        return result.data[0] if result.data else {}
    except Exception as e:
        logger.warning(f"Failed to reject action {approval_id}: {e}")
        return {}


def count_pending(org_id: str | None = None) -> int:
    """Count pending approvals (for UI badge)."""
    try:
        query = _db().table("aios_approvals").select("id", count="exact").eq("status", "pending")
        if org_id:
            query = query.eq("org_id", org_id)
        result = query.execute()
        return result.count or 0
    except Exception:
        return 0

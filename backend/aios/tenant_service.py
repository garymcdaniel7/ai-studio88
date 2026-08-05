"""AIOS Tenant Service — Story 030.

Tenant-scoped service layer for ALL AIOS operations.
Every function requires TenantContext and enforces workspace ownership.

This module is the ONLY approved way to perform AIOS data operations
from route handlers. Direct repository/queue calls bypass authorization.

Operations:
  Sessions: create, get, list, delete
  Messages: add (via session ownership)
  Decisions: log, list, stats
  Approvals: list, count, approve, reject (with actor attribution)
"""

from __future__ import annotations

import logging
from typing import Any

from backend.membership import OrgRole, TenantContext

logger = logging.getLogger(__name__)


# =============================================================================
# Errors
# =============================================================================


class AiosNotFoundError(Exception):
    """Resource not found within tenant scope (same for cross-tenant — no leak)."""

    def __init__(self, resource: str, resource_id: str) -> None:
        self.resource = resource
        self.resource_id = resource_id
        super().__init__(f"{resource} not found: {resource_id}")


class AiosAuthorizationError(Exception):
    """Actor lacks permission for this AIOS operation."""

    def __init__(self, action: str, role: str) -> None:
        self.action = action
        self.role = role
        super().__init__(f"Unauthorized: {action} requires admin/owner role. You have: {role}")


# =============================================================================
# Sessions (tenant-scoped)
# =============================================================================


def create_session(
    ctx: TenantContext,
    mode: str = "creative",
    talent_id: str | None = None,
    project_id: str | None = None,
) -> dict:
    """Create an AIOS session with trusted workspace and actor context."""
    from backend.aios.sessions import create_session as _create

    return _create(
        org_id=ctx.org_id,
        user_id=ctx.user_id,
        mode=mode,
        talent_id=talent_id,
        project_id=project_id,
    )


def get_session(ctx: TenantContext, session_id: str) -> dict:
    """Get an AIOS session, scoped to workspace.

    Raises AiosNotFoundError for both not-found and cross-tenant.
    """
    from backend.aios.sessions import get_session as _get

    session = _get(session_id, org_id=ctx.org_id)
    if not session:
        raise AiosNotFoundError("session", session_id)
    return session


def list_sessions(ctx: TenantContext, limit: int = 20) -> list[dict]:
    """List AIOS sessions for the authenticated workspace."""
    from backend.aios.sessions import list_sessions as _list

    return _list(org_id=ctx.org_id, limit=limit)


def delete_session(ctx: TenantContext, session_id: str) -> bool:
    """Delete an AIOS session, scoped to workspace."""
    from backend.aios.sessions import delete_session as _delete

    result = _delete(session_id, org_id=ctx.org_id)
    if not result:
        raise AiosNotFoundError("session", session_id)
    return True


# =============================================================================
# Messages (tenant-scoped via session ownership)
# =============================================================================


def add_message(ctx: TenantContext, session_id: str, role: str, content: str) -> dict:
    """Add a message to a session owned by this workspace."""
    from backend.aios.sessions import add_message as _add

    return _add(session_id, org_id=ctx.org_id, role=role, content=content)


# =============================================================================
# Decisions (tenant-scoped)
# =============================================================================


def log_decision(
    ctx: TenantContext,
    session_id: str,
    decision_type: str,
    provider: str,
    model: str,
    **kwargs: Any,
) -> dict:
    """Log an AI decision with trusted workspace and actor attribution."""
    from backend.aios.decisions import log_decision as _log

    return _log(
        org_id=ctx.org_id,
        session_id=session_id,
        decision_type=decision_type,
        provider=provider,
        model=model,
        user_id=ctx.user_id,
        **kwargs,
    )


def list_decisions(
    ctx: TenantContext,
    session_id: str | None = None,
    limit: int = 50,
    provider: str | None = None,
) -> list[dict]:
    """List decisions for the authenticated workspace."""
    from backend.aios.decisions import list_decisions as _list

    return _list(org_id=ctx.org_id, session_id=session_id, limit=limit, provider=provider)


def get_decision_stats(ctx: TenantContext) -> dict:
    """Get decision statistics for the authenticated workspace."""
    from backend.aios.decisions import get_decision_stats as _stats

    return _stats(org_id=ctx.org_id)


# =============================================================================
# Approvals (tenant-scoped with actor attribution)
# =============================================================================


def _db():
    from backend.database import supabase
    return supabase


def list_approvals(
    ctx: TenantContext,
    session_id: str | None = None,
    status: str = "pending",
) -> list[dict]:
    """List approvals scoped to workspace."""
    if not ctx.org_id:
        raise ValueError("org_id is required for tenant-scoped queries")

    try:
        query = (
            _db().table("aios_approvals")
            .select("*")
            .eq("org_id", ctx.org_id)
            .eq("status", status)
            .order("created_at", desc=True)
        )
        if session_id:
            query = query.eq("session_id", session_id)
        return query.execute().data or []
    except Exception:
        return []


def count_approvals(ctx: TenantContext, status: str = "pending") -> int:
    """Count approvals for workspace (for UI badge)."""
    if not ctx.org_id:
        raise ValueError("org_id is required for tenant-scoped queries")

    try:
        result = (
            _db().table("aios_approvals")
            .select("id", count="exact")
            .eq("org_id", ctx.org_id)
            .eq("status", status)
            .execute()
        )
        return result.count or 0
    except Exception:
        return 0


def approve_action(ctx: TenantContext, approval_id: str) -> dict:
    """Approve a pending action with actor attribution.

    Requirements:
    - Approval must belong to the authenticated workspace
    - Actor must have editor+ role (can trigger actions)
    - Actor identity is recorded

    Raises:
        AiosNotFoundError: Approval not found or belongs to another workspace.
        AiosAuthorizationError: Actor lacks sufficient role.
    """
    # Verify role (editor+ can approve since they can trigger actions)
    if not ctx.is_editor_or_above:
        raise AiosAuthorizationError("approve", ctx.role.value)

    # Fetch approval scoped to workspace (cross-tenant = not found)
    try:
        result = (
            _db().table("aios_approvals")
            .select("*")
            .eq("id", approval_id)
            .eq("org_id", ctx.org_id)
            .eq("status", "pending")
            .execute()
        )
        if not result.data:
            raise AiosNotFoundError("approval", approval_id)
    except AiosNotFoundError:
        raise
    except Exception:
        raise AiosNotFoundError("approval", approval_id)

    # Update with actor attribution
    try:
        update_result = (
            _db().table("aios_approvals")
            .update({
                "status": "approved",
                "decided_at": "now()",
                "decided_by": ctx.user_id,
            })
            .eq("id", approval_id)
            .eq("org_id", ctx.org_id)
            .eq("status", "pending")  # Optimistic lock — prevent double-approve
            .execute()
        )
        if not update_result.data:
            raise AiosNotFoundError("approval", approval_id)
        return update_result.data[0]
    except AiosNotFoundError:
        raise
    except Exception as e:
        logger.warning(f"Failed to approve {approval_id}: {e}")
        raise AiosNotFoundError("approval", approval_id)


def reject_action(ctx: TenantContext, approval_id: str, reason: str = "") -> dict:
    """Reject a pending action with actor attribution.

    Same ownership and role requirements as approve.
    """
    if not ctx.is_editor_or_above:
        raise AiosAuthorizationError("reject", ctx.role.value)

    # Fetch scoped to workspace
    try:
        result = (
            _db().table("aios_approvals")
            .select("*")
            .eq("id", approval_id)
            .eq("org_id", ctx.org_id)
            .eq("status", "pending")
            .execute()
        )
        if not result.data:
            raise AiosNotFoundError("approval", approval_id)
    except AiosNotFoundError:
        raise
    except Exception:
        raise AiosNotFoundError("approval", approval_id)

    # Update with actor attribution
    try:
        update_result = (
            _db().table("aios_approvals")
            .update({
                "status": "rejected",
                "rejection_reason": reason,
                "decided_at": "now()",
                "decided_by": ctx.user_id,
            })
            .eq("id", approval_id)
            .eq("org_id", ctx.org_id)
            .eq("status", "pending")
            .execute()
        )
        if not update_result.data:
            raise AiosNotFoundError("approval", approval_id)
        return update_result.data[0]
    except AiosNotFoundError:
        raise
    except Exception as e:
        logger.warning(f"Failed to reject {approval_id}: {e}")
        raise AiosNotFoundError("approval", approval_id)


def enqueue_approval(
    ctx: TenantContext,
    session_id: str,
    tool: str,
    parameters: dict,
    reasoning: str,
    estimated_cost_usd: float = 0.0,
    estimated_time_seconds: float = 0.0,
    agent: str = "",
) -> dict:
    """Enqueue an approval with workspace ownership and actor context."""
    from backend.aios.governance.queue import enqueue_approval as _enqueue

    return _enqueue(
        session_id=session_id,
        tool=tool,
        parameters=parameters,
        reasoning=reasoning,
        estimated_cost_usd=estimated_cost_usd,
        estimated_time_seconds=estimated_time_seconds,
        agent=agent,
        org_id=ctx.org_id,
    )

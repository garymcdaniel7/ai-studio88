"""Infrastructure Authorization — Capability-based access control.

Defines explicit capabilities for infrastructure operations and provides
FastAPI dependencies that enforce role requirements before endpoint execution.

Capability tiers:
    INFRA_READ       — View status, dashboards, cost summaries (viewer+)
    INFRA_OPERATE    — Toggle services, submit fleet jobs (editor+)
    INFRA_ADMIN      — Launch/stop/terminate workers, modify fleet, blacklist (admin+)
    INFRA_DESTRUCTIVE— Emergency shutdown, API key management, session persist (owner)

Each endpoint is mapped to exactly one capability. The dependency checks
the caller's resolved membership role against the required tier.
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from fastapi import Depends, HTTPException, Request, status

from backend.auth import AuthUser, require_auth
from backend.membership import MembershipError, OrgRole, TenantContext, resolve_membership

logger = logging.getLogger(__name__)


# =============================================================================
# Capability Enum
# =============================================================================


class InfraCapability(str, enum.Enum):
    """Infrastructure operation capability levels."""

    READ = "infra:read"
    OPERATE = "infra:operate"
    ADMIN = "infra:admin"
    DESTRUCTIVE = "infra:destructive"


# Minimum role required for each capability tier
CAPABILITY_ROLE_MAP: dict[InfraCapability, OrgRole] = {
    InfraCapability.READ: OrgRole.VIEWER,
    InfraCapability.OPERATE: OrgRole.EDITOR,
    InfraCapability.ADMIN: OrgRole.ADMIN,
    InfraCapability.DESTRUCTIVE: OrgRole.OWNER,
}


# =============================================================================
# Endpoint → Capability Matrix
# =============================================================================

# Maps route operation_id (function name) to its required capability.
# This is the single source of truth for authorization policy.
ENDPOINT_CAPABILITIES: dict[str, InfraCapability] = {
    # --- READ (viewer+) ---
    "get_status": InfraCapability.READ,
    "get_worker_progress": InfraCapability.READ,
    "get_dashboard": InfraCapability.READ,
    "get_connection_history": InfraCapability.READ,
    "get_cost_summary": InfraCapability.READ,
    "get_cost_history": InfraCapability.READ,
    "get_cost_hourly_breakdown": InfraCapability.READ,
    "get_job_costs": InfraCapability.READ,
    "get_reputation": InfraCapability.READ,
    "compare_providers": InfraCapability.READ,
    "get_blacklist": InfraCapability.READ,
    "get_fleet_status": InfraCapability.READ,
    "get_known_issues": InfraCapability.READ,
    "get_services_status": InfraCapability.READ,
    "get_service_settings": InfraCapability.READ,
    "check_service_health": InfraCapability.READ,
    "get_vast_connection_status": InfraCapability.READ,
    "get_runpod_connection_status": InfraCapability.READ,
    "get_all_gpu_provider_status": InfraCapability.READ,
    "stream_progress": InfraCapability.READ,
    "get_fleet_config": InfraCapability.READ,
    "get_fleet_budget": InfraCapability.READ,
    "check_budget_guard": InfraCapability.READ,
    "check_can_launch": InfraCapability.READ,
    "list_all_workers": InfraCapability.READ,
    "get_idle_workers": InfraCapability.READ,
    "get_gpu_requirements": InfraCapability.READ,
    "get_ollama_preference": InfraCapability.READ,
    "get_ollama_status": InfraCapability.READ,
    "dispatch_due_posts": InfraCapability.READ,
    "check_all_connections": InfraCapability.READ,
    # --- OPERATE (editor+) ---
    "toggle_service": InfraCapability.OPERATE,
    "submit_fleet_job": InfraCapability.OPERATE,
    "diagnose_error": InfraCapability.OPERATE,
    "trigger_auto_provision": InfraCapability.OPERATE,
    "set_ollama_preference": InfraCapability.OPERATE,
    "setup_service_on_worker": InfraCapability.OPERATE,
    # --- ADMIN (admin+) ---
    "launch_worker": InfraCapability.ADMIN,
    "stop_worker": InfraCapability.ADMIN,
    "pause_worker": InfraCapability.ADMIN,
    "resume_worker": InfraCapability.ADMIN,
    "add_to_blacklist": InfraCapability.ADMIN,
    "add_fleet_worker": InfraCapability.ADMIN,
    "remove_fleet_worker": InfraCapability.ADMIN,
    "stop_single_worker": InfraCapability.ADMIN,
    "pause_single_worker": InfraCapability.ADMIN,
    "resume_single_worker": InfraCapability.ADMIN,
    "shutdown_idle_workers": InfraCapability.ADMIN,
    "update_fleet_config": InfraCapability.ADMIN,
    "record_fleet_spend": InfraCapability.ADMIN,
    "persist_worker_session": InfraCapability.ADMIN,
    # --- DESTRUCTIVE (owner only) ---
    "stop_fleet": InfraCapability.DESTRUCTIVE,
    "save_api_keys": InfraCapability.DESTRUCTIVE,
}


# =============================================================================
# Audit Event
# =============================================================================


@dataclass
class InfraAuditEvent:
    """Structured audit record for infrastructure operations."""

    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    actor_id: str = ""
    actor_email: str | None = None
    org_id: str | None = None
    role: str = ""
    action: str = ""
    capability: str = ""
    resource_type: str | None = None
    resource_id: str | None = None
    request_data: dict[str, Any] = field(default_factory=dict)
    result: str = "success"  # success | denied | error
    denial_reason: str | None = None
    requires_approval: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize for logging and persistence."""
        return {k: v for k, v in self.__dict__.items() if v is not None and v != ""}


# In-memory audit log for the current process (persisted to Supabase when available)
_audit_log: list[InfraAuditEvent] = []

# Maximum in-memory audit entries before oldest are discarded
_MAX_AUDIT_LOG = 500


def emit_audit_event(event: InfraAuditEvent) -> None:
    """Record an audit event to the in-memory log and structured logger.

    In production, this also persists to the infra_audit_log table.
    """
    _audit_log.append(event)
    if len(_audit_log) > _MAX_AUDIT_LOG:
        _audit_log.pop(0)

    logger.info(
        "infra_audit",
        extra=event.to_dict(),
    )

    # Attempt async persistence to Supabase (non-blocking, best-effort)
    _persist_audit_event(event)


def _persist_audit_event(event: InfraAuditEvent) -> None:
    """Best-effort persist audit event to Supabase."""
    try:
        from backend.database import is_supabase_configured

        if not is_supabase_configured():
            return

        from backend.database import get_supabase_client

        client = get_supabase_client()
        client.table("infra_audit_log").insert(event.to_dict()).execute()
    except Exception:
        pass  # Audit persistence is non-critical


def get_audit_log(limit: int = 100) -> list[dict[str, Any]]:
    """Return recent audit events (most recent first)."""
    return [e.to_dict() for e in reversed(_audit_log[-limit:])]


# =============================================================================
# Approval Integration
# =============================================================================

# Operations that require approval before execution.
# These produce an "approval_required" response instead of executing directly.
APPROVAL_REQUIRED_ACTIONS: set[str] = {
    "stop_fleet",
    "save_api_keys",
}


@dataclass
class ApprovalCommand:
    """A pending command that requires explicit approval before execution."""

    action: str
    actor_id: str
    org_id: str | None
    request_data: dict[str, Any]
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    expires_at: str | None = None  # ISO format; None = no expiry
    approved: bool = False
    approval_token: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


def create_approval_command(
    action: str,
    actor_id: str,
    org_id: str | None,
    request_data: dict[str, Any],
    ttl_seconds: int = 300,
) -> ApprovalCommand:
    """Create an approval-ready command that must be confirmed before execution."""
    import secrets

    expires_at = datetime.now(UTC).isoformat()  # placeholder
    try:
        from datetime import timedelta

        expires_at = (datetime.now(UTC) + timedelta(seconds=ttl_seconds)).isoformat()
    except Exception:
        pass

    return ApprovalCommand(
        action=action,
        actor_id=actor_id,
        org_id=org_id,
        request_data=request_data,
        expires_at=expires_at,
        approval_token=secrets.token_urlsafe(24),
    )


# =============================================================================
# FastAPI Dependencies
# =============================================================================


def _resolve_tenant_context(user: AuthUser) -> TenantContext:
    """Resolve full TenantContext from AuthUser.

    In dev mode with org_id=None, creates a dev TenantContext with owner role.
    In production, resolves from org_members table.
    """
    # Dev mode fallback — AuthUser already has role resolved
    if user.org_id is None and user.user_id == "dev-user-local":
        return TenantContext(
            user_id=user.user_id,
            org_id="dev-org-local",
            role=OrgRole.OWNER,
            email=user.email,
        )

    if not user.org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No workspace membership resolved. Cannot access infrastructure.",
        )

    # Map the AuthUser.role string to OrgRole enum
    try:
        role = OrgRole(user.role)
    except ValueError:
        role = OrgRole.VIEWER  # Unknown role → lowest privilege

    return TenantContext(
        user_id=user.user_id,
        org_id=user.org_id,
        role=role,
        email=user.email,
    )


def require_infra_capability(capability: InfraCapability):
    """Factory that returns a FastAPI dependency enforcing the given capability.

    Usage:
        @router.post("/launch")
        def launch_worker(
            ctx: TenantContext = Depends(require_infra_capability(InfraCapability.ADMIN)),
        ):
            ...
    """

    def _dependency(user: AuthUser = Depends(require_auth)) -> TenantContext:
        ctx = _resolve_tenant_context(user)
        required_role = CAPABILITY_ROLE_MAP[capability]

        if not ctx.role.has_privilege(required_role):
            # Emit denial audit event
            emit_audit_event(InfraAuditEvent(
                actor_id=ctx.user_id,
                actor_email=ctx.email,
                org_id=ctx.org_id,
                role=ctx.role.value,
                action="authorization_check",
                capability=capability.value,
                result="denied",
                denial_reason=(
                    f"Requires {required_role.value} role. User has {ctx.role.value}."
                ),
            ))

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Insufficient permissions. "
                    f"This action requires '{required_role.value}' role or higher. "
                    f"Your current role: '{ctx.role.value}'."
                ),
            )

        return ctx

    return _dependency


def require_infra_read(user: AuthUser = Depends(require_auth)) -> TenantContext:
    """Dependency: requires viewer+ role (read-only infrastructure access)."""
    return require_infra_capability(InfraCapability.READ)(user)


def require_infra_operate(user: AuthUser = Depends(require_auth)) -> TenantContext:
    """Dependency: requires editor+ role (operational actions)."""
    return require_infra_capability(InfraCapability.OPERATE)(user)


def require_infra_admin(user: AuthUser = Depends(require_auth)) -> TenantContext:
    """Dependency: requires admin+ role (spend-changing / worker lifecycle)."""
    return require_infra_capability(InfraCapability.ADMIN)(user)


def require_infra_destructive(user: AuthUser = Depends(require_auth)) -> TenantContext:
    """Dependency: requires owner role (emergency/destructive operations)."""
    return require_infra_capability(InfraCapability.DESTRUCTIVE)(user)


# =============================================================================
# Workspace Ownership Verification
# =============================================================================


def verify_resource_ownership(
    ctx: TenantContext,
    resource_org_id: str | None,
    resource_type: str,
    resource_id: str,
) -> None:
    """Verify that a resource belongs to the caller's workspace.

    Raises 404 (not 403) to avoid leaking resource existence to other tenants.
    """
    if resource_org_id is None:
        # Resource has no org_id — allow (shared/system resource)
        return

    if ctx.org_id == "dev-org-local":
        # Dev mode — skip ownership check
        return

    if resource_org_id != ctx.org_id:
        logger.warning(
            "cross_tenant_access_attempt",
            extra={
                "actor_id": ctx.user_id,
                "actor_org": ctx.org_id,
                "resource_org": resource_org_id,
                "resource_type": resource_type,
                "resource_id": resource_id,
            },
        )
        emit_audit_event(InfraAuditEvent(
            actor_id=ctx.user_id,
            actor_email=ctx.email,
            org_id=ctx.org_id,
            role=ctx.role.value,
            action="cross_tenant_access",
            resource_type=resource_type,
            resource_id=resource_id,
            result="denied",
            denial_reason=f"Resource belongs to org {resource_org_id}, not {ctx.org_id}",
        ))
        # Return 404 to avoid leaking that the resource exists
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{resource_type} not found.",
        )


# =============================================================================
# Per-Org Rate Limiting for Spend-Changing Operations
# =============================================================================

import time
from collections import defaultdict

# Rate limit config: max N spend-changing requests per org per window
_RATE_LIMIT_MAX = 10  # max requests per window
_RATE_LIMIT_WINDOW = 60  # seconds

# In-memory store: org_id → list of timestamps
_org_rate_limits: dict[str, list[float]] = defaultdict(list)


def check_spend_rate_limit(org_id: str) -> tuple[bool, str]:
    """Check if an org has exceeded its spend-changing rate limit.

    Returns (allowed, reason). If allowed is False, the request should be rejected.
    """
    if not org_id or org_id == "dev-org-local":
        return True, ""

    now = time.time()
    window_start = now - _RATE_LIMIT_WINDOW

    # Clean expired entries
    _org_rate_limits[org_id] = [
        t for t in _org_rate_limits[org_id] if t > window_start
    ]

    if len(_org_rate_limits[org_id]) >= _RATE_LIMIT_MAX:
        return False, (
            f"Rate limit exceeded: max {_RATE_LIMIT_MAX} spend-changing operations "
            f"per {_RATE_LIMIT_WINDOW}s per workspace. Try again shortly."
        )

    _org_rate_limits[org_id].append(now)
    return True, ""


def require_spend_rate_limit(ctx: TenantContext) -> None:
    """Enforce per-org rate limiting on spend-changing operations.

    Call this at the top of admin-tier endpoints that incur costs.
    Raises 429 if the org has exceeded its rate limit.
    """
    allowed, reason = check_spend_rate_limit(ctx.org_id or "")
    if not allowed:
        emit_audit_event(InfraAuditEvent(
            actor_id=ctx.user_id,
            actor_email=ctx.email,
            org_id=ctx.org_id,
            role=ctx.role.value,
            action="rate_limit_exceeded",
            capability=InfraCapability.ADMIN.value,
            result="denied",
            denial_reason=reason,
        ))
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=reason,
        )

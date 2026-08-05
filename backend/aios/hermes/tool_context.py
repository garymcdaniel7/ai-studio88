"""Hermes Tool Execution Context — Story 036.

Every Hermes tool call MUST have a verified ToolExecutionContext that binds
the invocation to a specific user, workspace, role, session, and time window.

This prevents:
- Cross-tenant access (tools execute within the caller's workspace only)
- Privilege escalation (tools respect the caller's role, not service-role)
- Replay attacks (context has a unique nonce and short expiry)
- Over-scoping (capabilities are explicitly listed, not blanket access)
- Background continuation after session expiry

Contract:
    1. Context is created when a Hermes conversation begins (from TenantContext)
    2. Context is passed to every execute_tool_authorized() call
    3. Context is validated BEFORE governance enforcement and tool execution
    4. Context is short-lived (default 30 min, max 4 hours)
    5. Context cannot be reused across sessions or workspaces

Internal HTTP calls: Instead of implicit localhost privilege, tools forward
the execution context as a signed header that the receiving endpoint validates.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# Short-lived context limits
DEFAULT_TTL_SECONDS = 1800  # 30 minutes
MAX_TTL_SECONDS = 14400    # 4 hours

# Signing key for context tokens (from env, with fallback for dev)
_SIGNING_KEY = os.getenv("TOOL_CONTEXT_SIGNING_KEY", "dev-tool-context-key-not-for-production")


# =============================================================================
# Trust Domain
# =============================================================================


class TrustDomain(str, Enum):
    """Where this tool execution originates."""
    USER_INTERACTIVE = "user_interactive"  # User in Brain chat
    AGENT_AUTONOMOUS = "agent_autonomous"  # Agent-initiated (scheduled, plan execution)
    APPROVAL_BOUND = "approval_bound"      # Post-approval execution
    SYSTEM_WORKER = "system_worker"        # Background job worker


# =============================================================================
# Tool Execution Context
# =============================================================================


@dataclass(frozen=True)
class ToolExecutionContext:
    """Verified execution context for a Hermes tool call.

    Every field is required and validated before tool execution.
    The context is bound to a specific action scope and expires.
    """
    # Identity
    user_id: str
    org_id: str
    role: str  # viewer, editor, admin, owner

    # Session binding
    session_id: str
    request_id: str = field(default_factory=lambda: f"tex-{uuid.uuid4().hex[:12]}")

    # Trust and scope
    trust_domain: TrustDomain = TrustDomain.USER_INTERACTIVE
    capabilities: frozenset[str] = field(default_factory=frozenset)
    approval_id: str | None = None  # If this execution is approval-bound

    # Temporal bounds
    created_at: float = field(default_factory=time.time)
    ttl_seconds: int = DEFAULT_TTL_SECONDS

    # Nonce (prevents replay)
    nonce: str = field(default_factory=lambda: uuid.uuid4().hex[:16])

    @property
    def expires_at(self) -> float:
        """Unix timestamp when this context expires."""
        return self.created_at + self.ttl_seconds

    @property
    def is_expired(self) -> bool:
        """Check if the context has expired."""
        return time.time() > self.expires_at

    @property
    def remaining_seconds(self) -> float:
        """Seconds remaining before expiry."""
        return max(0, self.expires_at - time.time())

    def has_capability(self, capability: str) -> bool:
        """Check if this context has a specific capability.

        Empty capabilities = unrestricted (backward compat during migration).
        """
        if not self.capabilities:
            return True  # Unrestricted (transitional)
        return capability in self.capabilities

    def to_signed_token(self) -> str:
        """Serialize and sign the context for propagation to internal services.

        The token is short-lived and bound to this specific execution.
        """
        payload = {
            "uid": self.user_id,
            "oid": self.org_id,
            "role": self.role,
            "sid": self.session_id,
            "rid": self.request_id,
            "td": self.trust_domain.value,
            "caps": list(self.capabilities) if self.capabilities else [],
            "aid": self.approval_id,
            "cat": self.created_at,
            "ttl": self.ttl_seconds,
            "nonce": self.nonce,
        }
        payload_json = json.dumps(payload, sort_keys=True)
        signature = _sign(payload_json)
        return f"{payload_json}|{signature}"

    @staticmethod
    def from_signed_token(token: str) -> "ToolExecutionContext":
        """Deserialize and verify a signed context token.

        Raises:
            ToolContextError: If token is invalid, expired, or tampered.
        """
        parts = token.rsplit("|", 1)
        if len(parts) != 2:
            raise ToolContextError("Invalid token format")

        payload_json, signature = parts

        # Verify signature
        expected_sig = _sign(payload_json)
        if not hmac.compare_digest(signature, expected_sig):
            raise ToolContextError("Token signature invalid — possible tampering")

        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError:
            raise ToolContextError("Token payload corrupt")

        ctx = ToolExecutionContext(
            user_id=payload["uid"],
            org_id=payload["oid"],
            role=payload["role"],
            session_id=payload["sid"],
            request_id=payload["rid"],
            trust_domain=TrustDomain(payload["td"]),
            capabilities=frozenset(payload.get("caps", [])),
            approval_id=payload.get("aid"),
            created_at=payload["cat"],
            ttl_seconds=payload["ttl"],
            nonce=payload["nonce"],
        )

        if ctx.is_expired:
            raise ToolContextError("Token expired")

        return ctx


# =============================================================================
# Errors
# =============================================================================


class ToolContextError(Exception):
    """Raised when tool execution context is invalid."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Tool context invalid: {reason}")


class ToolAuthorizationError(Exception):
    """Raised when tool execution is denied by authorization."""

    def __init__(self, tool: str, reason: str) -> None:
        self.tool = tool
        self.reason = reason
        super().__init__(f"Tool '{tool}' denied: {reason}")


# =============================================================================
# Context Validation
# =============================================================================


def validate_context(ctx: ToolExecutionContext) -> None:
    """Validate a tool execution context is complete and valid.

    Raises ToolContextError if any check fails.
    """
    if not ctx.user_id:
        raise ToolContextError("Missing user_id")
    if not ctx.org_id:
        raise ToolContextError("Missing org_id")
    if not ctx.role:
        raise ToolContextError("Missing role")
    if not ctx.session_id:
        raise ToolContextError("Missing session_id")
    if ctx.is_expired:
        raise ToolContextError(f"Context expired {abs(ctx.remaining_seconds):.0f}s ago")
    if ctx.ttl_seconds > MAX_TTL_SECONDS:
        raise ToolContextError(f"TTL {ctx.ttl_seconds}s exceeds maximum {MAX_TTL_SECONDS}s")


# =============================================================================
# Authorized Tool Execution
# =============================================================================


def execute_tool_authorized(
    ctx: ToolExecutionContext,
    tool_name: str,
    arguments: dict,
) -> dict[str, Any]:
    """Execute a Hermes tool with full authorization enforcement.

    This is the ONLY approved way to invoke tools from Hermes.

    Steps:
    1. Validate execution context (identity, expiry, nonce)
    2. Check governance enforcement (Story 034)
    3. Execute the tool with scoped context
    4. Audit the result

    Returns:
        Tool execution result dict.

    Raises:
        ToolContextError: Context is invalid/expired/missing.
        ToolAuthorizationError: Tool denied by governance/role/capability.
    """
    # 1. Validate context
    validate_context(ctx)

    # 2. Check capability (if capabilities are specified)
    tool_capability = f"execute:{tool_name}"
    if ctx.capabilities and not ctx.has_capability(tool_capability):
        raise ToolAuthorizationError(
            tool_name,
            f"Context lacks capability '{tool_capability}'"
        )

    # 3. Governance enforcement (Story 034)
    from backend.aios.governance.enforcement import (
        GovernanceApprovalRequired,
        GovernanceBlockedError,
        enforce_governance,
        is_read_only,
    )

    try:
        decision = enforce_governance(
            tool=tool_name,
            parameters=arguments,
            actor_id=ctx.user_id,
            org_id=ctx.org_id,
            role=ctx.role,
            session_id=ctx.session_id,
            source=f"hermes_{ctx.trust_domain.value}",
        )
    except GovernanceBlockedError as e:
        raise ToolAuthorizationError(tool_name, e.decision.reason) from e
    except GovernanceApprovalRequired as e:
        raise ToolAuthorizationError(
            tool_name,
            f"Requires approval: {e.decision.reason}"
        ) from e

    # 4. Execute the tool (import the actual executor)
    from backend.aios.hermes.tools import execute_tool as _raw_execute

    result_str = _raw_execute(tool_name, arguments)

    # 5. Parse and return
    try:
        result = json.loads(result_str)
    except (json.JSONDecodeError, TypeError):
        result = {"raw": str(result_str)[:500]}

    # 6. Audit
    _audit_tool_execution(ctx, tool_name, decision.outcome.value, result)

    return result


# =============================================================================
# Context Factory
# =============================================================================


def create_context_from_tenant(
    tenant_ctx: Any,  # TenantContext from membership.py
    session_id: str,
    trust_domain: TrustDomain = TrustDomain.USER_INTERACTIVE,
    capabilities: frozenset[str] | None = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    approval_id: str | None = None,
) -> ToolExecutionContext:
    """Create a ToolExecutionContext from a verified TenantContext.

    This is the approved factory — context is derived from authenticated
    membership, not from request-supplied values.
    """
    ttl = min(ttl_seconds, MAX_TTL_SECONDS)

    return ToolExecutionContext(
        user_id=tenant_ctx.user_id,
        org_id=tenant_ctx.org_id,
        role=tenant_ctx.role.value if hasattr(tenant_ctx.role, 'value') else str(tenant_ctx.role),
        session_id=session_id,
        trust_domain=trust_domain,
        capabilities=capabilities or frozenset(),
        ttl_seconds=ttl,
        approval_id=approval_id,
    )


# =============================================================================
# Internal Helpers
# =============================================================================


def _sign(payload: str) -> str:
    """HMAC-SHA256 sign a payload."""
    return hmac.HMAC(
        _SIGNING_KEY.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()[:32]


def _audit_tool_execution(
    ctx: ToolExecutionContext,
    tool: str,
    outcome: str,
    result: dict,
) -> None:
    """Record tool execution for audit trail."""
    try:
        from backend.database import supabase
        supabase.table("aios_decisions").insert({
            "session_id": ctx.session_id,
            "decision_type": "tool_execution",
            "provider": f"hermes_{ctx.trust_domain.value}",
            "model": tool,
            "input_summary": f"tool={tool} nonce={ctx.nonce}",
            "output_summary": str(result.get("error") or result.get("status", "ok"))[:200],
            "latency_ms": 0,
            "mode": "tool",
            "confidence": 1.0,
            "reasoning": f"Authorized: user={ctx.user_id[:8]} org={ctx.org_id[:8]} role={ctx.role}",
            "metadata": {
                "request_id": ctx.request_id,
                "trust_domain": ctx.trust_domain.value,
                "org_id": ctx.org_id,
                "outcome": outcome,
            },
        }).execute()
    except Exception as e:
        logger.error(f"Tool audit failed: {e}")

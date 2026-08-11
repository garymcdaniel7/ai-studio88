"""Trust Domain Model and Enforcement — R57.

Implements the canonical 6-tier trust domain hierarchy per Requirement 57:
  FOUNDER_PRIVATE > PLATFORM_ADMIN > WORKSPACE_ADMIN > CUSTOMER_USER > SERVICE_WORKER > SYSTEM_AUTOMATION

Each domain resolves to separately authorized:
  - Knowledge sources (what information is accessible)
  - Memory scopes (what memory can be read/written)
  - System instructions (what prompts/context are injected)
  - Tools (what actions can be invoked)
  - Credentials (what secrets are available)
  - Approval capabilities (what can be approved/rejected)

Security invariants:
  - FOUNDER_PRIVATE content NEVER visible in CUSTOMER_USER or below sessions (R57.3)
  - PLATFORM_ADMIN content NOT accessible to CUSTOMER_USER or SERVICE_WORKER (R57.4)
  - Filtering is enforced server-side at retrieval time (R57.5)
  - Domain is resolved from validated JWT — client cannot influence (R57.1)
  - Cross-domain boundary violations are logged as P0 incidents (R57.7)

Validates: Requirements R57.1, R57.2, R57.3, R57.4, R57.5
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import IntEnum
from typing import Any, Protocol, Sequence


# =============================================================================
# Trust Domain Enum with Hierarchy
# =============================================================================


class TrustDomain(IntEnum):
    """Trust domains ordered by privilege level (higher = more access).

    The numeric value encodes the hierarchy: a domain can access content
    at its own level or below, but NEVER above.

    Domains per R57.1:
      FOUNDER_PRIVATE    — Executive strategy, internal runbooks, infrastructure secrets
      PLATFORM_ADMIN     — System configuration, cross-tenant views, operational tooling
      WORKSPACE_ADMIN    — Workspace settings, team management, billing
      CUSTOMER_USER      — Creative work, generation, training, publishing
      SERVICE_WORKER     — Job execution, result upload, health reporting
      SYSTEM_AUTOMATION  — Scheduled tasks, maintenance, monitoring
    """

    SYSTEM_AUTOMATION = 1
    SERVICE_WORKER = 2
    CUSTOMER_USER = 3
    WORKSPACE_ADMIN = 4
    PLATFORM_ADMIN = 5
    FOUNDER_PRIVATE = 6


# =============================================================================
# Trust Domain Capabilities
# =============================================================================


@dataclass(frozen=True)
class TrustDomainCapabilities:
    """Capabilities associated with a trust domain per R57.2.

    Each domain resolves to separately authorized sets of:
      - knowledge_sources: What information stores are accessible
      - memory_scopes: What memory namespaces can be read/written
      - system_instructions: What prompts/context are injected
      - tools: What actions can be invoked
      - credentials: What credential types are available
      - approval_capabilities: What actions can be approved/rejected
    """

    domain: TrustDomain
    knowledge_sources: frozenset[str]
    memory_scopes: frozenset[str]
    system_instructions: frozenset[str]
    tools: frozenset[str]
    credentials: frozenset[str]
    approval_capabilities: frozenset[str]


# =============================================================================
# Domain Capabilities Registry
# =============================================================================

DOMAIN_CAPABILITIES: dict[TrustDomain, TrustDomainCapabilities] = {
    TrustDomain.FOUNDER_PRIVATE: TrustDomainCapabilities(
        domain=TrustDomain.FOUNDER_PRIVATE,
        knowledge_sources=frozenset({
            "founder_private", "platform_internal", "workspace_shared",
            "customer_creative", "service_operational", "system_logs",
        }),
        memory_scopes=frozenset({
            "founder", "platform", "workspace", "user", "service", "system",
        }),
        system_instructions=frozenset({
            "founder_ops", "platform_admin", "workspace_admin",
            "creative", "infrastructure", "diagnostics",
        }),
        tools=frozenset({
            "generate_image", "generate_video", "train_lora", "search_talent",
            "get_talent_knowledge", "check_platform_health", "auto_configure_generation",
            "search_knowledge_graph", "get_fleet_status", "diagnose_service",
            "generate_voice", "schedule_post", "run_uat_tests", "get_uat_results",
            "launch_gpu", "stop_gpu", "manage_credentials", "view_costs",
            "manage_governance", "deploy_model", "destroy_worker",
            "manage_platform_config", "view_cross_tenant", "manage_operators",
        }),
        credentials=frozenset({
            "supabase_service_role", "b2_admin", "vast_api", "runpod_api",
            "openai_api", "anthropic_api", "elevenlabs_api", "platform_secrets",
        }),
        approval_capabilities=frozenset({
            "approve_deployments", "approve_governance_changes",
            "approve_destructive_actions", "approve_cost_overrides",
            "approve_cross_tenant_access", "approve_operator_grants",
        }),
    ),

    TrustDomain.PLATFORM_ADMIN: TrustDomainCapabilities(
        domain=TrustDomain.PLATFORM_ADMIN,
        knowledge_sources=frozenset({
            "platform_internal", "workspace_shared",
            "customer_creative", "service_operational", "system_logs",
        }),
        memory_scopes=frozenset({
            "platform", "workspace", "user", "service", "system",
        }),
        system_instructions=frozenset({
            "platform_admin", "workspace_admin", "creative",
            "infrastructure", "diagnostics",
        }),
        tools=frozenset({
            "generate_image", "generate_video", "train_lora", "search_talent",
            "get_talent_knowledge", "check_platform_health", "auto_configure_generation",
            "search_knowledge_graph", "get_fleet_status", "diagnose_service",
            "generate_voice", "schedule_post", "run_uat_tests", "get_uat_results",
            "launch_gpu", "stop_gpu", "manage_credentials", "view_costs",
            "manage_platform_config", "view_cross_tenant",
        }),
        credentials=frozenset({
            "b2_admin", "vast_api", "runpod_api",
            "openai_api", "anthropic_api", "elevenlabs_api",
        }),
        approval_capabilities=frozenset({
            "approve_deployments", "approve_governance_changes",
            "approve_cost_overrides",
        }),
    ),

    TrustDomain.WORKSPACE_ADMIN: TrustDomainCapabilities(
        domain=TrustDomain.WORKSPACE_ADMIN,
        knowledge_sources=frozenset({
            "workspace_shared", "customer_creative",
        }),
        memory_scopes=frozenset({
            "workspace", "user",
        }),
        system_instructions=frozenset({
            "workspace_admin", "creative",
        }),
        tools=frozenset({
            "generate_image", "generate_video", "train_lora", "search_talent",
            "get_talent_knowledge", "auto_configure_generation",
            "search_knowledge_graph", "generate_voice", "schedule_post",
            "launch_gpu", "stop_gpu", "manage_credentials", "view_costs",
        }),
        credentials=frozenset({
            "workspace_api_keys", "workspace_connections",
        }),
        approval_capabilities=frozenset({
            "approve_workspace_changes", "approve_team_invites",
            "approve_workspace_costs",
        }),
    ),

    TrustDomain.CUSTOMER_USER: TrustDomainCapabilities(
        domain=TrustDomain.CUSTOMER_USER,
        knowledge_sources=frozenset({
            "customer_creative",
        }),
        memory_scopes=frozenset({
            "workspace", "user",
        }),
        system_instructions=frozenset({
            "creative",
        }),
        tools=frozenset({
            "generate_image", "generate_video", "train_lora", "search_talent",
            "get_talent_knowledge", "auto_configure_generation",
            "search_knowledge_graph", "generate_voice", "schedule_post",
        }),
        credentials=frozenset[str](),
        approval_capabilities=frozenset[str](),
    ),

    TrustDomain.SERVICE_WORKER: TrustDomainCapabilities(
        domain=TrustDomain.SERVICE_WORKER,
        knowledge_sources=frozenset({
            "service_operational",
        }),
        memory_scopes=frozenset({
            "service",
        }),
        system_instructions=frozenset({
            "service_execution",
        }),
        tools=frozenset({
            "check_platform_health", "get_fleet_status",
            "upload_result", "report_status",
        }),
        credentials=frozenset({
            "service_token",
        }),
        approval_capabilities=frozenset[str](),
    ),

    TrustDomain.SYSTEM_AUTOMATION: TrustDomainCapabilities(
        domain=TrustDomain.SYSTEM_AUTOMATION,
        knowledge_sources=frozenset({
            "system_logs",
        }),
        memory_scopes=frozenset({
            "system",
        }),
        system_instructions=frozenset({
            "system_maintenance",
        }),
        tools=frozenset({
            "check_platform_health", "run_maintenance",
            "collect_metrics",
        }),
        credentials=frozenset({
            "system_token",
        }),
        approval_capabilities=frozenset[str](),
    ),
}


# =============================================================================
# Domain Hierarchy Access Control
# =============================================================================


def can_access(requesting_domain: TrustDomain, target_domain: TrustDomain) -> bool:
    """Check if requesting_domain can access content tagged with target_domain.

    Returns True only if the requesting domain's privilege level is >= the
    target domain's level. This enforces the hierarchy:
      FOUNDER_PRIVATE(6) > PLATFORM_ADMIN(5) > WORKSPACE_ADMIN(4)
      > CUSTOMER_USER(3) > SERVICE_WORKER(2) > SYSTEM_AUTOMATION(1)

    Examples:
      can_access(FOUNDER_PRIVATE, CUSTOMER_USER) → True (founder sees all)
      can_access(CUSTOMER_USER, FOUNDER_PRIVATE) → False (NEVER)
      can_access(CUSTOMER_USER, CUSTOMER_USER) → True (same level)
      can_access(PLATFORM_ADMIN, FOUNDER_PRIVATE) → False
    """
    return int(requesting_domain) >= int(target_domain)


# =============================================================================
# Trust Domain Content Filtering
# =============================================================================


class TrustDomainTagged(Protocol):
    """Protocol for items that carry a trust_domain attribute."""

    @property
    def trust_domain(self) -> TrustDomain | str: ...


def _resolve_item_domain(item: Any) -> TrustDomain:
    """Resolve the TrustDomain from an item's trust_domain attribute.

    Handles both TrustDomain enum values and string representations.
    If the value cannot be resolved, returns FOUNDER_PRIVATE (deny by default).
    """
    raw = getattr(item, "trust_domain", None)
    if raw is None:
        # No trust_domain attribute — treat as highest privilege (deny by default)
        return TrustDomain.FOUNDER_PRIVATE

    if isinstance(raw, TrustDomain):
        return raw

    # Try to match string to enum name or value
    if isinstance(raw, str):
        # Try by name (e.g., "FOUNDER_PRIVATE")
        try:
            return TrustDomain[raw.upper()]
        except (KeyError, AttributeError):
            pass
        # Try by value (e.g., "6")
        try:
            return TrustDomain(int(raw))
        except (ValueError, KeyError):
            pass

    # Unresolvable — deny by default
    return TrustDomain.FOUNDER_PRIVATE


def filter_by_trust_domain(
    items: Sequence[Any],
    requesting_domain: TrustDomain,
) -> list[Any]:
    """Filter a list of items by trust domain, excluding items above the requester's level.

    Each item must have a `trust_domain` attribute (str or TrustDomain enum).
    Items with a trust_domain level ABOVE the requesting_domain are excluded.

    This is the primary enforcement point for R57.3/R57.4/R57.5:
      - CUSTOMER_USER requesting → excludes FOUNDER_PRIVATE, PLATFORM_ADMIN, WORKSPACE_ADMIN
      - WORKSPACE_ADMIN requesting → excludes FOUNDER_PRIVATE, PLATFORM_ADMIN
      - PLATFORM_ADMIN requesting → excludes FOUNDER_PRIVATE
      - FOUNDER_PRIVATE requesting → sees everything

    Items without a trust_domain attribute are treated as FOUNDER_PRIVATE (deny by default).
    """
    result: list[Any] = []
    for item in items:
        item_domain = _resolve_item_domain(item)
        if can_access(requesting_domain, item_domain):
            result.append(item)
    return result


# =============================================================================
# Trust Domain Resolution from User Context
# =============================================================================


# Founder user IDs — configured via environment (comma-separated UUIDs)
_FOUNDER_IDS_RAW = os.getenv("FOUNDER_USER_IDS", "")
FOUNDER_USER_IDS: frozenset[str] = frozenset(
    uid.strip() for uid in _FOUNDER_IDS_RAW.split(",") if uid.strip()
)


@dataclass(frozen=True)
class ResolvedTrustContext:
    """The result of trust domain resolution for a request."""

    domain: TrustDomain
    capabilities: TrustDomainCapabilities
    resolution_reason: str
    user_id: str
    org_id: str
    role: str
    is_platform_operator: bool = False


def resolve_trust_domain(
    *,
    user_id: str,
    org_id: str,
    role: str,
    is_platform_operator: bool = False,
    platform_capabilities: frozenset[str] | None = None,
) -> ResolvedTrustContext:
    """Resolve the trust domain from user context per R57.1.

    Server-side only — the client CANNOT influence this decision.
    Uses validated auth identity + membership role + operator status.

    Resolution order:
      1. Founder check (explicit user ID in FOUNDER_USER_IDS env)
      2. Platform operator with capabilities → PLATFORM_ADMIN
      3. Role-based: owner/admin → WORKSPACE_ADMIN
      4. Role-based: editor/viewer → CUSTOMER_USER
      5. Service context (service_worker role) → SERVICE_WORKER
      6. System context (no user_id or system role) → SYSTEM_AUTOMATION
      7. Default → CUSTOMER_USER (deny-by-default for ambiguous cases)
    """
    # 1. System context (no interactive user)
    if not user_id or role == "system":
        return ResolvedTrustContext(
            domain=TrustDomain.SYSTEM_AUTOMATION,
            capabilities=DOMAIN_CAPABILITIES[TrustDomain.SYSTEM_AUTOMATION],
            resolution_reason="no_user_id:system_automation",
            user_id=user_id or "",
            org_id=org_id,
            role=role or "system",
        )

    # 2. Service worker context
    if role == "service_worker":
        return ResolvedTrustContext(
            domain=TrustDomain.SERVICE_WORKER,
            capabilities=DOMAIN_CAPABILITIES[TrustDomain.SERVICE_WORKER],
            resolution_reason="role:service_worker",
            user_id=user_id,
            org_id=org_id,
            role=role,
        )

    # 3. Founder check (explicit user ID match)
    if user_id in FOUNDER_USER_IDS:
        return ResolvedTrustContext(
            domain=TrustDomain.FOUNDER_PRIVATE,
            capabilities=DOMAIN_CAPABILITIES[TrustDomain.FOUNDER_PRIVATE],
            resolution_reason="founder_user_id_match",
            user_id=user_id,
            org_id=org_id,
            role=role,
        )

    # 4. Platform operator (capability-based, per R97)
    if is_platform_operator and platform_capabilities:
        return ResolvedTrustContext(
            domain=TrustDomain.PLATFORM_ADMIN,
            capabilities=DOMAIN_CAPABILITIES[TrustDomain.PLATFORM_ADMIN],
            resolution_reason="platform_operator_with_capabilities",
            user_id=user_id,
            org_id=org_id,
            role=role,
            is_platform_operator=True,
        )

    # 5. Workspace admin (owner or admin role)
    if role in ("owner", "admin"):
        return ResolvedTrustContext(
            domain=TrustDomain.WORKSPACE_ADMIN,
            capabilities=DOMAIN_CAPABILITIES[TrustDomain.WORKSPACE_ADMIN],
            resolution_reason=f"role:{role}",
            user_id=user_id,
            org_id=org_id,
            role=role,
        )

    # 6. Customer user (editor, viewer, or any other interactive role)
    return ResolvedTrustContext(
        domain=TrustDomain.CUSTOMER_USER,
        capabilities=DOMAIN_CAPABILITIES[TrustDomain.CUSTOMER_USER],
        resolution_reason=f"role:{role}:customer_user",
        user_id=user_id,
        org_id=org_id,
        role=role,
    )


# =============================================================================
# Audit Trail for Domain Boundary Crossings
# =============================================================================

_domain_audit: list[dict[str, Any]] = []
_MAX_AUDIT_ENTRIES = 1000


def record_domain_crossing(
    *,
    requesting_domain: TrustDomain,
    target_domain: TrustDomain,
    resource_type: str,
    resource_id: str,
    user_id: str,
    org_id: str,
    outcome: str,
    reason: str = "",
) -> None:
    """Record a trust domain boundary crossing (R57.6).

    Called when access is denied (always) or when a higher-privilege domain
    accesses lower-privilege content (for audit completeness).
    """
    entry = {
        "timestamp": datetime.now(UTC).isoformat(),
        "event": "trust_domain_crossing",
        "requesting_domain": requesting_domain.name,
        "target_domain": target_domain.name,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "user_id": user_id,
        "org_id": org_id,
        "outcome": outcome,  # "denied" or "allowed_downward"
        "reason": reason,
    }
    _domain_audit.append(entry)
    if len(_domain_audit) > _MAX_AUDIT_ENTRIES:
        _domain_audit.pop(0)


def get_domain_audit(
    org_id: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Get the trust domain crossing audit trail."""
    entries = _domain_audit if not org_id else [
        e for e in _domain_audit if e.get("org_id") == org_id
    ]
    return list(reversed(entries[-limit:]))


def clear_domain_audit() -> None:
    """Clear the audit trail (for testing only)."""
    _domain_audit.clear()

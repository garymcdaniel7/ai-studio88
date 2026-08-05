"""Hermes Trust Domain Isolation — Story 039.

Every Hermes request resolves to exactly ONE trust domain. Each domain defines
what prompts, tools, memory scopes, and knowledge vaults are accessible.
Cross-domain access is deny-by-default and audited.

Trust Domains:
    FOUNDER    — Platform owner/operator. Full infrastructure visibility, private
                 strategy, internal ops, all tools. Never exposed to customers.
    ADMIN      — Workspace administrator. Manages credentials, team, billing,
                 infrastructure for their workspace. No founder-internal knowledge.
    CUSTOMER   — Regular workspace member (editor/viewer). Creative tools,
                 generation, training, publishing. No admin internals.
    SYSTEM     — Non-interactive automated operations (cron, workers, webhooks).
                 Narrow tool access, no conversational personality.

Resolution rules (server-side only — client cannot select domain):
    1. If user_id matches FOUNDER_USER_IDS → FOUNDER
    2. If role is 'owner' or 'admin' → ADMIN
    3. If role is 'editor' or 'viewer' → CUSTOMER
    4. If no user_id (system context) → SYSTEM
    5. Default → CUSTOMER (deny-by-default for ambiguous cases)

Security invariants:
    - Domain is resolved SERVER-SIDE from validated auth — never from client
    - Client cannot request, override, or escalate their domain
    - Prompt injection cannot elevate trust (domain is structural, not textual)
    - Cross-domain tool/memory/vault access is denied and audited
    - Founder knowledge never appears in CUSTOMER or ADMIN responses
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


# =============================================================================
# Trust Domain Definitions
# =============================================================================


class TrustDomain(str, Enum):
    """Authenticated trust domains for Hermes interactions."""

    FOUNDER = "founder"      # Platform owner — full visibility
    ADMIN = "admin"          # Workspace admin — manages workspace
    CUSTOMER = "customer"    # Regular creator — creative tools only
    SYSTEM = "system"        # Automated operations — no personality


# Founder user IDs — configured via environment (comma-separated UUIDs)
# UNVERIFIED: Production should use a proper role/flag in org_members, not env var
_FOUNDER_IDS_RAW = os.getenv("FOUNDER_USER_IDS", "")
FOUNDER_USER_IDS: frozenset[str] = frozenset(
    uid.strip() for uid in _FOUNDER_IDS_RAW.split(",") if uid.strip()
)


# =============================================================================
# Domain Permission Matrix
# =============================================================================


@dataclass(frozen=True)
class DomainPermissions:
    """What a trust domain is allowed to access."""

    domain: TrustDomain
    allowed_prompts: frozenset[str]    # Which system prompt profiles
    allowed_tools: frozenset[str]      # Which tool names can be invoked
    allowed_memory_scopes: frozenset[str]  # Which memory namespaces
    allowed_vaults: frozenset[str]     # Which knowledge vaults
    can_see_infrastructure: bool = False
    can_see_costs: bool = False
    can_manage_team: bool = False
    can_access_founder_knowledge: bool = False


# Define permissions per domain
DOMAIN_PERMISSIONS: dict[TrustDomain, DomainPermissions] = {
    TrustDomain.FOUNDER: DomainPermissions(
        domain=TrustDomain.FOUNDER,
        allowed_prompts=frozenset({
            "creative", "prompt_engineer", "script_writer", "story_assistant",
            "production_advisor", "image_analyzer", "admin", "founder_ops",
            "infrastructure", "diagnostics",
        }),
        allowed_tools=frozenset({
            "generate_image", "generate_video", "train_lora", "search_talent",
            "get_talent_knowledge", "check_platform_health", "auto_configure_generation",
            "search_knowledge_graph", "get_fleet_status", "diagnose_service",
            "generate_voice", "schedule_post", "run_uat_tests", "get_uat_results",
            "launch_gpu", "stop_gpu", "manage_credentials", "view_costs",
            "manage_governance", "deploy_model", "destroy_worker",
        }),
        allowed_memory_scopes=frozenset({
            "workspace", "user", "founder", "system", "infrastructure",
        }),
        allowed_vaults=frozenset({
            "creative", "technical", "business", "infrastructure", "founder_private",
        }),
        can_see_infrastructure=True,
        can_see_costs=True,
        can_manage_team=True,
        can_access_founder_knowledge=True,
    ),

    TrustDomain.ADMIN: DomainPermissions(
        domain=TrustDomain.ADMIN,
        allowed_prompts=frozenset({
            "creative", "prompt_engineer", "script_writer", "story_assistant",
            "production_advisor", "image_analyzer", "admin",
        }),
        allowed_tools=frozenset({
            "generate_image", "generate_video", "train_lora", "search_talent",
            "get_talent_knowledge", "check_platform_health", "auto_configure_generation",
            "search_knowledge_graph", "get_fleet_status", "generate_voice",
            "schedule_post", "manage_credentials", "view_costs",
            "launch_gpu", "stop_gpu",
        }),
        allowed_memory_scopes=frozenset({
            "workspace", "user",
        }),
        allowed_vaults=frozenset({
            "creative", "technical",
        }),
        can_see_infrastructure=True,
        can_see_costs=True,
        can_manage_team=True,
        can_access_founder_knowledge=False,
    ),

    TrustDomain.CUSTOMER: DomainPermissions(
        domain=TrustDomain.CUSTOMER,
        allowed_prompts=frozenset({
            "creative", "prompt_engineer", "script_writer", "story_assistant",
            "production_advisor", "image_analyzer",
        }),
        allowed_tools=frozenset({
            "generate_image", "generate_video", "train_lora", "search_talent",
            "get_talent_knowledge", "auto_configure_generation",
            "search_knowledge_graph", "generate_voice", "schedule_post",
        }),
        allowed_memory_scopes=frozenset({
            "workspace", "user",
        }),
        allowed_vaults=frozenset({
            "creative",
        }),
        can_see_infrastructure=False,
        can_see_costs=False,
        can_manage_team=False,
        can_access_founder_knowledge=False,
    ),

    TrustDomain.SYSTEM: DomainPermissions(
        domain=TrustDomain.SYSTEM,
        allowed_prompts=frozenset({
            "system",
        }),
        allowed_tools=frozenset({
            "check_platform_health", "get_fleet_status", "diagnose_service",
            "run_uat_tests",
        }),
        allowed_memory_scopes=frozenset({
            "system",
        }),
        allowed_vaults=frozenset({
            "technical", "infrastructure",
        }),
        can_see_infrastructure=True,
        can_see_costs=False,
        can_manage_team=False,
        can_access_founder_knowledge=False,
    ),
}


# =============================================================================
# Domain Resolution
# =============================================================================


@dataclass(frozen=True)
class ResolvedDomain:
    """The result of trust-domain resolution for a request."""

    domain: TrustDomain
    permissions: DomainPermissions
    resolution_reason: str
    user_id: str
    org_id: str
    role: str


def resolve_trust_domain(
    *,
    user_id: str,
    org_id: str,
    role: str,
) -> ResolvedDomain:
    """Resolve the trust domain for a request.

    Server-side only — the client CANNOT influence this decision.
    Uses validated auth identity + membership role.

    Resolution order:
    1. Founder check (explicit user ID list)
    2. Role-based (owner/admin → ADMIN, editor/viewer → CUSTOMER)
    3. System (no user_id)
    4. Default → CUSTOMER (deny-by-default)
    """
    # 1. System context (no interactive user)
    if not user_id:
        return ResolvedDomain(
            domain=TrustDomain.SYSTEM,
            permissions=DOMAIN_PERMISSIONS[TrustDomain.SYSTEM],
            resolution_reason="no_user_id:system_context",
            user_id="",
            org_id=org_id,
            role="system",
        )

    # 2. Founder check
    if user_id in FOUNDER_USER_IDS:
        return ResolvedDomain(
            domain=TrustDomain.FOUNDER,
            permissions=DOMAIN_PERMISSIONS[TrustDomain.FOUNDER],
            resolution_reason="founder_user_id_match",
            user_id=user_id,
            org_id=org_id,
            role=role,
        )

    # 3. Admin (workspace owner or admin role)
    if role in ("owner", "admin"):
        return ResolvedDomain(
            domain=TrustDomain.ADMIN,
            permissions=DOMAIN_PERMISSIONS[TrustDomain.ADMIN],
            resolution_reason=f"role:{role}",
            user_id=user_id,
            org_id=org_id,
            role=role,
        )

    # 4. Customer (editor, viewer, or any other role)
    return ResolvedDomain(
        domain=TrustDomain.CUSTOMER,
        permissions=DOMAIN_PERMISSIONS[TrustDomain.CUSTOMER],
        resolution_reason=f"role:{role}:default_customer",
        user_id=user_id,
        org_id=org_id,
        role=role,
    )


# =============================================================================
# Access Control — Deny-by-Default
# =============================================================================


@dataclass
class AccessDecision:
    """Result of a cross-domain access check."""

    allowed: bool
    resource_type: str  # "tool", "prompt", "memory", "vault"
    resource_name: str
    domain: TrustDomain
    reason: str


# Audit trail for domain violations
_domain_audit: list[dict] = []
_MAX_AUDIT = 1000


def _audit_violation(decision: AccessDecision, user_id: str, org_id: str) -> None:
    """Record a cross-domain access denial."""
    _domain_audit.append({
        "timestamp": datetime.now(UTC).isoformat(),
        "event": "cross_domain_denial",
        "domain": decision.domain.value,
        "resource_type": decision.resource_type,
        "resource_name": decision.resource_name,
        "reason": decision.reason,
        "user_id": user_id,
        "org_id": org_id,
    })
    if len(_domain_audit) > _MAX_AUDIT:
        _domain_audit.pop(0)


def get_domain_audit(org_id: str | None = None, limit: int = 50) -> list[dict]:
    """Get domain violation audit trail."""
    entries = _domain_audit if not org_id else [
        e for e in _domain_audit if e.get("org_id") == org_id
    ]
    return list(reversed(entries[-limit:]))


def check_tool_access(resolved: ResolvedDomain, tool_name: str) -> AccessDecision:
    """Check if the resolved domain permits using a specific tool."""
    if tool_name in resolved.permissions.allowed_tools:
        return AccessDecision(
            allowed=True, resource_type="tool", resource_name=tool_name,
            domain=resolved.domain, reason="allowed_by_domain",
        )

    decision = AccessDecision(
        allowed=False, resource_type="tool", resource_name=tool_name,
        domain=resolved.domain,
        reason=f"tool '{tool_name}' not in {resolved.domain.value} allowlist",
    )
    _audit_violation(decision, resolved.user_id, resolved.org_id)
    return decision


def check_prompt_access(resolved: ResolvedDomain, prompt_name: str) -> AccessDecision:
    """Check if the resolved domain permits using a specific prompt profile."""
    if prompt_name in resolved.permissions.allowed_prompts:
        return AccessDecision(
            allowed=True, resource_type="prompt", resource_name=prompt_name,
            domain=resolved.domain, reason="allowed_by_domain",
        )

    decision = AccessDecision(
        allowed=False, resource_type="prompt", resource_name=prompt_name,
        domain=resolved.domain,
        reason=f"prompt '{prompt_name}' not in {resolved.domain.value} allowlist",
    )
    _audit_violation(decision, resolved.user_id, resolved.org_id)
    return decision


def check_memory_access(resolved: ResolvedDomain, scope: str) -> AccessDecision:
    """Check if the resolved domain permits accessing a memory scope."""
    if scope in resolved.permissions.allowed_memory_scopes:
        return AccessDecision(
            allowed=True, resource_type="memory", resource_name=scope,
            domain=resolved.domain, reason="allowed_by_domain",
        )

    decision = AccessDecision(
        allowed=False, resource_type="memory", resource_name=scope,
        domain=resolved.domain,
        reason=f"memory scope '{scope}' not in {resolved.domain.value} allowlist",
    )
    _audit_violation(decision, resolved.user_id, resolved.org_id)
    return decision


def check_vault_access(resolved: ResolvedDomain, vault_name: str) -> AccessDecision:
    """Check if the resolved domain permits accessing a knowledge vault."""
    if vault_name in resolved.permissions.allowed_vaults:
        return AccessDecision(
            allowed=True, resource_type="vault", resource_name=vault_name,
            domain=resolved.domain, reason="allowed_by_domain",
        )

    decision = AccessDecision(
        allowed=False, resource_type="vault", resource_name=vault_name,
        domain=resolved.domain,
        reason=f"vault '{vault_name}' not in {resolved.domain.value} allowlist",
    )
    _audit_violation(decision, resolved.user_id, resolved.org_id)
    return decision

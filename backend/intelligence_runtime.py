"""Canonical Intelligence Runtime Contract — Story 031.

This module defines the ONE authoritative contract for all intelligence operations
in AI Studio. Every user-facing AI interaction MUST flow through this contract.

CANONICAL RUNTIME: AIOS Gateway (backend/aios/gateway.py)
EVIDENCE: Both frontend callers already use /aios/v1/chat; it has governance,
provider routing, decision audit, session persistence, and council integration.

Contract guarantees:
    1. Every chat request has an authenticated TenantContext (org_id + user_id)
    2. Sessions are tenant-scoped (aios_sessions table with org_id)
    3. Governance is consulted for action-producing requests
    4. Decisions are audited (log_decision for every response)
    5. Provider routing selects best LLM per request
    6. Memory is scoped to workspace (no cross-tenant context injection)

Path dispositions:
    CANONICAL:
        /aios/v1/chat          — Primary conversational interface
        /aios/v1/plan          — Execution planning
        /aios/v1/council       — Multi-agent orchestration
        /aios/v1/sessions      — Session management
        /aios/v1/approvals     — Governance approval workflow
        /aios/v1/governance    — Policy management
        /aios/v1/hermes/chat   — Specialized deep-task agent
        /aios/v1/hermes/task   — Multi-step tool execution
        /aios/v1/health        — Runtime health

    COMPATIBILITY (retained, not for new features):
        /api/v1/brain/llm/chat      — Direct LLM access (used by auto-fix, RAG)
        /api/v1/brain/health        — Health check (used by frontend status)
        /api/v1/brain/collections   — Collection management (used by Brain page)
        /api/v1/brain/conversations — Conversation persistence (used by Brain page)
        /api/v1/brain/memory        — Production memory read/write
        /api/v1/brain/fix           — AI auto-fix (specialized, not conversational)

    DEPRECATED (should not be used for new features):
        /api/v1/brain/chat     — Legacy planner-only chat (no governance, no routing)
        /api/v1/brain/plan     — Legacy plan endpoint (use /aios/v1/plan instead)
        /api/v1/brain/sessions — Legacy in-memory sessions (use /aios/v1/sessions)
        /api/v1/brain/reasoning — Never implemented meaningfully

    RETIRED: None yet (all paths still respond for backward compat).

Runtime capabilities:
    - Chat: Natural language conversation with mode-specific personality
    - Plan: Decompose intent into executable tasks
    - Council: Multi-agent reasoning with governance
    - Generate: Intent-detected auto-generation (images, video)
    - Approve: Human-in-the-loop for high-risk actions
    - Memory: Workspace-scoped learned preferences (via RAG)
    - Tools: Hermes tool execution for complex tasks
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# =============================================================================
# Runtime Contract Types
# =============================================================================


class RuntimePath(str, Enum):
    """Classification of each intelligence endpoint."""

    CANONICAL = "canonical"
    COMPATIBILITY = "compatibility"
    DEPRECATED = "deprecated"
    RETIRED = "retired"


@dataclass(frozen=True)
class EndpointDisposition:
    """Documented disposition of an intelligence endpoint."""

    path: str
    status: RuntimePath
    description: str
    replacement: str = ""
    reason: str = ""


# =============================================================================
# Endpoint Registry
# =============================================================================

ENDPOINT_DISPOSITIONS: list[EndpointDisposition] = [
    # Canonical (AIOS Gateway)
    EndpointDisposition("/aios/v1/chat", RuntimePath.CANONICAL, "Primary conversational interface"),
    EndpointDisposition("/aios/v1/plan", RuntimePath.CANONICAL, "Execution planning from intent"),
    EndpointDisposition("/aios/v1/council", RuntimePath.CANONICAL, "Multi-agent orchestration"),
    EndpointDisposition("/aios/v1/sessions", RuntimePath.CANONICAL, "Tenant-scoped session management"),
    EndpointDisposition("/aios/v1/approvals", RuntimePath.CANONICAL, "Governance approval workflow"),
    EndpointDisposition("/aios/v1/governance/policies", RuntimePath.CANONICAL, "Policy configuration"),
    EndpointDisposition("/aios/v1/hermes/chat", RuntimePath.CANONICAL, "Deep-task specialized agent"),
    EndpointDisposition("/aios/v1/hermes/task", RuntimePath.CANONICAL, "Multi-step tool execution"),
    EndpointDisposition("/aios/v1/health", RuntimePath.CANONICAL, "Runtime health status"),

    # Compatibility (Brain Router — retained for specific features)
    EndpointDisposition("/api/v1/brain/llm/chat", RuntimePath.COMPATIBILITY,
                        "Direct LLM access for auto-fix and RAG"),
    EndpointDisposition("/api/v1/brain/health", RuntimePath.COMPATIBILITY,
                        "Health check used by frontend"),
    EndpointDisposition("/api/v1/brain/collections", RuntimePath.COMPATIBILITY,
                        "Collection CRUD used by Brain page"),
    EndpointDisposition("/api/v1/brain/conversations", RuntimePath.COMPATIBILITY,
                        "Conversation persistence used by Brain page"),
    EndpointDisposition("/api/v1/brain/memory", RuntimePath.COMPATIBILITY,
                        "Production memory read/write"),
    EndpointDisposition("/api/v1/brain/fix", RuntimePath.COMPATIBILITY,
                        "AI auto-fix endpoint (specialized)"),

    # Deprecated (should not be used for new development)
    EndpointDisposition("/api/v1/brain/chat", RuntimePath.DEPRECATED,
                        "Legacy planner-only chat",
                        replacement="/aios/v1/chat",
                        reason="No governance, no provider routing, no tenant scoping"),
    EndpointDisposition("/api/v1/brain/plan", RuntimePath.DEPRECATED,
                        "Legacy plan creation",
                        replacement="/aios/v1/plan",
                        reason="No governance integration"),
    EndpointDisposition("/api/v1/brain/sessions", RuntimePath.DEPRECATED,
                        "Legacy in-memory sessions",
                        replacement="/aios/v1/sessions",
                        reason="Not tenant-scoped, not persistent across restarts"),
    EndpointDisposition("/api/v1/brain/reasoning/{plan_id}", RuntimePath.DEPRECATED,
                        "Never implemented — returns static placeholder",
                        replacement="",
                        reason="Not implemented meaningfully, no tenant scoping or persistence"),
]


def get_endpoint_disposition(path: str) -> EndpointDisposition | None:
    """Look up the disposition of an intelligence endpoint."""
    for ep in ENDPOINT_DISPOSITIONS:
        if ep.path == path or path.startswith(ep.path):
            return ep
    return None


def get_all_dispositions() -> list[dict]:
    """Get all endpoint dispositions as dicts (for API/dashboard)."""
    return [
        {
            "path": ep.path,
            "status": ep.status.value,
            "description": ep.description,
            "replacement": ep.replacement,
            "reason": ep.reason,
        }
        for ep in ENDPOINT_DISPOSITIONS
    ]


# =============================================================================
# Canonical Runtime Contract
# =============================================================================


@dataclass
class ChatRequest:
    """Canonical chat request contract.

    Every chat interaction — regardless of caller — must resolve to this.
    """

    message: str
    org_id: str  # From TenantContext (required)
    user_id: str  # From TenantContext (required)
    session_id: str | None = None  # Creates new if None
    mode: str = "creative"
    talent_id: str | None = None
    project_id: str | None = None
    images: list[str] | None = None  # Base64 for vision
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatResponse:
    """Canonical chat response contract.

    Every chat response — regardless of provider — returns this shape.
    """

    session_id: str
    response: str
    provider: str
    model: str
    mode: str
    latency_ms: int
    # Optional enrichments
    actions: list[dict] = field(default_factory=list)
    governance: dict = field(default_factory=dict)
    generation: dict | None = None
    is_degraded: bool = False  # Governance unavailable but read-only allowed


# =============================================================================
# Runtime Health
# =============================================================================


@dataclass
class RuntimeHealth:
    """Canonical runtime health contract."""

    status: str  # "operational", "degraded", "unavailable"
    canonical_path: str = "/aios/v1/chat"
    providers_available: int = 0
    session_persistence: bool = False
    governance_available: bool = False
    memory_available: bool = False
    decision_audit: bool = False


def check_runtime_health() -> RuntimeHealth:
    """Check canonical runtime health."""
    health = RuntimeHealth(status="operational")

    # Check LLM providers
    try:
        from backend.brain.llm_provider import get_brain_health
        brain_health = get_brain_health()
        health.providers_available = sum(
            1 for p in brain_health.get("providers", {}).values()
            if p.get("available")
        )
        if health.providers_available == 0:
            health.status = "degraded"
    except Exception:
        health.status = "degraded"

    # Check session persistence
    try:
        from backend.database import is_supabase_configured
        health.session_persistence = is_supabase_configured()
    except Exception:
        pass

    # Governance available (governance module loads without error)
    try:
        from backend.governance import evaluate_action
        health.governance_available = True
    except Exception:
        pass

    # Decision audit available
    health.decision_audit = True  # In-memory always available

    # Memory (RAG) available
    try:
        from backend.brain.llm_provider import chat
        health.memory_available = True
    except Exception:
        pass

    return health

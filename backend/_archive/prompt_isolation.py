"""Customer Prompt Isolation — Story 045.

Enforces trust-domain-specific prompt profiles and knowledge allowlists.
Ensures founder/operator/developer content NEVER enters customer prompts.

Architecture:
    1. Prompt profiles define what system context each domain receives
    2. Retrieval authorization checks vault permissions BEFORE content enters prompt
    3. Content sanitization strips internal markers from any text reaching customers
    4. Denial logging records all blocked cross-domain retrieval attempts

Security model:
    - Access is enforced BEFORE content enters the prompt (not relying on model instructions)
    - Even if the model is compromised, structural enforcement prevents leakage
    - Denied content is never returned, cached, or summarized for the requesting domain
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from backend.trust_domains import (
    DOMAIN_PERMISSIONS,
    TrustDomain,
    ResolvedDomain,
    check_vault_access,
)


# =============================================================================
# Prompt Profiles — What each domain sees as system context
# =============================================================================


# Content that ONLY the founder domain can see
_FOUNDER_ONLY_CONTEXT = """
## ADMIN-ONLY POWERS
You are talking to the platform owner. You can:
- Launch/stop/destroy GPU workers (with cost confirmation)
- View all service health, balances, API key status
- Run UAT tests and view results
- Diagnose service failures with root cause analysis
- Manage models (deploy, remove, cache)
- View costs across all orgs
- Set budgets, rate limits, feature flags
- Propose code fixes (with approval before implementing)
- Invoke Red Team assessments
- Manage governance policies and approval thresholds

## PLATFORM ARCHITECTURE (internal)
Backend: FastAPI (port 8000), 15 routers, 173+ endpoints
Frontend: Next.js 16 (port 3000)
Database: Supabase PostgreSQL
Storage: Backblaze B2
GPU: RunPod (primary) + Vast.ai (secondary)
LLM: Ollama local-first, OpenRouter/OpenAI/Anthropic fallback

## INFRASTRUCTURE COMMANDS
- Ollama restart: pkill -f ollama && ollama serve
- Worker launch: Call get_fleet_status first
- Model deploy: download from B2 cache
- SSH tunnel: ssh -N -L 8188:localhost:8188 -p PORT root@HOST

## GOVERNANCE RULES (internal)
- Restarting local services: safe, auto-execute
- SSH commands to GPU worker: require approval
- Launching GPU instances: ALWAYS confirm cost first
- Code changes: PROPOSE fix, wait for approval
- Destructive actions: require explicit "yes"
"""

# Content for ADMIN domain (workspace managers)
_ADMIN_CONTEXT = """
## WORKSPACE ADMIN CAPABILITIES
You can help with:
- Managing API keys and service connections
- Configuring governance policies (budgets, approvals)
- Viewing workspace costs and usage
- Managing team members and roles
- Launching and monitoring GPU workers
- Diagnosing connectivity issues

You cannot access:
- Other workspaces' data
- Platform-level infrastructure beyond your workspace
- Internal platform code or architecture details
"""

# Content for CUSTOMER domain (regular creators)
_CUSTOMER_CONTEXT = """
## AI STUDIO ASSISTANT
You are a creative AI assistant for AI Studio. You help creators with:
- Image and video generation (prompts, styles, models)
- AI talent management (LoRA training, Creative DNA)
- Content production workflows
- Prompt engineering and optimization
- Story development and scripting
- Publishing preparation

You work within the creator's workspace and can access their:
- Talent profiles and Creative DNA
- Generated assets and history
- Projects and workflows
- Training datasets and LoRA models

For infrastructure questions, billing, or account management,
direct the user to their workspace administrator.
"""

# Content for SYSTEM domain (automated operations)
_SYSTEM_CONTEXT = """
## SYSTEM OPERATION MODE
You are executing an automated task. Follow the provided instructions precisely.
Report results and errors without embellishment.
"""


def get_prompt_profile(domain: TrustDomain) -> str:
    """Get the system prompt context appropriate for the trust domain.

    This is the STRUCTURAL enforcement point — content is selected
    before it reaches the model. Model instructions alone are not
    trusted for isolation.
    """
    profiles = {
        TrustDomain.FOUNDER: _FOUNDER_ONLY_CONTEXT + _ADMIN_CONTEXT + _CUSTOMER_CONTEXT,
        TrustDomain.ADMIN: _ADMIN_CONTEXT + _CUSTOMER_CONTEXT,
        TrustDomain.CUSTOMER: _CUSTOMER_CONTEXT,
        TrustDomain.SYSTEM: _SYSTEM_CONTEXT,
    }
    return profiles.get(domain, _CUSTOMER_CONTEXT)


# =============================================================================
# Content Classification
# =============================================================================


class ContentClassification(str, Enum):
    """Classification of knowledge content by sensitivity."""

    PUBLIC = "public"            # Available to all authenticated users
    WORKSPACE = "workspace"      # Available to workspace members
    ADMIN_ONLY = "admin_only"    # Workspace admins only
    FOUNDER_ONLY = "founder_only"  # Platform founder only
    SYSTEM_ONLY = "system_only"  # Automated operations only
    UNVERIFIED = "unverified"    # Classification not determined — deny by default


# Keywords/patterns that indicate founder/internal content
_INTERNAL_MARKERS = frozenset({
    "SUPABASE_SERVICE_ROLE_KEY",
    "B2_APPLICATION_KEY",
    "VAST_API_KEY",
    "RUNPOD_API_KEY",
    "SSH_PRIVATE_KEY",
    "pkill -f",
    "ssh -N -L",
    "uv run uvicorn",
    "docker run",
    "backend/",
    "frontend/src/",
    "__pycache__",
    "GOVERNANCE RULES (internal)",
    "ADMIN-ONLY POWERS",
    "platform owner",
    "Red Team",
    "@redteam",
    "@dev_team",
    "P0-1",
    "P0-2",
    "defects backlog",
    "COMFYUI_BASE_URL",
    "worker_orchestrator",
})


def contains_internal_content(text: str) -> bool:
    """Check if text contains markers of internal/founder content.

    Used as a safety check on retrieval results before they enter prompts.
    """
    if not text:
        return False
    for marker in _INTERNAL_MARKERS:
        if marker in text:
            return True
    return False


# =============================================================================
# Retrieval Authorization
# =============================================================================


_retrieval_audit: list[dict] = []
_MAX_AUDIT = 500


@dataclass
class RetrievalRequest:
    """A request to retrieve knowledge content."""

    vault: str
    query: str
    domain: TrustDomain
    user_id: str
    org_id: str


@dataclass
class RetrievalResult:
    """Result of an authorized retrieval attempt."""

    allowed: bool
    content: str = ""
    source_vault: str = ""
    denial_reason: str = ""
    was_sanitized: bool = False


def authorize_retrieval(
    request: RetrievalRequest,
    resolved_domain: ResolvedDomain,
) -> RetrievalResult:
    """Authorize a knowledge retrieval request BEFORE content enters the prompt.

    This is the enforcement boundary:
    1. Check vault access via trust domain permissions
    2. If denied: log, return empty (content never reaches the model)
    3. If allowed: check content for internal markers (defense in depth)
    4. Sanitize if needed

    Content is NEVER returned for denied requests — not even summarized.
    """
    # Check vault permission
    access = check_vault_access(resolved_domain, request.vault)

    if not access.allowed:
        # DENIED — log and return empty
        _log_denial(request, f"vault_access_denied:{request.vault}")
        return RetrievalResult(
            allowed=False,
            denial_reason=f"Vault '{request.vault}' not authorized for {request.domain.value} domain",
        )

    # Vault is allowed — in production this would fetch actual content
    # For now, return a placeholder indicating the retrieval was authorized
    return RetrievalResult(
        allowed=True,
        source_vault=request.vault,
        content="",  # Actual retrieval would go here
    )


def sanitize_for_domain(content: str, domain: TrustDomain) -> str:
    """Sanitize content for the target domain.

    Removes internal markers from content that somehow passed vault checks.
    Defense-in-depth — should rarely trigger if vault access is correct.
    """
    if domain == TrustDomain.FOUNDER:
        return content  # Founder sees everything

    if not content:
        return content

    # For non-founder domains, strip lines containing internal markers
    if contains_internal_content(content):
        lines = content.split("\n")
        safe_lines = [
            line for line in lines
            if not any(marker in line for marker in _INTERNAL_MARKERS)
        ]
        return "\n".join(safe_lines)

    return content


def _log_denial(request: RetrievalRequest, reason: str) -> None:
    """Log a retrieval denial (never includes the content that was denied)."""
    _retrieval_audit.append({
        "timestamp": datetime.now(UTC).isoformat(),
        "event": "retrieval_denied",
        "domain": request.domain.value,
        "vault": request.vault,
        "user_id": request.user_id,
        "org_id": request.org_id,
        "reason": reason,
        # NEVER log the query content for denied requests (could be injection attempt)
    })
    if len(_retrieval_audit) > _MAX_AUDIT:
        _retrieval_audit.pop(0)


def get_retrieval_audit(org_id: str | None = None, limit: int = 50) -> list[dict]:
    """Get retrieval denial audit trail."""
    entries = _retrieval_audit if not org_id else [
        e for e in _retrieval_audit if e.get("org_id") == org_id
    ]
    return list(reversed(entries[-limit:]))


# =============================================================================
# Prompt Assembly (Domain-Aware)
# =============================================================================


def assemble_prompt_context(
    *,
    resolved_domain: ResolvedDomain,
    mode: str = "creative",
    additional_context: str = "",
) -> str:
    """Assemble the complete system prompt for a Hermes request.

    Combines:
    1. Domain-appropriate profile (structural — not model-instruction-only)
    2. Mode-specific personality
    3. Sanitized additional context (if any)

    The result is safe for the resolved domain — no cross-domain leakage.
    """
    # Get domain-appropriate base context
    profile = get_prompt_profile(resolved_domain.domain)

    # Sanitize any additional context
    safe_additional = sanitize_for_domain(additional_context, resolved_domain.domain)

    # Combine
    parts = [profile]
    if safe_additional:
        parts.append(f"\n## ADDITIONAL CONTEXT\n{safe_additional}")

    return "\n".join(parts)

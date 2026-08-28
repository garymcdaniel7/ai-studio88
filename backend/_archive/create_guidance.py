"""Create Page Guidance Hierarchy — Story 116.

Classifies guidance content into tiers so the Create page shows
outcome-focused language by default and reserves infrastructure
details for authorized advanced/admin views.

Tiers:
    CREATOR   — Default path. Outcome-focused actions and truthful status.
                No SSH, worker topology, model deployment, or service internals.
    ADVANCED  — Power-user creative controls. LoRA strength, workflow selection,
                ComfyUI node parameters. Requires explicit disclosure toggle.
    ADMIN     — Infrastructure diagnostics. Worker status, SSH commands, GPU
                provider details, model cache, service health. Role-gated.

Rules:
    - Default view = CREATOR tier only
    - ADVANCED = visible when user explicitly opens "Advanced Controls"
    - ADMIN = visible only to admin/owner roles + explicit "Diagnostics" toggle
    - Capability status is always truthful (even in CREATOR tier)
    - Hermes can explain and route but cannot claim resolution without evidence
    - No privileged links leak into unauthorized views
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================


class GuidanceTier(str, Enum):
    CREATOR = "creator"       # Outcome-focused (default)
    ADVANCED = "advanced"     # Power-user creative controls
    ADMIN = "admin"           # Infrastructure diagnostics


class CapabilityState(str, Enum):
    READY = "ready"           # Fully operational
    DEGRADED = "degraded"     # Partially working (some features limited)
    UNAVAILABLE = "unavailable"  # Cannot generate
    PROVISIONING = "provisioning"  # Setting up (automated)
    UNKNOWN = "unknown"       # Cannot determine status


class UserRole(str, Enum):
    VIEWER = "viewer"
    EDITOR = "editor"
    ADMIN = "admin"
    OWNER = "owner"


ADMIN_ROLES = {UserRole.ADMIN, UserRole.OWNER}


# =============================================================================
# Guidance Content
# =============================================================================


@dataclass
class GuidanceItem:
    """A single piece of guidance content with tier classification."""
    item_id: str = ""
    tier: GuidanceTier = GuidanceTier.CREATOR
    title: str = ""
    message: str = ""
    action_label: str | None = None
    action_url: str | None = None
    is_dismissible: bool = True
    # Content classification markers
    contains_ssh: bool = False
    contains_worker_commands: bool = False
    contains_service_topology: bool = False
    contains_model_deployment: bool = False


@dataclass
class StatusMessage:
    """A truthful capability status message for the Create page."""
    state: CapabilityState
    headline: str            # Short user-facing text
    detail: str = ""         # Longer explanation
    tier: GuidanceTier = GuidanceTier.CREATOR
    recoverable: bool = True
    hermes_can_help: bool = False


@dataclass
class DiagnosticInfo:
    """Infrastructure diagnostic information (ADMIN only)."""
    worker_status: str = ""
    gpu_provider: str = ""
    ssh_command: str = ""
    model_cache_status: str = ""
    service_health: dict[str, str] = field(default_factory=dict)
    last_error: str = ""
    recovery_steps: list[str] = field(default_factory=list)


# =============================================================================
# Guidance Resolution
# =============================================================================


@dataclass
class CreatePageGuidance:
    """Resolved guidance for the Create page based on role and capability state."""
    # What the user sees
    visible_items: list[GuidanceItem] = field(default_factory=list)
    status: StatusMessage | None = None
    diagnostics: DiagnosticInfo | None = None  # Only for admin

    # Access control
    can_see_advanced: bool = False
    can_see_diagnostics: bool = False
    show_advanced: bool = False     # User toggled advanced open
    show_diagnostics: bool = False  # User toggled diagnostics open

    # Capability
    can_generate: bool = False


def resolve_guidance(
    user_role: UserRole,
    capability_state: CapabilityState,
    show_advanced: bool = False,
    show_diagnostics: bool = False,
    diagnostics: DiagnosticInfo | None = None,
) -> CreatePageGuidance:
    """Resolve what guidance the Create page should show.

    Default: CREATOR tier only (outcome-focused, no infrastructure).
    Advanced: if user explicitly toggles, show creative power-user controls.
    Admin: if user has admin role AND explicitly toggles diagnostics.
    """
    guidance = CreatePageGuidance(
        can_see_advanced=True,  # All authenticated users can toggle advanced
        can_see_diagnostics=user_role in ADMIN_ROLES,
        show_advanced=show_advanced,
        show_diagnostics=show_diagnostics and user_role in ADMIN_ROLES,
        can_generate=capability_state == CapabilityState.READY,
    )

    # Status message (always truthful, always shown)
    guidance.status = _get_status_message(capability_state)

    # Creator-tier guidance (always shown)
    guidance.visible_items = _get_creator_guidance(capability_state)

    # Advanced tier (only if toggled)
    if guidance.show_advanced:
        guidance.visible_items.extend(_get_advanced_guidance(capability_state))

    # Admin diagnostics (only if role allows AND toggled)
    if guidance.show_diagnostics and diagnostics:
        guidance.diagnostics = diagnostics

    return guidance


# =============================================================================
# Status Messages (always truthful)
# =============================================================================


def _get_status_message(state: CapabilityState) -> StatusMessage:
    """Get truthful status message for capability state."""
    messages = {
        CapabilityState.READY: StatusMessage(
            state=CapabilityState.READY,
            headline="Ready to create",
            detail="Describe what you'd like to generate.",
        ),
        CapabilityState.DEGRADED: StatusMessage(
            state=CapabilityState.DEGRADED,
            headline="Some features limited",
            detail="Generation is available but some models or features may be temporarily limited.",
            hermes_can_help=True,
        ),
        CapabilityState.UNAVAILABLE: StatusMessage(
            state=CapabilityState.UNAVAILABLE,
            headline="Generation unavailable",
            detail="The generation service is not currently available. This is being worked on.",
            recoverable=True,
            hermes_can_help=True,
        ),
        CapabilityState.PROVISIONING: StatusMessage(
            state=CapabilityState.PROVISIONING,
            headline="Setting up",
            detail="Generation infrastructure is being prepared. This usually takes a few minutes.",
            recoverable=True,
        ),
        CapabilityState.UNKNOWN: StatusMessage(
            state=CapabilityState.UNKNOWN,
            headline="Checking status",
            detail="Unable to determine current generation capability.",
            hermes_can_help=True,
        ),
    }
    return messages.get(state, messages[CapabilityState.UNKNOWN])


# =============================================================================
# Creator-Tier Guidance (outcome-focused, no infrastructure)
# =============================================================================


def _get_creator_guidance(state: CapabilityState) -> list[GuidanceItem]:
    """Get creator-tier guidance items — outcome-focused only."""
    items = []

    if state == CapabilityState.READY:
        items.append(GuidanceItem(
            item_id="creator-ready",
            tier=GuidanceTier.CREATOR,
            title="What would you like to create?",
            message="Describe your image, select a talent and style, then generate.",
        ))
    elif state == CapabilityState.UNAVAILABLE:
        items.append(GuidanceItem(
            item_id="creator-unavailable",
            tier=GuidanceTier.CREATOR,
            title="Generation is being restored",
            message="You can still explore talents, manage assets, and prepare prompts while generation is offline.",
            action_label="Browse Talent",
            action_url="/talent",
        ))
    elif state == CapabilityState.DEGRADED:
        items.append(GuidanceItem(
            item_id="creator-degraded",
            tier=GuidanceTier.CREATOR,
            title="Some options temporarily limited",
            message="You can generate with available models. Some advanced options may be temporarily restricted.",
        ))
    elif state == CapabilityState.PROVISIONING:
        items.append(GuidanceItem(
            item_id="creator-provisioning",
            tier=GuidanceTier.CREATOR,
            title="Getting ready",
            message="Generation resources are being prepared. You can start composing your prompt now.",
        ))

    return items


# =============================================================================
# Advanced-Tier Guidance (creative power-user)
# =============================================================================


def _get_advanced_guidance(state: CapabilityState) -> list[GuidanceItem]:
    """Get advanced creative controls guidance."""
    items = []

    if state == CapabilityState.READY:
        items.append(GuidanceItem(
            item_id="advanced-controls",
            tier=GuidanceTier.ADVANCED,
            title="Advanced Controls",
            message="Fine-tune generation parameters: steps, CFG, seed, LoRA strength, and workflow selection.",
        ))

    return items


# =============================================================================
# Content Classification
# =============================================================================


# Patterns that indicate infrastructure content (should NOT be in creator tier)
INFRASTRUCTURE_PATTERNS = [
    "ssh", "SSH", "worker", "gpu", "instance", "provider",
    "vast.ai", "runpod", "comfyui", "ComfyUI",
    "model cache", "safetensors", "checkpoint",
    "tunnel", "port forward", "docker",
    "pip install", "uv run", "python -m",
    "curl localhost", "health check endpoint",
]


def classify_content(text: str) -> GuidanceTier:
    """Classify text content into its appropriate tier.

    Infrastructure commands/terminology → ADMIN
    Creative parameter details → ADVANCED
    Everything else → CREATOR
    """
    text_lower = text.lower()

    # Check for infrastructure patterns
    for pattern in INFRASTRUCTURE_PATTERNS:
        if pattern.lower() in text_lower:
            return GuidanceTier.ADMIN

    # Check for advanced creative patterns
    advanced_patterns = ["cfg_scale", "sampler", "scheduler", "lora_strength",
                         "controlnet", "workflow", "node", "latent"]
    for pattern in advanced_patterns:
        if pattern in text_lower:
            return GuidanceTier.ADVANCED

    return GuidanceTier.CREATOR


def is_content_appropriate_for_tier(content: str, tier: GuidanceTier) -> bool:
    """Check if content is appropriate for display at the given tier."""
    content_tier = classify_content(content)

    # Tier hierarchy: CREATOR < ADVANCED < ADMIN
    tier_order = {GuidanceTier.CREATOR: 0, GuidanceTier.ADVANCED: 1, GuidanceTier.ADMIN: 2}
    return tier_order[content_tier] <= tier_order[tier]


# =============================================================================
# Link Protection
# =============================================================================


# Links that require admin role
ADMIN_ONLY_LINKS = {
    "/admin/fleet", "/admin/health", "/admin/keys",
    "/admin/downloads", "/admin/ise", "/admin/knowledge",
    "/settings",
}

# Links that are always safe for creators
CREATOR_SAFE_LINKS = {
    "/create", "/talent", "/assets", "/brain", "/production",
    "/publish", "/analytics", "/storyboards",
}


def filter_links_for_role(links: list[str], user_role: UserRole) -> list[str]:
    """Filter navigation links based on user role.

    Admin-only links hidden from non-admin users.
    Never exposes fleet/worker/SSH links to basic creators.
    """
    if user_role in ADMIN_ROLES:
        return links  # Admins see everything

    return [link for link in links if link not in ADMIN_ONLY_LINKS]


def is_link_authorized(link: str, user_role: UserRole) -> bool:
    """Check if a specific link is authorized for the user's role."""
    if link in ADMIN_ONLY_LINKS:
        return user_role in ADMIN_ROLES
    return True


# =============================================================================
# Testing Support
# =============================================================================


def _reset_store() -> None:
    pass  # Stateless module — nothing to reset

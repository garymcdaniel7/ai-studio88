"""Workspace Relationship Context Model — R57.6, R57.7, R57.8.

Provides the contextual relationship model that Brain/Hermes uses to understand
workspace entities and their authorized relationships for contextual responses.

The WorkspaceRelationshipContext aggregates:
  - User identity and trust domain
  - Workspace info (org_id, name, plan)
  - Active project (if any)
  - Selected talent (if any)
  - Active connections (summaries)
  - User preferences (from memory layer 2)
  - Workspace knowledge (from memory layer 3, trust-domain filtered)

All knowledge is filtered through the requesting user's trust domain per R57.5.
Boundary crossings (higher-privilege content accessed by lower-privilege user)
are logged as P0 security incidents per R57.7.

Validates: Requirements R57.6, R57.7, R57.8
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol, Sequence
from uuid import UUID

from backend.app.core.trust_domains import (
    ResolvedTrustContext,
    TrustDomain,
    filter_by_trust_domain,
    record_domain_crossing,
    resolve_trust_domain,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Supporting Dataclasses
# =============================================================================


@dataclass(frozen=True)
class UserContext:
    """Authenticated user identity within a workspace context."""

    user_id: str
    name: str
    role: str
    trust_domain: TrustDomain
    email: str | None = None


@dataclass(frozen=True)
class WorkspaceInfo:
    """Workspace (organisation) summary."""

    org_id: str
    name: str
    plan: str


@dataclass(frozen=True)
class ProjectSummary:
    """Lightweight project reference for context."""

    id: str
    name: str
    status: str = "active"


@dataclass(frozen=True)
class TalentSummary:
    """Lightweight talent reference for context."""

    id: str
    name: str
    talent_type: str = "ai_persona"


@dataclass(frozen=True)
class ConnectionSummary:
    """Summary of an active workspace connection."""

    id: str
    name: str
    provider: str
    status: str = "connected"


@dataclass(frozen=True)
class PreferenceItem:
    """A user preference stored in memory layer 2."""

    key: str
    value: str
    category: str = "general"


@dataclass(frozen=True)
class KnowledgeItem:
    """A knowledge item with trust domain tagging.

    The trust_domain attribute is required for filter_by_trust_domain() to work.
    """

    id: str
    content: str
    source: str
    trust_domain: TrustDomain = TrustDomain.CUSTOMER_USER
    category: str = "general"


# =============================================================================
# Workspace Relationship Context
# =============================================================================


@dataclass
class WorkspaceRelationshipContext:
    """Entities and their authorized relationships for contextual responses.

    Storage/query patterns determined by design.md.
    Brain/Hermes uses this to understand the full workspace context for a user,
    filtered through their trust domain so no unauthorized data leaks.

    Validates: R57.8 — Brain/Hermes SHALL understand authorized relationships
    between workspace entities: user, workspace, project, Talent, assets,
    connections, models, workflows, decisions, preferences, and approvals.
    """

    user: UserContext
    workspace: WorkspaceInfo
    active_project: ProjectSummary | None = None
    selected_talent: TalentSummary | None = None
    connections: list[ConnectionSummary] = field(default_factory=list)
    preferences: list[PreferenceItem] = field(default_factory=list)
    knowledge: list[KnowledgeItem] = field(default_factory=list)
    trust_context: ResolvedTrustContext | None = None
    boundary_crossings_logged: int = 0


# =============================================================================
# Serializable Summary (for Brain context injection)
# =============================================================================


@dataclass(frozen=True)
class WorkspaceContextSummary:
    """Serializable summary of workspace context for inclusion in Brain/LLM context.

    This is a compact representation suitable for injecting into LLM prompts
    without exposing internal dataclass structure.
    """

    user_name: str
    user_role: str
    trust_domain: str
    workspace_name: str
    workspace_plan: str
    active_project_name: str | None
    selected_talent_name: str | None
    connection_count: int
    preference_count: int
    knowledge_item_count: int

    def to_context_string(self) -> str:
        """Render as a concise context block for LLM injection."""
        lines = [
            f"User: {self.user_name} (role: {self.user_role})",
            f"Workspace: {self.workspace_name} (plan: {self.workspace_plan})",
        ]
        if self.active_project_name:
            lines.append(f"Active Project: {self.active_project_name}")
        if self.selected_talent_name:
            lines.append(f"Selected Talent: {self.selected_talent_name}")
        lines.append(f"Connections: {self.connection_count}")
        lines.append(f"Preferences: {self.preference_count}")
        lines.append(f"Knowledge Items: {self.knowledge_item_count}")
        return "\n".join(lines)


def summarize_context(ctx: WorkspaceRelationshipContext) -> WorkspaceContextSummary:
    """Create a serializable summary from a full workspace context."""
    return WorkspaceContextSummary(
        user_name=ctx.user.name,
        user_role=ctx.user.role,
        trust_domain=ctx.user.trust_domain.name,
        workspace_name=ctx.workspace.name,
        workspace_plan=ctx.workspace.plan,
        active_project_name=ctx.active_project.name if ctx.active_project else None,
        selected_talent_name=ctx.selected_talent.name if ctx.selected_talent else None,
        connection_count=len(ctx.connections),
        preference_count=len(ctx.preferences),
        knowledge_item_count=len(ctx.knowledge),
    )


# =============================================================================
# Context Builder
# =============================================================================


def _detect_and_log_boundary_crossings(
    *,
    all_knowledge: Sequence[Any],
    filtered_knowledge: list[Any],
    trust_context: ResolvedTrustContext,
) -> int:
    """Detect items that were filtered out due to trust domain restrictions.

    For each filtered-out item, log a boundary crossing per R57.6.
    If any higher-privilege content would have leaked, treat as P0 per R57.7.

    Returns the count of boundary crossings logged.
    """
    filtered_ids = {getattr(item, "id", None) for item in filtered_knowledge}
    crossings = 0

    for item in all_knowledge:
        item_id = getattr(item, "id", "unknown")
        if item_id not in filtered_ids:
            # This item was excluded by trust domain filtering
            item_domain_raw = getattr(item, "trust_domain", None)
            if isinstance(item_domain_raw, TrustDomain):
                item_domain = item_domain_raw
            elif isinstance(item_domain_raw, str):
                try:
                    item_domain = TrustDomain[item_domain_raw.upper()]
                except (KeyError, AttributeError):
                    item_domain = TrustDomain.FOUNDER_PRIVATE
            else:
                item_domain = TrustDomain.FOUNDER_PRIVATE

            # Log the crossing
            record_domain_crossing(
                requesting_domain=trust_context.domain,
                target_domain=item_domain,
                resource_type="knowledge_item",
                resource_id=str(item_id),
                user_id=trust_context.user_id,
                org_id=trust_context.org_id,
                outcome="denied",
                reason=(
                    f"Trust domain filtering excluded {item_domain.name} "
                    f"content from {trust_context.domain.name} session"
                ),
            )

            # Log as P0 security boundary event per R57.7
            logger.warning(
                "trust_domain_boundary_crossing",
                extra={
                    "event": "trust_domain_boundary_violation_prevented",
                    "severity": "P0",
                    "requesting_domain": trust_context.domain.name,
                    "target_domain": item_domain.name,
                    "resource_id": str(item_id),
                    "user_id": trust_context.user_id,
                    "org_id": trust_context.org_id,
                },
            )
            crossings += 1

    return crossings


async def build_workspace_context(
    *,
    user_id: str,
    user_name: str,
    org_id: str,
    org_name: str,
    org_plan: str,
    role: str,
    is_platform_operator: bool = False,
    platform_capabilities: frozenset[str] | None = None,
    active_project: ProjectSummary | None = None,
    selected_talent: TalentSummary | None = None,
    connections: list[ConnectionSummary] | None = None,
    preferences: list[PreferenceItem] | None = None,
    knowledge: Sequence[Any] | None = None,
    email: str | None = None,
) -> WorkspaceRelationshipContext:
    """Build a fully populated WorkspaceRelationshipContext.

    This function:
      1. Resolves the user's trust domain via resolve_trust_domain()
      2. Assembles workspace info, active project, selected talent, connections
      3. Filters knowledge through filter_by_trust_domain() per R57.5
      4. Logs any boundary crossings via record_domain_crossing() per R57.6
      5. Returns a fully populated WorkspaceRelationshipContext

    Args:
        user_id: Authenticated user ID (from JWT).
        user_name: User display name.
        org_id: Organisation (workspace) ID.
        org_name: Organisation name.
        org_plan: Subscription plan name.
        role: User's role in the workspace (owner, admin, editor, viewer).
        is_platform_operator: Whether user has platform operator status.
        platform_capabilities: Operator capability grants (if applicable).
        active_project: Currently active project (if any).
        selected_talent: Currently selected talent (if any).
        connections: List of workspace connections.
        preferences: User preference items (memory layer 2).
        knowledge: Raw knowledge items to be trust-domain filtered.
        email: User email (informational).

    Returns:
        A WorkspaceRelationshipContext with all knowledge filtered through
        the user's trust domain.
    """
    # Step 1: Resolve trust domain
    trust_context = resolve_trust_domain(
        user_id=user_id,
        org_id=org_id,
        role=role,
        is_platform_operator=is_platform_operator,
        platform_capabilities=platform_capabilities,
    )

    # Step 2: Assemble user context
    user_context = UserContext(
        user_id=user_id,
        name=user_name,
        role=role,
        trust_domain=trust_context.domain,
        email=email,
    )

    workspace = WorkspaceInfo(
        org_id=org_id,
        name=org_name,
        plan=org_plan,
    )

    # Step 3: Filter knowledge through trust domain (R57.5)
    all_knowledge = list(knowledge) if knowledge else []
    filtered_knowledge = filter_by_trust_domain(
        items=all_knowledge,
        requesting_domain=trust_context.domain,
    )

    # Step 4: Log boundary crossings (R57.6, R57.7)
    crossings_logged = _detect_and_log_boundary_crossings(
        all_knowledge=all_knowledge,
        filtered_knowledge=filtered_knowledge,
        trust_context=trust_context,
    )

    if crossings_logged > 0:
        logger.info(
            "workspace_context_built_with_crossings",
            extra={
                "user_id": user_id,
                "org_id": org_id,
                "trust_domain": trust_context.domain.name,
                "knowledge_total": len(all_knowledge),
                "knowledge_filtered": len(filtered_knowledge),
                "boundary_crossings": crossings_logged,
            },
        )

    # Step 5: Build and return context
    return WorkspaceRelationshipContext(
        user=user_context,
        workspace=workspace,
        active_project=active_project,
        selected_talent=selected_talent,
        connections=connections or [],
        preferences=preferences or [],
        knowledge=filtered_knowledge,
        trust_context=trust_context,
        boundary_crossings_logged=crossings_logged,
    )

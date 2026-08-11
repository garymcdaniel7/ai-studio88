"""Application Context envelope for Brain/Hermes sessions — R58.

Defines the server-validated context envelope that is transmitted with every
Brain chat request. The envelope contains the current workspace state, active
entities, capabilities, and UI state needed for contextual AI responses.

Key security constraints:
  - Authorization fields (org_id, user_id, role, trust_domain) are ALWAYS
    server-derived from the validated JWT and org_members lookup (R58.3)
  - All referenced IDs (project_id, talent_id, asset_ids, job_id) are
    validated against the authenticated org_id before use (R58.4)
  - Cross-tenant references are silently dropped with a warning log (R58.4)

Validates: Requirements R58.1, R58.2, R58.3, R58.4
"""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.core.dependencies import TenantContext, TrustDomain, WorkspaceRole

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================


class BrainMode(StrEnum):
    """Active Brain mode determines personality and tool selection."""

    CREATIVE = "creative"
    PROMPT_ENGINEER = "prompt_engineer"
    STORY_ASSISTANT = "story_assistant"
    PRODUCTION_ADVISOR = "production_advisor"
    RESEARCH = "research"
    IMAGE_ANALYZER = "image_analyzer"
    BUSINESS_STRATEGY = "business_strategy"


# =============================================================================
# Context Sub-Models (Server-Derived)
# =============================================================================


class WorkspaceContextInfo(BaseModel):
    """Server-derived workspace information from TenantContext.

    These fields are NEVER client-supplied — they are resolved from the
    validated JWT and org_members lookup.
    """

    org_id: UUID
    name: str
    plan: str

    model_config = ConfigDict(from_attributes=True)


class UserContextInfo(BaseModel):
    """Server-derived user information from TenantContext.

    These fields are NEVER client-supplied — they are resolved from the
    validated JWT.
    """

    user_id: UUID
    role: WorkspaceRole
    trust_domain: TrustDomain

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# Client Request Schema (what the frontend sends)
# =============================================================================


class ApplicationContextRequest(BaseModel):
    """What the client sends with each Brain chat request.

    This schema accepts ONLY the client-supplied fields. Authorization
    fields (org_id, user_id, role) must NEVER be accepted from the client —
    they are derived server-side from TenantContext (R58.3).

    Validates: R58.2 — structured, typed context transmitted with each chat request.
    """

    current_page: str | None = Field(
        default=None,
        max_length=200,
        description="Current frontend page/route (e.g., '/talent', '/create')",
    )
    active_project_id: UUID | None = Field(
        default=None,
        description="Currently active project UUID (validated against org)",
    )
    selected_talent_id: UUID | None = Field(
        default=None,
        description="Currently selected Talent UUID (validated against org)",
    )
    selected_asset_ids: list[UUID] = Field(
        default_factory=list,
        max_length=50,
        description="Selected asset UUIDs (validated against org)",
    )
    active_job_id: UUID | None = Field(
        default=None,
        description="Currently active job UUID (validated against org)",
    )
    active_brain_mode: BrainMode = Field(
        default=BrainMode.CREATIVE,
        description="Active Brain mode for personality/tool selection",
    )
    workflow_state: dict[str, Any] | None = Field(
        default=None,
        description="Current workflow state from frontend (opaque to backend)",
    )
    ui_state: dict[str, Any] | None = Field(
        default=None,
        description="Current UI state (sanitized — no secrets or auth data)",
    )
    context_version: str = Field(
        default="1",
        max_length=10,
        description="Context schema version for forward compatibility",
    )

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    @field_validator("ui_state")
    @classmethod
    def sanitize_ui_state(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        """Strip any keys that could contain auth/secret data from UI state."""
        if v is None:
            return None
        forbidden_keys = {
            "token", "jwt", "password", "secret", "api_key",
            "authorization", "credentials", "cookie",
        }
        return {
            k: val for k, val in v.items()
            if k.lower() not in forbidden_keys
        }


# =============================================================================
# Full Application Context (Server-Assembled)
# =============================================================================


class ApplicationContext(BaseModel):
    """Full server-validated Application Context envelope.

    This is the complete context available to Brain/Hermes for a session.
    It combines server-derived identity/authorization with validated
    client-supplied state.

    Validates: R58.1 — contains workspace, page, project, talent, assets,
    job, mode, capabilities, workflow state, and UI state.
    """

    # Server-derived (NEVER from client) — R58.3
    workspace: WorkspaceContextInfo
    user: UserContextInfo

    # Client-supplied, server-validated — R58.4
    current_page: str | None = None
    active_project_id: UUID | None = None
    selected_talent_id: UUID | None = None
    selected_asset_ids: list[UUID] = Field(default_factory=list)
    active_job_id: UUID | None = None
    active_brain_mode: BrainMode = BrainMode.CREATIVE

    # Server-resolved from plan + role
    capabilities: list[str] = Field(default_factory=list)

    # Client-supplied opaque state
    workflow_state: dict[str, Any] | None = None
    ui_state: dict[str, Any] | None = None

    # Metadata
    context_version: str = "1"
    dropped_references: list[str] = Field(
        default_factory=list,
        description="IDs that were dropped due to org validation failure",
    )

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# Capability Resolution
# =============================================================================


# Capabilities granted per plan tier
_PLAN_CAPABILITIES: dict[str, list[str]] = {
    "free": [
        "generation.basic",
        "brain.chat",
        "talent.manage",
        "project.manage",
    ],
    "starter": [
        "generation.basic",
        "generation.batch",
        "brain.chat",
        "brain.modes",
        "talent.manage",
        "project.manage",
        "assets.manage",
        "publishing.basic",
    ],
    "pro": [
        "generation.basic",
        "generation.batch",
        "generation.advanced",
        "brain.chat",
        "brain.modes",
        "brain.memory",
        "talent.manage",
        "talent.training",
        "project.manage",
        "assets.manage",
        "publishing.basic",
        "publishing.scheduling",
        "analytics.basic",
        "video.basic",
    ],
    "enterprise": [
        "generation.basic",
        "generation.batch",
        "generation.advanced",
        "brain.chat",
        "brain.modes",
        "brain.memory",
        "brain.autonomous",
        "talent.manage",
        "talent.training",
        "talent.advanced",
        "project.manage",
        "assets.manage",
        "publishing.basic",
        "publishing.scheduling",
        "publishing.automation",
        "analytics.basic",
        "analytics.advanced",
        "video.basic",
        "video.advanced",
        "audio.voice",
        "audio.music",
        "connections.advanced",
    ],
}

# Additional capabilities granted per role (additive to plan)
_ROLE_CAPABILITIES: dict[WorkspaceRole, list[str]] = {
    WorkspaceRole.OWNER: [
        "workspace.settings",
        "workspace.billing",
        "workspace.members",
        "workspace.connections",
        "workspace.delete",
    ],
    WorkspaceRole.ADMIN: [
        "workspace.settings",
        "workspace.members",
        "workspace.connections",
    ],
    WorkspaceRole.EDITOR: [
        "workspace.create_content",
    ],
    WorkspaceRole.VIEWER: [],
}


def resolve_capabilities(plan: str, role: WorkspaceRole) -> list[str]:
    """Resolve available capabilities from plan tier and workspace role.

    Plan capabilities define what the workspace can do. Role capabilities
    define what the specific user can do within that workspace.

    Args:
        plan: Subscription plan name (free, starter, pro, enterprise).
        role: User's workspace role.

    Returns:
        Sorted deduplicated list of capability strings.
    """
    plan_caps = _PLAN_CAPABILITIES.get(plan.lower(), _PLAN_CAPABILITIES["free"])
    role_caps = _ROLE_CAPABILITIES.get(role, [])
    all_caps = set(plan_caps) | set(role_caps)
    return sorted(all_caps)


# =============================================================================
# ID Validation (org ownership check)
# =============================================================================


class OrgOwnershipValidator:
    """Validates that referenced IDs belong to the authenticated org.

    This is a pluggable validator. In production, it queries Supabase to
    verify ownership. In tests, it can be replaced with a mock.

    Validates: R58.4 — invalid or cross-tenant references SHALL be silently
    dropped with a warning log.
    """

    async def validate_project(self, project_id: UUID, org_id: UUID) -> bool:
        """Check if project belongs to org. Returns True if valid."""
        try:
            from backend.database import get_supabase_client, is_supabase_configured

            if not is_supabase_configured():
                return False

            client = get_supabase_client()
            result = (
                client.table("projects")
                .select("id")
                .eq("id", str(project_id))
                .eq("org_id", str(org_id))
                .execute()
            )
            return len(result.data or []) > 0
        except Exception as exc:
            logger.warning(
                "org_ownership_check_failed",
                resource_type="project",
                resource_id=str(project_id),
                org_id=str(org_id),
                error=str(exc),
            )
            return False

    async def validate_talent(self, talent_id: UUID, org_id: UUID) -> bool:
        """Check if talent belongs to org. Returns True if valid."""
        try:
            from backend.database import get_supabase_client, is_supabase_configured

            if not is_supabase_configured():
                return False

            client = get_supabase_client()
            result = (
                client.table("ai_talent")
                .select("id")
                .eq("id", str(talent_id))
                .eq("org_id", str(org_id))
                .execute()
            )
            return len(result.data or []) > 0
        except Exception as exc:
            logger.warning(
                "org_ownership_check_failed",
                resource_type="talent",
                resource_id=str(talent_id),
                org_id=str(org_id),
                error=str(exc),
            )
            return False

    async def validate_assets(
        self, asset_ids: list[UUID], org_id: UUID
    ) -> list[UUID]:
        """Return only the asset IDs that belong to org."""
        if not asset_ids:
            return []
        try:
            from backend.database import get_supabase_client, is_supabase_configured

            if not is_supabase_configured():
                return []

            client = get_supabase_client()
            result = (
                client.table("assets")
                .select("id")
                .in_("id", [str(aid) for aid in asset_ids])
                .eq("org_id", str(org_id))
                .execute()
            )
            valid_ids = {row["id"] for row in (result.data or [])}
            return [aid for aid in asset_ids if str(aid) in valid_ids]
        except Exception as exc:
            logger.warning(
                "org_ownership_check_failed",
                resource_type="assets",
                resource_ids=[str(aid) for aid in asset_ids],
                org_id=str(org_id),
                error=str(exc),
            )
            return []

    async def validate_job(self, job_id: UUID, org_id: UUID) -> bool:
        """Check if job belongs to org. Returns True if valid."""
        try:
            from backend.database import get_supabase_client, is_supabase_configured

            if not is_supabase_configured():
                return False

            client = get_supabase_client()
            result = (
                client.table("content_jobs")
                .select("id")
                .eq("id", str(job_id))
                .eq("org_id", str(org_id))
                .execute()
            )
            return len(result.data or []) > 0
        except Exception as exc:
            logger.warning(
                "org_ownership_check_failed",
                resource_type="job",
                resource_id=str(job_id),
                org_id=str(org_id),
                error=str(exc),
            )
            return False


# Default validator instance (can be replaced in tests)
_default_validator = OrgOwnershipValidator()


# =============================================================================
# Context Builder
# =============================================================================


async def build_application_context(
    request: ApplicationContextRequest,
    tenant_context: TenantContext,
    *,
    workspace_name: str = "",
    workspace_plan: str = "free",
    validator: OrgOwnershipValidator | None = None,
) -> ApplicationContext:
    """Build a fully populated ApplicationContext from client request + TenantContext.

    This function:
      1. Server-derives org_id, user_id, role, trust_domain from TenantContext (R58.3)
      2. Validates all referenced IDs belong to the authenticated org_id (R58.4)
      3. Silently drops invalid/cross-tenant references with warning log (R58.4)
      4. Resolves capabilities from role and plan
      5. Returns a fully populated ApplicationContext

    Args:
        request: Client-supplied context request (page, IDs, mode, state).
        tenant_context: Server-resolved tenant context from JWT validation.
        workspace_name: Organisation display name (resolved server-side).
        workspace_plan: Subscription plan name (resolved server-side).
        validator: Optional custom validator (for testing).

    Returns:
        A fully populated ApplicationContext with all server-derived fields
        set from TenantContext and all referenced IDs validated.
    """
    owv = validator or _default_validator
    org_id = tenant_context.org_id
    dropped: list[str] = []

    # Validate active_project_id
    validated_project_id: UUID | None = None
    if request.active_project_id:
        if await owv.validate_project(request.active_project_id, org_id):
            validated_project_id = request.active_project_id
        else:
            dropped.append(f"project:{request.active_project_id}")
            logger.warning(
                "application_context_reference_dropped",
                extra={
                    "resource_type": "project",
                    "resource_id": str(request.active_project_id),
                    "org_id": str(org_id),
                    "user_id": str(tenant_context.user_id),
                    "reason": "cross_tenant_or_not_found",
                },
            )

    # Validate selected_talent_id
    validated_talent_id: UUID | None = None
    if request.selected_talent_id:
        if await owv.validate_talent(request.selected_talent_id, org_id):
            validated_talent_id = request.selected_talent_id
        else:
            dropped.append(f"talent:{request.selected_talent_id}")
            logger.warning(
                "application_context_reference_dropped",
                extra={
                    "resource_type": "talent",
                    "resource_id": str(request.selected_talent_id),
                    "org_id": str(org_id),
                    "user_id": str(tenant_context.user_id),
                    "reason": "cross_tenant_or_not_found",
                },
            )

    # Validate selected_asset_ids
    validated_asset_ids: list[UUID] = []
    if request.selected_asset_ids:
        validated_asset_ids = await owv.validate_assets(
            request.selected_asset_ids, org_id
        )
        invalid_assets = set(request.selected_asset_ids) - set(validated_asset_ids)
        for invalid_id in invalid_assets:
            dropped.append(f"asset:{invalid_id}")
            logger.warning(
                "application_context_reference_dropped",
                extra={
                    "resource_type": "asset",
                    "resource_id": str(invalid_id),
                    "org_id": str(org_id),
                    "user_id": str(tenant_context.user_id),
                    "reason": "cross_tenant_or_not_found",
                },
            )

    # Validate active_job_id
    validated_job_id: UUID | None = None
    if request.active_job_id:
        if await owv.validate_job(request.active_job_id, org_id):
            validated_job_id = request.active_job_id
        else:
            dropped.append(f"job:{request.active_job_id}")
            logger.warning(
                "application_context_reference_dropped",
                extra={
                    "resource_type": "job",
                    "resource_id": str(request.active_job_id),
                    "org_id": str(org_id),
                    "user_id": str(tenant_context.user_id),
                    "reason": "cross_tenant_or_not_found",
                },
            )

    # Resolve capabilities
    capabilities = resolve_capabilities(workspace_plan, tenant_context.role)

    return ApplicationContext(
        workspace=WorkspaceContextInfo(
            org_id=org_id,
            name=workspace_name,
            plan=workspace_plan,
        ),
        user=UserContextInfo(
            user_id=tenant_context.user_id,
            role=tenant_context.role,
            trust_domain=tenant_context.trust_domain,
        ),
        current_page=request.current_page,
        active_project_id=validated_project_id,
        selected_talent_id=validated_talent_id,
        selected_asset_ids=validated_asset_ids,
        active_job_id=validated_job_id,
        active_brain_mode=request.active_brain_mode,
        capabilities=capabilities,
        workflow_state=request.workflow_state,
        ui_state=request.ui_state,
        context_version=request.context_version,
        dropped_references=dropped,
    )

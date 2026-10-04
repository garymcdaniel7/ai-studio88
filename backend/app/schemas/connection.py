"""Pydantic v2 schemas for Connections Hub.

Request/response schemas for creating, updating, and listing connections.
Connections represent workspace or user integrations with external services.

Validates: Requirements R85.1, R85.3, R85.4, R92.1, R92.2, R92.3
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema, PaginatedResponse, TimestampedSchema
from app.services.platform_registry import PlatformAvailability

# =============================================================================
# Enums (mirrored from ORM for schema-level validation)
# =============================================================================


class ConnectionOwnershipEnum(str, Enum):
    """Connection ownership classification."""

    USER = "user"
    WORKSPACE = "workspace"


class ConnectionLifecycleEnum(str, Enum):
    """Connection lifecycle states."""

    CONNECTING = "connecting"
    CONNECTED = "connected"
    DEGRADED = "degraded"
    REAUTH_REQUIRED = "reauth_required"
    DISCONNECTED = "disconnected"
    REVOKED = "revoked"


class ConnectionCategoryEnum(str, Enum):
    """Connection category."""

    AI_PROVIDER = "ai_provider"
    STORAGE = "storage"
    SOCIAL = "social"
    COMPUTE = "compute"
    DEVELOPER = "developer"
    BUSINESS = "business"


class ConnectionAuthMethodEnum(str, Enum):
    """Supported authentication methods."""

    OAUTH = "oauth"
    API_KEY = "api_key"
    SSH = "ssh"
    MCP = "mcp"


# =============================================================================
# Request Schemas
# =============================================================================


class ConnectionCreate(BaseSchema):
    """Request schema for creating a connection.

    org_id is NEVER accepted from client — resolved from TenantContext.
    user_id is set from JWT for USER connections.
    """

    ownership: ConnectionOwnershipEnum = Field(
        ...,
        description="Connection ownership: user (personal) or workspace (shared)",
    )
    category: ConnectionCategoryEnum = Field(
        ...,
        description="Connection category",
    )
    provider_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Provider identifier (e.g. 'openai', 'instagram', 'runpod')",
    )
    display_name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Human-readable display name",
    )
    auth_method: ConnectionAuthMethodEnum = Field(
        ...,
        description="Authentication method for this connection",
    )
    oauth_token_ref: UUID | None = Field(
        default=None,
        description="Reference to encrypted token in workspace_credentials",
    )
    capabilities: list[str] = Field(
        default_factory=list,
        description="Discovered provider capabilities",
    )
    allowed_roles: list[str] = Field(
        default_factory=lambda: ["owner", "admin", "editor"],
        description="Roles allowed to use this connection",
    )
    tool_policy: dict = Field(
        default_factory=dict,
        description="Per-tool allow/deny policy",
    )


class ConnectionUpdate(BaseSchema):
    """Request schema for updating a connection (PATCH — partial update).

    All fields Optional. Only provided fields are updated.
    """

    display_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="Human-readable display name",
    )
    lifecycle_state: ConnectionLifecycleEnum | None = Field(
        default=None,
        description="Updated lifecycle state",
    )
    capabilities: list[str] | None = Field(
        default=None,
        description="Updated capabilities list",
    )
    allowed_roles: list[str] | None = Field(
        default=None,
        description="Updated allowed roles",
    )
    tool_policy: dict | None = Field(
        default=None,
        description="Updated per-tool allow/deny policy",
    )
    health_status: str | None = Field(
        default=None,
        max_length=30,
        description="Health check result",
    )


class ConnectionHealthUpdate(BaseSchema):
    """Request schema for updating connection health status."""

    health_status: str = Field(
        ...,
        min_length=1,
        max_length=30,
        description="Health check result: healthy, degraded, unreachable",
    )


# =============================================================================
# Response Schemas
# =============================================================================


class ConnectionResponse(TimestampedSchema):
    """Response schema for a single connection."""

    id: UUID
    org_id: UUID
    user_id: UUID | None = None
    ownership: ConnectionOwnershipEnum
    category: ConnectionCategoryEnum
    provider_name: str
    display_name: str
    lifecycle_state: ConnectionLifecycleEnum
    auth_method: ConnectionAuthMethodEnum
    oauth_token_ref: UUID | None = None
    capabilities: list = Field(default_factory=list)
    allowed_roles: list[str] = Field(default_factory=list)
    tool_policy: dict = Field(default_factory=dict)
    last_health_check_at: datetime | None = None
    health_status: str | None = None


class ConnectionListResponse(PaginatedResponse):
    """Paginated list of connections."""

    items: list[ConnectionResponse]  # type: ignore[assignment]


class PlatformPolicySchema(BaseSchema):
    """Client-safe platform publishing requirements."""

    ai_label_required: bool = False
    watermark_required: bool = False
    caption_disclosure_required: bool = False
    nsfw_allowed: bool = False
    age_verification_required: bool = False
    consent_identity_required: bool = False
    verified_creator_required: bool = False
    reasonable_person_moderation_required: bool = False
    explicit_publish_confirmation_required: bool = True


class PlatformCapabilityResponse(BaseSchema):
    """Client-safe platform rollout and capability metadata."""

    platform: str
    display_name: str
    lane: str
    availability: PlatformAvailability
    enabled: bool
    verified: bool
    oauth_supported: bool
    capabilities: list[str]
    policy: PlatformPolicySchema
    allowed_roles: list[str]


class PlatformListResponse(BaseSchema):
    """List of registered publishing destinations."""

    platforms: list[PlatformCapabilityResponse]


class PublishPolicyRequest(BaseSchema):
    """Evidence submitted before a publish operation is allowed."""

    ai_generated: bool = True
    ai_label_present: bool = False
    watermark_present: bool = False
    caption_disclosure_present: bool = False
    age_verified: bool = False
    consent_verified: bool = False
    identity_verified: bool = False
    verified_creator: bool = False
    moderation_passed: bool = False
    publish_confirmed: bool = False
    is_nsfw: bool = False


class PublishPolicyResponse(BaseSchema):
    """Successful publish-policy decision."""

    allowed: bool
    platform: str
    missing_requirements: list[str]
    capabilities: list[str]

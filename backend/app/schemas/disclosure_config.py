"""Pydantic v2 schemas for Workspace Disclosure Configuration.

Covers workspace-level disclosure hook settings and the disclosure
preview endpoint — showing users exactly what disclosures will be
attached before publishing.

Requirements: R80.1, R80.2, R80.3, R80.4, R80.5, R80.6
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema


# =============================================================================
# Enums
# =============================================================================


class DisclosureHookType(str, Enum):
    """Types of disclosure hooks that can fire at publish time.

    Requirements: R80.1
    """

    AI_SYNTHETIC = "AI_SYNTHETIC"
    SPONSORSHIP_COMMERCIAL = "SPONSORSHIP_COMMERCIAL"
    PROVENANCE_C2PA = "PROVENANCE_C2PA"
    PLATFORM_SPECIFIC = "PLATFORM_SPECIFIC"


# =============================================================================
# Request Schemas
# =============================================================================


class DisclosureConfigUpdateRequest(BaseSchema):
    """Request to update workspace disclosure configuration.

    All fields are optional — only provided fields are updated.
    org_id is NEVER accepted from client — resolved from TenantContext.

    Requirements: R80.2, R80.3
    """

    ai_disclosure_enabled: bool | None = Field(
        default=None, description="Enable AI/synthetic media disclosure"
    )
    ai_disclosure_text: str | None = Field(
        default=None,
        max_length=500,
        description="Text to include for AI disclosure (e.g., 'This content was created with AI')",
    )
    sponsorship_disclosure_enabled: bool | None = Field(
        default=None, description="Enable sponsorship/commercial disclosure (FTC/ASA)"
    )
    sponsorship_text: str | None = Field(
        default=None,
        max_length=500,
        description="Text to include for sponsorship disclosure (e.g., '#Ad #Sponsored')",
    )
    disclosure_tags: list[str] | None = Field(
        default=None,
        max_length=20,
        description="Hashtags/tags to add for disclosure (e.g., ['#AIGenerated', '#Sponsored'])",
    )
    platform_requirements: dict | None = Field(
        default=None,
        description=(
            "Platform-specific disclosure requirements as JSON. "
            "Keys are platform names, values are disclosure config per platform."
        ),
    )
    c2pa_enabled: bool | None = Field(
        default=None, description="Enable C2PA/Content Credentials provenance metadata"
    )


class DisclosurePreviewRequest(BaseSchema):
    """Request a preview of what disclosures will be applied to a post.

    Simulates the disclosure evaluation without actually publishing.

    Requirements: R80.5
    """

    platform: str = Field(
        ..., min_length=1, max_length=50, description="Target platform (instagram, tiktok, etc.)"
    )
    caption: str = Field(
        default="", max_length=2200, description="Current post caption"
    )
    is_sponsored: bool = Field(
        default=False, description="Whether this post is sponsored/commercial content"
    )
    asset_id: UUID | None = Field(
        default=None, description="Asset being published (for provenance lookup)"
    )


# =============================================================================
# Response Schemas
# =============================================================================


class DisclosureConfigResponse(BaseSchema):
    """Response containing the workspace disclosure configuration."""

    id: UUID
    org_id: UUID
    ai_disclosure_enabled: bool
    ai_disclosure_text: str | None = None
    sponsorship_disclosure_enabled: bool
    sponsorship_text: str | None = None
    disclosure_tags: list[str] | None = None
    platform_requirements: dict | None = None
    c2pa_enabled: bool
    created_at: datetime
    updated_at: datetime


class DisclosureHookResult(BaseSchema):
    """A single disclosure hook evaluation result."""

    hook_type: DisclosureHookType = Field(description="Type of disclosure hook")
    triggered: bool = Field(description="Whether this hook was triggered")
    text: str | None = Field(default=None, description="Disclosure text to include")
    tags: list[str] = Field(default_factory=list, description="Tags to add to the post")
    metadata: dict = Field(
        default_factory=dict,
        description="Additional metadata (e.g., C2PA manifest reference, platform label)",
    )
    reason: str = Field(description="Why this hook was triggered or skipped")


class DisclosurePreviewResponse(BaseSchema):
    """Response showing what disclosures would be applied to a post.

    Requirements: R80.5
    """

    hooks_evaluated: list[DisclosureHookResult] = Field(
        description="All hooks that were evaluated"
    )
    final_caption: str = Field(
        description="Caption with disclosure text appended"
    )
    final_tags: list[str] = Field(
        default_factory=list, description="All tags (original + disclosure tags)"
    )
    c2pa_attached: bool = Field(
        default=False, description="Whether C2PA metadata would be attached"
    )
    platform: str = Field(description="Target platform this preview is for")
    summary: str = Field(
        description="Human-readable summary of all disclosures applied"
    )

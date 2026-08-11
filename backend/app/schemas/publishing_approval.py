"""Pydantic v2 schemas for Publishing Approval Binding.

Publishing approvals bind to an exact package state: asset version (checksum),
caption, destination, schedule, targeting, consent state, disclosure settings,
and policy state. Any change to a bound element after approval invalidates it
and requires re-evaluation.

Requirements: R79.1, R79.2, R79.3, R79.4, R79.5, R79.6
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema


# =============================================================================
# Sub-schemas (elements of the approved package)
# =============================================================================


class DestinationSnapshot(BaseSchema):
    """Destination platform and account for publishing."""

    platform: str = Field(..., min_length=1, max_length=50, description="Target platform")
    account_id: str | None = Field(
        default=None, max_length=255, description="Platform account identifier"
    )
    post_type: str = Field(
        default="image", max_length=50, description="Content type (image, video, reel, story)"
    )


class ScheduleSnapshot(BaseSchema):
    """Scheduling state at time of approval."""

    scheduled_at: datetime | None = Field(
        default=None, description="Scheduled publish time (NULL = immediate)"
    )
    timezone: str | None = Field(
        default=None, max_length=64, description="Timezone for scheduled_at"
    )


class TargetingSnapshot(BaseSchema):
    """Targeting/audience configuration at time of approval."""

    audience_tags: list[str] = Field(
        default_factory=list, description="Audience targeting tags"
    )
    geo_targeting: list[str] = Field(
        default_factory=list, description="Geographic targeting regions"
    )
    age_range: dict | None = Field(
        default=None, description="Age range targeting (min/max)"
    )


class ConsentStateSnapshot(BaseSchema):
    """Consent state for all talent referenced at approval time."""

    talent_id: UUID = Field(..., description="Talent this consent applies to")
    active_scopes: list[str] = Field(
        default_factory=list, description="Active consent scopes at approval time"
    )
    consent_record_ids: list[UUID] = Field(
        default_factory=list, description="IDs of active consent records"
    )
    verified_at: datetime | None = Field(
        default=None, description="When consent was last verified"
    )


class DisclosureSettingsSnapshot(BaseSchema):
    """Disclosure/transparency settings at approval time."""

    ai_disclosure_enabled: bool = Field(
        default=True, description="Whether AI disclosure is required"
    )
    disclosure_text: str | None = Field(
        default=None, max_length=500, description="Disclosure text to include"
    )
    disclosure_tags: list[str] = Field(
        default_factory=list, description="Disclosure hashtags/tags"
    )
    platform_disclosure_format: str | None = Field(
        default=None, max_length=100, description="Platform-specific disclosure format"
    )


class PolicyStateSnapshot(BaseSchema):
    """Policy/governance state at approval time."""

    workspace_privacy_restrictions: list[str] = Field(
        default_factory=list, description="Active privacy restrictions"
    )
    content_policy_version: str | None = Field(
        default=None, max_length=50, description="Content policy version applied"
    )
    safety_check_passed: bool = Field(
        default=False, description="Whether safety kernel check passed"
    )
    governance_decision_id: str | None = Field(
        default=None, max_length=100, description="Governance boundary decision reference"
    )


# =============================================================================
# Request Schemas
# =============================================================================


class PublishingApprovalCreateRequest(BaseSchema):
    """Request to create a publishing approval binding.

    Binds the exact current state of all elements into an immutable record.
    org_id is NEVER accepted from client — resolved from TenantContext.
    """

    asset_id: UUID = Field(..., description="UUID of the asset to publish")
    asset_checksum: str = Field(
        ..., min_length=8, max_length=128, description="SHA-256 checksum of the asset binary"
    )
    caption: str = Field(
        default="", max_length=2200, description="Post caption text"
    )
    destination: DestinationSnapshot = Field(
        ..., description="Publishing destination"
    )
    schedule: ScheduleSnapshot = Field(
        default_factory=ScheduleSnapshot, description="Scheduling configuration"
    )
    targeting: TargetingSnapshot = Field(
        default_factory=TargetingSnapshot, description="Audience targeting"
    )
    consent_state: list[ConsentStateSnapshot] = Field(
        default_factory=list, description="Consent state for all referenced talent"
    )
    disclosure_settings: DisclosureSettingsSnapshot = Field(
        default_factory=DisclosureSettingsSnapshot, description="Disclosure/transparency settings"
    )
    policy_state: PolicyStateSnapshot = Field(
        default_factory=PolicyStateSnapshot, description="Policy/governance state"
    )
    talent_id: UUID | None = Field(
        default=None, description="Optional talent ID associated with the content"
    )
    project_id: UUID | None = Field(
        default=None, description="Optional project ID for the content"
    )


class PublishingApprovalVerifyRequest(BaseSchema):
    """Request to verify an approval is still valid at publish time.

    Provides current state of all bound elements for comparison.
    """

    asset_checksum: str = Field(
        ..., min_length=8, max_length=128, description="Current SHA-256 checksum of the asset"
    )
    caption: str = Field(default="", max_length=2200, description="Current caption text")
    destination: DestinationSnapshot = Field(
        ..., description="Current destination"
    )
    schedule: ScheduleSnapshot = Field(
        default_factory=ScheduleSnapshot, description="Current schedule"
    )
    targeting: TargetingSnapshot = Field(
        default_factory=TargetingSnapshot, description="Current targeting"
    )
    consent_state: list[ConsentStateSnapshot] = Field(
        default_factory=list, description="Current consent state"
    )
    disclosure_settings: DisclosureSettingsSnapshot = Field(
        default_factory=DisclosureSettingsSnapshot, description="Current disclosure settings"
    )
    policy_state: PolicyStateSnapshot = Field(
        default_factory=PolicyStateSnapshot, description="Current policy state"
    )


# =============================================================================
# Response Schemas
# =============================================================================


class PublishingApprovalResponse(BaseSchema):
    """Response for a single publishing approval record."""

    id: UUID
    org_id: UUID
    asset_id: UUID
    asset_checksum: str
    caption: str
    destination: DestinationSnapshot
    schedule: ScheduleSnapshot
    targeting: TargetingSnapshot
    consent_state: list[ConsentStateSnapshot]
    disclosure_settings: DisclosureSettingsSnapshot
    policy_state: PolicyStateSnapshot
    talent_id: UUID | None = None
    project_id: UUID | None = None
    package_hash: str = Field(description="SHA-256 hash of the entire approved package")
    approved_by: UUID
    approved_at: datetime
    invalidated_at: datetime | None = None
    invalidation_reason: str | None = None
    is_valid: bool
    created_at: datetime
    updated_at: datetime


class PublishingApprovalVerifyResponse(BaseSchema):
    """Response from verifying an approval against current state."""

    approval_id: UUID
    is_valid: bool
    mismatched_fields: list[str] = Field(
        default_factory=list, description="Fields that differ from approved state"
    )
    invalidation_reason: str | None = None
    approved_at: datetime
    message: str = Field(description="Human-readable verification result")


class PublishingApprovalListResponse(BaseSchema):
    """Paginated list of publishing approvals."""

    items: list[PublishingApprovalResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)

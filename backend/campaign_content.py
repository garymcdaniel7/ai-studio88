"""Campaign Content Items & Platform Variants — Story 122.

One canonical campaign content item owns shared creative intent. Platform-
specific variants own destination truth with independent approval and execution.

Model:
    ContentItem (canonical source)
        ├── PlatformVariant[instagram]
        ├── PlatformVariant[tiktok]
        └── PlatformVariant[youtube]

Field inheritance per variant:
    INHERIT  — use the value from the canonical content item
    OVERRIDE — use a platform-specific value
    RESET    — clear to platform default

Rules:
    - Variants have independent approval/execution lifecycle
    - Source edits do NOT silently rewrite approved historical variants
    - Cross-workspace assets/accounts rejected
    - Each variant links to exact source asset and context versions

DECISION-REQUIRED:
    - Which platforms are supported (currently: instagram, tiktok, youtube, twitter, linkedin)
    - Platform-specific field constraints (character limits, media formats)
    - Whether shared caption changes propagate to unapproved variants
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================


class Platform(str, Enum):
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"
    YOUTUBE = "youtube"
    TWITTER = "twitter"
    LINKEDIN = "linkedin"


class FieldAction(str, Enum):
    INHERIT = "inherit"
    OVERRIDE = "override"
    RESET = "reset"


class VariantStatus(str, Enum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ContentItemStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


# =============================================================================
# Variant Field
# =============================================================================


@dataclass
class VariantField:
    """A single field in a variant with explicit action."""
    name: str
    action: FieldAction
    source_value: Any = None      # From content item (at creation time)
    override_value: Any = None    # Platform-specific value
    default_value: Any = None     # Platform default (for RESET)

    @property
    def effective_value(self) -> Any:
        if self.action == FieldAction.INHERIT:
            return self.source_value
        elif self.action == FieldAction.OVERRIDE:
            return self.override_value
        elif self.action == FieldAction.RESET:
            return self.default_value
        return self.source_value


# =============================================================================
# Platform Variant
# =============================================================================


@dataclass
class PlatformVariant:
    """A platform-specific variant of a content item."""
    variant_id: str = field(default_factory=lambda: f"var-{uuid.uuid4().hex[:12]}")
    content_item_id: str = ""
    org_id: str = ""
    platform: Platform = Platform.INSTAGRAM

    # Fields with inheritance tracking
    fields: dict[str, VariantField] = field(default_factory=dict)

    # Platform-specific
    account_id: str = ""          # Which account to publish from
    media_asset_ids: list[str] = field(default_factory=list)
    format_spec: dict[str, Any] = field(default_factory=dict)  # dimensions, aspect ratio

    # Lifecycle (independent per variant)
    status: VariantStatus = VariantStatus.DRAFT
    approved_by: str | None = None
    approved_at: float | None = None
    published_at: float | None = None
    execution_ref: str | None = None  # Provider post ID

    # Lineage (frozen at creation — source edits don't change this)
    source_asset_version: str = ""
    source_context_id: str = ""
    created_at: float = field(default_factory=time.time)

    # Version
    version: int = 1

    @property
    def inherited_fields(self) -> list[str]:
        return [n for n, f in self.fields.items() if f.action == FieldAction.INHERIT]

    @property
    def overridden_fields(self) -> list[str]:
        return [n for n, f in self.fields.items() if f.action == FieldAction.OVERRIDE]

    @property
    def is_terminal(self) -> bool:
        return self.status in (VariantStatus.PUBLISHED, VariantStatus.CANCELLED)


# =============================================================================
# Content Item (canonical source)
# =============================================================================


SHARED_FIELDS = {"caption", "hashtags", "cta", "disclosure", "brand_id", "talent_id"}


@dataclass
class ContentItem:
    """Canonical campaign content item — the source of truth."""
    item_id: str = field(default_factory=lambda: f"ci-{uuid.uuid4().hex[:12]}")
    org_id: str = ""
    campaign_id: str = ""
    project_id: str = ""
    brand_id: str = ""
    creator_id: str = ""

    # Shared content (inherited by variants unless overridden)
    caption: str = ""
    hashtags: list[str] = field(default_factory=list)
    cta: str = ""                 # Call to action
    disclosure: str = ""          # Paid partnership / ad disclosure

    # Source lineage
    source_asset_ids: list[str] = field(default_factory=list)
    source_context_id: str = ""   # Generation/context package reference
    talent_id: str = ""

    # Status
    status: ContentItemStatus = ContentItemStatus.DRAFT

    # Variants
    variants: dict[Platform, PlatformVariant] = field(default_factory=dict)

    # Versioning
    version: int = 1
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @property
    def variant_count(self) -> int:
        return len(self.variants)

    @property
    def shared_values(self) -> dict[str, Any]:
        """Get current shared field values (for inheritance)."""
        return {
            "caption": self.caption,
            "hashtags": self.hashtags,
            "cta": self.cta,
            "disclosure": self.disclosure,
            "brand_id": self.brand_id,
            "talent_id": self.talent_id,
        }


# =============================================================================
# Store
# =============================================================================

_items: dict[str, ContentItem] = {}
_variant_index: dict[str, str] = {}  # variant_id → item_id


# =============================================================================
# Content Item API
# =============================================================================


def create_content_item(
    org_id: str,
    campaign_id: str,
    creator_id: str,
    caption: str = "",
    hashtags: list[str] | None = None,
    cta: str = "",
    disclosure: str = "",
    source_asset_ids: list[str] | None = None,
    source_context_id: str = "",
    brand_id: str = "",
    talent_id: str = "",
    project_id: str = "",
) -> ContentItem:
    """Create a canonical campaign content item."""
    if not org_id or not creator_id:
        raise ValueError("org_id and creator_id are required")

    item = ContentItem(
        org_id=org_id,
        campaign_id=campaign_id,
        project_id=project_id,
        brand_id=brand_id,
        creator_id=creator_id,
        caption=caption,
        hashtags=hashtags or [],
        cta=cta,
        disclosure=disclosure,
        source_asset_ids=source_asset_ids or [],
        source_context_id=source_context_id,
        talent_id=talent_id,
        status=ContentItemStatus.ACTIVE,
    )

    _items[item.item_id] = item
    logger.info(f"CONTENT_ITEM_CREATED: id={item.item_id} campaign={campaign_id}")
    return item


def update_content_item(
    item_id: str,
    org_id: str,
    updates: dict[str, Any],
) -> ContentItem:
    """Update shared fields on a content item.

    NOTE: This does NOT retroactively change approved variants.
    Approved variants retain their frozen inherited values.
    """
    item = _get_item(item_id, org_id)
    for key, value in updates.items():
        if hasattr(item, key) and key in SHARED_FIELDS:
            setattr(item, key, value)
    item.version += 1
    item.updated_at = time.time()
    return item


# =============================================================================
# Platform Variant API
# =============================================================================


def create_variant(
    item_id: str,
    org_id: str,
    platform: Platform,
    account_id: str = "",
    field_overrides: dict[str, dict[str, Any]] | None = None,
    media_asset_ids: list[str] | None = None,
    format_spec: dict[str, Any] | None = None,
) -> PlatformVariant:
    """Create a platform-specific variant for a content item.

    Fields default to INHERIT. Override/reset specified explicitly.
    Source values are frozen at creation time (source edits don't change them).
    """
    item = _get_item(item_id, org_id)

    # Prevent duplicate platform variant
    if platform in item.variants:
        return item.variants[platform]  # Idempotent

    # Build fields with explicit actions
    shared = item.shared_values
    fields: dict[str, VariantField] = {}
    overrides = field_overrides or {}

    for field_name, source_value in shared.items():
        spec = overrides.get(field_name, {})
        action = FieldAction(spec.get("action", "inherit"))
        fields[field_name] = VariantField(
            name=field_name,
            action=action,
            source_value=source_value,  # Frozen at this moment
            override_value=spec.get("value") if action == FieldAction.OVERRIDE else None,
            default_value=None,
        )

    variant = PlatformVariant(
        content_item_id=item_id,
        org_id=org_id,
        platform=platform,
        account_id=account_id,
        fields=fields,
        media_asset_ids=media_asset_ids or list(item.source_asset_ids),
        format_spec=format_spec or {},
        source_asset_version=f"v{item.version}",
        source_context_id=item.source_context_id,
    )

    item.variants[platform] = variant
    _variant_index[variant.variant_id] = item_id

    logger.info(f"VARIANT_CREATED: id={variant.variant_id} platform={platform.value} item={item_id}")
    return variant


def update_variant(
    variant_id: str,
    org_id: str,
    field_updates: dict[str, dict[str, Any]] | None = None,
    account_id: str | None = None,
    media_asset_ids: list[str] | None = None,
) -> PlatformVariant:
    """Update a variant's fields or settings."""
    variant = _get_variant(variant_id, org_id)

    if variant.status in (VariantStatus.PUBLISHED, VariantStatus.CANCELLED):
        raise VariantImmutable("Cannot update a published or cancelled variant")

    if field_updates:
        for field_name, spec in field_updates.items():
            if field_name in variant.fields:
                action = FieldAction(spec.get("action", "override"))
                variant.fields[field_name].action = action
                if action == FieldAction.OVERRIDE:
                    variant.fields[field_name].override_value = spec.get("value")

    if account_id is not None:
        variant.account_id = account_id
    if media_asset_ids is not None:
        variant.media_asset_ids = media_asset_ids

    variant.version += 1
    return variant


# =============================================================================
# Variant Lifecycle (independent per variant)
# =============================================================================


def approve_variant(variant_id: str, org_id: str, approver_id: str) -> PlatformVariant:
    """Approve a variant for scheduling/publishing."""
    variant = _get_variant(variant_id, org_id)

    if variant.status == VariantStatus.APPROVED:
        return variant  # Idempotent

    if variant.status not in (VariantStatus.DRAFT, VariantStatus.PENDING_APPROVAL):
        raise InvalidVariantState(f"Cannot approve from state {variant.status.value}")

    variant.status = VariantStatus.APPROVED
    variant.approved_by = approver_id
    variant.approved_at = time.time()
    return variant


def schedule_variant(variant_id: str, org_id: str, schedule_time: float) -> PlatformVariant:
    """Schedule an approved variant for publishing."""
    variant = _get_variant(variant_id, org_id)
    if variant.status != VariantStatus.APPROVED:
        raise InvalidVariantState("Must be approved before scheduling")
    variant.status = VariantStatus.SCHEDULED
    return variant


def publish_variant(variant_id: str, org_id: str, execution_ref: str) -> PlatformVariant:
    """Mark variant as published with provider reference."""
    variant = _get_variant(variant_id, org_id)
    if variant.status not in (VariantStatus.APPROVED, VariantStatus.SCHEDULED):
        raise InvalidVariantState(f"Cannot publish from state {variant.status.value}")
    variant.status = VariantStatus.PUBLISHED
    variant.published_at = time.time()
    variant.execution_ref = execution_ref
    return variant


def cancel_variant(variant_id: str, org_id: str) -> PlatformVariant:
    """Cancel a variant."""
    variant = _get_variant(variant_id, org_id)
    if variant.is_terminal:
        return variant  # Idempotent
    variant.status = VariantStatus.CANCELLED
    return variant


# =============================================================================
# Lineage & Query
# =============================================================================


def get_content_item(item_id: str, org_id: str) -> ContentItem | None:
    """Get content item with tenant isolation."""
    item = _items.get(item_id)
    if not item or item.org_id != org_id:
        return None
    return item


def get_variant(variant_id: str, org_id: str) -> PlatformVariant | None:
    """Get variant with tenant isolation."""
    item_id = _variant_index.get(variant_id)
    if not item_id:
        return None
    item = _items.get(item_id)
    if not item or item.org_id != org_id:
        return None
    for v in item.variants.values():
        if v.variant_id == variant_id:
            return v
    return None


def get_variant_lineage(variant_id: str, org_id: str) -> dict[str, Any] | None:
    """Get full lineage for a variant — traces back to source."""
    variant = get_variant(variant_id, org_id)
    if not variant:
        return None
    item = _items.get(variant.content_item_id)
    if not item:
        return None

    return {
        "variant_id": variant.variant_id,
        "platform": variant.platform.value,
        "content_item_id": item.item_id,
        "campaign_id": item.campaign_id,
        "source_asset_ids": item.source_asset_ids,
        "source_context_id": variant.source_context_id,
        "source_asset_version": variant.source_asset_version,
        "inherited_fields": variant.inherited_fields,
        "overridden_fields": variant.overridden_fields,
    }


# =============================================================================
# Legacy Migration
# =============================================================================


def migrate_calendar_entry(
    org_id: str,
    creator_id: str,
    platform: str,
    caption: str,
    campaign_id: str = "",
    asset_ids: list[str] | None = None,
) -> ContentItem:
    """Migrate a legacy single-platform calendar entry to the new model.

    Creates a content item + one variant for the specified platform.
    """
    item = create_content_item(
        org_id=org_id,
        campaign_id=campaign_id,
        creator_id=creator_id,
        caption=caption,
        source_asset_ids=asset_ids or [],
    )

    try:
        plat = Platform(platform.lower())
    except ValueError:
        plat = Platform.INSTAGRAM  # Default for unknown

    create_variant(item.item_id, org_id, plat)
    return item


# =============================================================================
# Helpers
# =============================================================================


def _get_item(item_id: str, org_id: str) -> ContentItem:
    item = _items.get(item_id)
    if not item or item.org_id != org_id:
        raise ContentItemNotFound(f"Content item {item_id} not found")
    return item


def _get_variant(variant_id: str, org_id: str) -> PlatformVariant:
    item_id = _variant_index.get(variant_id)
    if not item_id:
        raise VariantNotFound(f"Variant {variant_id} not found")
    item = _items.get(item_id)
    if not item or item.org_id != org_id:
        raise VariantNotFound(f"Variant {variant_id} not found")
    for v in item.variants.values():
        if v.variant_id == variant_id:
            return v
    raise VariantNotFound(f"Variant {variant_id} not found")


# =============================================================================
# Exceptions
# =============================================================================


class CampaignContentError(Exception):
    """Base error."""


class ContentItemNotFound(CampaignContentError):
    """Not found or cross-tenant."""


class VariantNotFound(CampaignContentError):
    """Variant not found or cross-tenant."""


class VariantImmutable(CampaignContentError):
    """Cannot modify published/cancelled variant."""


class InvalidVariantState(CampaignContentError):
    """Invalid state transition."""


# =============================================================================
# Testing Support
# =============================================================================


def _reset_store() -> None:
    _items.clear()
    _variant_index.clear()

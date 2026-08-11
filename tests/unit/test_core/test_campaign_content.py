"""Campaign content items & platform variants tests — Story 122.

Tests prove:
  - Cross-tenant rejected
  - Variant inherits source values
  - Variant override uses platform-specific value
  - Variant reset uses default
  - Independent approval per variant
  - Source edit doesn't rewrite approved historical variant
  - Legacy migration creates item + variant
  - Lineage traces variant → content item → assets → context
  - Duplicate variant creation idempotent
  - Published variant immutable
"""

import pytest

from backend.campaign_content import (
    ContentItemNotFound,
    FieldAction,
    InvalidVariantState,
    Platform,
    VariantImmutable,
    VariantStatus,
    _reset_store,
    approve_variant,
    cancel_variant,
    create_content_item,
    create_variant,
    get_content_item,
    get_variant,
    get_variant_lineage,
    migrate_calendar_entry,
    publish_variant,
    update_content_item,
    update_variant,
)


@pytest.fixture(autouse=True)
def clean():
    _reset_store()
    yield
    _reset_store()


ORG = "org-test-001"
OTHER_ORG = "org-other-999"
USER = "user-001"


def _create_item(**overrides) -> str:
    defaults = dict(
        org_id=ORG, campaign_id="camp-001", creator_id=USER,
        caption="Check out our new collection! #fashion",
        hashtags=["fashion", "style"],
        cta="Shop now",
        disclosure="Paid partnership",
        source_asset_ids=["ast-001", "ast-002"],
        source_context_id="ctx-001",
        brand_id="brand-001",
        talent_id="talent-001",
    )
    defaults.update(overrides)
    item = create_content_item(**defaults)
    return item.item_id


# =============================================================================
# Cross-Tenant
# =============================================================================


@pytest.mark.unit
class TestCrossTenant:

    def test_cross_tenant_get_returns_none(self):
        item_id = _create_item()
        assert get_content_item(item_id, OTHER_ORG) is None

    def test_cross_tenant_create_variant_raises(self):
        item_id = _create_item()
        with pytest.raises(ContentItemNotFound):
            create_variant(item_id, OTHER_ORG, Platform.INSTAGRAM)

    def test_cross_tenant_approve_raises(self):
        item_id = _create_item()
        variant = create_variant(item_id, ORG, Platform.INSTAGRAM)
        with pytest.raises(Exception):
            approve_variant(variant.variant_id, OTHER_ORG, "hacker")


# =============================================================================
# Field Inheritance
# =============================================================================


@pytest.mark.unit
class TestFieldInheritance:

    def test_inherit_uses_source_value(self):
        item_id = _create_item(caption="Shared caption")
        variant = create_variant(item_id, ORG, Platform.INSTAGRAM)
        assert variant.fields["caption"].action == FieldAction.INHERIT
        assert variant.fields["caption"].effective_value == "Shared caption"

    def test_override_uses_platform_value(self):
        item_id = _create_item(caption="Shared caption")
        variant = create_variant(item_id, ORG, Platform.TIKTOK, field_overrides={
            "caption": {"action": "override", "value": "TikTok specific! #fyp"},
        })
        assert variant.fields["caption"].action == FieldAction.OVERRIDE
        assert variant.fields["caption"].effective_value == "TikTok specific! #fyp"

    def test_reset_uses_default(self):
        item_id = _create_item(cta="Shop now")
        variant = create_variant(item_id, ORG, Platform.YOUTUBE, field_overrides={
            "cta": {"action": "reset"},
        })
        assert variant.fields["cta"].action == FieldAction.RESET
        assert variant.fields["cta"].effective_value is None  # Default

    def test_mixed_inheritance(self):
        item_id = _create_item(caption="Shared", disclosure="Paid ad")
        variant = create_variant(item_id, ORG, Platform.TWITTER, field_overrides={
            "caption": {"action": "override", "value": "Short tweet"},
            "disclosure": {"action": "inherit"},
        })
        assert variant.fields["caption"].effective_value == "Short tweet"
        assert variant.fields["disclosure"].effective_value == "Paid ad"
        assert "caption" in variant.overridden_fields
        assert "disclosure" in variant.inherited_fields


# =============================================================================
# Independent Approval
# =============================================================================


@pytest.mark.unit
class TestIndependentApproval:

    def test_variants_approved_independently(self):
        item_id = _create_item()
        v_ig = create_variant(item_id, ORG, Platform.INSTAGRAM)
        v_tt = create_variant(item_id, ORG, Platform.TIKTOK)

        approve_variant(v_ig.variant_id, ORG, "approver-1")
        assert v_ig.status == VariantStatus.APPROVED
        assert v_tt.status == VariantStatus.DRAFT  # Unaffected

    def test_approve_idempotent(self):
        item_id = _create_item()
        v = create_variant(item_id, ORG, Platform.INSTAGRAM)
        approve_variant(v.variant_id, ORG, "a1")
        result = approve_variant(v.variant_id, ORG, "a2")
        assert result.status == VariantStatus.APPROVED

    def test_publish_requires_approval(self):
        item_id = _create_item()
        v = create_variant(item_id, ORG, Platform.INSTAGRAM)
        with pytest.raises(InvalidVariantState):
            publish_variant(v.variant_id, ORG, "post-123")

    def test_publish_after_approval(self):
        item_id = _create_item()
        v = create_variant(item_id, ORG, Platform.INSTAGRAM)
        approve_variant(v.variant_id, ORG, "approver")
        publish_variant(v.variant_id, ORG, "ig-post-abc")
        assert v.status == VariantStatus.PUBLISHED
        assert v.execution_ref == "ig-post-abc"


# =============================================================================
# Source Edit Doesn't Rewrite History
# =============================================================================


@pytest.mark.unit
class TestSourceEditIsolation:

    def test_source_edit_doesnt_change_variant(self):
        """Approved variant's inherited values are frozen at creation time."""
        item_id = _create_item(caption="Original caption")
        v = create_variant(item_id, ORG, Platform.INSTAGRAM)
        approve_variant(v.variant_id, ORG, "approver")

        # Edit the source content item
        update_content_item(item_id, ORG, {"caption": "Updated caption"})

        # Variant still has the frozen original value
        assert v.fields["caption"].source_value == "Original caption"
        assert v.fields["caption"].effective_value == "Original caption"

    def test_source_version_tracked(self):
        item_id = _create_item()
        v = create_variant(item_id, ORG, Platform.TIKTOK)
        assert v.source_asset_version == "v1"


# =============================================================================
# Legacy Migration
# =============================================================================


@pytest.mark.unit
class TestLegacyMigration:

    def test_migrate_creates_item_and_variant(self):
        item = migrate_calendar_entry(
            ORG, USER, "instagram",
            caption="Legacy post",
            campaign_id="camp-legacy",
            asset_ids=["ast-old"],
        )
        assert item.caption == "Legacy post"
        assert Platform.INSTAGRAM in item.variants
        assert item.variant_count == 1

    def test_migrate_unknown_platform_defaults(self):
        item = migrate_calendar_entry(ORG, USER, "unknown_platform", "text")
        assert Platform.INSTAGRAM in item.variants  # Default


# =============================================================================
# Lineage
# =============================================================================


@pytest.mark.unit
class TestLineage:

    def test_variant_lineage_complete(self):
        item_id = _create_item(source_context_id="ctx-gen-001")
        v = create_variant(item_id, ORG, Platform.INSTAGRAM)
        lineage = get_variant_lineage(v.variant_id, ORG)
        assert lineage is not None
        assert lineage["content_item_id"] == item_id
        assert lineage["source_context_id"] == "ctx-gen-001"
        assert lineage["platform"] == "instagram"
        assert "caption" in lineage["inherited_fields"]

    def test_cross_tenant_lineage_none(self):
        item_id = _create_item()
        v = create_variant(item_id, ORG, Platform.INSTAGRAM)
        assert get_variant_lineage(v.variant_id, OTHER_ORG) is None


# =============================================================================
# Idempotency & Immutability
# =============================================================================


@pytest.mark.unit
class TestIdempotencyImmutability:

    def test_duplicate_variant_returns_existing(self):
        item_id = _create_item()
        v1 = create_variant(item_id, ORG, Platform.INSTAGRAM)
        v2 = create_variant(item_id, ORG, Platform.INSTAGRAM)
        assert v1.variant_id == v2.variant_id

    def test_published_variant_immutable(self):
        item_id = _create_item()
        v = create_variant(item_id, ORG, Platform.INSTAGRAM)
        approve_variant(v.variant_id, ORG, "a1")
        publish_variant(v.variant_id, ORG, "post-1")
        with pytest.raises(VariantImmutable):
            update_variant(v.variant_id, ORG, field_updates={"caption": {"action": "override", "value": "new"}})

    def test_cancelled_variant_immutable_for_publish(self):
        item_id = _create_item()
        v = create_variant(item_id, ORG, Platform.TIKTOK)
        cancel_variant(v.variant_id, ORG)
        assert v.is_terminal


# =============================================================================
# Multiple Platforms
# =============================================================================


@pytest.mark.unit
class TestMultiplePlatforms:

    def test_multiple_variants_different_media(self):
        item_id = _create_item()
        v_ig = create_variant(item_id, ORG, Platform.INSTAGRAM,
                              media_asset_ids=["ast-square"])
        v_tt = create_variant(item_id, ORG, Platform.TIKTOK,
                              media_asset_ids=["ast-vertical"])
        assert v_ig.media_asset_ids == ["ast-square"]
        assert v_tt.media_asset_ids == ["ast-vertical"]

    def test_item_tracks_variant_count(self):
        item_id = _create_item()
        create_variant(item_id, ORG, Platform.INSTAGRAM)
        create_variant(item_id, ORG, Platform.TIKTOK)
        create_variant(item_id, ORG, Platform.YOUTUBE)
        item = get_content_item(item_id, ORG)
        assert item.variant_count == 3

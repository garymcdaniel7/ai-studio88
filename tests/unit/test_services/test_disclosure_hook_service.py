"""Unit tests for DisclosureHookService.

Tests:
- evaluate_hooks: evaluates all 4 hook types correctly
- AI disclosure: enabled/disabled, custom text, platform override
- Sponsorship: requires both config enabled AND post is_sponsored
- C2PA provenance: enabled/disabled, requires asset_id
- Platform-specific: config-driven, handles missing platform
- preview_disclosures: constructs final caption, tags, summary
- get_config: returns default when no config exists
- update_config: partial updates, field-level granularity

No I/O, no DB — all tested with mocks.

Validates: Requirements R80.1, R80.2, R80.3, R80.4, R80.5, R80.6
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.dependencies import TenantContext, TrustDomain, WorkspaceRole
from app.models.workspace_disclosure_config import WorkspaceDisclosureConfig
from app.schemas.disclosure_config import (
    DisclosureConfigUpdateRequest,
    DisclosureHookType,
)
from app.services.disclosure_hook_service import DisclosureHookService


# =============================================================================
# Helpers
# =============================================================================

ORG_ID = uuid4()
USER_ID = uuid4()


def _make_tenant() -> TenantContext:
    """Create a TenantContext for testing."""
    return TenantContext(
        user_id=USER_ID,
        org_id=ORG_ID,
        role=WorkspaceRole.ADMIN,
        trust_domain=TrustDomain.WORKSPACE_ADMIN,
        email="test@example.com",
    )


def _make_config(
    ai_enabled: bool = False,
    ai_text: str | None = None,
    sponsorship_enabled: bool = False,
    sponsorship_text: str | None = None,
    disclosure_tags: list[str] | None = None,
    platform_requirements: dict | None = None,
    c2pa_enabled: bool = False,
) -> WorkspaceDisclosureConfig:
    """Create a WorkspaceDisclosureConfig for testing."""
    config = WorkspaceDisclosureConfig(
        id=uuid4(),
        org_id=ORG_ID,
        ai_disclosure_enabled=ai_enabled,
        ai_disclosure_text=ai_text,
        sponsorship_disclosure_enabled=sponsorship_enabled,
        sponsorship_text=sponsorship_text,
        disclosure_tags=disclosure_tags,
        platform_requirements=platform_requirements,
        c2pa_enabled=c2pa_enabled,
    )
    config.created_at = datetime.now(UTC)
    config.updated_at = datetime.now(UTC)
    return config


def _make_service_with_config(config: WorkspaceDisclosureConfig) -> DisclosureHookService:
    """Create a DisclosureHookService with a mocked DB that returns the given config."""
    db = AsyncMock()
    tenant = _make_tenant()
    service = DisclosureHookService(db=db, tenant=tenant)

    # Mock the DB query chain for get_config
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = config
    db.execute = AsyncMock(return_value=mock_result)

    return service


# =============================================================================
# AI Disclosure Hook Tests
# =============================================================================


class TestAIDisclosureHook:
    """Tests for _evaluate_ai_disclosure."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_ai_disclosure_disabled_returns_not_triggered(self) -> None:
        """When AI disclosure is disabled, hook should not trigger."""
        config = _make_config(ai_enabled=False)
        service = _make_service_with_config(config)

        hooks = await service.evaluate_hooks(platform="instagram")

        ai_hook = next(h for h in hooks if h.hook_type == DisclosureHookType.AI_SYNTHETIC)
        assert ai_hook.triggered is False
        assert "disabled" in ai_hook.reason.lower()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_ai_disclosure_enabled_uses_default_text(self) -> None:
        """When AI disclosure is enabled without custom text, uses default."""
        config = _make_config(ai_enabled=True)
        service = _make_service_with_config(config)

        hooks = await service.evaluate_hooks(platform="tiktok")

        ai_hook = next(h for h in hooks if h.hook_type == DisclosureHookType.AI_SYNTHETIC)
        assert ai_hook.triggered is True
        assert ai_hook.text is not None
        assert "AI" in ai_hook.text

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_ai_disclosure_enabled_uses_custom_text(self) -> None:
        """When custom AI disclosure text is set, uses that text."""
        config = _make_config(ai_enabled=True, ai_text="Made with generative AI tools")
        service = _make_service_with_config(config)

        hooks = await service.evaluate_hooks(platform="instagram")

        ai_hook = next(h for h in hooks if h.hook_type == DisclosureHookType.AI_SYNTHETIC)
        assert ai_hook.triggered is True
        assert ai_hook.text == "Made with generative AI tools"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_ai_disclosure_platform_override(self) -> None:
        """Platform-specific ai_label overrides workspace text."""
        config = _make_config(
            ai_enabled=True,
            ai_text="Default AI text",
            platform_requirements={"instagram": {"ai_label": "IG: AI Content"}},
        )
        service = _make_service_with_config(config)

        hooks = await service.evaluate_hooks(platform="instagram")

        ai_hook = next(h for h in hooks if h.hook_type == DisclosureHookType.AI_SYNTHETIC)
        assert ai_hook.triggered is True
        assert ai_hook.text == "IG: AI Content"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_ai_disclosure_includes_matching_tags(self) -> None:
        """AI hook includes disclosure tags containing 'ai' or 'generated'."""
        config = _make_config(
            ai_enabled=True,
            disclosure_tags=["#AIGenerated", "#Sponsored", "#GeneratedContent"],
        )
        service = _make_service_with_config(config)

        hooks = await service.evaluate_hooks(platform="tiktok")

        ai_hook = next(h for h in hooks if h.hook_type == DisclosureHookType.AI_SYNTHETIC)
        assert ai_hook.triggered is True
        assert "#AIGenerated" in ai_hook.tags
        assert "#GeneratedContent" in ai_hook.tags
        assert "#Sponsored" not in ai_hook.tags


# =============================================================================
# Sponsorship Disclosure Hook Tests
# =============================================================================


class TestSponsorshipDisclosureHook:
    """Tests for _evaluate_sponsorship_disclosure."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_sponsorship_disabled_returns_not_triggered(self) -> None:
        """When sponsorship disclosure is disabled, hook does not trigger."""
        config = _make_config(sponsorship_enabled=False)
        service = _make_service_with_config(config)

        hooks = await service.evaluate_hooks(platform="instagram", is_sponsored=True)

        hook = next(h for h in hooks if h.hook_type == DisclosureHookType.SPONSORSHIP_COMMERCIAL)
        assert hook.triggered is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_sponsorship_enabled_but_not_sponsored_post(self) -> None:
        """Enabled sponsorship config does NOT trigger if post is not sponsored."""
        config = _make_config(sponsorship_enabled=True)
        service = _make_service_with_config(config)

        hooks = await service.evaluate_hooks(platform="instagram", is_sponsored=False)

        hook = next(h for h in hooks if h.hook_type == DisclosureHookType.SPONSORSHIP_COMMERCIAL)
        assert hook.triggered is False
        assert "not marked" in hook.reason.lower()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_sponsorship_enabled_and_sponsored_triggers(self) -> None:
        """Both config enabled AND sponsored post → hook triggers."""
        config = _make_config(
            sponsorship_enabled=True,
            sponsorship_text="Paid partnership with Brand X",
        )
        service = _make_service_with_config(config)

        hooks = await service.evaluate_hooks(platform="instagram", is_sponsored=True)

        hook = next(h for h in hooks if h.hook_type == DisclosureHookType.SPONSORSHIP_COMMERCIAL)
        assert hook.triggered is True
        assert hook.text == "Paid partnership with Brand X"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_sponsorship_default_text_when_no_custom(self) -> None:
        """Uses default '#Ad #Sponsored' when no custom text configured."""
        config = _make_config(sponsorship_enabled=True)
        service = _make_service_with_config(config)

        hooks = await service.evaluate_hooks(platform="tiktok", is_sponsored=True)

        hook = next(h for h in hooks if h.hook_type == DisclosureHookType.SPONSORSHIP_COMMERCIAL)
        assert hook.triggered is True
        assert "#Ad" in hook.text
        assert "#Sponsored" in hook.text


# =============================================================================
# C2PA Provenance Hook Tests
# =============================================================================


class TestC2PAHook:
    """Tests for _evaluate_c2pa."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_c2pa_disabled_returns_not_triggered(self) -> None:
        """C2PA disabled → hook not triggered even with asset_id."""
        config = _make_config(c2pa_enabled=False)
        service = _make_service_with_config(config)
        asset_id = uuid4()

        hooks = await service.evaluate_hooks(platform="instagram", asset_id=asset_id)

        hook = next(h for h in hooks if h.hook_type == DisclosureHookType.PROVENANCE_C2PA)
        assert hook.triggered is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_c2pa_enabled_no_asset_returns_not_triggered(self) -> None:
        """C2PA enabled but no asset_id → cannot attach provenance."""
        config = _make_config(c2pa_enabled=True)
        service = _make_service_with_config(config)

        hooks = await service.evaluate_hooks(platform="instagram", asset_id=None)

        hook = next(h for h in hooks if h.hook_type == DisclosureHookType.PROVENANCE_C2PA)
        assert hook.triggered is False
        assert "no asset_id" in hook.reason.lower()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_c2pa_enabled_with_asset_triggers(self) -> None:
        """C2PA enabled + asset_id → hook triggers with metadata."""
        config = _make_config(c2pa_enabled=True)
        service = _make_service_with_config(config)
        asset_id = uuid4()

        hooks = await service.evaluate_hooks(platform="youtube", asset_id=asset_id)

        hook = next(h for h in hooks if h.hook_type == DisclosureHookType.PROVENANCE_C2PA)
        assert hook.triggered is True
        assert hook.metadata["asset_id"] == str(asset_id)
        assert hook.metadata["c2pa_action"] == "attach_manifest"
        assert hook.metadata["standard"] == "C2PA v2.0"


# =============================================================================
# Platform-Specific Hook Tests
# =============================================================================


class TestPlatformSpecificHook:
    """Tests for _evaluate_platform_specific."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_no_platform_config_returns_not_triggered(self) -> None:
        """No platform_requirements in config → hook not triggered."""
        config = _make_config(platform_requirements=None)
        service = _make_service_with_config(config)

        hooks = await service.evaluate_hooks(platform="instagram")

        hook = next(h for h in hooks if h.hook_type == DisclosureHookType.PLATFORM_SPECIFIC)
        assert hook.triggered is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_platform_not_in_config_returns_not_triggered(self) -> None:
        """Platform present in config but not the target platform."""
        config = _make_config(
            platform_requirements={"tiktok": {"label": "TikTok disclosure"}}
        )
        service = _make_service_with_config(config)

        hooks = await service.evaluate_hooks(platform="instagram")

        hook = next(h for h in hooks if h.hook_type == DisclosureHookType.PLATFORM_SPECIFIC)
        assert hook.triggered is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_platform_config_with_text_triggers(self) -> None:
        """Platform config with disclosure_text → hook triggers."""
        config = _make_config(
            platform_requirements={
                "instagram": {"disclosure_text": "AI-generated content per IG policy"}
            }
        )
        service = _make_service_with_config(config)

        hooks = await service.evaluate_hooks(platform="instagram")

        hook = next(h for h in hooks if h.hook_type == DisclosureHookType.PLATFORM_SPECIFIC)
        assert hook.triggered is True
        assert hook.text == "AI-generated content per IG policy"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_platform_config_with_tags_triggers(self) -> None:
        """Platform config with disclosure_tags → hook triggers with tags."""
        config = _make_config(
            platform_requirements={
                "tiktok": {"disclosure_tags": ["#AIContent", "#Synthetic"]}
            }
        )
        service = _make_service_with_config(config)

        hooks = await service.evaluate_hooks(platform="tiktok")

        hook = next(h for h in hooks if h.hook_type == DisclosureHookType.PLATFORM_SPECIFIC)
        assert hook.triggered is True
        assert "#AIContent" in hook.tags
        assert "#Synthetic" in hook.tags

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_platform_config_empty_values_not_triggered(self) -> None:
        """Platform config exists but has no disclosure content → not triggered."""
        config = _make_config(
            platform_requirements={"instagram": {"some_other_setting": "foo"}}
        )
        service = _make_service_with_config(config)

        hooks = await service.evaluate_hooks(platform="instagram")

        hook = next(h for h in hooks if h.hook_type == DisclosureHookType.PLATFORM_SPECIFIC)
        assert hook.triggered is False


# =============================================================================
# Preview Tests
# =============================================================================


class TestPreviewDisclosures:
    """Tests for preview_disclosures — full integration of all hooks."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_preview_no_disclosures(self) -> None:
        """All hooks disabled → preview shows no disclosures."""
        config = _make_config()
        service = _make_service_with_config(config)

        preview = await service.preview_disclosures(
            platform="instagram",
            caption="Hello world!",
        )

        assert preview.final_caption == "Hello world!"
        assert preview.final_tags == []
        assert preview.c2pa_attached is False
        assert "No disclosures" in preview.summary

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_preview_with_ai_disclosure(self) -> None:
        """AI disclosure enabled → appended to caption."""
        config = _make_config(ai_enabled=True, ai_text="🤖 AI-generated content")
        service = _make_service_with_config(config)

        preview = await service.preview_disclosures(
            platform="instagram",
            caption="Check out this photo!",
        )

        assert "🤖 AI-generated content" in preview.final_caption
        assert "Check out this photo!" in preview.final_caption
        assert preview.platform == "instagram"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_preview_with_multiple_hooks(self) -> None:
        """Multiple hooks triggered → all texts included in caption."""
        config = _make_config(
            ai_enabled=True,
            ai_text="AI-made",
            sponsorship_enabled=True,
            sponsorship_text="#Ad #Partnership",
            c2pa_enabled=True,
        )
        service = _make_service_with_config(config)
        asset_id = uuid4()

        preview = await service.preview_disclosures(
            platform="youtube",
            caption="Original caption",
            is_sponsored=True,
            asset_id=asset_id,
        )

        assert "AI-made" in preview.final_caption
        assert "#Ad #Partnership" in preview.final_caption
        assert "Original caption" in preview.final_caption
        assert preview.c2pa_attached is True
        assert "3 disclosure" in preview.summary

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_preview_empty_caption_no_separator(self) -> None:
        """Empty caption gets disclosure text without leading separator."""
        config = _make_config(ai_enabled=True, ai_text="AI content")
        service = _make_service_with_config(config)

        preview = await service.preview_disclosures(
            platform="tiktok",
            caption="",
        )

        assert preview.final_caption == "AI content"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_preview_summary_names_triggered_hooks(self) -> None:
        """Summary lists the names of all triggered hooks."""
        config = _make_config(ai_enabled=True, c2pa_enabled=True)
        service = _make_service_with_config(config)
        asset_id = uuid4()

        preview = await service.preview_disclosures(
            platform="instagram",
            caption="test",
            asset_id=asset_id,
        )

        assert "AI_SYNTHETIC" in preview.summary
        assert "PROVENANCE_C2PA" in preview.summary


# =============================================================================
# Configuration Tests
# =============================================================================


class TestGetConfig:
    """Tests for get_config."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_config_returns_existing(self) -> None:
        """Returns existing config when one exists for org."""
        config = _make_config(ai_enabled=True, c2pa_enabled=True)
        service = _make_service_with_config(config)

        result = await service.get_config()

        assert result.ai_disclosure_enabled is True
        assert result.c2pa_enabled is True
        assert result.org_id == ORG_ID

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_config_creates_default_when_none(self) -> None:
        """Creates a default config (all disabled) when none exists."""
        db = AsyncMock()
        tenant = _make_tenant()
        service = DisclosureHookService(db=db, tenant=tenant)

        # Mock no existing config
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        # Mock flush and refresh to populate config attributes
        created_config = _make_config()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()

        result = await service.get_config()

        # Verify a new config was added to session
        db.add.assert_called_once()
        added = db.add.call_args[0][0]
        assert isinstance(added, WorkspaceDisclosureConfig)
        assert added.org_id == ORG_ID
        assert added.ai_disclosure_enabled is False
        assert added.sponsorship_disclosure_enabled is False
        assert added.c2pa_enabled is False


class TestUpdateConfig:
    """Tests for update_config."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_update_config_partial_fields(self) -> None:
        """Only provided fields are updated."""
        config = _make_config(ai_enabled=False, c2pa_enabled=False)
        service = _make_service_with_config(config)

        # Also mock flush/refresh for update path
        service._db.flush = AsyncMock()
        service._db.refresh = AsyncMock()

        request = DisclosureConfigUpdateRequest(
            ai_disclosure_enabled=True,
            ai_disclosure_text="Custom AI text",
        )

        result = await service.update_config(request)

        assert result.ai_disclosure_enabled is True
        assert result.ai_disclosure_text == "Custom AI text"
        # c2pa should remain unchanged
        assert result.c2pa_enabled is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_update_config_tags(self) -> None:
        """Can update disclosure_tags list."""
        config = _make_config()
        service = _make_service_with_config(config)
        service._db.flush = AsyncMock()
        service._db.refresh = AsyncMock()

        request = DisclosureConfigUpdateRequest(
            disclosure_tags=["#AIGenerated", "#Sponsored", "#BrandPartner"],
        )

        result = await service.update_config(request)

        assert result.disclosure_tags == ["#AIGenerated", "#Sponsored", "#BrandPartner"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_update_config_platform_requirements(self) -> None:
        """Can update platform_requirements JSONB field."""
        config = _make_config()
        service = _make_service_with_config(config)
        service._db.flush = AsyncMock()
        service._db.refresh = AsyncMock()

        platform_reqs = {
            "instagram": {"ai_label": "AI-generated", "disclosure_text": "Made with AI"},
            "tiktok": {"disclosure_tags": ["#AIContent"]},
        }
        request = DisclosureConfigUpdateRequest(platform_requirements=platform_reqs)

        result = await service.update_config(request)

        assert result.platform_requirements == platform_reqs


# =============================================================================
# Hook Evaluation Count Tests
# =============================================================================


class TestHookEvaluationCount:
    """Test that evaluate_hooks always returns exactly 4 results."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_always_evaluates_four_hooks(self) -> None:
        """All 4 hook types are always evaluated regardless of config."""
        config = _make_config()
        service = _make_service_with_config(config)

        hooks = await service.evaluate_hooks(platform="instagram")

        assert len(hooks) == 4
        hook_types = {h.hook_type for h in hooks}
        assert hook_types == {
            DisclosureHookType.AI_SYNTHETIC,
            DisclosureHookType.SPONSORSHIP_COMMERCIAL,
            DisclosureHookType.PROVENANCE_C2PA,
            DisclosureHookType.PLATFORM_SPECIFIC,
        }

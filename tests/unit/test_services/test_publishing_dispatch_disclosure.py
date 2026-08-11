"""Unit tests for disclosure hook integration at dispatch time.

Tests that the PublishingService.dispatch_post method:
- Evaluates disclosure hooks before publishing
- Augments the caption with disclosure text
- Persists audit log entries for each hook evaluation
- Logs disclosure decisions correctly

No I/O, no DB — all tested with mocks.

Validates: Requirements R80.4, R80.6
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.disclosure_audit_log import DisclosureAuditLog
from app.models.scheduled_post import ScheduledPost, ScheduledPostStatus
from app.models.workspace_disclosure_config import WorkspaceDisclosureConfig
from app.schemas.disclosure_config import DisclosureHookResult, DisclosureHookType
from app.services.publishing_service import (
    PLATFORM_RESIZE_SPECS,
    PublishingService,
)


# =============================================================================
# Helpers
# =============================================================================

ORG_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


def _make_tenant() -> MagicMock:
    """Create a mock TenantContext."""
    tenant = MagicMock()
    tenant.org_id = ORG_ID
    tenant.user_id = USER_ID
    return tenant


def _make_db() -> AsyncMock:
    """Create a mock async DB session."""
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    db.scalar = AsyncMock()
    db.commit = AsyncMock()
    return db


def _make_post(
    org_id: uuid.UUID | None = None,
    status: ScheduledPostStatus = ScheduledPostStatus.SCHEDULED,
    platform: str = "instagram",
    caption: str = "Check out this photo!",
) -> ScheduledPost:
    """Create a ScheduledPost instance for testing."""
    post = ScheduledPost()
    post.id = uuid.uuid4()
    post.org_id = org_id or ORG_ID
    post.asset_id = uuid.uuid4()
    post.talent_id = None
    post.connection_id = None
    post.approval_id = None
    post.platform = platform
    post.caption = caption
    post.scheduled_at = datetime.now(UTC) - timedelta(seconds=30)
    post.dispatched_at = None
    post.status = status
    post.platform_post_id = None
    post.error_message = None
    post.resize_spec = PLATFORM_RESIZE_SPECS.get(platform)
    post.created_at = datetime.now(UTC)
    post.updated_at = datetime.now(UTC)
    return post


def _make_config(
    ai_enabled: bool = False,
    ai_text: str | None = None,
    sponsorship_enabled: bool = False,
    c2pa_enabled: bool = False,
    platform_requirements: dict | None = None,
) -> WorkspaceDisclosureConfig:
    """Create a WorkspaceDisclosureConfig for testing."""
    config = WorkspaceDisclosureConfig(
        id=uuid.uuid4(),
        org_id=ORG_ID,
        ai_disclosure_enabled=ai_enabled,
        ai_disclosure_text=ai_text,
        sponsorship_disclosure_enabled=sponsorship_enabled,
        sponsorship_text=None,
        disclosure_tags=None,
        platform_requirements=platform_requirements,
        c2pa_enabled=c2pa_enabled,
    )
    config.created_at = datetime.now(UTC)
    config.updated_at = datetime.now(UTC)
    return config


# =============================================================================
# Dispatch + Disclosure Integration Tests
# =============================================================================


class TestDispatchDisclosureIntegration:
    """Tests for disclosure hook evaluation at dispatch time (R80.4)."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_dispatch_evaluates_disclosure_hooks(self) -> None:
        """Dispatch should call disclosure hook evaluation.

        Validates: Requirements R80.4
        """
        db = _make_db()
        tenant = _make_tenant()
        service = PublishingService(db=db, tenant=tenant)

        post = _make_post(org_id=ORG_ID, caption="Hello world")
        config = _make_config(ai_enabled=True, ai_text="AI-generated content")

        # Mock get_post to return our post
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = post
        db.execute.return_value = mock_result

        # Mock the disclosure service's DB query (get_config)
        with patch(
            "app.services.publishing_service.DisclosureHookService"
        ) as MockDisclosureService:
            mock_disclosure_instance = AsyncMock()
            MockDisclosureService.return_value = mock_disclosure_instance

            # Return hooks with AI triggered
            mock_disclosure_instance.evaluate_hooks.return_value = [
                DisclosureHookResult(
                    hook_type=DisclosureHookType.AI_SYNTHETIC,
                    triggered=True,
                    text="AI-generated content",
                    tags=["#AIGenerated"],
                    reason="AI disclosure enabled",
                ),
                DisclosureHookResult(
                    hook_type=DisclosureHookType.SPONSORSHIP_COMMERCIAL,
                    triggered=False,
                    reason="Not sponsored",
                ),
                DisclosureHookResult(
                    hook_type=DisclosureHookType.PROVENANCE_C2PA,
                    triggered=False,
                    reason="C2PA disabled",
                ),
                DisclosureHookResult(
                    hook_type=DisclosureHookType.PLATFORM_SPECIFIC,
                    triggered=False,
                    reason="No platform config",
                ),
            ]
            mock_disclosure_instance.get_config.return_value = config

            result = await service.dispatch_post(post.id, force=True)

        # Verify disclosure hooks were evaluated
        mock_disclosure_instance.evaluate_hooks.assert_called_once_with(
            platform=post.platform,
            is_sponsored=False,
            asset_id=post.asset_id,
        )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_dispatch_augments_caption_with_disclosure_text(self) -> None:
        """Dispatch should append disclosure text to the caption.

        Validates: Requirements R80.4
        """
        db = _make_db()
        tenant = _make_tenant()
        service = PublishingService(db=db, tenant=tenant)

        post = _make_post(org_id=ORG_ID, caption="Original caption")
        config = _make_config(ai_enabled=True, ai_text="Made with AI")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = post
        db.execute.return_value = mock_result

        with patch(
            "app.services.publishing_service.DisclosureHookService"
        ) as MockDisclosureService:
            mock_disclosure_instance = AsyncMock()
            MockDisclosureService.return_value = mock_disclosure_instance

            mock_disclosure_instance.evaluate_hooks.return_value = [
                DisclosureHookResult(
                    hook_type=DisclosureHookType.AI_SYNTHETIC,
                    triggered=True,
                    text="Made with AI",
                    tags=[],
                    reason="AI disclosure enabled",
                ),
                DisclosureHookResult(
                    hook_type=DisclosureHookType.SPONSORSHIP_COMMERCIAL,
                    triggered=False,
                    reason="Disabled",
                ),
                DisclosureHookResult(
                    hook_type=DisclosureHookType.PROVENANCE_C2PA,
                    triggered=False,
                    reason="Disabled",
                ),
                DisclosureHookResult(
                    hook_type=DisclosureHookType.PLATFORM_SPECIFIC,
                    triggered=False,
                    reason="No config",
                ),
            ]
            mock_disclosure_instance.get_config.return_value = config

            await service.dispatch_post(post.id, force=True)

        # Verify caption was augmented
        assert "Original caption" in post.caption
        assert "Made with AI" in post.caption

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_dispatch_no_disclosure_leaves_caption_unchanged(self) -> None:
        """When no hooks trigger, caption should remain unchanged.

        Validates: Requirements R80.4
        """
        db = _make_db()
        tenant = _make_tenant()
        service = PublishingService(db=db, tenant=tenant)

        post = _make_post(org_id=ORG_ID, caption="Unchanged caption")
        config = _make_config()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = post
        db.execute.return_value = mock_result

        with patch(
            "app.services.publishing_service.DisclosureHookService"
        ) as MockDisclosureService:
            mock_disclosure_instance = AsyncMock()
            MockDisclosureService.return_value = mock_disclosure_instance

            mock_disclosure_instance.evaluate_hooks.return_value = [
                DisclosureHookResult(
                    hook_type=DisclosureHookType.AI_SYNTHETIC,
                    triggered=False,
                    reason="Disabled",
                ),
                DisclosureHookResult(
                    hook_type=DisclosureHookType.SPONSORSHIP_COMMERCIAL,
                    triggered=False,
                    reason="Disabled",
                ),
                DisclosureHookResult(
                    hook_type=DisclosureHookType.PROVENANCE_C2PA,
                    triggered=False,
                    reason="Disabled",
                ),
                DisclosureHookResult(
                    hook_type=DisclosureHookType.PLATFORM_SPECIFIC,
                    triggered=False,
                    reason="No config",
                ),
            ]
            mock_disclosure_instance.get_config.return_value = config

            await service.dispatch_post(post.id, force=True)

        assert post.caption == "Unchanged caption"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_dispatch_multiple_disclosures_appended(self) -> None:
        """Multiple triggered hooks should all append their text.

        Validates: Requirements R80.4
        """
        db = _make_db()
        tenant = _make_tenant()
        service = PublishingService(db=db, tenant=tenant)

        post = _make_post(org_id=ORG_ID, caption="My post")
        config = _make_config(ai_enabled=True, sponsorship_enabled=True)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = post
        db.execute.return_value = mock_result

        with patch(
            "app.services.publishing_service.DisclosureHookService"
        ) as MockDisclosureService:
            mock_disclosure_instance = AsyncMock()
            MockDisclosureService.return_value = mock_disclosure_instance

            mock_disclosure_instance.evaluate_hooks.return_value = [
                DisclosureHookResult(
                    hook_type=DisclosureHookType.AI_SYNTHETIC,
                    triggered=True,
                    text="🤖 AI content",
                    tags=[],
                    reason="Enabled",
                ),
                DisclosureHookResult(
                    hook_type=DisclosureHookType.SPONSORSHIP_COMMERCIAL,
                    triggered=True,
                    text="#Ad #Sponsored",
                    tags=["#Ad"],
                    reason="Sponsored post",
                ),
                DisclosureHookResult(
                    hook_type=DisclosureHookType.PROVENANCE_C2PA,
                    triggered=False,
                    reason="Disabled",
                ),
                DisclosureHookResult(
                    hook_type=DisclosureHookType.PLATFORM_SPECIFIC,
                    triggered=False,
                    reason="No config",
                ),
            ]
            mock_disclosure_instance.get_config.return_value = config

            await service.dispatch_post(post.id, force=True)

        assert "My post" in post.caption
        assert "🤖 AI content" in post.caption
        assert "#Ad #Sponsored" in post.caption


# =============================================================================
# Audit Logging Tests (R80.6)
# =============================================================================


class TestDisclosureAuditLogging:
    """Tests for disclosure audit log persistence at dispatch time (R80.6)."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_dispatch_persists_audit_entries_for_all_hooks(self) -> None:
        """Every hook evaluation should produce an audit log entry.

        Validates: Requirements R80.6
        """
        db = _make_db()
        tenant = _make_tenant()
        service = PublishingService(db=db, tenant=tenant)

        post = _make_post(org_id=ORG_ID)
        config = _make_config(ai_enabled=True, ai_text="AI content")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = post
        db.execute.return_value = mock_result

        with patch(
            "app.services.publishing_service.DisclosureHookService"
        ) as MockDisclosureService:
            mock_disclosure_instance = AsyncMock()
            MockDisclosureService.return_value = mock_disclosure_instance

            mock_disclosure_instance.evaluate_hooks.return_value = [
                DisclosureHookResult(
                    hook_type=DisclosureHookType.AI_SYNTHETIC,
                    triggered=True,
                    text="AI content",
                    tags=["#AI"],
                    metadata={"source": "workspace_config"},
                    reason="AI enabled",
                ),
                DisclosureHookResult(
                    hook_type=DisclosureHookType.SPONSORSHIP_COMMERCIAL,
                    triggered=False,
                    reason="Disabled",
                ),
                DisclosureHookResult(
                    hook_type=DisclosureHookType.PROVENANCE_C2PA,
                    triggered=False,
                    reason="Disabled",
                ),
                DisclosureHookResult(
                    hook_type=DisclosureHookType.PLATFORM_SPECIFIC,
                    triggered=False,
                    reason="No config",
                ),
            ]
            mock_disclosure_instance.get_config.return_value = config

            await service.dispatch_post(post.id, force=True)

        # Count DisclosureAuditLog additions (4 hooks = 4 audit entries)
        audit_adds = [
            call[0][0]
            for call in db.add.call_args_list
            if isinstance(call[0][0], DisclosureAuditLog)
        ]
        assert len(audit_adds) == 4

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_audit_entry_records_triggered_hook_details(self) -> None:
        """Triggered hook audit entries should include text, tags, metadata.

        Validates: Requirements R80.6
        """
        db = _make_db()
        tenant = _make_tenant()
        service = PublishingService(db=db, tenant=tenant)

        post = _make_post(org_id=ORG_ID, platform="tiktok")
        config = _make_config(ai_enabled=True, ai_text="Made by AI")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = post
        db.execute.return_value = mock_result

        with patch(
            "app.services.publishing_service.DisclosureHookService"
        ) as MockDisclosureService:
            mock_disclosure_instance = AsyncMock()
            MockDisclosureService.return_value = mock_disclosure_instance

            mock_disclosure_instance.evaluate_hooks.return_value = [
                DisclosureHookResult(
                    hook_type=DisclosureHookType.AI_SYNTHETIC,
                    triggered=True,
                    text="Made by AI",
                    tags=["#AIGenerated"],
                    metadata={"platform": "tiktok", "source": "workspace_config"},
                    reason="AI disclosure enabled in workspace configuration",
                ),
                DisclosureHookResult(
                    hook_type=DisclosureHookType.SPONSORSHIP_COMMERCIAL,
                    triggered=False,
                    reason="Disabled",
                ),
                DisclosureHookResult(
                    hook_type=DisclosureHookType.PROVENANCE_C2PA,
                    triggered=False,
                    reason="Disabled",
                ),
                DisclosureHookResult(
                    hook_type=DisclosureHookType.PLATFORM_SPECIFIC,
                    triggered=False,
                    reason="No config",
                ),
            ]
            mock_disclosure_instance.get_config.return_value = config

            await service.dispatch_post(post.id, force=True)

        # Find the AI_SYNTHETIC audit entry
        audit_adds = [
            call[0][0]
            for call in db.add.call_args_list
            if isinstance(call[0][0], DisclosureAuditLog)
        ]

        ai_entry = next(
            e for e in audit_adds if e.hook_type == "AI_SYNTHETIC"
        )
        assert ai_entry.triggered is True
        assert ai_entry.applied_text == "Made by AI"
        assert ai_entry.applied_tags == ["#AIGenerated"]
        assert ai_entry.platform == "tiktok"
        assert ai_entry.post_id == post.id
        assert ai_entry.org_id == ORG_ID
        assert ai_entry.reason == "AI disclosure enabled in workspace configuration"
        assert ai_entry.metadata_payload == {
            "platform": "tiktok",
            "source": "workspace_config",
        }

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_audit_entry_skipped_hook_has_no_applied_text(self) -> None:
        """Skipped hook audit entries should have None for text and tags.

        Validates: Requirements R80.6
        """
        db = _make_db()
        tenant = _make_tenant()
        service = PublishingService(db=db, tenant=tenant)

        post = _make_post(org_id=ORG_ID)
        config = _make_config()  # All disabled

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = post
        db.execute.return_value = mock_result

        with patch(
            "app.services.publishing_service.DisclosureHookService"
        ) as MockDisclosureService:
            mock_disclosure_instance = AsyncMock()
            MockDisclosureService.return_value = mock_disclosure_instance

            mock_disclosure_instance.evaluate_hooks.return_value = [
                DisclosureHookResult(
                    hook_type=DisclosureHookType.AI_SYNTHETIC,
                    triggered=False,
                    reason="Disabled in workspace config",
                ),
                DisclosureHookResult(
                    hook_type=DisclosureHookType.SPONSORSHIP_COMMERCIAL,
                    triggered=False,
                    reason="Disabled",
                ),
                DisclosureHookResult(
                    hook_type=DisclosureHookType.PROVENANCE_C2PA,
                    triggered=False,
                    reason="Disabled",
                ),
                DisclosureHookResult(
                    hook_type=DisclosureHookType.PLATFORM_SPECIFIC,
                    triggered=False,
                    reason="No config",
                ),
            ]
            mock_disclosure_instance.get_config.return_value = config

            await service.dispatch_post(post.id, force=True)

        audit_adds = [
            call[0][0]
            for call in db.add.call_args_list
            if isinstance(call[0][0], DisclosureAuditLog)
        ]

        ai_entry = next(
            e for e in audit_adds if e.hook_type == "AI_SYNTHETIC"
        )
        assert ai_entry.triggered is False
        assert ai_entry.applied_text is None
        assert ai_entry.applied_tags is None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_audit_entry_includes_config_snapshot(self) -> None:
        """Audit entries should include a snapshot of the config at evaluation time.

        Validates: Requirements R80.6
        """
        db = _make_db()
        tenant = _make_tenant()
        service = PublishingService(db=db, tenant=tenant)

        post = _make_post(org_id=ORG_ID)
        config = _make_config(
            ai_enabled=True,
            c2pa_enabled=True,
            platform_requirements={"instagram": {"label": "AI"}},
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = post
        db.execute.return_value = mock_result

        with patch(
            "app.services.publishing_service.DisclosureHookService"
        ) as MockDisclosureService:
            mock_disclosure_instance = AsyncMock()
            MockDisclosureService.return_value = mock_disclosure_instance

            mock_disclosure_instance.evaluate_hooks.return_value = [
                DisclosureHookResult(
                    hook_type=DisclosureHookType.AI_SYNTHETIC,
                    triggered=True,
                    text="AI",
                    tags=[],
                    reason="Enabled",
                ),
                DisclosureHookResult(
                    hook_type=DisclosureHookType.SPONSORSHIP_COMMERCIAL,
                    triggered=False,
                    reason="Disabled",
                ),
                DisclosureHookResult(
                    hook_type=DisclosureHookType.PROVENANCE_C2PA,
                    triggered=False,
                    reason="Disabled",
                ),
                DisclosureHookResult(
                    hook_type=DisclosureHookType.PLATFORM_SPECIFIC,
                    triggered=False,
                    reason="No config",
                ),
            ]
            mock_disclosure_instance.get_config.return_value = config

            await service.dispatch_post(post.id, force=True)

        audit_adds = [
            call[0][0]
            for call in db.add.call_args_list
            if isinstance(call[0][0], DisclosureAuditLog)
        ]

        # All entries should have the same config snapshot
        for entry in audit_adds:
            assert entry.config_snapshot is not None
            assert entry.config_snapshot["ai_disclosure_enabled"] is True
            assert entry.config_snapshot["c2pa_enabled"] is True
            assert entry.config_snapshot["platform_requirements"] == {
                "instagram": {"label": "AI"}
            }

"""Unit tests for the Core Publishing Service (Task 36.3).

Tests scheduling, dispatch, cancellation, token refresh, platform resize,
and validation logic.

Run with:
    pytest tests/unit/test_publishing_service.py -v

Requirements: R38.1, R38.2, R38.3, R38.4, R38.5, R38.6, R38.7, R38.8
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.scheduled_post import ScheduledPost, ScheduledPostStatus
from app.services.publishing_service import (
    MIN_SCHEDULE_MINUTES,
    PLATFORM_RESIZE_SPECS,
    SUPPORTED_PLATFORMS,
    PublishingService,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_tenant():
    """Create a mock TenantContext."""
    tenant = MagicMock()
    tenant.org_id = uuid.uuid4()
    tenant.user_id = uuid.uuid4()
    tenant.role = MagicMock()
    return tenant


@pytest.fixture
def mock_db():
    """Create a mock async DB session."""
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    db.scalar = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture
def service(mock_db, mock_tenant):
    """Create a PublishingService with mocked dependencies."""
    return PublishingService(db=mock_db, tenant=mock_tenant)


def _make_post(
    org_id: uuid.UUID | None = None,
    status: ScheduledPostStatus = ScheduledPostStatus.SCHEDULED,
    scheduled_at: datetime | None = None,
    platform: str = "instagram",
    connection_id: uuid.UUID | None = None,
) -> ScheduledPost:
    """Create a ScheduledPost instance for testing."""
    post = ScheduledPost()
    post.id = uuid.uuid4()
    post.org_id = org_id or uuid.uuid4()
    post.asset_id = uuid.uuid4()
    post.talent_id = None
    post.connection_id = connection_id
    post.approval_id = None
    post.platform = platform
    post.caption = "Test caption"
    post.scheduled_at = scheduled_at or (datetime.now(UTC) + timedelta(hours=1))
    post.dispatched_at = None
    post.status = status
    post.platform_post_id = None
    post.error_message = None
    post.resize_spec = PLATFORM_RESIZE_SPECS.get(platform)
    post.created_at = datetime.now(UTC)
    post.updated_at = datetime.now(UTC)
    return post


# =============================================================================
# Schedule Post Tests
# =============================================================================


class TestSchedulePost:
    """Tests for PublishingService.schedule_post."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_schedule_valid_post(self, service, mock_db, mock_tenant):
        """Valid scheduling creates a ScheduledPost with correct fields.

        Validates: R38.1 — schedule with valid platform, asset_id, scheduled_at.
        """
        asset_id = uuid.uuid4()
        scheduled_at = datetime.now(UTC) + timedelta(hours=1)

        # Mock flush to set id on the record
        async def mock_flush():
            pass

        async def mock_refresh(record):
            record.id = uuid.uuid4()
            record.created_at = datetime.now(UTC)
            record.updated_at = datetime.now(UTC)

        mock_db.flush = AsyncMock(side_effect=mock_flush)
        mock_db.refresh = AsyncMock(side_effect=mock_refresh)

        result = await service.schedule_post(
            asset_id=asset_id,
            platform="instagram",
            scheduled_at=scheduled_at,
            caption="Test post",
        )

        assert result.org_id == mock_tenant.org_id
        assert result.asset_id == asset_id
        assert result.platform == "instagram"
        assert result.status == ScheduledPostStatus.SCHEDULED
        assert result.caption == "Test post"
        assert result.resize_spec == {"width": 1080, "height": 1350, "aspect": "4:5"}
        mock_db.add.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_schedule_rejects_past_time(self, service):
        """Scheduling with past time returns 422.

        Validates: R38.2 — scheduled_at < now + 5 min → 422.
        """
        from fastapi import HTTPException

        scheduled_at = datetime.now(UTC) - timedelta(hours=1)

        with pytest.raises(HTTPException) as exc_info:
            await service.schedule_post(
                asset_id=uuid.uuid4(),
                platform="instagram",
                scheduled_at=scheduled_at,
            )
        assert exc_info.value.status_code == 422
        assert "5 minutes" in exc_info.value.detail

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_schedule_rejects_too_soon(self, service):
        """Scheduling within 5 minutes of now returns 422.

        Validates: R38.2 — scheduled_at < now + 5 min → 422.
        """
        from fastapi import HTTPException

        # 3 minutes from now (less than 5 min minimum)
        scheduled_at = datetime.now(UTC) + timedelta(minutes=3)

        with pytest.raises(HTTPException) as exc_info:
            await service.schedule_post(
                asset_id=uuid.uuid4(),
                platform="instagram",
                scheduled_at=scheduled_at,
            )
        assert exc_info.value.status_code == 422

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_schedule_rejects_unsupported_platform(self, service):
        """Scheduling to unsupported platform returns 422.

        Validates: R38.1 — valid platform requirement.
        """
        from fastapi import HTTPException

        scheduled_at = datetime.now(UTC) + timedelta(hours=1)

        with pytest.raises(HTTPException) as exc_info:
            await service.schedule_post(
                asset_id=uuid.uuid4(),
                platform="snapchat",
                scheduled_at=scheduled_at,
            )
        assert exc_info.value.status_code == 422
        assert "Unsupported platform" in exc_info.value.detail

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_schedule_rejects_naive_datetime(self, service):
        """Scheduling with naive datetime (no timezone) returns 422."""
        from fastapi import HTTPException

        # Naive datetime — no timezone info
        scheduled_at = datetime(2030, 1, 1, 12, 0, 0)

        with pytest.raises(HTTPException) as exc_info:
            await service.schedule_post(
                asset_id=uuid.uuid4(),
                platform="instagram",
                scheduled_at=scheduled_at,
            )
        assert exc_info.value.status_code == 422
        assert "timezone" in exc_info.value.detail

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_schedule_applies_tiktok_resize(self, service, mock_db):
        """TikTok posts get 9:16 resize spec.

        Validates: R38.7 — platform-specific resize.
        """
        scheduled_at = datetime.now(UTC) + timedelta(hours=1)

        async def mock_refresh(record):
            record.id = uuid.uuid4()
            record.created_at = datetime.now(UTC)
            record.updated_at = datetime.now(UTC)

        mock_db.refresh = AsyncMock(side_effect=mock_refresh)

        result = await service.schedule_post(
            asset_id=uuid.uuid4(),
            platform="tiktok",
            scheduled_at=scheduled_at,
        )

        assert result.resize_spec == {"width": 1080, "height": 1920, "aspect": "9:16"}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_schedule_applies_youtube_resize(self, service, mock_db):
        """YouTube posts get 16:9 resize spec.

        Validates: R38.7 — platform-specific resize.
        """
        scheduled_at = datetime.now(UTC) + timedelta(hours=1)

        async def mock_refresh(record):
            record.id = uuid.uuid4()
            record.created_at = datetime.now(UTC)
            record.updated_at = datetime.now(UTC)

        mock_db.refresh = AsyncMock(side_effect=mock_refresh)

        result = await service.schedule_post(
            asset_id=uuid.uuid4(),
            platform="youtube",
            scheduled_at=scheduled_at,
        )

        assert result.resize_spec == {"width": 1920, "height": 1080, "aspect": "16:9"}


# =============================================================================
# Cancel Post Tests
# =============================================================================


class TestCancelPost:
    """Tests for PublishingService.cancel_post."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_cancel_scheduled_post(self, service, mock_db, mock_tenant):
        """Can cancel a post with status 'scheduled'.

        Validates: R38.6 — DELETE of scheduled post returns 204.
        """
        post = _make_post(org_id=mock_tenant.org_id, status=ScheduledPostStatus.SCHEDULED)

        # Mock get_post
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = post
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def mock_refresh(record):
            pass

        mock_db.refresh = AsyncMock(side_effect=mock_refresh)

        result = await service.cancel_post(post.id)
        assert result.status == ScheduledPostStatus.CANCELLED

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_cancel_published_post_fails(self, service, mock_db, mock_tenant):
        """Cannot cancel a post that is already published (409).

        Validates: R38.6 — targeting published/failed returns 409.
        """
        from fastapi import HTTPException

        post = _make_post(org_id=mock_tenant.org_id, status=ScheduledPostStatus.PUBLISHED)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = post
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(HTTPException) as exc_info:
            await service.cancel_post(post.id)
        assert exc_info.value.status_code == 409

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_cancel_failed_post_fails(self, service, mock_db, mock_tenant):
        """Cannot cancel a post that has failed (409).

        Validates: R38.6 — targeting failed returns 409.
        """
        from fastapi import HTTPException

        post = _make_post(org_id=mock_tenant.org_id, status=ScheduledPostStatus.FAILED)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = post
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(HTTPException) as exc_info:
            await service.cancel_post(post.id)
        assert exc_info.value.status_code == 409

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_cancel_nonexistent_post_404(self, service, mock_db):
        """Cancelling a non-existent post returns 404."""
        from fastapi import HTTPException

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(HTTPException) as exc_info:
            await service.cancel_post(uuid.uuid4())
        assert exc_info.value.status_code == 404


# =============================================================================
# Dispatch Post Tests
# =============================================================================


class TestDispatchPost:
    """Tests for PublishingService.dispatch_post."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_dispatch_scheduled_post_simulation(self, service, mock_db, mock_tenant):
        """Dispatching a scheduled post in simulation mode succeeds.

        Validates: R38.3, R38.8 — dispatch within window, simulation records intent.
        """
        # Post scheduled in the past (due for dispatch)
        post = _make_post(
            org_id=mock_tenant.org_id,
            status=ScheduledPostStatus.SCHEDULED,
            scheduled_at=datetime.now(UTC) - timedelta(minutes=1),
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = post
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def mock_refresh(record):
            pass

        mock_db.refresh = AsyncMock(side_effect=mock_refresh)

        # Mock disclosure hook evaluation (added by task 36.2)
        disclosure_mock = AsyncMock(return_value={
            "final_caption": post.caption,
            "triggered_count": 0,
            "hooks": [],
        })

        with (
            patch.dict("os.environ", {"PUBLISHING_PROVIDER": "simulation"}),
            patch.object(service, "_evaluate_disclosures_for_dispatch", disclosure_mock),
        ):
            result = await service.dispatch_post(post.id, force=True)

        assert result.status == ScheduledPostStatus.PUBLISHED
        assert result.platform_post_id is not None
        assert result.platform_post_id.startswith("sim_")

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_dispatch_rejects_not_due_post(self, service, mock_db, mock_tenant):
        """Cannot dispatch a post before its scheduled time without force.

        Validates: R38.3 — dispatch within ±60 seconds.
        """
        from fastapi import HTTPException

        # Post scheduled far in the future
        post = _make_post(
            org_id=mock_tenant.org_id,
            status=ScheduledPostStatus.SCHEDULED,
            scheduled_at=datetime.now(UTC) + timedelta(hours=2),
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = post
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(HTTPException) as exc_info:
            await service.dispatch_post(post.id, force=False)
        assert exc_info.value.status_code == 409
        assert "not yet due" in exc_info.value.detail

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_dispatch_force_ignores_schedule(self, service, mock_db, mock_tenant):
        """Force=True dispatches regardless of scheduled time."""
        post = _make_post(
            org_id=mock_tenant.org_id,
            status=ScheduledPostStatus.SCHEDULED,
            scheduled_at=datetime.now(UTC) + timedelta(hours=2),
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = post
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def mock_refresh(record):
            pass

        mock_db.refresh = AsyncMock(side_effect=mock_refresh)

        # Mock disclosure hook evaluation (added by task 36.2)
        disclosure_mock = AsyncMock(return_value={
            "final_caption": post.caption,
            "triggered_count": 0,
            "hooks": [],
        })

        with (
            patch.dict("os.environ", {"PUBLISHING_PROVIDER": "simulation"}),
            patch.object(service, "_evaluate_disclosures_for_dispatch", disclosure_mock),
        ):
            result = await service.dispatch_post(post.id, force=True)

        assert result.status == ScheduledPostStatus.PUBLISHED

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_dispatch_already_published_409(self, service, mock_db, mock_tenant):
        """Cannot dispatch an already-published post (409).

        Validates: Idempotency — no double dispatch.
        """
        from fastapi import HTTPException

        post = _make_post(
            org_id=mock_tenant.org_id,
            status=ScheduledPostStatus.PUBLISHED,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = post
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(HTTPException) as exc_info:
            await service.dispatch_post(post.id, force=True)
        assert exc_info.value.status_code == 409

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_dispatch_failed_post_can_retry(self, service, mock_db, mock_tenant):
        """Failed posts can be re-dispatched (retry scenario)."""
        post = _make_post(
            org_id=mock_tenant.org_id,
            status=ScheduledPostStatus.FAILED,
            scheduled_at=datetime.now(UTC) - timedelta(minutes=5),
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = post
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def mock_refresh(record):
            pass

        mock_db.refresh = AsyncMock(side_effect=mock_refresh)

        # Mock disclosure hook evaluation (added by task 36.2)
        disclosure_mock = AsyncMock(return_value={
            "final_caption": post.caption,
            "triggered_count": 0,
            "hooks": [],
        })

        with (
            patch.dict("os.environ", {"PUBLISHING_PROVIDER": "simulation"}),
            patch.object(service, "_evaluate_disclosures_for_dispatch", disclosure_mock),
        ):
            result = await service.dispatch_post(post.id, force=True)

        assert result.status == ScheduledPostStatus.PUBLISHED


# =============================================================================
# Token Refresh Tests
# =============================================================================


class TestTokenRefresh:
    """Tests for OAuth token refresh logic.

    Validates: R38.5 — refresh on expired, mark disconnected if fails.
    """

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_no_connection_returns_true(self, service):
        """Posts without connection_id skip token refresh.

        Validates: simulation mode works without credentials.
        """
        post = _make_post(connection_id=None)
        result = await service._refresh_token_if_needed(post)
        assert result is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_expired_token_no_refresh_token_disconnects(
        self, service, mock_tenant
    ):
        """Expired token with no refresh_token marks disconnected.

        Validates: R38.5 — if refresh fails, mark disconnected + post failed.
        """
        post = _make_post(
            org_id=mock_tenant.org_id,
            connection_id=uuid.uuid4(),
            platform="instagram",
        )

        # Mock the Supabase calls
        expired_time = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        mock_conn_data = [
            {
                "platform": "instagram",
                "access_token": "expired_token",
                "refresh_token": "",  # No refresh token
                "expires_at": expired_time,
            }
        ]

        mock_execute = MagicMock()
        mock_execute.data = mock_conn_data

        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_table.select.return_value.eq.return_value.execute.return_value = mock_execute
        mock_table.update.return_value.eq.return_value.execute.return_value = MagicMock()
        mock_client.table.return_value = mock_table

        with (
            patch("backend.database.is_supabase_configured", return_value=True),
            patch("backend.database.get_supabase_client", return_value=mock_client),
        ):
            result = await service._refresh_token_if_needed(post)

        assert result is False


# =============================================================================
# Platform Resize Spec Tests
# =============================================================================


class TestPlatformResize:
    """Tests for platform-specific resize specifications.

    Validates: R38.7 — platform specs (9:16 TikTok, 4:5 IG, 16:9 YouTube).
    """

    @pytest.mark.unit
    def test_tiktok_9_16(self):
        """TikTok resize spec is 9:16 at 1080x1920."""
        spec = PublishingService.get_resize_spec("tiktok")
        assert spec == {"width": 1080, "height": 1920, "aspect": "9:16"}

    @pytest.mark.unit
    def test_instagram_4_5(self):
        """Instagram resize spec is 4:5 at 1080x1350."""
        spec = PublishingService.get_resize_spec("instagram")
        assert spec == {"width": 1080, "height": 1350, "aspect": "4:5"}

    @pytest.mark.unit
    def test_youtube_16_9(self):
        """YouTube resize spec is 16:9 at 1920x1080."""
        spec = PublishingService.get_resize_spec("youtube")
        assert spec == {"width": 1920, "height": 1080, "aspect": "16:9"}

    @pytest.mark.unit
    def test_unknown_platform_returns_none(self):
        """Unknown platform returns None (no forced resize)."""
        spec = PublishingService.get_resize_spec("snapchat")
        assert spec is None

    @pytest.mark.unit
    def test_x_no_forced_resize(self):
        """X/Twitter has no forced resize in current spec."""
        spec = PublishingService.get_resize_spec("x")
        assert spec is None  # Not in PLATFORM_RESIZE_SPECS


# =============================================================================
# Supported Platforms Tests
# =============================================================================


class TestSupportedPlatforms:
    """Tests for platform validation."""

    @pytest.mark.unit
    def test_required_platforms_supported(self):
        """TikTok, Instagram, and YouTube are in the supported set."""
        assert "tiktok" in SUPPORTED_PLATFORMS
        assert "instagram" in SUPPORTED_PLATFORMS
        assert "youtube" in SUPPORTED_PLATFORMS

    @pytest.mark.unit
    def test_supported_platforms_is_set(self):
        """SUPPORTED_PLATFORMS is a set for O(1) lookup."""
        assert isinstance(SUPPORTED_PLATFORMS, set)


# =============================================================================
# List Scheduled Posts Tests
# =============================================================================


class TestListScheduledPosts:
    """Tests for PublishingService.list_scheduled_posts."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_list_returns_paginated_results(self, service, mock_db):
        """List returns items and total count."""
        mock_db.scalar = AsyncMock(return_value=2)

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [_make_post(), _make_post()]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        items, total = await service.list_scheduled_posts(limit=20, offset=0)

        assert total == 2
        assert len(items) == 2

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_list_respects_pagination(self, service, mock_db):
        """List passes limit and offset to the query."""
        mock_db.scalar = AsyncMock(return_value=50)

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        items, total = await service.list_scheduled_posts(limit=10, offset=20)

        assert total == 50
        # Verify execute was called (query built with limit/offset)
        assert mock_db.execute.called


# =============================================================================
# Model Status Enum Tests
# =============================================================================


class TestScheduledPostStatus:
    """Tests for the ScheduledPostStatus enum."""

    @pytest.mark.unit
    def test_status_values(self):
        """All expected status values exist."""
        assert ScheduledPostStatus.SCHEDULED.value == "scheduled"
        assert ScheduledPostStatus.DISPATCHING.value == "dispatching"
        assert ScheduledPostStatus.PUBLISHED.value == "published"
        assert ScheduledPostStatus.FAILED.value == "failed"
        assert ScheduledPostStatus.CANCELLED.value == "cancelled"

    @pytest.mark.unit
    def test_status_count(self):
        """Exactly 5 status values exist."""
        assert len(ScheduledPostStatus) == 5


# =============================================================================
# Dispatch Due Posts (Scheduler Tick) Tests
# =============================================================================


class TestDispatchDuePosts:
    """Tests for PublishingService.dispatch_due_posts.

    Validates: R38.3 — dispatch within ±60 seconds of scheduled time.
    """

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_dispatch_due_posts_finds_and_dispatches(self, service, mock_db, mock_tenant):
        """Scheduler tick finds due posts and dispatches them in simulation mode.

        Validates: R38.3 — dispatch within ±60 seconds.
        """
        # Create a due post (scheduled in the past)
        due_post = _make_post(
            org_id=mock_tenant.org_id,
            status=ScheduledPostStatus.SCHEDULED,
            scheduled_at=datetime.now(UTC) - timedelta(minutes=1),
        )

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [due_post]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def mock_refresh(record):
            pass

        mock_db.refresh = AsyncMock(side_effect=mock_refresh)

        with patch.dict("os.environ", {"PUBLISHING_PROVIDER": "simulation"}):
            result = await service.dispatch_due_posts()

        assert result["due_count"] == 1
        assert len(result["dispatched"]) == 1
        assert str(due_post.id) in result["dispatched"]
        assert len(result["failed"]) == 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_dispatch_due_posts_no_due_posts(self, service, mock_db, mock_tenant):
        """Scheduler tick with no due posts returns empty results."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.dispatch_due_posts()

        assert result["due_count"] == 0
        assert result["dispatched"] == []
        assert result["failed"] == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_dispatch_due_posts_handles_token_failure(
        self, service, mock_db, mock_tenant
    ):
        """Scheduler tick marks post failed when token refresh fails.

        Validates: R38.5 — if refresh fails, mark connection disconnected + post failed.
        """
        connection_id = uuid.uuid4()
        due_post = _make_post(
            org_id=mock_tenant.org_id,
            status=ScheduledPostStatus.SCHEDULED,
            scheduled_at=datetime.now(UTC) - timedelta(minutes=1),
            connection_id=connection_id,
        )

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [due_post]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Mock _refresh_token_if_needed to return False (token refresh failed)
        with patch.object(service, "_refresh_token_if_needed", return_value=False):
            result = await service.dispatch_due_posts()

        assert result["due_count"] == 1
        assert len(result["dispatched"]) == 0
        assert len(result["failed"]) == 1
        assert due_post.status == ScheduledPostStatus.FAILED

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_dispatch_due_posts_multiple_mixed_results(
        self, service, mock_db, mock_tenant
    ):
        """Scheduler tick handles mix of successful and failed dispatches."""
        post_ok = _make_post(
            org_id=mock_tenant.org_id,
            status=ScheduledPostStatus.SCHEDULED,
            scheduled_at=datetime.now(UTC) - timedelta(minutes=1),
        )
        post_fail = _make_post(
            org_id=mock_tenant.org_id,
            status=ScheduledPostStatus.SCHEDULED,
            scheduled_at=datetime.now(UTC) - timedelta(minutes=2),
            connection_id=uuid.uuid4(),
        )

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [post_ok, post_fail]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def mock_refresh(record):
            pass

        mock_db.refresh = AsyncMock(side_effect=mock_refresh)

        # Make _refresh_token_if_needed pass for first post, fail for second
        call_count = [0]

        async def side_effect_refresh(post):
            call_count[0] += 1
            # First call (post_ok has no connection_id) → True
            # Second call (post_fail has connection_id) → False
            return post.connection_id is None

        with (
            patch.object(service, "_refresh_token_if_needed", side_effect=side_effect_refresh),
            patch.dict("os.environ", {"PUBLISHING_PROVIDER": "simulation"}),
        ):
            result = await service.dispatch_due_posts()

        assert result["due_count"] == 2
        assert len(result["dispatched"]) == 1
        assert len(result["failed"]) == 1

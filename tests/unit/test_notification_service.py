"""Unit tests for the notification service.

Tests NotificationService CRUD operations, NotificationChannel Protocol,
InAppChannel, mandatory notification enforcement, and schema validation.

No I/O — all DB operations are mocked.

Requirements: R101.1, R101.2, R101.3
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.models.notification import Notification
from backend.notifications.notification_schemas import (
    MANDATORY_CATEGORIES,
    NotificationCategory,
    NotificationCountResponse,
    NotificationCreate,
    NotificationListResponse,
    NotificationResponse,
)
from backend.notifications.notification_service import (
    DeliveryResult,
    InAppChannel,
    NotificationChannel,
    NotificationService,
)


# =============================================================================
# Test fixtures
# =============================================================================


@pytest.fixture
def org_id() -> UUID:
    """Standard org_id for tests."""
    return uuid4()


@pytest.fixture
def user_id() -> UUID:
    """Standard user_id for tests."""
    return uuid4()


@pytest.fixture
def mock_db() -> AsyncMock:
    """Mock AsyncSession that simulates flush/execute/scalar calls."""
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


# =============================================================================
# NotificationCategory Enum Tests
# =============================================================================


class TestNotificationCategory:
    """Tests for the NotificationCategory enum."""

    def test_all_categories_defined(self) -> None:
        """All required categories exist in the enum."""
        expected = {
            "job_completed",
            "job_failed",
            "approval_requested",
            "approval_resolved",
            "connection_expired",
            "provider_unavailable",
            "publishing_result",
            "budget_threshold",
            "safety_action",
            "hermes_needs_input",
        }
        actual = {c.value for c in NotificationCategory}
        assert actual == expected

    def test_safety_action_is_mandatory(self) -> None:
        """safety_action is in the MANDATORY_CATEGORIES set."""
        assert NotificationCategory.SAFETY_ACTION in MANDATORY_CATEGORIES

    def test_non_mandatory_categories_not_in_set(self) -> None:
        """Non-mandatory categories are not in MANDATORY_CATEGORIES."""
        non_mandatory = [
            NotificationCategory.JOB_COMPLETED,
            NotificationCategory.JOB_FAILED,
            NotificationCategory.APPROVAL_REQUESTED,
            NotificationCategory.APPROVAL_RESOLVED,
            NotificationCategory.CONNECTION_EXPIRED,
            NotificationCategory.PROVIDER_UNAVAILABLE,
            NotificationCategory.PUBLISHING_RESULT,
            NotificationCategory.BUDGET_THRESHOLD,
            NotificationCategory.HERMES_NEEDS_INPUT,
        ]
        for cat in non_mandatory:
            assert cat not in MANDATORY_CATEGORIES

    def test_mandatory_categories_frozenset_immutable(self) -> None:
        """MANDATORY_CATEGORIES is a frozenset (immutable)."""
        assert isinstance(MANDATORY_CATEGORIES, frozenset)


# =============================================================================
# NotificationChannel Protocol Tests
# =============================================================================


class TestNotificationChannelProtocol:
    """Tests for the NotificationChannel Protocol."""

    def test_in_app_channel_satisfies_protocol(self) -> None:
        """InAppChannel implements the NotificationChannel Protocol."""
        channel = InAppChannel()
        assert isinstance(channel, NotificationChannel)

    @pytest.mark.asyncio
    async def test_in_app_channel_returns_delivery_result(
        self, org_id: UUID, user_id: UUID, mock_db: AsyncMock
    ) -> None:
        """InAppChannel.deliver returns a successful DeliveryResult."""
        channel = InAppChannel()
        notification = Notification(
            id=uuid4(),
            org_id=org_id,
            user_id=user_id,
            category="job_completed",
            title="Test",
            is_read=False,
            is_mandatory=False,
            extra_data={},
        )

        result = await channel.deliver(notification, mock_db)

        assert isinstance(result, DeliveryResult)
        assert result.success is True
        assert result.channel == "in_app"
        assert result.error is None

    def test_custom_channel_satisfies_protocol(self) -> None:
        """A custom channel class with deliver() satisfies the Protocol."""

        class EmailChannel:
            async def deliver(self, notification, db):
                return DeliveryResult(success=True, channel="email")

        channel = EmailChannel()
        assert isinstance(channel, NotificationChannel)


# =============================================================================
# NotificationService.create() Tests
# =============================================================================


class TestNotificationServiceCreate:
    """Tests for NotificationService.create()."""

    @pytest.mark.asyncio
    async def test_create_basic_notification(
        self, mock_db: AsyncMock, org_id: UUID, user_id: UUID
    ) -> None:
        """Creating a notification sets correct fields on the ORM object."""
        service = NotificationService(mock_db)
        data = NotificationCreate(
            user_id=user_id,
            category=NotificationCategory.JOB_COMPLETED,
            title="Job Done",
            body="Your image generation job completed.",
            action_url="/jobs/123",
            metadata={"job_id": "j-123"},
        )

        notification = await service.create(org_id, data)

        assert notification.org_id == org_id
        assert notification.user_id == user_id
        assert notification.category == "job_completed"
        assert notification.title == "Job Done"
        assert notification.body == "Your image generation job completed."
        assert notification.action_url == "/jobs/123"
        assert notification.is_read is False
        assert notification.is_mandatory is False
        assert notification.extra_data == {"job_id": "j-123"}

    @pytest.mark.asyncio
    async def test_create_mandatory_notification(
        self, mock_db: AsyncMock, org_id: UUID, user_id: UUID
    ) -> None:
        """safety_action notifications are automatically marked mandatory."""
        service = NotificationService(mock_db)
        data = NotificationCreate(
            user_id=user_id,
            category=NotificationCategory.SAFETY_ACTION,
            title="Content Removed",
            body="Your content was removed for policy violation.",
        )

        notification = await service.create(org_id, data)

        assert notification.is_mandatory is True
        assert notification.category == "safety_action"

    @pytest.mark.asyncio
    async def test_create_non_mandatory_notification(
        self, mock_db: AsyncMock, org_id: UUID, user_id: UUID
    ) -> None:
        """Non-safety categories are NOT marked mandatory."""
        service = NotificationService(mock_db)
        data = NotificationCreate(
            user_id=user_id,
            category=NotificationCategory.JOB_FAILED,
            title="Job Failed",
        )

        notification = await service.create(org_id, data)

        assert notification.is_mandatory is False

    @pytest.mark.asyncio
    async def test_create_with_no_body_or_url(
        self, mock_db: AsyncMock, org_id: UUID, user_id: UUID
    ) -> None:
        """Notification can be created with only required fields."""
        service = NotificationService(mock_db)
        data = NotificationCreate(
            user_id=user_id,
            category=NotificationCategory.HERMES_NEEDS_INPUT,
            title="Hermes needs your input",
        )

        notification = await service.create(org_id, data)

        assert notification.body is None
        assert notification.action_url is None
        assert notification.extra_data == {}

    @pytest.mark.asyncio
    async def test_create_adds_to_session_and_flushes(
        self, mock_db: AsyncMock, org_id: UUID, user_id: UUID
    ) -> None:
        """create() adds the notification to the session and flushes."""
        service = NotificationService(mock_db)
        data = NotificationCreate(
            user_id=user_id,
            category=NotificationCategory.JOB_COMPLETED,
            title="Done",
        )

        await service.create(org_id, data)

        mock_db.add.assert_called_once()
        mock_db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_delivers_through_channels(
        self, mock_db: AsyncMock, org_id: UUID, user_id: UUID
    ) -> None:
        """create() calls deliver() on all configured channels."""
        delivered = []

        class MockChannel:
            async def deliver(self, notification, db):
                delivered.append(notification)
                return DeliveryResult(success=True, channel="mock")

        service = NotificationService(mock_db, channels=[MockChannel()])
        data = NotificationCreate(
            user_id=user_id,
            category=NotificationCategory.JOB_COMPLETED,
            title="Done",
        )

        await service.create(org_id, data)

        assert len(delivered) == 1
        assert delivered[0].title == "Done"

    @pytest.mark.asyncio
    async def test_create_delivers_through_multiple_channels(
        self, mock_db: AsyncMock, org_id: UUID, user_id: UUID
    ) -> None:
        """create() delivers to all channels when multiple are configured."""
        results = []

        class ChannelA:
            async def deliver(self, notification, db):
                results.append("A")
                return DeliveryResult(success=True, channel="a")

        class ChannelB:
            async def deliver(self, notification, db):
                results.append("B")
                return DeliveryResult(success=True, channel="b")

        service = NotificationService(mock_db, channels=[ChannelA(), ChannelB()])
        data = NotificationCreate(
            user_id=user_id,
            category=NotificationCategory.JOB_COMPLETED,
            title="Done",
        )

        await service.create(org_id, data)

        assert results == ["A", "B"]

    @pytest.mark.asyncio
    async def test_create_continues_on_channel_failure(
        self, mock_db: AsyncMock, org_id: UUID, user_id: UUID
    ) -> None:
        """If a channel raises an exception, notification is still created."""

        class FailingChannel:
            async def deliver(self, notification, db):
                raise RuntimeError("channel error")

        service = NotificationService(mock_db, channels=[FailingChannel()])
        data = NotificationCreate(
            user_id=user_id,
            category=NotificationCategory.JOB_COMPLETED,
            title="Done",
        )

        # Should not raise
        notification = await service.create(org_id, data)
        assert notification.title == "Done"
        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_continues_on_delivery_failure_result(
        self, mock_db: AsyncMock, org_id: UUID, user_id: UUID
    ) -> None:
        """If a channel returns failure result, notification is still created."""

        class SoftFailChannel:
            async def deliver(self, notification, db):
                return DeliveryResult(success=False, channel="soft_fail", error="timeout")

        service = NotificationService(mock_db, channels=[SoftFailChannel()])
        data = NotificationCreate(
            user_id=user_id,
            category=NotificationCategory.JOB_COMPLETED,
            title="Done",
        )

        notification = await service.create(org_id, data)
        assert notification.title == "Done"


# =============================================================================
# NotificationService.mark_read() Tests
# =============================================================================


class TestNotificationServiceMarkRead:
    """Tests for NotificationService.mark_read()."""

    @pytest.mark.asyncio
    async def test_mark_read_success(
        self, mock_db: AsyncMock, org_id: UUID, user_id: UUID
    ) -> None:
        """Marking a notification as read sets is_read=True."""
        notification_id = uuid4()
        notification = Notification(
            id=notification_id,
            org_id=org_id,
            user_id=user_id,
            category="job_completed",
            title="Done",
            is_read=False,
            is_mandatory=False,
            extra_data={},
        )

        # Mock the execute to return our notification
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = notification
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = NotificationService(mock_db)
        result = await service.mark_read(notification_id, org_id, user_id)

        assert result is not None
        assert result.is_read is True

    @pytest.mark.asyncio
    async def test_mark_read_returns_none_when_not_found(
        self, mock_db: AsyncMock, org_id: UUID, user_id: UUID
    ) -> None:
        """mark_read returns None if notification not found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = NotificationService(mock_db)
        result = await service.mark_read(uuid4(), org_id, user_id)

        assert result is None


# =============================================================================
# NotificationService.mark_all_read() Tests
# =============================================================================


class TestNotificationServiceMarkAllRead:
    """Tests for NotificationService.mark_all_read()."""

    @pytest.mark.asyncio
    async def test_mark_all_read_returns_count(
        self, mock_db: AsyncMock, org_id: UUID, user_id: UUID
    ) -> None:
        """mark_all_read returns the number of updated rows."""
        mock_result = MagicMock()
        mock_result.rowcount = 5
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = NotificationService(mock_db)
        count = await service.mark_all_read(org_id, user_id)

        assert count == 5

    @pytest.mark.asyncio
    async def test_mark_all_read_returns_zero_when_none(
        self, mock_db: AsyncMock, org_id: UUID, user_id: UUID
    ) -> None:
        """mark_all_read returns 0 when no unread notifications."""
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = NotificationService(mock_db)
        count = await service.mark_all_read(org_id, user_id)

        assert count == 0


# =============================================================================
# NotificationService.list_for_user() Tests
# =============================================================================


class TestNotificationServiceListForUser:
    """Tests for NotificationService.list_for_user()."""

    @pytest.mark.asyncio
    async def test_list_returns_items_and_counts(
        self, mock_db: AsyncMock, org_id: UUID, user_id: UUID
    ) -> None:
        """list_for_user returns items, total, and unread_count."""
        notification = Notification(
            id=uuid4(),
            org_id=org_id,
            user_id=user_id,
            category="job_completed",
            title="Done",
            is_read=False,
            is_mandatory=False,
            extra_data={},
        )

        # Mock scalar calls for counts
        scalar_returns = [3, 2]  # total=3, unread=2
        mock_db.scalar = AsyncMock(side_effect=scalar_returns)

        # Mock execute for items query
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [notification]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = NotificationService(mock_db)
        items, total, unread = await service.list_for_user(org_id, user_id)

        assert items == [notification]
        assert total == 3
        assert unread == 2


# =============================================================================
# NotificationService.count_unread() Tests
# =============================================================================


class TestNotificationServiceCountUnread:
    """Tests for NotificationService.count_unread()."""

    @pytest.mark.asyncio
    async def test_count_unread_returns_counts(
        self, mock_db: AsyncMock, org_id: UUID, user_id: UUID
    ) -> None:
        """count_unread returns correct unread and total."""
        mock_db.scalar = AsyncMock(side_effect=[10, 3])  # total=10, unread=3

        service = NotificationService(mock_db)
        unread, total = await service.count_unread(org_id, user_id)

        assert unread == 3
        assert total == 10

    @pytest.mark.asyncio
    async def test_count_unread_handles_none_from_db(
        self, mock_db: AsyncMock, org_id: UUID, user_id: UUID
    ) -> None:
        """count_unread handles None scalar results (empty table)."""
        mock_db.scalar = AsyncMock(side_effect=[None, None])

        service = NotificationService(mock_db)
        unread, total = await service.count_unread(org_id, user_id)

        assert unread == 0
        assert total == 0


# =============================================================================
# Mandatory Notification Enforcement Tests
# =============================================================================


class TestMandatoryNotificationEnforcement:
    """Tests that mandatory notifications cannot be disabled."""

    def test_is_category_mandatory_safety_action(self) -> None:
        """safety_action is correctly identified as mandatory."""
        service = NotificationService.__new__(NotificationService)
        assert service.is_category_mandatory(NotificationCategory.SAFETY_ACTION) is True

    def test_is_category_mandatory_job_completed(self) -> None:
        """job_completed is correctly identified as non-mandatory."""
        service = NotificationService.__new__(NotificationService)
        assert (
            service.is_category_mandatory(NotificationCategory.JOB_COMPLETED) is False
        )

    def test_is_category_mandatory_all_non_mandatory(self) -> None:
        """All non-safety categories return False."""
        service = NotificationService.__new__(NotificationService)
        non_mandatory = [
            NotificationCategory.JOB_COMPLETED,
            NotificationCategory.JOB_FAILED,
            NotificationCategory.APPROVAL_REQUESTED,
            NotificationCategory.APPROVAL_RESOLVED,
            NotificationCategory.CONNECTION_EXPIRED,
            NotificationCategory.PROVIDER_UNAVAILABLE,
            NotificationCategory.PUBLISHING_RESULT,
            NotificationCategory.BUDGET_THRESHOLD,
            NotificationCategory.HERMES_NEEDS_INPUT,
        ]
        for cat in non_mandatory:
            assert service.is_category_mandatory(cat) is False

    @pytest.mark.asyncio
    async def test_mandatory_flag_auto_set_on_create(
        self, mock_db: AsyncMock, org_id: UUID, user_id: UUID
    ) -> None:
        """Creating a safety_action notification auto-sets is_mandatory=True."""
        service = NotificationService(mock_db)
        data = NotificationCreate(
            user_id=user_id,
            category=NotificationCategory.SAFETY_ACTION,
            title="Takedown Notice",
            body="Content removed.",
        )

        notification = await service.create(org_id, data)

        assert notification.is_mandatory is True

    @pytest.mark.asyncio
    async def test_non_mandatory_flag_for_regular_notifications(
        self, mock_db: AsyncMock, org_id: UUID, user_id: UUID
    ) -> None:
        """Creating a regular notification sets is_mandatory=False."""
        service = NotificationService(mock_db)
        data = NotificationCreate(
            user_id=user_id,
            category=NotificationCategory.BUDGET_THRESHOLD,
            title="Budget Warning",
        )

        notification = await service.create(org_id, data)

        assert notification.is_mandatory is False


# =============================================================================
# Schema Validation Tests
# =============================================================================


class TestNotificationSchemas:
    """Tests for Pydantic schema validation."""

    def test_create_schema_rejects_empty_title(self) -> None:
        """NotificationCreate rejects empty title."""
        with pytest.raises(Exception):
            NotificationCreate(
                user_id=uuid4(),
                category=NotificationCategory.JOB_COMPLETED,
                title="",
            )

    def test_create_schema_rejects_invalid_category(self) -> None:
        """NotificationCreate rejects invalid category value."""
        with pytest.raises(Exception):
            NotificationCreate(
                user_id=uuid4(),
                category="not_a_real_category",  # type: ignore[arg-type]
                title="Test",
            )

    def test_create_schema_accepts_valid_input(self) -> None:
        """NotificationCreate accepts valid data."""
        uid = uuid4()
        data = NotificationCreate(
            user_id=uid,
            category=NotificationCategory.JOB_COMPLETED,
            title="Done",
            body="Job finished.",
            action_url="/jobs/123",
            metadata={"job_id": "j-123"},
        )

        assert data.user_id == uid
        assert data.category == NotificationCategory.JOB_COMPLETED
        assert data.title == "Done"
        assert data.metadata == {"job_id": "j-123"}

    def test_create_schema_rejects_extra_fields(self) -> None:
        """NotificationCreate rejects unknown fields."""
        with pytest.raises(Exception):
            NotificationCreate(
                user_id=uuid4(),
                category=NotificationCategory.JOB_COMPLETED,
                title="Done",
                unknown_field="bad",  # type: ignore[call-arg]
            )

    def test_response_schema_from_dict(self) -> None:
        """NotificationResponse can be created from dict with extra_data alias."""
        now = datetime.now(UTC)
        response = NotificationResponse.model_validate({
            "id": uuid4(),
            "org_id": uuid4(),
            "user_id": uuid4(),
            "category": "job_completed",
            "title": "Done",
            "body": None,
            "action_url": None,
            "is_read": False,
            "is_mandatory": False,
            "extra_data": {"key": "val"},
            "created_at": now,
            "updated_at": now,
        })

        assert response.category == "job_completed"
        assert response.is_read is False
        assert response.metadata == {"key": "val"}

    def test_list_response_schema(self) -> None:
        """NotificationListResponse validates correctly."""
        response = NotificationListResponse(
            items=[],
            total=0,
            unread_count=0,
            limit=20,
            offset=0,
        )
        assert response.total == 0
        assert response.unread_count == 0

    def test_count_response_schema(self) -> None:
        """NotificationCountResponse validates correctly."""
        response = NotificationCountResponse(
            unread_count=5,
            total=10,
        )
        assert response.unread_count == 5
        assert response.total == 10

    def test_list_response_rejects_negative_total(self) -> None:
        """NotificationListResponse rejects negative total."""
        with pytest.raises(Exception):
            NotificationListResponse(
                items=[],
                total=-1,
                unread_count=0,
                limit=20,
                offset=0,
            )


# =============================================================================
# DeliveryResult Tests
# =============================================================================


class TestDeliveryResult:
    """Tests for the DeliveryResult dataclass."""

    def test_success_result(self) -> None:
        """DeliveryResult can represent success."""
        result = DeliveryResult(success=True, channel="in_app")
        assert result.success is True
        assert result.channel == "in_app"
        assert result.error is None

    def test_failure_result(self) -> None:
        """DeliveryResult can represent failure with error message."""
        result = DeliveryResult(success=False, channel="email", error="SMTP timeout")
        assert result.success is False
        assert result.channel == "email"
        assert result.error == "SMTP timeout"

    def test_result_is_frozen(self) -> None:
        """DeliveryResult is immutable (frozen dataclass)."""
        result = DeliveryResult(success=True, channel="in_app")
        with pytest.raises(AttributeError):
            result.success = False  # type: ignore[misc]

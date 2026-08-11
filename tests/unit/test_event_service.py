"""Unit tests for the event delivery layer.

Tests the EventEnvelope, InMemoryEventBus, tenant isolation, deduplication,
subscription timeout, and publish_event convenience function.

Requirements: R63.1, R63.2, R63.3
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from app.services.event_adapters.in_memory import InMemoryEventBus, InMemorySubscription
from app.services.event_service import (
    EventBus,
    EventEnvelope,
    EventPublishError,
    EventType,
    Subscription,
    get_event_bus,
    publish_event,
    reset_event_bus,
    set_event_bus,
)

# =============================================================================
# EventEnvelope Tests
# =============================================================================


class TestEventEnvelope:
    """Tests for EventEnvelope creation and field defaults."""

    def test_create_with_all_fields(self) -> None:
        """EventEnvelope can be created with all fields specified."""
        event_id = uuid4()
        correlation_id = uuid4()
        causation_id = uuid4()
        ts = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)

        envelope = EventEnvelope(
            event_type="job.completed",
            event_id=event_id,
            version=2,
            correlation_id=correlation_id,
            causation_id=causation_id,
            sequence=42,
            timestamp=ts,
            org_id="org-123",
            user_id="user-456",
            payload={"job_id": "j-789", "status": "completed"},
        )

        assert envelope.event_type == "job.completed"
        assert envelope.event_id == event_id
        assert envelope.version == 2
        assert envelope.correlation_id == correlation_id
        assert envelope.causation_id == causation_id
        assert envelope.sequence == 42
        assert envelope.timestamp == ts
        assert envelope.org_id == "org-123"
        assert envelope.user_id == "user-456"
        assert envelope.payload == {"job_id": "j-789", "status": "completed"}

    def test_create_with_defaults(self) -> None:
        """EventEnvelope uses sensible defaults for optional fields."""
        envelope = EventEnvelope(
            event_type="asset.created",
            org_id="org-abc",
        )

        assert envelope.event_type == "asset.created"
        assert isinstance(envelope.event_id, UUID)
        assert envelope.version == 1
        assert envelope.correlation_id is None
        assert envelope.causation_id is None
        assert envelope.sequence == 0
        assert isinstance(envelope.timestamp, datetime)
        assert envelope.timestamp.tzinfo is not None
        assert envelope.org_id == "org-abc"
        assert envelope.user_id is None
        assert envelope.payload == {}

    def test_envelope_is_frozen(self) -> None:
        """EventEnvelope is immutable (frozen dataclass)."""
        envelope = EventEnvelope(event_type="job.submitted", org_id="org-1")

        with pytest.raises(AttributeError):
            envelope.event_type = "job.failed"  # type: ignore[misc]

    def test_unique_event_ids(self) -> None:
        """Each EventEnvelope gets a unique event_id by default."""
        e1 = EventEnvelope(event_type="job.submitted", org_id="org-1")
        e2 = EventEnvelope(event_type="job.submitted", org_id="org-1")

        assert e1.event_id != e2.event_id

    def test_timestamp_is_utc(self) -> None:
        """Default timestamp is in UTC."""
        envelope = EventEnvelope(event_type="job.submitted", org_id="org-1")

        assert envelope.timestamp.tzinfo == UTC


# =============================================================================
# EventType Constants Tests
# =============================================================================


class TestEventTypeConstants:
    """Tests for event type constant definitions."""

    def test_job_lifecycle_events_exist(self) -> None:
        """All job lifecycle event types are defined."""
        assert EventType.JOB_SUBMITTED == "job.submitted"
        assert EventType.JOB_CLAIMED == "job.claimed"
        assert EventType.JOB_RUNNING == "job.running"
        assert EventType.JOB_COMPLETED == "job.completed"
        assert EventType.JOB_FAILED == "job.failed"

    def test_asset_lifecycle_events_exist(self) -> None:
        """All asset lifecycle event types are defined."""
        assert EventType.ASSET_CREATED == "asset.created"
        assert EventType.ASSET_DELETED == "asset.deleted"

    def test_talent_lifecycle_events_exist(self) -> None:
        """All talent lifecycle event types are defined."""
        assert EventType.TALENT_CREATED == "talent.created"
        assert EventType.TALENT_UPDATED == "talent.updated"
        assert EventType.TALENT_DELETED == "talent.deleted"

    def test_training_events_exist(self) -> None:
        """Training lifecycle event types are defined."""
        assert EventType.TRAINING_STARTED == "training.started"
        assert EventType.TRAINING_COMPLETED == "training.completed"

    def test_notification_event_exists(self) -> None:
        """Notification event type is defined."""
        assert EventType.NOTIFICATION_NEW == "notification.new"


# =============================================================================
# Protocol Compliance Tests
# =============================================================================


class TestProtocolCompliance:
    """Tests that InMemoryEventBus satisfies the EventBus Protocol."""

    def test_in_memory_bus_satisfies_event_bus_protocol(self) -> None:
        """InMemoryEventBus is a valid EventBus implementation."""
        bus = InMemoryEventBus()
        assert isinstance(bus, EventBus)

    def test_in_memory_subscription_satisfies_protocol(self) -> None:
        """InMemorySubscription is a valid Subscription implementation."""
        sub = InMemorySubscription(org_id="org-1")
        assert isinstance(sub, Subscription)


# =============================================================================
# InMemoryEventBus Tests
# =============================================================================


class TestInMemoryEventBusPublishSubscribe:
    """Tests for InMemoryEventBus publish/subscribe round-trip."""

    @pytest.mark.asyncio
    async def test_publish_subscribe_round_trip(self) -> None:
        """Published events are received by matching subscriptions."""
        bus = InMemoryEventBus()
        sub = await bus.subscribe("org-123", event_types=["job.completed"])

        event = EventEnvelope(
            event_type="job.completed",
            org_id="org-123",
            payload={"job_id": "j-1"},
        )
        await bus.publish(event)

        received = await sub.receive(timeout=1.0)
        assert received is not None
        assert received.event_type == "job.completed"
        assert received.org_id == "org-123"
        assert received.payload == {"job_id": "j-1"}
        assert received.event_id == event.event_id

    @pytest.mark.asyncio
    async def test_subscribe_all_event_types(self) -> None:
        """Subscription without event_types filter receives all org events."""
        bus = InMemoryEventBus()
        sub = await bus.subscribe("org-123")

        await bus.publish(
            EventEnvelope(event_type="job.submitted", org_id="org-123")
        )
        await bus.publish(
            EventEnvelope(event_type="asset.created", org_id="org-123")
        )

        e1 = await sub.receive(timeout=1.0)
        e2 = await sub.receive(timeout=1.0)

        assert e1 is not None
        assert e1.event_type == "job.submitted"
        assert e2 is not None
        assert e2.event_type == "asset.created"

    @pytest.mark.asyncio
    async def test_event_type_filter(self) -> None:
        """Subscription with event_types filter only receives matching types."""
        bus = InMemoryEventBus()
        sub = await bus.subscribe("org-123", event_types=["job.completed"])

        await bus.publish(
            EventEnvelope(event_type="job.submitted", org_id="org-123")
        )
        await bus.publish(
            EventEnvelope(event_type="job.completed", org_id="org-123")
        )

        received = await sub.receive(timeout=1.0)
        assert received is not None
        assert received.event_type == "job.completed"

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self) -> None:
        """Multiple subscribers for same org all receive the event."""
        bus = InMemoryEventBus()
        sub1 = await bus.subscribe("org-123")
        sub2 = await bus.subscribe("org-123")

        event = EventEnvelope(event_type="job.completed", org_id="org-123")
        await bus.publish(event)

        r1 = await sub1.receive(timeout=1.0)
        r2 = await sub2.receive(timeout=1.0)

        assert r1 is not None
        assert r2 is not None
        assert r1.event_id == r2.event_id

    @pytest.mark.asyncio
    async def test_published_events_stored(self) -> None:
        """All published events are stored for test inspection."""
        bus = InMemoryEventBus()

        e1 = EventEnvelope(event_type="job.submitted", org_id="org-1")
        e2 = EventEnvelope(event_type="job.completed", org_id="org-1")

        await bus.publish(e1)
        await bus.publish(e2)

        assert len(bus.published_events) == 2
        assert bus.published_events[0].event_id == e1.event_id
        assert bus.published_events[1].event_id == e2.event_id


# =============================================================================
# Tenant Isolation Tests
# =============================================================================


class TestTenantIsolation:
    """Tests that subscriptions enforce strict tenant isolation (R63.2)."""

    @pytest.mark.asyncio
    async def test_org_a_never_receives_org_b_events(self) -> None:
        """Subscription for org A never receives events published for org B."""
        bus = InMemoryEventBus()
        sub_a = await bus.subscribe("org-A")
        sub_b = await bus.subscribe("org-B")

        # Publish event for org B only
        await bus.publish(
            EventEnvelope(event_type="job.completed", org_id="org-B")
        )

        # org A should NOT receive it
        received_a = await sub_a.receive(timeout=0.1)
        assert received_a is None

        # org B should receive it
        received_b = await sub_b.receive(timeout=0.1)
        assert received_b is not None
        assert received_b.org_id == "org-B"

    @pytest.mark.asyncio
    async def test_publish_rejects_empty_org_id(self) -> None:
        """Publishing an event without org_id raises ValueError."""
        bus = InMemoryEventBus()

        with pytest.raises(ValueError, match="org_id"):
            await bus.publish(
                EventEnvelope(event_type="job.completed", org_id="")
            )

    @pytest.mark.asyncio
    async def test_publish_rejects_whitespace_org_id(self) -> None:
        """Publishing an event with whitespace-only org_id raises ValueError."""
        bus = InMemoryEventBus()

        with pytest.raises(ValueError, match="org_id"):
            await bus.publish(
                EventEnvelope(event_type="job.completed", org_id="   ")
            )

    @pytest.mark.asyncio
    async def test_subscribe_rejects_empty_org_id(self) -> None:
        """Subscribing without org_id raises ValueError."""
        bus = InMemoryEventBus()

        with pytest.raises(ValueError, match="org_id"):
            await bus.subscribe("")

    @pytest.mark.asyncio
    async def test_subscribe_rejects_whitespace_org_id(self) -> None:
        """Subscribing with whitespace-only org_id raises ValueError."""
        bus = InMemoryEventBus()

        with pytest.raises(ValueError, match="org_id"):
            await bus.subscribe("   ")

    @pytest.mark.asyncio
    async def test_many_orgs_isolated(self) -> None:
        """Events stay within their tenant across many organizations."""
        bus = InMemoryEventBus()
        org_ids = [f"org-{i}" for i in range(10)]
        subs = {oid: await bus.subscribe(oid) for oid in org_ids}

        # Publish one event per org
        for oid in org_ids:
            await bus.publish(
                EventEnvelope(event_type="job.completed", org_id=oid)
            )

        # Each subscription should receive exactly one event — its own
        for oid in org_ids:
            received = await subs[oid].receive(timeout=0.1)
            assert received is not None
            assert received.org_id == oid

            # No more events
            extra = await subs[oid].receive(timeout=0.05)
            assert extra is None


# =============================================================================
# Deduplication Tests
# =============================================================================


class TestDeduplication:
    """Tests for event deduplication by event_id."""

    @pytest.mark.asyncio
    async def test_duplicate_event_id_deduplicated(self) -> None:
        """Same event_id published twice is only received once."""
        bus = InMemoryEventBus()
        sub = await bus.subscribe("org-123")

        shared_id = uuid4()
        event1 = EventEnvelope(
            event_type="job.completed",
            event_id=shared_id,
            org_id="org-123",
        )
        event2 = EventEnvelope(
            event_type="job.completed",
            event_id=shared_id,
            org_id="org-123",
        )

        await bus.publish(event1)
        await bus.publish(event2)

        # First receive returns the event
        first = await sub.receive(timeout=0.5)
        assert first is not None
        assert first.event_id == shared_id

        # Second receive returns None (deduplicated)
        second = await sub.receive(timeout=0.1)
        assert second is None


# =============================================================================
# Subscription Timeout Tests
# =============================================================================


class TestSubscriptionTimeout:
    """Tests for subscription receive timeout behavior."""

    @pytest.mark.asyncio
    async def test_receive_returns_none_on_timeout(self) -> None:
        """Receive returns None when no events arrive within timeout."""
        bus = InMemoryEventBus()
        sub = await bus.subscribe("org-123")

        result = await sub.receive(timeout=0.05)
        assert result is None

    @pytest.mark.asyncio
    async def test_unsubscribed_receives_none(self) -> None:
        """After unsubscribe, receive always returns None."""
        bus = InMemoryEventBus()
        sub = await bus.subscribe("org-123")

        await sub.unsubscribe()

        result = await sub.receive(timeout=0.05)
        assert result is None

    @pytest.mark.asyncio
    async def test_unsubscribed_stops_receiving_new_events(self) -> None:
        """After unsubscribe, new events are not delivered."""
        bus = InMemoryEventBus()
        sub = await bus.subscribe("org-123")
        await sub.unsubscribe()

        await bus.publish(
            EventEnvelope(event_type="job.completed", org_id="org-123")
        )

        result = await sub.receive(timeout=0.05)
        assert result is None


# =============================================================================
# publish_event() Convenience Function Tests
# =============================================================================


class TestPublishEventFunction:
    """Tests for the publish_event() convenience function."""

    @pytest.fixture(autouse=True)
    def _reset_bus(self) -> None:
        """Reset global event bus before and after each test."""
        reset_event_bus()
        yield  # type: ignore[misc]
        reset_event_bus()

    @pytest.mark.asyncio
    async def test_publish_event_returns_envelope(self) -> None:
        """publish_event returns a fully populated EventEnvelope."""
        bus = InMemoryEventBus()
        set_event_bus(bus)

        result = await publish_event(
            event_type="job.completed",
            org_id="org-123",
            payload={"job_id": "j-1"},
            user_id="user-456",
        )

        assert isinstance(result, EventEnvelope)
        assert result.event_type == "job.completed"
        assert result.org_id == "org-123"
        assert result.payload == {"job_id": "j-1"}
        assert result.user_id == "user-456"
        assert isinstance(result.event_id, UUID)
        assert result.sequence > 0

    @pytest.mark.asyncio
    async def test_publish_event_rejects_empty_org_id(self) -> None:
        """publish_event raises ValueError for empty org_id."""
        bus = InMemoryEventBus()
        set_event_bus(bus)

        with pytest.raises(ValueError, match="org_id"):
            await publish_event(
                event_type="job.completed",
                org_id="",
            )

    @pytest.mark.asyncio
    async def test_publish_event_rejects_whitespace_org_id(self) -> None:
        """publish_event raises ValueError for whitespace-only org_id."""
        bus = InMemoryEventBus()
        set_event_bus(bus)

        with pytest.raises(ValueError, match="org_id"):
            await publish_event(
                event_type="job.completed",
                org_id="   ",
            )

    @pytest.mark.asyncio
    async def test_publish_event_raises_when_no_bus_configured(self) -> None:
        """publish_event raises EventPublishError when no bus is set."""
        # Don't set any bus
        with pytest.raises(EventPublishError, match="No event bus configured"):
            await publish_event(
                event_type="job.completed",
                org_id="org-123",
            )

    @pytest.mark.asyncio
    async def test_publish_event_with_correlation_id(self) -> None:
        """publish_event passes correlation_id to the envelope."""
        bus = InMemoryEventBus()
        set_event_bus(bus)
        corr_id = uuid4()

        result = await publish_event(
            event_type="job.submitted",
            org_id="org-123",
            correlation_id=corr_id,
        )

        assert result.correlation_id == corr_id

    @pytest.mark.asyncio
    async def test_publish_event_increments_sequence(self) -> None:
        """publish_event increments the global sequence counter."""
        bus = InMemoryEventBus()
        set_event_bus(bus)

        e1 = await publish_event(event_type="job.submitted", org_id="org-1")
        e2 = await publish_event(event_type="job.completed", org_id="org-1")

        assert e2.sequence > e1.sequence

    @pytest.mark.asyncio
    async def test_set_get_event_bus(self) -> None:
        """set_event_bus and get_event_bus work correctly."""
        assert get_event_bus() is None

        bus = InMemoryEventBus()
        set_event_bus(bus)

        assert get_event_bus() is bus

    @pytest.mark.asyncio
    async def test_publish_event_delivers_to_subscriber(self) -> None:
        """publish_event delivers to subscribers via the configured bus."""
        bus = InMemoryEventBus()
        set_event_bus(bus)

        sub = await bus.subscribe("org-123", event_types=["job.completed"])

        await publish_event(
            event_type="job.completed",
            org_id="org-123",
            payload={"result": "success"},
        )

        received = await sub.receive(timeout=1.0)
        assert received is not None
        assert received.event_type == "job.completed"
        assert received.payload == {"result": "success"}

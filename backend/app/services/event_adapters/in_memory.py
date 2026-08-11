"""In-memory event bus adapter for testing.

Provides a fully functional EventBus implementation that stores events
in memory and delivers them to subscriptions via asyncio.Queue. No
external dependencies required.

Enforces tenant isolation: subscriptions only receive events matching
their org_id and optional event_type filters.

Requirements: R63.1, R63.2
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from app.core.logging import get_logger
from app.services.event_service import EventEnvelope

logger = get_logger(__name__)


@dataclass
class InMemorySubscription:
    """In-memory subscription backed by asyncio.Queue.

    Receives events pushed by the InMemoryEventBus when they match
    this subscription's org_id and event_type filters.
    """

    org_id: str
    event_types: list[str] | None = None
    _queue: asyncio.Queue[EventEnvelope] = field(
        default_factory=lambda: asyncio.Queue()
    )
    _active: bool = True
    _seen_event_ids: set = field(default_factory=set)

    async def receive(self, timeout: float = 30.0) -> EventEnvelope | None:
        """Receive the next event, or None if timeout elapses.

        Performs deduplication: if an event with the same event_id has
        already been received by this subscription, it is skipped.

        Args:
            timeout: Maximum seconds to wait for the next event.

        Returns:
            The next EventEnvelope, or None on timeout.
        """
        if not self._active:
            return None

        try:
            event = await asyncio.wait_for(self._queue.get(), timeout=timeout)
            # Deduplication by event_id
            if event.event_id in self._seen_event_ids:
                return None
            self._seen_event_ids.add(event.event_id)
            return event
        except TimeoutError:
            return None

    async def unsubscribe(self) -> None:
        """Mark subscription as inactive and stop receiving events."""
        self._active = False

    def matches(self, event: EventEnvelope) -> bool:
        """Check if an event matches this subscription's filters.

        Args:
            event: The event to check.

        Returns:
            True if the event matches org_id and event_type filters.
        """
        if event.org_id != self.org_id:
            return False
        if self.event_types is not None:
            return event.event_type in self.event_types
        return True


class InMemoryEventBus:
    """In-memory EventBus implementation for testing.

    Stores published events in a list and delivers them to matching
    subscriptions in real-time via asyncio.Queue.

    Thread-safety: Not thread-safe. Designed for single-threaded asyncio
    test environments.
    """

    def __init__(self) -> None:
        self._subscriptions: list[InMemorySubscription] = []
        self._published_events: list[EventEnvelope] = []

    @property
    def published_events(self) -> list[EventEnvelope]:
        """All events published through this bus (for test assertions)."""
        return self._published_events

    async def publish(self, event: EventEnvelope) -> None:
        """Publish an event to all matching subscriptions.

        Enforces tenant isolation: only subscriptions with matching
        org_id receive the event.

        Args:
            event: The event envelope to publish.

        Raises:
            ValueError: If event.org_id is empty.
        """
        if not event.org_id or not event.org_id.strip():
            raise ValueError("Cannot publish event without org_id")

        self._published_events.append(event)

        # Deliver to matching active subscriptions
        for sub in self._subscriptions:
            if sub._active and sub.matches(event):
                await sub._queue.put(event)

        logger.debug(
            "event_published_in_memory",
            event_type=event.event_type,
            org_id=event.org_id,
            subscriber_count=sum(
                1 for s in self._subscriptions if s._active and s.matches(event)
            ),
        )

    async def subscribe(
        self, org_id: str, event_types: list[str] | None = None
    ) -> InMemorySubscription:
        """Create a subscription for events matching org_id and event_types.

        Enforces tenant authorization: org_id must be non-empty.

        Args:
            org_id: The tenant to subscribe to (required, non-empty).
            event_types: Optional filter — only these event types are
                delivered. If None, all events for the org are delivered.

        Returns:
            An InMemorySubscription for receiving events.

        Raises:
            ValueError: If org_id is empty.
        """
        if not org_id or not org_id.strip():
            raise ValueError("org_id is required for subscription (tenant isolation)")

        subscription = InMemorySubscription(
            org_id=org_id,
            event_types=event_types,
        )
        self._subscriptions.append(subscription)

        logger.debug(
            "subscription_created_in_memory",
            org_id=org_id,
            event_types=event_types,
        )

        return subscription

    def clear(self) -> None:
        """Clear all subscriptions and published events (test cleanup)."""
        self._subscriptions.clear()
        self._published_events.clear()

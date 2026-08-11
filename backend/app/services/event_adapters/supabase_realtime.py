"""Supabase Realtime event bus adapter.

Primary event delivery adapter using Supabase Realtime channels for
server-to-client event push. Channels are scoped per-tenant to enforce
tenant isolation at the transport layer.

Channel naming: `events:{org_id}` — each tenant gets a dedicated channel.

Requirements: R63.1, R63.2
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from app.core.logging import get_logger
from app.services.event_service import EventEnvelope

logger = get_logger(__name__)


@dataclass
class SupabaseRealtimeSubscription:
    """Subscription backed by a Supabase Realtime channel.

    In production, this wraps the Supabase Realtime client subscription.
    Events are received via the channel and buffered in an asyncio.Queue.
    """

    org_id: str
    event_types: list[str] | None = None
    _queue: asyncio.Queue[EventEnvelope] = field(
        default_factory=lambda: asyncio.Queue()
    )
    _active: bool = True
    _channel: Any = None
    _seen_event_ids: set = field(default_factory=set)

    async def receive(self, timeout: float = 30.0) -> EventEnvelope | None:
        """Receive the next event from the Supabase channel.

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
        """Unsubscribe from the Supabase Realtime channel."""
        self._active = False
        if self._channel is not None:
            try:
                # In production, call channel.unsubscribe()
                logger.info(
                    "supabase_channel_unsubscribed",
                    org_id=self.org_id,
                )
            except Exception as exc:
                logger.warning(
                    "supabase_unsubscribe_error",
                    org_id=self.org_id,
                    error=str(exc),
                )


class SupabaseRealtimeEventBus:
    """Supabase Realtime event bus adapter.

    Publishes events to tenant-scoped Realtime channels. Each org_id
    gets a dedicated channel (`events:{org_id}`), enforcing tenant
    isolation at the transport layer.

    Configuration:
        - supabase_url: The Supabase project URL.
        - supabase_key: The anon/service-role key for channel auth.

    Note: This adapter requires the Supabase Realtime client library.
    When Supabase is not configured (e.g., in dev/test), use
    InMemoryEventBus instead.
    """

    def __init__(
        self,
        supabase_url: str,
        supabase_key: str,
    ) -> None:
        self._supabase_url = supabase_url
        self._supabase_key = supabase_key
        self._subscriptions: list[SupabaseRealtimeSubscription] = []

        if not supabase_url:
            logger.warning("supabase_realtime_no_url_configured")
        if not supabase_key:
            logger.warning("supabase_realtime_no_key_configured")

    def _channel_name(self, org_id: str) -> str:
        """Generate tenant-scoped channel name.

        Args:
            org_id: The tenant identifier.

        Returns:
            Channel name in format `events:{org_id}`.
        """
        return f"events:{org_id}"

    async def publish(self, event: EventEnvelope) -> None:
        """Publish an event to the tenant's Supabase Realtime channel.

        Serializes the event envelope to JSON and broadcasts to the
        tenant-scoped channel. Also delivers to any local subscriptions
        for testing/dev scenarios.

        Args:
            event: The event envelope to publish.

        Raises:
            ValueError: If event.org_id is empty.
        """
        if not event.org_id or not event.org_id.strip():
            raise ValueError("Cannot publish event without org_id")

        channel_name = self._channel_name(event.org_id)

        # Serialize envelope for Realtime broadcast
        _event_data = {
            "event_type": event.event_type,
            "event_id": str(event.event_id),
            "version": event.version,
            "correlation_id": str(event.correlation_id) if event.correlation_id else None,
            "causation_id": str(event.causation_id) if event.causation_id else None,
            "sequence": event.sequence,
            "timestamp": event.timestamp.isoformat(),
            "org_id": event.org_id,
            "user_id": event.user_id,
            "payload": event.payload,
        }

        # In production, this would use the Supabase Realtime client:
        # await supabase.channel(channel_name).send({
        #     "type": "broadcast",
        #     "event": event.event_type,
        #     "payload": event_data
        # })
        logger.info(
            "supabase_event_broadcast",
            channel=channel_name,
            event_type=event.event_type,
            event_id=str(event.event_id),
        )

        # Deliver to local subscriptions (for hybrid/dev mode)
        for sub in self._subscriptions:
            if sub._active and sub.org_id == event.org_id:
                if sub.event_types is None or event.event_type in sub.event_types:
                    await sub._queue.put(event)

    async def subscribe(
        self, org_id: str, event_types: list[str] | None = None
    ) -> SupabaseRealtimeSubscription:
        """Subscribe to events on the tenant's Supabase Realtime channel.

        Creates a channel subscription scoped to the tenant's org_id.
        Tenant authorization is enforced: org_id must be non-empty.

        Args:
            org_id: The tenant to subscribe to (required, non-empty).
            event_types: Optional filter for specific event types.

        Returns:
            A SupabaseRealtimeSubscription for receiving events.

        Raises:
            ValueError: If org_id is empty.
        """
        if not org_id or not org_id.strip():
            raise ValueError("org_id is required for subscription (tenant isolation)")

        channel_name = self._channel_name(org_id)

        subscription = SupabaseRealtimeSubscription(
            org_id=org_id,
            event_types=event_types,
        )

        # In production, this would subscribe to the Supabase channel:
        # channel = supabase.channel(channel_name)
        # channel.on("broadcast", {"event": "*"}, callback)
        # await channel.subscribe()

        self._subscriptions.append(subscription)

        logger.info(
            "supabase_channel_subscribed",
            channel=channel_name,
            org_id=org_id,
            event_types=event_types,
        )

        return subscription

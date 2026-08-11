"""Event delivery layer — provider-neutral event bus with tenant isolation.

Defines the canonical EventEnvelope, EventBus Protocol, Subscription Protocol,
event type constants, and a convenience publish_event() function.

The event system supports Supabase Realtime as primary adapter with
InMemoryEventBus for testing. All subscriptions are tenant-scoped —
a client will ONLY receive events for their authenticated org_id.

Requirements: R63.1, R63.2, R63.3
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable
from uuid import UUID, uuid4

from app.core.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Event Type Constants
# =============================================================================


class EventType(StrEnum):
    """Canonical event types for the platform.

    Naming convention: {domain}.{action} (lowercase, dot-separated).
    """

    # Job lifecycle
    JOB_SUBMITTED = "job.submitted"
    JOB_CLAIMED = "job.claimed"
    JOB_RUNNING = "job.running"
    JOB_COMPLETED = "job.completed"
    JOB_FAILED = "job.failed"

    # Asset lifecycle
    ASSET_CREATED = "asset.created"
    ASSET_DELETED = "asset.deleted"

    # Talent lifecycle
    TALENT_CREATED = "talent.created"
    TALENT_UPDATED = "talent.updated"
    TALENT_DELETED = "talent.deleted"

    # Training lifecycle
    TRAINING_STARTED = "training.started"
    TRAINING_COMPLETED = "training.completed"

    # Notifications
    NOTIFICATION_NEW = "notification.new"

    # Approvals
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_RESOLVED = "approval.resolved"

    # Cost
    COST_THRESHOLD_REACHED = "cost.threshold_reached"

    # Connections (Rev 4 extended)
    CONNECTION_STATE_CHANGED = "connection.state_changed"

    # Compute (Rev 4 extended)
    COMPUTE_STATE_CHANGED = "compute.state_changed"


# =============================================================================
# Event Envelope
# =============================================================================


@dataclass(frozen=True)
class EventEnvelope:
    """Canonical event envelope per design spec (R63.3).

    All fields are immutable once created. The envelope carries metadata
    for deduplication, ordering, correlation, and tenant scoping.

    Attributes:
        event_type: Domain event type (e.g., "job.completed").
        event_id: Unique ID for deduplication.
        version: Schema version for envelope evolution.
        correlation_id: Links related events across a request chain.
        causation_id: What caused this event (parent event_id).
        sequence: Monotonic cursor for ordering and resumption.
        timestamp: When the event was created (UTC).
        org_id: Tenant scope — events are ALWAYS scoped to an org.
        user_id: Originating user (optional, for audit).
        payload: Event-specific data dictionary.
    """

    event_type: str
    event_id: UUID = field(default_factory=uuid4)
    version: int = 1
    correlation_id: UUID | None = None
    causation_id: UUID | None = None
    sequence: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    org_id: str = ""
    user_id: str | None = None
    payload: dict = field(default_factory=dict)


# =============================================================================
# Protocols
# =============================================================================


@runtime_checkable
class Subscription(Protocol):
    """Protocol for event subscription.

    Subscriptions are async iterators that receive events matching
    the subscribed event types for a specific tenant.
    """

    async def receive(self, timeout: float = 30.0) -> EventEnvelope | None:
        """Receive the next event, or None if timeout elapses.

        Args:
            timeout: Maximum seconds to wait for the next event.

        Returns:
            The next EventEnvelope, or None on timeout.
        """
        ...

    async def unsubscribe(self) -> None:
        """Unsubscribe and release resources."""
        ...


@runtime_checkable
class EventBus(Protocol):
    """Protocol for event delivery (R63.1).

    Implementations must enforce tenant isolation: subscriptions
    only receive events for the authenticated org_id.
    """

    async def publish(self, event: EventEnvelope) -> None:
        """Publish an event to all matching subscribers.

        Args:
            event: The event envelope to publish.

        Raises:
            ValueError: If event.org_id is empty.
        """
        ...

    async def subscribe(
        self, org_id: str, event_types: list[str] | None = None
    ) -> Subscription:
        """Subscribe to events for a specific tenant.

        Args:
            org_id: The tenant to subscribe to (required, non-empty).
            event_types: Optional filter — if provided, only these types
                are delivered. If None, all events for the org are delivered.

        Returns:
            A Subscription object for receiving events.

        Raises:
            ValueError: If org_id is empty.
        """
        ...


# =============================================================================
# Convenience publisher
# =============================================================================


class EventPublishError(Exception):
    """Raised when event publishing fails."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


_event_bus_instance: EventBus | None = None
_sequence_counter: int = 0


def set_event_bus(bus: EventBus) -> None:
    """Set the global event bus instance.

    Called once at application startup to configure the active adapter.

    Args:
        bus: An EventBus implementation to use for publishing.
    """
    global _event_bus_instance
    _event_bus_instance = bus
    logger.info("event_bus_configured", adapter=type(bus).__name__)


def get_event_bus() -> EventBus | None:
    """Get the current event bus instance.

    Returns:
        The configured EventBus, or None if not yet configured.
    """
    return _event_bus_instance


async def publish_event(
    event_type: str,
    org_id: str,
    payload: dict | None = None,
    correlation_id: UUID | None = None,
    causation_id: UUID | None = None,
    user_id: str | None = None,
) -> EventEnvelope:
    """Convenience function for publishing events.

    Validates org_id, generates event_id and timestamp, increments the
    global sequence counter, and publishes via the configured EventBus.

    Args:
        event_type: The event type string (e.g., "job.completed").
        org_id: Tenant scope (required, non-empty).
        payload: Event-specific data dictionary.
        correlation_id: Optional correlation ID linking related events.
        causation_id: Optional ID of the event that caused this one.
        user_id: Optional originating user ID.

    Returns:
        The published EventEnvelope.

    Raises:
        ValueError: If org_id is empty.
        EventPublishError: If no event bus is configured.
    """
    if not org_id or not org_id.strip():
        raise ValueError("org_id is required and cannot be empty")

    if _event_bus_instance is None:
        raise EventPublishError(
            "No event bus configured. Call set_event_bus() at startup."
        )

    global _sequence_counter
    _sequence_counter += 1

    event = EventEnvelope(
        event_type=event_type,
        event_id=uuid4(),
        version=1,
        correlation_id=correlation_id,
        causation_id=causation_id,
        sequence=_sequence_counter,
        timestamp=datetime.now(UTC),
        org_id=org_id,
        user_id=user_id,
        payload=payload or {},
    )

    await _event_bus_instance.publish(event)

    logger.info(
        "event_published",
        event_type=event_type,
        event_id=str(event.event_id),
        org_id=org_id,
        sequence=event.sequence,
    )

    return event


def reset_event_bus() -> None:
    """Reset the global event bus (for testing only).

    Clears the configured event bus and resets the sequence counter.
    """
    global _event_bus_instance, _sequence_counter
    _event_bus_instance = None
    _sequence_counter = 0

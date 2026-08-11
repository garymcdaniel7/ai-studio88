"""Event delivery adapters.

Provides concrete implementations of the EventBus protocol:
    - InMemoryEventBus: For testing (no external dependencies).
    - SupabaseRealtimeEventBus: Primary adapter using Supabase Realtime channels.

All adapters enforce tenant isolation — subscriptions only receive events
for the authenticated org_id.

Requirements: R63.1, R63.2
"""

from app.services.event_adapters.in_memory import InMemoryEventBus

__all__ = ["InMemoryEventBus"]

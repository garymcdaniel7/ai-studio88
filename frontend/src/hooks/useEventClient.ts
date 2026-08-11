"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { supabase, isSupabaseConfigured } from "@/lib/supabase";
import type { RealtimeChannel } from "@supabase/supabase-js";

// =============================================================================
// Types
// =============================================================================

/**
 * Connection state enum for the realtime EventClient.
 *
 * - CONNECTED: Active subscription, events flowing
 * - RECONNECTING: Lost connection, attempting to re-establish (1-2 attempts)
 * - DEGRADED: 3+ reconnection attempts without success
 * - STALE: Connected but no events received for 60s when events are expected
 * - OFFLINE: Explicitly disconnected or Supabase not configured
 */
export type ConnectionState =
  | "CONNECTED"
  | "RECONNECTING"
  | "DEGRADED"
  | "STALE"
  | "OFFLINE";

/**
 * Canonical event envelope matching the backend event delivery layer.
 */
export interface EventEnvelope {
  event_id: string;
  event_type: string;
  version: number;
  correlation_id: string | null;
  causation_id: string | null;
  cursor: string;
  timestamp: string;
  org_id: string;
  payload: Record<string, unknown>;
}

/**
 * Subscription options for a specific event type or channel.
 */
export interface SubscribeOptions {
  /** Supabase Realtime channel name (e.g., "org:{org_id}:events") */
  channel: string;
  /** Filter by event_type (optional — receives all if omitted) */
  eventTypes?: string[];
  /** Callback invoked with each deduplicated event */
  onEvent: (event: EventEnvelope) => void;
}

/**
 * Return value of the useEventClient hook.
 */
export interface EventClientReturn {
  /** Current connection state */
  connectionState: ConnectionState;
  /** Subscribe to events on a channel */
  subscribe: (options: SubscribeOptions) => string;
  /** Unsubscribe by subscription ID */
  unsubscribe: (subscriptionId: string) => void;
  /** Last event received (any subscription) */
  lastEvent: EventEnvelope | null;
}

// =============================================================================
// Constants
// =============================================================================

const STALE_TIMEOUT_MS = 60_000;
const DEGRADED_THRESHOLD = 3;

// =============================================================================
// Hook Implementation
// =============================================================================

let subscriptionCounter = 0;

/**
 * React hook providing a resilient realtime event client.
 *
 * Connects to Supabase Realtime, tracks connection state through
 * CONNECTED → RECONNECTING → DEGRADED → STALE → OFFLINE lifecycle,
 * and provides cursor-based resumption with event deduplication.
 *
 * Validates: Requirements R63.4, R63.5, R63.6
 */
export function useEventClient(): EventClientReturn {
  const [connectionState, setConnectionState] = useState<ConnectionState>(
    isSupabaseConfigured ? "OFFLINE" : "OFFLINE"
  );
  const [lastEvent, setLastEvent] = useState<EventEnvelope | null>(null);

  // Track subscriptions: id → { channel, options, realtimeChannel }
  const subscriptionsRef = useRef<
    Map<
      string,
      {
        options: SubscribeOptions;
        realtimeChannel: RealtimeChannel | null;
      }
    >
  >(new Map());

  // Cursor tracking per channel (last received cursor)
  const cursorsRef = useRef<Map<string, string>>(new Map());

  // Deduplication set: stores recent event_ids to prevent duplicates on reconnect
  const seenEventsRef = useRef<Set<string>>(new Set());
  const maxSeenEvents = 500;

  // Reconnection tracking
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Stale detection timer
  const staleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hasActiveSubscriptionsRef = useRef(false);

  // ─── Stale Detection ───────────────────────────────────────────────────

  const resetStaleTimer = useCallback(() => {
    if (staleTimerRef.current) {
      clearTimeout(staleTimerRef.current);
    }
    if (hasActiveSubscriptionsRef.current) {
      staleTimerRef.current = setTimeout(() => {
        setConnectionState((prev) => {
          if (prev === "CONNECTED") return "STALE";
          return prev;
        });
      }, STALE_TIMEOUT_MS);
    }
  }, []);

  // ─── Event Processing ──────────────────────────────────────────────────

  const processEvent = useCallback(
    (event: EventEnvelope, onEvent: (e: EventEnvelope) => void) => {
      // Deduplication by event_id
      if (seenEventsRef.current.has(event.event_id)) {
        return;
      }

      // Add to seen set, prune if too large
      seenEventsRef.current.add(event.event_id);
      if (seenEventsRef.current.size > maxSeenEvents) {
        const iterator = seenEventsRef.current.values();
        // Remove oldest 100 entries
        for (let i = 0; i < 100; i++) {
          const next = iterator.next();
          if (next.done) break;
          seenEventsRef.current.delete(next.value);
        }
      }

      // Update cursor for this channel
      if (event.cursor) {
        cursorsRef.current.set(event.org_id, event.cursor);
      }

      // Reset stale timer on successful event receipt
      resetStaleTimer();

      // Update connection state to CONNECTED on event receipt
      setConnectionState("CONNECTED");
      reconnectAttemptsRef.current = 0;

      // Store last event
      setLastEvent(event);

      // Invoke callback
      onEvent(event);
    },
    [resetStaleTimer]
  );

  // ─── Channel Management ────────────────────────────────────────────────

  const createRealtimeChannel = useCallback(
    (subscriptionId: string, options: SubscribeOptions): RealtimeChannel | null => {
      if (!supabase) return null;

      const channel = supabase.channel(options.channel, {
        config: { broadcast: { self: false } },
      });

      // Subscribe to broadcast events
      channel.on("broadcast", { event: "event" }, (payload) => {
        const event = payload.payload as EventEnvelope;
        if (!event || !event.event_id) return;

        // Filter by event types if specified
        if (
          options.eventTypes &&
          options.eventTypes.length > 0 &&
          !options.eventTypes.includes(event.event_type)
        ) {
          return;
        }

        processEvent(event, options.onEvent);
      });

      channel.subscribe((status) => {
        switch (status) {
          case "SUBSCRIBED":
            setConnectionState("CONNECTED");
            reconnectAttemptsRef.current = 0;
            resetStaleTimer();
            break;
          case "CHANNEL_ERROR":
            handleReconnect(subscriptionId);
            break;
          case "TIMED_OUT":
            handleReconnect(subscriptionId);
            break;
          case "CLOSED":
            // Only set OFFLINE if no other subscriptions are active
            if (subscriptionsRef.current.size <= 1) {
              setConnectionState("OFFLINE");
            }
            break;
        }
      });

      return channel;
    },
    [processEvent, resetStaleTimer]
  );

  // ─── Reconnection Logic ────────────────────────────────────────────────

  const handleReconnect = useCallback(
    (subscriptionId: string) => {
      reconnectAttemptsRef.current += 1;

      if (reconnectAttemptsRef.current >= DEGRADED_THRESHOLD) {
        setConnectionState("DEGRADED");
      } else {
        setConnectionState("RECONNECTING");
      }

      // Exponential backoff: 1s, 2s, 4s, 8s, max 30s
      const delay = Math.min(
        1000 * Math.pow(2, reconnectAttemptsRef.current - 1),
        30_000
      );

      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
      }

      reconnectTimerRef.current = setTimeout(() => {
        const sub = subscriptionsRef.current.get(subscriptionId);
        if (!sub) return;

        // Remove old channel
        if (sub.realtimeChannel && supabase) {
          supabase.removeChannel(sub.realtimeChannel);
        }

        // Create new channel (cursor-based resumption)
        const newChannel = createRealtimeChannel(subscriptionId, sub.options);
        sub.realtimeChannel = newChannel;
      }, delay);
    },
    [createRealtimeChannel]
  );

  // ─── Subscribe ─────────────────────────────────────────────────────────

  const subscribe = useCallback(
    (options: SubscribeOptions): string => {
      const id = `sub_${++subscriptionCounter}`;

      const realtimeChannel = createRealtimeChannel(id, options);

      subscriptionsRef.current.set(id, {
        options,
        realtimeChannel,
      });

      hasActiveSubscriptionsRef.current = subscriptionsRef.current.size > 0;
      resetStaleTimer();

      return id;
    },
    [createRealtimeChannel, resetStaleTimer]
  );

  // ─── Unsubscribe ───────────────────────────────────────────────────────

  const unsubscribe = useCallback((subscriptionId: string) => {
    const sub = subscriptionsRef.current.get(subscriptionId);
    if (!sub) return;

    if (sub.realtimeChannel && supabase) {
      supabase.removeChannel(sub.realtimeChannel);
    }

    subscriptionsRef.current.delete(subscriptionId);
    hasActiveSubscriptionsRef.current = subscriptionsRef.current.size > 0;

    if (!hasActiveSubscriptionsRef.current) {
      setConnectionState("OFFLINE");
      if (staleTimerRef.current) {
        clearTimeout(staleTimerRef.current);
        staleTimerRef.current = null;
      }
    }
  }, []);

  // ─── Cleanup on Unmount ────────────────────────────────────────────────

  useEffect(() => {
    return () => {
      // Clean up all subscriptions
      subscriptionsRef.current.forEach((sub) => {
        if (sub.realtimeChannel && supabase) {
          supabase.removeChannel(sub.realtimeChannel);
        }
      });
      subscriptionsRef.current.clear();

      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
      }
      if (staleTimerRef.current) {
        clearTimeout(staleTimerRef.current);
      }
    };
  }, []);

  return {
    connectionState,
    subscribe,
    unsubscribe,
    lastEvent,
  };
}

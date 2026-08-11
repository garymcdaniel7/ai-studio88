"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useEventClient, type EventEnvelope } from "./useEventClient";

// =============================================================================
// Types
// =============================================================================

/**
 * In-app notification matching the backend notifications table schema.
 */
export interface AppNotification {
  id: string;
  org_id: string;
  user_id: string;
  category: string;
  title: string;
  body: string;
  action_url: string | null;
  is_read: boolean;
  is_mandatory: boolean;
  metadata: Record<string, unknown>;
  created_at: string;
}

/**
 * Return value of the useNotifications hook.
 */
export interface NotificationsReturn {
  /** List of recent notifications (newest first) */
  notifications: AppNotification[];
  /** Count of unread notifications */
  unreadCount: number;
  /** Mark a single notification as read */
  markAsRead: (notificationId: string) => void;
  /** Mark all notifications as read */
  markAllAsRead: () => void;
  /** Whether the hook is connected and receiving events */
  isConnected: boolean;
}

// =============================================================================
// Constants
// =============================================================================

const MAX_NOTIFICATIONS = 50;
const NOTIFICATION_CHANNEL_PREFIX = "org:";
const NOTIFICATION_EVENT_TYPE = "notification_created";

// =============================================================================
// Hook Implementation
// =============================================================================

/**
 * Hook that listens for realtime notification events via useEventClient
 * and maintains an in-memory list of recent notifications with unread count.
 *
 * Uses the EventClient's deduplication and cursor-based resumption to ensure
 * notifications are not duplicated on reconnect.
 *
 * @param orgId - The organization ID to subscribe to notifications for
 * @param userId - The user ID to filter notifications (optional client-side filter)
 */
export function useNotifications(
  orgId: string | null,
  userId: string | null
): NotificationsReturn {
  const { connectionState, subscribe, unsubscribe } = useEventClient();
  const [notifications, setNotifications] = useState<AppNotification[]>([]);
  const subscriptionIdRef = useRef<string | null>(null);

  // ─── Event Handler ─────────────────────────────────────────────────────

  const handleNotificationEvent = useCallback(
    (event: EventEnvelope) => {
      if (event.event_type !== NOTIFICATION_EVENT_TYPE) return;

      const payload = event.payload as Partial<AppNotification>;
      if (!payload.id || !payload.title) return;

      // Client-side user filter: only show notifications for this user
      if (userId && payload.user_id && payload.user_id !== userId) return;

      const notification: AppNotification = {
        id: payload.id,
        org_id: payload.org_id ?? event.org_id,
        user_id: payload.user_id ?? "",
        category: payload.category ?? "info",
        title: payload.title,
        body: payload.body ?? "",
        action_url: payload.action_url ?? null,
        is_read: payload.is_read ?? false,
        is_mandatory: payload.is_mandatory ?? false,
        metadata: payload.metadata ?? {},
        created_at: payload.created_at ?? event.timestamp,
      };

      setNotifications((prev) => {
        // Prevent duplicates by id
        if (prev.some((n) => n.id === notification.id)) return prev;
        // Prepend (newest first), cap at max
        const next = [notification, ...prev];
        return next.slice(0, MAX_NOTIFICATIONS);
      });
    },
    [userId]
  );

  // ─── Subscription Management ───────────────────────────────────────────

  useEffect(() => {
    if (!orgId) return;

    const channel = `${NOTIFICATION_CHANNEL_PREFIX}${orgId}:events`;
    const subId = subscribe({
      channel,
      eventTypes: [NOTIFICATION_EVENT_TYPE],
      onEvent: handleNotificationEvent,
    });
    subscriptionIdRef.current = subId;

    return () => {
      if (subscriptionIdRef.current) {
        unsubscribe(subscriptionIdRef.current);
        subscriptionIdRef.current = null;
      }
    };
  }, [orgId, subscribe, unsubscribe, handleNotificationEvent]);

  // ─── Actions ───────────────────────────────────────────────────────────

  const markAsRead = useCallback((notificationId: string) => {
    setNotifications((prev) =>
      prev.map((n) => (n.id === notificationId ? { ...n, is_read: true } : n))
    );
  }, []);

  const markAllAsRead = useCallback(() => {
    setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
  }, []);

  // ─── Derived State ─────────────────────────────────────────────────────

  const unreadCount = notifications.filter((n) => !n.is_read).length;
  const isConnected = connectionState === "CONNECTED";

  return {
    notifications,
    unreadCount,
    markAsRead,
    markAllAsRead,
    isConnected,
  };
}

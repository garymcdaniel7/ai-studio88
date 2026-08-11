"use client";

import { useSyncExternalStore, useCallback } from "react";
import {
  getNotificationStore,
  type NotificationLevel,
  type NotificationOptions,
  type NotificationStoreState,
} from "@/lib/notification-store";

// =============================================================================
// Hook: useNotification
// =============================================================================

/**
 * Hook providing access to the unified notification system.
 *
 * Usage:
 * ```tsx
 * const { success, error, warning, info, notify, dismiss, dismissAll } = useNotification();
 *
 * // Simple
 * success("Talent created!");
 * error("Failed to save");
 *
 * // With deduplication
 * error("Connection lost", { dedupKey: "connection-error" });
 *
 * // With recovery action
 * error("Upload failed", {
 *   dedupKey: "upload-fail",
 *   actions: [{ label: "Retry", onClick: () => retryUpload() }],
 * });
 * ```
 */
export function useNotification() {
  const store = getNotificationStore();

  const state = useSyncExternalStore<NotificationStoreState>(
    store.subscribe,
    store.getSnapshot,
    store.getSnapshot // SSR fallback returns same empty state
  );

  const notify = useCallback(
    (level: NotificationLevel, message: string, options?: NotificationOptions) =>
      store.notify(level, message, options),
    [store]
  );

  const success = useCallback(
    (message: string, options?: NotificationOptions) =>
      store.success(message, options),
    [store]
  );

  const info = useCallback(
    (message: string, options?: NotificationOptions) =>
      store.info(message, options),
    [store]
  );

  const warning = useCallback(
    (message: string, options?: NotificationOptions) =>
      store.warning(message, options),
    [store]
  );

  const error = useCallback(
    (message: string, options?: NotificationOptions) =>
      store.error(message, options),
    [store]
  );

  const dismiss = useCallback(
    (id: string) => store.dismiss(id),
    [store]
  );

  const dismissAll = useCallback(
    () => store.dismissAll(),
    [store]
  );

  const pause = useCallback(
    (id: string) => store.pause(id),
    [store]
  );

  const resume = useCallback(
    (id: string) => store.resume(id),
    [store]
  );

  return {
    /** Current notifications (reactive) */
    notifications: state.notifications,
    /** Show a notification with explicit level */
    notify,
    /** Success notification — auto-dismisses after 4s */
    success,
    /** Info notification — auto-dismisses after 5s */
    info,
    /** Warning notification — auto-dismisses after 7s */
    warning,
    /** Error notification — persists until dismissed */
    error,
    /** Dismiss a specific notification by id */
    dismiss,
    /** Dismiss all notifications */
    dismissAll,
    /** Pause auto-dismiss timer (called on hover/focus) */
    pause,
    /** Resume auto-dismiss timer (called on mouse leave/blur) */
    resume,
  };
}

// =============================================================================
// Legacy compatibility: useToast (drop-in replacement)
// =============================================================================

/**
 * Drop-in replacement for the legacy useToast hook.
 * Maps the old `show(message, type)` API to the new notification store.
 *
 * @deprecated Use `useNotification()` directly for new code.
 */
export function useToast() {
  const { notify } = useNotification();

  const show = useCallback(
    (message: string, type: "success" | "error" | "info" = "info") => {
      notify(type, message);
    },
    [notify]
  );

  return { show };
}

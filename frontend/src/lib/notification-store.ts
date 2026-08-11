/**
 * Unified Notification Store — Story 140
 *
 * Single authoritative store for all toast/notification state.
 * Typed operation outcomes, deduplication, lifecycle management,
 * pause-on-hover, recovery actions, and flood prevention.
 *
 * Features:
 * - Typed notification levels: success, info, warning, error
 * - Deduplication by key (same key = update existing, not stack new)
 * - Error notifications persist until dismissed (no auto-dismiss)
 * - Pause timer on hover/focus (resume on leave)
 * - Recovery actions (retry, undo, navigate)
 * - Max visible limit to prevent flood
 * - Reduced-motion support (no entrance/exit animation)
 * - Timer cleanup on unmount
 */

// =============================================================================
// Types
// =============================================================================

export type NotificationLevel = "success" | "info" | "warning" | "error";

export interface NotificationAction {
  /** Button label */
  label: string;
  /** Callback — must be idempotent */
  onClick: () => void;
  /** Optional: variant for styling */
  variant?: "default" | "destructive";
}

export interface Notification {
  id: string;
  /** Deduplication key — notifications with same key replace each other */
  dedupKey?: string;
  level: NotificationLevel;
  title?: string;
  message: string;
  /** Unix timestamp ms when created */
  createdAt: number;
  /** Whether auto-dismiss timer is paused (hover/focus) */
  paused: boolean;
  /** Duration in ms before auto-dismiss. null = persist until dismissed */
  duration: number | null;
  /** Remaining duration when paused */
  remainingMs: number | null;
  /** Optional actions the user can take */
  actions?: NotificationAction[];
  /** Source operation for correlation */
  source?: string;
}

export interface NotificationStoreState {
  notifications: Notification[];
  /** Max visible at once (older ones are queued) */
  maxVisible: number;
}

export interface NotificationOptions {
  /** Deduplication key — same key replaces existing */
  dedupKey?: string;
  title?: string;
  /** Duration ms. Defaults: success=4000, info=5000, warning=7000, error=null (persistent) */
  duration?: number | null;
  /** Recovery or contextual actions */
  actions?: NotificationAction[];
  /** Source identifier for debugging/correlation */
  source?: string;
}

export interface NotificationStoreActions {
  /** Show a notification */
  notify: (level: NotificationLevel, message: string, options?: NotificationOptions) => string;
  /** Convenience: success notification */
  success: (message: string, options?: NotificationOptions) => string;
  /** Convenience: info notification */
  info: (message: string, options?: NotificationOptions) => string;
  /** Convenience: warning notification */
  warning: (message: string, options?: NotificationOptions) => string;
  /** Convenience: error notification (persistent by default) */
  error: (message: string, options?: NotificationOptions) => string;
  /** Dismiss a notification by id */
  dismiss: (id: string) => void;
  /** Dismiss all notifications */
  dismissAll: () => void;
  /** Pause auto-dismiss timer for a notification (hover/focus) */
  pause: (id: string) => void;
  /** Resume auto-dismiss timer for a notification */
  resume: (id: string) => void;
  /** Subscribe to state changes */
  subscribe: (listener: () => void) => () => void;
  /** Get current snapshot */
  getSnapshot: () => NotificationStoreState;
  /** Destroy — clear all timers */
  destroy: () => void;
}

export type NotificationStore = NotificationStoreActions;

// =============================================================================
// Constants
// =============================================================================

const DEFAULT_DURATIONS: Record<NotificationLevel, number | null> = {
  success: 4000,
  info: 5000,
  warning: 7000,
  error: null, // errors persist until dismissed
};

const MAX_VISIBLE_DEFAULT = 5;

// =============================================================================
// Store Implementation
// =============================================================================

let idCounter = 0;
function generateId(): string {
  return `notif_${Date.now()}_${++idCounter}`;
}

export function createNotificationStore(): NotificationStore {
  let state: NotificationStoreState = {
    notifications: [],
    maxVisible: MAX_VISIBLE_DEFAULT,
  };

  const listeners = new Set<() => void>();
  const timers = new Map<string, ReturnType<typeof setTimeout>>();
  const pausedAt = new Map<string, number>(); // id → timestamp when paused

  function notify_listeners(): void {
    listeners.forEach((fn) => fn());
  }

  function setState(next: NotificationStoreState): void {
    state = next;
    notify_listeners();
  }

  // ─── Timer management ────────────────────────────────────────────────────

  function startTimer(id: string, durationMs: number): void {
    clearTimer(id);
    const timer = setTimeout(() => {
      timers.delete(id);
      dismiss(id);
    }, durationMs);
    timers.set(id, timer);
  }

  function clearTimer(id: string): void {
    const existing = timers.get(id);
    if (existing) {
      clearTimeout(existing);
      timers.delete(id);
    }
  }

  // ─── Core actions ────────────────────────────────────────────────────────

  function notify(
    level: NotificationLevel,
    message: string,
    options?: NotificationOptions
  ): string {
    const duration = options?.duration !== undefined
      ? options.duration
      : DEFAULT_DURATIONS[level];

    const dedupKey = options?.dedupKey;

    // Deduplication: if a notification with the same dedupKey exists, replace it
    if (dedupKey) {
      const existingIndex = state.notifications.findIndex(
        (n) => n.dedupKey === dedupKey
      );
      if (existingIndex !== -1) {
        const existing = state.notifications[existingIndex];
        clearTimer(existing.id);

        const updated: Notification = {
          ...existing,
          level,
          message,
          title: options?.title ?? existing.title,
          createdAt: Date.now(),
          paused: false,
          duration,
          remainingMs: duration,
          actions: options?.actions ?? existing.actions,
          source: options?.source ?? existing.source,
        };

        const next = [...state.notifications];
        next[existingIndex] = updated;
        setState({ ...state, notifications: next });

        if (duration !== null) {
          startTimer(existing.id, duration);
        }

        return existing.id;
      }
    }

    // Flood control: drop oldest non-error if at max
    let notifications = [...state.notifications];
    if (notifications.length >= state.maxVisible) {
      const oldestDismissable = notifications.findIndex(
        (n) => n.level !== "error" && !n.paused
      );
      if (oldestDismissable !== -1) {
        const removed = notifications[oldestDismissable];
        clearTimer(removed.id);
        notifications.splice(oldestDismissable, 1);
      }
    }

    const id = generateId();
    const notification: Notification = {
      id,
      dedupKey,
      level,
      message,
      title: options?.title,
      createdAt: Date.now(),
      paused: false,
      duration,
      remainingMs: duration,
      actions: options?.actions,
      source: options?.source,
    };

    notifications = [...notifications, notification];
    setState({ ...state, notifications });

    if (duration !== null) {
      startTimer(id, duration);
    }

    return id;
  }

  function dismiss(id: string): void {
    clearTimer(id);
    pausedAt.delete(id);
    const next = state.notifications.filter((n) => n.id !== id);
    if (next.length !== state.notifications.length) {
      setState({ ...state, notifications: next });
    }
  }

  function dismissAll(): void {
    timers.forEach((_, id) => clearTimer(id));
    pausedAt.clear();
    setState({ ...state, notifications: [] });
  }

  function pause(id: string): void {
    const notif = state.notifications.find((n) => n.id === id);
    if (!notif || notif.paused || notif.duration === null) return;

    clearTimer(id);
    pausedAt.set(id, Date.now());

    // Calculate remaining time
    const elapsed = Date.now() - notif.createdAt;
    const remaining = Math.max((notif.duration ?? 0) - elapsed, 500);

    const next = state.notifications.map((n) =>
      n.id === id ? { ...n, paused: true, remainingMs: remaining } : n
    );
    setState({ ...state, notifications: next });
  }

  function resume(id: string): void {
    const notif = state.notifications.find((n) => n.id === id);
    if (!notif || !notif.paused) return;

    pausedAt.delete(id);

    const remaining = notif.remainingMs ?? notif.duration ?? 4000;
    const next = state.notifications.map((n) =>
      n.id === id ? { ...n, paused: false } : n
    );
    setState({ ...state, notifications: next });

    startTimer(id, remaining);
  }

  // ─── Convenience helpers ─────────────────────────────────────────────────

  function success(message: string, options?: NotificationOptions): string {
    return notify("success", message, options);
  }

  function info(message: string, options?: NotificationOptions): string {
    return notify("info", message, options);
  }

  function warning(message: string, options?: NotificationOptions): string {
    return notify("warning", message, options);
  }

  function error(message: string, options?: NotificationOptions): string {
    return notify("error", message, options);
  }

  // ─── Subscription ────────────────────────────────────────────────────────

  function subscribe(listener: () => void): () => void {
    listeners.add(listener);
    return () => { listeners.delete(listener); };
  }

  function getSnapshot(): NotificationStoreState {
    return state;
  }

  function destroy(): void {
    timers.forEach((timer) => clearTimeout(timer));
    timers.clear();
    pausedAt.clear();
    listeners.clear();
    setState({ ...state, notifications: [] });
  }

  return {
    notify,
    success,
    info,
    warning,
    error,
    dismiss,
    dismissAll,
    pause,
    resume,
    subscribe,
    getSnapshot,
    destroy,
  };
}

// =============================================================================
// Singleton instance for the application
// =============================================================================

let _store: NotificationStore | null = null;

export function getNotificationStore(): NotificationStore {
  if (!_store) {
    _store = createNotificationStore();
  }
  return _store;
}

/**
 * Reset the singleton (for testing only).
 */
export function resetNotificationStore(): void {
  if (_store) {
    _store.destroy();
    _store = null;
  }
}

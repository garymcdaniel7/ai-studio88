/**
 * Notification Store tests — Story 140
 *
 * Tests prove:
 * - Timing: auto-dismiss at correct intervals per level
 * - Error persistence: errors don't auto-dismiss
 * - Deduplication: same dedupKey replaces, not stacks
 * - Pause/resume: timers pause on hover, resume with remaining time
 * - Flood prevention: max visible enforced
 * - Dismiss: individual and bulk dismiss
 * - Actions: recovery actions stored and accessible
 * - Cleanup: destroy clears all timers and state
 * - Screen-reader semantics: correct level assignments for ARIA routing
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  createNotificationStore,
  resetNotificationStore,
  type NotificationStore,
} from "../notification-store";

// =============================================================================
// Setup
// =============================================================================

let store: NotificationStore;

beforeEach(() => {
  vi.useFakeTimers();
  store = createNotificationStore();
});

afterEach(() => {
  store.destroy();
  resetNotificationStore();
  vi.useRealTimers();
});

// =============================================================================
// Timing
// =============================================================================

describe("Auto-dismiss timing", () => {
  it("success notifications dismiss after 4000ms", () => {
    store.success("Done");
    expect(store.getSnapshot().notifications).toHaveLength(1);

    vi.advanceTimersByTime(3999);
    expect(store.getSnapshot().notifications).toHaveLength(1);

    vi.advanceTimersByTime(1);
    expect(store.getSnapshot().notifications).toHaveLength(0);
  });

  it("info notifications dismiss after 5000ms", () => {
    store.info("FYI");
    expect(store.getSnapshot().notifications).toHaveLength(1);

    vi.advanceTimersByTime(4999);
    expect(store.getSnapshot().notifications).toHaveLength(1);

    vi.advanceTimersByTime(1);
    expect(store.getSnapshot().notifications).toHaveLength(0);
  });

  it("warning notifications dismiss after 7000ms", () => {
    store.warning("Heads up");
    expect(store.getSnapshot().notifications).toHaveLength(1);

    vi.advanceTimersByTime(6999);
    expect(store.getSnapshot().notifications).toHaveLength(1);

    vi.advanceTimersByTime(1);
    expect(store.getSnapshot().notifications).toHaveLength(0);
  });

  it("custom duration overrides default", () => {
    store.success("Quick", { duration: 1000 });
    vi.advanceTimersByTime(1000);
    expect(store.getSnapshot().notifications).toHaveLength(0);
  });
});

// =============================================================================
// Error Persistence
// =============================================================================

describe("Error persistence", () => {
  it("error notifications do NOT auto-dismiss", () => {
    store.error("Something broke");
    expect(store.getSnapshot().notifications).toHaveLength(1);

    // Wait a very long time
    vi.advanceTimersByTime(60_000);
    expect(store.getSnapshot().notifications).toHaveLength(1);
    expect(store.getSnapshot().notifications[0].level).toBe("error");
  });

  it("error notifications can be manually dismissed", () => {
    const id = store.error("Fail");
    expect(store.getSnapshot().notifications).toHaveLength(1);

    store.dismiss(id);
    expect(store.getSnapshot().notifications).toHaveLength(0);
  });

  it("error with explicit duration will auto-dismiss", () => {
    store.error("Recoverable", { duration: 10_000 });
    vi.advanceTimersByTime(10_000);
    expect(store.getSnapshot().notifications).toHaveLength(0);
  });
});

// =============================================================================
// Deduplication
// =============================================================================

describe("Deduplication", () => {
  it("same dedupKey replaces existing notification (no stacking)", () => {
    store.error("Connection lost", { dedupKey: "conn" });
    store.error("Connection lost", { dedupKey: "conn" });
    store.error("Connection lost", { dedupKey: "conn" });

    expect(store.getSnapshot().notifications).toHaveLength(1);
  });

  it("dedup updates message content", () => {
    store.error("Attempt 1 failed", { dedupKey: "upload" });
    store.error("Attempt 2 failed", { dedupKey: "upload" });

    const notifs = store.getSnapshot().notifications;
    expect(notifs).toHaveLength(1);
    expect(notifs[0].message).toBe("Attempt 2 failed");
  });

  it("dedup preserves the original id", () => {
    const id1 = store.error("First", { dedupKey: "key" });
    const id2 = store.error("Second", { dedupKey: "key" });

    expect(id1).toBe(id2);
    expect(store.getSnapshot().notifications[0].id).toBe(id1);
  });

  it("different dedupKeys create separate notifications", () => {
    store.error("Error A", { dedupKey: "a" });
    store.error("Error B", { dedupKey: "b" });

    expect(store.getSnapshot().notifications).toHaveLength(2);
  });

  it("no dedupKey always creates new notification", () => {
    store.success("Done");
    store.success("Done");
    store.success("Done");

    expect(store.getSnapshot().notifications).toHaveLength(3);
  });

  it("dedup resets timer on timed notifications", () => {
    store.warning("Retrying...", { dedupKey: "retry" });

    // Advance 5 seconds (still within 7s warning default)
    vi.advanceTimersByTime(5000);
    expect(store.getSnapshot().notifications).toHaveLength(1);

    // Replace via dedup — should reset the 7s timer
    store.warning("Still retrying...", { dedupKey: "retry" });

    // Advance 5 more seconds (within the NEW 7s window)
    vi.advanceTimersByTime(5000);
    expect(store.getSnapshot().notifications).toHaveLength(1);

    // Advance past the full 7s from second call
    vi.advanceTimersByTime(2000);
    expect(store.getSnapshot().notifications).toHaveLength(0);
  });
});

// =============================================================================
// Pause / Resume
// =============================================================================

describe("Pause and resume", () => {
  it("pause stops the auto-dismiss timer", () => {
    const id = store.success("Hovering");

    // Advance 2s, then pause
    vi.advanceTimersByTime(2000);
    store.pause(id);

    // Advance past original dismiss time
    vi.advanceTimersByTime(10_000);

    // Should still be visible (paused)
    expect(store.getSnapshot().notifications).toHaveLength(1);
    expect(store.getSnapshot().notifications[0].paused).toBe(true);
  });

  it("resume dismisses after remaining time", () => {
    const id = store.success("Hover me"); // 4000ms

    // Advance 2s, pause, then resume
    vi.advanceTimersByTime(2000);
    store.pause(id);
    store.resume(id);

    // Should dismiss ~2s later (remaining)
    vi.advanceTimersByTime(1999);
    expect(store.getSnapshot().notifications).toHaveLength(1);

    vi.advanceTimersByTime(1);
    expect(store.getSnapshot().notifications).toHaveLength(0);
  });

  it("pause on persistent (error) notifications is a no-op", () => {
    const id = store.error("Persistent");
    store.pause(id);

    // Error has null duration — pause shouldn't change state
    expect(store.getSnapshot().notifications[0].paused).toBe(false);
  });
});

// =============================================================================
// Flood Prevention
// =============================================================================

describe("Flood prevention", () => {
  it("caps visible notifications at maxVisible (5)", () => {
    for (let i = 0; i < 10; i++) {
      store.info(`Message ${i}`);
    }

    expect(store.getSnapshot().notifications.length).toBeLessThanOrEqual(5);
  });

  it("errors are preserved during flood (non-error evicted first)", () => {
    store.error("Critical error", { dedupKey: "crit" });
    // Fill up with info messages
    for (let i = 0; i < 10; i++) {
      store.info(`Info ${i}`);
    }

    const notifs = store.getSnapshot().notifications;
    const hasError = notifs.some((n) => n.level === "error");
    expect(hasError).toBe(true);
  });
});

// =============================================================================
// Dismiss
// =============================================================================

describe("Dismiss", () => {
  it("dismiss removes specific notification by id", () => {
    const id1 = store.info("First");
    const id2 = store.info("Second");

    store.dismiss(id1);

    const notifs = store.getSnapshot().notifications;
    expect(notifs).toHaveLength(1);
    expect(notifs[0].id).toBe(id2);
  });

  it("dismissAll clears everything", () => {
    store.info("A");
    store.error("B");
    store.warning("C");

    store.dismissAll();
    expect(store.getSnapshot().notifications).toHaveLength(0);
  });

  it("dismiss cleans up timer (no late callback)", () => {
    const id = store.success("Quick");
    store.dismiss(id);

    // Advance past original dismiss time — should not throw
    vi.advanceTimersByTime(10_000);
    expect(store.getSnapshot().notifications).toHaveLength(0);
  });

  it("dismiss non-existent id is a no-op", () => {
    store.info("Exists");
    store.dismiss("non-existent-id");
    expect(store.getSnapshot().notifications).toHaveLength(1);
  });
});

// =============================================================================
// Recovery Actions
// =============================================================================

describe("Recovery actions", () => {
  it("stores actions on notification", () => {
    const retry = vi.fn();
    store.error("Upload failed", {
      actions: [{ label: "Retry", onClick: retry }],
    });

    const notif = store.getSnapshot().notifications[0];
    expect(notif.actions).toHaveLength(1);
    expect(notif.actions![0].label).toBe("Retry");
  });

  it("action onClick is callable and idempotent", () => {
    const retry = vi.fn();
    store.error("Failed", {
      actions: [{ label: "Retry", onClick: retry }],
    });

    const action = store.getSnapshot().notifications[0].actions![0];
    action.onClick();
    action.onClick();
    expect(retry).toHaveBeenCalledTimes(2);
  });

  it("actions with variant are stored correctly", () => {
    store.warning("Are you sure?", {
      actions: [
        { label: "Delete", onClick: () => {}, variant: "destructive" },
        { label: "Cancel", onClick: () => {} },
      ],
    });

    const actions = store.getSnapshot().notifications[0].actions!;
    expect(actions[0].variant).toBe("destructive");
    expect(actions[1].variant).toBeUndefined();
  });
});

// =============================================================================
// Subscription
// =============================================================================

describe("Subscription", () => {
  it("listeners are called on state changes", () => {
    const listener = vi.fn();
    store.subscribe(listener);

    store.info("Hello");
    expect(listener).toHaveBeenCalled();
  });

  it("unsubscribe stops notifications", () => {
    const listener = vi.fn();
    const unsub = store.subscribe(listener);

    store.info("First");
    expect(listener).toHaveBeenCalledTimes(1);

    unsub();
    store.info("Second");
    expect(listener).toHaveBeenCalledTimes(1); // not called again
  });
});

// =============================================================================
// Cleanup / Destroy
// =============================================================================

describe("Destroy", () => {
  it("destroy clears all timers and notifications", () => {
    store.success("A");
    store.info("B");
    store.warning("C");

    store.destroy();

    expect(store.getSnapshot().notifications).toHaveLength(0);

    // Advancing timers should not cause errors
    vi.advanceTimersByTime(30_000);
  });
});

// =============================================================================
// Screen-reader announcement routing
// =============================================================================

describe("Screen-reader semantics (level assignment)", () => {
  it("error level is assigned for error notifications", () => {
    store.error("Critical failure");
    expect(store.getSnapshot().notifications[0].level).toBe("error");
  });

  it("warning level is assigned for warning notifications", () => {
    store.warning("Disk almost full");
    expect(store.getSnapshot().notifications[0].level).toBe("warning");
  });

  it("success level is assigned for success notifications", () => {
    store.success("Saved");
    expect(store.getSnapshot().notifications[0].level).toBe("success");
  });

  it("info level is assigned for info notifications", () => {
    store.info("Tip of the day");
    expect(store.getSnapshot().notifications[0].level).toBe("info");
  });

  it("notify() with explicit level works", () => {
    store.notify("warning", "Explicit");
    expect(store.getSnapshot().notifications[0].level).toBe("warning");
  });
});

// =============================================================================
// Source correlation
// =============================================================================

describe("Source correlation", () => {
  it("stores source identifier for debugging", () => {
    store.error("Upload failed", { source: "storage.upload" });
    expect(store.getSnapshot().notifications[0].source).toBe("storage.upload");
  });
});

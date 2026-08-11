"use client";

/**
 * Unified Toast/Notification Provider — Story 140
 *
 * Replaces the legacy context-based toast system with one backed by the
 * notification store. Renders the accessible ToastContainer and re-exports
 * the useToast hook for backward compatibility.
 *
 * New code should use `useNotification()` from `@/hooks/use-notification`.
 */

import { useNotification, useToast } from "@/hooks/use-notification";
import { ToastContainer } from "@/components/notification-toast";

// Re-export legacy hook so existing `import { useToast } from "@/components/toast"` keeps working
export { useToast };

/**
 * ToastProvider renders the global notification container.
 * Mount once at the app root (already done in providers.tsx).
 */
export function ToastProvider({ children }: { children: React.ReactNode }) {
  const { notifications, dismiss, pause, resume } = useNotification();

  return (
    <>
      {children}
      <ToastContainer
        notifications={notifications}
        onDismiss={dismiss}
        onPause={pause}
        onResume={resume}
      />
    </>
  );
}

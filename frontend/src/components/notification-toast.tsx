"use client";

import { useCallback, useEffect, useRef } from "react";
import { X, CheckCircle2, AlertCircle, AlertTriangle, Info } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Notification, NotificationLevel, NotificationAction } from "@/lib/notification-store";

// =============================================================================
// Toast Item Component
// =============================================================================

interface ToastItemProps {
  notification: Notification;
  onDismiss: (id: string) => void;
  onPause: (id: string) => void;
  onResume: (id: string) => void;
}

const LEVEL_STYLES: Record<NotificationLevel, string> = {
  success: "border-status-success/30 bg-status-success-muted text-status-success",
  info: "border-status-info/30 bg-status-info-muted text-status-info",
  warning: "border-status-warning/30 bg-status-warning-muted text-status-warning",
  error: "border-status-error/30 bg-status-error-muted text-status-error",
};

const LEVEL_ICONS: Record<NotificationLevel, typeof CheckCircle2> = {
  success: CheckCircle2,
  info: Info,
  warning: AlertTriangle,
  error: AlertCircle,
};

/**
 * Accessible label for the notification level, used by screen readers.
 */
const LEVEL_LABELS: Record<NotificationLevel, string> = {
  success: "Success",
  info: "Information",
  warning: "Warning",
  error: "Error",
};

export function ToastItem({ notification, onDismiss, onPause, onResume }: ToastItemProps) {
  const { id, level, title, message, actions } = notification;
  const Icon = LEVEL_ICONS[level];
  const itemRef = useRef<HTMLDivElement>(null);

  const handleMouseEnter = useCallback(() => onPause(id), [id, onPause]);
  const handleMouseLeave = useCallback(() => onResume(id), [id, onResume]);
  const handleFocus = useCallback(() => onPause(id), [id, onPause]);
  const handleBlur = useCallback(
    (e: React.FocusEvent) => {
      // Only resume if focus leaves the toast entirely
      if (itemRef.current && !itemRef.current.contains(e.relatedTarget as Node)) {
        onResume(id);
      }
    },
    [id, onResume]
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Escape") {
        onDismiss(id);
      }
    },
    [id, onDismiss]
  );

  return (
    <div
      ref={itemRef}
      data-testid={`notification-toast-${id}`}
      data-level={level}
      className={cn(
        "flex flex-col gap-2 rounded-lg border px-4 py-3 shadow-lg backdrop-blur-sm",
        "motion-safe:animate-in motion-safe:fade-in-0 motion-safe:slide-in-from-right-4",
        "motion-reduce:opacity-100",
        LEVEL_STYLES[level]
      )}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onFocus={handleFocus}
      onBlur={handleBlur}
      onKeyDown={handleKeyDown}
      // tabIndex for keyboard focus and Escape handling
      tabIndex={-1}
    >
      {/* Main content row */}
      <div className="flex items-start gap-3">
        <Icon className="h-4 w-4 shrink-0 mt-0.5" aria-hidden="true" />
        <div className="flex-1 min-w-0">
          {/* Screen reader level prefix (visually hidden) */}
          <span className="sr-only">{LEVEL_LABELS[level]}:</span>
          {title && (
            <p className="text-sm font-medium leading-tight">{title}</p>
          )}
          <p className={cn("text-sm", title && "text-white/70 mt-0.5")}>
            {message}
          </p>
        </div>
        <button
          onClick={() => onDismiss(id)}
          className="p-1 rounded opacity-60 hover:opacity-100 focus-visible:opacity-100 focus-visible:ring-2 focus-visible:ring-white/30 focus-visible:outline-none transition-opacity shrink-0"
          aria-label={`Dismiss ${LEVEL_LABELS[level].toLowerCase()} notification: ${title || message}`}
          type="button"
        >
          <X className="h-3.5 w-3.5" aria-hidden="true" />
        </button>
      </div>

      {/* Recovery actions row */}
      {actions && actions.length > 0 && (
        <div className="flex items-center gap-2 ml-7">
          {actions.map((action, index) => (
            <ToastAction key={index} action={action} />
          ))}
        </div>
      )}
    </div>
  );
}

// =============================================================================
// Toast Action Button
// =============================================================================

interface ToastActionProps {
  action: NotificationAction;
}

function ToastAction({ action }: ToastActionProps) {
  const handleClick = useCallback(() => {
    action.onClick();
  }, [action]);

  return (
    <button
      onClick={handleClick}
      type="button"
      className={cn(
        "text-xs font-medium px-2 py-1 rounded border transition-colors",
        "focus-visible:ring-2 focus-visible:ring-white/30 focus-visible:outline-none",
        action.variant === "destructive"
          ? "border-red-400/40 text-red-300 hover:bg-red-500/20"
          : "border-white/20 text-white/80 hover:bg-white/10"
      )}
    >
      {action.label}
    </button>
  );
}

// =============================================================================
// Toast Container (renders all visible toasts with live region)
// =============================================================================

interface ToastContainerProps {
  notifications: Notification[];
  onDismiss: (id: string) => void;
  onPause: (id: string) => void;
  onResume: (id: string) => void;
}

/**
 * The toast container uses two live regions:
 * - aria-live="assertive" for errors (role="alert")
 * - aria-live="polite" for success/info/warning (role="status")
 *
 * This ensures errors interrupt screen readers immediately while
 * non-critical notifications wait for a natural pause.
 */
export function ToastContainer({
  notifications,
  onDismiss,
  onPause,
  onResume,
}: ToastContainerProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  // Move focus to the toast region when an error appears (important for a11y)
  const prevErrorCountRef = useRef(0);
  useEffect(() => {
    const errorCount = notifications.filter((n) => n.level === "error").length;
    if (errorCount > prevErrorCountRef.current && containerRef.current) {
      // Don't steal focus from active interactive element — only announce
      // The live region will handle announcement without focus theft
    }
    prevErrorCountRef.current = errorCount;
  }, [notifications]);

  const errorNotifications = notifications.filter((n) => n.level === "error");
  const otherNotifications = notifications.filter((n) => n.level !== "error");

  return (
    <div
      ref={containerRef}
      className="fixed bottom-4 right-4 z-50 flex flex-col-reverse gap-2 max-w-sm w-full pointer-events-none"
      data-testid="notification-container"
    >
      {/* Polite live region for non-error notifications */}
      <div
        aria-live="polite"
        aria-atomic="false"
        aria-relevant="additions removals"
        role="status"
        className="contents"
      >
        {otherNotifications.map((n) => (
          <div key={n.id} className="pointer-events-auto">
            <ToastItem
              notification={n}
              onDismiss={onDismiss}
              onPause={onPause}
              onResume={onResume}
            />
          </div>
        ))}
      </div>

      {/* Assertive live region for errors */}
      <div
        aria-live="assertive"
        aria-atomic="false"
        aria-relevant="additions removals"
        role="alert"
        className="contents"
      >
        {errorNotifications.map((n) => (
          <div key={n.id} className="pointer-events-auto">
            <ToastItem
              notification={n}
              onDismiss={onDismiss}
              onPause={onPause}
              onResume={onResume}
            />
          </div>
        ))}
      </div>
    </div>
  );
}

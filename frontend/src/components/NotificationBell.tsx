"use client";

import { useState, useRef, useEffect } from "react";
import { Bell, Check, CheckCheck, X } from "lucide-react";
import { useNotifications, type AppNotification } from "@/hooks/useNotifications";
import { cn } from "@/lib/utils";

// =============================================================================
// Types
// =============================================================================

interface NotificationBellProps {
  /** Organization ID for event subscription */
  orgId: string | null;
  /** User ID for notification filtering */
  userId: string | null;
  /** Additional className for the container */
  className?: string;
}

// =============================================================================
// Category styling helpers
// =============================================================================

const CATEGORY_COLORS: Record<string, string> = {
  job_completed: "text-emerald-400",
  job_failed: "text-red-400",
  approval_requested: "text-amber-400",
  approval_resolved: "text-blue-400",
  connection_expired: "text-orange-400",
  provider_unavailable: "text-red-300",
  publishing_result: "text-purple-400",
  budget_threshold: "text-yellow-400",
  safety_action: "text-red-500",
  hermes_needs_input: "text-cyan-400",
};

function getCategoryLabel(category: string): string {
  const labels: Record<string, string> = {
    job_completed: "Job Complete",
    job_failed: "Job Failed",
    approval_requested: "Approval Needed",
    approval_resolved: "Approval Resolved",
    connection_expired: "Connection Expired",
    provider_unavailable: "Provider Down",
    publishing_result: "Published",
    budget_threshold: "Budget Alert",
    safety_action: "Safety Action",
    hermes_needs_input: "Input Needed",
  };
  return labels[category] ?? category;
}

function formatRelativeTime(isoString: string): string {
  const now = Date.now();
  const then = new Date(isoString).getTime();
  const diffMs = now - then;
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHour = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHour / 24);

  if (diffSec < 60) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffHour < 24) return `${diffHour}h ago`;
  return `${diffDay}d ago`;
}

// =============================================================================
// NotificationItem Component
// =============================================================================

function NotificationItem({
  notification,
  onMarkAsRead,
}: {
  notification: AppNotification;
  onMarkAsRead: (id: string) => void;
}) {
  const categoryColor = CATEGORY_COLORS[notification.category] ?? "text-content-muted";

  return (
    <div
      className={cn(
        "px-4 py-3 border-b border-border-subtle last:border-0 transition-colors",
        notification.is_read
          ? "opacity-60"
          : "bg-surface-hover/30"
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <span
              className={cn(
                "text-[10px] font-medium uppercase tracking-wide",
                categoryColor
              )}
            >
              {getCategoryLabel(notification.category)}
            </span>
            {notification.is_mandatory && (
              <span className="text-[9px] font-bold text-red-400 bg-red-400/10 px-1 py-0.5 rounded">
                REQUIRED
              </span>
            )}
          </div>
          <p className="text-sm font-medium text-content-primary truncate">
            {notification.title}
          </p>
          {notification.body && (
            <p className="text-xs text-content-tertiary mt-0.5 line-clamp-2">
              {notification.body}
            </p>
          )}
          <span className="text-[10px] text-content-muted mt-1 block">
            {formatRelativeTime(notification.created_at)}
          </span>
        </div>
        {!notification.is_read && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onMarkAsRead(notification.id);
            }}
            aria-label="Mark as read"
            className="p-1 rounded hover:bg-surface-hover text-content-muted hover:text-content-secondary transition-colors shrink-0"
          >
            <Check className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
      {notification.action_url && (
        <a
          href={notification.action_url}
          className="text-[11px] text-status-info hover:text-interactive-default mt-1.5 inline-block"
        >
          View details →
        </a>
      )}
    </div>
  );
}

// =============================================================================
// NotificationBell Component
// =============================================================================

/**
 * Notification bell with unread badge and dropdown.
 *
 * Uses useNotifications hook (backed by useEventClient) for realtime
 * event-driven updates without polling.
 *
 * Validates: Requirements R63.4, R63.5, R63.6
 */
export function NotificationBell({ orgId, userId, className }: NotificationBellProps) {
  const { notifications, unreadCount, markAsRead, markAllAsRead, isConnected } =
    useNotifications(orgId, userId);
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close on click outside
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // Close on Escape key
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setIsOpen(false);
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, []);

  return (
    <div ref={dropdownRef} className={cn("relative", className)}>
      {/* Bell Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        aria-label={`Notifications${unreadCount > 0 ? ` (${unreadCount} unread)` : ""}`}
        aria-expanded={isOpen}
        className="relative p-2 text-content-tertiary hover:text-content-secondary transition-colors rounded-lg hover:bg-surface-hover"
      >
        <Bell className="h-5 w-5" />
        {unreadCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-status-error text-[9px] font-bold text-content-inverse animate-in fade-in duration-200">
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        )}
        {/* Connection indicator dot */}
        {!isConnected && orgId && (
          <span
            className="absolute bottom-0.5 right-0.5 h-2 w-2 rounded-full bg-amber-500"
            title="Realtime disconnected"
          />
        )}
      </button>

      {/* Dropdown */}
      {isOpen && (
        <div className="absolute right-0 top-full mt-2 w-96 rounded-xl border border-border-strong bg-surface-raised shadow-2xl z-50 animate-in fade-in slide-in-from-top-1 duration-150">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-border-subtle">
            <div className="flex items-center gap-2">
              <p className="text-sm font-semibold text-content-primary">Notifications</p>
              {unreadCount > 0 && (
                <span className="text-[10px] font-medium text-content-muted bg-surface-hover px-1.5 py-0.5 rounded-full">
                  {unreadCount} new
                </span>
              )}
            </div>
            <div className="flex items-center gap-1">
              {unreadCount > 0 && (
                <button
                  onClick={markAllAsRead}
                  aria-label="Mark all as read"
                  className="p-1.5 rounded-lg text-content-muted hover:text-content-secondary hover:bg-surface-hover transition-colors"
                  title="Mark all as read"
                >
                  <CheckCheck className="h-4 w-4" />
                </button>
              )}
              <button
                onClick={() => setIsOpen(false)}
                aria-label="Close notifications"
                className="p-1.5 rounded-lg text-content-muted hover:text-content-primary hover:bg-surface-hover transition-colors"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Notification List */}
          <div className="max-h-[400px] overflow-y-auto">
            {notifications.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-8 px-4">
                <Bell className="h-8 w-8 text-content-muted mb-2 opacity-40" />
                <p className="text-sm text-content-muted">No notifications yet</p>
                <p className="text-xs text-content-muted mt-1">
                  You&apos;ll see updates about jobs, approvals, and system events here.
                </p>
              </div>
            ) : (
              notifications.map((notification) => (
                <NotificationItem
                  key={notification.id}
                  notification={notification}
                  onMarkAsRead={markAsRead}
                />
              ))
            )}
          </div>

          {/* Footer */}
          {notifications.length > 0 && (
            <div className="px-4 py-2 border-t border-border-subtle">
              <p className="text-[10px] text-content-muted text-center">
                Showing {notifications.length} most recent
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

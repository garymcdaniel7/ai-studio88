"use client";

/**
 * useOnlineStatus — Tracks browser online/offline state.
 *
 * Uses navigator.onLine + online/offline events for immediate detection.
 * Also performs periodic backend health checks for more accurate status
 * (navigator.onLine can be true even when backend is unreachable).
 *
 * Validates: Requirements R17.5, R23.6
 */

import { useState, useEffect, useCallback, useRef } from "react";

// =============================================================================
// Types
// =============================================================================

export interface OnlineStatus {
  /** Whether the browser reports being online */
  isOnline: boolean;
  /** Whether we've confirmed backend connectivity (stricter than isOnline) */
  isBackendReachable: boolean;
  /** Timestamp of last successful connectivity check */
  lastOnlineAt: number;
  /** Trigger a manual connectivity check */
  checkNow: () => void;
}

// =============================================================================
// Constants
// =============================================================================

/** How often to verify connectivity (ms) */
const CHECK_INTERVAL = 30_000;

/** Timeout for health check requests (ms) */
const CHECK_TIMEOUT = 5_000;

// =============================================================================
// Hook
// =============================================================================

/**
 * Tracks online/offline state using both browser events and backend health checks.
 *
 * @example
 * ```tsx
 * const { isOnline, isBackendReachable } = useOnlineStatus();
 * ```
 */
export function useOnlineStatus(): OnlineStatus {
  const [isOnline, setIsOnline] = useState<boolean>(
    typeof navigator !== "undefined" ? navigator.onLine : true
  );
  const [isBackendReachable, setIsBackendReachable] = useState<boolean>(true);
  const [lastOnlineAt, setLastOnlineAt] = useState<number>(Date.now());

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ─── Backend health check ──────────────────────────────────────────────

  const checkBackend = useCallback(async () => {
    if (!navigator.onLine) {
      setIsBackendReachable(false);
      return;
    }

    try {
      const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const response = await fetch(`${apiBase}/`, {
        method: "HEAD",
        signal: AbortSignal.timeout(CHECK_TIMEOUT),
      });
      const reachable = response.ok;
      setIsBackendReachable(reachable);
      if (reachable) {
        setLastOnlineAt(Date.now());
      }
    } catch {
      setIsBackendReachable(false);
    }
  }, []);

  // ─── Browser online/offline events ─────────────────────────────────────

  useEffect(() => {
    function handleOnline() {
      setIsOnline(true);
      setLastOnlineAt(Date.now());
      // Verify backend is also reachable
      checkBackend();
    }

    function handleOffline() {
      setIsOnline(false);
      setIsBackendReachable(false);
    }

    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);

    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, [checkBackend]);

  // ─── Periodic health check ─────────────────────────────────────────────

  useEffect(() => {
    // Initial check
    checkBackend();

    // Periodic check
    intervalRef.current = setInterval(checkBackend, CHECK_INTERVAL);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [checkBackend]);

  return {
    isOnline,
    isBackendReachable,
    lastOnlineAt,
    checkNow: checkBackend,
  };
}

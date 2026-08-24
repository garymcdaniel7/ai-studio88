"use client";

import { useEffect, useRef } from "react";

/**
 * useIdleTimeout — auto-invokes `onIdle` after the user is inactive for
 * `timeoutMs` (no mouse/touch/keyboard activity on the window). Resets the
 * timer on any user interaction. Used to auto-logout / protect an open session.
 *
 * @param onIdle  Called once when the idle threshold is reached.
 * @param timeoutMs  Idle threshold in milliseconds (default 30 min).
 * @param enabled  When false, the timer is disabled (e.g. not authenticated).
 */
export function useIdleTimeout(
  onIdle: () => void,
  timeoutMs = 30 * 60 * 1000,
  enabled = true,
) {
  const onIdleRef = useRef(onIdle);
  onIdleRef.current = onIdle;
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!enabled) return;

    const resetTimer = () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      timeoutRef.current = setTimeout(() => onIdleRef.current(), timeoutMs);
    };

    const events: (keyof WindowEventMap)[] = [
      "mousemove",
      "mousedown",
      "keydown",
      "touchstart",
      "scroll",
      "wheel",
    ];

    // Reset on activity
    events.forEach((e) => window.addEventListener(e, resetTimer, { passive: true }));

    // Kick off the initial timer
    resetTimer();

    return () => {
      events.forEach((e) => window.removeEventListener(e, resetTimer));
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, [timeoutMs, enabled]);
}

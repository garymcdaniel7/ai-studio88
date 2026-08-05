"""Ọbalúayé Background Monitor — runs health checks periodically.

Starts on application boot and runs every 30 seconds.
Stores results for the admin dashboard (Ise page) to display.
Alerts are surfaced via the /aios/v1/health/alerts endpoint and
feed into the frontend topbar bell icon.

This runs as a background thread (not a separate process).
It does NOT need LLM — pure rule-based health polling.

## Current Architecture (2026-07-19)

Monitored services:
- ComfyUI (GPU generation) — auto-restart via SSH on failure
- Ollama (local LLM) — auto-restart locally on crash
- Supabase (database) — alert only
- Backblaze B2 (storage) — alert only
- ElevenLabs (voice) — alert only
- Worker API (GPU worker HTTP) — alert only

Recovery rules:
- Ollama: safe to auto-restart locally (free, local, no data loss)
- ComfyUI: safe to auto-restart on worker (already running, just needs bounce)
- Others: alert user, never auto-fix external services

Red Team findings integrated:
- Auth (401) and rate limiting (429) are CORRECT — don't try to "fix" them
- GPU offline is expected when no worker active — not a critical alert
- Cost tracking active — budget alerts at 80% threshold
"""

from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)

_monitor_thread: threading.Thread | None = None
_running = False
_check_interval = 30  # seconds


def start_background_monitor() -> None:
    """Start the background health monitor thread.

    Called once on application startup. Safe to call multiple times.
    """
    global _monitor_thread, _running

    if _running:
        return

    _running = True
    _monitor_thread = threading.Thread(target=_monitor_loop, daemon=True, name="ise-monitor")
    _monitor_thread.start()
    logger.info(f"Ise background monitor started (interval: {_check_interval}s)")


def stop_background_monitor() -> None:
    """Stop the background monitor."""
    global _running
    _running = False
    logger.info("Ise background monitor stopped")


def _monitor_loop() -> None:
    """Main monitoring loop — runs health checks every interval."""
    # Wait a bit on startup to let services initialize
    time.sleep(10)

    while _running:
        try:
            from backend.aios.obaluaye.monitor import get_monitor

            monitor = get_monitor()
            report = monitor.check_all()

            # Log alerts
            for alert in report.alerts:
                logger.warning(f"[ISE ALERT] {alert.get('service', '?')}: {alert.get('message', '?')}")

            # Auto-recovery for transient failures
            for name, svc in report.services.items():
                if svc.status.value == "down" and svc.consecutive_failures == 3:
                    # First time hitting DOWN — try auto-recovery
                    _attempt_recovery(name, svc.error or "")

        except Exception as e:
            logger.debug(f"Ise monitor loop error: {e}")

        time.sleep(_check_interval)


def _attempt_recovery(service: str, error: str) -> None:
    """Attempt automatic recovery for a downed service.

    Recovery governance:
    - Ollama (local): safe, free, auto-restart always
    - ComfyUI (on worker): safe if worker is active, restart via SSH
    - Worker API: safe if worker is active
    - External services (Supabase, B2, ElevenLabs): NEVER auto-fix, alert only
    - Auth/rate limit: NEVER "fix" — these are correct security behavior
    """
    import subprocess

    # IMPORTANT: 401 and 429 are CORRECT behavior — never try to "fix" auth or rate limits
    error_lower = error.lower()
    if "401" in error_lower or "unauthorized" in error_lower:
        logger.debug(f"[ISE] {service} returned 401 — auth working correctly, no recovery needed")
        return
    if "429" in error_lower or "rate limit" in error_lower:
        logger.debug(f"[ISE] {service} returned 429 — rate limiting working correctly")
        return

    # Auto-restart Ollama locally (safe, free, no approval needed)
    if service == "ollama" and ("Not reachable" in error or "broken pipe" in error_lower):
        try:
            subprocess.run(["pkill", "-f", "ollama serve"], capture_output=True, timeout=5)
            import time
            time.sleep(2)
            subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logger.info("[ISE AUTO-RECOVERY] Restarted Ollama locally")
            return
        except Exception as e:
            logger.warning(f"Ollama auto-restart failed: {e}")

    # For other services, use the recovery engine
    try:
        from backend.aios.obaluaye.recovery import get_recovery_engine

        engine = get_recovery_engine()
        action = engine.handle_failure(service, error)
        if action:
            logger.info(f"[ISE RECOVERY] {service}: {action.action} — {action.reason}")
    except Exception as e:
        logger.debug(f"Recovery attempt failed: {e}")

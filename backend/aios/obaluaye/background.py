"""Ise/Obaluaye Background Monitor — runs health checks periodically.

Starts on application boot and runs every 30 seconds.
Stores results for the Ise dashboard to display.
Alerts are surfaced via the /aios/v1/health/alerts endpoint.

This runs as a background thread (not a separate process).
It does NOT need LLM — pure rule-based health polling.
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
    """Attempt automatic recovery for a downed service."""
    try:
        from backend.aios.obaluaye.recovery import get_recovery_engine

        engine = get_recovery_engine()
        action = engine.handle_failure(service, error)
        if action:
            logger.info(f"[ISE RECOVERY] {service}: {action.action} — {action.reason}")
    except Exception as e:
        logger.debug(f"Recovery attempt failed: {e}")

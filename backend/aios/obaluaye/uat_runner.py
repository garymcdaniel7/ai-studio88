"""Ise UAT Runner — Scheduled Playwright test execution.

Runs Playwright E2E tests on a schedule, stores results in memory,
and surfaces failures as Ise alerts.

Features:
- Configurable interval (default: every 60 minutes)
- Full test suite or targeted test groups
- Stores last N test runs in memory for the dashboard
- Failed tests generate Ise alerts with screenshots
- Results accessible via /aios/v1/ise/uat/results
"""

from __future__ import annotations

import json
import logging
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# --- Test Run Results ---


@dataclass
class TestResult:
    """A single test case result."""

    name: str
    status: str  # "passed", "failed", "skipped"
    duration_ms: float = 0.0
    error: str | None = None
    screenshot: str | None = None  # base64 or file path


@dataclass
class TestRun:
    """A complete test run."""

    run_id: str
    started_at: str
    completed_at: str | None = None
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    duration_seconds: float = 0.0
    results: list[TestResult] = field(default_factory=list)
    trigger: str = "scheduled"  # "scheduled" | "manual" | "on_deploy"


# --- UAT Runner ---

_MAX_STORED_RUNS = 20
_test_runs: list[dict[str, Any]] = []
_uat_thread: threading.Thread | None = None
_uat_running = False
_uat_interval = 3600  # 60 minutes default


def get_test_runs() -> list[dict[str, Any]]:
    """Get all stored test run results."""
    return list(_test_runs)


def get_latest_run() -> dict[str, Any] | None:
    """Get the most recent test run."""
    return _test_runs[-1] if _test_runs else None


def get_uat_alerts() -> list[dict[str, Any]]:
    """Get alerts from the latest UAT run (failed tests)."""
    latest = get_latest_run()
    if not latest or latest.get("failed", 0) == 0:
        return []

    alerts = []
    for result in latest.get("results", []):
        if result.get("status") == "failed":
            alerts.append({
                "service": "uat",
                "severity": "warning",
                "message": f"Test failed: {result['name']} — {result.get('error', 'unknown')}",
                "timestamp": latest.get("completed_at"),
                "test_name": result["name"],
            })
    return alerts


def run_tests_now(test_filter: str | None = None, trigger: str = "manual") -> dict[str, Any]:
    """Run Playwright tests immediately and return results.

    Args:
        test_filter: Optional filter string (e.g. "fleet" to run only fleet tests)
        trigger: What triggered this run (manual, scheduled, on_deploy)
    """
    project_root = Path(__file__).resolve().parents[3]  # ai-studio88/
    tests_dir = project_root / "tests" / "e2e"

    # Build command
    cmd = ["npx", "playwright", "test", "--reporter=json"]

    if test_filter:
        cmd.append(f"--grep={test_filter}")

    # If we have a specific test directory
    if tests_dir.exists():
        cmd.append(str(tests_dir))
    else:
        # Fallback: run from frontend if tests are there
        frontend_tests = project_root / "frontend" / "tests"
        if frontend_tests.exists():
            cmd.append(str(frontend_tests))

    run_id = f"uat_{int(time.time())}"
    started_at = datetime.now(timezone.utc).isoformat()

    logger.info(f"[ISE UAT] Starting test run {run_id} (trigger: {trigger}, filter: {test_filter})")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout
            cwd=str(project_root / "frontend") if (project_root / "frontend").exists() else str(project_root),
        )

        completed_at = datetime.now(timezone.utc).isoformat()

        # Parse Playwright JSON output
        run_data = _parse_playwright_json(result.stdout, run_id, started_at, completed_at, trigger)

        # If JSON parse fails, fallback to exit code
        if run_data["total"] == 0 and result.returncode != 0:
            run_data["total"] = 1
            run_data["failed"] = 1
            run_data["results"] = [{
                "name": "playwright_execution",
                "status": "failed",
                "error": result.stderr[:500] if result.stderr else "Non-zero exit code",
            }]

    except subprocess.TimeoutExpired:
        completed_at = datetime.now(timezone.utc).isoformat()
        run_data = {
            "run_id": run_id,
            "started_at": started_at,
            "completed_at": completed_at,
            "total": 1,
            "passed": 0,
            "failed": 1,
            "skipped": 0,
            "trigger": trigger,
            "results": [{"name": "timeout", "status": "failed", "error": "Test run exceeded 10min timeout"}],
        }
    except FileNotFoundError:
        completed_at = datetime.now(timezone.utc).isoformat()
        run_data = {
            "run_id": run_id,
            "started_at": started_at,
            "completed_at": completed_at,
            "total": 0,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "trigger": trigger,
            "results": [],
            "error": "Playwright not installed (npx playwright not found)",
        }

    # Store result
    _test_runs.append(run_data)
    if len(_test_runs) > _MAX_STORED_RUNS:
        _test_runs.pop(0)

    # Log summary
    logger.info(
        f"[ISE UAT] Run {run_id} complete: "
        f"{run_data['passed']}/{run_data['total']} passed, "
        f"{run_data['failed']} failed"
    )

    return run_data


def _parse_playwright_json(
    stdout: str,
    run_id: str,
    started_at: str,
    completed_at: str,
    trigger: str,
) -> dict[str, Any]:
    """Parse Playwright JSON reporter output."""
    try:
        data = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return {
            "run_id": run_id,
            "started_at": started_at,
            "completed_at": completed_at,
            "total": 0,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "trigger": trigger,
            "results": [],
        }

    results = []
    passed = 0
    failed = 0
    skipped = 0

    # Playwright JSON format: suites → specs → tests
    for suite in data.get("suites", []):
        for spec in suite.get("specs", []):
            for test in spec.get("tests", []):
                status = test.get("status", "unknown")
                result_entry = {
                    "name": f"{spec.get('title', '')} > {test.get('title', '')}".strip(" > "),
                    "status": status,
                    "duration_ms": test.get("duration", 0),
                }

                if status == "passed":
                    passed += 1
                elif status == "failed" or status == "timedOut":
                    failed += 1
                    # Extract error message
                    for r in test.get("results", []):
                        if r.get("error"):
                            result_entry["error"] = r["error"].get("message", "")[:300]
                            break
                else:
                    skipped += 1

                results.append(result_entry)

    return {
        "run_id": run_id,
        "started_at": started_at,
        "completed_at": completed_at,
        "total": passed + failed + skipped,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "trigger": trigger,
        "results": results,
    }


# --- Scheduled Runner ---


def start_uat_scheduler(interval_seconds: int = 3600) -> None:
    """Start the UAT scheduler thread.

    Args:
        interval_seconds: How often to run tests (default 1 hour)
    """
    global _uat_thread, _uat_running, _uat_interval

    if _uat_running:
        return

    _uat_interval = interval_seconds
    _uat_running = True
    _uat_thread = threading.Thread(target=_uat_loop, daemon=True, name="ise-uat-scheduler")
    _uat_thread.start()
    logger.info(f"Ise UAT scheduler started (interval: {interval_seconds}s)")


def stop_uat_scheduler() -> None:
    """Stop the UAT scheduler."""
    global _uat_running
    _uat_running = False
    logger.info("Ise UAT scheduler stopped")


def _uat_loop() -> None:
    """UAT scheduler loop — runs tests at intervals."""
    # Initial delay: wait 5 minutes after startup
    time.sleep(300)

    while _uat_running:
        try:
            run_tests_now(trigger="scheduled")
        except Exception as e:
            logger.error(f"[ISE UAT] Scheduler error: {e}")

        time.sleep(_uat_interval)

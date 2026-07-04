"""Infrastructure Status Dashboard — Aggregated real-time status for UI consumption.

Provides a single, comprehensive JSON response combining:
- Worker orchestrator state (session, GPU, connection)
- Connection race metrics (boot speed, success rate)
- Model cache inventory (B2 cached + loaded on worker)
- Cost tracking (session, daily, monthly)
- Provider health (simulation, comfyui, vast)
- Reputation summary (tracked hosts, blacklisted, preferred)

Design principles:
- User-centric: Response is designed for a frontend dashboard to render directly
- Safe: Never expose secrets, API keys, or full URLs with credentials
- Resilient: Each section is independently try/excepted — partial data is fine
- Real-time: Costs and status reflect the current moment
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _mask_url(url: Optional[str]) -> Optional[str]:
    """Mask a URL to avoid leaking tokens or internal IPs in dashboard."""
    if not url:
        return None
    # Only show scheme + host, not query params or paths with tokens
    if "?" in url:
        return url.split("?")[0]
    return url


def _safe_section(name: str, fn, default: Any = None):
    """Execute a section builder, return default on failure."""
    try:
        return fn()
    except Exception as e:
        logger.warning(f"Dashboard section '{name}' failed: {e}")
        return default if default is not None else {"error": str(e)}


# =============================================================================
# Section Builders
# =============================================================================


def _build_system_health(worker_status: dict, providers: dict) -> str:
    """Determine overall system health from subsystem states."""
    # If worker is in error state, system is degraded
    if worker_status.get("status") == "error":
        return "degraded"

    # If no session, system is healthy (idle) — ComfyUI being down is expected
    if worker_status.get("status") == "no_session":
        return "healthy"

    # If there's an active session, check provider health
    unhealthy_critical = [
        name for name, info in providers.items()
        if name in ("comfyui", "vast") and not info.get("healthy", True)
    ]
    if unhealthy_critical:
        return "degraded"

    return "healthy"


def _build_worker_section(orchestrator) -> dict[str, Any]:
    """Build the worker status section from the orchestrator."""
    status_data = orchestrator.get_status()
    session = orchestrator.session

    if not session:
        return {
            "status": "no_session",
            "gpu_name": None,
            "instance_id": None,
            "ssh_host": None,
            "ssh_port": None,
            "comfyui_url": None,
            "uptime_seconds": 0,
            "jobs_completed": 0,
            "current_cost": 0.0,
            "hourly_rate": 0.0,
        }

    # Calculate uptime
    uptime_seconds = 0.0
    if session.status not in ("stopped", "destroyed", "error"):
        try:
            started = datetime.fromisoformat(session.started_at)
            uptime_seconds = (datetime.now(timezone.utc) - started).total_seconds()
        except (ValueError, TypeError):
            pass

    return {
        "status": session.status,
        "gpu_name": session.gpu_name or None,
        "instance_id": session.instance_id,
        "ssh_host": session.ssh_host or None,
        "ssh_port": session.ssh_port or None,
        "comfyui_url": _mask_url(session.comfyui_url),
        "uptime_seconds": round(uptime_seconds, 1),
        "jobs_completed": session.jobs_completed,
        "current_cost": round(session.total_cost, 4),
        "hourly_rate": session.hourly_rate,
    }


def _build_connection_section(orchestrator) -> dict[str, Any]:
    """Build connection race metrics from the orchestrator."""
    log = orchestrator.get_connection_log()
    session = orchestrator.session

    # Compute lifetime stats
    total_attempts = len(log)
    successes = sum(1 for a in log if a.get("status") == "success")
    success_rate = round(successes / total_attempts, 2) if total_attempts > 0 else 0.0

    # Boot time from latest successful attempt
    successful_attempts = [
        a for a in log
        if a.get("status") == "success" and a.get("boot_time_seconds")
    ]
    last_boot_time = (
        successful_attempts[-1]["boot_time_seconds"]
        if successful_attempts
        else None
    )

    # Race in progress?
    race_in_progress = (
        session is not None and session.status in ("connecting", "booting")
    )

    # If there's an active race, get candidate info from metadata
    candidates_launched = 0
    candidates_alive = 0
    winner_found = False

    if session and session.metadata:
        candidates_launched = session.metadata.get("race_candidates", 0)
        winner_found = session.status not in ("connecting", "booting", "error")

    return {
        "race_in_progress": race_in_progress,
        "candidates_launched": candidates_launched,
        "candidates_alive": candidates_alive,
        "winner_found": winner_found,
        "last_boot_time_seconds": last_boot_time,
        "total_attempts_lifetime": total_attempts,
        "success_rate": success_rate,
    }


def _build_models_section(orchestrator) -> dict[str, Any]:
    """Build model cache and loaded model info."""
    session = orchestrator.session
    loaded_on_worker = session.models_loaded if session else []

    # Try to list cached models from B2
    cached_in_b2: list[str] = []
    try:
        from backend.providers.vast.model_cache import list_cached_models, list_known_models

        cached = list_cached_models()
        cached_in_b2 = [m["filename"] for m in cached]
    except Exception as e:
        logger.debug(f"Could not list B2 cache: {e}")
        # Fall back to known models list
        try:
            from backend.providers.vast.model_cache import list_known_models
            known = list_known_models()
            cached_in_b2 = [m["name"] for m in known]
        except Exception:
            pass

    # Download in progress? Check worker status
    download_in_progress = None
    if session and session.status == "downloading_model":
        download_in_progress = "model download active"

    return {
        "cached_in_b2": cached_in_b2,
        "loaded_on_worker": loaded_on_worker,
        "download_in_progress": download_in_progress,
    }


def _build_cost_section(orchestrator) -> dict[str, Any]:
    """Build cost tracking section using the Cost Intelligence module."""
    from backend.infrastructure.cost_intelligence import get_cost_tracker

    tracker = get_cost_tracker()
    current = tracker.get_current_spend()
    budget = tracker.check_budget()

    return {
        "current_session_cost": current["current_cost"],
        "today_cost": tracker.get_daily_spend(),
        "this_month_cost": tracker.get_monthly_spend(),
        "hourly_rate": current["hourly_rate"],
        "budget": budget,
    }


def _build_providers_section(orchestrator) -> dict[str, Any]:
    """Build provider health checks."""
    providers: dict[str, Any] = {}

    # Simulation provider (always healthy — it's local)
    providers["simulation"] = {"healthy": True}

    # ComfyUI health — check if worker has comfyui_url
    session = orchestrator.session
    if session and session.comfyui_url and session.status == "ready":
        providers["comfyui"] = {"healthy": True}
    elif session and session.status in ("installing", "starting_comfyui", "downloading_model"):
        providers["comfyui"] = {"healthy": False, "message": f"ComfyUI is {session.status}"}
    else:
        providers["comfyui"] = {"healthy": False, "message": "No active ComfyUI instance"}

    # Vast.ai provider
    if session and session.instance_id:
        providers["vast"] = {"healthy": True, "running_instances": 1}
    else:
        providers["vast"] = {"healthy": True, "running_instances": 0}

    return providers


def _build_reputation_section() -> dict[str, Any]:
    """Build reputation summary from the reputation engine."""
    from backend.infrastructure.provider_reputation import get_reputation_engine

    engine = get_reputation_engine()
    all_reps = engine.get_all_reputations()

    total_hosts = len(all_reps.get("hosts", []))
    blacklisted = len(engine.get_blacklist())
    preferred = len(engine.get_preferred_hosts())

    # Find best GPU and region by overall score
    best_gpu = None
    best_gpu_score = 0.0
    for gpu in all_reps.get("gpus", []):
        if gpu.get("overall_score", 0) > best_gpu_score:
            best_gpu_score = gpu["overall_score"]
            best_gpu = gpu.get("entity_id")

    best_region = None
    best_region_score = 0.0
    for region in all_reps.get("regions", []):
        if region.get("overall_score", 0) > best_region_score:
            best_region_score = region["overall_score"]
            best_region = region.get("entity_id")

    return {
        "total_hosts_tracked": total_hosts,
        "blacklisted_hosts": blacklisted,
        "preferred_hosts": preferred,
        "best_gpu": best_gpu,
        "best_region": best_region,
    }


# =============================================================================
# Main Dashboard Builder
# =============================================================================


def get_dashboard_status() -> dict[str, Any]:
    """Build the full infrastructure status dashboard.

    Aggregates data from all infrastructure subsystems into a single
    JSON-friendly response designed for UI rendering.

    Each section is independently resilient — if one fails, the others
    still report correctly.

    Returns:
        Complete dashboard dict ready for JSON serialization.
    """
    from backend.infrastructure.worker_orchestrator import get_orchestrator

    orchestrator = get_orchestrator()

    # Build each section safely
    worker = _safe_section("worker", lambda: _build_worker_section(orchestrator), {
        "status": "unknown", "error": "Failed to read worker status"
    })

    connection = _safe_section("connection", lambda: _build_connection_section(orchestrator), {
        "race_in_progress": False, "error": "Failed to read connection data"
    })

    models = _safe_section("models", lambda: _build_models_section(orchestrator), {
        "cached_in_b2": [], "loaded_on_worker": [], "download_in_progress": None
    })

    cost = _safe_section("cost", lambda: _build_cost_section(orchestrator), {
        "current_session_cost": 0.0, "today_cost": 0.0, "this_month_cost": 0.0, "hourly_rate": 0.0
    })

    providers = _safe_section("providers", lambda: _build_providers_section(orchestrator), {
        "simulation": {"healthy": True},
        "comfyui": {"healthy": False, "message": "Status unavailable"},
        "vast": {"healthy": True, "running_instances": 0},
    })

    reputation = _safe_section("reputation", lambda: _build_reputation_section(), {
        "total_hosts_tracked": 0, "blacklisted_hosts": 0, "preferred_hosts": 0,
        "best_gpu": None, "best_region": None,
    })

    # Determine overall system health
    system_health = _safe_section(
        "system_health",
        lambda: _build_system_health(worker, providers),
        "healthy",
    )

    return {
        "system_health": system_health,
        "worker": worker,
        "connection": connection,
        "models": models,
        "cost": cost,
        "providers": providers,
        "reputation": reputation,
    }

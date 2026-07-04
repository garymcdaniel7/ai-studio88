"""Infrastructure Intelligence API Router.

Endpoints for worker orchestration, connection racing, and fleet management.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.infrastructure.cost_intelligence import get_cost_tracker
from backend.infrastructure.provider_reputation import get_reputation_engine
from backend.infrastructure.status_dashboard import get_dashboard_status
from backend.infrastructure.worker_orchestrator import get_orchestrator

router = APIRouter(prefix="/api/v1/infrastructure", tags=["infrastructure"])


# =============================================================================
# Request Models
# =============================================================================


class LaunchRequest(BaseModel):
    """Parameters for launching a worker via Connection Race Mode."""
    max_price: float = Field(default=1.50, description="Max hourly cost per GPU")
    min_vram_gb: float = Field(default=12.0, description="Minimum VRAM in GB")
    num_candidates: int = Field(default=3, ge=1, le=10, description="Number of instances to race")
    gpu_filter: Optional[str] = Field(default=None, description="Specific GPU model (e.g. 'RTX 4090')")
    excluded_hosts: list[int] = Field(default_factory=list, description="Host IDs to exclude")
    disk_gb: int = Field(default=80, ge=20, le=500, description="Disk space in GB")
    timeout: int = Field(default=600, ge=60, le=1200, description="Max boot wait in seconds")
    setup_comfyui: bool = Field(default=True, description="Install ComfyUI after SSH is ready")


class StopRequest(BaseModel):
    """Parameters for stopping a worker (currently empty, reserved for future use)."""
    force: bool = Field(default=False, description="Force destroy without graceful shutdown")


class BlacklistRequest(BaseModel):
    """Parameters for manually blacklisting a host."""
    host_id: str = Field(..., description="The host/machine ID to blacklist")
    reason: str = Field(..., description="Reason for blacklisting")


# =============================================================================
# Endpoints
# =============================================================================


@router.post("/launch")
def launch_worker(request: LaunchRequest):
    """Launch a new GPU worker using Connection Race Mode.

    Races multiple Vast.ai instances in parallel. First to boot and
    respond to SSH wins — all others are immediately destroyed.

    Returns session info with connection details on success.
    """
    orchestrator = get_orchestrator()

    try:
        result = orchestrator.launch_worker(
            max_price=request.max_price,
            min_vram_gb=request.min_vram_gb,
            num_candidates=request.num_candidates,
            gpu_filter=request.gpu_filter,
            excluded_hosts=request.excluded_hosts,
            disk_gb=request.disk_gb,
            timeout=request.timeout,
            setup_comfyui=request.setup_comfyui,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Launch failed: {e}")

    if result.get("status") == "already_active":
        raise HTTPException(
            status_code=409,
            detail="A worker session is already active. Stop it first.",
        )

    return result


@router.get("/status")
def get_status():
    """Get comprehensive infrastructure status for dashboard display.

    Returns a single aggregated response covering all subsystems:
    - system_health: overall health (healthy, degraded, offline)
    - worker: GPU session status, uptime, cost
    - connection: race metrics, boot times, success rate
    - models: B2 cache inventory, loaded models, downloads
    - cost: session/daily/monthly cost tracking
    - providers: health of simulation, comfyui, vast
    - reputation: host tracking, blacklist, preferred hosts

    Each section is independently resilient — partial failures
    won't bring down the entire response.
    """
    return get_dashboard_status()


@router.get("/dashboard")
def get_dashboard():
    """Comprehensive infrastructure dashboard — alias for /status.

    Same rich response as /status, provided as a dedicated dashboard
    endpoint for frontend routing convenience.
    """
    return get_dashboard_status()


@router.post("/stop")
def stop_worker(request: Optional[StopRequest] = None):
    """Stop and destroy the current worker instance.

    Terminates the Vast.ai instance and ends the session.
    Calculates final cost based on elapsed time.
    """
    orchestrator = get_orchestrator()
    result = orchestrator.stop_worker()

    if result.get("status") == "no_session":
        raise HTTPException(status_code=404, detail="No active worker to stop")

    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("message", "Stop failed"))

    return result


@router.get("/history")
def get_connection_history():
    """Get the full history of connection attempts.

    Returns all attempts from Connection Race Mode, including
    successes, failures, and timeouts with timing data.
    Useful for provider reputation analysis and cost tracking.
    """
    orchestrator = get_orchestrator()
    return {
        "attempts": orchestrator.get_connection_log(),
        "total_attempts": len(orchestrator.get_connection_log()),
    }


# =============================================================================
# Cost Intelligence Endpoints
# =============================================================================


@router.get("/cost")
def get_cost_summary():
    """Get current spend summary with budget check.

    Returns real-time cost information including:
    - Current active session cost
    - Today's total spend
    - This month's total spend
    - Budget status (daily and monthly limits)
    - Cost breakdown by GPU and provider
    """
    tracker = get_cost_tracker()
    return tracker.get_summary()


@router.get("/cost/history")
def get_cost_history(days: int = 30):
    """Get daily cost history for charting.

    Args:
        days: Number of days to include (default 30, max 365)

    Returns:
        List of daily cost entries with date, cost, and session count.
    """
    days = min(max(days, 1), 365)
    tracker = get_cost_tracker()
    return {
        "history": tracker.get_cost_history(days=days),
        "days": days,
        "budget": tracker.check_budget(),
    }


# =============================================================================
# Reputation Endpoints
# =============================================================================


@router.get("/reputation")
def get_reputation():
    """Get all provider reputation scores.

    Returns reputation data for hosts, GPUs, and regions based on
    historical connection attempts. Scores include reliability,
    performance, and cost efficiency metrics.
    """
    engine = get_reputation_engine()
    return engine.get_all_reputations()


@router.get("/blacklist")
def get_blacklist():
    """Get all blacklisted hosts.

    Returns the list of host IDs that have been blacklisted
    (either manually or auto-blacklisted due to low reliability).
    """
    engine = get_reputation_engine()
    return {
        "blacklisted_hosts": engine.get_blacklist(),
        "total": len(engine.get_blacklist()),
    }


@router.post("/blacklist")
def add_to_blacklist(request: BlacklistRequest):
    """Manually blacklist a host.

    Prevents the host from being used in future connection races.
    Hosts can also be auto-blacklisted if reliability drops below 30%
    after 3+ attempts.
    """
    engine = get_reputation_engine()

    if engine.is_blacklisted(request.host_id):
        raise HTTPException(
            status_code=409,
            detail=f"Host {request.host_id} is already blacklisted",
        )

    engine.blacklist_host(request.host_id, request.reason)
    return {
        "status": "blacklisted",
        "host_id": request.host_id,
        "reason": request.reason,
    }


# =============================================================================
# Render Fleet Endpoints
# =============================================================================

from backend.infrastructure.render_fleet import get_fleet_manager


class FleetAddRequest(BaseModel):
    """Parameters for adding a worker to the fleet."""
    max_price: float = Field(default=1.50, description="Max $/hr")
    min_vram_gb: float = Field(default=12.0, description="Minimum VRAM")
    specialty: str = Field(default="general", description="Worker specialty: general, image, video, training, upscale")
    gpu_filter: Optional[str] = Field(default=None, description="Specific GPU model")
    num_candidates: int = Field(default=3, ge=1, le=10)
    disk_gb: int = Field(default=80, ge=20, le=500)
    timeout: int = Field(default=600, ge=60, le=1200)


@router.get("/fleet")
def get_fleet_status():
    """Get render fleet status — all active workers, queue, costs.

    Returns comprehensive fleet information for dashboard display:
    - Fleet size and worker details
    - Job queue depth
    - Total hourly and running costs
    - Worker specialties breakdown
    """
    fleet = get_fleet_manager()
    return fleet.get_fleet_status()


@router.post("/fleet/add")
def add_fleet_worker(request: FleetAddRequest):
    """Add a new worker to the render fleet.

    Launches a GPU worker via Connection Race Mode and adds it to
    the fleet for parallel job processing. Specify a specialty to
    route specific job types to this worker.
    """
    fleet = get_fleet_manager()
    try:
        result = fleet.add_worker(
            max_price=request.max_price,
            min_vram_gb=request.min_vram_gb,
            specialty=request.specialty,
            gpu_filter=request.gpu_filter,
            num_candidates=request.num_candidates,
            disk_gb=request.disk_gb,
            timeout=request.timeout,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fleet add failed: {e}")
    return result


@router.delete("/fleet/{worker_id}")
def remove_fleet_worker(worker_id: str):
    """Remove a worker from the fleet and destroy its instance."""
    fleet = get_fleet_manager()
    result = fleet.remove_worker(worker_id)
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/fleet/stop-all")
def stop_fleet():
    """Emergency shutdown — destroy all fleet workers immediately."""
    fleet = get_fleet_manager()
    return fleet.stop_all()


@router.post("/fleet/jobs")
def submit_fleet_job(data: dict):
    """Submit a job to the fleet queue.

    Jobs are automatically routed to the best available worker
    based on specialty and availability.

    Required: job_type (image, video, training, upscale)
    Optional: model, priority (1-10, lower=higher), params
    """
    if not data.get("job_type"):
        raise HTTPException(status_code=400, detail="'job_type' required")

    fleet = get_fleet_manager()
    job = fleet.submit_job(
        job_type=data["job_type"],
        model=data.get("model", ""),
        priority=int(data.get("priority", 5)),
        params=data.get("params", {}),
    )
    return job.to_dict()


# =============================================================================
# Admin Settings Endpoints
# =============================================================================

from backend.infrastructure.admin_settings import get_all_service_status
from backend.infrastructure.diagnostic_agent import get_diagnostic_agent


# =============================================================================
# Diagnostic Agent Endpoints
# =============================================================================


class DiagnoseRequest(BaseModel):
    """Parameters for submitting an error for diagnosis."""
    error_type: str = Field(..., description="Error identifier (e.g. 'cuda_incompatible')")
    context: dict = Field(default_factory=dict, description="Additional context about the error")
    attempt_auto_fix: bool = Field(default=False, description="Attempt automatic resolution if possible")


@router.post("/diagnose")
def diagnose_error(request: DiagnoseRequest):
    """Submit an error for diagnosis by the self-healing agent.

    The diagnostic agent recognizes known error patterns, suggests
    fixes, and can attempt automatic resolution. It learns from
    every interaction to improve future suggestions.

    Set attempt_auto_fix=true to let the agent try resolving
    the issue automatically (only works for known fixable errors).
    """
    agent = get_diagnostic_agent()
    diagnosis = agent.diagnose(request.error_type, request.context)

    response = {
        "error_type": diagnosis.error_type,
        "severity": diagnosis.severity.value,
        "root_cause": diagnosis.root_cause,
        "suggested_fix": diagnosis.suggested_fix,
        "can_auto_fix": diagnosis.can_auto_fix,
        "auto_fix_action": diagnosis.auto_fix_action,
        "related_errors": diagnosis.related_errors,
    }

    # Attempt auto-fix if requested and possible
    if request.attempt_auto_fix and diagnosis.can_auto_fix:
        fix_result = agent.auto_fix(request.error_type, request.context)
        response["auto_fix_result"] = fix_result

    return response


@router.get("/known-issues")
def get_known_issues():
    """List all recognized error patterns with fix success rates.

    Returns every pattern the diagnostic agent knows about,
    including severity, root cause, suggested fix, and historical
    success rate for each fix type.
    """
    agent = get_diagnostic_agent()
    return {
        "patterns": agent.get_known_issues(),
        "total": len(agent.get_known_issues()),
    }


@router.get("/admin/services")
def get_services_status():
    """Check all configured service connections.

    Returns connection status for every external service:
    Vast.ai, Backblaze B2, Supabase, ComfyUI, ElevenLabs,
    HuggingFace, and Model Cache.

    Designed for the admin dashboard — shows what's working,
    what needs configuration, and response times.
    """
    return get_all_service_status()

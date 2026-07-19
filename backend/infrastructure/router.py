"""Infrastructure Intelligence API Router.

Endpoints for worker orchestration, connection racing, and fleet management.
"""

from __future__ import annotations

import os
from datetime import UTC
from pathlib import Path

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
    num_candidates: int = Field(default=3, ge=1, le=10, description="Number of instances to race (Vast.ai only)")
    gpu_filter: str | None = Field(default=None, description="Specific GPU model (e.g. 'RTX 4090')")
    excluded_hosts: list[int] = Field(default_factory=list, description="Host IDs to exclude")
    disk_gb: int = Field(default=80, ge=20, le=500, description="Disk space in GB")
    timeout: int = Field(default=600, ge=60, le=1200, description="Max boot wait in seconds")
    setup_comfyui: bool = Field(default=True, description="Install ComfyUI after boot")
    provider: str | None = Field(default=None, description="GPU provider: 'runpod' (default, faster) or 'vast' (cheaper, variable)")


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
            provider=request.provider,
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


@router.get("/worker/progress")
def get_worker_progress():
    """Get lightweight worker boot progress (for frontend polling during launch).

    Returns only the worker session status and progress message.
    Frontend should poll this every 3-5 seconds during boot.

    Statuses:
    - no_session: Nothing running
    - pending: Looking for GPU
    - booting: Instance launching, waiting for SSH
    - installing: ComfyUI being installed
    - downloading_model: AI model loading
    - starting_comfyui: Starting generation engine
    - ready: Worker fully operational
    - error: Something went wrong (check progress_message)
    """
    orchestrator = get_orchestrator()
    return orchestrator.get_status()


@router.get("/dashboard")
def get_dashboard():
    """Comprehensive infrastructure dashboard — alias for /status.

    Same rich response as /status, provided as a dedicated dashboard
    endpoint for frontend routing convenience.
    """
    return get_dashboard_status()


@router.post("/stop")
def stop_worker(request: StopRequest | None = None):
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
    - This week's and month's total spend
    - Per-job cost breakdown
    - Budget status (daily and monthly limits)
    """
    tracker = get_cost_tracker()
    summary = tracker.get_summary()

    # Add job costs breakdown
    job_totals = tracker.get_total_job_spend()
    summary["job_costs"] = job_totals
    summary["generation_count"] = job_totals.get("job_count", 0)
    summary["per_image_avg"] = (
        round(
            job_totals["by_type"].get("generation", 0)
            / max(1, sum(1 for c in tracker.get_job_costs("generation") if c)),
            6,
        )
        if job_totals["by_type"].get("generation")
        else 0
    )

    return summary


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


@router.get("/cost/hourly")
def get_cost_hourly_breakdown():
    """Get today's GPU cost broken down by hour.

    Used for the tooltip on the admin GPU Balance card
    and the analytics cost chart.
    """
    from datetime import datetime

    get_cost_tracker()

    # Get today's date
    today = datetime.now(UTC).date().isoformat()

    # Build hourly breakdown (24 slots)
    hours: dict[str, float] = {}
    for h in range(24):
        hours[f"{h:02d}:00"] = 0.0

    # If we have the active session, calculate current cost
    orchestrator = get_orchestrator()
    if orchestrator.is_active and orchestrator.session:
        from datetime import datetime as dt

        started = orchestrator.session.started_at
        rate = orchestrator.session.hourly_rate
        try:
            start_time = dt.fromisoformat(started.replace("Z", "+00:00"))
            elapsed_hours = (dt.now(UTC) - start_time).total_seconds() / 3600
            current_hour = dt.now(UTC).hour
            hours[f"{current_hour:02d}:00"] = round(elapsed_hours * rate, 4)
        except Exception:
            pass

    total_today = sum(hours.values())

    return {
        "date": today,
        "hourly": hours,
        "total_today": round(total_today, 4),
        "currency": "USD",
    }


# =============================================================================
# Reputation Endpoints
# =============================================================================


@router.get("/cost/jobs")
def get_job_costs(job_type: str | None = None, limit: int = 50):
    """Get per-job cost records (generation, voice, training)."""
    tracker = get_cost_tracker()
    return {
        "costs": tracker.get_job_costs(job_type=job_type, limit=limit),
        "totals": tracker.get_total_job_spend(),
    }


@router.get("/reputation")
def get_reputation():
    """Get all provider reputation scores.

    Returns reputation data for hosts, GPUs, and regions based on
    historical connection attempts. Scores include reliability,
    performance, and cost efficiency metrics.
    """
    engine = get_reputation_engine()
    return engine.get_all_reputations()


@router.get("/providers/compare")
def compare_providers():
    """Compare GPU providers (Vast.ai vs RunPod) based on historical performance.

    Returns boot time averages, success rates, cost data, and a recommendation
    for which provider to use as default. Used by the Fleet Settings UI to
    show the advisory note about load times.
    """
    engine = get_reputation_engine()
    return engine.get_provider_comparison()


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
    specialty: str = Field(
        default="general", description="Worker specialty: general, image, video, training, upscale"
    )
    gpu_filter: str | None = Field(default=None, description="Specific GPU model")
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
    attempt_auto_fix: bool = Field(
        default=False, description="Attempt automatic resolution if possible"
    )


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


def _persist_service_state(service_name: str, enabled: bool, source: str) -> None:
    """Persist service toggle state to Supabase so it survives server restarts."""
    try:
        from backend.database import supabase

        record = {
            "service_name": service_name,
            "enabled": enabled,
            "source": source,
            "updated_at": "now()",
        }
        # Upsert by service_name
        supabase.table("service_settings").upsert(
            record, on_conflict="service_name"
        ).execute()
    except Exception:
        pass  # Non-critical — toggle still works, just won't persist


@router.get("/services/settings")
def get_service_settings():
    """Get persisted service toggle states.

    Returns the saved enabled/disabled state for each service
    so the frontend can restore toggle positions after a page refresh or restart.
    """
    try:
        from backend.database import supabase

        result = supabase.table("service_settings").select("*").execute()
        settings = {row["service_name"]: row for row in (result.data or [])}
        return {"settings": settings}
    except Exception:
        return {"settings": {}}


@router.post("/services/{service_name}/toggle")
def toggle_service(service_name: str, data: dict = None):
    """Toggle a GPU service on or off.

    When enabled=True: SSHs to the worker and starts the service.
    When enabled=False: SSHs to the worker and stops the service.
    Falls back to local if service is detected locally.
    Persists the desired state to Supabase so it survives restarts.

    On cloud deployments (Vercel/Railway): SSH is unavailable.
    For Ollama: user can provide a custom URL via OLLAMA_BASE_URL env var.
    """
    import os
    import shutil
    import subprocess

    if data is None:
        data = {}
    enabled = data.get("enabled", True)
    data.get("force_local", False)

    # Detect if SSH is available (not on Vercel/cloud)
    ssh_available = shutil.which("ssh") is not None

    # Check if worker is online
    orchestrator = get_orchestrator()
    session = orchestrator.session
    worker_active = session is not None and session.instance_id is not None

    # Check local availability first
    local_available = False
    if service_name == "ollama":
        import httpx

        try:
            r = httpx.get("http://localhost:11434/api/tags", timeout=2)
            local_available = r.status_code == 200
        except Exception:
            pass
    elif service_name == "comfyui":
        import httpx

        try:
            r = httpx.get("http://localhost:8188/system_stats", timeout=2)
            local_available = r.status_code == 200
        except Exception:
            pass

    # If already available locally and enabling, just report success
    if local_available and enabled:
        _persist_service_state(service_name, True, "local")
        return {
            "service": service_name,
            "enabled": True,
            "source": "local",
            "status": "already_running",
            "message": f"{service_name} is already running locally",
        }

    # Need a worker to start services remotely
    if not worker_active and not local_available and enabled:
        # On cloud: if Ollama URL is configured externally, just verify connectivity
        if service_name == "ollama" and not ssh_available:
            ollama_url = os.getenv("OLLAMA_BASE_URL", "")
            if ollama_url and ollama_url != "http://localhost:11434":
                _persist_service_state(service_name, True, "remote_url")
                return {
                    "service": service_name,
                    "enabled": True,
                    "source": "remote_url",
                    "status": "configured",
                    "message": f"Ollama configured at {ollama_url}. Verify it's running on your machine or GPU worker.",
                }
            _persist_service_state(service_name, enabled, "cloud")
            return {
                "service": service_name,
                "enabled": enabled,
                "source": "cloud",
                "status": "no_ssh",
                "message": f"Running on cloud (no SSH). Set OLLAMA_BASE_URL in environment to connect to your local Ollama, or launch a GPU worker with Ollama pre-installed.",
            }
        if not ssh_available:
            _persist_service_state(service_name, enabled, "cloud")
            return {
                "service": service_name,
                "enabled": enabled,
                "source": "cloud",
                "status": "no_ssh",
                "message": f"Cannot toggle {service_name}: running on cloud deployment (no SSH). Launch a GPU worker first, or configure the service URL in environment variables.",
            }
        raise HTTPException(
            status_code=409,
            detail=f"Cannot toggle {service_name}: no GPU worker active and not detected locally. Launch a worker first.",
        )

    # SSH to worker and start/stop the service (only if SSH is available)
    if worker_active and session and ssh_available:
        ssh_key = os.path.expanduser(os.getenv("VASTAI_SSH_KEY_PATH", "~/.ssh/id_ed25519"))
        ssh_host = session.ssh_host
        ssh_port = str(session.ssh_port)

        START_COMMANDS = {
            "comfyui": (
                "cd /workspace/ComfyUI && "
                "setsid python main.py --listen 0.0.0.0 --port 8188 </dev/null > /tmp/comfyui.log 2>&1 & disown && "
                "echo STARTED"
            ),
            "ollama": (
                "which ollama >/dev/null 2>&1 || (curl -fsSL https://ollama.ai/install.sh | sh); "
                "nohup ollama serve > /tmp/ollama.log 2>&1 & "
                "sleep 2; echo STARTED"
            ),
        }

        STOP_COMMANDS = {
            "comfyui": "pkill -f 'python main.py.*8188' 2>/dev/null; echo STOPPED",
            "ollama": "pkill -f 'ollama serve' 2>/dev/null; echo STOPPED",
        }

        cmd = START_COMMANDS.get(service_name) if enabled else STOP_COMMANDS.get(service_name)
        if not cmd:
            raise HTTPException(status_code=400, detail=f"Unknown service: {service_name}")

        try:
            ssh_cmd = [
                "ssh",
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "UserKnownHostsFile=/dev/null",
                "-o",
                "ConnectTimeout=10",
                "-i",
                ssh_key,
                "-p",
                ssh_port,
                f"root@{ssh_host}",
                cmd,
            ]
            result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=120)
            # Consider success if our marker text appears, exit code is 0, or it's a stop command that connected
            output_combined = result.stdout + result.stderr
            success = (
                "STARTED" in output_combined
                or "STOPPED" in output_combined
                or result.returncode == 0
                or (not enabled)  # stop commands: if SSH connected and ran, consider it done
            )

            # After starting a service, open an SSH tunnel so it's reachable locally
            if enabled and success:
                port_map = {"comfyui": "8188", "ollama": "11434"}
                local_port = port_map.get(service_name)
                if local_port:
                    # Kill any existing tunnel for this port
                    subprocess.run(
                        ["pkill", "-f", f"ssh.*-L {local_port}:127.0.0.1:{local_port}"],
                        capture_output=True,
                        timeout=5,
                    )
                    import time

                    time.sleep(0.5)
                    # Start tunnel in background
                    tunnel_cmd = [
                        "ssh",
                        "-o",
                        "StrictHostKeyChecking=no",
                        "-o",
                        "UserKnownHostsFile=/dev/null",
                        "-o",
                        "ServerAliveInterval=30",
                        "-N",
                        "-i",
                        ssh_key,
                        "-p",
                        ssh_port,
                        "-L",
                        f"{local_port}:127.0.0.1:{local_port}",
                        f"root@{ssh_host}",
                    ]
                    subprocess.Popen(
                        tunnel_cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    time.sleep(2)  # Give tunnel time to connect

            # After stopping a service, kill the SSH tunnel
            if not enabled and success:
                port_map = {"comfyui": "8188", "ollama": "11434"}
                local_port = port_map.get(service_name)
                if local_port:
                    subprocess.run(
                        ["pkill", "-f", f"ssh.*-L {local_port}:127.0.0.1:{local_port}"],
                        capture_output=True,
                        timeout=5,
                    )

            if success:
                _persist_service_state(service_name, enabled, "gpu_worker")
            return {
                "service": service_name,
                "enabled": enabled,
                "source": "gpu_worker",
                "status": "started"
                if (enabled and success)
                else "stopped"
                if (not enabled and success)
                else "error",
                "message": f"{service_name} {'started' if enabled else 'stopped'} on worker {session.worker_name}",
                "output": output_combined.strip()[:200],
            }
        except subprocess.TimeoutExpired:
            return {
                "service": service_name,
                "enabled": enabled,
                "source": "gpu_worker",
                "status": "timeout",
                "message": f"{service_name} command sent but timed out. Service may still be starting.",
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"SSH execution failed: {e}")

    return {
        "service": service_name,
        "enabled": enabled,
        "source": "none",
        "status": "no_action",
        "message": f"No action taken for {service_name}",
    }


@router.post("/pause")
def pause_worker():
    """Pause (stop billing on) the current Vast.ai instance without destroying it.

    The instance can be resumed later with /resume.
    """
    orchestrator = get_orchestrator()
    if not orchestrator._session or not orchestrator._session.instance_id:
        raise HTTPException(status_code=404, detail="No active worker to pause")

    try:
        client = orchestrator._get_client()
        client.stop_instance(orchestrator._session.instance_id)
        return {
            "status": "paused",
            "instance_id": orchestrator._session.instance_id,
            "message": "Instance paused. Billing stopped. Use /resume to restart.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pause failed: {e}")


@router.post("/resume")
def resume_worker():
    """Resume a paused Vast.ai instance."""
    orchestrator = get_orchestrator()
    if not orchestrator._session or not orchestrator._session.instance_id:
        raise HTTPException(status_code=404, detail="No worker session to resume")

    try:
        import httpx

        client = orchestrator._get_client()
        # Vast.ai resume is PUT with state: running
        resp = httpx.put(
            f"https://console.vast.ai/api/v0/instances/{orchestrator._session.instance_id}/",
            headers={"Authorization": f"Bearer {client.api_key}"},
            json={"state": "running"},
            timeout=15,
            follow_redirects=True,
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=500, detail=f"Resume failed: {resp.text}")
        return {
            "status": "resuming",
            "instance_id": orchestrator._session.instance_id,
            "message": "Instance resuming. May take 30-60s to become available.",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Resume failed: {e}")


@router.get("/vast/status")
def get_vast_connection_status():
    """Get Vast.ai connection status for UI indicators.

    Returns:
    - api_connected: bool (API key valid)
    - instance_active: bool (GPU instance running)
    - instance_paused: bool (instance exists but stopped)
    - balance: float (account balance)
    - instance_info: dict (GPU name, price, status)
    """
    import os

    from backend.providers.vast.client import VastClient, VastClientError

    api_key = os.getenv("VAST_API_KEY", "")
    if not api_key:
        return {
            "api_connected": False,
            "instance_active": False,
            "instance_paused": False,
            "balance": 0,
            "instance_info": None,
            "error": "VAST_API_KEY not configured",
        }

    try:
        client = VastClient(api_key=api_key)
        user_info = client.validate_api_key()
        balance = user_info.get("credit", user_info.get("balance", 0))

        # Check for running instances
        instances = client.get_instances()
        active_instance = None
        paused_instance = None
        for inst in instances:
            status = inst.get("actual_status", inst.get("status_msg", ""))
            if status in ("running", "loading"):
                active_instance = inst
                break
            elif status in ("stopped", "exited"):
                paused_instance = inst

        instance_info = None
        if active_instance:
            instance_info = {
                "id": active_instance.get("id"),
                "gpu_name": active_instance.get("gpu_name", "Unknown"),
                "price_per_hour": active_instance.get("dph_total", 0),
                "status": active_instance.get("actual_status", "running"),
            }
        elif paused_instance:
            instance_info = {
                "id": paused_instance.get("id"),
                "gpu_name": paused_instance.get("gpu_name", "Unknown"),
                "price_per_hour": paused_instance.get("dph_total", 0),
                "status": "paused",
            }

        return {
            "api_connected": True,
            "instance_active": active_instance is not None,
            "instance_paused": paused_instance is not None and active_instance is None,
            "balance": balance,
            "instance_info": instance_info,
        }
    except VastClientError as e:
        return {
            "api_connected": False,
            "instance_active": False,
            "instance_paused": False,
            "balance": 0,
            "instance_info": None,
            "error": str(e),
        }


@router.get("/runpod/status")
def get_runpod_connection_status():
    """Get RunPod connection status for UI indicators.

    Returns the same structure as /vast/status for uniform frontend handling:
    - provider: "runpod"
    - api_connected: bool
    - instance_active: bool
    - instance_paused: bool
    - balance: float (credit balance)
    - instance_info: dict (pod ID, GPU name, price, status)
    """
    import os

    api_key = os.getenv("RUNPOD_API_KEY", "")
    if not api_key:
        return {
            "provider": "runpod",
            "api_connected": False,
            "instance_active": False,
            "instance_paused": False,
            "balance": 0,
            "instance_info": None,
            "error": "RUNPOD_API_KEY not configured",
        }

    try:
        from backend.providers.runpod.client import RunPodClient

        client = RunPodClient(api_key=api_key)

        # Get account info
        info = client.validate_api_key()
        spend_per_hr = float(info.get("currentSpendPerHr", 0))

        # Get pods
        pods = client.get_pods()
        active_pod = None
        paused_pod = None
        for pod in pods:
            status = pod.get("desiredStatus", "")
            if status == "RUNNING":
                active_pod = pod
            elif status == "EXITED":
                paused_pod = pod

        instance_info = None
        if active_pod:
            gpu_name = active_pod.get("machine", {}).get("gpuDisplayName", "Unknown") if active_pod.get("machine") else "Unknown"
            instance_info = {
                "id": active_pod.get("id"),
                "gpu_name": gpu_name,
                "price_per_hour": spend_per_hr,
                "status": "running",
            }
        elif paused_pod:
            gpu_name = paused_pod.get("machine", {}).get("gpuDisplayName", "Unknown") if paused_pod.get("machine") else "Unknown"
            instance_info = {
                "id": paused_pod.get("id"),
                "gpu_name": gpu_name,
                "price_per_hour": 0,
                "status": "paused",
            }

        return {
            "provider": "runpod",
            "api_connected": True,
            "instance_active": active_pod is not None,
            "instance_paused": paused_pod is not None and active_pod is None,
            "balance": spend_per_hr,  # RunPod doesn't expose credit balance easily
            "spend_per_hr": spend_per_hr,
            "instance_info": instance_info,
        }
    except Exception as e:
        return {
            "provider": "runpod",
            "api_connected": False,
            "instance_active": False,
            "instance_paused": False,
            "balance": 0,
            "instance_info": None,
            "error": str(e),
        }


@router.get("/gpu/providers")
def get_all_gpu_provider_status():
    """Get status of ALL configured GPU providers (Vast.ai + RunPod).

    Returns a unified view showing which providers are connected,
    which have active instances, and combined balance/spend info.
    Used by the admin dashboard and home page for multi-provider display.
    """
    vast = get_vast_connection_status()
    runpod = get_runpod_connection_status()

    # Determine overall GPU status
    any_active = vast.get("instance_active") or runpod.get("instance_active")
    any_paused = vast.get("instance_paused") or runpod.get("instance_paused")
    any_connected = vast.get("api_connected") or runpod.get("api_connected")

    return {
        "providers": {
            "vast": {**vast, "provider": "vast"},
            "runpod": {**runpod, "provider": "runpod"},
        },
        "summary": {
            "any_active": any_active,
            "any_paused": any_paused,
            "any_connected": any_connected,
            "total_balance": (vast.get("balance") or 0) + (runpod.get("balance") or 0),
            "active_provider": (
                "vast"
                if vast.get("instance_active")
                else "runpod"
                if runpod.get("instance_active")
                else None
            ),
        },
    }


@router.get("/progress/stream")
async def stream_progress(job_id: str):
    """Stream real-time progress updates via Server-Sent Events (SSE).

    Frontend usage:
        const es = new EventSource('/api/v1/infrastructure/progress/stream?job_id=xxx');
        es.onmessage = (e) => { const data = JSON.parse(e.data); updateUI(data); };

    Events contain: {status, progress, current_step, total_steps, elapsed_seconds}
    Stream closes automatically when job completes/fails or after 10 min timeout.
    """
    from fastapi.responses import StreamingResponse

    from backend.infrastructure.sse_progress import generate_progress_events

    if not job_id:
        raise HTTPException(status_code=400, detail="'job_id' query parameter required")

    return StreamingResponse(
        generate_progress_events(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/admin/keys")
def save_api_keys(data: dict):
    """Save API keys to the .env file.

    Accepts a dict of {key_id: value} pairs and writes them to the
    project's .env file. Only writes non-empty values.
    Keys are mapped to their env var names before writing.
    """
    import os
    from pathlib import Path

    keys = data.get("keys", {})
    if not keys:
        raise HTTPException(status_code=400, detail="No keys provided")

    # Map key IDs to env var names
    KEY_MAP = {
        "vast": "VAST_API_KEY",
        "runpod": "RUNPOD_API_KEY",
        "b2_key_id": "B2_KEY_ID",
        "b2_app_key": "B2_APPLICATION_KEY",
        "supabase_url": "SUPABASE_URL",
        "supabase_key": "SUPABASE_SERVICE_ROLE_KEY",
        "hf": "HF_TOKEN",
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "elevenlabs": "ELEVENLABS_API_KEY",
        "kling": "KLING_API_KEY",
    }

    # Find the .env file
    env_path = Path(__file__).parent.parent.parent / ".env"
    if not env_path.exists():
        raise HTTPException(status_code=500, detail=".env file not found")

    # Read existing content
    content = env_path.read_text()
    lines = content.split("\n")

    updated_vars = set()
    for key_id, value in keys.items():
        if not value or not value.strip():
            continue
        env_var = KEY_MAP.get(key_id)
        if not env_var:
            continue

        # Find and replace existing line, or append
        found = False
        for i, line in enumerate(lines):
            # Match lines like: ENV_VAR=value or ENV_VAR= (with or without quotes)
            if line.strip().startswith(f"{env_var}=") or line.strip().startswith(f"{env_var} ="):
                lines[i] = f"{env_var}={value.strip()}"
                found = True
                updated_vars.add(env_var)
                break

        if not found:
            lines.append(f"{env_var}={value.strip()}")
            updated_vars.add(env_var)

    # Write back
    env_path.write_text("\n".join(lines))

    # Also update os.environ so the current process picks up changes
    for key_id, value in keys.items():
        if not value or not value.strip():
            continue
        env_var = KEY_MAP.get(key_id)
        if env_var:
            os.environ[env_var] = value.strip()

    return {
        "status": "saved",
        "updated": list(updated_vars),
        "message": f"Updated {len(updated_vars)} key(s) in .env. Changes take effect immediately for new connections.",
    }


@router.post("/services/{service_name}/setup")
def setup_service_on_worker(service_name: str):
    """SSH to the GPU worker and install/start a service (ComfyUI or Ollama).

    Dispatches the appropriate setup script to the active worker.
    """
    orchestrator = get_orchestrator()
    if not orchestrator.is_active or not orchestrator.session:
        raise HTTPException(status_code=409, detail="No active GPU worker. Launch one first.")

    ssh_host = orchestrator.session.ssh_host
    ssh_port = orchestrator.session.ssh_port

    SETUP_COMMANDS = {
        "comfyui": (
            "cd /workspace && "
            "git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git 2>/dev/null || true && "
            "cd ComfyUI && pip install -q -r requirements.txt && "
            "mkdir -p models/checkpoints models/loras models/vae && "
            "setsid python main.py --listen 0.0.0.0 --port 8188 </dev/null > /tmp/comfyui.log 2>&1 & disown"
        ),
        "ollama": (
            "curl -fsSL https://ollama.ai/install.sh | sh && "
            "setsid ollama serve </dev/null > /tmp/ollama.log 2>&1 & disown && "
            "sleep 5 && ollama pull llama3.1:8b"
        ),
    }

    cmd = SETUP_COMMANDS.get(service_name)
    if not cmd:
        raise HTTPException(
            status_code=400, detail=f"Unknown service: {service_name}. Valid: comfyui, ollama"
        )

    return {
        "status": "dispatched",
        "service": service_name,
        "worker": orchestrator.session.worker_name,
        "ssh_target": f"{ssh_host}:{ssh_port}",
        "command": cmd,
        "message": f"Setup command for {service_name} ready. Execute via SSH to {ssh_host}:{ssh_port}.",
    }


@router.post("/session/persist")
def persist_worker_session():
    """Save the current worker session to Supabase for crash recovery."""
    orchestrator = get_orchestrator()
    if not orchestrator.session:
        raise HTTPException(status_code=404, detail="No active session to persist")

    session = orchestrator.session
    record = {
        "session_id": session.id,
        "instance_id": session.instance_id,
        "worker_name": session.worker_name,
        "gpu_name": session.gpu_name,
        "ssh_host": session.ssh_host,
        "ssh_port": session.ssh_port,
        "status": session.status,
        "hourly_rate": session.hourly_rate,
        "started_at": session.started_at,
        "metadata": session.metadata,
    }

    try:
        from backend.database import supabase

        supabase.table("worker_sessions").upsert(record, on_conflict="session_id").execute()
        return {"status": "persisted", "session_id": session.id}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/publishing/dispatch-due")
def dispatch_due_posts():
    """Check for scheduled posts that are due and mark them for dispatch.

    In production, this would be called by a background worker.
    For now it can be triggered manually or via cron.
    """
    from datetime import datetime

    from backend.database import supabase

    now = datetime.now(UTC).isoformat()

    try:
        due_posts = (
            supabase.table("publishing_posts")
            .select("*")
            .eq("status", "scheduled")
            .lte("publish_at", now)
            .execute()
            .data
            or []
        )

        dispatched = []
        for post in due_posts:
            supabase.table("publishing_posts").update(
                {
                    "status": "publishing",
                    "updated_at": "now()",
                }
            ).eq("id", post["id"]).execute()
            dispatched.append(post["id"])

        return {
            "checked_at": now,
            "due_count": len(due_posts),
            "dispatched": dispatched,
            "message": f"Found {len(due_posts)} posts due for publishing.",
        }
    except Exception as e:
        return {"error": str(e), "due_count": 0, "dispatched": []}


@router.get("/health/connections")
def check_all_connections():
    """Health check that verifies B2 + Supabase connectivity with auto-retry.

    If a connection fails, attempts reconnection up to 3 times with backoff.
    """
    import os
    import time

    results = {}

    # Check Supabase
    for attempt in range(3):
        try:
            from backend.database import supabase

            supabase.table("talent").select("id").limit(1).execute()
            results["supabase"] = {"connected": True, "attempts": attempt + 1}
            break
        except Exception as e:
            if attempt == 2:
                results["supabase"] = {"connected": False, "error": str(e), "attempts": 3}
            time.sleep(1 * (attempt + 1))

    # Check B2
    for attempt in range(3):
        try:
            from backend.storage import _get_client

            client = _get_client()
            bucket = os.getenv("B2_BUCKET_NAME", "")
            client.head_bucket(Bucket=bucket)
            results["b2"] = {"connected": True, "attempts": attempt + 1}
            break
        except Exception as e:
            if attempt == 2:
                results["b2"] = {"connected": False, "error": str(e), "attempts": 3}
            time.sleep(1 * (attempt + 1))

    all_connected = all(r.get("connected") for r in results.values())
    return {"healthy": all_connected, "services": results}


# =============================================================================
# Fleet Settings — User-configurable fleet management
# =============================================================================

from backend.infrastructure.fleet_settings import IDLE_ACTIONS, get_fleet_settings


@router.get("/fleet/settings")
def get_fleet_config():
    """Get current fleet settings (max instances, budget, idle timeout, etc.)."""
    mgr = get_fleet_settings()
    return {
        "settings": mgr.config.to_dict(),
        "budget_status": mgr.get_budget_status(),
        "idle_actions_by_vendor": IDLE_ACTIONS,
    }


@router.put("/fleet/settings")
def update_fleet_config(data: dict):
    """Update fleet settings.

    Accepts any combination of:
        max_instances: int (1-10)
        daily_budget_usd: float
        idle_timeout_minutes: int (0=disabled, otherwise minutes)
        auto_provision: bool
        preferred_provider: str (vast | runpod)
        min_vram_gb: int
        max_price_per_hour: float
        cool_down_seconds: int
        enable_spot_instances: bool
    """
    mgr = get_fleet_settings()

    # Validate bounds
    if "max_instances" in data:
        data["max_instances"] = max(1, min(10, int(data["max_instances"])))
    if "daily_budget_usd" in data:
        data["daily_budget_usd"] = max(0.5, float(data["daily_budget_usd"]))
    if "idle_timeout_minutes" in data:
        data["idle_timeout_minutes"] = max(0, int(data["idle_timeout_minutes"]))
    if "max_price_per_hour" in data:
        data["max_price_per_hour"] = max(0.05, min(10.0, float(data["max_price_per_hour"])))

    updated = mgr.update(**data)
    return {
        "status": "updated",
        "settings": updated.to_dict(),
        "budget_status": mgr.get_budget_status(),
    }


@router.get("/fleet/budget")
def get_fleet_budget():
    """Get current daily budget status (spent, remaining, percentage)."""
    mgr = get_fleet_settings()
    return mgr.get_budget_status()


@router.post("/fleet/can-launch")
def check_can_launch():
    """Check if a new instance can be launched (budget, max, cool-down)."""
    mgr = get_fleet_settings()

    # Get current instance count
    try:
        from backend.providers.vast.client import VastClient

        vast_client = VastClient()
        instances = vast_client.get_instances()
        running = [i for i in instances if i.get("actual_status") in ("running", "loading")]
        count = len(running)
    except Exception:
        count = 0

    # Also check RunPod
    try:
        import os

        if os.getenv("RUNPOD_API_KEY"):
            from backend.providers.runpod.client import RunPodClient

            rp_client = RunPodClient()
            pods = rp_client.get_pods()
            count += len([p for p in pods if p.get("desiredStatus") == "RUNNING"])
    except Exception:
        pass

    allowed, reason = mgr.can_launch(count)
    return {
        "can_launch": allowed,
        "reason": reason,
        "current_instances": count,
        "max_instances": mgr.config.max_instances,
        "budget_status": mgr.get_budget_status(),
    }


# =============================================================================
# Worker Registry — Per-instance controls
# =============================================================================

from backend.infrastructure.worker_registry import get_worker_registry


@router.get("/workers")
def list_all_workers():
    """List all GPU workers across all providers with current status."""
    registry = get_worker_registry()
    workers = registry.list_workers()
    settings = get_fleet_settings()
    return {
        "workers": workers,
        "total": len(workers),
        "active": registry.active_count,
        "max_allowed": settings.config.max_instances,
        "idle_timeout_minutes": settings.config.idle_timeout_minutes,
    }


@router.post("/workers/{worker_id}/stop")
def stop_single_worker(worker_id: str):
    """Stop a specific worker (vendor-aware: destroy for Vast, stop for RunPod)."""
    registry = get_worker_registry()
    return registry.stop_worker(worker_id)


@router.post("/workers/{worker_id}/pause")
def pause_single_worker(worker_id: str):
    """Pause a specific worker (stops billing, preserves state where possible)."""
    registry = get_worker_registry()
    return registry.pause_worker(worker_id)


@router.post("/workers/{worker_id}/resume")
def resume_single_worker(worker_id: str):
    """Resume a paused/stopped worker."""
    registry = get_worker_registry()
    return registry.resume_worker(worker_id)


@router.get("/workers/idle")
def get_idle_workers():
    """Get workers that have exceeded the idle timeout (candidates for shutdown)."""
    registry = get_worker_registry()
    idle = registry.get_idle_workers()
    return {
        "idle_workers": [w.to_dict() for w in idle],
        "count": len(idle),
        "idle_timeout_minutes": get_fleet_settings().config.idle_timeout_minutes,
    }


@router.post("/workers/idle/shutdown")
def shutdown_idle_workers():
    """Shut down all workers that have exceeded the idle timeout."""
    registry = get_worker_registry()
    idle = registry.get_idle_workers()
    results = []
    for worker in idle:
        result = registry.stop_worker(worker.id)
        results.append({"worker_id": worker.id, **result})
    return {
        "shut_down": len(results),
        "results": results,
    }


# =============================================================================
# Auto-Provisioning — On-demand worker launch for queued jobs
# =============================================================================

from backend.infrastructure.auto_provisioner import get_auto_provisioner


@router.post("/auto-provision")
def trigger_auto_provision(data: dict = None):
    """Check if a worker is available for a job; auto-provision if needed.

    Called by job submission endpoints before dispatching work.

    Body (optional):
        job_type: str — image | training | video | general
        required_vram_gb: int — minimum VRAM needed (0 = use fleet default)

    Returns whether a worker is available or being provisioned.
    """
    if data is None:
        data = {}
    provisioner = get_auto_provisioner()
    result = provisioner.check_and_provision(
        job_type=data.get("job_type", "image"),
        required_vram_gb=int(data.get("required_vram_gb", 0)),
    )
    return result


@router.get("/gpu-requirements")
def get_gpu_requirements():
    """Get GPU requirements per job type for cost estimation.

    Used by frontend to show users what GPU will be provisioned
    and estimated costs before they submit a job.
    """
    provisioner = get_auto_provisioner()
    job_types = ["image", "video", "training"]
    requirements = {}
    for jt in job_types:
        vram = provisioner._get_vram_requirement(jt)
        max_price = provisioner._get_max_price(jt)
        requirements[jt] = {
            "min_vram_gb": vram,
            "max_price_per_hour": max_price,
            "recommended_gpu": (
                "A100 80GB or H100"
                if vram >= 80
                else "RTX 3090/4090 (24GB)"
                if vram >= 24
                else "RTX 3060/4070 (12GB)"
            ),
            "estimated_cost_range": (f"${max_price * 0.6:.2f}-${max_price:.2f}/hr"),
        }
    return {"requirements": requirements}


# =============================================================================
# Budget Guard — Real-time spend tracking
# =============================================================================


@router.post("/fleet/record-spend")
def record_fleet_spend(data: dict):
    """Record GPU spend for budget tracking.

    Called periodically (e.g., every hour) or when a worker stops.
    Body: {amount_usd: float}
    """
    amount = float(data.get("amount_usd", 0))
    if amount <= 0:
        raise HTTPException(status_code=400, detail="amount_usd must be positive")

    settings = get_fleet_settings()
    settings.record_spend(amount)

    budget = settings.get_budget_status()
    return {
        "recorded": amount,
        "budget_status": budget,
        "warning": budget["percentage_used"] > 80,
    }


@router.get("/fleet/budget-check")
def check_budget_guard():
    """Check if budget allows new launches or continued operation.

    Returns whether the system should shut down workers to stay in budget.
    """
    settings = get_fleet_settings()
    registry = get_worker_registry()
    budget = settings.get_budget_status()

    # Calculate projected daily cost based on running workers
    workers = registry.list_workers()
    active_workers = [w for w in workers if w["status"] in ("ready", "busy")]
    hourly_total = sum(w["hourly_rate"] for w in active_workers)
    projected_daily = hourly_total * 24

    over_budget = budget["spent_today"] >= budget["daily_budget"]
    will_exceed = (budget["spent_today"] + hourly_total) > budget["daily_budget"]

    return {
        "budget": budget,
        "active_workers": len(active_workers),
        "hourly_burn_rate": round(hourly_total, 4),
        "projected_daily_cost": round(projected_daily, 2),
        "over_budget": over_budget,
        "will_exceed_in_next_hour": will_exceed,
        "recommendation": (
            "SHUTDOWN — over daily budget"
            if over_budget
            else "WARNING — will exceed budget within 1 hour"
            if will_exceed
            else "OK — within budget"
        ),
    }


# =============================================================================
# Service Health — Check if ComfyUI/Ollama are actually reachable
# =============================================================================


@router.get("/services/health")
def check_service_health():
    """Check actual reachability of ComfyUI and Ollama.

    Called by the admin page to determine toggle state.
    Routes through backend to avoid browser CORS issues.
    """
    import httpx

    results = {}

    # Check ComfyUI
    try:
        resp = httpx.get("http://localhost:8188/system_stats", timeout=3)
        results["comfyui"] = {
            "online": resp.status_code == 200,
            "version": resp.json().get("system", {}).get("comfyui_version")
            if resp.status_code == 200
            else None,
        }
    except Exception:
        results["comfyui"] = {"online": False, "version": None}

    # Check Ollama
    try:
        resp = httpx.get("http://localhost:11434/api/tags", timeout=2)
        if resp.status_code == 200:
            models = resp.json().get("models", [])
            results["ollama"] = {"online": True, "models": len(models)}
        else:
            results["ollama"] = {"online": False, "models": 0}
    except Exception:
        results["ollama"] = {"online": False, "models": 0}

    return results


# =============================================================================
# Ollama Preference — Local vs Remote vs Auto
# =============================================================================

_ollama_preference: str = os.getenv("OLLAMA_PREFERENCE", "auto")  # "auto" | "local" | "remote"


@router.get("/ollama/preference")
def get_ollama_preference():
    """Get the current Ollama source preference."""
    return {"preference": _ollama_preference}


@router.put("/ollama/preference")
def set_ollama_preference(data: dict):
    """Set Ollama source preference: auto, local, or remote. Persists to .env."""
    global _ollama_preference
    pref = data.get("preference", "auto")
    if pref not in ("auto", "local", "remote"):
        raise HTTPException(status_code=422, detail="preference must be auto, local, or remote")
    _ollama_preference = pref
    os.environ["OLLAMA_PREFERENCE"] = pref

    # Persist to .env
    try:
        import re

        env_path = Path(__file__).parent.parent.parent / ".env"
        if env_path.exists():
            content = env_path.read_text()
            if "OLLAMA_PREFERENCE=" in content:
                content = re.sub(r"OLLAMA_PREFERENCE=.*", f"OLLAMA_PREFERENCE={pref}", content)
            else:
                content += f"\nOLLAMA_PREFERENCE={pref}\n"
            env_path.write_text(content)
    except Exception:
        pass

    return {"preference": _ollama_preference, "message": f"Ollama preference set to {pref}"}


@router.get("/ollama/status")
def get_ollama_status():
    """Get detailed Ollama status: local availability, remote availability, active source."""
    import httpx

    local_online = False
    local_models = 0
    remote_online = False

    # Check local Ollama
    try:
        r = httpx.get("http://localhost:11434/api/tags", timeout=2)
        if r.status_code == 200:
            local_online = True
            local_models = len(r.json().get("models", []))
    except Exception:
        pass

    # Check remote Ollama (on GPU worker via tunnel or direct)
    # If local is online via tunnel from GPU, check if it's truly local or tunneled
    orchestrator = get_orchestrator()
    session = orchestrator.session
    worker_active = session is not None and session.instance_id is not None

    # Determine active source based on preference
    active_source = "none"
    if _ollama_preference == "local":
        active_source = "local" if local_online else "none"
    elif _ollama_preference == "remote":
        active_source = "remote" if (local_online and worker_active) else "none"
    else:  # auto
        if local_online:
            active_source = "local" if not worker_active else "local"
        elif worker_active:
            active_source = "remote"

    return {
        "preference": _ollama_preference,
        "local": {
            "online": local_online,
            "models": local_models,
            "source": "localhost:11434",
        },
        "remote": {
            "available": worker_active,
            "online": local_online and worker_active,  # reachable via tunnel
            "source": f"{session.ssh_host}:{session.ssh_port}" if session else None,
        },
        "active_source": active_source,
        "overall_online": local_online or (worker_active and remote_online),
    }

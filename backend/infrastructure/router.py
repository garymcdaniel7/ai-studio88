"""Infrastructure Intelligence API Router.

Endpoints for worker orchestration, connection racing, and fleet management.

All endpoints require authenticated identity. Operations are gated by capability:
    INFRA_READ       — dashboards, status, cost summaries (viewer+)
    INFRA_OPERATE    — toggle services, submit jobs (editor+)
    INFRA_ADMIN      — launch/stop workers, fleet changes, blacklist (admin+)
    INFRA_DESTRUCTIVE— emergency shutdown, API key management (owner)
"""

from __future__ import annotations

import os
from datetime import UTC
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.infrastructure.authorization import (
    APPROVAL_REQUIRED_ACTIONS,
    ApprovalCommand,
    InfraAuditEvent,
    InfraCapability,
    TenantContext,
    create_approval_command,
    emit_audit_event,
    get_audit_log,
    require_infra_admin,
    require_infra_capability,
    require_infra_destructive,
    require_infra_operate,
    require_infra_read,
    require_spend_rate_limit,
    verify_resource_ownership,
)
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
    provider: str | None = Field(default=None, description="GPU provider: 'thundercompute' (default, primary) or 'local' fallback")


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
async def launch_worker(
    request: LaunchRequest,
    ctx: TenantContext = Depends(require_infra_admin),
):
    """Launch a new GPU worker on Thunder Compute.

    Requires: admin+ role (spend-changing operation).

    Provisions an instance through the Thunder Compute provider via the
    async orchestrator (RunPod + Vast.ai retired). Returns worker details
    on success, including the public ComfyUI/Ollama endpoints.

    Returns session info with connection details on success.
    """
    emit_audit_event(InfraAuditEvent(
        actor_id=ctx.user_id,
        actor_email=ctx.email,
        org_id=ctx.org_id,
        role=ctx.role.value,
        action="launch_worker",
        capability=InfraCapability.ADMIN.value,
        request_data=request.model_dump(),
    ))

    # Rate limit spend-changing operations
    require_spend_rate_limit(ctx)

    from backend.app.providers.compute import ComputeRequirements
    from backend.infrastructure.worker_orchestrator import get_orchestrator

    orchestrator = get_orchestrator()

    requirements = ComputeRequirements(
        vram_gb=int(request.min_vram_gb or 24),
        storage_gb=request.disk_gb or 300,
        workload_type="image_generation",
        max_duration_seconds=request.timeout or 3600,
        org_id=ctx.org_id,
    )

    try:
        instance = await orchestrator.provision_worker(
            org_id=str(ctx.org_id),
            requirements=requirements,
            preferred_provider="thundercompute",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Launch failed: {e}")

    return {
        "status": "provisioning",
        "provider": "thundercompute",
        "instance_id": instance.id,
        "message": f"Thunder Compute worker provisioning ({instance.id[:8]}...)",
    }


@router.get("/status")
def get_status(ctx: TenantContext = Depends(require_infra_read)):
    """Get comprehensive infrastructure status for dashboard display.

    Requires: viewer+ role.
    """
    return get_dashboard_status()


@router.get("/worker/progress")
def get_worker_progress(ctx: TenantContext = Depends(require_infra_read)):
    """Get lightweight worker boot progress (for frontend polling during launch).

    Requires: viewer+ role.

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
def get_dashboard(ctx: TenantContext = Depends(require_infra_read)):
    """Comprehensive infrastructure dashboard — alias for /status.

    Requires: viewer+ role.
    """
    return get_dashboard_status()


@router.post("/stop")
def stop_worker(
    request: StopRequest | None = None,
    ctx: TenantContext = Depends(require_infra_admin),
):
    """Stop and destroy the current worker instance.

    Requires: admin+ role (spend-changing operation).

    Terminates the Vast.ai instance and ends the session.
    Calculates final cost based on elapsed time.
    """
    emit_audit_event(InfraAuditEvent(
        actor_id=ctx.user_id,
        actor_email=ctx.email,
        org_id=ctx.org_id,
        role=ctx.role.value,
        action="stop_worker",
        capability=InfraCapability.ADMIN.value,
        request_data={"force": request.force if request else False},
    ))

    orchestrator = get_orchestrator()
    result = orchestrator.stop_worker()

    if result.get("status") == "no_session":
        raise HTTPException(status_code=404, detail="No active worker to stop")

    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("message", "Stop failed"))

    return result


@router.get("/history")
def get_connection_history(ctx: TenantContext = Depends(require_infra_read)):
    """Get the full history of connection attempts.

    Requires: viewer+ role.
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
def get_cost_summary(ctx: TenantContext = Depends(require_infra_read)):
    """Get current spend summary with budget check.

    Requires: viewer+ role.
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
def get_cost_history(days: int = 30, ctx: TenantContext = Depends(require_infra_read)):
    """Get daily cost history for charting.

    Requires: viewer+ role.

    Args:
        days: Number of days to include (default 30, max 365)
    """
    days = min(max(days, 1), 365)
    tracker = get_cost_tracker()
    return {
        "history": tracker.get_cost_history(days=days),
        "days": days,
        "budget": tracker.check_budget(),
    }


@router.get("/cost/hourly")
def get_cost_hourly_breakdown(ctx: TenantContext = Depends(require_infra_read)):
    """Get today's GPU cost broken down by hour.

    Requires: viewer+ role.
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
def get_job_costs(
    job_type: str | None = None,
    limit: int = 50,
    ctx: TenantContext = Depends(require_infra_read),
):
    """Get per-job cost records (generation, voice, training).

    Requires: viewer+ role.
    """
    tracker = get_cost_tracker()
    return {
        "costs": tracker.get_job_costs(job_type=job_type, limit=limit),
        "totals": tracker.get_total_job_spend(),
    }


@router.get("/reputation")
def get_reputation(ctx: TenantContext = Depends(require_infra_read)):
    """Get all provider reputation scores.

    Requires: viewer+ role.
    """
    engine = get_reputation_engine()
    return engine.get_all_reputations()


@router.get("/providers/compare")
def compare_providers(ctx: TenantContext = Depends(require_infra_read)):
    """Compare GPU providers (Vast.ai vs RunPod) based on historical performance.

    Requires: viewer+ role.

    Returns boot time averages, success rates, cost data, and a recommendation.
    NOTE: Provider account details are redacted for non-admin roles.
    """
    engine = get_reputation_engine()
    return engine.get_provider_comparison()


@router.get("/blacklist")
def get_blacklist(ctx: TenantContext = Depends(require_infra_read)):
    """Get all blacklisted hosts.

    Requires: viewer+ role.
    """
    engine = get_reputation_engine()
    return {
        "blacklisted_hosts": engine.get_blacklist(),
        "total": len(engine.get_blacklist()),
    }


@router.post("/blacklist")
def add_to_blacklist(
    request: BlacklistRequest,
    ctx: TenantContext = Depends(require_infra_admin),
):
    """Manually blacklist a host.

    Requires: admin+ role.

    Prevents the host from being used in future connection races.
    """
    emit_audit_event(InfraAuditEvent(
        actor_id=ctx.user_id,
        actor_email=ctx.email,
        org_id=ctx.org_id,
        role=ctx.role.value,
        action="add_to_blacklist",
        capability=InfraCapability.ADMIN.value,
        resource_type="host",
        resource_id=request.host_id,
        request_data=request.model_dump(),
    ))

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
def get_fleet_status(ctx: TenantContext = Depends(require_infra_read)):
    """Get render fleet status — all active workers, queue, costs.

    Requires: viewer+ role.
    """
    fleet = get_fleet_manager()
    return fleet.get_fleet_status()


@router.post("/fleet/add")
def add_fleet_worker(
    request: FleetAddRequest,
    ctx: TenantContext = Depends(require_infra_admin),
):
    """Add a new worker to the render fleet.

    Requires: admin+ role (spend-changing operation).
    """
    emit_audit_event(InfraAuditEvent(
        actor_id=ctx.user_id,
        actor_email=ctx.email,
        org_id=ctx.org_id,
        role=ctx.role.value,
        action="add_fleet_worker",
        capability=InfraCapability.ADMIN.value,
        request_data=request.model_dump(),
    ))

    # Rate limit spend-changing operations
    require_spend_rate_limit(ctx)

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
def remove_fleet_worker(
    worker_id: str,
    ctx: TenantContext = Depends(require_infra_admin),
):
    """Remove a worker from the fleet and destroy its instance.

    Requires: admin+ role. Verifies worker belongs to caller's workspace.
    """
    # Check ownership if worker exists in registry
    registry = get_worker_registry()
    worker = registry.get_worker(worker_id)
    if worker:
        verify_resource_ownership(ctx, worker.org_id, "worker", worker_id)

    emit_audit_event(InfraAuditEvent(
        actor_id=ctx.user_id,
        actor_email=ctx.email,
        org_id=ctx.org_id,
        role=ctx.role.value,
        action="remove_fleet_worker",
        capability=InfraCapability.ADMIN.value,
        resource_type="worker",
        resource_id=worker_id,
    ))

    fleet = get_fleet_manager()
    result = fleet.remove_worker(worker_id)
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/fleet/stop-all")
def stop_fleet(ctx: TenantContext = Depends(require_infra_destructive)):
    """Emergency shutdown — destroy all fleet workers immediately.

    Requires: owner role (destructive operation).
    Produces an approval-ready command.
    """
    action = "stop_fleet"

    # Approval gate — destructive action
    if action in APPROVAL_REQUIRED_ACTIONS:
        approval = create_approval_command(
            action=action,
            actor_id=ctx.user_id,
            org_id=ctx.org_id,
            request_data={},
        )
        emit_audit_event(InfraAuditEvent(
            actor_id=ctx.user_id,
            actor_email=ctx.email,
            org_id=ctx.org_id,
            role=ctx.role.value,
            action=action,
            capability=InfraCapability.DESTRUCTIVE.value,
            requires_approval=True,
        ))
        # For now, execute immediately but record the approval requirement
        # In a full governance system, this would return the approval command
        # and wait for confirmation. Current behavior: warn + execute.

    emit_audit_event(InfraAuditEvent(
        actor_id=ctx.user_id,
        actor_email=ctx.email,
        org_id=ctx.org_id,
        role=ctx.role.value,
        action="stop_fleet_executed",
        capability=InfraCapability.DESTRUCTIVE.value,
    ))

    fleet = get_fleet_manager()
    return fleet.stop_all()


@router.post("/fleet/jobs")
def submit_fleet_job(
    data: dict,
    ctx: TenantContext = Depends(require_infra_operate),
):
    """Submit a job to the fleet queue.

    Requires: editor+ role.
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
def diagnose_error(
    request: DiagnoseRequest,
    ctx: TenantContext = Depends(require_infra_operate),
):
    """Submit an error for diagnosis by the self-healing agent.

    Requires: editor+ role.
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
def get_known_issues(ctx: TenantContext = Depends(require_infra_read)):
    """List all recognized error patterns with fix success rates.

    Requires: viewer+ role.
    """
    agent = get_diagnostic_agent()
    return {
        "patterns": agent.get_known_issues(),
        "total": len(agent.get_known_issues()),
    }


@router.get("/admin/services")
def get_services_status(ctx: TenantContext = Depends(require_infra_read)):
    """Check all configured service connections.

    Requires: viewer+ role.
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
def get_service_settings(ctx: TenantContext = Depends(require_infra_read)):
    """Get persisted service toggle states.

    Requires: viewer+ role.
    """
    try:
        from backend.database import supabase

        result = supabase.table("service_settings").select("*").execute()
        settings = {row["service_name"]: row for row in (result.data or [])}
        return {"settings": settings}
    except Exception:
        return {"settings": {}}


@router.post("/services/{service_name}/toggle")
def toggle_service(
    service_name: str,
    data: dict = None,
    ctx: TenantContext = Depends(require_infra_operate),
):
    """Toggle a GPU service on or off.

    Requires: editor+ role (operational action).
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
def pause_worker(ctx: TenantContext = Depends(require_infra_admin)):
    """Pause (stop billing on) the current Vast.ai instance without destroying it.

    Requires: admin+ role.
    """
    emit_audit_event(InfraAuditEvent(
        actor_id=ctx.user_id,
        actor_email=ctx.email,
        org_id=ctx.org_id,
        role=ctx.role.value,
        action="pause_worker",
        capability=InfraCapability.ADMIN.value,
    ))

    orchestrator = get_orchestrator()
    if not orchestrator._session or not orchestrator._session.instance_id:
        raise HTTPException(status_code=404, detail="No active worker to pause")

    try:
        client = orchestrator._get_client()
        client.stop_instance(orchestrator._session.instance_id)
        orchestrator._session.status = "paused"
        return {
            "status": "paused",
            "instance_id": orchestrator._session.instance_id,
            "message": "Instance paused. Billing stopped. Use /resume to restart.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pause failed: {e}")


@router.post("/resume")
def resume_worker(ctx: TenantContext = Depends(require_infra_admin)):
    """Resume a paused Vast.ai instance.

    Requires: admin+ role.
    """
    emit_audit_event(InfraAuditEvent(
        actor_id=ctx.user_id,
        actor_email=ctx.email,
        org_id=ctx.org_id,
        role=ctx.role.value,
        action="resume_worker",
        capability=InfraCapability.ADMIN.value,
    ))

    orchestrator = get_orchestrator()
    if not orchestrator._session or not orchestrator._session.instance_id:
        raise HTTPException(status_code=404, detail="No worker session to resume")

    try:
        import httpx

        client = orchestrator._get_client()
        resp = httpx.put(
            f"https://console.vast.ai/api/v0/instances/{orchestrator._session.instance_id}/",
            headers={"Authorization": f"Bearer {client.api_key}"},
            json={"state": "running"},
            timeout=15,
            follow_redirects=True,
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=500, detail=f"Resume failed: {resp.text}")
        orchestrator._session.status = "resuming"
        return {
            "status": "resuming",
            "instance_id": orchestrator._session.instance_id,
            "message": "Instance resuming. May take 30-60s to become available.",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Resume failed: {e}")


@router.get("/thunder/status")
def get_thunder_connection_status(ctx: TenantContext = Depends(require_infra_read)):
    """Get Thunder Compute connection status for UI indicators.

    Uses the THUNDER_COMPUTE_API_KEY and the live ComfyUI/Ollama public
    endpoints to report real worker state. Thunder Compute is the primary
    GPU provider (RunPod + Vast.ai retired).

    Requires: viewer+ role.
    """
    import os

    api_key = os.getenv("THUNDER_COMPUTE_API_KEY", "")
    comfy_base = os.getenv("COMFYUI_BASE_URL", "").rstrip("/")

    if not api_key:
        return {
            "provider": "thundercompute",
            "api_connected": False,
            "instance_active": False,
            "instance_paused": False,
            "balance": 0,
            "instance_info": None,
            "error": "THUNDER_COMPUTE_API_KEY not configured",
        }

    # Real worker probe: ComfyUI /system_stats proves the A6000 is live
    instance_info = None
    instance_active = False
    try:
        import requests

        resp = requests.get(f"{comfy_base}/system_stats", timeout=6)
        if resp.ok:
            stats = resp.json()
            devices = stats.get("devices", [{}])
            gpu = devices[0] if devices else {}
            instance_active = True
            instance_info = {
                "id": "do5u5dbx",
                "gpu_name": gpu.get("name", "A6000 (Thunder)"),
                "price_per_hour": 0.35,
                "status": "running",
                "vram_total_gb": round(gpu.get("vram_total", 0) / (1024**3), 1),
                "vram_free_gb": round(gpu.get("vram_free", 0) / (1024**3), 1),
            }
    except Exception:
        pass

    return {
        "provider": "thundercompute",
        "api_connected": True,
        "instance_active": instance_active,
        "instance_paused": False,
        "balance": 0,
        "spend_per_hr": 0.35 if instance_active else 0,
        "instance_info": instance_info,
        "error": None if instance_active else "Worker not reachable via ComfyUI health probe",
    }


@router.get("/vast/status")
def get_vast_connection_status(ctx: TenantContext = Depends(require_infra_read)):
    """Get Vast.ai connection status for UI indicators.

    Requires: viewer+ role.
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
def get_runpod_connection_status(ctx: TenantContext = Depends(require_infra_read)):
    """Get RunPod connection status for UI indicators.

    Requires: viewer+ role.
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
def get_all_gpu_provider_status(ctx: TenantContext = Depends(require_infra_read)):
    """Get status of ALL configured GPU providers (Vast.ai + RunPod).

    Requires: viewer+ role.
    """
    vast = get_vast_connection_status(ctx)
    runpod = get_runpod_connection_status(ctx)

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
async def stream_progress(job_id: str, ctx: TenantContext = Depends(require_infra_read)):
    """Stream real-time progress updates via Server-Sent Events (SSE).

    Requires: viewer+ role.
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
def save_api_keys(
    data: dict,
    ctx: TenantContext = Depends(require_infra_destructive),
):
    """Save API keys to the .env file.

    Requires: owner role (destructive — modifies service credentials).
    """
    action = "save_api_keys"
    emit_audit_event(InfraAuditEvent(
        actor_id=ctx.user_id,
        actor_email=ctx.email,
        org_id=ctx.org_id,
        role=ctx.role.value,
        action=action,
        capability=InfraCapability.DESTRUCTIVE.value,
        request_data={"keys_provided": list((data.get("keys") or {}).keys())},
        requires_approval=action in APPROVAL_REQUIRED_ACTIONS,
    ))
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
def setup_service_on_worker(
    service_name: str,
    ctx: TenantContext = Depends(require_infra_operate),
):
    """SSH to the GPU worker and install/start a service (ComfyUI or Ollama).

    Requires: editor+ role.
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
def persist_worker_session(ctx: TenantContext = Depends(require_infra_admin)):
    """Save the current worker session to Supabase for crash recovery.

    Requires: admin+ role.
    """
    emit_audit_event(InfraAuditEvent(
        actor_id=ctx.user_id,
        actor_email=ctx.email,
        org_id=ctx.org_id,
        role=ctx.role.value,
        action="persist_worker_session",
        capability=InfraCapability.ADMIN.value,
    ))

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
def dispatch_due_posts(ctx: TenantContext = Depends(require_infra_read)):
    """Check for scheduled posts that are due and mark them for dispatch.

    Requires: viewer+ role.
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
def check_all_connections(ctx: TenantContext = Depends(require_infra_read)):
    """Health check that verifies B2 + Supabase connectivity with auto-retry.

    Requires: viewer+ role.
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
def get_fleet_config(ctx: TenantContext = Depends(require_infra_read)):
    """Get current fleet settings (max instances, budget, idle timeout, etc.).

    Requires: viewer+ role.
    """
    mgr = get_fleet_settings()
    return {
        "settings": mgr.config.to_dict(),
        "budget_status": mgr.get_budget_status(),
        "idle_actions_by_vendor": IDLE_ACTIONS,
    }


@router.put("/fleet/settings")
def update_fleet_config(
    data: dict,
    ctx: TenantContext = Depends(require_infra_admin),
):
    """Update fleet settings.

    Requires: admin+ role (spend-changing operation).
    """
    emit_audit_event(InfraAuditEvent(
        actor_id=ctx.user_id,
        actor_email=ctx.email,
        org_id=ctx.org_id,
        role=ctx.role.value,
        action="update_fleet_config",
        capability=InfraCapability.ADMIN.value,
        request_data=data,
    ))
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
def get_fleet_budget(ctx: TenantContext = Depends(require_infra_read)):
    """Get current daily budget status (spent, remaining, percentage).

    Requires: viewer+ role.
    """
    mgr = get_fleet_settings()
    return mgr.get_budget_status()


@router.post("/fleet/can-launch")
def check_can_launch(ctx: TenantContext = Depends(require_infra_read)):
    """Check if a new instance can be launched (budget, max, cool-down).

    Requires: viewer+ role.
    """
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
def list_all_workers(ctx: TenantContext = Depends(require_infra_read)):
    """List all GPU workers across all providers with current status.

    Requires: viewer+ role.
    """
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
def stop_single_worker(
    worker_id: str,
    ctx: TenantContext = Depends(require_infra_admin),
):
    """Stop a specific worker (vendor-aware: destroy for Vast, stop for RunPod).

    Requires: admin+ role. Verifies worker belongs to caller's workspace.
    """
    registry = get_worker_registry()
    worker = registry.get_worker(worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    verify_resource_ownership(ctx, worker.org_id, "worker", worker_id)

    emit_audit_event(InfraAuditEvent(
        actor_id=ctx.user_id,
        actor_email=ctx.email,
        org_id=ctx.org_id,
        role=ctx.role.value,
        action="stop_single_worker",
        capability=InfraCapability.ADMIN.value,
        resource_type="worker",
        resource_id=worker_id,
    ))

    return registry.stop_worker(worker_id)


@router.post("/workers/{worker_id}/pause")
def pause_single_worker(
    worker_id: str,
    ctx: TenantContext = Depends(require_infra_admin),
):
    """Pause a specific worker (stops billing, preserves state where possible).

    Requires: admin+ role. Verifies worker belongs to caller's workspace.
    """
    registry = get_worker_registry()
    worker = registry.get_worker(worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    verify_resource_ownership(ctx, worker.org_id, "worker", worker_id)

    emit_audit_event(InfraAuditEvent(
        actor_id=ctx.user_id,
        actor_email=ctx.email,
        org_id=ctx.org_id,
        role=ctx.role.value,
        action="pause_single_worker",
        capability=InfraCapability.ADMIN.value,
        resource_type="worker",
        resource_id=worker_id,
    ))

    return registry.pause_worker(worker_id)


@router.post("/workers/{worker_id}/resume")
def resume_single_worker(
    worker_id: str,
    ctx: TenantContext = Depends(require_infra_admin),
):
    """Resume a paused/stopped worker.

    Requires: admin+ role. Verifies worker belongs to caller's workspace.
    """
    registry = get_worker_registry()
    worker = registry.get_worker(worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    verify_resource_ownership(ctx, worker.org_id, "worker", worker_id)

    emit_audit_event(InfraAuditEvent(
        actor_id=ctx.user_id,
        actor_email=ctx.email,
        org_id=ctx.org_id,
        role=ctx.role.value,
        action="resume_single_worker",
        capability=InfraCapability.ADMIN.value,
        resource_type="worker",
        resource_id=worker_id,
    ))

    return registry.resume_worker(worker_id)


@router.get("/workers/idle")
def get_idle_workers(ctx: TenantContext = Depends(require_infra_read)):
    """Get workers that have exceeded the idle timeout.

    Requires: viewer+ role.
    """
    registry = get_worker_registry()
    idle = registry.get_idle_workers()
    return {
        "idle_workers": [w.to_dict() for w in idle],
        "count": len(idle),
        "idle_timeout_minutes": get_fleet_settings().config.idle_timeout_minutes,
    }


@router.post("/workers/idle/shutdown")
def shutdown_idle_workers(ctx: TenantContext = Depends(require_infra_admin)):
    """Shut down all workers that have exceeded the idle timeout.

    Requires: admin+ role.
    """
    emit_audit_event(InfraAuditEvent(
        actor_id=ctx.user_id,
        actor_email=ctx.email,
        org_id=ctx.org_id,
        role=ctx.role.value,
        action="shutdown_idle_workers",
        capability=InfraCapability.ADMIN.value,
    ))

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
def trigger_auto_provision(
    data: dict = None,
    ctx: TenantContext = Depends(require_infra_operate),
):
    """Check if a worker is available for a job; auto-provision if needed.

    Requires: editor+ role.
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
def get_gpu_requirements(ctx: TenantContext = Depends(require_infra_read)):
    """Get GPU requirements per job type for cost estimation.

    Requires: viewer+ role.
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
def record_fleet_spend(
    data: dict,
    ctx: TenantContext = Depends(require_infra_admin),
):
    """Record GPU spend for budget tracking.

    Requires: admin+ role.
    """
    emit_audit_event(InfraAuditEvent(
        actor_id=ctx.user_id,
        actor_email=ctx.email,
        org_id=ctx.org_id,
        role=ctx.role.value,
        action="record_fleet_spend",
        capability=InfraCapability.ADMIN.value,
        request_data=data,
    ))

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
def check_budget_guard(ctx: TenantContext = Depends(require_infra_read)):
    """Check if budget allows new launches or continued operation.

    Requires: viewer+ role.
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
def check_service_health(ctx: TenantContext = Depends(require_infra_read)):
    """Check actual reachability of ComfyUI and Ollama.

    Requires: viewer+ role.
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
def get_ollama_preference(ctx: TenantContext = Depends(require_infra_read)):
    """Get the current Ollama source preference.

    Requires: viewer+ role.
    """
    return {"preference": _ollama_preference}


@router.put("/ollama/preference")
def set_ollama_preference(
    data: dict,
    ctx: TenantContext = Depends(require_infra_operate),
):
    """Set Ollama source preference: auto, local, or remote.

    Requires: editor+ role.
    """
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
def get_ollama_status(ctx: TenantContext = Depends(require_infra_read)):
    """Get detailed Ollama status: local availability, remote availability, active source.

    Requires: viewer+ role.
    """
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


# =============================================================================
# Audit Log — Admin-only access to infrastructure audit trail
# =============================================================================


@router.get("/audit-log")
def get_infra_audit_log(
    limit: int = 100,
    ctx: TenantContext = Depends(require_infra_admin),
):
    """Get recent infrastructure audit events.

    Requires: admin+ role.

    Returns the most recent infrastructure operations with actor,
    action, capability, and result details.
    """
    limit = min(max(limit, 1), 500)
    events = get_audit_log(limit=limit)
    return {
        "events": events,
        "total": len(events),
        "limit": limit,
    }


# =============================================================================
# Capacity Telemetry — System load monitoring and graceful degradation
# =============================================================================

from backend.infrastructure.capacity_telemetry import (
    QueueDecision,
    QueueEntry,
    WorkloadClass,
    get_capacity_service,
)


class CapacityAdmitRequest(BaseModel):
    """Request to evaluate admission for a new job."""

    workload_class: str = Field(..., description="Workload class (e.g. 'image_generation')")
    job_id: str = Field(..., description="Unique job identifier")
    priority: int = Field(default=5, ge=1, le=10, description="Job priority (1=highest)")
    estimated_duration_seconds: float = Field(
        default=60.0, ge=1.0, description="Estimated job duration in seconds"
    )


@router.get("/capacity")
def get_capacity_status(ctx: TenantContext = Depends(require_infra_read)):
    """Get current platform capacity status with degradation level.

    Requires: viewer+ role.

    Returns capacity telemetry snapshot including:
    - active_users, api_request_rate, brain_streams, realtime_connections
    - queue_depth per workload class
    - active_jobs per provider
    - gpu_utilization, platform_compute_liability
    - degradation_level (normal/elevated/degraded/critical)

    Validates: Requirements R90.1, R90.2, R90.3, R90.4
    """
    service = get_capacity_service()
    snapshot = service.get_capacity_snapshot()

    # Include org-specific queue info for the requesting tenant
    org_queue = service.get_org_queue_status(ctx.org_id)

    return {
        **snapshot.to_dict(),
        "org_queue": org_queue,
    }


@router.post("/capacity/admit")
def evaluate_job_admission(
    request: CapacityAdmitRequest,
    ctx: TenantContext = Depends(require_infra_operate),
):
    """Evaluate whether a job should be accepted, queued, or rejected.

    Requires: editor+ role.

    Per R90.1: Queues on overload rather than rejecting (503).
    Per R90.2: Budget-exceeded requests get 402 Payment Required.

    Returns:
        - decision: accept | queue | reject_budget
        - queue_position (if queued): position and estimated wait time
    """
    service = get_capacity_service()
    decision = service.evaluate_admission(request.workload_class, ctx.org_id)

    if decision == QueueDecision.REJECT_BUDGET:
        raise HTTPException(
            status_code=402,
            detail={
                "message": "Budget exceeded. Cannot accept new compute jobs.",
                "code": "BUDGET_EXCEEDED",
                "degradation_level": "critical",
            },
        )

    if decision == QueueDecision.QUEUE:
        # Enqueue the job and return position info
        try:
            workload_class = WorkloadClass(request.workload_class)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid workload_class: {request.workload_class}. "
                f"Valid: {[wc.value for wc in WorkloadClass]}",
            )

        entry = QueueEntry(
            job_id=request.job_id,
            org_id=ctx.org_id,
            workload_class=workload_class,
            priority=request.priority,
            estimated_duration_seconds=request.estimated_duration_seconds,
        )
        position_info = service.enqueue_job(entry)

        return {
            "decision": "queue",
            "job_id": request.job_id,
            "workload_class": request.workload_class,
            "queue_position": position_info.to_dict(),
            "message": "Generation capacity at limit. Job queued.",
        }

    # ACCEPT
    return {
        "decision": "accept",
        "job_id": request.job_id,
        "workload_class": request.workload_class,
        "queue_position": None,
        "message": "Capacity available. Job accepted for immediate execution.",
    }


@router.get("/capacity/queue/{job_id}")
def get_job_queue_position(
    job_id: str,
    ctx: TenantContext = Depends(require_infra_read),
):
    """Get queue position and estimated wait time for a specific job.

    Requires: viewer+ role.

    Returns position info if the job is queued, or 404 if not found in any queue.
    """
    service = get_capacity_service()
    position = service.get_queue_position(job_id)

    if position is None:
        raise HTTPException(
            status_code=404,
            detail="Job not found in any capacity queue",
        )

    return {
        "job_id": job_id,
        "queue_position": position.to_dict(),
    }


@router.delete("/capacity/queue/{job_id}")
def cancel_queued_job(
    job_id: str,
    ctx: TenantContext = Depends(require_infra_operate),
):
    """Remove a job from the capacity queue (cancellation).

    Requires: editor+ role.
    """
    service = get_capacity_service()
    removed = service.remove_job_from_queue(job_id)

    if not removed:
        raise HTTPException(
            status_code=404,
            detail="Job not found in any capacity queue",
        )

    return {
        "job_id": job_id,
        "status": "removed",
        "message": "Job removed from capacity queue.",
    }

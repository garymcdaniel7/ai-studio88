"""Infrastructure Intelligence API Router.

Endpoints for worker orchestration, connection racing, and fleet management.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

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
    """Get live status of the current worker session.

    Returns connection info, GPU details, cost tracking,
    and current operational status for dashboard display.

    Status values:
    - no_session: No worker running
    - connecting: Race in progress
    - booting: Instances launching
    - installing: ComfyUI being installed
    - downloading_model: Pulling model weights
    - starting_comfyui: ComfyUI server starting
    - ready: Worker available for jobs
    - generating: Currently processing a job
    - error: Something went wrong
    - stopped: Session ended
    """
    orchestrator = get_orchestrator()
    return orchestrator.get_status()


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

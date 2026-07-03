"""Worker Manager — manages external GPU workers.

Workers are external processes (ComfyUI instances, GPU servers, cloud VMs)
that register with AI Studio, report their capabilities, and accept jobs.

The Worker Manager:
- Tracks registered workers and their status
- Handles heartbeats (detects offline workers)
- Assigns jobs to appropriate workers
- Manages graceful shutdown and restart
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorkerGPU:
    """GPU capabilities reported by a worker."""
    model: str = "Unknown"
    vram_total_gb: float = 0.0
    vram_free_gb: float = 0.0
    cuda_version: str = ""
    driver_version: str = ""
    temperature_c: int = 0
    utilization_pct: int = 0
    supported_models: list[str] = field(default_factory=list)


@dataclass
class Worker:
    """A registered worker instance."""
    id: str = ""
    name: str = ""
    type: str = "gpu"  # gpu, cpu, cloud
    provider: str = ""  # comfyui, vast_ai, runpod, shadow_pc, local
    url: str = ""
    status: str = "offline"  # online, busy, offline, error
    gpu: WorkerGPU = field(default_factory=WorkerGPU)
    current_job: str | None = None
    queue_size: int = 0
    last_heartbeat: float = 0.0
    registered_at: float = 0.0
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def is_alive(self) -> bool:
        """Worker is alive if heartbeat within last 60 seconds."""
        return (time.time() - self.last_heartbeat) < 60.0

    @property
    def is_available(self) -> bool:
        """Worker can accept jobs."""
        return self.status == "online" and self.is_alive


# =============================================================================
# Worker Registry (in-memory, future: Redis/DB-backed)
# =============================================================================

_workers: dict[str, Worker] = {}


def register_worker(
    name: str,
    provider: str = "local",
    url: str = "",
    gpu: dict | None = None,
    tags: list[str] | None = None,
) -> Worker:
    """Register a new worker or update existing one."""
    worker_id = f"{provider}-{name}-{uuid.uuid4().hex[:6]}"

    # Check if already registered by name+provider
    for existing in _workers.values():
        if existing.name == name and existing.provider == provider:
            worker_id = existing.id
            break

    worker = Worker(
        id=worker_id,
        name=name,
        provider=provider,
        url=url,
        status="online",
        gpu=WorkerGPU(**(gpu or {})),
        last_heartbeat=time.time(),
        registered_at=time.time(),
        tags=tags or [],
    )
    _workers[worker_id] = worker
    return worker


def heartbeat(worker_id: str, gpu_status: dict | None = None) -> Worker | None:
    """Update worker heartbeat. Returns None if worker not found."""
    worker = _workers.get(worker_id)
    if not worker:
        return None
    worker.last_heartbeat = time.time()
    worker.status = "online"
    if gpu_status:
        worker.gpu.vram_free_gb = gpu_status.get("vram_free_gb", worker.gpu.vram_free_gb)
        worker.gpu.temperature_c = gpu_status.get("temperature_c", worker.gpu.temperature_c)
        worker.gpu.utilization_pct = gpu_status.get("utilization_pct", worker.gpu.utilization_pct)
    return worker


def get_worker(worker_id: str) -> Worker | None:
    """Get a worker by ID."""
    return _workers.get(worker_id)


def list_workers(status: str | None = None) -> list[Worker]:
    """List all workers, optionally filtered by status."""
    workers = list(_workers.values())
    if status:
        workers = [w for w in workers if w.status == status]
    return workers


def unregister_worker(worker_id: str) -> bool:
    """Remove a worker from the registry."""
    if worker_id in _workers:
        del _workers[worker_id]
        return True
    return False


def mark_worker_busy(worker_id: str, job_id: str) -> None:
    """Mark a worker as busy with a job."""
    worker = _workers.get(worker_id)
    if worker:
        worker.status = "busy"
        worker.current_job = job_id


def mark_worker_idle(worker_id: str) -> None:
    """Mark a worker as idle (job completed)."""
    worker = _workers.get(worker_id)
    if worker:
        worker.status = "online"
        worker.current_job = None


def detect_offline_workers() -> list[Worker]:
    """Find workers that haven't sent a heartbeat recently."""
    offline = []
    for worker in _workers.values():
        if not worker.is_alive and worker.status != "offline":
            worker.status = "offline"
            worker.current_job = None
            offline.append(worker)
    return offline


def get_system_health() -> dict:
    """Get overall system health summary."""
    all_workers = list(_workers.values())
    online = [w for w in all_workers if w.status == "online"]
    busy = [w for w in all_workers if w.status == "busy"]
    offline = [w for w in all_workers if w.status == "offline"]

    total_vram = sum(w.gpu.vram_total_gb for w in all_workers)
    free_vram = sum(w.gpu.vram_free_gb for w in online + busy)

    return {
        "total_workers": len(all_workers),
        "online": len(online),
        "busy": len(busy),
        "offline": len(offline),
        "total_vram_gb": total_vram,
        "free_vram_gb": free_vram,
        "healthy": len(online) + len(busy) > 0,
    }


# =============================================================================
# Initialize with a simulated local worker
# =============================================================================

def _init_simulated_worker():
    """Register a simulated worker for development."""
    register_worker(
        name="local-sim",
        provider="simulation",
        url="http://localhost:8188",
        gpu={
            "model": "Simulated RTX 4090",
            "vram_total_gb": 24.0,
            "vram_free_gb": 20.0,
            "cuda_version": "12.1",
            "driver_version": "535.86",
            "supported_models": ["flux-dev", "sdxl", "wan-2.1"],
        },
        tags=["simulation", "dev"],
    )


_init_simulated_worker()

"""Render Fleet Mode — Manage multiple GPU workers simultaneously.

Enables large productions by maintaining a fleet of specialized workers:
- Image workers (SDXL, Flux)
- Video workers (WAN 2.1)
- Training workers (LoRA)
- Upscaling workers
- Export/encoding workers

The fleet coordinator:
- Maintains multiple concurrent worker sessions
- Routes jobs to the best available worker
- Tracks per-worker utilization and cost
- Auto-scales based on queue depth (future)
- Provides fleet-wide health and cost dashboard

Architecture:
    FleetManager (singleton)
    ├── workers: dict[str, FleetWorker]  # worker_id -> worker
    ├── job_queue: list[FleetJob]        # pending jobs
    └── router: FleetRouter              # assigns jobs to workers
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from backend.infrastructure.connection_race import ConnectionRace, RaceConfig, RaceResult
from backend.providers.vast.client import VastClient, VastClientError

logger = logging.getLogger(__name__)


# =============================================================================
# Data Models
# =============================================================================


@dataclass
class FleetWorker:
    """A single worker in the render fleet."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    instance_id: Optional[int] = None
    name: str = ""
    gpu_name: str = ""
    gpu_ram_mb: int = 0
    ssh_host: str = ""
    ssh_port: int = 0
    comfyui_url: Optional[str] = None
    status: str = "launching"  # launching, ready, busy, error, stopped
    specialty: str = "general"  # general, image, video, training, upscale
    hourly_rate: float = 0.0
    current_job_id: Optional[str] = None
    jobs_completed: int = 0
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict = field(default_factory=dict)

    @property
    def is_available(self) -> bool:
        return self.status == "ready"

    @property
    def uptime_seconds(self) -> float:
        try:
            started = datetime.fromisoformat(self.started_at)
            return (datetime.now(timezone.utc) - started).total_seconds()
        except (ValueError, TypeError):
            return 0.0

    @property
    def current_cost(self) -> float:
        return round((self.uptime_seconds / 3600) * self.hourly_rate, 4)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "instance_id": self.instance_id,
            "name": self.name,
            "gpu_name": self.gpu_name,
            "gpu_ram_mb": self.gpu_ram_mb,
            "ssh_host": self.ssh_host,
            "ssh_port": self.ssh_port,
            "comfyui_url": self.comfyui_url,
            "status": self.status,
            "specialty": self.specialty,
            "hourly_rate": self.hourly_rate,
            "current_job_id": self.current_job_id,
            "jobs_completed": self.jobs_completed,
            "uptime_seconds": round(self.uptime_seconds, 1),
            "current_cost": self.current_cost,
            "started_at": self.started_at,
        }


@dataclass
class FleetJob:
    """A job in the fleet queue."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    job_type: str = "image"  # image, video, training, upscale
    priority: int = 5  # 1=highest, 10=lowest
    model: str = ""
    params: dict = field(default_factory=dict)
    worker_id: Optional[str] = None
    status: str = "queued"  # queued, assigned, running, completed, failed
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    result: Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "job_type": self.job_type,
            "priority": self.priority,
            "model": self.model,
            "worker_id": self.worker_id,
            "status": self.status,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }


# =============================================================================
# Fleet Manager
# =============================================================================


class FleetManager:
    """Manages a fleet of GPU workers for parallel production.

    Supports:
    - Adding/removing workers dynamically
    - Job routing based on worker specialty and availability
    - Fleet-wide cost tracking
    - Health monitoring
    """

    def __init__(self):
        self._workers: dict[str, FleetWorker] = {}
        self._job_queue: list[FleetJob] = []
        self._completed_jobs: list[FleetJob] = []
        self._client: Optional[VastClient] = None

    @property
    def workers(self) -> list[FleetWorker]:
        return list(self._workers.values())

    @property
    def active_workers(self) -> list[FleetWorker]:
        return [w for w in self._workers.values() if w.status in ("ready", "busy")]

    @property
    def available_workers(self) -> list[FleetWorker]:
        return [w for w in self._workers.values() if w.is_available]

    @property
    def fleet_size(self) -> int:
        return len(self._workers)

    @property
    def total_hourly_cost(self) -> float:
        return sum(w.hourly_rate for w in self.active_workers)

    @property
    def total_running_cost(self) -> float:
        return sum(w.current_cost for w in self.active_workers)

    def _get_client(self) -> VastClient:
        if not self._client:
            self._client = VastClient()
        return self._client

    # ─── Add Worker ───────────────────────────────────────────────────────

    def add_worker(
        self,
        max_price: float = 1.50,
        min_vram_gb: float = 12.0,
        specialty: str = "general",
        gpu_filter: Optional[str] = None,
        num_candidates: int = 3,
        disk_gb: int = 80,
        timeout: int = 600,
    ) -> dict[str, Any]:
        """Launch a new worker and add it to the fleet.

        Uses Connection Race Mode for fast provisioning.

        Args:
            max_price: Maximum $/hr
            min_vram_gb: Minimum VRAM
            specialty: Worker role (general, image, video, training, upscale)
            gpu_filter: Specific GPU model name
            num_candidates: Race candidates
            disk_gb: Disk space
            timeout: Boot timeout

        Returns:
            Dict with worker info on success, error info on failure.
        """
        worker = FleetWorker(specialty=specialty, status="launching")
        self._workers[worker.id] = worker

        config = RaceConfig(
            max_price=max_price,
            min_vram_gb=min_vram_gb,
            num_candidates=num_candidates,
            gpu_filter=gpu_filter,
            disk_gb=disk_gb,
            timeout=timeout,
        )

        race = ConnectionRace(self._get_client())
        result: RaceResult = race.run(config)

        if not result.success or not result.winner:
            worker.status = "error"
            worker.metadata["error"] = result.error
            return {
                "status": "failed",
                "worker_id": worker.id,
                "error": result.error,
                "time_seconds": result.total_time_seconds,
            }

        # Configure worker from race winner
        winner = result.winner
        worker.instance_id = winner.instance_id
        worker.name = f"fleet-{specialty}-{winner.gpu_name.replace(' ', '-').lower()}"
        worker.gpu_name = winner.gpu_name
        worker.gpu_ram_mb = winner.gpu_ram_mb
        worker.ssh_host = winner.ssh_host or ""
        worker.ssh_port = winner.ssh_port or 0
        worker.hourly_rate = winner.hourly_cost
        worker.status = "ready"
        worker.metadata.update({
            "offer_id": winner.offer_id,
            "region": winner.region,
            "boot_time_seconds": winner.boot_time_seconds,
        })

        logger.info(f"Fleet worker added: {worker.name} ({worker.gpu_name})")

        return {
            "status": "success",
            "worker_id": worker.id,
            "worker": worker.to_dict(),
            "boot_time_seconds": winner.boot_time_seconds,
        }

    # ─── Remove Worker ────────────────────────────────────────────────────

    def remove_worker(self, worker_id: str) -> dict[str, Any]:
        """Stop and remove a worker from the fleet.

        Destroys the Vast.ai instance and removes from tracking.
        """
        worker = self._workers.get(worker_id)
        if not worker:
            return {"status": "not_found", "error": f"Worker {worker_id} not in fleet"}

        if worker.instance_id:
            try:
                self._get_client().destroy_instance(worker.instance_id)
                logger.info(f"Destroyed fleet worker instance {worker.instance_id}")
            except Exception as e:
                logger.warning(f"Failed to destroy instance: {e}")

        worker.status = "stopped"
        del self._workers[worker_id]

        return {
            "status": "removed",
            "worker_id": worker_id,
            "final_cost": worker.current_cost,
            "jobs_completed": worker.jobs_completed,
        }

    # ─── Stop All ─────────────────────────────────────────────────────────

    def stop_all(self) -> dict[str, Any]:
        """Destroy all fleet workers. Emergency shutdown."""
        results = []
        worker_ids = list(self._workers.keys())
        for wid in worker_ids:
            results.append(self.remove_worker(wid))

        total_cost = sum(r.get("final_cost", 0) for r in results)
        return {
            "status": "fleet_stopped",
            "workers_stopped": len(results),
            "total_cost": round(total_cost, 4),
            "results": results,
        }

    # ─── Job Routing ──────────────────────────────────────────────────────

    def submit_job(self, job_type: str, model: str = "", priority: int = 5, params: dict = None) -> FleetJob:
        """Submit a job to the fleet queue.

        The job will be routed to the best available worker.
        """
        job = FleetJob(
            job_type=job_type,
            model=model,
            priority=priority,
            params=params or {},
        )

        # Try immediate assignment
        worker = self._find_worker_for_job(job)
        if worker:
            job.worker_id = worker.id
            job.status = "assigned"
            worker.current_job_id = job.id
            worker.status = "busy"
        else:
            self._job_queue.append(job)

        return job

    def _find_worker_for_job(self, job: FleetJob) -> Optional[FleetWorker]:
        """Find the best available worker for a job."""
        available = self.available_workers
        if not available:
            return None

        # Prefer workers with matching specialty
        specialty_match = [w for w in available if w.specialty == job.job_type]
        if specialty_match:
            return specialty_match[0]

        # Prefer general workers
        general = [w for w in available if w.specialty == "general"]
        if general:
            return general[0]

        # Any available worker
        return available[0]

    def complete_job(self, job_id: str, result: dict = None) -> None:
        """Mark a job as completed and free the worker."""
        # Find job in active assignments
        for worker in self._workers.values():
            if worker.current_job_id == job_id:
                worker.current_job_id = None
                worker.status = "ready"
                worker.jobs_completed += 1
                break

        # Check queue for next job
        self._process_queue()

    def _process_queue(self) -> None:
        """Try to assign queued jobs to available workers."""
        remaining = []
        for job in sorted(self._job_queue, key=lambda j: j.priority):
            worker = self._find_worker_for_job(job)
            if worker:
                job.worker_id = worker.id
                job.status = "assigned"
                worker.current_job_id = job.id
                worker.status = "busy"
            else:
                remaining.append(job)
        self._job_queue = remaining

    # ─── Fleet Status ─────────────────────────────────────────────────────

    def get_fleet_status(self) -> dict[str, Any]:
        """Get comprehensive fleet status for dashboard."""
        return {
            "fleet_size": self.fleet_size,
            "active_workers": len(self.active_workers),
            "available_workers": len(self.available_workers),
            "queued_jobs": len(self._job_queue),
            "total_hourly_cost": round(self.total_hourly_cost, 3),
            "total_running_cost": round(self.total_running_cost, 4),
            "workers": [w.to_dict() for w in self._workers.values()],
            "queue": [j.to_dict() for j in self._job_queue],
            "specialties": self._get_specialty_summary(),
        }

    def _get_specialty_summary(self) -> dict[str, int]:
        """Count workers by specialty."""
        summary: dict[str, int] = {}
        for w in self.active_workers:
            summary[w.specialty] = summary.get(w.specialty, 0) + 1
        return summary


# =============================================================================
# Module-level singleton
# =============================================================================

_fleet_manager: Optional[FleetManager] = None


def get_fleet_manager() -> FleetManager:
    """Get or create the global FleetManager singleton."""
    global _fleet_manager
    if _fleet_manager is None:
        _fleet_manager = FleetManager()
    return _fleet_manager

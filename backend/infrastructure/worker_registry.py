"""Worker Registry — Tracks all GPU instances across all providers.

Provides a unified interface for managing multiple workers regardless of
whether they're on Vast.ai, RunPod, or Shadow. Each worker has:
- Unique ID, provider, instance details
- Status (provisioning, ready, busy, idle, stopped, destroyed)
- Specialty (image, training, video, general)
- Per-instance controls (start, stop, pause)
- Idle tracking (last_active_at for timeout logic)

Vendor-specific behaviors:
- Vast.ai: stop = destroy instance (no persistent state)
- RunPod: stop = stop pod (persistent volume preserved)
- Shadow: stop = pause (fastest resume)
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from backend.infrastructure.fleet_settings import get_fleet_settings, IDLE_ACTIONS

logger = logging.getLogger(__name__)


@dataclass
class WorkerInstance:
    """A single GPU worker instance in the fleet."""

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    provider: str = "vast"  # vast | runpod | shadow
    provider_instance_id: Optional[str] = None  # Vast instance ID or RunPod pod ID
    gpu_name: str = ""
    vram_gb: int = 0
    specialty: str = "general"  # image | training | video | general
    status: str = "provisioning"  # provisioning | ready | busy | idle | stopped | destroyed
    ssh_host: str = ""
    ssh_port: int = 0
    hourly_rate: float = 0.0
    models_loaded: list[str] = field(default_factory=list)
    apps_installed: list[str] = field(default_factory=list)  # comfyui, simpletuner, ollama
    launched_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_active_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    jobs_completed: int = 0
    total_cost: float = 0.0
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "provider": self.provider,
            "provider_instance_id": self.provider_instance_id,
            "gpu_name": self.gpu_name,
            "vram_gb": self.vram_gb,
            "specialty": self.specialty,
            "status": self.status,
            "ssh_host": self.ssh_host,
            "ssh_port": self.ssh_port,
            "hourly_rate": self.hourly_rate,
            "models_loaded": self.models_loaded,
            "apps_installed": self.apps_installed,
            "launched_at": self.launched_at,
            "last_active_at": self.last_active_at,
            "jobs_completed": self.jobs_completed,
            "total_cost": self.total_cost,
            "idle_minutes": self.idle_minutes,
            "idle_action": IDLE_ACTIONS.get(self.provider, "destroy"),
        }

    @property
    def idle_minutes(self) -> float:
        """Minutes since last activity."""
        try:
            last = datetime.fromisoformat(self.last_active_at.replace("Z", "+00:00"))
            return (datetime.now(timezone.utc) - last).total_seconds() / 60
        except Exception:
            return 0.0

    def mark_active(self) -> None:
        """Update last_active_at to now."""
        self.last_active_at = datetime.now(timezone.utc).isoformat()


class WorkerRegistry:
    """Registry of all GPU workers across all providers.

    Provides unified start/stop/pause controls with vendor-specific handling.
    """

    def __init__(self):
        self._workers: dict[str, WorkerInstance] = {}
        self._sync_from_providers()

    def _sync_from_providers(self) -> None:
        """Sync registry with actual running instances from providers."""
        # Sync Vast.ai instances
        try:
            from backend.providers.vast.client import VastClient
            client = VastClient()
            instances = client.get_instances()
            for inst in instances:
                status = inst.get("actual_status", "")
                if status in ("running", "loading"):
                    iid = str(inst.get("id"))
                    # Check if already registered
                    existing = self._find_by_provider_id("vast", iid)
                    if not existing:
                        worker = WorkerInstance(
                            provider="vast",
                            provider_instance_id=iid,
                            gpu_name=inst.get("gpu_name", ""),
                            vram_gb=inst.get("gpu_ram", 0) // 1024,
                            status="ready",
                            ssh_host=inst.get("ssh_host", ""),
                            ssh_port=inst.get("ssh_port", 0),
                            hourly_rate=inst.get("dph_total", 0),
                        )
                        self._workers[worker.id] = worker
                        logger.info(f"Synced Vast.ai instance {iid} as worker {worker.id}")
        except Exception as e:
            logger.debug(f"Vast.ai sync failed: {e}")

        # Sync RunPod pods
        try:
            if os.getenv("RUNPOD_API_KEY"):
                from backend.providers.runpod.client import RunPodClient
                client = RunPodClient()
                pods = client.get_pods()
                for pod in pods:
                    if pod.get("desiredStatus") == "RUNNING":
                        pid = pod.get("id", "")
                        existing = self._find_by_provider_id("runpod", pid)
                        if not existing:
                            worker = WorkerInstance(
                                provider="runpod",
                                provider_instance_id=pid,
                                gpu_name=pod.get("machine", {}).get("gpuDisplayName", ""),
                                vram_gb=0,
                                status="ready",
                                hourly_rate=pod.get("costPerHr", 0),
                            )
                            self._workers[worker.id] = worker
        except Exception as e:
            logger.debug(f"RunPod sync failed: {e}")

    def _find_by_provider_id(self, provider: str, provider_id: str) -> Optional[WorkerInstance]:
        for w in self._workers.values():
            if w.provider == provider and w.provider_instance_id == provider_id:
                return w
        return None

    # ─── Public API ───────────────────────────────────────────────────────

    def list_workers(self) -> list[dict]:
        """List all workers with their current status."""
        return [w.to_dict() for w in self._workers.values() if w.status != "destroyed"]

    def get_worker(self, worker_id: str) -> Optional[WorkerInstance]:
        return self._workers.get(worker_id)

    def register_worker(self, worker: WorkerInstance) -> WorkerInstance:
        """Register a new worker in the fleet."""
        self._workers[worker.id] = worker
        return worker

    def stop_worker(self, worker_id: str) -> dict:
        """Stop a worker — vendor-aware action (destroy for Vast, stop for RunPod)."""
        worker = self._workers.get(worker_id)
        if not worker:
            return {"status": "not_found", "error": f"Worker {worker_id} not found"}

        action = IDLE_ACTIONS.get(worker.provider, "destroy")
        provider_id = worker.provider_instance_id

        try:
            if worker.provider == "vast" and provider_id:
                from backend.providers.vast.client import VastClient
                client = VastClient()
                if action == "destroy":
                    client.destroy_instance(int(provider_id))
                    worker.status = "destroyed"
                else:
                    client.stop_instance(int(provider_id))
                    worker.status = "stopped"

            elif worker.provider == "runpod" and provider_id:
                from backend.providers.runpod.client import RunPodClient
                client = RunPodClient()
                client.stop_pod(provider_id)
                worker.status = "stopped"

            return {
                "status": "stopped",
                "worker_id": worker_id,
                "action": action,
                "provider": worker.provider,
                "message": f"Worker {action}ed via {worker.provider}",
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def pause_worker(self, worker_id: str) -> dict:
        """Pause a worker (stop billing but preserve state where possible)."""
        worker = self._workers.get(worker_id)
        if not worker:
            return {"status": "not_found", "error": f"Worker {worker_id} not found"}

        provider_id = worker.provider_instance_id
        try:
            if worker.provider == "vast" and provider_id:
                from backend.providers.vast.client import VastClient
                client = VastClient()
                client.stop_instance(int(provider_id))  # Vast "stop" = pause
                worker.status = "stopped"

            elif worker.provider == "runpod" and provider_id:
                from backend.providers.runpod.client import RunPodClient
                client = RunPodClient()
                client.stop_pod(provider_id)
                worker.status = "stopped"

            return {"status": "paused", "worker_id": worker_id, "provider": worker.provider}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def resume_worker(self, worker_id: str) -> dict:
        """Resume a paused/stopped worker."""
        worker = self._workers.get(worker_id)
        if not worker:
            return {"status": "not_found", "error": f"Worker {worker_id} not found"}

        provider_id = worker.provider_instance_id
        try:
            if worker.provider == "vast" and provider_id:
                import httpx
                api_key = os.getenv("VAST_API_KEY", "")
                resp = httpx.put(
                    f"https://console.vast.ai/api/v0/instances/{provider_id}/",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"state": "running"},
                    timeout=15,
                    follow_redirects=True,
                )
                if resp.status_code == 200:
                    worker.status = "ready"
                else:
                    return {"status": "error", "error": f"Resume failed: {resp.text[:100]}"}

            elif worker.provider == "runpod" and provider_id:
                from backend.providers.runpod.client import RunPodClient
                client = RunPodClient()
                client.resume_pod(provider_id)
                worker.status = "ready"

            return {"status": "resumed", "worker_id": worker_id, "provider": worker.provider}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def get_idle_workers(self) -> list[WorkerInstance]:
        """Get workers that have exceeded the idle timeout."""
        settings = get_fleet_settings()
        timeout = settings.config.idle_timeout_minutes
        if timeout <= 0:
            return []  # Idle timeout disabled

        return [
            w for w in self._workers.values()
            if w.status in ("ready", "idle") and w.idle_minutes > timeout
        ]

    def get_available_worker(self, specialty: str = "general") -> Optional[WorkerInstance]:
        """Find an available worker matching the requested specialty."""
        for w in self._workers.values():
            if w.status == "ready" and (w.specialty == specialty or w.specialty == "general"):
                return w
        return None

    @property
    def active_count(self) -> int:
        return sum(1 for w in self._workers.values() if w.status in ("ready", "busy", "idle"))


# Singleton
_registry: Optional[WorkerRegistry] = None


def get_worker_registry() -> WorkerRegistry:
    global _registry
    if _registry is None:
        _registry = WorkerRegistry()
    return _registry

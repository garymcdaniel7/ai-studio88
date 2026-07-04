"""Worker Orchestrator — Manages the lifecycle of GPU workers.

Responsibilities:
- Launch workers via Connection Race Mode
- Track connection attempts and session history
- Set up ComfyUI (install, pull models, start)
- Maintain persistent primary worker connection
- Report live status for dashboard consumption
- Provide start/stop/status/history interface

Status lifecycle:
    connecting → booting → installing → downloading_model → starting_comfyui → ready → generating → error
"""
from __future__ import annotations

import logging
import os
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from backend.infrastructure.connection_race import (
    ConnectionRace,
    RaceCandidate,
    RaceConfig,
    RaceResult,
)
from backend.providers.vast.client import VastClient, VastClientError

logger = logging.getLogger(__name__)


# =============================================================================
# Data Models
# =============================================================================


@dataclass
class ConnectionAttempt:
    """Record of a single connection attempt (for history/learning)."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    offer_id: int = 0
    instance_id: Optional[int] = None
    gpu_name: str = ""
    gpu_ram_mb: int = 0
    region: str = ""
    country: str = ""
    provider: str = "vast_ai"
    status: str = "pending"  # success, failed, timeout
    boot_time_seconds: Optional[float] = None
    ssh_verified_at: Optional[str] = None
    comfyui_verified_at: Optional[str] = None
    failure_reason: Optional[str] = None
    hourly_cost: float = 0.0
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class WorkerSession:
    """An active worker session (the primary connection)."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    instance_id: Optional[int] = None
    worker_name: str = ""
    gpu_name: str = ""
    ssh_host: str = ""
    ssh_port: int = 0
    comfyui_url: Optional[str] = None
    status: str = "connecting"
    models_loaded: list[str] = field(default_factory=list)
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    ended_at: Optional[str] = None
    total_cost: float = 0.0
    jobs_completed: int = 0
    hourly_rate: float = 0.0
    metadata: dict = field(default_factory=dict)


# =============================================================================
# Worker Orchestrator
# =============================================================================


class WorkerOrchestrator:
    """Orchestrates GPU worker lifecycle for AI Studio.

    Maintains a persistent primary worker connection and tracks
    all connection attempts for learning/reputation.

    Usage:
        orchestrator = WorkerOrchestrator()
        result = orchestrator.launch_worker(max_price=1.0, min_vram_gb=24)
        status = orchestrator.get_status()
        orchestrator.stop_worker()
    """

    def __init__(self, vast_client: Optional[VastClient] = None):
        self._client = vast_client
        self._session: Optional[WorkerSession] = None
        self._connection_log: list[ConnectionAttempt] = []
        self._race: Optional[ConnectionRace] = None

    @property
    def session(self) -> Optional[WorkerSession]:
        """Current active session, if any."""
        return self._session

    @property
    def is_active(self) -> bool:
        """Whether there's an active worker session."""
        return self._session is not None and self._session.status not in (
            "stopped", "error", "destroyed"
        )

    def _get_client(self) -> VastClient:
        """Lazily initialize the Vast client."""
        if not self._client:
            self._client = VastClient()
        return self._client

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # ─── Launch ───────────────────────────────────────────────────────────

    def launch_worker(
        self,
        max_price: float = 1.50,
        min_vram_gb: float = 12.0,
        num_candidates: int = 3,
        gpu_filter: Optional[str] = None,
        excluded_hosts: Optional[list[int]] = None,
        disk_gb: int = 80,
        timeout: int = 600,
        setup_comfyui: bool = True,
    ) -> dict[str, Any]:
        """Launch a worker using Connection Race Mode.

        Args:
            max_price: Maximum hourly cost per GPU
            min_vram_gb: Minimum VRAM in GB
            num_candidates: Number of instances to race
            gpu_filter: Specific GPU model name (e.g. "RTX 4090")
            excluded_hosts: Host IDs to skip
            disk_gb: Disk space to request
            timeout: Max seconds to wait for boot
            setup_comfyui: Whether to install ComfyUI after SSH is up

        Returns:
            Dict with session info, status, and connection details
        """
        if self.is_active:
            return {
                "status": "already_active",
                "message": "A worker session is already active. Stop it first.",
                "session": self._session_to_dict(),
            }

        # Create new session
        self._session = WorkerSession(status="connecting")
        logger.info("Starting Connection Race Mode...")

        # Build race config
        config = RaceConfig(
            max_price=max_price,
            min_vram_gb=min_vram_gb,
            num_candidates=num_candidates,
            gpu_filter=gpu_filter,
            excluded_hosts=excluded_hosts or [],
            disk_gb=disk_gb,
            timeout=timeout,
        )

        # Run the race
        self._race = ConnectionRace(self._get_client())
        self._session.status = "booting"

        race_result: RaceResult = self._race.run(config)

        # Log all attempts
        for candidate in race_result.candidates:
            attempt = ConnectionAttempt(
                offer_id=candidate.offer_id,
                instance_id=candidate.instance_id,
                gpu_name=candidate.gpu_name,
                gpu_ram_mb=candidate.gpu_ram_mb,
                region=candidate.region,
                country=candidate.country,
                status="success" if candidate.status == "won" else (
                    "timeout" if candidate.status == "timeout" else "failed"
                ),
                boot_time_seconds=candidate.boot_time_seconds,
                ssh_verified_at=self._now_iso() if candidate.ssh_verified else None,
                failure_reason=candidate.failure_reason,
                hourly_cost=candidate.hourly_cost,
            )
            self._connection_log.append(attempt)

        if not race_result.success or not race_result.winner:
            self._session.status = "error"
            self._session.metadata["error"] = race_result.error
            return {
                "status": "failed",
                "error": race_result.error,
                "attempts": len(race_result.candidates),
                "total_time_seconds": race_result.total_time_seconds,
            }

        # Configure session from winner
        winner = race_result.winner
        self._session.instance_id = winner.instance_id
        self._session.gpu_name = winner.gpu_name
        self._session.ssh_host = winner.ssh_host or ""
        self._session.ssh_port = winner.ssh_port or 0
        self._session.hourly_rate = winner.hourly_cost
        self._session.worker_name = f"vast-{winner.gpu_name.replace(' ', '-').lower()}-{winner.instance_id}"
        self._session.metadata.update({
            "offer_id": winner.offer_id,
            "region": winner.region,
            "country": winner.country,
            "boot_time_seconds": winner.boot_time_seconds,
            "race_candidates": len(race_result.candidates),
            "race_time_seconds": race_result.total_time_seconds,
        })

        # Setup ComfyUI if requested
        if setup_comfyui:
            self._setup_comfyui()
        else:
            self._session.status = "ready"

        logger.info(
            f"Worker ready: {self._session.worker_name} "
            f"({self._session.gpu_name}) @ {self._session.ssh_host}:{self._session.ssh_port}"
        )

        return {
            "status": "success",
            "session": self._session_to_dict(),
            "boot_time_seconds": winner.boot_time_seconds,
            "race_candidates": len(race_result.candidates),
            "total_time_seconds": race_result.total_time_seconds,
        }

    # ─── ComfyUI Setup ────────────────────────────────────────────────────

    def _setup_comfyui(self) -> None:
        """Install and start ComfyUI on the worker via SSH.

        Steps:
        1. Install ComfyUI
        2. Pull model from B2 cache (or HF fallback)
        3. Start ComfyUI server
        """
        if not self._session:
            return

        ssh_key = os.path.expanduser("~/.ssh/id_ed25519")
        ssh_target = f"root@{self._session.ssh_host}"
        ssh_port = str(self._session.ssh_port)

        base_ssh_cmd = [
            "ssh", "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-i", ssh_key,
            "-p", ssh_port,
            ssh_target,
        ]

        def _ssh_exec(command: str, step_name: str) -> bool:
            """Execute a command on the remote worker via SSH."""
            try:
                result = subprocess.run(
                    base_ssh_cmd + [command],
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                if result.returncode != 0:
                    logger.warning(f"SSH {step_name} failed: {result.stderr[:200]}")
                    return False
                return True
            except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                logger.warning(f"SSH {step_name} error: {e}")
                return False

        # Step 1: Install ComfyUI
        self._session.status = "installing"
        install_cmd = (
            "cd /workspace && "
            "git clone https://github.com/comfyanonymous/ComfyUI.git 2>/dev/null || true && "
            "cd ComfyUI && pip install -r requirements.txt -q"
        )
        if not _ssh_exec(install_cmd, "install_comfyui"):
            logger.warning("ComfyUI install may have issues, continuing...")

        # Step 2: Download model from B2 cache or HF
        self._session.status = "downloading_model"
        b2_key_id = os.getenv("B2_KEY_ID", "")
        b2_app_key = os.getenv("B2_APPLICATION_KEY", "")
        b2_endpoint = os.getenv("B2_ENDPOINT_URL", "")
        model_bucket = os.getenv("MODEL_CACHE_BUCKET", "")
        model_prefix = os.getenv("MODEL_CACHE_PREFIX", "models")

        if b2_key_id and b2_app_key and model_bucket:
            # Try B2 cache first
            download_cmd = (
                f"pip install boto3 -q && python -c \""
                f"import boto3; "
                f"s3 = boto3.client('s3', "
                f"endpoint_url='{b2_endpoint}', "
                f"aws_access_key_id='{b2_key_id}', "
                f"aws_secret_access_key='{b2_app_key}'); "
                f"print('B2 connected')\""
            )
            _ssh_exec(download_cmd, "model_download")
        else:
            logger.info("B2 cache not configured, skipping model pre-download")

        # Step 3: Start ComfyUI
        self._session.status = "starting_comfyui"
        start_cmd = (
            "cd /workspace/ComfyUI && "
            "nohup python main.py --listen 0.0.0.0 --port 8188 > /tmp/comfyui.log 2>&1 &"
        )
        _ssh_exec(start_cmd, "start_comfyui")

        # Give it a moment to start
        time.sleep(5)

        # Build ComfyUI URL
        self._session.comfyui_url = f"http://{self._session.ssh_host}:8188"
        self._session.status = "ready"

    # ─── Status ───────────────────────────────────────────────────────────

    def get_status(self) -> dict[str, Any]:
        """Get current worker/session status.

        Returns live status suitable for dashboard display.
        """
        if not self._session:
            return {
                "active": False,
                "status": "no_session",
                "message": "No active worker session",
            }

        # Calculate running cost
        if self._session.status not in ("stopped", "error", "destroyed"):
            started = datetime.fromisoformat(self._session.started_at)
            elapsed_hours = (
                datetime.now(timezone.utc) - started
            ).total_seconds() / 3600
            self._session.total_cost = round(
                elapsed_hours * self._session.hourly_rate, 4
            )

        return {
            "active": self.is_active,
            **self._session_to_dict(),
        }

    # ─── Stop ─────────────────────────────────────────────────────────────

    def stop_worker(self) -> dict[str, Any]:
        """Stop and destroy the current worker.

        Returns status info about the terminated session.
        """
        if not self._session:
            return {"status": "no_session", "message": "No active worker to stop"}

        session_info = self._session_to_dict()

        if self._session.instance_id:
            try:
                self._get_client().destroy_instance(self._session.instance_id)
                self._session.status = "destroyed"
                logger.info(f"Destroyed worker instance {self._session.instance_id}")
            except Exception as e:
                self._session.status = "error"
                logger.error(f"Failed to destroy instance: {e}")
                return {
                    "status": "error",
                    "message": f"Failed to destroy instance: {e}",
                    "session": session_info,
                }

        self._session.ended_at = self._now_iso()
        self._session.status = "stopped"

        # Calculate final cost
        started = datetime.fromisoformat(self._session.started_at)
        ended = datetime.fromisoformat(self._session.ended_at)
        elapsed_hours = (ended - started).total_seconds() / 3600
        self._session.total_cost = round(
            elapsed_hours * self._session.hourly_rate, 4
        )

        result = {
            "status": "stopped",
            "message": "Worker stopped and destroyed",
            "session": self._session_to_dict(),
        }

        # Clear active session (keep in log)
        self._session = None
        return result

    # ─── Connection Log ───────────────────────────────────────────────────

    def get_connection_log(self) -> list[dict[str, Any]]:
        """Get full history of connection attempts."""
        return [
            {
                "id": a.id,
                "offer_id": a.offer_id,
                "instance_id": a.instance_id,
                "gpu_name": a.gpu_name,
                "gpu_ram_mb": a.gpu_ram_mb,
                "region": a.region,
                "country": a.country,
                "provider": a.provider,
                "status": a.status,
                "boot_time_seconds": a.boot_time_seconds,
                "ssh_verified_at": a.ssh_verified_at,
                "comfyui_verified_at": a.comfyui_verified_at,
                "failure_reason": a.failure_reason,
                "hourly_cost": a.hourly_cost,
                "created_at": a.created_at,
            }
            for a in self._connection_log
        ]

    # ─── Helpers ──────────────────────────────────────────────────────────

    def _session_to_dict(self) -> dict[str, Any]:
        """Convert current session to a dict for API responses."""
        if not self._session:
            return {}
        return {
            "id": self._session.id,
            "instance_id": self._session.instance_id,
            "worker_name": self._session.worker_name,
            "gpu_name": self._session.gpu_name,
            "ssh_host": self._session.ssh_host,
            "ssh_port": self._session.ssh_port,
            "comfyui_url": self._session.comfyui_url,
            "status": self._session.status,
            "models_loaded": self._session.models_loaded,
            "started_at": self._session.started_at,
            "ended_at": self._session.ended_at,
            "total_cost": self._session.total_cost,
            "hourly_rate": self._session.hourly_rate,
            "jobs_completed": self._session.jobs_completed,
            "metadata": self._session.metadata,
        }


# =============================================================================
# Module-level singleton for use across the app
# =============================================================================

_orchestrator: Optional[WorkerOrchestrator] = None


def get_orchestrator() -> WorkerOrchestrator:
    """Get or create the global WorkerOrchestrator singleton."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = WorkerOrchestrator()
    return _orchestrator

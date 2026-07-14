"""Worker Orchestrator — Manages the lifecycle of GPU workers.

Responsibilities:
- Launch workers via Connection Race Mode
- Track connection attempts and session history
- Set up ComfyUI (install, pull models, start)
- Maintain persistent primary worker connection
- Report live status for dashboard consumption
- Provide start/stop/status/history interface

Status lifecycle:
    pending → booting → installing → downloading_model → starting_comfyui → ready → generating → error
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from backend.infrastructure.connection_race import (
    ConnectionRace,
    RaceConfig,
    RaceResult,
)
from backend.providers.vast.client import VastClient

logger = logging.getLogger(__name__)


# =============================================================================
# Data Models
# =============================================================================


@dataclass
class ConnectionAttempt:
    """Record of a single connection attempt (for history/learning)."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    offer_id: int = 0
    instance_id: int | None = None
    gpu_name: str = ""
    gpu_ram_mb: int = 0
    region: str = ""
    country: str = ""
    provider: str = "vast_ai"
    status: str = "pending"  # success, failed, timeout
    boot_time_seconds: float | None = None
    ssh_verified_at: str | None = None
    comfyui_verified_at: str | None = None
    failure_reason: str | None = None
    hourly_cost: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class WorkerSession:
    """An active worker session (the primary connection)."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    instance_id: int | None = None
    worker_name: str = ""
    gpu_name: str = ""
    ssh_host: str = ""
    ssh_port: int = 0
    comfyui_url: str | None = None
    status: str = "pending"
    progress_message: str = ""
    models_loaded: list[str] = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    ended_at: str | None = None
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

    def __init__(self, vast_client: VastClient | None = None) -> None:
        self._client = vast_client
        self._session: WorkerSession | None = None
        self._connection_log: list[ConnectionAttempt] = []
        self._race: ConnectionRace | None = None
        self._tunnel_process: subprocess.Popen | None = None
        # Attempt to reconnect to any existing running instance
        self._try_reconnect()

    def _try_reconnect(self) -> None:
        """Check for existing running Vast.ai instances and reconnect session.

        Called on startup to recover state after a backend restart.
        SINGLE INSTANCE POLICY: If multiple instances are running, keeps the
        best one (by GPU priority: A100 > 4090 > 3090) and destroys the rest.
        """
        try:
            client = self._get_client()
            instances = client.get_instances()

            # Find all running/loading instances
            active = [i for i in instances if i.get("actual_status") in ("running", "loading")]

            if not active:
                # Check for paused instances we can reconnect to
                paused = [i for i in instances if i.get("actual_status") in ("stopped", "exited")]
                if paused:
                    inst = paused[0]
                    self._session = WorkerSession(
                        instance_id=inst.get("id"),
                        worker_name=f"vast-paused-{inst.get('id')}",
                        gpu_name=inst.get("gpu_name", "Unknown"),
                        ssh_host=inst.get("ssh_host", ""),
                        ssh_port=inst.get("ssh_port", 0),
                        status="paused",
                        hourly_rate=inst.get("dph_total", 0),
                        metadata={"reconnected": True, "original_status": "paused"},
                    )
                    logger.info(f"Found paused instance {inst.get('id')} ({inst.get('gpu_name')})")
                return

            # SINGLE INSTANCE POLICY: Keep the best GPU, destroy others
            if len(active) > 1:
                logger.warning(
                    f"Found {len(active)} running instances — enforcing single instance policy"
                )
                # Sort by GPU priority: A100 > A6000 > 4090 > 3090 > others
                GPU_PRIORITY = {"A100": 0, "A6000": 1, "RTX 4090": 2, "RTX 4080": 3, "RTX 3090": 4}
                active.sort(key=lambda i: GPU_PRIORITY.get(i.get("gpu_name", ""), 99))

                # Keep the best, destroy the rest
                keeper = active[0]
                for inst in active[1:]:
                    iid = inst.get("id")
                    logger.info(f"Destroying extra instance {iid} ({inst.get('gpu_name')})")
                    try:
                        client.destroy_instance(iid)
                    except Exception as e:
                        logger.warning(f"Failed to destroy instance {iid}: {e}")

                active = [keeper]

            # Reconnect to the single active instance
            inst = active[0]
            status = inst.get("actual_status", "running")
            self._session = WorkerSession(
                instance_id=inst.get("id"),
                worker_name=f"vast-reconnected-{inst.get('id')}",
                gpu_name=inst.get("gpu_name", "Unknown"),
                ssh_host=inst.get("ssh_host", ""),
                ssh_port=inst.get("ssh_port", 0),
                status="ready" if status == "running" else "booting",
                hourly_rate=inst.get("dph_total", 0),
                metadata={"reconnected": True, "original_status": status},
            )
            logger.info(
                f"Reconnected to instance {inst.get('id')} ({inst.get('gpu_name')}) on startup"
            )
        except Exception as e:
            # Don't crash on reconnect failure — just start fresh
            logger.debug(f"Reconnect check skipped: {e}")

    @property
    def session(self) -> WorkerSession | None:
        """Current active session, if any."""
        return self._session

    @property
    def is_active(self) -> bool:
        """Whether there's an active worker session."""
        return self._session is not None and self._session.status not in (
            "stopped",
            "error",
            "destroyed",
        )

    def _get_client(self) -> VastClient:
        """Lazily initialize the Vast client."""
        if not self._client:
            self._client = VastClient()
        return self._client

    def _now_iso(self) -> str:
        return datetime.now(UTC).isoformat()

    # ─── Launch ───────────────────────────────────────────────────────────

    def launch_worker(
        self,
        max_price: float = 1.50,
        min_vram_gb: float = 12.0,
        num_candidates: int = 3,
        gpu_filter: str | None = None,
        excluded_hosts: list[int] | None = None,
        disk_gb: int = 80,
        timeout: int = 600,
        setup_comfyui: bool = True,
    ) -> dict[str, Any]:
        """Launch a worker using Connection Race Mode (async — returns immediately).

        The actual boot happens in a background thread. Poll GET /status
        to track progress through: pending → booting → installing → ready.

        Returns immediately with session_id for tracking.
        """
        if self.is_active:
            return {
                "status": "already_active",
                "message": "A worker session is already active. Stop it first.",
                "session": self._session_to_dict(),
            }

        # If already pending/booting, return current status
        if self._session and self._session.status in ("pending", "booting", "installing",
                                                       "downloading_model", "starting_comfyui"):
            return {
                "status": "launching",
                "message": self._session.progress_message or "Boot in progress...",
                "session": self._session_to_dict(),
            }

        # Create new session in pending state — return immediately
        self._session = WorkerSession(status="pending", progress_message="Finding best GPU...")
        session_id = self._session.id
        logger.info("Launch requested — starting background boot...")

        # Run the actual boot in a background thread
        config = RaceConfig(
            max_price=max_price,
            min_vram_gb=min_vram_gb,
            num_candidates=num_candidates,
            gpu_filter=gpu_filter,
            excluded_hosts=excluded_hosts or [],
            disk_gb=disk_gb,
            timeout=timeout,
        )

        thread = threading.Thread(
            target=self._boot_worker_background,
            args=(config, setup_comfyui),
            daemon=True,
            name="worker-boot",
        )
        thread.start()

        return {
            "status": "pending",
            "message": "Worker launch started. Poll /status for progress.",
            "session_id": session_id,
            "session": self._session_to_dict(),
        }

    def _boot_worker_background(self, config: RaceConfig, setup_comfyui: bool) -> None:
        """Background thread: runs connection race + ComfyUI setup.

        Updates self._session.status and progress_message as it goes.
        The frontend polls /status to see progress.
        """
        try:
            # Phase 1: Connection Race
            self._session.status = "booting"
            self._session.progress_message = "Launching GPU instances..."

            self._race = ConnectionRace(self._get_client())
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
                    status="success"
                    if candidate.status == "won"
                    else ("timeout" if candidate.status == "timeout" else "failed"),
                    boot_time_seconds=candidate.boot_time_seconds,
                    ssh_verified_at=self._now_iso() if candidate.ssh_verified else None,
                    failure_reason=candidate.failure_reason,
                    hourly_cost=candidate.hourly_cost,
                )
                self._connection_log.append(attempt)

            if not race_result.success or not race_result.winner:
                self._session.status = "error"
                self._session.progress_message = race_result.error or "No GPU available"
                self._session.metadata["error"] = race_result.error
                logger.error(f"Connection race failed: {race_result.error}")
                return

            # Configure session from winner
            winner = race_result.winner
            self._session.instance_id = winner.instance_id
            self._session.gpu_name = winner.gpu_name
            self._session.ssh_host = winner.ssh_host or ""
            self._session.ssh_port = winner.ssh_port or 0
            self._session.hourly_rate = winner.hourly_cost
            self._session.worker_name = (
                f"vast-{winner.gpu_name.replace(' ', '-').lower()}-{winner.instance_id}"
            )
            self._session.progress_message = f"Connected to {winner.gpu_name}!"
            self._session.metadata.update(
                {
                    "offer_id": winner.offer_id,
                    "region": winner.region,
                    "country": winner.country,
                    "boot_time_seconds": winner.boot_time_seconds,
                    "race_candidates": len(race_result.candidates),
                    "race_time_seconds": race_result.total_time_seconds,
                }
            )

            logger.info(
                f"Race won: {winner.gpu_name} (instance {winner.instance_id}) "
                f"in {winner.boot_time_seconds:.1f}s"
            )

            # Phase 2: ComfyUI Setup
            if setup_comfyui:
                self._setup_comfyui()
            else:
                self._session.status = "ready"
                self._session.progress_message = "Worker ready (no ComfyUI setup)"

            if self._session.status == "ready":
                logger.info(
                    f"Worker ready: {self._session.worker_name} "
                    f"({self._session.gpu_name}) @ {self._session.ssh_host}:{self._session.ssh_port}"
                )

        except Exception as e:
            logger.error(f"Background boot failed: {e}")
            if self._session:
                self._session.status = "error"
                self._session.progress_message = f"Boot failed: {str(e)[:100]}"
                self._session.metadata["error"] = str(e)

    # ─── ComfyUI Setup ────────────────────────────────────────────────────

    def _setup_comfyui(self) -> None:
        """Install and start ComfyUI on the worker via SSH.

        Steps:
        1. Install ComfyUI + pip requirements
        2. Download SDXL Turbo from HuggingFace (fast on datacenter)
        3. Start ComfyUI server (background)
        4. Create local SSH tunnel (localhost:8188 → worker:8188)
        5. Verify ComfyUI responds
        """
        if not self._session:
            return

        ssh_key = os.path.expanduser("~/.ssh/id_ed25519")
        ssh_target = f"root@{self._session.ssh_host}"
        ssh_port = str(self._session.ssh_port)

        base_ssh_cmd = [
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-i",
            ssh_key,
            "-p",
            ssh_port,
            ssh_target,
        ]

        def _ssh_exec(command: str, step_name: str, timeout: int = 600) -> bool:
            """Execute a command on the remote worker via SSH."""
            try:
                result = subprocess.run(
                    base_ssh_cmd + [command],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                if result.returncode != 0:
                    logger.warning(f"SSH {step_name} failed: {result.stderr[:200]}")
                    return False
                return True
            except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                logger.warning(f"SSH {step_name} error: {e}")
                return False

        # Check if this is a RunPod pod with persistent volume
        # If ComfyUI is already installed, skip the install step
        self._session.metadata.get("provider") == "runpod"

        def _check_installed(path: str) -> bool:
            """Check if a path exists on the remote worker."""
            result = subprocess.run(
                base_ssh_cmd + [f"test -d {path} && echo 'exists' || echo 'missing'"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            return "exists" in result.stdout

        comfyui_installed = _check_installed("/workspace/ComfyUI")

        if comfyui_installed:
            logger.info("ComfyUI already installed on persistent volume — skipping install")
            self._session.status = "starting_comfyui"
            self._session.progress_message = "ComfyUI found — starting server..."

        # Step 1: Install ComfyUI (skip if already present on persistent volume)
        if not comfyui_installed:
            self._session.status = "installing"
            self._session.progress_message = "Installing ComfyUI on GPU worker..."
            logger.info("Installing ComfyUI on worker...")
            install_cmd = (
                "cd /workspace && "
                "git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git 2>/dev/null || true && "
                "cd ComfyUI && pip install -q -r requirements.txt && pip install -q huggingface-hub && "
                "mkdir -p models/checkpoints models/loras models/vae input output"
            )
            _ssh_exec(install_cmd, "install_comfyui")
        else:
            logger.info("Skipping ComfyUI install — already present")

        # Step 2: Download model from HuggingFace (datacenter speed)
        self._session.status = "downloading_model"
        self._session.progress_message = "Downloading AI model (datacenter speed)..."
        logger.info("Downloading SDXL Turbo model...")
        hf_token = os.getenv("HF_TOKEN", "")
        dl_cmd = (
            f"cd /workspace/ComfyUI/models/checkpoints && "
            f'python -c "from huggingface_hub import hf_hub_download; '
            f"hf_hub_download('stabilityai/sdxl-turbo', 'sd_xl_turbo_1.0_fp16.safetensors', "
            f"local_dir='.', token='{hf_token}' or None)\""
        )
        if not _ssh_exec(dl_cmd, "model_download"):
            logger.warning("Model download failed — worker will have no models")

        # Step 3: Start ComfyUI in background
        self._session.status = "starting_comfyui"
        self._session.progress_message = "Starting ComfyUI generation engine..."
        logger.info("Starting ComfyUI...")
        # Use setsid + disown to fully detach from SSH session
        start_cmd = (
            "cd /workspace/ComfyUI && "
            "setsid python main.py --listen 0.0.0.0 --port 8188 "
            "</dev/null > /tmp/comfyui.log 2>&1 & disown"
        )
        _ssh_exec(start_cmd, "start_comfyui", timeout=30)
        time.sleep(10)  # Give it time to start

        # Step 4: Create SSH tunnel (localhost:8188 → worker:8188)
        logger.info("Creating SSH tunnel...")
        tunnel_cmd = [
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-i",
            ssh_key,
            "-p",
            ssh_port,
            "-N",
            "-L",
            "8188:127.0.0.1:8188",
            ssh_target,
        ]
        self._tunnel_process = subprocess.Popen(
            tunnel_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        time.sleep(3)

        # Step 5: Verify ComfyUI responds
        import httpx

        comfy_url = "http://localhost:8188"
        for _attempt in range(5):
            try:
                resp = httpx.get(f"{comfy_url}/system_stats", timeout=5)
                if resp.status_code == 200:
                    self._session.comfyui_url = comfy_url
                    self._session.status = "ready"
                    self._session.models_loaded.append("sd_xl_turbo_1.0_fp16.safetensors")
                    logger.info("ComfyUI is ONLINE and ready for generation!")
                    return
            except Exception:
                time.sleep(5)

        # If we get here, ComfyUI didn't respond but worker is up
        self._session.comfyui_url = comfy_url
        self._session.status = "ready"
        logger.warning("ComfyUI may not be fully ready yet — tunnel is up")

        # Step 2: Download model from B2 cache using presigned URL
        self._session.status = "downloading_model"
        try:
            from backend.providers.vast.model_cache import (
                get_cache_download_url,
                model_exists_in_cache,
            )

            # Try to get a presigned URL for SDXL Turbo (primary test model)
            model_filename = "sd_xl_turbo_1.0_fp16.safetensors"
            if model_exists_in_cache("checkpoint", model_filename):
                presigned_url = get_cache_download_url(
                    "checkpoint", model_filename, expires_in=3600
                )
                if presigned_url:
                    download_cmd = (
                        f"mkdir -p /workspace/ComfyUI/models/checkpoints && "
                        f"curl -sL -o /workspace/ComfyUI/models/checkpoints/{model_filename} "
                        f"'{presigned_url}'"
                    )
                    if _ssh_exec(download_cmd, "model_download_b2"):
                        self._session.models_loaded.append(model_filename)
                        logger.info(f"Model downloaded from B2 via presigned URL: {model_filename}")
                    else:
                        logger.warning("B2 presigned URL download failed, model not loaded")
                else:
                    logger.warning("Could not generate presigned URL for model")
            else:
                logger.info("SDXL Turbo not in B2 cache, skipping model download")
        except Exception as e:
            logger.warning(f"Model download setup failed: {e}")

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
        """Get current worker/session status with progress info.

        Returns live status suitable for dashboard polling.
        Frontend should poll this every 5s during boot.
        """
        if not self._session:
            return {
                "active": False,
                "status": "no_session",
                "message": "No active worker session",
                "progress_message": "",
            }

        # Calculate running cost
        if self._session.status not in ("stopped", "error", "destroyed", "pending"):
            started = datetime.fromisoformat(self._session.started_at)
            elapsed_hours = (datetime.now(UTC) - started).total_seconds() / 3600
            self._session.total_cost = round(elapsed_hours * self._session.hourly_rate, 4)

        return {
            "active": self.is_active,
            "progress_message": self._session.progress_message,
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

        # Kill SSH tunnel if running
        if self._tunnel_process:
            try:
                self._tunnel_process.terminate()
                self._tunnel_process = None
                logger.info("SSH tunnel terminated")
            except Exception:
                pass

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
        duration_seconds = (ended - started).total_seconds()
        elapsed_hours = duration_seconds / 3600
        self._session.total_cost = round(elapsed_hours * self._session.hourly_rate, 4)

        # Record cost in the Cost Intelligence tracker
        try:
            from backend.infrastructure.cost_intelligence import get_cost_tracker

            tracker = get_cost_tracker()
            tracker.record_session_cost(
                session_id=self._session.id,
                hourly_rate=self._session.hourly_rate,
                duration_seconds=duration_seconds,
                gpu_name=self._session.gpu_name,
                provider="vast_ai",
                jobs_completed=self._session.jobs_completed,
                start_time=self._session.started_at,
                end_time=self._session.ended_at,
            )
        except Exception as e:
            logger.warning(f"Failed to record session cost: {e}")

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
            "progress_message": self._session.progress_message,
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

_orchestrator: WorkerOrchestrator | None = None


def get_orchestrator() -> WorkerOrchestrator:
    """Get or create the global WorkerOrchestrator singleton."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = WorkerOrchestrator()
    return _orchestrator

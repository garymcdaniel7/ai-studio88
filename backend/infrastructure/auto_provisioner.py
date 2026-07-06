"""Auto-Provisioner — Automatically launches GPU workers when jobs queue up.

Logic:
1. A job is submitted (generation, training, video)
2. Check if an available worker exists with matching specialty
3. If no worker available AND auto_provision is enabled:
   a. Check fleet settings (max instances, budget, cool-down)
   b. If allowed: launch a new worker on the preferred provider
   c. If not allowed: queue the job and return "queued" status

This module is called by job submission endpoints to decide whether
to provision infrastructure on-demand.

Vendor selection strategy:
- Training jobs → prefer RunPod (persistent volume, no reinstall)
- Image/video jobs → prefer Vast.ai (cheaper, ephemeral OK)
- If preferred provider is unavailable → fall back to other
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Optional

from backend.infrastructure.fleet_settings import get_fleet_settings
from backend.infrastructure.worker_registry import get_worker_registry, WorkerInstance

logger = logging.getLogger(__name__)


class AutoProvisioner:
    """Decides whether to launch a new GPU worker for incoming jobs."""

    def __init__(self):
        self._provisioning_lock = threading.Lock()
        self._last_provision_attempt: Optional[float] = None

    def check_and_provision(
        self,
        job_type: str = "image",
        required_vram_gb: int = 0,
    ) -> dict:
        """Check if a worker is available; if not, attempt auto-provision.

        Args:
            job_type: Type of job (image, training, video, general)
            required_vram_gb: Minimum VRAM needed (0 = use fleet default)

        Returns:
            {
                "worker_available": bool,
                "worker_id": str | None,
                "provisioning": bool,
                "reason": str,
            }
        """
        settings = get_fleet_settings()
        registry = get_worker_registry()

        # Map job type to worker specialty
        specialty = self._map_specialty(job_type)
        min_vram = max(required_vram_gb, self._get_vram_requirement(job_type))

        # 1. Check if a worker is already available with enough VRAM
        worker = registry.get_available_worker(specialty)
        if worker and worker.vram_gb >= min_vram:
            worker.mark_active()
            return {
                "worker_available": True,
                "worker_id": worker.id,
                "provisioning": False,
                "reason": f"Worker {worker.id} available ({worker.gpu_name}, {worker.vram_gb}GB)",
            }
        elif worker and worker.vram_gb < min_vram:
            # Worker exists but doesn't have enough VRAM for this job
            pass  # Fall through to auto-provision

        # 2. Check if auto-provision is enabled
        if not settings.config.auto_provision:
            return {
                "worker_available": False,
                "worker_id": None,
                "provisioning": False,
                "reason": "No available worker. Auto-provision is disabled.",
            }

        # 3. Check if we can launch (budget, max instances, cool-down)
        can_launch, reason = settings.can_launch(registry.active_count)
        if not can_launch:
            return {
                "worker_available": False,
                "worker_id": None,
                "provisioning": False,
                "reason": f"Cannot auto-provision: {reason}",
            }

        # 4. Attempt to provision in background
        with self._provisioning_lock:
            # Double-check (another thread may have started provisioning)
            if self._last_provision_attempt and (time.time() - self._last_provision_attempt) < 30:
                return {
                    "worker_available": False,
                    "worker_id": None,
                    "provisioning": True,
                    "reason": "Provisioning already in progress",
                }

            self._last_provision_attempt = time.time()

        # Launch in background thread
        thread = threading.Thread(
            target=self._provision_worker,
            args=(job_type, specialty, required_vram_gb or settings.config.min_vram_gb),
            daemon=True,
        )
        thread.start()

        return {
            "worker_available": False,
            "worker_id": None,
            "provisioning": True,
            "reason": f"Auto-provisioning a {specialty} worker...",
        }

    def _map_specialty(self, job_type: str) -> str:
        """Map job type to worker specialty."""
        mapping = {
            "image": "image",
            "image_generation": "image",
            "video": "video",
            "video_generation": "video",
            "training": "training",
            "lora_training": "training",
            "upscale": "image",
        }
        return mapping.get(job_type, "general")

    def _get_vram_requirement(self, job_type: str) -> int:
        """Get minimum VRAM for this job type."""
        requirements = {
            "image": 12,
            "image_generation": 12,
            "video": 80,
            "video_generation": 80,
            "training": 24,
            "lora_training": 24,
            "upscale": 12,
        }
        return requirements.get(job_type, 12)

    def _get_max_price(self, job_type: str) -> float:
        """Get max hourly price for this job type."""
        settings = get_fleet_settings()
        base_price = settings.config.max_price_per_hour

        # Video needs expensive GPUs (A100/H100) — allow higher price
        if job_type in ("video", "video_generation"):
            return max(base_price, 3.50)  # A100 80GB typically ~$2-3/hr
        # Training can be expensive too
        if job_type in ("training", "lora_training"):
            return max(base_price, 2.00)

        return base_price

    def _select_provider(self, job_type: str) -> str:
        """Select the best provider for this job type."""
        settings = get_fleet_settings()
        preferred = settings.config.preferred_provider

        # Training prefers RunPod (persistent volume)
        if job_type in ("training", "lora_training"):
            if os.getenv("RUNPOD_API_KEY"):
                return "runpod"

        return preferred

    def _provision_worker(self, job_type: str, specialty: str, min_vram_gb: int) -> None:
        """Background: launch a new GPU worker."""
        settings = get_fleet_settings()
        registry = get_worker_registry()
        provider = self._select_provider(job_type)

        # Use job-type-specific VRAM if no explicit requirement was passed
        effective_vram = max(min_vram_gb, self._get_vram_requirement(job_type))
        max_price = self._get_max_price(job_type)

        logger.info(
            f"Auto-provisioning {specialty} worker on {provider} "
            f"(min {effective_vram}GB VRAM, max ${max_price:.2f}/hr)..."
        )

        try:
            if provider == "vast":
                worker = self._launch_vast(specialty, effective_vram, max_price)
            elif provider == "runpod":
                worker = self._launch_runpod(specialty, effective_vram)
            else:
                logger.warning(f"Unknown provider: {provider}")
                return

            if worker:
                registry.register_worker(worker)
                settings.record_launch()
                logger.info(f"Auto-provisioned worker {worker.id} ({worker.gpu_name}) on {provider}")
            else:
                logger.warning(
                    f"No {effective_vram}GB+ GPU available on {provider} under ${max_price:.2f}/hr. "
                    f"{'Video requires A100 80GB or H100.' if specialty == 'video' else ''}"
                )

        except Exception as e:
            logger.error(f"Auto-provision failed: {e}")

    def _launch_vast(self, specialty: str, min_vram_gb: int, max_price: float) -> Optional[WorkerInstance]:
        """Launch a worker on Vast.ai."""
        import json
        import httpx

        api_key = os.getenv("VAST_API_KEY", "")
        if not api_key:
            return None

        # Query for available offers
        query = {
            "rentable": {"eq": True},
            "gpu_ram": {"gte": min_vram_gb * 1024},
            "dph_total": {"lte": max_price},
            "disk_space": {"gte": 50},
            "reliability2": {"gte": 0.9},
        }

        try:
            resp = httpx.get(
                "https://console.vast.ai/api/v0/bundles/",
                headers={"Authorization": f"Bearer {api_key}"},
                params={"q": json.dumps(query)},
                timeout=30,
                follow_redirects=True,
            )
            if resp.status_code != 200:
                return None

            data = resp.json()
            offers = data.get("offers", data) if isinstance(data, dict) else data
            if not isinstance(offers, list) or not offers:
                return None

            # Filter out Blackwell GPUs
            offers = [o for o in offers if "5090" not in o.get("gpu_name", "") and "5080" not in o.get("gpu_name", "")]
            if not offers:
                return None

            # Sort by price, try cheapest first
            offers.sort(key=lambda o: o.get("dph_total", 999))

            for offer in offers[:5]:
                try:
                    launch_resp = httpx.put(
                        f"https://console.vast.ai/api/v0/asks/{offer['id']}/",
                        headers={"Authorization": f"Bearer {api_key}"},
                        json={
                            "client_id": "me",
                            "image": "pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime",
                            "disk": 80,
                            "runtype": "ssh",
                        },
                        timeout=30,
                        follow_redirects=True,
                    )
                    if launch_resp.status_code in (200, 201):
                        result = launch_resp.json()
                        instance_id = str(result.get("new_contract", ""))
                        return WorkerInstance(
                            provider="vast",
                            provider_instance_id=instance_id,
                            gpu_name=offer.get("gpu_name", ""),
                            vram_gb=offer.get("gpu_ram", 0) // 1024,
                            specialty=specialty,
                            status="provisioning",
                            hourly_rate=offer.get("dph_total", 0),
                        )
                except Exception:
                    continue

        except Exception as e:
            logger.error(f"Vast.ai launch error: {e}")

        return None

    def _launch_runpod(self, specialty: str, min_vram_gb: int) -> Optional[WorkerInstance]:
        """Launch a worker on RunPod."""
        try:
            from backend.providers.runpod.client import RunPodClient
            client = RunPodClient()

            # Find a suitable GPU type
            gpu_types = client.filter_gpu_types(min_vram_gb=min_vram_gb)
            if not gpu_types:
                return None

            # Pick cheapest
            gpu_types.sort(key=lambda g: g.get("communityPrice", 999))
            gpu = gpu_types[0]

            pod = client.launch_pod(
                gpu_type_id=gpu.get("id", ""),
                name=f"ai-studio-{specialty}",
                ports="8188/http,22/tcp",
            )

            return WorkerInstance(
                provider="runpod",
                provider_instance_id=pod.get("id", ""),
                gpu_name=gpu.get("displayName", ""),
                vram_gb=gpu.get("memoryInGb", 0),
                specialty=specialty,
                status="provisioning",
                hourly_rate=gpu.get("communityPrice", 0),
            )
        except Exception as e:
            logger.error(f"RunPod launch error: {e}")
            return None


# Singleton
_provisioner: Optional[AutoProvisioner] = None


def get_auto_provisioner() -> AutoProvisioner:
    global _provisioner
    if _provisioner is None:
        _provisioner = AutoProvisioner()
    return _provisioner

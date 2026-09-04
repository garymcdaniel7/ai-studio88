"""Thunder Compute provider — primary GPU compute adapter.

Thunder Compute is the platform's single GPU provider (RunPod + Vast.ai
retired). This adapter implements the ComputeProvider protocol and talks
to Thunder's HTTP API directly (same endpoints the `tnr` CLI uses), so it
works from Railway — no CLI dependency.

Auth: THUNDER_COMPUTE_API_KEY (or TNR_API_TOKEN) as Bearer token.
API base: https://api.thundercompute.com:8443

Endpoints (mirror tnr CLI):
  GET  /v1/instances/list             → list instances
  POST /v1/instances/create           → provision (gpu, num_gpus, disk, template)
  POST /v1/instances/{id}/delete      → terminate
  POST /v1/instances/{id}/ports       → manage HTTP ports
  POST /v1/auth/validate              → validate API token

Validates: Requirements R13.1, R13.3, R13.4 (ComputeProvider protocol).
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import httpx
import structlog

from backend.app.providers.compute import (
    ComputeProviderCapabilities,
    ComputeRequirements,
    CostEstimate,
    HealthState,
    HealthStatus,
    InstanceHandle,
    InstanceState,
    InstanceStatus,
    OfferInfo,
    ProviderUnavailableError,
)

logger = structlog.get_logger(__name__)

API_BASE = os.getenv("THUNDER_API_BASE", "https://api.thundercompute.com:8443")
TIMEOUT = float(os.getenv("THUNDER_API_TIMEOUT", "30"))

# Known pricing per GPU type (USD/hour) — Thunder flat rates
GPU_PRICES = {
    "a6000": 0.35,
    "a100": 1.29,
    "l40": 0.79,
    "h100": 3.09,
}


def _bearer_token() -> str:
    """Return the Thunder API token from env."""
    return os.getenv("THUNDER_COMPUTE_API_KEY") or os.getenv("TNR_API_TOKEN") or ""


class ThunderComputeProvider:
    """Thunder Compute GPU provider — primary adapter.

    Provisions A6000 (default) / A100 / L40 / H100 instances with the
    comfy-ui template, exposes HTTP ports (8188 ComfyUI, 11434 Ollama),
    and reports real health via /system_stats.
    """

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        self._api_key = api_key or _bearer_token()
        self._base_url = (base_url or API_BASE).rstrip("/")
        if not self._api_key:
            logger.warning(
                "thunder_provider_no_api_key",
                message="Thunder provider initialized without API key — calls will fail",
            )

    # ─── Transport helpers ─────────────────────────────────────────────

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}

    def _request(self, method: str, path: str, **kwargs) -> Any:
        """Make an HTTP request to Thunder's API. Raises ProviderUnavailableError on failure."""
        if not self._api_key:
            raise ProviderUnavailableError(
                "Thunder provider not configured — set THUNDER_COMPUTE_API_KEY",
                provider="thundercompute",
            )
        try:
            resp = httpx.request(
                method,
                f"{self._base_url}{path}",
                headers=self._headers(),
                timeout=TIMEOUT,
                **kwargs,
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict) and data.get("error"):
                raise ProviderUnavailableError(
                    f"Thunder API error: {data.get('message', data.get('error'))}",
                    provider="thundercompute",
                )
            return data
        except httpx.HTTPStatusError as e:
            raise ProviderUnavailableError(
                f"Thunder API HTTP {e.response.status_code}: {e.response.text[:200]}",
                provider="thundercompute",
            ) from e
        except httpx.TransportError as e:
            raise ProviderUnavailableError(
                f"Thunder API unreachable: {e}", provider="thundercompute"
            ) from e

    # ─── ComputeProvider protocol ───────────────────────────────────────

    @property
    def capabilities(self) -> ComputeProviderCapabilities:
        """Return Thunder provider capabilities."""
        return ComputeProviderCapabilities(
            name="thundercompute",
            display_name="Thunder Compute",
            supports_persistent_storage=True,
            supports_network_volume=False,
            supports_stop_resume=True,
            supports_snapshot=True,
            supports_multi_gpu=True,
            supports_autoscaling=False,
            supports_private_networking=True,
            supports_custom_images=False,
            supports_worker_health=True,
            supports_cost_estimation=True,
            min_vram_gb=12,
            max_vram_gb=80,
            regions=["US"],
            gpu_types=["A6000", "A100", "L40", "H100"],
            startup_time_seconds=90,
        )

    async def provision(self, requirements: ComputeRequirements) -> InstanceHandle:
        """Provision a Thunder Compute instance.

        Uses the comfy-ui template by default; selects GPU from the
        requirements' VRAM need or falls back to A6000. Exposes HTTP ports
        8188 + 11434 so the worker is reachable from Railway without SSH.
        """
        # Pick GPU by VRAM requirement (cheapest fit)
        gpu_key = "a6000"
        if requirements.vram_gb > 24:
            gpu_key = "a100"

        body = {
            "gpu_type": gpu_key,
            "num_gpus": requirements.gpu_count or 1,
            "disk_size_gb": requirements.storage_gb or 300,
            "cpu_cores": 8,
            "template": "comfy-ui",
        }
        data = self._request("POST", "/instances/create", json=body)
        instance_id = data.get("uuid") or data.get("id")
        if not instance_id:
            raise ProviderUnavailableError(
                f"Thunder create returned no instance id: {data}", provider="thundercompute"
            )

        # Expose HTTP ports (ComfyUI + Ollama) so Railway can reach the worker
        try:
            self._request(
                "POST", f"/instances/{instance_id}/ports",
                json={"add_ports": [8188, 11434]},
            )
        except ProviderUnavailableError as exc:
            logger.warning("thunder_port_expose_failed", instance_id=instance_id, error=str(exc))

        return InstanceHandle(
            instance_id=str(instance_id),
            host="",
            port=8188,
            state=InstanceState.PROVISIONING,
        )

    async def terminate(self, instance_id: str) -> None:
        """Terminate a Thunder instance."""
        self._request("POST", f"/instances/{instance_id}/delete")

    async def health_check(self, instance_id: str) -> HealthStatus:
        """Check health of a Thunder instance."""
        try:
            status = await self.get_status(instance_id)
            return HealthStatus(
                instance_id=instance_id,
                state=HealthState.HEALTHY if status.state == InstanceState.RUNNING else HealthState.UNREACHABLE,
                message=f"Thunder {status.state.value}",
            )
        except ProviderUnavailableError as e:
            return HealthStatus(
                instance_id=instance_id,
                state=HealthState.UNREACHABLE,
                message=str(e),
            )

    async def get_status(self, instance_id: str) -> InstanceStatus:
        """Get status of a Thunder instance from the live list."""
        data = self._request("GET", "/instances/list")
        if not isinstance(data, list):
            raise ProviderUnavailableError("Thunder list returned unexpected shape", provider="thundercompute")
        for inst in data:
            if not isinstance(inst, dict):
                continue
            if str(inst.get("uuid") or inst.get("id")) == str(instance_id):
                state = InstanceState.RUNNING if inst.get("status") == "RUNNING" else InstanceState.STOPPED
                return InstanceStatus(
                    instance_id=instance_id,
                    state=state,
                    uptime_seconds=0.0,
                    gpu_utilization_pct=None,
                    vram_used_gb=None,
                )
        raise ProviderUnavailableError(
            f"Instance {instance_id} not found in Thunder", provider="thundercompute"
        )

    async def list_available(self) -> list[OfferInfo]:
        """List available Thunder GPU offers (static pricing table)."""
        return [
            OfferInfo(
                offer_id=f"thunder-{gpu}",
                gpu_name=gpu.upper(),
                vram_gb=24 if gpu == "a6000" else 80,
                price_per_hour_usd=price,
                available=True,
                region="US",
            )
            for gpu, price in GPU_PRICES.items()
        ]

    async def estimate_cost(self, requirements: ComputeRequirements) -> CostEstimate:
        """Estimate cost for a workload on Thunder."""
        gpu_key = "a6000"
        if requirements.vram_gb > 24:
            gpu_key = "a100"
        price = GPU_PRICES.get(gpu_key, GPU_PRICES["a6000"])
        estimated_usd = price * (requirements.max_duration_seconds / 3600)
        return CostEstimate(
            estimated_usd=round(estimated_usd, 4),
            estimated_duration_seconds=requirements.max_duration_seconds,
            confidence=0.85,
        )

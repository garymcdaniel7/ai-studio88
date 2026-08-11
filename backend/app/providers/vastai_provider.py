"""Vast.ai compute provider — legacy adapter.

Wraps the existing VastClient from backend/providers/vast/ to conform
to the ComputeProvider protocol. Retained for backward compatibility
while the platform transitions to RunPod as the primary provider.

Validates: Requirements R13.1, R13.3, R13.4
"""

from __future__ import annotations

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
    ProvisionError,
    TerminateError,
)

logger = structlog.get_logger(__name__)


class VastAiProvider:
    """Vast.ai compute provider — legacy adapter.

    Wraps the existing VastClient to implement the ComputeProvider protocol.
    Vast.ai does NOT support persistent volumes, network volumes, stop/resume,
    or snapshots — these are reported as False in capabilities.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key
        self._client = None  # Lazy-initialized to avoid import errors in tests

    def _get_client(self):
        """Lazy-initialize the VastClient to avoid import at module level."""
        if self._client is None:
            try:
                from backend.providers.vast.client import VastClient

                self._client = VastClient(api_key=self._api_key)
            except Exception as exc:
                raise ProviderUnavailableError(
                    f"Failed to initialize Vast.ai client: {exc}",
                    provider="vastai",
                ) from exc
        return self._client

    @property
    def capabilities(self) -> ComputeProviderCapabilities:
        """Return Vast.ai provider capabilities (limited feature set)."""
        return ComputeProviderCapabilities(
            name="vastai",
            display_name="Vast.ai (Legacy)",
            supports_persistent_storage=False,
            supports_network_volume=False,
            supports_stop_resume=False,
            supports_snapshot=False,
            supports_multi_gpu=True,
            supports_autoscaling=False,
            supports_private_networking=False,
            supports_custom_images=True,
            supports_worker_health=False,
            supports_cost_estimation=True,
            min_vram_gb=8,
            max_vram_gb=80,
            regions=["US", "EU", "APAC"],
            gpu_types=[
                "RTX_3090",
                "RTX_4090",
                "A100_40GB",
                "A100_80GB",
                "H100",
            ],
            startup_time_seconds=180,
        )

    async def provision(self, requirements: ComputeRequirements) -> InstanceHandle:
        """Provision a Vast.ai instance.

        Uses the legacy VastClient to find an offer and launch an instance.
        """
        try:
            client = self._get_client()
            offers = client.filter_offers(
                min_vram_gb=requirements.vram_gb,
                min_disk_gb=requirements.storage_gb,
                num_gpus=requirements.gpu_count,
            )
            if not offers:
                raise ProvisionError(
                    f"No Vast.ai offers match requirements (vram={requirements.vram_gb}GB)",
                    provider="vastai",
                )

            # Select cheapest offer
            offers.sort(key=lambda o: o.get("dph_total", 999))
            offer = offers[0]

            result = client.launch_instance(
                offer_id=int(offer["id"]),
                disk_gb=requirements.storage_gb,
            )
            instance_id = str(result.get("new_contract", result.get("id", "")))

            logger.info(
                "vastai_instance_provisioned",
                instance_id=instance_id,
                gpu=offer.get("gpu_name"),
                price=offer.get("dph_total"),
            )

            return InstanceHandle(
                instance_id=instance_id,
                host="",  # SSH host resolved later via get_connection_info
                port=22,
                state=InstanceState.PROVISIONING,
            )

        except (ProvisionError, ProviderUnavailableError):
            raise
        except Exception as exc:
            raise ProvisionError(
                f"Vast.ai provisioning failed: {exc}", provider="vastai"
            ) from exc

    async def terminate(self, instance_id: str) -> None:
        """Terminate a Vast.ai instance."""
        try:
            client = self._get_client()
            client.destroy_instance(int(instance_id))
            logger.info("vastai_instance_terminated", instance_id=instance_id)
        except Exception as exc:
            raise TerminateError(
                f"Vast.ai terminate failed: {exc}", provider="vastai"
            ) from exc

    async def health_check(self, instance_id: str) -> HealthStatus:
        """Check health of a Vast.ai instance.

        Vast.ai has limited health reporting — we check instance state.
        """
        try:
            client = self._get_client()
            data = client.get_instance(int(instance_id))
            status = data.get("actual_status", "unknown")

            if status == "running":
                return HealthStatus(
                    instance_id=instance_id,
                    state=HealthState.HEALTHY,
                    message="Instance running",
                )
            elif status in ("loading", "starting"):
                return HealthStatus(
                    instance_id=instance_id,
                    state=HealthState.DEGRADED,
                    message=f"Instance state: {status}",
                )
            else:
                return HealthStatus(
                    instance_id=instance_id,
                    state=HealthState.UNHEALTHY,
                    message=f"Instance state: {status}",
                )

        except Exception as exc:
            return HealthStatus(
                instance_id=instance_id,
                state=HealthState.UNREACHABLE,
                message=f"Health check failed: {exc}",
            )

    async def get_status(self, instance_id: str) -> InstanceStatus:
        """Get current status of a Vast.ai instance."""
        try:
            client = self._get_client()
            data = client.get_instance(int(instance_id))
            status = data.get("actual_status", "unknown")

            state_map = {
                "running": InstanceState.RUNNING,
                "loading": InstanceState.PROVISIONING,
                "starting": InstanceState.PROVISIONING,
                "stopped": InstanceState.STOPPED,
                "exited": InstanceState.TERMINATED,
            }
            state = state_map.get(status, InstanceState.FAILED)

            return InstanceStatus(
                instance_id=instance_id,
                state=state,
                uptime_seconds=data.get("duration", 0.0),
                gpu_utilization_pct=data.get("gpu_util", None),
            )

        except Exception as exc:
            logger.warning(
                "vastai_get_status_failed",
                instance_id=instance_id,
                error=str(exc),
            )
            return InstanceStatus(
                instance_id=instance_id,
                state=InstanceState.FAILED,
            )

    async def list_available(self) -> list[OfferInfo]:
        """List available Vast.ai GPU offers."""
        try:
            client = self._get_client()
            offers = client.list_offers()
            return [
                OfferInfo(
                    offer_id=str(o.get("id", "")),
                    gpu_name=o.get("gpu_name", "Unknown"),
                    vram_gb=int(o.get("gpu_ram", 0) / 1024),
                    price_per_hour_usd=o.get("dph_total", 0.0),
                    available=True,
                    region=o.get("geolocation", ""),
                )
                for o in offers[:50]  # Limit to 50 results
            ]
        except Exception as exc:
            logger.warning(
                "vastai_list_available_failed",
                error=str(exc),
            )
            return []

    async def estimate_cost(self, requirements: ComputeRequirements) -> CostEstimate:
        """Estimate cost on Vast.ai based on current marketplace offers."""
        try:
            client = self._get_client()
            offers = client.filter_offers(
                min_vram_gb=requirements.vram_gb,
                num_gpus=requirements.gpu_count,
            )
            if not offers:
                # Fallback estimate
                rate = 0.50 * (requirements.vram_gb / 12)
            else:
                # Use cheapest matching offer
                offers.sort(key=lambda o: o.get("dph_total", 999))
                rate = offers[0].get("dph_total", 0.50)

            duration = requirements.max_duration_seconds
            total = rate * (duration / 3600)
            return CostEstimate(
                estimated_usd=round(total, 4),
                estimated_duration_seconds=duration,
                confidence=0.6,
            )
        except Exception:
            # If API call fails, return rough estimate
            rate = 0.50 * (requirements.vram_gb / 12)
            duration = requirements.max_duration_seconds
            total = rate * (duration / 3600)
            return CostEstimate(
                estimated_usd=round(total, 4),
                estimated_duration_seconds=duration,
                confidence=0.3,
            )

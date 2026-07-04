"""Connection Race Mode — Launch N instances in parallel, first to SSH wins.

Strategy:
1. Query Vast.ai for rentable offers matching criteria
2. Filter out unsupported GPUs (Blackwell architecture)
3. Launch num_candidates instances simultaneously
4. Poll every 15s checking for SSH availability
5. First instance to respond to SSH = winner
6. Immediately destroy all other candidates
7. Return winner's connection info
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx

from backend.providers.vast.client import VastClient, VastClientError

logger = logging.getLogger(__name__)

# Blackwell GPUs — PyTorch doesn't support these yet
BLACKWELL_GPUS = frozenset({
    "RTX 5090",
    "RTX 5080",
    "RTX 5070",
    "RTX 5060",
    "PRO 6000",
    "GeForce RTX 5090",
    "GeForce RTX 5080",
    "GeForce RTX 5070",
    "GeForce RTX 5060",
    "NVIDIA RTX PRO 6000",
})

DEFAULT_IMAGE = "pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime"
POLL_INTERVAL = 15  # seconds between SSH checks
MAX_BOOT_TIMEOUT = 600  # 10 minutes max wait


@dataclass
class RaceCandidate:
    """A single candidate in the connection race."""
    offer_id: int
    instance_id: Optional[int] = None
    gpu_name: str = ""
    gpu_ram_mb: int = 0
    region: str = ""
    country: str = ""
    hourly_cost: float = 0.0
    status: str = "pending"  # pending, launching, polling, won, lost, failed, timeout
    ssh_host: Optional[str] = None
    ssh_port: Optional[int] = None
    boot_time_seconds: Optional[float] = None
    ssh_verified: bool = False
    failure_reason: Optional[str] = None
    launched_at: Optional[float] = None


@dataclass
class RaceConfig:
    """Configuration for a connection race."""
    max_price: float = 1.50
    min_vram_gb: float = 12.0
    num_candidates: int = 3
    gpu_filter: Optional[str] = None  # e.g. "RTX 4090"
    excluded_hosts: list[int] = field(default_factory=list)
    disk_gb: int = 80
    image: str = DEFAULT_IMAGE
    timeout: int = MAX_BOOT_TIMEOUT


@dataclass
class RaceResult:
    """Result of a connection race."""
    success: bool
    winner: Optional[RaceCandidate] = None
    candidates: list[RaceCandidate] = field(default_factory=list)
    total_time_seconds: float = 0.0
    error: Optional[str] = None


class ConnectionRace:
    """Runs a connection race to find the fastest GPU worker."""

    def __init__(self, vast_client: Optional[VastClient] = None):
        self._client = vast_client or VastClient()
        self._candidates: list[RaceCandidate] = []
        self._running = False

    @property
    def candidates(self) -> list[RaceCandidate]:
        return self._candidates

    def _is_blackwell(self, gpu_name: str) -> bool:
        """Check if a GPU is Blackwell architecture (unsupported by PyTorch)."""
        gpu_upper = gpu_name.upper()
        for blocked in BLACKWELL_GPUS:
            if blocked.upper() in gpu_upper:
                return True
        return False

    def query_offers(self, config: RaceConfig) -> list[dict]:
        """Query Vast.ai for rentable offers matching the race config.

        Uses the verified query format with JSON 'q' parameter.
        """
        query_filter: dict = {
            "rentable": {"eq": True},
            "gpu_ram": {"gte": config.min_vram_gb * 1024},
            "dph_total": {"lte": config.max_price},
            "disk_space": {"gte": config.disk_gb},
        }

        if config.gpu_filter:
            query_filter["gpu_name"] = {"eq": config.gpu_filter}

        try:
            resp = httpx.get(
                "https://console.vast.ai/api/v0/bundles/",
                headers={"Authorization": f"Bearer {self._client.api_key}"},
                params={"q": json.dumps(query_filter)},
                timeout=30,
                follow_redirects=True,
            )
            if resp.status_code != 200:
                raise VastClientError(f"Offers query failed ({resp.status_code}): {resp.text}")

            data = resp.json()
            offers = data.get("offers", data) if isinstance(data, dict) else data
            if not isinstance(offers, list):
                offers = []
        except httpx.HTTPError as e:
            raise VastClientError(f"Network error querying offers: {e}")

        # Filter out Blackwell GPUs and excluded hosts
        filtered = []
        for offer in offers:
            gpu_name = offer.get("gpu_name", "")
            if self._is_blackwell(gpu_name):
                logger.info(f"Skipping Blackwell GPU: {gpu_name} (offer {offer.get('id')})")
                continue
            host_id = offer.get("machine_id") or offer.get("host_id")
            if host_id and host_id in config.excluded_hosts:
                logger.info(f"Skipping excluded host {host_id}")
                continue
            filtered.append(offer)

        # Sort by price
        filtered.sort(key=lambda o: o.get("dph_total", 999))

        return filtered[:config.num_candidates * 2]  # Get extra in case some fail to launch

    def _launch_candidate(self, offer: dict, config: RaceConfig) -> RaceCandidate:
        """Launch a single candidate instance."""
        candidate = RaceCandidate(
            offer_id=offer.get("id", 0),
            gpu_name=offer.get("gpu_name", "unknown"),
            gpu_ram_mb=offer.get("gpu_ram", 0),
            region=offer.get("geolocation", ""),
            country=offer.get("country", ""),
            hourly_cost=offer.get("dph_total", 0.0),
        )

        try:
            candidate.status = "launching"
            result = self._client.launch_instance(
                offer_id=candidate.offer_id,
                image=config.image,
                disk_gb=config.disk_gb,
            )
            candidate.instance_id = result.get("new_contract")
            candidate.launched_at = time.time()
            candidate.status = "polling"
            logger.info(
                f"Launched candidate: offer={candidate.offer_id}, "
                f"instance={candidate.instance_id}, gpu={candidate.gpu_name}"
            )
        except Exception as e:
            candidate.status = "failed"
            candidate.failure_reason = str(e)
            logger.warning(f"Failed to launch offer {candidate.offer_id}: {e}")

        return candidate

    def _check_ssh(self, host: str, port: int, timeout: float = 5.0) -> bool:
        """Check if SSH port is accepting connections (TCP connect test)."""
        import socket
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            sock.close()
            return result == 0
        except (socket.error, OSError):
            return False

    def _poll_candidate(self, candidate: RaceCandidate) -> bool:
        """Poll a candidate for SSH readiness. Returns True if SSH is up."""
        if not candidate.instance_id or candidate.status not in ("polling",):
            return False

        try:
            instance = self._client.get_instance(candidate.instance_id)
            ssh_host = instance.get("ssh_host", "")
            ssh_port = instance.get("ssh_port")
            status = instance.get("actual_status") or instance.get("cur_state", "")

            if not ssh_host or not ssh_port:
                return False

            # Try TCP connection to SSH
            if self._check_ssh(ssh_host, int(ssh_port)):
                candidate.ssh_host = ssh_host
                candidate.ssh_port = int(ssh_port)
                candidate.ssh_verified = True
                candidate.boot_time_seconds = time.time() - (candidate.launched_at or time.time())
                candidate.status = "won"
                return True

        except Exception as e:
            logger.debug(f"Poll error for instance {candidate.instance_id}: {e}")

        return False

    def _destroy_losers(self, winner: RaceCandidate) -> None:
        """Destroy all candidates except the winner."""
        for candidate in self._candidates:
            if candidate is winner:
                continue
            if candidate.instance_id and candidate.status not in ("failed",):
                try:
                    self._client.destroy_instance(candidate.instance_id)
                    candidate.status = "lost"
                    logger.info(f"Destroyed loser: instance={candidate.instance_id}")
                except Exception as e:
                    logger.warning(
                        f"Failed to destroy instance {candidate.instance_id}: {e}"
                    )

    def run(self, config: Optional[RaceConfig] = None) -> RaceResult:
        """Execute the connection race synchronously.

        Returns the race result with winner info or error.
        """
        config = config or RaceConfig()
        start_time = time.time()
        self._candidates = []
        self._running = True

        try:
            # 1. Query offers
            offers = self.query_offers(config)
            if not offers:
                return RaceResult(
                    success=False,
                    error="No suitable offers found matching criteria",
                    total_time_seconds=time.time() - start_time,
                )

            # 2. Launch candidates (up to num_candidates)
            launched = 0
            for offer in offers:
                if launched >= config.num_candidates:
                    break
                candidate = self._launch_candidate(offer, config)
                self._candidates.append(candidate)
                if candidate.status == "polling":
                    launched += 1

            if launched == 0:
                return RaceResult(
                    success=False,
                    candidates=self._candidates,
                    error="All candidate launches failed",
                    total_time_seconds=time.time() - start_time,
                )

            # 3. Poll for SSH readiness
            deadline = start_time + config.timeout
            winner = None

            while time.time() < deadline and self._running:
                for candidate in self._candidates:
                    if candidate.status == "polling":
                        if self._poll_candidate(candidate):
                            winner = candidate
                            break

                if winner:
                    break

                # Check if all candidates failed
                active = [c for c in self._candidates if c.status == "polling"]
                if not active:
                    return RaceResult(
                        success=False,
                        candidates=self._candidates,
                        error="All candidates failed or timed out",
                        total_time_seconds=time.time() - start_time,
                    )

                time.sleep(POLL_INTERVAL)

            if not winner:
                # Timeout — mark remaining as timed out and destroy
                for c in self._candidates:
                    if c.status == "polling":
                        c.status = "timeout"
                        c.failure_reason = "Boot timeout exceeded"
                        if c.instance_id:
                            try:
                                self._client.destroy_instance(c.instance_id)
                            except Exception:
                                pass

                return RaceResult(
                    success=False,
                    candidates=self._candidates,
                    error=f"No instance booted within {config.timeout}s timeout",
                    total_time_seconds=time.time() - start_time,
                )

            # 4. We have a winner — destroy losers
            self._destroy_losers(winner)

            return RaceResult(
                success=True,
                winner=winner,
                candidates=self._candidates,
                total_time_seconds=time.time() - start_time,
            )

        except Exception as e:
            # Cleanup on error
            for c in self._candidates:
                if c.instance_id and c.status == "polling":
                    try:
                        self._client.destroy_instance(c.instance_id)
                    except Exception:
                        pass
                    c.status = "failed"
                    c.failure_reason = f"Race aborted: {e}"

            return RaceResult(
                success=False,
                candidates=self._candidates,
                error=f"Race failed: {e}",
                total_time_seconds=time.time() - start_time,
            )
        finally:
            self._running = False

    def abort(self) -> None:
        """Signal the race to stop."""
        self._running = False

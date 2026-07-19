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

import contextlib
import json
import logging
import time
from dataclasses import dataclass, field

import httpx

from backend.providers.vast.client import VastClient, VastClientError

logger = logging.getLogger(__name__)


# Lazy import to avoid circular dependency at module level
def _get_reputation():
    from backend.infrastructure.provider_reputation import get_reputation_engine

    return get_reputation_engine()


# Blackwell GPUs — PyTorch doesn't support these yet
BLACKWELL_GPUS = frozenset(
    {
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
    }
)

DEFAULT_IMAGE = "pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime"
POLL_INTERVAL = 10  # seconds between SSH checks (was 15, reduced for faster detection)
MAX_BOOT_TIMEOUT = 600  # 10 minutes max wait
STUCK_THRESHOLD = 90  # seconds — auto-destroy candidate if no SSH after this


@dataclass
class RaceCandidate:
    """A single candidate in the connection race."""

    offer_id: int
    instance_id: int | None = None
    gpu_name: str = ""
    gpu_ram_mb: int = 0
    region: str = ""
    country: str = ""
    hourly_cost: float = 0.0
    status: str = "pending"  # pending, launching, polling, won, lost, failed, timeout
    ssh_host: str | None = None
    ssh_port: int | None = None
    boot_time_seconds: float | None = None
    ssh_verified: bool = False
    failure_reason: str | None = None
    launched_at: float | None = None


@dataclass
class RaceConfig:
    """Configuration for a connection race."""

    max_price: float = 1.50
    min_vram_gb: float = 12.0
    num_candidates: int = 3
    gpu_filter: str | None = None  # e.g. "RTX 4090"
    excluded_hosts: list[int] = field(default_factory=list)
    disk_gb: int = 80
    image: str = DEFAULT_IMAGE
    timeout: int = MAX_BOOT_TIMEOUT


@dataclass
class RaceResult:
    """Result of a connection race."""

    success: bool
    winner: RaceCandidate | None = None
    candidates: list[RaceCandidate] = field(default_factory=list)
    total_time_seconds: float = 0.0
    error: str | None = None


class ConnectionRace:
    """Runs a connection race to find the fastest GPU worker."""

    def __init__(self, vast_client: VastClient | None = None) -> None:
        self._client = vast_client or VastClient()
        self._candidates: list[RaceCandidate] = []
        self._running = False

    @property
    def candidates(self) -> list[RaceCandidate]:
        return self._candidates

    def _is_blackwell(self, gpu_name: str) -> bool:
        """Check if a GPU is Blackwell architecture (unsupported by PyTorch)."""
        gpu_upper = gpu_name.upper()
        return any(blocked.upper() in gpu_upper for blocked in BLACKWELL_GPUS)

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

        # Filter out Blackwell GPUs, excluded hosts, and blacklisted hosts
        reputation = _get_reputation()
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
            if host_id and reputation.is_blacklisted(str(host_id)):
                logger.info(f"Skipping blacklisted host {host_id} (offer {offer.get('id')})")
                continue
            filtered.append(offer)

        # Sort by reputation score (best first), falling back to price
        pool_size = config.num_candidates * 2
        recommended = reputation.recommend_offers(filtered, count=pool_size)

        # If reputation engine returned fewer (e.g. all new hosts), fall back to price sort
        if len(recommended) < pool_size:
            seen_ids = {o.get("id") for o in recommended}
            remaining = [o for o in filtered if o.get("id") not in seen_ids]
            remaining.sort(key=lambda o: o.get("dph_total", 999))
            recommended.extend(remaining[: pool_size - len(recommended)])

        return recommended[:pool_size]

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
        except OSError:
            return False

    def _poll_candidate(self, candidate: RaceCandidate) -> bool:
        """Poll a candidate for SSH readiness. Returns True if SSH is up."""
        if not candidate.instance_id or candidate.status not in ("polling",):
            return False

        try:
            instance = self._client.get_instance(candidate.instance_id)
            ssh_host = instance.get("ssh_host", "")
            ssh_port = instance.get("ssh_port")
            instance.get("actual_status") or instance.get("cur_state", "")

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
                    logger.warning(f"Failed to destroy instance {candidate.instance_id}: {e}")

    def run(self, config: RaceConfig | None = None) -> RaceResult:
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
                    if candidate.status == "polling" and self._poll_candidate(candidate):
                        winner = candidate
                        break

                if winner:
                    break

                # Stuck instance detection: auto-destroy candidates that haven't
                # responded after STUCK_THRESHOLD seconds
                for candidate in self._candidates:
                    if (
                        candidate.status == "polling"
                        and candidate.launched_at
                        and (time.time() - candidate.launched_at) > STUCK_THRESHOLD
                    ):
                        logger.warning(
                            f"Candidate {candidate.instance_id} stuck (>{STUCK_THRESHOLD}s) — destroying"
                        )
                        candidate.status = "failed"
                        candidate.failure_reason = f"No SSH response after {STUCK_THRESHOLD}s (stuck)"
                        if candidate.instance_id:
                            try:
                                self._client.destroy_instance(candidate.instance_id)
                            except Exception:
                                pass

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
                            with contextlib.suppress(Exception):
                                self._client.destroy_instance(c.instance_id)

                # Record all attempts to reputation engine
                self._record_race_to_reputation()

                return RaceResult(
                    success=False,
                    candidates=self._candidates,
                    error=f"No instance booted within {config.timeout}s timeout",
                    total_time_seconds=time.time() - start_time,
                )

            # 4. We have a winner — destroy losers
            self._destroy_losers(winner)

            # 5. Record all attempts to reputation engine
            self._record_race_to_reputation()

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
                    with contextlib.suppress(Exception):
                        self._client.destroy_instance(c.instance_id)
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

    def _record_race_to_reputation(self) -> None:
        """Record all race candidates to the reputation engine."""
        reputation = _get_reputation()
        for candidate in self._candidates:
            host_id = str(candidate.offer_id)  # Use offer_id as host proxy
            status_map = {
                "won": "success",
                "lost": "success",  # Lost but launched fine — still counts
                "failed": "failed",
                "timeout": "timeout",
            }
            status = status_map.get(candidate.status, "failed")
            # A "lost" candidate launched but didn't win — still a viable host
            # Only the winner gets boot_time recorded as success metric
            if candidate.status == "lost":
                status = "success"

            reputation.record_attempt(
                {
                    "host_id": host_id,
                    "gpu_name": candidate.gpu_name,
                    "region": candidate.region,
                    "status": status,
                    "boot_time_seconds": candidate.boot_time_seconds,
                    "hourly_cost": candidate.hourly_cost,
                    "failure_reason": candidate.failure_reason,
                }
            )

    def abort(self) -> None:
        """Signal the race to stop."""
        self._running = False

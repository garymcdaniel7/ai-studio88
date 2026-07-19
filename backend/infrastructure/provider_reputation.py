"""Provider Reputation & Learning Engine.

Tracks historical performance of GPU providers (hosts, GPUs, regions)
and learns which offers are most likely to succeed. Scores providers
based on reliability, boot speed, and cost efficiency.

Storage: In-memory for now, with persistence hooks for Supabase later.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

# Penalty event types that count as failures
PENALTY_EVENTS = frozenset(
    {
        "ssh_failure",
        "comfyui_failure",
        "cuda_error",
        "oom",
        "timeout",
        "crash",
    }
)

# Thresholds for auto-blacklisting
BLACKLIST_RELIABILITY_THRESHOLD = 0.3
BLACKLIST_MIN_ATTEMPTS = 3

# Scoring weights
WEIGHT_RELIABILITY = 0.5
WEIGHT_PERFORMANCE = 0.3
WEIGHT_COST_EFFICIENCY = 0.2

# Max boot time for performance scoring (seconds)
MAX_BOOT_TIME = 300.0

# Neutral score for hosts with no history
NEUTRAL_SCORE = 0.5


@dataclass
class ReputationScore:
    """Reputation metrics for a host, GPU, or region."""

    entity_id: str = ""  # host_id, gpu_name, or region
    entity_type: str = ""  # "host", "gpu", or "region"
    total_attempts: int = 0
    successes: int = 0
    failures: int = 0
    timeouts: int = 0
    avg_boot_time_seconds: float = 0.0
    reliability_score: float = 0.0
    performance_score: float = 0.0
    cost_efficiency_score: float = 0.0
    overall_score: float = 0.0
    last_attempt_at: str = ""
    blacklisted: bool = False
    blacklist_reason: str | None = None

    def to_dict(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "total_attempts": self.total_attempts,
            "successes": self.successes,
            "failures": self.failures,
            "timeouts": self.timeouts,
            "avg_boot_time_seconds": self.avg_boot_time_seconds,
            "reliability_score": self.reliability_score,
            "performance_score": self.performance_score,
            "cost_efficiency_score": self.cost_efficiency_score,
            "overall_score": self.overall_score,
            "last_attempt_at": self.last_attempt_at,
            "blacklisted": self.blacklisted,
            "blacklist_reason": self.blacklist_reason,
        }


@dataclass
class AttemptRecord:
    """A single recorded connection attempt for reputation tracking."""

    host_id: str = ""
    gpu_name: str = ""
    region: str = ""
    provider: str = ""  # "vast" or "runpod"
    status: str = ""  # success, failed, timeout, stuck
    boot_time_seconds: float | None = None
    hourly_cost: float = 0.0
    failure_reason: str | None = None
    recorded_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class ProviderReputation:
    """Tracks and scores provider reputation based on connection history.

    Maintains in-memory records of all connection attempts and computes
    reputation scores for hosts, GPUs, and regions. Supports blacklisting
    unreliable providers and recommending the best offers.
    """

    def __init__(self) -> None:
        self._attempts: list[AttemptRecord] = []
        self._blacklist: dict[str, str] = {}  # host_id -> reason

    # ─── Recording ────────────────────────────────────────────────────────

    def record_attempt(self, attempt_data: dict) -> None:
        """Log a connection attempt result.

        Args:
            attempt_data: Dict with keys:
                - host_id (str): The host/machine identifier
                - gpu_name (str): GPU model name
                - region (str): Geographic region
                - status (str): "success", "failed", or "timeout"
                - boot_time_seconds (float|None): Time to boot if successful
                - hourly_cost (float): Cost per hour
                - failure_reason (str|None): Why it failed, if applicable
        """
        record = AttemptRecord(
            host_id=str(attempt_data.get("host_id", "")),
            gpu_name=attempt_data.get("gpu_name", ""),
            region=attempt_data.get("region", ""),
            provider=attempt_data.get("provider", "vast"),
            status=attempt_data.get("status", "failed"),
            boot_time_seconds=attempt_data.get("boot_time_seconds"),
            hourly_cost=attempt_data.get("hourly_cost", 0.0),
            failure_reason=attempt_data.get("failure_reason"),
        )
        self._attempts.append(record)

        # Check auto-blacklist for host
        if record.host_id:
            self._check_auto_blacklist(record.host_id)

        logger.debug(
            f"Recorded attempt: host={record.host_id}, "
            f"gpu={record.gpu_name}, status={record.status}"
        )

    # ─── Reputation Queries ───────────────────────────────────────────────

    def get_host_reputation(self, host_id: str) -> ReputationScore:
        """Get reputation score for a specific host."""
        attempts = [a for a in self._attempts if a.host_id == str(host_id)]
        score = self._compute_score(attempts, str(host_id), "host")
        score.blacklisted = str(host_id) in self._blacklist
        score.blacklist_reason = self._blacklist.get(str(host_id))
        return score

    def get_gpu_reputation(self, gpu_name: str) -> ReputationScore:
        """Get reputation score for a specific GPU model."""
        attempts = [a for a in self._attempts if a.gpu_name == gpu_name]
        return self._compute_score(attempts, gpu_name, "gpu")

    def get_region_reputation(self, region: str) -> ReputationScore:
        """Get reputation score for a specific region."""
        attempts = [a for a in self._attempts if a.region == region]
        return self._compute_score(attempts, region, "region")

    def get_all_reputations(self) -> dict:
        """Get all reputation scores grouped by type."""
        hosts: dict[str, list[AttemptRecord]] = {}
        gpus: dict[str, list[AttemptRecord]] = {}
        regions: dict[str, list[AttemptRecord]] = {}

        for attempt in self._attempts:
            if attempt.host_id:
                hosts.setdefault(attempt.host_id, []).append(attempt)
            if attempt.gpu_name:
                gpus.setdefault(attempt.gpu_name, []).append(attempt)
            if attempt.region:
                regions.setdefault(attempt.region, []).append(attempt)

        host_scores = []
        for host_id, attempts in hosts.items():
            score = self._compute_score(attempts, host_id, "host")
            score.blacklisted = host_id in self._blacklist
            score.blacklist_reason = self._blacklist.get(host_id)
            host_scores.append(score.to_dict())

        gpu_scores = [
            self._compute_score(attempts, gpu_name, "gpu").to_dict()
            for gpu_name, attempts in gpus.items()
        ]

        region_scores = [
            self._compute_score(attempts, region, "region").to_dict()
            for region, attempts in regions.items()
        ]

        return {
            "hosts": host_scores,
            "gpus": gpu_scores,
            "regions": region_scores,
            "total_attempts": len(self._attempts),
        }

    def get_provider_comparison(self) -> dict:
        """Compare providers (vast vs runpod) based on historical data.

        Returns boot time averages, success rates, and cost efficiency
        per provider so the system can recommend the best default.
        """
        providers: dict[str, list[AttemptRecord]] = {}
        for attempt in self._attempts:
            provider = attempt.provider or "vast"
            providers.setdefault(provider, []).append(attempt)

        comparison = {}
        for provider, attempts in providers.items():
            successes = [a for a in attempts if a.status == "success"]
            failures = [a for a in attempts if a.status in ("failed", "timeout", "stuck")]
            boot_times = [a.boot_time_seconds for a in successes if a.boot_time_seconds]
            costs = [a.hourly_cost for a in successes if a.hourly_cost > 0]

            comparison[provider] = {
                "total_attempts": len(attempts),
                "successes": len(successes),
                "failures": len(failures),
                "success_rate": round(len(successes) / max(len(attempts), 1), 2),
                "avg_boot_time_seconds": round(sum(boot_times) / max(len(boot_times), 1), 1) if boot_times else None,
                "min_boot_time_seconds": round(min(boot_times), 1) if boot_times else None,
                "max_boot_time_seconds": round(max(boot_times), 1) if boot_times else None,
                "avg_hourly_cost": round(sum(costs) / max(len(costs), 1), 4) if costs else None,
                "common_failure_reasons": self._top_failures(failures),
            }

        # Determine recommended provider
        recommended = "runpod"  # Default to RunPod (faster, persistent volumes)
        if "vast" in comparison and "runpod" in comparison:
            vast_rate = comparison["vast"]["success_rate"]
            runpod_rate = comparison["runpod"]["success_rate"]
            if vast_rate > runpod_rate + 0.1:  # Vast significantly more reliable
                recommended = "vast"

        return {
            "providers": comparison,
            "recommended": recommended,
            "recommendation_reason": "RunPod default: faster boot, persistent volumes, no SSH tunnel needed. Switch to Vast.ai for lower cost (load times may vary).",
        }

    def _top_failures(self, failures: list[AttemptRecord], limit: int = 3) -> list[str]:
        """Get most common failure reasons."""
        from collections import Counter
        reasons = Counter(a.failure_reason for a in failures if a.failure_reason)
        return [reason for reason, _ in reasons.most_common(limit)]

    # ─── Blacklist Management ─────────────────────────────────────────────

    def get_blacklist(self) -> list[dict]:
        """Get all blacklisted host IDs with reasons."""
        return [
            {"host_id": host_id, "reason": reason} for host_id, reason in self._blacklist.items()
        ]

    def blacklist_host(self, host_id: str, reason: str) -> None:
        """Manually blacklist a host.

        Args:
            host_id: The host/machine ID to blacklist
            reason: Why this host is being blacklisted
        """
        self._blacklist[str(host_id)] = reason
        logger.info(f"Blacklisted host {host_id}: {reason}")

    def unblacklist_host(self, host_id: str) -> bool:
        """Remove a host from the blacklist. Returns True if it was blacklisted."""
        removed = self._blacklist.pop(str(host_id), None)
        if removed:
            logger.info(f"Removed host {host_id} from blacklist")
        return removed is not None

    def is_blacklisted(self, host_id: str) -> bool:
        """Check if a host is blacklisted."""
        return str(host_id) in self._blacklist

    # ─── Preferred Hosts ──────────────────────────────────────────────────

    def get_preferred_hosts(self) -> list[dict]:
        """Get historically successful hosts, sorted by reliability.

        Returns hosts with at least 2 successful connections,
        sorted by overall score descending.
        """
        hosts: dict[str, list[AttemptRecord]] = {}
        for attempt in self._attempts:
            if attempt.host_id:
                hosts.setdefault(attempt.host_id, []).append(attempt)

        preferred = []
        for host_id, attempts in hosts.items():
            if host_id in self._blacklist:
                continue
            score = self._compute_score(attempts, host_id, "host")
            if score.successes >= 2 and score.reliability_score >= 0.7:
                preferred.append(score.to_dict())

        preferred.sort(key=lambda s: s["overall_score"], reverse=True)
        return preferred

    # ─── Offer Recommendation ─────────────────────────────────────────────

    def recommend_offers(self, offers: list[dict], count: int = 3) -> list[dict]:
        """Score and rank offers based on provider reputation.

        Args:
            offers: List of offer dicts from Vast.ai (must have id, gpu_name, etc.)
            count: How many top offers to return

        Returns:
            Top `count` offers sorted by reputation score, excluding blacklisted hosts.
        """
        scored_offers = []

        # Compute max cost for cost efficiency normalization
        costs = [o.get("dph_total", 0.0) for o in offers if o.get("dph_total", 0.0) > 0]
        max_cost = max(costs) if costs else 1.0

        for offer in offers:
            host_id = str(offer.get("machine_id") or offer.get("host_id") or "")

            # Skip blacklisted hosts
            if host_id and self.is_blacklisted(host_id):
                logger.debug(f"Skipping blacklisted host {host_id}")
                continue

            # Compute combined reputation score
            offer_score = self._score_offer(offer, host_id, max_cost)
            scored_offers.append((offer_score, offer))

        # Sort by score descending
        scored_offers.sort(key=lambda x: x[0], reverse=True)

        # Return top N with scores attached
        result = []
        for score, offer in scored_offers[:count]:
            offer_copy = dict(offer)
            offer_copy["reputation_score"] = round(score, 4)
            result.append(offer_copy)

        return result

    # ─── Private Methods ──────────────────────────────────────────────────

    def _score_offer(self, offer: dict, host_id: str, max_cost: float) -> float:
        """Compute a combined reputation score for an offer."""
        gpu_name = offer.get("gpu_name", "")
        region = offer.get("geolocation", "") or offer.get("region", "")

        # Get individual scores (or neutral if no data)
        host_score = NEUTRAL_SCORE
        if host_id:
            host_attempts = [a for a in self._attempts if a.host_id == host_id]
            if host_attempts:
                rep = self._compute_score(host_attempts, host_id, "host")
                host_score = rep.overall_score

        gpu_score = NEUTRAL_SCORE
        if gpu_name:
            gpu_attempts = [a for a in self._attempts if a.gpu_name == gpu_name]
            if gpu_attempts:
                rep = self._compute_score(gpu_attempts, gpu_name, "gpu")
                gpu_score = rep.overall_score

        region_score = NEUTRAL_SCORE
        if region:
            region_attempts = [a for a in self._attempts if a.region == region]
            if region_attempts:
                rep = self._compute_score(region_attempts, region, "region")
                region_score = rep.overall_score

        # Weighted combination: host matters most, then GPU, then region
        combined = 0.5 * host_score + 0.3 * gpu_score + 0.2 * region_score

        # Apply cost efficiency bonus from this specific offer
        offer_cost = offer.get("dph_total", 0.0)
        if max_cost > 0 and offer_cost > 0:
            cost_factor = 1.0 - (offer_cost / max_cost)
            cost_factor = max(0.0, min(1.0, cost_factor))
            # Blend cost into score (10% weight)
            combined = 0.9 * combined + 0.1 * cost_factor

        return combined

    def _compute_score(
        self, attempts: list[AttemptRecord], entity_id: str, entity_type: str
    ) -> ReputationScore:
        """Compute reputation metrics from a list of attempts."""
        score = ReputationScore(entity_id=entity_id, entity_type=entity_type)

        if not attempts:
            score.overall_score = NEUTRAL_SCORE
            return score

        score.total_attempts = len(attempts)
        score.successes = sum(1 for a in attempts if a.status == "success")
        score.failures = sum(1 for a in attempts if a.status == "failed")
        score.timeouts = sum(1 for a in attempts if a.status == "timeout")

        # Last attempt timestamp
        score.last_attempt_at = attempts[-1].recorded_at

        # Reliability: successes / total
        score.reliability_score = (
            score.successes / score.total_attempts if score.total_attempts > 0 else 0.0
        )

        # Performance: based on average boot time of successful attempts
        boot_times = [
            a.boot_time_seconds
            for a in attempts
            if a.boot_time_seconds is not None and a.status == "success"
        ]
        if boot_times:
            score.avg_boot_time_seconds = sum(boot_times) / len(boot_times)
            # 1.0 - (avg_boot / 300), clamped to [0, 1]
            raw_perf = 1.0 - (score.avg_boot_time_seconds / MAX_BOOT_TIME)
            score.performance_score = max(0.0, min(1.0, raw_perf))
        else:
            score.performance_score = NEUTRAL_SCORE

        # Cost efficiency: based on average cost relative to max seen cost
        costs = [a.hourly_cost for a in attempts if a.hourly_cost > 0]
        if costs:
            avg_cost = sum(costs) / len(costs)
            all_costs = [a.hourly_cost for a in self._attempts if a.hourly_cost > 0]
            max_cost = max(all_costs) if all_costs else avg_cost
            if max_cost > 0:
                raw_eff = 1.0 - (avg_cost / max_cost)
                score.cost_efficiency_score = max(0.0, min(1.0, raw_eff))
            else:
                score.cost_efficiency_score = NEUTRAL_SCORE
        else:
            score.cost_efficiency_score = NEUTRAL_SCORE

        # Overall weighted combination
        score.overall_score = (
            WEIGHT_RELIABILITY * score.reliability_score
            + WEIGHT_PERFORMANCE * score.performance_score
            + WEIGHT_COST_EFFICIENCY * score.cost_efficiency_score
        )

        return score

    def _check_auto_blacklist(self, host_id: str) -> None:
        """Auto-blacklist a host if reliability drops below threshold."""
        if host_id in self._blacklist:
            return

        attempts = [a for a in self._attempts if a.host_id == host_id]
        if len(attempts) < BLACKLIST_MIN_ATTEMPTS:
            return

        successes = sum(1 for a in attempts if a.status == "success")
        reliability = successes / len(attempts)

        if reliability < BLACKLIST_RELIABILITY_THRESHOLD:
            reason = (
                f"Auto-blacklisted: reliability {reliability:.2f} "
                f"({successes}/{len(attempts)} successes) below threshold "
                f"{BLACKLIST_RELIABILITY_THRESHOLD}"
            )
            self._blacklist[host_id] = reason
            logger.warning(f"Auto-blacklisted host {host_id}: {reason}")


# =============================================================================
# Module-level singleton
# =============================================================================

_reputation_engine: ProviderReputation | None = None


def get_reputation_engine() -> ProviderReputation:
    """Get or create the global ProviderReputation singleton."""
    global _reputation_engine
    if _reputation_engine is None:
        _reputation_engine = ProviderReputation()
    return _reputation_engine

"""Durable Connection Race — Story 059.

Every connection race is a tracked, reconcilable obligation. No candidate
can be launched without persistence, and no loser can be abandoned without
confirmed provider cleanup.

Lifecycle:
    start_race(org_id, ...) → RACING (candidates launched, cost reserved)
    candidate_ready(race_id, candidate_id) → winner selected
    select_winner(race_id) → WINNER_SELECTED (losers queued for cleanup)
    cleanup_loser(race_id, candidate_id) → CLEANUP_PENDING → CLEANED
    finalize(race_id) → COMPLETED (all losers confirmed terminated)
    
    If cleanup fails → CLEANUP_FAILED → alert + retry
    If all candidates fail → ALL_FAILED → cost released

Properties:
    1. Workspace lease: only one active race per workspace at a time
    2. Cost reservation: worst-case spend reserved before launching
    3. Candidate persistence: every provider_id persisted before considered active
    4. Winner evidence: deterministic criteria recorded
    5. Loser cleanup: durable, retryable, provider-confirmed
    6. Alert on unresolved: candidates not confirmed terminated trigger alert
    7. Billing reconciliation: actual vs reserved cost tracked
"""

from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any


# =============================================================================
# Race States
# =============================================================================


class RaceState(str, Enum):
    RACING = "racing"                # Candidates launched, awaiting readiness
    WINNER_SELECTED = "winner_selected"  # One winner, losers queued for cleanup
    CLEANING_UP = "cleaning_up"      # Actively terminating losers
    COMPLETED = "completed"          # All losers confirmed terminated
    ALL_FAILED = "all_failed"        # No candidate succeeded
    CLEANUP_FAILED = "cleanup_failed"  # Loser termination unconfirmed (ALERT)


class CandidateState(str, Enum):
    LAUNCHING = "launching"
    READY = "ready"
    WINNER = "winner"
    LOSER_PENDING_CLEANUP = "loser_pending_cleanup"
    LOSER_CLEANUP_CONFIRMED = "loser_cleanup_confirmed"
    LOSER_CLEANUP_FAILED = "loser_cleanup_failed"
    FAILED = "failed"  # Launch failed


# =============================================================================
# Candidate Record
# =============================================================================


@dataclass
class RaceCandidate:
    """A single candidate in a connection race."""

    id: str
    provider: str  # "runpod" or "vast"
    provider_instance_id: str  # Pod ID / instance ID from provider
    state: CandidateState = CandidateState.LAUNCHING
    gpu_name: str = ""
    hourly_rate: float = 0.0
    ready_at: str | None = None
    cleanup_attempted_at: str | None = None
    cleanup_confirmed_at: str | None = None
    cleanup_attempts: int = 0
    error: str = ""


# =============================================================================
# Race Record
# =============================================================================


@dataclass
class DurableRace:
    """A durable connection race with full lifecycle tracking."""

    id: str
    org_id: str
    user_id: str
    state: RaceState = RaceState.RACING
    # Cost reservation
    cost_reservation_usd: float = 0.0
    actual_cost_usd: float = 0.0
    # Candidates
    candidates: list[RaceCandidate] = field(default_factory=list)
    # Winner
    winner_candidate_id: str | None = None
    winner_criteria: str = ""  # Why this one was picked
    winner_worker_id: str | None = None  # Canonical worker record ID after transfer
    # Timing
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    winner_selected_at: str | None = None
    completed_at: str | None = None
    # Alert
    alert_raised: bool = False
    alert_reason: str = ""

    def to_status(self) -> dict:
        return {
            "id": self.id,
            "org_id": self.org_id,
            "state": self.state.value,
            "cost_reservation_usd": self.cost_reservation_usd,
            "actual_cost_usd": self.actual_cost_usd,
            "candidate_count": len(self.candidates),
            "winner_candidate_id": self.winner_candidate_id,
            "winner_criteria": self.winner_criteria,
            "winner_worker_id": self.winner_worker_id,
            "alert_raised": self.alert_raised,
            "alert_reason": self.alert_reason,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "candidates": [
                {
                    "id": c.id,
                    "provider": c.provider,
                    "provider_instance_id": c.provider_instance_id,
                    "state": c.state.value,
                    "gpu_name": c.gpu_name,
                    "hourly_rate": c.hourly_rate,
                    "cleanup_attempts": c.cleanup_attempts,
                    "error": c.error,
                }
                for c in self.candidates
            ],
        }


# =============================================================================
# Store
# =============================================================================

_race_store: dict[str, DurableRace] = {}
_workspace_leases: dict[str, str] = {}  # org_id → active race_id (prevents duplicates)
_store_lock = threading.Lock()
_alerts: list[dict] = []


def _make_race_id() -> str:
    return f"race-{secrets.token_hex(8)}"


def _make_candidate_id() -> str:
    return f"cand-{secrets.token_hex(6)}"


# =============================================================================
# Connection Race Service
# =============================================================================


class ConnectionRaceService:
    """Durable connection race management."""

    @staticmethod
    def start_race(
        *,
        org_id: str,
        user_id: str,
        candidates: list[dict[str, Any]],
        max_cost_per_candidate_usd: float = 2.0,
    ) -> DurableRace | None:
        """Start a connection race for a workspace.

        Prevents duplicate races via workspace lease.
        Reserves worst-case cost before launching.

        Args:
            org_id: Workspace
            user_id: Actor
            candidates: List of {provider, provider_instance_id, gpu_name, hourly_rate}
            max_cost_per_candidate_usd: Worst-case cost per candidate for reservation

        Returns:
            DurableRace record, or None if a race is already active for this workspace.
        """
        if not org_id or not candidates:
            return None

        with _store_lock:
            # Workspace lease — prevent duplicate races
            if org_id in _workspace_leases:
                existing_race = _race_store.get(_workspace_leases[org_id])
                if existing_race and existing_race.state == RaceState.RACING:
                    return None  # Duplicate prevented

            # Reserve worst-case cost
            cost_reservation = max_cost_per_candidate_usd * len(candidates)

            # Create race record
            race = DurableRace(
                id=_make_race_id(),
                org_id=org_id,
                user_id=user_id,
                cost_reservation_usd=cost_reservation,
            )

            # Persist candidates BEFORE considering them active
            for c in candidates:
                candidate = RaceCandidate(
                    id=_make_candidate_id(),
                    provider=c.get("provider", "unknown"),
                    provider_instance_id=c.get("provider_instance_id", ""),
                    gpu_name=c.get("gpu_name", ""),
                    hourly_rate=c.get("hourly_rate", 0.0),
                )
                race.candidates.append(candidate)

            _race_store[race.id] = race
            _workspace_leases[org_id] = race.id

        return race

    @staticmethod
    def candidate_ready(race_id: str, provider_instance_id: str) -> bool:
        """Mark a candidate as ready (SSH/HTTP reachable)."""
        with _store_lock:
            race = _race_store.get(race_id)
            if not race or race.state != RaceState.RACING:
                return False

            for c in race.candidates:
                if c.provider_instance_id == provider_instance_id:
                    c.state = CandidateState.READY
                    c.ready_at = datetime.now(UTC).isoformat()
                    return True
        return False

    @staticmethod
    def candidate_failed(race_id: str, provider_instance_id: str, error: str = "") -> bool:
        """Mark a candidate as failed to launch."""
        with _store_lock:
            race = _race_store.get(race_id)
            if not race:
                return False

            for c in race.candidates:
                if c.provider_instance_id == provider_instance_id:
                    c.state = CandidateState.FAILED
                    c.error = error[:200]
                    break

            # Check if ALL failed
            if all(c.state == CandidateState.FAILED for c in race.candidates):
                race.state = RaceState.ALL_FAILED
                race.completed_at = datetime.now(UTC).isoformat()
                # Release workspace lease
                if race.org_id in _workspace_leases:
                    del _workspace_leases[race.org_id]

        return True

    @staticmethod
    def select_winner(race_id: str, criteria: str = "first_ready") -> RaceCandidate | None:
        """Select the winner from ready candidates.

        Criteria: "first_ready" (default), "lowest_cost", "best_gpu"
        Losers are queued for cleanup.
        """
        with _store_lock:
            race = _race_store.get(race_id)
            if not race or race.state != RaceState.RACING:
                return None

            ready = [c for c in race.candidates if c.state == CandidateState.READY]
            if not ready:
                return None

            # Deterministic winner selection
            if criteria == "lowest_cost":
                winner = min(ready, key=lambda c: c.hourly_rate)
            elif criteria == "best_gpu":
                # Simple heuristic — lower hourly usually means worse GPU
                winner = max(ready, key=lambda c: c.hourly_rate)
            else:  # first_ready
                winner = ready[0]

            # Mark winner
            winner.state = CandidateState.WINNER
            race.winner_candidate_id = winner.id
            race.winner_criteria = criteria
            race.winner_selected_at = datetime.now(UTC).isoformat()
            race.state = RaceState.CLEANING_UP

            # Mark losers for cleanup
            for c in race.candidates:
                if c.id != winner.id and c.state in (CandidateState.READY, CandidateState.LAUNCHING):
                    c.state = CandidateState.LOSER_PENDING_CLEANUP

        return winner

    @staticmethod
    def confirm_loser_cleanup(race_id: str, candidate_id: str) -> bool:
        """Confirm a loser has been terminated by the provider.

        Must be called after provider API confirms termination.
        """
        with _store_lock:
            race = _race_store.get(race_id)
            if not race:
                return False

            for c in race.candidates:
                if c.id == candidate_id:
                    c.state = CandidateState.LOSER_CLEANUP_CONFIRMED
                    c.cleanup_confirmed_at = datetime.now(UTC).isoformat()
                    break

            # Check if all losers are cleaned up
            losers = [c for c in race.candidates if c.id != race.winner_candidate_id
                      and c.state != CandidateState.FAILED]
            if all(c.state == CandidateState.LOSER_CLEANUP_CONFIRMED for c in losers):
                race.state = RaceState.COMPLETED
                race.completed_at = datetime.now(UTC).isoformat()
                # Release workspace lease
                if race.org_id in _workspace_leases:
                    del _workspace_leases[race.org_id]

        return True

    @staticmethod
    def mark_cleanup_failed(race_id: str, candidate_id: str, error: str = "") -> None:
        """Mark a loser cleanup as failed (triggers alert)."""
        with _store_lock:
            race = _race_store.get(race_id)
            if not race:
                return

            for c in race.candidates:
                if c.id == candidate_id:
                    c.state = CandidateState.LOSER_CLEANUP_FAILED
                    c.cleanup_attempts += 1
                    c.error = error[:200]
                    break

            # Raise alert
            race.state = RaceState.CLEANUP_FAILED
            race.alert_raised = True
            race.alert_reason = f"Candidate {candidate_id} cleanup failed: {error[:100]}"

            _alerts.append({
                "timestamp": datetime.now(UTC).isoformat(),
                "race_id": race_id,
                "org_id": race.org_id,
                "candidate_id": candidate_id,
                "provider_instance_id": next(
                    (c.provider_instance_id for c in race.candidates if c.id == candidate_id), ""
                ),
                "reason": f"Loser cleanup failed after {c.cleanup_attempts} attempts",
            })

    @staticmethod
    def retry_cleanup(race_id: str, candidate_id: str) -> bool:
        """Retry cleanup for a failed loser candidate."""
        with _store_lock:
            race = _race_store.get(race_id)
            if not race:
                return False

            for c in race.candidates:
                if c.id == candidate_id and c.state == CandidateState.LOSER_CLEANUP_FAILED:
                    c.state = CandidateState.LOSER_PENDING_CLEANUP
                    c.cleanup_attempted_at = datetime.now(UTC).isoformat()
                    return True
        return False

    @staticmethod
    def transfer_winner(race_id: str, worker_id: str) -> bool:
        """Transfer the winner into the canonical worker lifecycle."""
        with _store_lock:
            race = _race_store.get(race_id)
            if not race or not race.winner_candidate_id:
                return False
            race.winner_worker_id = worker_id
        return True

    @staticmethod
    def get_race(race_id: str, org_id: str) -> dict | None:
        """Get race status (tenant-scoped)."""
        race = _race_store.get(race_id)
        if not race or race.org_id != org_id:
            return None
        return race.to_status()

    @staticmethod
    def get_active_race(org_id: str) -> dict | None:
        """Get the active race for a workspace (if any)."""
        race_id = _workspace_leases.get(org_id)
        if not race_id:
            return None
        race = _race_store.get(race_id)
        if not race:
            return None
        return race.to_status()

    @staticmethod
    def get_unresolved_alerts() -> list[dict]:
        """Get alerts for unresolved (orphaned) provider resources."""
        return list(_alerts)

    @staticmethod
    def reconcile_cost(race_id: str, actual_cost_usd: float) -> bool:
        """Record actual cost for billing reconciliation."""
        race = _race_store.get(race_id)
        if not race:
            return False
        race.actual_cost_usd = actual_cost_usd
        return True

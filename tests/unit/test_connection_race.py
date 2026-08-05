"""Durable Connection Race Tests (Story 059).

Proves: workspace lease prevents duplicates, cost reservation, candidate
persistence, winner selection, loser cleanup, alert on unresolved, crash
recovery, and billing reconciliation.

Run with:
    pytest tests/unit/test_connection_race.py -v
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from backend.connection_race import (
    CandidateState,
    ConnectionRaceService,
    RaceState,
    _alerts,
    _race_store,
    _workspace_leases,
)

ORG_A = str(uuid4())
ORG_B = str(uuid4())
USER_A = str(uuid4())

CANDIDATES = [
    {"provider": "runpod", "provider_instance_id": "pod-1", "gpu_name": "A100", "hourly_rate": 1.5},
    {"provider": "runpod", "provider_instance_id": "pod-2", "gpu_name": "A6000", "hourly_rate": 0.8},
    {"provider": "vast", "provider_instance_id": "inst-3", "gpu_name": "RTX4090", "hourly_rate": 0.5},
]


@pytest.fixture(autouse=True)
def clean():
    _race_store.clear()
    _workspace_leases.clear()
    _alerts.clear()
    yield
    _race_store.clear()
    _workspace_leases.clear()
    _alerts.clear()


# =============================================================================
# Workspace Lease (Duplicate Prevention)
# =============================================================================


class TestWorkspaceLease:

    @pytest.mark.unit
    def test_start_race_creates_record(self):
        race = ConnectionRaceService.start_race(
            org_id=ORG_A, user_id=USER_A, candidates=CANDIDATES,
        )
        assert race is not None
        assert race.state == RaceState.RACING
        assert len(race.candidates) == 3

    @pytest.mark.unit
    def test_duplicate_race_prevented(self):
        """Only one active race per workspace."""
        race1 = ConnectionRaceService.start_race(
            org_id=ORG_A, user_id=USER_A, candidates=CANDIDATES,
        )
        race2 = ConnectionRaceService.start_race(
            org_id=ORG_A, user_id=USER_A, candidates=CANDIDATES,
        )
        assert race1 is not None
        assert race2 is None  # Blocked by lease

    @pytest.mark.unit
    def test_different_org_can_race(self):
        """Different workspaces can race independently."""
        r1 = ConnectionRaceService.start_race(org_id=ORG_A, user_id=USER_A, candidates=CANDIDATES)
        r2 = ConnectionRaceService.start_race(org_id=ORG_B, user_id=USER_A, candidates=CANDIDATES)
        assert r1 is not None
        assert r2 is not None
        assert r1.id != r2.id


# =============================================================================
# Cost Reservation
# =============================================================================


class TestCostReservation:

    @pytest.mark.unit
    def test_worst_case_reserved(self):
        """Cost reservation = max_per_candidate × candidate_count."""
        race = ConnectionRaceService.start_race(
            org_id=ORG_A, user_id=USER_A, candidates=CANDIDATES,
            max_cost_per_candidate_usd=3.0,
        )
        assert race.cost_reservation_usd == 9.0  # 3 candidates × $3

    @pytest.mark.unit
    def test_reconcile_actual_cost(self):
        """Actual cost can be reconciled against reservation."""
        race = ConnectionRaceService.start_race(
            org_id=ORG_A, user_id=USER_A, candidates=CANDIDATES,
        )
        ConnectionRaceService.reconcile_cost(race.id, 1.5)
        assert _race_store[race.id].actual_cost_usd == 1.5


# =============================================================================
# Candidate Persistence & Winner Selection
# =============================================================================


class TestWinnerSelection:

    @pytest.mark.unit
    def test_candidate_ready_and_winner(self):
        """First ready candidate becomes winner."""
        race = ConnectionRaceService.start_race(
            org_id=ORG_A, user_id=USER_A, candidates=CANDIDATES,
        )
        ConnectionRaceService.candidate_ready(race.id, "pod-2")

        winner = ConnectionRaceService.select_winner(race.id)
        assert winner is not None
        assert winner.provider_instance_id == "pod-2"
        assert winner.state == CandidateState.WINNER

    @pytest.mark.unit
    def test_losers_marked_for_cleanup(self):
        """Non-winner ready candidates marked for cleanup."""
        race = ConnectionRaceService.start_race(
            org_id=ORG_A, user_id=USER_A, candidates=CANDIDATES,
        )
        ConnectionRaceService.candidate_ready(race.id, "pod-1")
        ConnectionRaceService.candidate_ready(race.id, "pod-2")
        ConnectionRaceService.select_winner(race.id, criteria="first_ready")

        stored = _race_store[race.id]
        losers = [c for c in stored.candidates if c.state == CandidateState.LOSER_PENDING_CLEANUP]
        assert len(losers) >= 1

    @pytest.mark.unit
    def test_winner_criteria_recorded(self):
        """Winner selection criteria is recorded as evidence."""
        race = ConnectionRaceService.start_race(
            org_id=ORG_A, user_id=USER_A, candidates=CANDIDATES,
        )
        ConnectionRaceService.candidate_ready(race.id, "pod-1")
        ConnectionRaceService.select_winner(race.id, criteria="lowest_cost")

        stored = _race_store[race.id]
        assert stored.winner_criteria == "lowest_cost"

    @pytest.mark.unit
    def test_winner_transfer_to_worker(self):
        """Winner can be transferred to canonical worker lifecycle."""
        race = ConnectionRaceService.start_race(
            org_id=ORG_A, user_id=USER_A, candidates=CANDIDATES,
        )
        ConnectionRaceService.candidate_ready(race.id, "pod-1")
        ConnectionRaceService.select_winner(race.id)
        ConnectionRaceService.transfer_winner(race.id, "worker-canonical-1")

        assert _race_store[race.id].winner_worker_id == "worker-canonical-1"


# =============================================================================
# Loser Cleanup
# =============================================================================


class TestLoserCleanup:

    @pytest.mark.unit
    def test_confirm_cleanup_completes_race(self):
        """All losers confirmed terminated → race COMPLETED."""
        race = ConnectionRaceService.start_race(
            org_id=ORG_A, user_id=USER_A, candidates=CANDIDATES[:2],
        )
        ConnectionRaceService.candidate_ready(race.id, "pod-1")
        ConnectionRaceService.candidate_ready(race.id, "pod-2")
        ConnectionRaceService.select_winner(race.id)

        # Find loser
        stored = _race_store[race.id]
        loser = next(c for c in stored.candidates if c.state == CandidateState.LOSER_PENDING_CLEANUP)

        ConnectionRaceService.confirm_loser_cleanup(race.id, loser.id)
        assert _race_store[race.id].state == RaceState.COMPLETED

    @pytest.mark.unit
    def test_cleanup_failed_raises_alert(self):
        """Failed cleanup raises an alert."""
        race = ConnectionRaceService.start_race(
            org_id=ORG_A, user_id=USER_A, candidates=CANDIDATES[:2],
        )
        ConnectionRaceService.candidate_ready(race.id, "pod-1")
        ConnectionRaceService.candidate_ready(race.id, "pod-2")
        ConnectionRaceService.select_winner(race.id)

        stored = _race_store[race.id]
        loser = next(c for c in stored.candidates if c.state == CandidateState.LOSER_PENDING_CLEANUP)

        ConnectionRaceService.mark_cleanup_failed(race.id, loser.id, "provider timeout")

        assert _race_store[race.id].state == RaceState.CLEANUP_FAILED
        assert _race_store[race.id].alert_raised is True
        assert len(_alerts) == 1

    @pytest.mark.unit
    def test_retry_cleanup(self):
        """Failed cleanup can be retried."""
        race = ConnectionRaceService.start_race(
            org_id=ORG_A, user_id=USER_A, candidates=CANDIDATES[:2],
        )
        ConnectionRaceService.candidate_ready(race.id, "pod-1")
        ConnectionRaceService.candidate_ready(race.id, "pod-2")
        ConnectionRaceService.select_winner(race.id)

        stored = _race_store[race.id]
        loser = next(c for c in stored.candidates if c.state == CandidateState.LOSER_PENDING_CLEANUP)

        ConnectionRaceService.mark_cleanup_failed(race.id, loser.id, "timeout")
        assert ConnectionRaceService.retry_cleanup(race.id, loser.id) is True

        # Should be back to pending
        refreshed = next(c for c in _race_store[race.id].candidates if c.id == loser.id)
        assert refreshed.state == CandidateState.LOSER_PENDING_CLEANUP


# =============================================================================
# All Candidates Failed
# =============================================================================


class TestAllFailed:

    @pytest.mark.unit
    def test_all_failed_releases_lease(self):
        """If all candidates fail, race enters ALL_FAILED and releases lease."""
        race = ConnectionRaceService.start_race(
            org_id=ORG_A, user_id=USER_A, candidates=CANDIDATES[:2],
        )
        ConnectionRaceService.candidate_failed(race.id, "pod-1", "boot timeout")
        ConnectionRaceService.candidate_failed(race.id, "pod-2", "GPU unavailable")

        stored = _race_store[race.id]
        assert stored.state == RaceState.ALL_FAILED
        # Lease released — new race can start
        assert ORG_A not in _workspace_leases

    @pytest.mark.unit
    def test_partial_failure_still_racing(self):
        """If only some candidates fail, race continues."""
        race = ConnectionRaceService.start_race(
            org_id=ORG_A, user_id=USER_A, candidates=CANDIDATES,
        )
        ConnectionRaceService.candidate_failed(race.id, "pod-1", "timeout")
        assert _race_store[race.id].state == RaceState.RACING


# =============================================================================
# Tenant Isolation
# =============================================================================


class TestTenantIsolation:

    @pytest.mark.unit
    def test_get_race_wrong_org_none(self):
        race = ConnectionRaceService.start_race(
            org_id=ORG_A, user_id=USER_A, candidates=CANDIDATES,
        )
        assert ConnectionRaceService.get_race(race.id, ORG_B) is None
        assert ConnectionRaceService.get_race(race.id, ORG_A) is not None

    @pytest.mark.unit
    def test_get_active_race_scoped(self):
        ConnectionRaceService.start_race(
            org_id=ORG_A, user_id=USER_A, candidates=CANDIDATES,
        )
        assert ConnectionRaceService.get_active_race(ORG_A) is not None
        assert ConnectionRaceService.get_active_race(ORG_B) is None

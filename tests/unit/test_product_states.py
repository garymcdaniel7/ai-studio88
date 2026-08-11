"""Shared Product State Contract Tests (Story 113).

Proves: state transitions, simulation labeling, completion requirements,
stale detection, and cross-surface consistency.

Run with:
    pytest tests/unit/test_product_states.py -v
"""
from __future__ import annotations

import pytest

from backend.product_states import (
    STALE_THRESHOLD_SECONDS,
    CapabilityState,
    CapabilityStatus,
    CompletionGuardError,
    ExecutionState,
    ExecutionStatus,
    MediaSurface,
    clear_registry,
    derive_capability_state,
    derive_execution_state,
    get_all_capabilities,
    get_available_surfaces,
    get_capability,
    guard_production_completion,
    is_status_stale,
    register_capability,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def _clean():
    clear_registry()
    yield
    clear_registry()


# =============================================================================
# Capability State Derivation
# =============================================================================


class TestCapabilityDerivation:

    @pytest.mark.unit
    def test_all_clear_is_available(self):
        """Valid credentials + health pass → AVAILABLE."""
        state = derive_capability_state(
            credentials_configured=True, credentials_valid=True, health_check_passed=True,
        )
        assert state == CapabilityState.AVAILABLE

    @pytest.mark.unit
    def test_no_credentials_unavailable(self):
        """No credentials → UNAVAILABLE."""
        state = derive_capability_state(credentials_configured=False)
        assert state == CapabilityState.UNAVAILABLE

    @pytest.mark.unit
    def test_invalid_credentials_unavailable(self):
        """Invalid credentials → UNAVAILABLE."""
        state = derive_capability_state(
            credentials_configured=True, credentials_valid=False,
        )
        assert state == CapabilityState.UNAVAILABLE

    @pytest.mark.unit
    def test_health_failed_unavailable(self):
        """Health check failed → UNAVAILABLE."""
        state = derive_capability_state(
            credentials_configured=True, credentials_valid=True, health_check_passed=False,
        )
        assert state == CapabilityState.UNAVAILABLE

    @pytest.mark.unit
    def test_degradation_reported(self):
        """Health pass + degradation reason → DEGRADED."""
        state = derive_capability_state(
            credentials_configured=True, credentials_valid=True,
            health_check_passed=True, degradation_reason="Rate limited",
        )
        assert state == CapabilityState.DEGRADED

    @pytest.mark.unit
    def test_explicit_simulation(self):
        """Explicit simulation → SIMULATION regardless of other evidence."""
        state = derive_capability_state(
            credentials_configured=True, credentials_valid=True,
            health_check_passed=True, explicit_simulation=True,
        )
        assert state == CapabilityState.SIMULATION

    @pytest.mark.unit
    def test_ambiguous_fails_safe(self):
        """Unchecked credentials/health → UNKNOWN (fail-safe)."""
        state = derive_capability_state(
            credentials_configured=True, credentials_valid=None, health_check_passed=None,
        )
        assert state == CapabilityState.UNKNOWN


# =============================================================================
# Execution State Derivation
# =============================================================================


class TestExecutionDerivation:

    @pytest.mark.unit
    def test_verified_output_completed(self):
        """All output evidence present → COMPLETED."""
        state = derive_execution_state(
            has_asset_id=True, has_storage_key=True, has_checksum=True,
        )
        assert state == ExecutionState.COMPLETED

    @pytest.mark.unit
    def test_simulation_output_simulation_done(self):
        """Simulation with output → SIMULATION_DONE."""
        state = derive_execution_state(
            is_simulation=True, has_asset_id=True, has_storage_key=True, has_checksum=True,
        )
        assert state == ExecutionState.SIMULATION_DONE

    @pytest.mark.unit
    def test_cancelled(self):
        """Cancelled flag → CANCELLED."""
        state = derive_execution_state(is_cancelled=True)
        assert state == ExecutionState.CANCELLED

    @pytest.mark.unit
    def test_error(self):
        """Error flag → FAILED."""
        state = derive_execution_state(has_error=True)
        assert state == ExecutionState.FAILED

    @pytest.mark.unit
    def test_executing(self):
        """Executing flag → RUNNING."""
        state = derive_execution_state(is_executing=True)
        assert state == ExecutionState.RUNNING

    @pytest.mark.unit
    def test_default_queued(self):
        """No flags → QUEUED."""
        state = derive_execution_state()
        assert state == ExecutionState.QUEUED

    @pytest.mark.unit
    def test_incomplete_lineage(self):
        """Output exists but lineage incomplete → LINEAGE_INCOMPLETE."""
        state = derive_execution_state(
            has_asset_id=True, has_storage_key=True, has_checksum=True,
            lineage_complete=False,
        )
        assert state == ExecutionState.LINEAGE_INCOMPLETE

    @pytest.mark.unit
    def test_missing_checksum_not_completed(self):
        """Missing checksum → not completed (stays QUEUED)."""
        state = derive_execution_state(
            has_asset_id=True, has_storage_key=True, has_checksum=False,
        )
        assert state == ExecutionState.QUEUED


# =============================================================================
# Simulation Labeling
# =============================================================================


class TestSimulationLabeling:

    @pytest.mark.unit
    def test_simulation_done_is_not_production_complete(self):
        """SIMULATION_DONE is NOT production-complete."""
        assert not ExecutionState.SIMULATION_DONE.is_production_complete

    @pytest.mark.unit
    def test_completed_is_production_complete(self):
        """Only COMPLETED is production-complete."""
        assert ExecutionState.COMPLETED.is_production_complete

    @pytest.mark.unit
    def test_simulation_capability_distinct(self):
        """SIMULATION capability state is distinct from AVAILABLE."""
        assert CapabilityState.SIMULATION != CapabilityState.AVAILABLE

    @pytest.mark.unit
    def test_simulation_done_is_terminal(self):
        """SIMULATION_DONE is a terminal state."""
        assert ExecutionState.SIMULATION_DONE.is_terminal


# =============================================================================
# Completion Guard
# =============================================================================


class TestCompletionGuard:

    @pytest.mark.unit
    def test_all_evidence_passes(self):
        """All evidence present passes guard."""
        guard_production_completion(
            has_asset_id=True, has_storage_key=True, has_checksum=True,
        )  # No exception

    @pytest.mark.unit
    def test_simulation_blocked(self):
        """Simulation cannot pass production completion."""
        with pytest.raises(CompletionGuardError) as exc_info:
            guard_production_completion(
                is_simulation=True, has_asset_id=True,
                has_storage_key=True, has_checksum=True,
            )
        assert "simulation" in exc_info.value.message.lower()

    @pytest.mark.unit
    def test_missing_asset_blocked(self):
        """Missing asset_id blocks completion."""
        with pytest.raises(CompletionGuardError) as exc_info:
            guard_production_completion(
                has_asset_id=False, has_storage_key=True, has_checksum=True,
            )
        assert "asset_id" in exc_info.value.missing

    @pytest.mark.unit
    def test_missing_storage_blocked(self):
        """Missing storage_key blocks completion."""
        with pytest.raises(CompletionGuardError) as exc_info:
            guard_production_completion(
                has_asset_id=True, has_storage_key=False, has_checksum=True,
            )
        assert "storage_key" in exc_info.value.missing

    @pytest.mark.unit
    def test_missing_checksum_blocked(self):
        """Missing checksum blocks completion."""
        with pytest.raises(CompletionGuardError) as exc_info:
            guard_production_completion(
                has_asset_id=True, has_storage_key=True, has_checksum=False,
            )
        assert "checksum" in exc_info.value.missing

    @pytest.mark.unit
    def test_incomplete_lineage_blocked(self):
        """Incomplete lineage blocks completion."""
        with pytest.raises(CompletionGuardError) as exc_info:
            guard_production_completion(
                has_asset_id=True, has_storage_key=True, has_checksum=True,
                lineage_complete=False,
            )
        assert "lineage" in exc_info.value.missing


# =============================================================================
# Stale Detection
# =============================================================================


class TestStaleDetection:

    @pytest.mark.unit
    def test_recent_check_not_stale(self):
        """Check from now is not stale."""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        assert is_status_stale(now, now) is False

    @pytest.mark.unit
    def test_old_check_is_stale(self):
        """Check older than threshold is stale."""
        assert is_status_stale("2020-01-01T00:00:00+00:00", "2025-06-01T00:00:00+00:00") is True

    @pytest.mark.unit
    def test_threshold_value(self):
        """Stale threshold is 5 minutes."""
        assert STALE_THRESHOLD_SECONDS == 300


# =============================================================================
# Cross-Surface Registry
# =============================================================================


class TestRegistry:

    @pytest.mark.unit
    def test_register_and_retrieve(self):
        """Can register and retrieve capability status."""
        status = CapabilityStatus(
            surface=MediaSurface.IMAGE_GENERATION,
            state=CapabilityState.AVAILABLE,
            provider="comfyui",
        )
        register_capability(status)
        result = get_capability(MediaSurface.IMAGE_GENERATION)
        assert result.state == CapabilityState.AVAILABLE

    @pytest.mark.unit
    def test_unregistered_returns_unknown(self):
        """Unregistered surface returns UNKNOWN (fail-safe)."""
        result = get_capability(MediaSurface.LIP_SYNC)
        assert result.state == CapabilityState.UNKNOWN

    @pytest.mark.unit
    def test_get_available_surfaces(self):
        """get_available_surfaces returns only AVAILABLE."""
        register_capability(CapabilityStatus(
            surface=MediaSurface.IMAGE_GENERATION, state=CapabilityState.AVAILABLE,
        ))
        register_capability(CapabilityStatus(
            surface=MediaSurface.VIDEO_GENERATION, state=CapabilityState.UNAVAILABLE,
        ))
        register_capability(CapabilityStatus(
            surface=MediaSurface.AUDIO_VOICE, state=CapabilityState.SIMULATION,
        ))
        available = get_available_surfaces()
        assert MediaSurface.IMAGE_GENERATION in available
        assert MediaSurface.VIDEO_GENERATION not in available
        assert MediaSurface.AUDIO_VOICE not in available

    @pytest.mark.unit
    def test_all_media_surfaces_defined(self):
        """All expected media surfaces exist in enum."""
        surfaces = set(MediaSurface)
        assert len(surfaces) >= 9

    @pytest.mark.unit
    def test_status_serializable(self):
        """CapabilityStatus.to_dict() is JSON-serializable."""
        import json
        status = CapabilityStatus(
            surface=MediaSurface.IMAGE_GENERATION,
            state=CapabilityState.DEGRADED,
            explanation="Rate limited to 5 req/min",
        )
        json.dumps(status.to_dict())

    @pytest.mark.unit
    def test_execution_status_serializable(self):
        """ExecutionStatus.to_dict() is JSON-serializable."""
        import json
        status = ExecutionStatus(
            job_id="j-1", surface=MediaSurface.QUICK_EDIT,
            state=ExecutionState.RUNNING, progress_pct=45.0,
        )
        json.dumps(status.to_dict())


# =============================================================================
# State Properties
# =============================================================================


class TestStateProperties:

    @pytest.mark.unit
    def test_terminal_states(self):
        """Terminal states correctly identified."""
        assert ExecutionState.COMPLETED.is_terminal
        assert ExecutionState.FAILED.is_terminal
        assert ExecutionState.CANCELLED.is_terminal
        assert ExecutionState.SIMULATION_DONE.is_terminal
        assert ExecutionState.LINEAGE_INCOMPLETE.is_terminal
        assert not ExecutionState.QUEUED.is_terminal
        assert not ExecutionState.RUNNING.is_terminal

    @pytest.mark.unit
    def test_active_states(self):
        """Active states correctly identified."""
        assert ExecutionState.QUEUED.is_active
        assert ExecutionState.RUNNING.is_active
        assert not ExecutionState.COMPLETED.is_active
        assert not ExecutionState.FAILED.is_active

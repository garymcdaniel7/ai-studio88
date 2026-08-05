"""Provider Readiness Contract Tests (Story 093).

Proves: live-ready enforcement, simulation labeling, degraded handling,
submission blocking, mode propagation, state derivation, and fail-safe.

Run with:
    pytest tests/unit/test_provider_readiness.py -v
"""
from __future__ import annotations

import pytest

from backend.provider_readiness import (
    ExecutionMode,
    JobModeRecord,
    ProviderName,
    ProviderState,
    ProviderStatus,
    ReadinessEvidence,
    SubmissionBlockedError,
    clear_registry,
    create_job_mode,
    derive_provider_state,
    get_live_ready_providers,
    get_provider_status,
    guard_production_submission,
    guard_simulation_submission,
    list_provider_statuses,
    register_provider_status,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def _clean():
    clear_registry()
    yield
    clear_registry()


def _live_ready_status(provider: ProviderName = ProviderName.VAST_AI) -> ProviderStatus:
    return ProviderStatus(
        provider=provider,
        state=ProviderState.LIVE_READY,
        evidence=ReadinessEvidence(
            credentials_present=True,
            credentials_valid=True,
            health_check_passed=True,
            health_check_latency_ms=120,
        ),
    )


def _simulation_status(provider: ProviderName = ProviderName.SIMULATION) -> ProviderStatus:
    return ProviderStatus(
        provider=provider,
        state=ProviderState.SIMULATION,
        is_simulation=True,
    )


# =============================================================================
# State Derivation
# =============================================================================


class TestStateDerivation:

    @pytest.mark.unit
    def test_all_checks_pass_live_ready(self):
        """Valid credentials + health pass → LIVE_READY."""
        state, evidence = derive_provider_state(
            credentials_present=True,
            credentials_valid=True,
            health_check_passed=True,
        )
        assert state == ProviderState.LIVE_READY

    @pytest.mark.unit
    def test_no_credentials_unavailable(self):
        """No credentials → UNAVAILABLE."""
        state, _ = derive_provider_state(credentials_present=False)
        assert state == ProviderState.UNAVAILABLE

    @pytest.mark.unit
    def test_invalid_credentials_configured(self):
        """Credentials present but invalid → CONFIGURED."""
        state, _ = derive_provider_state(
            credentials_present=True,
            credentials_valid=False,
        )
        assert state == ProviderState.CONFIGURED

    @pytest.mark.unit
    def test_health_failed_configured(self):
        """Credentials valid but health fails → CONFIGURED."""
        state, _ = derive_provider_state(
            credentials_present=True,
            credentials_valid=True,
            health_check_passed=False,
            error="Connection refused",
        )
        assert state == ProviderState.CONFIGURED

    @pytest.mark.unit
    def test_health_pass_with_degradation(self):
        """Health passes but degradation reported → DEGRADED."""
        state, _ = derive_provider_state(
            credentials_present=True,
            credentials_valid=True,
            health_check_passed=True,
            degradation_reason="Rate limited to 5 req/min",
        )
        assert state == ProviderState.DEGRADED

    @pytest.mark.unit
    def test_explicit_simulation(self):
        """Explicit simulation flag → SIMULATION regardless of other evidence."""
        state, _ = derive_provider_state(
            credentials_present=True,
            credentials_valid=True,
            health_check_passed=True,
            explicit_simulation=True,
        )
        assert state == ProviderState.SIMULATION

    @pytest.mark.unit
    def test_unknown_state_fails_safe(self):
        """Ambiguous evidence → UNAVAILABLE (fail-safe)."""
        state, evidence = derive_provider_state(
            credentials_present=True,
            credentials_valid=None,  # Not checked
            health_check_passed=None,  # Not checked
        )
        assert state == ProviderState.UNAVAILABLE
        assert evidence.error_message is not None

    @pytest.mark.unit
    def test_evidence_captures_latency(self):
        """Evidence records health check latency."""
        _, evidence = derive_provider_state(
            credentials_present=True,
            credentials_valid=True,
            health_check_passed=True,
            health_latency_ms=250,
        )
        assert evidence.health_check_latency_ms == 250


# =============================================================================
# Live-Ready Enforcement
# =============================================================================


class TestLiveReadyEnforcement:

    @pytest.mark.unit
    def test_live_ready_allows_production(self):
        """LIVE_READY allows production submission."""
        status = _live_ready_status()
        guard_production_submission(status)  # Should not raise

    @pytest.mark.unit
    def test_degraded_blocks_production(self):
        """DEGRADED blocks production submission."""
        status = ProviderStatus(
            provider=ProviderName.VAST_AI,
            state=ProviderState.DEGRADED,
        )
        with pytest.raises(SubmissionBlockedError) as exc_info:
            guard_production_submission(status)
        assert "degraded" in exc_info.value.state

    @pytest.mark.unit
    def test_configured_blocks_production(self):
        """CONFIGURED blocks production submission."""
        status = ProviderStatus(
            provider=ProviderName.COMFYUI,
            state=ProviderState.CONFIGURED,
        )
        with pytest.raises(SubmissionBlockedError):
            guard_production_submission(status)

    @pytest.mark.unit
    def test_unavailable_blocks_production(self):
        """UNAVAILABLE blocks production submission."""
        status = ProviderStatus(
            provider=ProviderName.RUNPOD,
            state=ProviderState.UNAVAILABLE,
        )
        with pytest.raises(SubmissionBlockedError):
            guard_production_submission(status)

    @pytest.mark.unit
    def test_simulation_blocks_production(self):
        """SIMULATION state blocks production submission."""
        status = _simulation_status()
        with pytest.raises(SubmissionBlockedError):
            guard_production_submission(status)


# =============================================================================
# Simulation Labeling
# =============================================================================


class TestSimulationLabeling:

    @pytest.mark.unit
    def test_simulation_state_allows_simulation_submission(self):
        """SIMULATION state allows simulation submission."""
        status = _simulation_status()
        guard_simulation_submission(status)  # Should not raise

    @pytest.mark.unit
    def test_live_ready_blocks_simulation_submission(self):
        """LIVE_READY blocks simulation submission (prevent accidental sim on live)."""
        status = _live_ready_status()
        with pytest.raises(SubmissionBlockedError):
            guard_simulation_submission(status)

    @pytest.mark.unit
    def test_simulation_flag_on_status(self):
        """Simulation status has is_simulation flag."""
        status = _simulation_status()
        assert status.is_simulation is True

    @pytest.mark.unit
    def test_live_ready_not_simulation(self):
        """Live-ready status is not simulation."""
        status = _live_ready_status()
        assert status.is_simulation is False


# =============================================================================
# Degraded Handling
# =============================================================================


class TestDegradedHandling:

    @pytest.mark.unit
    def test_degraded_is_not_healthy(self):
        """DEGRADED is NOT reported as healthy."""
        status = ProviderStatus(
            provider=ProviderName.VAST_AI,
            state=ProviderState.DEGRADED,
            evidence=ReadinessEvidence(degradation_reason="High latency"),
        )
        assert status.is_healthy is False

    @pytest.mark.unit
    def test_degraded_blocks_production(self):
        """DEGRADED cannot submit production jobs."""
        status = ProviderStatus(
            provider=ProviderName.VAST_AI,
            state=ProviderState.DEGRADED,
        )
        assert status.allows_production_submission is False

    @pytest.mark.unit
    def test_only_live_ready_is_healthy(self):
        """Only LIVE_READY reports is_healthy=True."""
        for state in ProviderState:
            status = ProviderStatus(provider=ProviderName.VAST_AI, state=state)
            if state == ProviderState.LIVE_READY:
                assert status.is_healthy is True
            else:
                assert status.is_healthy is False


# =============================================================================
# Mode Propagation
# =============================================================================


class TestModePropagation:

    @pytest.mark.unit
    def test_production_mode_from_live_ready(self):
        """LIVE_READY provider creates PRODUCTION mode record."""
        status = _live_ready_status()
        mode = create_job_mode(status)
        assert mode.mode == ExecutionMode.PRODUCTION
        assert mode.provider == ProviderName.VAST_AI
        assert mode.provider_state_at_submission == ProviderState.LIVE_READY

    @pytest.mark.unit
    def test_simulation_mode_from_simulation_state(self):
        """SIMULATION provider creates SIMULATION mode record."""
        status = _simulation_status()
        mode = create_job_mode(status)
        assert mode.mode == ExecutionMode.SIMULATION

    @pytest.mark.unit
    def test_explicit_simulation_flag_overrides(self):
        """Explicit simulation flag creates SIMULATION mode regardless of state."""
        status = _live_ready_status()
        mode = create_job_mode(status, explicit_simulation=True)
        assert mode.mode == ExecutionMode.SIMULATION

    @pytest.mark.unit
    def test_mode_captures_evidence_snapshot(self):
        """Mode record captures evidence at submission time."""
        status = _live_ready_status()
        mode = create_job_mode(status)
        assert mode.evidence_snapshot["credentials_valid"] is True
        assert mode.evidence_snapshot["health_check_passed"] is True

    @pytest.mark.unit
    def test_mode_has_timestamp(self):
        """Mode record has submitted_at timestamp."""
        status = _live_ready_status()
        mode = create_job_mode(status)
        assert mode.submitted_at is not None

    @pytest.mark.unit
    def test_mode_serializable(self):
        """JobModeRecord.to_dict() is JSON-serializable."""
        import json
        status = _live_ready_status()
        mode = create_job_mode(status)
        json.dumps(mode.to_dict())


# =============================================================================
# Provider Registry
# =============================================================================


class TestProviderRegistry:

    @pytest.mark.unit
    def test_register_and_retrieve(self):
        """Can register and retrieve provider status."""
        status = _live_ready_status()
        register_provider_status(status)
        result = get_provider_status(ProviderName.VAST_AI)
        assert result.state == ProviderState.LIVE_READY

    @pytest.mark.unit
    def test_unregistered_returns_unavailable(self):
        """Unregistered provider returns UNAVAILABLE (fail-safe)."""
        result = get_provider_status(ProviderName.RUNPOD)
        assert result.state == ProviderState.UNAVAILABLE
        assert result.evidence.error_message is not None

    @pytest.mark.unit
    def test_list_all_statuses(self):
        """list_provider_statuses returns all registered."""
        register_provider_status(_live_ready_status(ProviderName.VAST_AI))
        register_provider_status(_simulation_status(ProviderName.SIMULATION))
        statuses = list_provider_statuses()
        assert len(statuses) == 2

    @pytest.mark.unit
    def test_get_live_ready_providers(self):
        """get_live_ready_providers filters to LIVE_READY only."""
        register_provider_status(_live_ready_status(ProviderName.VAST_AI))
        register_provider_status(_simulation_status(ProviderName.SIMULATION))
        register_provider_status(ProviderStatus(
            provider=ProviderName.RUNPOD, state=ProviderState.CONFIGURED,
        ))
        live = get_live_ready_providers()
        assert len(live) == 1
        assert live[0].provider == ProviderName.VAST_AI

    @pytest.mark.unit
    def test_status_serializable(self):
        """ProviderStatus.to_dict() is JSON-serializable."""
        import json
        status = _live_ready_status()
        json.dumps(status.to_dict())

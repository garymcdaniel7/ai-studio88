"""Provider Readiness Contract — Story 093.

One truthful capability-state contract for all providers. Prevents production
submission when provider is not live-ready. Requires explicit simulation
selection and carries mode through jobs and artifacts.

Provider States:
    LIVE_READY      — Fully operational, credentials valid, health confirmed
    DEGRADED        — Partially functional (e.g., slow, rate-limited)
    CONFIGURED      — Credentials present but not verified or health check failed
    UNAVAILABLE     — Not configured or permanently unreachable
    SIMULATION      — Explicit simulation mode (developer/test only)

Invariants:
1. Live submission blocked unless LIVE_READY
2. DEGRADED cannot masquerade as healthy
3. Simulation requires explicit opt-in (never auto-selected for production)
4. Job and artifact records preserve the provider mode at execution time
5. State changes are observable (timestamp + evidence)
6. Unknown/unresolved state fails safe to UNAVAILABLE
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


# =============================================================================
# Provider Capability State
# =============================================================================


class ProviderState(StrEnum):
    LIVE_READY = "live_ready"           # Fully operational
    DEGRADED = "degraded"               # Partially functional
    CONFIGURED = "configured"           # Creds present, not verified
    UNAVAILABLE = "unavailable"         # Not configured or unreachable
    SIMULATION = "simulation"           # Explicit dev/test mode


class ProviderName(StrEnum):
    VAST_AI = "vast_ai"
    RUNPOD = "runpod"
    COMFYUI = "comfyui"
    ELEVENLABS = "elevenlabs"
    SUNO = "suno"
    OLLAMA = "ollama"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    BACKBLAZE_B2 = "backblaze_b2"
    SIMULATION = "simulation"


# =============================================================================
# Readiness Evidence
# =============================================================================


@dataclass
class ReadinessEvidence:
    """Evidence supporting the current provider state."""

    checked_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    credentials_present: bool = False
    credentials_valid: bool | None = None   # None = not checked
    health_check_passed: bool | None = None
    health_check_latency_ms: int | None = None
    last_successful_job_at: str | None = None
    error_message: str | None = None
    degradation_reason: str | None = None

    def to_dict(self) -> dict:
        return {
            "checked_at": self.checked_at,
            "credentials_present": self.credentials_present,
            "credentials_valid": self.credentials_valid,
            "health_check_passed": self.health_check_passed,
            "health_check_latency_ms": self.health_check_latency_ms,
            "last_successful_job_at": self.last_successful_job_at,
            "error_message": self.error_message,
            "degradation_reason": self.degradation_reason,
        }


# =============================================================================
# Provider Status Record
# =============================================================================


@dataclass
class ProviderStatus:
    """Current status of a single provider."""

    provider: ProviderName
    state: ProviderState
    evidence: ReadinessEvidence = field(default_factory=ReadinessEvidence)
    is_simulation: bool = False
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def is_live_ready(self) -> bool:
        return self.state == ProviderState.LIVE_READY

    @property
    def is_healthy(self) -> bool:
        """Only LIVE_READY is considered healthy. DEGRADED is NOT healthy."""
        return self.state == ProviderState.LIVE_READY

    @property
    def allows_production_submission(self) -> bool:
        """Only LIVE_READY allows production job submission."""
        return self.state == ProviderState.LIVE_READY

    @property
    def allows_simulation_submission(self) -> bool:
        """SIMULATION state allows simulation jobs."""
        return self.state == ProviderState.SIMULATION

    def to_dict(self) -> dict:
        return {
            "provider": self.provider.value,
            "state": self.state.value,
            "is_live_ready": self.is_live_ready,
            "is_healthy": self.is_healthy,
            "is_simulation": self.is_simulation,
            "evidence": self.evidence.to_dict(),
            "updated_at": self.updated_at,
        }


# =============================================================================
# State Derivation
# =============================================================================


def derive_provider_state(
    *,
    credentials_present: bool = False,
    credentials_valid: bool | None = None,
    health_check_passed: bool | None = None,
    health_latency_ms: int | None = None,
    explicit_simulation: bool = False,
    degradation_reason: str | None = None,
    error: str | None = None,
) -> tuple[ProviderState, ReadinessEvidence]:
    """Derive provider state from observable evidence.

    Rules:
    1. Explicit simulation → SIMULATION
    2. No credentials → UNAVAILABLE
    3. Credentials present + not valid → CONFIGURED
    4. Credentials valid + health fails → CONFIGURED
    5. Credentials valid + health passes + degradation → DEGRADED
    6. Credentials valid + health passes → LIVE_READY
    7. Unknown/ambiguous → UNAVAILABLE (fail-safe)
    """
    evidence = ReadinessEvidence(
        credentials_present=credentials_present,
        credentials_valid=credentials_valid,
        health_check_passed=health_check_passed,
        health_check_latency_ms=health_latency_ms,
        error_message=error,
        degradation_reason=degradation_reason,
    )

    # Rule 1: Explicit simulation
    if explicit_simulation:
        return ProviderState.SIMULATION, evidence

    # Rule 2: No credentials
    if not credentials_present:
        evidence.error_message = error or "No credentials configured"
        return ProviderState.UNAVAILABLE, evidence

    # Rule 3: Credentials not valid
    if credentials_valid is False:
        evidence.error_message = error or "Credentials invalid"
        return ProviderState.CONFIGURED, evidence

    # Rule 4: Health check failed
    if health_check_passed is False:
        evidence.error_message = error or "Health check failed"
        return ProviderState.CONFIGURED, evidence

    # Rule 5: Health passed but degraded
    if health_check_passed is True and degradation_reason:
        return ProviderState.DEGRADED, evidence

    # Rule 6: Everything checks out
    if credentials_valid is True and health_check_passed is True:
        return ProviderState.LIVE_READY, evidence

    # Rule 7: Unknown state — fail safe
    evidence.error_message = error or "State could not be determined"
    return ProviderState.UNAVAILABLE, evidence


# =============================================================================
# Submission Guard
# =============================================================================


class SubmissionBlockedError(Exception):
    """Raised when submission is blocked due to provider state."""

    def __init__(self, message: str, provider: str, state: str):
        self.message = message
        self.provider = provider
        self.state = state
        super().__init__(message)


def guard_production_submission(status: ProviderStatus) -> None:
    """Guard: blocks production submission unless provider is LIVE_READY.

    Raises SubmissionBlockedError if not live-ready.
    """
    if status.allows_production_submission:
        return  # OK

    raise SubmissionBlockedError(
        f"Production submission blocked: provider '{status.provider.value}' "
        f"is '{status.state.value}', not 'live_ready'",
        provider=status.provider.value,
        state=status.state.value,
    )


def guard_simulation_submission(status: ProviderStatus) -> None:
    """Guard: blocks simulation submission unless provider is in SIMULATION state.

    Prevents accidentally using simulation mode on a live provider.
    """
    if status.allows_simulation_submission:
        return  # OK

    raise SubmissionBlockedError(
        f"Simulation submission requires explicit simulation mode. "
        f"Provider '{status.provider.value}' is '{status.state.value}'",
        provider=status.provider.value,
        state=status.state.value,
    )


# =============================================================================
# Execution Mode (carried through jobs and artifacts)
# =============================================================================


class ExecutionMode(StrEnum):
    PRODUCTION = "production"       # Real provider, real output
    SIMULATION = "simulation"       # Simulated, not production-grade


@dataclass
class JobModeRecord:
    """Mode metadata carried on every job and artifact."""

    mode: ExecutionMode
    provider: ProviderName
    provider_state_at_submission: ProviderState
    submitted_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    evidence_snapshot: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "mode": self.mode.value,
            "provider": self.provider.value,
            "provider_state_at_submission": self.provider_state_at_submission.value,
            "submitted_at": self.submitted_at,
        }


def create_job_mode(
    status: ProviderStatus,
    *,
    explicit_simulation: bool = False,
) -> JobModeRecord:
    """Create a JobModeRecord from provider status at submission time.

    The mode is locked at submission and persisted with the job/artifact.
    """
    if explicit_simulation or status.state == ProviderState.SIMULATION:
        mode = ExecutionMode.SIMULATION
    else:
        mode = ExecutionMode.PRODUCTION

    return JobModeRecord(
        mode=mode,
        provider=status.provider,
        provider_state_at_submission=status.state,
        evidence_snapshot=status.evidence.to_dict(),
    )


# =============================================================================
# Multi-Provider Registry
# =============================================================================


_provider_registry: dict[ProviderName, ProviderStatus] = {}


def clear_registry() -> None:
    """Clear registry (testing only)."""
    _provider_registry.clear()


def register_provider_status(status: ProviderStatus) -> None:
    """Register or update a provider's status."""
    _provider_registry[status.provider] = status


def get_provider_status(provider: ProviderName) -> ProviderStatus:
    """Get current status for a provider.

    Returns UNAVAILABLE if not registered (fail-safe).
    """
    if provider in _provider_registry:
        return _provider_registry[provider]

    # Fail-safe: unknown provider is unavailable
    return ProviderStatus(
        provider=provider,
        state=ProviderState.UNAVAILABLE,
        evidence=ReadinessEvidence(error_message="Provider not registered"),
    )


def list_provider_statuses() -> list[ProviderStatus]:
    """List all registered provider statuses."""
    return list(_provider_registry.values())


def get_live_ready_providers() -> list[ProviderStatus]:
    """Get all providers that are LIVE_READY."""
    return [s for s in _provider_registry.values() if s.is_live_ready]

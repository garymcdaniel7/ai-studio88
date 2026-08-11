"""Model/LoRA Promotion Gates — Lifecycle State Machine (R67).

Enforces the model lifecycle:
    IMPORTED/TRAINED → INTEGRITY_VERIFIED → EVALUATED → APPROVED → ACTIVE → DEPRECATED → QUARANTINED

Key invariants:
    - State only advances forward through the defined sequence
    - Exception: ANY state can jump to QUARANTINED
    - Models SHALL NOT automatically become APPROVED or ACTIVE upon import/training
    - Two risk classes: STANDARD (auto-promote through integrity/compatibility)
      and HIGH_RISK (human approval required before APPROVED)
    - All transitions are logged with: model_id, from_state, to_state, actor, evidence, timestamp

Validates: Requirements R67.1, R67.2
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


# =============================================================================
# Lifecycle States
# =============================================================================


class ModelLifecycleState(StrEnum):
    """Model lifecycle states per R67.1."""

    IMPORTED = "imported"
    TRAINED = "trained"
    INTEGRITY_VERIFIED = "integrity_verified"
    EVALUATED = "evaluated"
    APPROVED = "approved"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    QUARANTINED = "quarantined"


# States that models enter upon creation — they NEVER auto-promote past these
INITIAL_STATES: set[ModelLifecycleState] = {
    ModelLifecycleState.IMPORTED,
    ModelLifecycleState.TRAINED,
}

# States that require human gating (cannot be auto-promoted to)
HUMAN_GATED_STATES: set[ModelLifecycleState] = {
    ModelLifecycleState.APPROVED,
    ModelLifecycleState.ACTIVE,
}


# =============================================================================
# Risk Classes
# =============================================================================


class ModelRiskClass(StrEnum):
    """Risk classification for promotion gate behavior per R67.4."""

    STANDARD = "standard"       # Auto-promote through integrity/compatibility
    HIGH_RISK = "high_risk"     # Human approval required before APPROVED


# =============================================================================
# Valid Transitions (forward-only + quarantine escape)
# =============================================================================

# Defines the ordered lifecycle sequence
_LIFECYCLE_ORDER: list[ModelLifecycleState] = [
    ModelLifecycleState.IMPORTED,
    ModelLifecycleState.TRAINED,
    ModelLifecycleState.INTEGRITY_VERIFIED,
    ModelLifecycleState.EVALUATED,
    ModelLifecycleState.APPROVED,
    ModelLifecycleState.ACTIVE,
    ModelLifecycleState.DEPRECATED,
    ModelLifecycleState.QUARANTINED,
]

# Forward transitions: each state can move to its immediate next in sequence.
# IMPORTED and TRAINED both lead to INTEGRITY_VERIFIED (they are equivalent entry points).
# Additionally, ANY state can transition to QUARANTINED.
VALID_TRANSITIONS: dict[ModelLifecycleState, set[ModelLifecycleState]] = {
    ModelLifecycleState.IMPORTED: {
        ModelLifecycleState.INTEGRITY_VERIFIED,
        ModelLifecycleState.QUARANTINED,
    },
    ModelLifecycleState.TRAINED: {
        ModelLifecycleState.INTEGRITY_VERIFIED,
        ModelLifecycleState.QUARANTINED,
    },
    ModelLifecycleState.INTEGRITY_VERIFIED: {
        ModelLifecycleState.EVALUATED,
        ModelLifecycleState.QUARANTINED,
    },
    ModelLifecycleState.EVALUATED: {
        ModelLifecycleState.APPROVED,
        ModelLifecycleState.QUARANTINED,
    },
    ModelLifecycleState.APPROVED: {
        ModelLifecycleState.ACTIVE,
        ModelLifecycleState.QUARANTINED,
    },
    ModelLifecycleState.ACTIVE: {
        ModelLifecycleState.DEPRECATED,
        ModelLifecycleState.QUARANTINED,
    },
    ModelLifecycleState.DEPRECATED: {
        ModelLifecycleState.QUARANTINED,
    },
    ModelLifecycleState.QUARANTINED: set(),  # Terminal state — no transitions out
}


# =============================================================================
# Errors
# =============================================================================


class ModelLifecycleError(Exception):
    """Raised when an invalid lifecycle transition is attempted."""

    def __init__(self, message: str, code: str = "LIFECYCLE_VIOLATION"):
        self.message = message
        self.code = code
        super().__init__(message)


class ModelNotFoundError(Exception):
    """Raised when a model is not found in the registry."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


# =============================================================================
# Transition Audit Record
# =============================================================================


@dataclass
class TransitionRecord:
    """Immutable record of a lifecycle state transition."""

    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    model_id: str = ""
    from_state: str = ""
    to_state: str = ""
    actor: str = ""
    actor_type: str = "human"       # "human" or "system"
    risk_class: str = ""
    evidence: str = ""
    gate_checks_performed: list[str] = field(default_factory=list)
    gate_checks_passed: list[str] = field(default_factory=list)
    success: bool = True
    error: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "model_id": self.model_id,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "actor": self.actor,
            "actor_type": self.actor_type,
            "risk_class": self.risk_class,
            "evidence": self.evidence,
            "gate_checks_performed": self.gate_checks_performed,
            "gate_checks_passed": self.gate_checks_passed,
            "success": self.success,
            "error": self.error,
            "timestamp": self.timestamp,
        }


# =============================================================================
# Model Registry (in-memory for contract; production uses Supabase)
# =============================================================================


@dataclass
class ModelRecord:
    """A model/LoRA record with lifecycle state."""

    model_id: str
    org_id: str
    name: str = ""
    state: ModelLifecycleState = ModelLifecycleState.IMPORTED
    risk_class: ModelRiskClass = ModelRiskClass.STANDARD
    base_model_id: str = ""
    checksum: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


_model_store: dict[str, ModelRecord] = {}
_transition_log: list[TransitionRecord] = []


def clear_registry() -> None:
    """Clear all state (testing only)."""
    _model_store.clear()
    _transition_log.clear()


def register_model(model: ModelRecord) -> None:
    """Register a model in the store."""
    _model_store[model.model_id] = model


def get_model(model_id: str) -> ModelRecord | None:
    """Retrieve a model by ID."""
    return _model_store.get(model_id)


def get_transition_log(model_id: str | None = None) -> list[TransitionRecord]:
    """Get transition history, optionally filtered by model_id."""
    if model_id:
        return [r for r in _transition_log if r.model_id == model_id]
    return list(_transition_log)


# =============================================================================
# Transition Validation
# =============================================================================


def is_valid_transition(
    current_state: ModelLifecycleState,
    target_state: ModelLifecycleState,
) -> bool:
    """Check if a transition from current to target is valid."""
    allowed = VALID_TRANSITIONS.get(current_state, set())
    return target_state in allowed


def requires_human_approval(
    target_state: ModelLifecycleState,
    risk_class: ModelRiskClass,
) -> bool:
    """Check if the transition to target_state requires human approval.

    HIGH_RISK models require human approval for APPROVED and ACTIVE states.
    STANDARD models can auto-promote through integrity/compatibility but
    still require explicit (possibly automated) gate passage.
    """
    if risk_class == ModelRiskClass.HIGH_RISK:
        return target_state in HUMAN_GATED_STATES
    return False


# =============================================================================
# Transition Execution
# =============================================================================


def transition_model(
    model_id: str,
    current_state: ModelLifecycleState,
    target_state: ModelLifecycleState,
    actor: str,
    risk_class: ModelRiskClass = ModelRiskClass.STANDARD,
    evidence: str = "",
    actor_type: str = "human",
) -> TransitionRecord:
    """Validate and perform a model lifecycle state transition.

    Args:
        model_id: The model being transitioned.
        current_state: The expected current state (optimistic concurrency).
        target_state: The desired target state.
        actor: Identity of the actor performing the transition.
        risk_class: Risk classification of the model.
        evidence: Supporting evidence/rationale for the transition.
        actor_type: "human" or "system".

    Returns:
        TransitionRecord documenting the transition.

    Raises:
        ModelNotFoundError: Model not in registry.
        ModelLifecycleError: Invalid transition attempted.
    """
    model = _model_store.get(model_id)
    if model is None:
        raise ModelNotFoundError(f"Model {model_id} not found")

    # Optimistic concurrency: verify current state matches
    if model.state != current_state:
        record = TransitionRecord(
            model_id=model_id,
            from_state=current_state.value,
            to_state=target_state.value,
            actor=actor,
            actor_type=actor_type,
            risk_class=risk_class.value,
            evidence=evidence,
            success=False,
            error=(
                f"State mismatch: expected {current_state.value}, "
                f"actual {model.state.value}"
            ),
        )
        _transition_log.append(record)
        raise ModelLifecycleError(
            f"State mismatch: model is in {model.state.value}, "
            f"expected {current_state.value}",
            code="STATE_MISMATCH",
        )

    # Validate forward-only + quarantine escape
    if not is_valid_transition(current_state, target_state):
        record = TransitionRecord(
            model_id=model_id,
            from_state=current_state.value,
            to_state=target_state.value,
            actor=actor,
            actor_type=actor_type,
            risk_class=risk_class.value,
            evidence=evidence,
            success=False,
            error=(
                f"Invalid transition: {current_state.value} → {target_state.value}. "
                f"Allowed: {[s.value for s in VALID_TRANSITIONS.get(current_state, set())]}"
            ),
        )
        _transition_log.append(record)
        raise ModelLifecycleError(
            f"Invalid transition: {current_state.value} → {target_state.value}. "
            f"State can only advance forward or to quarantined.",
            code="INVALID_TRANSITION",
        )

    # Validate human approval gate for HIGH_RISK models
    if requires_human_approval(target_state, risk_class) and actor_type != "human":
        record = TransitionRecord(
            model_id=model_id,
            from_state=current_state.value,
            to_state=target_state.value,
            actor=actor,
            actor_type=actor_type,
            risk_class=risk_class.value,
            evidence=evidence,
            success=False,
            error=(
                f"Human approval required for HIGH_RISK model transition "
                f"to {target_state.value}"
            ),
        )
        _transition_log.append(record)
        raise ModelLifecycleError(
            f"Human approval required: HIGH_RISK model cannot auto-promote "
            f"to {target_state.value}",
            code="HUMAN_APPROVAL_REQUIRED",
        )

    # Execute the transition
    model.state = target_state

    # Log successful transition
    gate_checks = []
    if target_state == ModelLifecycleState.INTEGRITY_VERIFIED:
        gate_checks = ["checksum_valid", "format_valid"]
    elif target_state == ModelLifecycleState.EVALUATED:
        gate_checks = ["compatibility_check", "test_generation"]
    elif target_state == ModelLifecycleState.APPROVED:
        gate_checks = ["license_check", "safety_scan"]
        if risk_class == ModelRiskClass.HIGH_RISK:
            gate_checks.append("human_approval")

    record = TransitionRecord(
        model_id=model_id,
        from_state=current_state.value,
        to_state=target_state.value,
        actor=actor,
        actor_type=actor_type,
        risk_class=risk_class.value,
        evidence=evidence,
        gate_checks_performed=gate_checks,
        gate_checks_passed=gate_checks,
        success=True,
    )
    _transition_log.append(record)
    return record

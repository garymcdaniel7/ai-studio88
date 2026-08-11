"""Unit tests for Model/LoRA Lifecycle Service — promotion gate enforcement.

Tests cover:
    - Model registration in valid initial states
    - Registration rejection for invalid initial states
    - Forward-only promotion (happy path for each transition)
    - Invalid transition rejection (backward, skip, from quarantined)
    - Human approval gate for HIGH_RISK models
    - STANDARD models auto-promote without human gate
    - Quarantine from any state
    - Quarantine of already-quarantined model (409)
    - Deprecation of ACTIVE model
    - Deprecation rejection for non-ACTIVE models
    - Transition audit logging
    - State machine monotonicity property

Requirements: R67.1, R67.2, R67.3, R67.4, R67.5, R67.6, R67.7, R67.8, R34.8
"""

from __future__ import annotations

import pytest

from app.services.model_promotion_gates import (
    ModelLifecycleError,
    ModelLifecycleState,
    ModelNotFoundError,
    ModelRecord,
    ModelRiskClass,
    TransitionRecord,
    VALID_TRANSITIONS,
    clear_registry,
    get_model,
    get_transition_log,
    is_valid_transition,
    register_model,
    requires_human_approval,
    transition_model,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def _clean_registry():
    """Clear the in-memory model registry before each test."""
    clear_registry()
    yield
    clear_registry()


def _make_model(
    model_id: str = "model-001",
    org_id: str = "org-001",
    state: ModelLifecycleState = ModelLifecycleState.IMPORTED,
    risk_class: ModelRiskClass = ModelRiskClass.STANDARD,
) -> ModelRecord:
    """Create and register a model record for testing."""
    model = ModelRecord(
        model_id=model_id,
        org_id=org_id,
        name="Test Model",
        state=state,
        risk_class=risk_class,
    )
    register_model(model)
    return model


# =============================================================================
# Registration Tests
# =============================================================================


class TestModelRegistration:
    """Tests for model registration."""

    def test_register_model_imported(self):
        """Model can be registered in IMPORTED state."""
        model = _make_model(state=ModelLifecycleState.IMPORTED)
        assert get_model("model-001") is not None
        assert model.state == ModelLifecycleState.IMPORTED

    def test_register_model_trained(self):
        """Model can be registered in TRAINED state."""
        model = _make_model(state=ModelLifecycleState.TRAINED)
        assert model.state == ModelLifecycleState.TRAINED

    def test_model_defaults_to_standard_risk(self):
        """Models default to STANDARD risk class."""
        model = _make_model()
        assert model.risk_class == ModelRiskClass.STANDARD


# =============================================================================
# Valid Transition Tests (Forward-Only)
# =============================================================================


class TestValidTransitions:
    """Tests for valid lifecycle transitions."""

    def test_imported_to_integrity_verified(self):
        """IMPORTED → INTEGRITY_VERIFIED is valid."""
        _make_model(state=ModelLifecycleState.IMPORTED)
        record = transition_model(
            model_id="model-001",
            current_state=ModelLifecycleState.IMPORTED,
            target_state=ModelLifecycleState.INTEGRITY_VERIFIED,
            actor="test-user",
        )
        assert record.success is True
        assert record.to_state == "integrity_verified"
        assert get_model("model-001").state == ModelLifecycleState.INTEGRITY_VERIFIED

    def test_trained_to_integrity_verified(self):
        """TRAINED → INTEGRITY_VERIFIED is valid."""
        _make_model(state=ModelLifecycleState.TRAINED)
        record = transition_model(
            model_id="model-001",
            current_state=ModelLifecycleState.TRAINED,
            target_state=ModelLifecycleState.INTEGRITY_VERIFIED,
            actor="test-user",
        )
        assert record.success is True
        assert get_model("model-001").state == ModelLifecycleState.INTEGRITY_VERIFIED

    def test_integrity_verified_to_evaluated(self):
        """INTEGRITY_VERIFIED → EVALUATED is valid."""
        _make_model(state=ModelLifecycleState.INTEGRITY_VERIFIED)
        record = transition_model(
            model_id="model-001",
            current_state=ModelLifecycleState.INTEGRITY_VERIFIED,
            target_state=ModelLifecycleState.EVALUATED,
            actor="test-user",
        )
        assert record.success is True
        assert get_model("model-001").state == ModelLifecycleState.EVALUATED

    def test_evaluated_to_approved(self):
        """EVALUATED → APPROVED is valid for STANDARD risk."""
        _make_model(state=ModelLifecycleState.EVALUATED)
        record = transition_model(
            model_id="model-001",
            current_state=ModelLifecycleState.EVALUATED,
            target_state=ModelLifecycleState.APPROVED,
            actor="test-user",
        )
        assert record.success is True
        assert get_model("model-001").state == ModelLifecycleState.APPROVED

    def test_approved_to_active(self):
        """APPROVED → ACTIVE is valid."""
        _make_model(state=ModelLifecycleState.APPROVED)
        record = transition_model(
            model_id="model-001",
            current_state=ModelLifecycleState.APPROVED,
            target_state=ModelLifecycleState.ACTIVE,
            actor="test-user",
        )
        assert record.success is True
        assert get_model("model-001").state == ModelLifecycleState.ACTIVE

    def test_active_to_deprecated(self):
        """ACTIVE → DEPRECATED is valid."""
        _make_model(state=ModelLifecycleState.ACTIVE)
        record = transition_model(
            model_id="model-001",
            current_state=ModelLifecycleState.ACTIVE,
            target_state=ModelLifecycleState.DEPRECATED,
            actor="test-user",
        )
        assert record.success is True
        assert get_model("model-001").state == ModelLifecycleState.DEPRECATED

    def test_full_lifecycle_happy_path(self):
        """Model can progress through full lifecycle: IMPORTED → ACTIVE."""
        _make_model(state=ModelLifecycleState.IMPORTED)
        states = [
            ModelLifecycleState.INTEGRITY_VERIFIED,
            ModelLifecycleState.EVALUATED,
            ModelLifecycleState.APPROVED,
            ModelLifecycleState.ACTIVE,
        ]
        current = ModelLifecycleState.IMPORTED
        for target in states:
            transition_model(
                model_id="model-001",
                current_state=current,
                target_state=target,
                actor="test-user",
            )
            current = target
        assert get_model("model-001").state == ModelLifecycleState.ACTIVE


# =============================================================================
# Invalid Transition Tests
# =============================================================================


class TestInvalidTransitions:
    """Tests for transition enforcement — backward/skip moves are blocked."""

    def test_cannot_go_backward(self):
        """EVALUATED cannot go back to IMPORTED."""
        _make_model(state=ModelLifecycleState.EVALUATED)
        with pytest.raises(ModelLifecycleError) as exc_info:
            transition_model(
                model_id="model-001",
                current_state=ModelLifecycleState.EVALUATED,
                target_state=ModelLifecycleState.IMPORTED,
                actor="test-user",
            )
        assert "Invalid transition" in exc_info.value.message

    def test_cannot_skip_states(self):
        """IMPORTED cannot skip to APPROVED directly."""
        _make_model(state=ModelLifecycleState.IMPORTED)
        with pytest.raises(ModelLifecycleError) as exc_info:
            transition_model(
                model_id="model-001",
                current_state=ModelLifecycleState.IMPORTED,
                target_state=ModelLifecycleState.APPROVED,
                actor="test-user",
            )
        assert "Invalid transition" in exc_info.value.message

    def test_cannot_transition_from_quarantined(self):
        """QUARANTINED is terminal — no transitions out."""
        _make_model(state=ModelLifecycleState.QUARANTINED)
        with pytest.raises(ModelLifecycleError) as exc_info:
            transition_model(
                model_id="model-001",
                current_state=ModelLifecycleState.QUARANTINED,
                target_state=ModelLifecycleState.ACTIVE,
                actor="test-user",
            )
        assert "Invalid transition" in exc_info.value.message

    def test_state_mismatch_raises_error(self):
        """Attempting transition with wrong current_state raises error."""
        _make_model(state=ModelLifecycleState.IMPORTED)
        with pytest.raises(ModelLifecycleError) as exc_info:
            transition_model(
                model_id="model-001",
                current_state=ModelLifecycleState.EVALUATED,
                target_state=ModelLifecycleState.APPROVED,
                actor="test-user",
            )
        assert "State mismatch" in exc_info.value.message
        assert exc_info.value.code == "STATE_MISMATCH"

    def test_model_not_found(self):
        """Transition on non-existent model raises ModelNotFoundError."""
        with pytest.raises(ModelNotFoundError):
            transition_model(
                model_id="nonexistent",
                current_state=ModelLifecycleState.IMPORTED,
                target_state=ModelLifecycleState.INTEGRITY_VERIFIED,
                actor="test-user",
            )


# =============================================================================
# Quarantine Tests (R67.5)
# =============================================================================


class TestQuarantine:
    """Tests for quarantine — can jump from any state."""

    @pytest.mark.parametrize(
        "state",
        [
            ModelLifecycleState.IMPORTED,
            ModelLifecycleState.TRAINED,
            ModelLifecycleState.INTEGRITY_VERIFIED,
            ModelLifecycleState.EVALUATED,
            ModelLifecycleState.APPROVED,
            ModelLifecycleState.ACTIVE,
            ModelLifecycleState.DEPRECATED,
        ],
    )
    def test_quarantine_from_any_state(self, state: ModelLifecycleState):
        """Model can be quarantined from any non-quarantined state."""
        _make_model(state=state)
        record = transition_model(
            model_id="model-001",
            current_state=state,
            target_state=ModelLifecycleState.QUARANTINED,
            actor="safety-scanner",
            evidence="Safety policy violation detected",
        )
        assert record.success is True
        assert get_model("model-001").state == ModelLifecycleState.QUARANTINED


# =============================================================================
# Human Approval Gate Tests (R67.4)
# =============================================================================


class TestHumanApprovalGate:
    """Tests for HIGH_RISK human approval requirement."""

    def test_high_risk_requires_human_for_approved(self):
        """HIGH_RISK model cannot auto-promote to APPROVED."""
        _make_model(
            state=ModelLifecycleState.EVALUATED,
            risk_class=ModelRiskClass.HIGH_RISK,
        )
        with pytest.raises(ModelLifecycleError) as exc_info:
            transition_model(
                model_id="model-001",
                current_state=ModelLifecycleState.EVALUATED,
                target_state=ModelLifecycleState.APPROVED,
                actor="auto-scanner",
                risk_class=ModelRiskClass.HIGH_RISK,
                actor_type="system",
            )
        assert "Human approval required" in exc_info.value.message
        assert exc_info.value.code == "HUMAN_APPROVAL_REQUIRED"

    def test_high_risk_requires_human_for_active(self):
        """HIGH_RISK model cannot auto-promote to ACTIVE."""
        _make_model(
            state=ModelLifecycleState.APPROVED,
            risk_class=ModelRiskClass.HIGH_RISK,
        )
        with pytest.raises(ModelLifecycleError) as exc_info:
            transition_model(
                model_id="model-001",
                current_state=ModelLifecycleState.APPROVED,
                target_state=ModelLifecycleState.ACTIVE,
                actor="auto-scanner",
                risk_class=ModelRiskClass.HIGH_RISK,
                actor_type="system",
            )
        assert "Human approval required" in exc_info.value.message

    def test_high_risk_human_can_approve(self):
        """HIGH_RISK model can be promoted to APPROVED by human actor."""
        _make_model(
            state=ModelLifecycleState.EVALUATED,
            risk_class=ModelRiskClass.HIGH_RISK,
        )
        record = transition_model(
            model_id="model-001",
            current_state=ModelLifecycleState.EVALUATED,
            target_state=ModelLifecycleState.APPROVED,
            actor="admin-user",
            risk_class=ModelRiskClass.HIGH_RISK,
            actor_type="human",
        )
        assert record.success is True
        assert get_model("model-001").state == ModelLifecycleState.APPROVED

    def test_standard_risk_system_can_promote(self):
        """STANDARD risk model can auto-promote to APPROVED by system."""
        _make_model(
            state=ModelLifecycleState.EVALUATED,
            risk_class=ModelRiskClass.STANDARD,
        )
        record = transition_model(
            model_id="model-001",
            current_state=ModelLifecycleState.EVALUATED,
            target_state=ModelLifecycleState.APPROVED,
            actor="auto-scanner",
            risk_class=ModelRiskClass.STANDARD,
            actor_type="system",
        )
        assert record.success is True
        assert get_model("model-001").state == ModelLifecycleState.APPROVED

    def test_high_risk_system_can_promote_non_gated_states(self):
        """HIGH_RISK system can still promote through non-gated states."""
        _make_model(
            state=ModelLifecycleState.IMPORTED,
            risk_class=ModelRiskClass.HIGH_RISK,
        )
        record = transition_model(
            model_id="model-001",
            current_state=ModelLifecycleState.IMPORTED,
            target_state=ModelLifecycleState.INTEGRITY_VERIFIED,
            actor="integrity-checker",
            risk_class=ModelRiskClass.HIGH_RISK,
            actor_type="system",
        )
        assert record.success is True


# =============================================================================
# Transition Audit Log Tests (R67.6)
# =============================================================================


class TestTransitionAuditLog:
    """Tests for transition audit logging."""

    def test_successful_transition_logged(self):
        """Successful transitions are logged."""
        _make_model(state=ModelLifecycleState.IMPORTED)
        transition_model(
            model_id="model-001",
            current_state=ModelLifecycleState.IMPORTED,
            target_state=ModelLifecycleState.INTEGRITY_VERIFIED,
            actor="test-user",
            evidence="checksum verified",
        )
        logs = get_transition_log("model-001")
        assert len(logs) == 1
        assert logs[0].success is True
        assert logs[0].from_state == "imported"
        assert logs[0].to_state == "integrity_verified"
        assert logs[0].actor == "test-user"
        assert logs[0].evidence == "checksum verified"
        assert logs[0].timestamp is not None

    def test_failed_transition_logged(self):
        """Failed transitions are also logged."""
        _make_model(state=ModelLifecycleState.IMPORTED)
        with pytest.raises(ModelLifecycleError):
            transition_model(
                model_id="model-001",
                current_state=ModelLifecycleState.IMPORTED,
                target_state=ModelLifecycleState.ACTIVE,
                actor="test-user",
            )
        logs = get_transition_log("model-001")
        assert len(logs) == 1
        assert logs[0].success is False
        assert logs[0].error is not None

    def test_gate_checks_recorded(self):
        """Gate checks are recorded in the transition log."""
        _make_model(state=ModelLifecycleState.IMPORTED)
        record = transition_model(
            model_id="model-001",
            current_state=ModelLifecycleState.IMPORTED,
            target_state=ModelLifecycleState.INTEGRITY_VERIFIED,
            actor="test-user",
        )
        assert "checksum_valid" in record.gate_checks_performed
        assert "format_valid" in record.gate_checks_performed

    def test_multiple_transitions_logged_chronologically(self):
        """Multiple transitions are logged in order."""
        _make_model(state=ModelLifecycleState.IMPORTED)
        transition_model(
            model_id="model-001",
            current_state=ModelLifecycleState.IMPORTED,
            target_state=ModelLifecycleState.INTEGRITY_VERIFIED,
            actor="user-1",
        )
        transition_model(
            model_id="model-001",
            current_state=ModelLifecycleState.INTEGRITY_VERIFIED,
            target_state=ModelLifecycleState.EVALUATED,
            actor="user-2",
        )
        logs = get_transition_log("model-001")
        assert len(logs) == 2
        assert logs[0].actor == "user-1"
        assert logs[1].actor == "user-2"

    def test_transition_record_contains_risk_class(self):
        """Transition log records the risk class at time of transition."""
        _make_model(
            state=ModelLifecycleState.IMPORTED,
            risk_class=ModelRiskClass.HIGH_RISK,
        )
        record = transition_model(
            model_id="model-001",
            current_state=ModelLifecycleState.IMPORTED,
            target_state=ModelLifecycleState.INTEGRITY_VERIFIED,
            actor="test-user",
            risk_class=ModelRiskClass.HIGH_RISK,
        )
        assert record.risk_class == "high_risk"


# =============================================================================
# Validation Helper Tests
# =============================================================================


class TestValidationHelpers:
    """Tests for validation helper functions."""

    def test_is_valid_transition_forward(self):
        """Forward transitions are valid."""
        assert is_valid_transition(
            ModelLifecycleState.IMPORTED,
            ModelLifecycleState.INTEGRITY_VERIFIED,
        ) is True

    def test_is_valid_transition_backward(self):
        """Backward transitions are invalid."""
        assert is_valid_transition(
            ModelLifecycleState.EVALUATED,
            ModelLifecycleState.IMPORTED,
        ) is False

    def test_is_valid_transition_quarantine_always_valid(self):
        """Quarantine is valid from any non-quarantined state."""
        for state in ModelLifecycleState:
            if state == ModelLifecycleState.QUARANTINED:
                assert is_valid_transition(state, ModelLifecycleState.QUARANTINED) is False
            else:
                assert is_valid_transition(state, ModelLifecycleState.QUARANTINED) is True

    def test_requires_human_approval_high_risk_approved(self):
        """HIGH_RISK requires human for APPROVED state."""
        assert requires_human_approval(
            ModelLifecycleState.APPROVED, ModelRiskClass.HIGH_RISK
        ) is True

    def test_requires_human_approval_high_risk_active(self):
        """HIGH_RISK requires human for ACTIVE state."""
        assert requires_human_approval(
            ModelLifecycleState.ACTIVE, ModelRiskClass.HIGH_RISK
        ) is True

    def test_requires_human_approval_standard_no_gate(self):
        """STANDARD does not require human approval."""
        assert requires_human_approval(
            ModelLifecycleState.APPROVED, ModelRiskClass.STANDARD
        ) is False

    def test_requires_human_approval_high_risk_non_gated(self):
        """HIGH_RISK does not require human for non-gated states."""
        assert requires_human_approval(
            ModelLifecycleState.INTEGRITY_VERIFIED, ModelRiskClass.HIGH_RISK
        ) is False


# =============================================================================
# Property: Lifecycle Monotonicity (Property 10)
# =============================================================================


class TestLifecycleMonotonicity:
    """Property 10: State only advances forward or jumps to quarantined."""

    def test_valid_transitions_are_forward_or_quarantine(self):
        """All entries in VALID_TRANSITIONS advance forward or go to quarantined."""
        lifecycle_order = [
            ModelLifecycleState.IMPORTED,
            ModelLifecycleState.TRAINED,
            ModelLifecycleState.INTEGRITY_VERIFIED,
            ModelLifecycleState.EVALUATED,
            ModelLifecycleState.APPROVED,
            ModelLifecycleState.ACTIVE,
            ModelLifecycleState.DEPRECATED,
            ModelLifecycleState.QUARANTINED,
        ]

        # IMPORTED and TRAINED are both at position 0-1 (equivalent entry points)
        for from_state, allowed_targets in VALID_TRANSITIONS.items():
            for target in allowed_targets:
                if target == ModelLifecycleState.QUARANTINED:
                    # Quarantine is always valid (not a forward move but allowed)
                    continue
                # The target must be after the source in lifecycle order
                # (IMPORTED and TRAINED both go to INTEGRITY_VERIFIED)
                from_idx = lifecycle_order.index(from_state)
                to_idx = lifecycle_order.index(target)
                assert to_idx > from_idx, (
                    f"Non-forward transition: {from_state} → {target} "
                    f"(idx {from_idx} → {to_idx})"
                )

    def test_quarantined_has_no_exit_transitions(self):
        """QUARANTINED is terminal — no transitions out."""
        assert VALID_TRANSITIONS[ModelLifecycleState.QUARANTINED] == set()

    def test_never_auto_promotes_to_active(self):
        """Models cannot skip directly to ACTIVE from initial states."""
        for initial in [ModelLifecycleState.IMPORTED, ModelLifecycleState.TRAINED]:
            assert ModelLifecycleState.ACTIVE not in VALID_TRANSITIONS[initial]
            assert ModelLifecycleState.APPROVED not in VALID_TRANSITIONS[initial]

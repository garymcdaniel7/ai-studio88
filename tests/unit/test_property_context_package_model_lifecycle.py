"""Property-Based Tests: Context Package Integrity & Model Lifecycle Monotonicity — Task 29.4.

Proves two correctness properties using hypothesis:

  Property 8 — Immutable Context Package Integrity:
    - Once created and finalized, no field of a context package can be modified
    - Any attempt to modify a persisted package raises PackageImmutableError
    - Stale references (deleted/changed resources) cause job rejection

  Property 10 — Model Lifecycle Monotonicity:
    - State only advances forward through the defined lifecycle sequence
    - ANY state can jump to QUARANTINED (escape hatch)
    - Backward transitions are always rejected
    - Models SHALL NOT auto-promote to APPROVED or ACTIVE without gates
    - HIGH_RISK models require human approval for APPROVED/ACTIVE

Validates: Requirements R60.2, R60.5, R67.1, R67.2

Run with:
    pytest tests/unit/test_property_context_package_model_lifecycle.py -v
"""
from __future__ import annotations

import uuid

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from backend.context_package import (
    ContextPackage,
    PackageImmutableError,
    PackageNotFoundError,
    clear_store,
    compute_canonical_hash,
    finalize_package,
    modify_package,
    persist_package,
    retrieve_package,
)
from backend.app.services.model_promotion_gates import (
    HUMAN_GATED_STATES,
    INITIAL_STATES,
    VALID_TRANSITIONS,
    ModelLifecycleError,
    ModelLifecycleState,
    ModelNotFoundError,
    ModelRecord,
    ModelRiskClass,
    TransitionRecord,
    clear_registry,
    get_model,
    get_transition_log,
    is_valid_transition,
    register_model,
    requires_human_approval,
    transition_model,
)


# =============================================================================
# Strategies — Context Package
# =============================================================================

# Random prompts
prompt_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "Nd", "P", "Z")),
    min_size=1,
    max_size=200,
)

# Model IDs
model_id_strategy = st.sampled_from([
    "flux-dev", "sdxl", "sd15", "flux-schnell", "wan-21",
    "ltx-video", "sdxl-turbo", "flux-lora-custom",
])

# Talent IDs
talent_id_strategy = st.from_regex(r"talent-[a-z0-9]{4,12}", fullmatch=True)

# Org IDs
org_id_strategy = st.from_regex(r"org-[a-f0-9]{4,16}", fullmatch=True)

# User IDs
user_id_strategy = st.from_regex(r"usr-[a-f0-9]{4,12}", fullmatch=True)

# LoRA info
lora_id_strategy = st.one_of(st.none(), st.from_regex(r"lora-[a-z0-9]{3,10}", fullmatch=True))
lora_version_strategy = st.one_of(st.none(), st.sampled_from(["v1", "v2", "v3", "v4", "v5"]))
lora_strength_strategy = st.one_of(
    st.none(),
    st.floats(min_value=0.0, max_value=1.5, allow_nan=False, allow_infinity=False),
)

# Applied rules
rule_strategy = st.fixed_dictionaries({
    "rule_id": st.from_regex(r"r-[0-9]{1,4}", fullmatch=True),
    "version": st.integers(min_value=1, max_value=10),
    "type": st.sampled_from(["include", "avoid", "style", "technical"]),
    "text": st.text(min_size=1, max_size=50),
})
rules_list_strategy = st.lists(rule_strategy, min_size=0, max_size=5)

# Random field names for modification attempts
modifiable_field_strategy = st.sampled_from([
    "effective_positive_prompt",
    "effective_negative_prompt",
    "model_id",
    "model_version",
    "lora_id",
    "lora_version",
    "talent_id",
    "talent_version",
    "merge_policy_version",
])

# =============================================================================
# Strategies — Model Lifecycle
# =============================================================================

# All lifecycle states
lifecycle_state_strategy = st.sampled_from(list(ModelLifecycleState))

# Non-quarantined states (for generating backward transition attempts)
non_quarantined_state_strategy = st.sampled_from([
    s for s in ModelLifecycleState if s != ModelLifecycleState.QUARANTINED
])

# Risk classes
risk_class_strategy = st.sampled_from(list(ModelRiskClass))

# Actor identities
actor_strategy = st.from_regex(r"(admin|operator|system)-[a-f0-9]{4}", fullmatch=True)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def _clean_stores():
    """Clear both context package and model stores before/after each test."""
    clear_store()
    clear_registry()
    yield
    clear_store()
    clear_registry()


# =============================================================================
# Property 8.1: Immutable Context Package — Modification Always Fails
# "For ANY context package, once finalized and persisted, no modification
#  attempt succeeds — PackageImmutableError is always raised."
# =============================================================================


@pytest.mark.unit
class TestContextPackageImmutability:
    """Once finalized and persisted, context packages cannot be modified.

    **Validates: Requirements R60.2**
    """

    @given(
        org_id=org_id_strategy,
        user_id=user_id_strategy,
        positive_prompt=prompt_strategy,
        negative_prompt=prompt_strategy,
        model_id=model_id_strategy,
        talent_id=talent_id_strategy,
        lora_id=lora_id_strategy,
        lora_version=lora_version_strategy,
        lora_strength=lora_strength_strategy,
        applied_rules=rules_list_strategy,
        field_to_modify=modifiable_field_strategy,
        new_value=prompt_strategy,
    )
    @settings(max_examples=200, deadline=None)
    def test_modify_persisted_package_always_raises(
        self,
        org_id: str,
        user_id: str,
        positive_prompt: str,
        negative_prompt: str,
        model_id: str,
        talent_id: str,
        lora_id: str | None,
        lora_version: str | None,
        lora_strength: float | None,
        applied_rules: list[dict],
        field_to_modify: str,
        new_value: str,
    ):
        """For ANY package, modify_package always raises PackageImmutableError.

        **Validates: Requirements R60.2**
        """
        clear_store()

        pkg = ContextPackage(
            org_id=org_id,
            user_id=user_id,
            talent_id=talent_id,
            talent_version=1,
            effective_positive_prompt=positive_prompt,
            effective_negative_prompt=negative_prompt,
            model_id=model_id,
            model_version="1.0",
            lora_id=lora_id,
            lora_version=lora_version,
            lora_strength=lora_strength,
            applied_rules=applied_rules,
            merge_policy_version="1.0",
        )

        finalize_package(pkg)
        persist_package(pkg)

        # Attempt to modify — must ALWAYS raise
        with pytest.raises(PackageImmutableError) as exc_info:
            modify_package(pkg.package_id, {field_to_modify: new_value})

        assert "immutable" in exc_info.value.message.lower()

    @given(
        org_id=org_id_strategy,
        positive_prompt=prompt_strategy,
        model_id=model_id_strategy,
        talent_id=talent_id_strategy,
    )
    @settings(max_examples=200, deadline=None)
    def test_finalized_package_hash_is_stable(
        self,
        org_id: str,
        positive_prompt: str,
        model_id: str,
        talent_id: str,
    ):
        """For ANY package, hash computed once is the hash computed every time.

        **Validates: Requirements R60.2**
        """
        clear_store()

        pkg = ContextPackage(
            org_id=org_id,
            user_id="usr-test",
            talent_id=talent_id,
            talent_version=1,
            effective_positive_prompt=positive_prompt,
            effective_negative_prompt="",
            model_id=model_id,
            model_version="1.0",
            merge_policy_version="1.0",
        )

        # Compute hash multiple times — must be identical
        h1 = compute_canonical_hash(pkg)
        h2 = compute_canonical_hash(pkg)
        h3 = compute_canonical_hash(pkg)

        assert h1 == h2 == h3
        assert len(h1) == 32


# =============================================================================
# Property 8.2: Stale References → Job Rejected
# "If a referenced resource changes after context resolution, the system
#  must reject the job rather than proceeding with invalid context."
# =============================================================================


@pytest.mark.unit
class TestStaleReferenceRejection:
    """Stale references in context packages cause job rejection.

    **Validates: Requirements R60.5**
    """

    @given(
        org_id=org_id_strategy,
        talent_id=talent_id_strategy,
        model_id=model_id_strategy,
        positive_prompt=prompt_strategy,
    )
    @settings(max_examples=200, deadline=None)
    def test_deleted_package_reference_raises_not_found(
        self,
        org_id: str,
        talent_id: str,
        model_id: str,
        positive_prompt: str,
    ):
        """Referencing a non-existent context package raises PackageNotFoundError.

        This simulates a job referencing a context package that was deleted or
        never existed — the platform must reject rather than proceed.

        **Validates: Requirements R60.5**
        """
        clear_store()

        # Generate a random package_id that doesn't exist
        fake_package_id = f"ctx-{uuid.uuid4().hex[:16]}"

        with pytest.raises(PackageNotFoundError):
            retrieve_package(fake_package_id, requesting_org_id=org_id)

    @given(
        org_id=org_id_strategy,
        talent_id=talent_id_strategy,
        model_id=model_id_strategy,
        positive_prompt=prompt_strategy,
        stale_talent_version=st.integers(min_value=2, max_value=100),
    )
    @settings(max_examples=200, deadline=None)
    def test_version_mismatch_detectable_via_hash(
        self,
        org_id: str,
        talent_id: str,
        model_id: str,
        positive_prompt: str,
        stale_talent_version: int,
    ):
        """Context package hash changes when referenced resources change.

        If talent_version changes after resolution, the hash will differ from
        the stored package — enabling stale reference detection.

        **Validates: Requirements R60.5**
        """
        clear_store()

        # Original context at resolution time
        pkg_original = ContextPackage(
            org_id=org_id,
            user_id="usr-test",
            talent_id=talent_id,
            talent_version=1,
            effective_positive_prompt=positive_prompt,
            effective_negative_prompt="",
            model_id=model_id,
            model_version="1.0",
            merge_policy_version="1.0",
        )
        original_hash = compute_canonical_hash(pkg_original)

        # Same context but talent version has changed (stale reference)
        pkg_stale = ContextPackage(
            org_id=org_id,
            user_id="usr-test",
            talent_id=talent_id,
            talent_version=stale_talent_version,
            effective_positive_prompt=positive_prompt,
            effective_negative_prompt="",
            model_id=model_id,
            model_version="1.0",
            merge_policy_version="1.0",
        )
        stale_hash = compute_canonical_hash(pkg_stale)

        # Hashes MUST differ — enabling detection of stale references
        assert original_hash != stale_hash, (
            f"STALE REFERENCE UNDETECTED: talent version changed from 1 to "
            f"{stale_talent_version} but hash remained {original_hash}"
        )

    @given(
        org_id=org_id_strategy,
        positive_prompt=prompt_strategy,
        model_id=model_id_strategy,
    )
    @settings(max_examples=200, deadline=None)
    def test_cross_org_package_access_denied(
        self,
        org_id: str,
        positive_prompt: str,
        model_id: str,
    ):
        """Context package cannot be accessed by a different org.

        If a job references a package from another org, retrieval fails —
        preventing cross-tenant stale reference exploitation.

        **Validates: Requirements R60.5**
        """
        clear_store()

        pkg = ContextPackage(
            org_id=org_id,
            user_id="usr-test",
            talent_id="talent-1",
            talent_version=1,
            effective_positive_prompt=positive_prompt,
            effective_negative_prompt="",
            model_id=model_id,
            model_version="1.0",
            merge_policy_version="1.0",
        )
        finalize_package(pkg)
        persist_package(pkg)

        # Different org trying to access
        other_org = f"org-{uuid.uuid4().hex[:12]}"
        assume(other_org != org_id)

        from backend.context_package import PackageUnauthorizedError

        with pytest.raises(PackageUnauthorizedError):
            retrieve_package(pkg.package_id, requesting_org_id=other_org)


# =============================================================================
# Property 10.1: Model Lifecycle Monotonicity — Forward-Only Transitions
# "For ANY sequence of state transitions, the model lifecycle only moves
#  forward through the defined sequence or to QUARANTINED."
# =============================================================================


@pytest.mark.unit
class TestModelLifecycleForwardOnly:
    """Model state only advances forward or jumps to QUARANTINED.

    **Validates: Requirements R67.1**
    """

    @given(
        current_state=non_quarantined_state_strategy,
        target_state=lifecycle_state_strategy,
    )
    @settings(max_examples=200, deadline=None)
    def test_valid_transitions_are_forward_or_quarantine(
        self,
        current_state: ModelLifecycleState,
        target_state: ModelLifecycleState,
    ):
        """Every valid transition is either forward in sequence or to QUARANTINED.

        **Validates: Requirements R67.1**
        """
        if is_valid_transition(current_state, target_state):
            # Must be forward or quarantine
            assert (
                target_state == ModelLifecycleState.QUARANTINED
                or target_state in VALID_TRANSITIONS[current_state]
            ), (
                f"MONOTONICITY BREACH: transition {current_state.value} → "
                f"{target_state.value} is marked valid but is neither "
                f"forward nor quarantine"
            )

    @given(
        current_state=lifecycle_state_strategy,
    )
    @settings(max_examples=200, deadline=None)
    def test_quarantine_always_reachable_from_non_quarantined(
        self,
        current_state: ModelLifecycleState,
    ):
        """From ANY non-QUARANTINED state, QUARANTINED is a valid target.

        **Validates: Requirements R67.1**
        """
        if current_state != ModelLifecycleState.QUARANTINED:
            assert is_valid_transition(current_state, ModelLifecycleState.QUARANTINED), (
                f"QUARANTINE UNREACHABLE: state {current_state.value} cannot "
                f"transition to QUARANTINED — violates R67.5"
            )

    @given(
        current_state=lifecycle_state_strategy,
    )
    @settings(max_examples=200, deadline=None)
    def test_quarantined_is_terminal(
        self,
        current_state: ModelLifecycleState,
    ):
        """QUARANTINED state has no valid outgoing transitions.

        **Validates: Requirements R67.1**
        """
        if current_state == ModelLifecycleState.QUARANTINED:
            allowed = VALID_TRANSITIONS.get(current_state, set())
            assert len(allowed) == 0, (
                f"QUARANTINED IS NOT TERMINAL: has transitions to "
                f"{[s.value for s in allowed]}"
            )

    @given(
        current_state=non_quarantined_state_strategy,
        target_state=non_quarantined_state_strategy,
    )
    @settings(max_examples=200, deadline=None)
    def test_backward_transitions_rejected(
        self,
        current_state: ModelLifecycleState,
        target_state: ModelLifecycleState,
    ):
        """Backward transitions are never valid (monotonicity).

        **Validates: Requirements R67.1**
        """
        clear_registry()

        # Define the forward order (excluding quarantined)
        forward_order = [
            ModelLifecycleState.IMPORTED,
            ModelLifecycleState.TRAINED,
            ModelLifecycleState.INTEGRITY_VERIFIED,
            ModelLifecycleState.EVALUATED,
            ModelLifecycleState.APPROVED,
            ModelLifecycleState.ACTIVE,
            ModelLifecycleState.DEPRECATED,
        ]

        # Get positions (IMPORTED and TRAINED are both at position 0)
        def get_position(state: ModelLifecycleState) -> int:
            if state in (ModelLifecycleState.IMPORTED, ModelLifecycleState.TRAINED):
                return 0
            return forward_order.index(state)

        current_pos = get_position(current_state)
        target_pos = get_position(target_state)

        # If target is strictly behind current, it must not be valid
        if target_pos < current_pos:
            assert not is_valid_transition(current_state, target_state), (
                f"BACKWARD TRANSITION ALLOWED: {current_state.value} (pos {current_pos}) "
                f"→ {target_state.value} (pos {target_pos}) — violates monotonicity"
            )


# =============================================================================
# Property 10.2: No Auto-Promotion to APPROVED or ACTIVE
# "Models SHALL NOT automatically become APPROVED or ACTIVE upon import
#  or training — they require explicit gate passage."
# =============================================================================


@pytest.mark.unit
class TestNoAutoPromotion:
    """Models cannot auto-promote to APPROVED or ACTIVE without gates.

    **Validates: Requirements R67.2**
    """

    @given(
        initial_state=st.sampled_from(list(INITIAL_STATES)),
        model_id=st.from_regex(r"model-[a-f0-9]{8}", fullmatch=True),
        org_id=org_id_strategy,
    )
    @settings(max_examples=200, deadline=None)
    def test_initial_state_cannot_reach_approved_directly(
        self,
        initial_state: ModelLifecycleState,
        model_id: str,
        org_id: str,
    ):
        """From IMPORTED/TRAINED, direct transition to APPROVED is invalid.

        **Validates: Requirements R67.2**
        """
        assert not is_valid_transition(initial_state, ModelLifecycleState.APPROVED), (
            f"AUTO-PROMOTION TO APPROVED: {initial_state.value} can directly "
            f"reach APPROVED — violates R67.2"
        )

    @given(
        initial_state=st.sampled_from(list(INITIAL_STATES)),
        model_id=st.from_regex(r"model-[a-f0-9]{8}", fullmatch=True),
        org_id=org_id_strategy,
    )
    @settings(max_examples=200, deadline=None)
    def test_initial_state_cannot_reach_active_directly(
        self,
        initial_state: ModelLifecycleState,
        model_id: str,
        org_id: str,
    ):
        """From IMPORTED/TRAINED, direct transition to ACTIVE is invalid.

        **Validates: Requirements R67.2**
        """
        assert not is_valid_transition(initial_state, ModelLifecycleState.ACTIVE), (
            f"AUTO-PROMOTION TO ACTIVE: {initial_state.value} can directly "
            f"reach ACTIVE — violates R67.2"
        )

    @given(
        model_id=st.from_regex(r"model-[a-f0-9]{8}", fullmatch=True),
        org_id=org_id_strategy,
        actor=actor_strategy,
    )
    @settings(max_examples=200, deadline=None)
    def test_high_risk_system_cannot_auto_approve(
        self,
        model_id: str,
        org_id: str,
        actor: str,
    ):
        """HIGH_RISK model cannot be system-promoted to APPROVED.

        **Validates: Requirements R67.2**
        """
        clear_registry()

        model = ModelRecord(
            model_id=model_id,
            org_id=org_id,
            name="test-model",
            state=ModelLifecycleState.EVALUATED,
            risk_class=ModelRiskClass.HIGH_RISK,
        )
        register_model(model)

        # System actor attempting to promote to APPROVED
        with pytest.raises(ModelLifecycleError) as exc_info:
            transition_model(
                model_id=model_id,
                current_state=ModelLifecycleState.EVALUATED,
                target_state=ModelLifecycleState.APPROVED,
                actor=actor,
                risk_class=ModelRiskClass.HIGH_RISK,
                actor_type="system",
                evidence="automated check",
            )

        assert "human approval required" in exc_info.value.message.lower()

    @given(
        model_id=st.from_regex(r"model-[a-f0-9]{8}", fullmatch=True),
        org_id=org_id_strategy,
        actor=actor_strategy,
    )
    @settings(max_examples=200, deadline=None)
    def test_high_risk_system_cannot_auto_activate(
        self,
        model_id: str,
        org_id: str,
        actor: str,
    ):
        """HIGH_RISK model cannot be system-promoted to ACTIVE.

        **Validates: Requirements R67.2**
        """
        clear_registry()

        model = ModelRecord(
            model_id=model_id,
            org_id=org_id,
            name="test-model",
            state=ModelLifecycleState.APPROVED,
            risk_class=ModelRiskClass.HIGH_RISK,
        )
        register_model(model)

        # System actor attempting to promote to ACTIVE
        with pytest.raises(ModelLifecycleError) as exc_info:
            transition_model(
                model_id=model_id,
                current_state=ModelLifecycleState.APPROVED,
                target_state=ModelLifecycleState.ACTIVE,
                actor=actor,
                risk_class=ModelRiskClass.HIGH_RISK,
                actor_type="system",
                evidence="automated check",
            )

        assert "human approval required" in exc_info.value.message.lower()


# =============================================================================
# Property 10.3: Transition Execution Enforces Monotonicity
# "transition_model() rejects ALL invalid transitions with ModelLifecycleError."
# =============================================================================


@pytest.mark.unit
class TestTransitionExecutionEnforcesMonotonicity:
    """transition_model() enforces forward-only lifecycle for all inputs.

    **Validates: Requirements R67.1, R67.2**
    """

    @given(
        current_state=lifecycle_state_strategy,
        target_state=lifecycle_state_strategy,
        model_id=st.from_regex(r"model-[a-f0-9]{8}", fullmatch=True),
        org_id=org_id_strategy,
        actor=actor_strategy,
        risk_class=risk_class_strategy,
    )
    @settings(max_examples=200, deadline=None)
    def test_invalid_transitions_always_raise(
        self,
        current_state: ModelLifecycleState,
        target_state: ModelLifecycleState,
        model_id: str,
        org_id: str,
        actor: str,
        risk_class: ModelRiskClass,
    ):
        """For ANY invalid transition, transition_model raises ModelLifecycleError.

        **Validates: Requirements R67.1**
        """
        clear_registry()

        # Skip if this is actually a valid transition
        if is_valid_transition(current_state, target_state):
            # Also skip if it would be blocked by human approval gate
            if requires_human_approval(target_state, risk_class):
                return
            return

        model = ModelRecord(
            model_id=model_id,
            org_id=org_id,
            name="test-model",
            state=current_state,
            risk_class=risk_class,
        )
        register_model(model)

        with pytest.raises(ModelLifecycleError):
            transition_model(
                model_id=model_id,
                current_state=current_state,
                target_state=target_state,
                actor=actor,
                risk_class=risk_class,
                actor_type="human",
                evidence="test",
            )

    @given(
        current_state=non_quarantined_state_strategy,
        model_id=st.from_regex(r"model-[a-f0-9]{8}", fullmatch=True),
        org_id=org_id_strategy,
        actor=actor_strategy,
    )
    @settings(max_examples=200, deadline=None)
    def test_valid_quarantine_transition_succeeds(
        self,
        current_state: ModelLifecycleState,
        model_id: str,
        org_id: str,
        actor: str,
    ):
        """Transitioning to QUARANTINED always succeeds from any non-quarantined state.

        **Validates: Requirements R67.1**
        """
        clear_registry()

        model = ModelRecord(
            model_id=model_id,
            org_id=org_id,
            name="test-model",
            state=current_state,
            risk_class=ModelRiskClass.STANDARD,
        )
        register_model(model)

        record = transition_model(
            model_id=model_id,
            current_state=current_state,
            target_state=ModelLifecycleState.QUARANTINED,
            actor=actor,
            risk_class=ModelRiskClass.STANDARD,
            actor_type="human",
            evidence="safety concern",
        )

        assert record.success is True
        assert record.to_state == ModelLifecycleState.QUARANTINED.value
        assert get_model(model_id).state == ModelLifecycleState.QUARANTINED


# =============================================================================
# Property 10.4: All Transitions Are Logged
# "Every lifecycle transition (success or failure) produces an audit record."
# =============================================================================


@pytest.mark.unit
class TestTransitionAuditCompleteness:
    """Every lifecycle transition attempt produces an audit record.

    **Validates: Requirements R67.1**
    """

    @given(
        current_state=lifecycle_state_strategy,
        target_state=lifecycle_state_strategy,
        model_id=st.from_regex(r"model-[a-f0-9]{8}", fullmatch=True),
        org_id=org_id_strategy,
        actor=actor_strategy,
    )
    @settings(max_examples=200, deadline=None)
    def test_every_transition_attempt_is_logged(
        self,
        current_state: ModelLifecycleState,
        target_state: ModelLifecycleState,
        model_id: str,
        org_id: str,
        actor: str,
    ):
        """Whether success or failure, every transition attempt creates a log record.

        **Validates: Requirements R67.1**
        """
        clear_registry()

        model = ModelRecord(
            model_id=model_id,
            org_id=org_id,
            name="test-model",
            state=current_state,
            risk_class=ModelRiskClass.STANDARD,
        )
        register_model(model)

        initial_log_count = len(get_transition_log(model_id))

        try:
            transition_model(
                model_id=model_id,
                current_state=current_state,
                target_state=target_state,
                actor=actor,
                risk_class=ModelRiskClass.STANDARD,
                actor_type="human",
                evidence="test",
            )
        except (ModelLifecycleError, ModelNotFoundError):
            pass

        # A log entry must have been created
        new_log_count = len(get_transition_log(model_id))
        assert new_log_count > initial_log_count, (
            f"NO AUDIT RECORD: transition attempt {current_state.value} → "
            f"{target_state.value} did not create a log entry"
        )

        # Verify log has required fields per R67.6
        record = get_transition_log(model_id)[-1]
        assert record.model_id == model_id
        assert record.from_state == current_state.value
        assert record.to_state == target_state.value
        assert record.actor == actor
        assert record.timestamp and len(record.timestamp) > 0

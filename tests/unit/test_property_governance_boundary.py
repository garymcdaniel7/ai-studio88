"""Property-Based Governance Boundary Completeness Tests — Task 14.4.

Proves the Governance Boundary Completeness property using hypothesis:
  - No side effect executes without governance check
  - Every evaluation produces an audit record
  - High-risk actions fail closed on governance unavailability
  - Unknown actions are conservatively classified (PAID)
  - No decision state silently permits execution

Validates: Requirements R59.1, R59.6

Run with:
    pytest tests/unit/test_property_governance_boundary.py -v
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from backend.governance import (
    ACTION_RISK_MAP,
    DecisionState,
    GovernanceDecision,
    RiskClass,
    _governance_audit,
    classify_action,
    evaluate_action,
    get_governance_audit,
)
from tests.fixtures.tenant_fixtures import (
    ALPHA_OWNER,
    BETA_OWNER,
    ORG_ALPHA,
    ORG_BETA,
)


# =============================================================================
# Strategies — generate random governance contexts
# =============================================================================

# Random action strings (mix of known and unknown)
known_action_strategy = st.sampled_from(list(ACTION_RISK_MAP.keys()))
unknown_action_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "Nd"), whitelist_characters="_"),
    min_size=3,
    max_size=30,
).filter(lambda s: s not in ACTION_RISK_MAP)
any_action_strategy = st.one_of(known_action_strategy, unknown_action_strategy)

# All risk classes
risk_class_strategy = st.sampled_from(list(RiskClass))

# High-risk classes that require fail-closed behavior
high_risk_strategy = st.sampled_from([
    rc for rc in RiskClass if rc.requires_fail_closed
])

# Low-risk classes that allow degraded mode
low_risk_strategy = st.sampled_from([
    rc for rc in RiskClass if rc.allows_degraded
])

# All decision states
decision_state_strategy = st.sampled_from(list(DecisionState))

# Valid org/user IDs
org_id_strategy = st.from_regex(
    r"org-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}",
    fullmatch=True,
)
user_id_strategy = st.from_regex(
    r"usr-[a-f0-9]{4}-[a-f0-9]{12}",
    fullmatch=True,
)

# Estimated cost (non-negative)
cost_strategy = st.floats(min_value=0.0, max_value=1000.0, allow_nan=False, allow_infinity=False)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def clean_audit():
    """Clear the in-memory audit trail before/after each test."""
    _governance_audit.clear()
    yield
    _governance_audit.clear()


# =============================================================================
# Property 7.1: evaluate_action() Always Returns a GovernanceDecision
# "For ANY action and risk class, evaluate_action never raises and never
#  returns None — it always produces an explicit GovernanceDecision."
# =============================================================================


@pytest.mark.unit
class TestEvaluateActionAlwaysReturnsDecision:
    """evaluate_action() always returns a GovernanceDecision, never None.

    **Validates: Requirements R59.1**
    """

    @given(
        action=any_action_strategy,
        risk_class=risk_class_strategy,
        org_id=org_id_strategy,
        user_id=user_id_strategy,
        cost=cost_strategy,
    )
    @settings(max_examples=200, deadline=None)
    def test_evaluate_always_returns_decision(
        self,
        action: str,
        risk_class: RiskClass,
        org_id: str,
        user_id: str,
        cost: float,
    ):
        """For any inputs, evaluate_action returns a GovernanceDecision.

        **Validates: Requirements R59.1**
        """
        _governance_audit.clear()

        # Mock all external dependencies so the function can run purely
        with patch("backend.governance._check_policy_availability") as mock_policy, \
             patch("backend.governance._check_budget_availability") as mock_budget, \
             patch("backend.governance._check_audit_availability") as mock_audit:
            mock_policy.return_value = MagicMock(available=True)
            mock_budget.return_value = MagicMock(available=True)
            mock_audit.return_value = MagicMock(available=True)

            with patch("backend.aios.governance.policies.get_policies", return_value={
                "max_auto_spend_usd": 999.0,
                "budget_daily_usd": 9999.0,
                "require_delete_approval": False,
                "require_publish_approval": False,
                "auto_approve_gpu_launch": True,
            }):
                with patch(
                    "backend.infrastructure.cost_intelligence.get_cost_tracker"
                ) as mock_tracker:
                    mock_tracker.return_value.get_today_total.return_value = 0.0

                    decision = evaluate_action(
                        action=action,
                        risk_class=risk_class,
                        actor_user_id=user_id,
                        org_id=org_id,
                        estimated_cost_usd=cost,
                    )

        # Must return a GovernanceDecision, never None
        assert decision is not None
        assert isinstance(decision, GovernanceDecision)
        # Must have an explicit state
        assert isinstance(decision.state, DecisionState)
        # Must have a risk class
        assert isinstance(decision.risk_class, RiskClass)
        # Must have a non-empty reason
        assert decision.reason and len(decision.reason) > 0
        # Must have the correct actor and org
        assert decision.actor_user_id == user_id
        assert decision.org_id == org_id


# =============================================================================
# Property 7.2: Every Evaluation Produces an Audit Record
# "After evaluate_action() is called, the audit trail contains a
#  corresponding record with required fields."
# =============================================================================


@pytest.mark.unit
class TestEveryEvaluationProducesAuditRecord:
    """Every governance evaluation creates an audit record.

    **Validates: Requirements R59.6**
    """

    @given(
        action=any_action_strategy,
        risk_class=risk_class_strategy,
        org_id=org_id_strategy,
        user_id=user_id_strategy,
        cost=cost_strategy,
    )
    @settings(max_examples=200, deadline=None)
    def test_audit_record_created_for_every_evaluation(
        self,
        action: str,
        risk_class: RiskClass,
        org_id: str,
        user_id: str,
        cost: float,
    ):
        """After evaluation, audit trail contains a matching record.

        **Validates: Requirements R59.6**
        """
        _governance_audit.clear()

        with patch("backend.governance._check_policy_availability") as mock_policy, \
             patch("backend.governance._check_budget_availability") as mock_budget, \
             patch("backend.governance._check_audit_availability") as mock_audit:
            mock_policy.return_value = MagicMock(available=True)
            mock_budget.return_value = MagicMock(available=True)
            mock_audit.return_value = MagicMock(available=True)

            with patch("backend.aios.governance.policies.get_policies", return_value={
                "max_auto_spend_usd": 999.0,
                "budget_daily_usd": 9999.0,
                "require_delete_approval": False,
                "require_publish_approval": False,
                "auto_approve_gpu_launch": True,
            }):
                with patch(
                    "backend.infrastructure.cost_intelligence.get_cost_tracker"
                ) as mock_tracker:
                    mock_tracker.return_value.get_today_total.return_value = 0.0

                    decision = evaluate_action(
                        action=action,
                        risk_class=risk_class,
                        actor_user_id=user_id,
                        org_id=org_id,
                        estimated_cost_usd=cost,
                    )

        # Audit trail must contain at least one record
        assert len(_governance_audit) >= 1, (
            "No audit record found after governance evaluation"
        )

        # Find the matching record by request_id
        matching = [
            e for e in _governance_audit
            if e["request_id"] == decision.request_id
        ]
        assert len(matching) == 1, (
            f"Expected exactly 1 audit record for request_id={decision.request_id}, "
            f"found {len(matching)}"
        )

        record = matching[0]

        # R59.6: Log must contain required fields
        assert "request_id" in record
        assert "actor_user_id" in record  # identity
        assert "org_id" in record  # trust_domain / tenant context
        assert "action" in record  # action_type
        assert "risk_class" in record  # risk_classification
        assert "state" in record  # result
        assert "reason" in record  # denial_reason (or success reason)
        assert "timestamp" in record

        # Values must match the decision
        assert record["actor_user_id"] == user_id
        assert record["org_id"] == org_id
        assert record["action"] == action
        assert record["risk_class"] == risk_class.value
        assert record["state"] == decision.state.value


# =============================================================================
# Property 7.3: High-Risk Actions Fail Closed on Governance Unavailability
# "For ALL risk classes requiring fail_closed, when a governance dependency
#  is unavailable, decision.allowed is always False."
# =============================================================================


@pytest.mark.unit
class TestHighRiskFailsClosed:
    """High-risk actions deny when governance dependencies are unavailable.

    **Validates: Requirements R59.1**
    """

    @given(
        action=any_action_strategy,
        risk_class=high_risk_strategy,
        org_id=org_id_strategy,
        user_id=user_id_strategy,
        cost=cost_strategy,
    )
    @settings(max_examples=200, deadline=None)
    def test_policy_unavailable_denies_high_risk(
        self,
        action: str,
        risk_class: RiskClass,
        org_id: str,
        user_id: str,
        cost: float,
    ):
        """Policy dependency failure → execution denied for high-risk.

        **Validates: Requirements R59.1**
        """
        _governance_audit.clear()

        with patch("backend.governance._check_policy_availability") as mock_policy, \
             patch("backend.governance._check_budget_availability") as mock_budget, \
             patch("backend.governance._check_audit_availability") as mock_audit:
            # Policy unavailable
            mock_policy.return_value = MagicMock(available=False, error="timeout")
            mock_budget.return_value = MagicMock(available=True)
            mock_audit.return_value = MagicMock(available=True)

            decision = evaluate_action(
                action=action,
                risk_class=risk_class,
                actor_user_id=user_id,
                org_id=org_id,
                estimated_cost_usd=cost,
            )

        # High-risk MUST be denied when policy is unavailable
        assert decision.allowed is False, (
            f"GOVERNANCE BREACH: high-risk action '{action}' "
            f"(risk_class={risk_class.value}) was ALLOWED despite "
            f"policy dependency unavailability"
        )
        assert decision.state == DecisionState.GOVERNANCE_UNAVAILABLE

    @given(
        action=any_action_strategy,
        risk_class=high_risk_strategy,
        org_id=org_id_strategy,
        user_id=user_id_strategy,
        cost=cost_strategy,
    )
    @settings(max_examples=200, deadline=None)
    def test_audit_unavailable_denies_high_risk(
        self,
        action: str,
        risk_class: RiskClass,
        org_id: str,
        user_id: str,
        cost: float,
    ):
        """Audit dependency failure → execution denied for high-risk.

        **Validates: Requirements R59.1**
        """
        _governance_audit.clear()

        with patch("backend.governance._check_policy_availability") as mock_policy, \
             patch("backend.governance._check_budget_availability") as mock_budget, \
             patch("backend.governance._check_audit_availability") as mock_audit:
            mock_policy.return_value = MagicMock(available=True)
            mock_budget.return_value = MagicMock(available=True)
            # Audit unavailable
            mock_audit.return_value = MagicMock(available=False, error="db_timeout")

            decision = evaluate_action(
                action=action,
                risk_class=risk_class,
                actor_user_id=user_id,
                org_id=org_id,
                estimated_cost_usd=cost,
            )

        # High-risk MUST be denied when audit is unavailable
        assert decision.allowed is False, (
            f"GOVERNANCE BREACH: high-risk action '{action}' "
            f"(risk_class={risk_class.value}) was ALLOWED despite "
            f"audit dependency unavailability"
        )
        assert decision.state == DecisionState.GOVERNANCE_UNAVAILABLE


# =============================================================================
# Property 7.4: Unknown Actions Are Conservatively Classified
# "Actions not in ACTION_RISK_MAP default to PAID (fail-closed behavior)."
# =============================================================================


@pytest.mark.unit
class TestUnknownActionsConservativelyClassified:
    """Unknown actions default to PAID, ensuring fail-closed behavior.

    **Validates: Requirements R59.1**
    """

    @given(action=unknown_action_strategy)
    @settings(max_examples=200, deadline=None)
    def test_unknown_action_classified_as_paid(self, action: str):
        """Any action not in ACTION_RISK_MAP is classified as PAID.

        **Validates: Requirements R59.1**
        """
        result = classify_action(action)
        assert result == RiskClass.PAID, (
            f"Unknown action '{action}' classified as {result.value} "
            f"instead of PAID (fail-closed default)"
        )

    @given(action=unknown_action_strategy)
    @settings(max_examples=200, deadline=None)
    def test_unknown_action_requires_fail_closed(self, action: str):
        """Unknown actions inherit PAID's fail-closed requirement.

        **Validates: Requirements R59.1**
        """
        risk = classify_action(action)
        assert risk.requires_fail_closed is True, (
            f"Unknown action '{action}' classified as {risk.value} which "
            f"does NOT require fail-closed — conservative default violated"
        )


# =============================================================================
# Property 7.5: Decision State Permits Execution Correctly
# "Only ALLOWED and DEGRADED_ALLOWED permit execution; all other states
#  block. No silent allow possible."
# =============================================================================


@pytest.mark.unit
class TestDecisionStatePermitsExecutionCorrectly:
    """Only ALLOWED and DEGRADED_ALLOWED permit execution.

    **Validates: Requirements R59.1, R59.6**
    """

    @given(state=decision_state_strategy)
    @settings(max_examples=200, deadline=None)
    def test_only_allowed_states_permit_execution(self, state: DecisionState):
        """permits_execution is True only for ALLOWED and DEGRADED_ALLOWED.

        **Validates: Requirements R59.1**
        """
        permitting_states = {DecisionState.ALLOWED, DecisionState.DEGRADED_ALLOWED}

        if state in permitting_states:
            assert state.permits_execution is True, (
                f"State {state.value} should permit execution but does not"
            )
        else:
            assert state.permits_execution is False, (
                f"GOVERNANCE BREACH: State {state.value} silently permits "
                f"execution — only ALLOWED and DEGRADED_ALLOWED should allow"
            )

    @given(state=decision_state_strategy)
    @settings(max_examples=200, deadline=None)
    def test_decision_allowed_property_matches_permits_execution(
        self, state: DecisionState
    ):
        """GovernanceDecision.allowed always matches state.permits_execution.

        **Validates: Requirements R59.6**
        """
        decision = GovernanceDecision(
            state=state,
            risk_class=RiskClass.READ_ONLY,
            reason="test",
            action="test_action",
            actor_user_id="usr-test",
            org_id="org-test",
        )
        assert decision.allowed == state.permits_execution, (
            f"Decision.allowed ({decision.allowed}) does not match "
            f"state.permits_execution ({state.permits_execution}) "
            f"for state {state.value}"
        )


# =============================================================================
# Property 7.6: Known Actions Map to Expected Risk Classes
# "Every action in ACTION_RISK_MAP maps to its declared risk class."
# =============================================================================


@pytest.mark.unit
class TestKnownActionsMapCorrectly:
    """All known actions in ACTION_RISK_MAP classify to their expected risk.

    **Validates: Requirements R59.1**
    """

    @given(action=known_action_strategy)
    @settings(max_examples=200, deadline=None)
    def test_known_action_maps_to_expected_risk(self, action: str):
        """classify_action returns the mapped risk class for known actions.

        **Validates: Requirements R59.1**
        """
        expected = ACTION_RISK_MAP[action]
        actual = classify_action(action)
        assert actual == expected, (
            f"Action '{action}' classified as {actual.value} "
            f"but expected {expected.value}"
        )


# =============================================================================
# Property 7.7: Read-Only/Low-Risk May Degrade But High-Risk Cannot
# "Degraded mode is only possible for READ_ONLY and LOW_RISK."
# =============================================================================


@pytest.mark.unit
class TestDegradedModeOnlyForLowRisk:
    """Degraded mode is only available for READ_ONLY and LOW_RISK.

    **Validates: Requirements R59.1**
    """

    @given(risk_class=risk_class_strategy)
    @settings(max_examples=200, deadline=None)
    def test_allows_degraded_matches_risk_level(self, risk_class: RiskClass):
        """Only READ_ONLY and LOW_RISK allow degraded mode.

        **Validates: Requirements R59.1**
        """
        degradable = {RiskClass.READ_ONLY, RiskClass.LOW_RISK}
        if risk_class in degradable:
            assert risk_class.allows_degraded is True
        else:
            assert risk_class.allows_degraded is False, (
                f"GOVERNANCE BREACH: {risk_class.value} allows degraded mode "
                f"but is not READ_ONLY or LOW_RISK"
            )

    @given(
        risk_class=low_risk_strategy,
        org_id=org_id_strategy,
        user_id=user_id_strategy,
    )
    @settings(max_examples=200, deadline=None)
    def test_low_risk_degrades_when_policy_unavailable(
        self,
        risk_class: RiskClass,
        org_id: str,
        user_id: str,
    ):
        """Low-risk actions return DEGRADED_ALLOWED when policies fail.

        **Validates: Requirements R59.1**
        """
        _governance_audit.clear()

        with patch(
            "backend.aios.governance.policies.get_policies",
            side_effect=Exception("policy service down"),
        ):
            decision = evaluate_action(
                action="chat",
                risk_class=risk_class,
                actor_user_id=user_id,
                org_id=org_id,
            )

        assert decision.state == DecisionState.DEGRADED_ALLOWED
        assert decision.allowed is True
        assert decision.is_degraded is True


# =============================================================================
# Property 7.8: Audit Record Fields Are Never Empty for Required Fields
# "Every audit record has non-empty required fields per R59.6."
# =============================================================================


@pytest.mark.unit
class TestAuditRecordFieldsComplete:
    """Audit records always have complete, non-empty required fields.

    **Validates: Requirements R59.6**
    """

    @given(
        action=any_action_strategy,
        risk_class=risk_class_strategy,
        org_id=org_id_strategy,
        user_id=user_id_strategy,
    )
    @settings(max_examples=200, deadline=None)
    def test_audit_record_fields_never_empty(
        self,
        action: str,
        risk_class: RiskClass,
        org_id: str,
        user_id: str,
    ):
        """All required audit fields are non-empty strings or valid values.

        **Validates: Requirements R59.6**
        """
        _governance_audit.clear()

        with patch("backend.governance._check_policy_availability") as mock_policy, \
             patch("backend.governance._check_budget_availability") as mock_budget, \
             patch("backend.governance._check_audit_availability") as mock_audit:
            mock_policy.return_value = MagicMock(available=True)
            mock_budget.return_value = MagicMock(available=True)
            mock_audit.return_value = MagicMock(available=True)

            with patch("backend.aios.governance.policies.get_policies", return_value={
                "max_auto_spend_usd": 999.0,
                "budget_daily_usd": 9999.0,
                "require_delete_approval": False,
                "require_publish_approval": False,
                "auto_approve_gpu_launch": True,
            }):
                with patch(
                    "backend.infrastructure.cost_intelligence.get_cost_tracker"
                ) as mock_tracker:
                    mock_tracker.return_value.get_today_total.return_value = 0.0

                    evaluate_action(
                        action=action,
                        risk_class=risk_class,
                        actor_user_id=user_id,
                        org_id=org_id,
                    )

        assert len(_governance_audit) >= 1

        record = _governance_audit[-1]

        # Required fields per R59.6 must be non-empty
        assert record["request_id"] and len(record["request_id"]) > 0
        assert record["actor_user_id"] and len(record["actor_user_id"]) > 0
        assert record["org_id"] and len(record["org_id"]) > 0
        assert record["action"] and len(record["action"]) > 0
        assert record["risk_class"] and len(record["risk_class"]) > 0
        assert record["state"] and len(record["state"]) > 0
        assert record["reason"] and len(record["reason"]) > 0
        assert record["timestamp"] and len(record["timestamp"]) > 0
        # allowed must be a boolean
        assert isinstance(record["allowed"], bool)

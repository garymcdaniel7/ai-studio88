"""Fail-Safe Governance Decision Contract Tests (Story 025).

Tests every risk class and dependency-failure branch.

Run with:
    pytest tests/unit/test_governance.py -v
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock
from uuid import uuid4

import pytest

from backend.governance import (
    DecisionState,
    GovernanceDecision,
    RiskClass,
    _governance_audit,
    classify_action,
    evaluate_action,
    get_governance_audit,
)

ORG = str(uuid4())
USER = str(uuid4())


@pytest.fixture(autouse=True)
def clean_audit():
    _governance_audit.clear()
    yield
    _governance_audit.clear()


# =============================================================================
# Risk Classification
# =============================================================================


class TestRiskClassification:

    @pytest.mark.unit
    def test_high_risk_classes_require_fail_closed(self):
        for rc in [RiskClass.PAID, RiskClass.DESTRUCTIVE, RiskClass.PUBLISHING,
                   RiskClass.CREDENTIAL, RiskClass.MODEL_ACTIVATE, RiskClass.INFRASTRUCTURE]:
            assert rc.requires_fail_closed is True

    @pytest.mark.unit
    def test_low_risk_classes_allow_degraded(self):
        assert RiskClass.READ_ONLY.allows_degraded is True
        assert RiskClass.LOW_RISK.allows_degraded is True

    @pytest.mark.unit
    def test_high_risk_does_not_allow_degraded(self):
        assert RiskClass.PAID.allows_degraded is False
        assert RiskClass.DESTRUCTIVE.allows_degraded is False

    @pytest.mark.unit
    def test_unknown_action_classified_as_paid(self):
        assert classify_action("unknown_xyz") == RiskClass.PAID

    @pytest.mark.unit
    def test_known_actions_classified_correctly(self):
        assert classify_action("chat") == RiskClass.READ_ONLY
        assert classify_action("generate_image") == RiskClass.PAID
        assert classify_action("delete_asset") == RiskClass.DESTRUCTIVE
        assert classify_action("launch_gpu") == RiskClass.INFRASTRUCTURE
        assert classify_action("publish_post") == RiskClass.PUBLISHING
        assert classify_action("store_credential") == RiskClass.CREDENTIAL
        assert classify_action("promote_lora") == RiskClass.MODEL_ACTIVATE


# =============================================================================
# Decision States
# =============================================================================


class TestDecisionStates:

    @pytest.mark.unit
    def test_allowed_permits_execution(self):
        assert DecisionState.ALLOWED.permits_execution is True
        assert DecisionState.DEGRADED_ALLOWED.permits_execution is True

    @pytest.mark.unit
    def test_denied_blocks_execution(self):
        assert DecisionState.DENIED.permits_execution is False
        assert DecisionState.GOVERNANCE_UNAVAILABLE.permits_execution is False
        assert DecisionState.BUDGET_EXCEEDED.permits_execution is False
        assert DecisionState.AUDIT_FAILURE.permits_execution is False
        assert DecisionState.APPROVAL_REQUIRED.permits_execution is False


# =============================================================================
# Paid Action — Budget Check Failure (Fail-Closed)
# =============================================================================


class TestPaidActionBudgetFailure:

    @pytest.mark.unit
    @patch("backend.governance._check_budget_availability")
    @patch("backend.governance._check_policy_availability")
    @patch("backend.governance._check_audit_availability")
    def test_budget_timeout_denies_paid_action(self, mock_audit, mock_policy, mock_budget):
        """Budget service timeout → GOVERNANCE_UNAVAILABLE."""
        mock_policy.return_value = MagicMock(available=True)
        mock_budget.return_value = MagicMock(available=False, error="timeout")
        mock_audit.return_value = MagicMock(available=True)

        decision = evaluate_action(
            action="generate_image", risk_class=RiskClass.PAID,
            actor_user_id=USER, org_id=ORG, estimated_cost_usd=1.50,
        )
        assert decision.state == DecisionState.GOVERNANCE_UNAVAILABLE
        assert decision.allowed is False

    @pytest.mark.unit
    @patch("backend.governance._check_budget_availability")
    @patch("backend.governance._check_policy_availability")
    @patch("backend.governance._check_audit_availability")
    def test_paid_action_allowed_when_all_pass(self, mock_audit, mock_policy, mock_budget):
        """All deps available + within budget → ALLOWED."""
        mock_policy.return_value = MagicMock(available=True)
        mock_budget.return_value = MagicMock(available=True)
        mock_audit.return_value = MagicMock(available=True)

        with patch("backend.aios.governance.policies.get_policies", return_value={
            "max_auto_spend_usd": 10.0, "budget_daily_usd": 50.0,
        }):
            with patch("backend.infrastructure.cost_intelligence.get_cost_tracker") as mt:
                mt.return_value.get_today_total.return_value = 5.0
                decision = evaluate_action(
                    action="generate_image", risk_class=RiskClass.PAID,
                    actor_user_id=USER, org_id=ORG, estimated_cost_usd=1.50,
                )

        assert decision.state == DecisionState.ALLOWED
        assert decision.allowed is True


# =============================================================================
# Destructive Action — Policy Failure (Fail-Closed)
# =============================================================================


class TestDestructiveActionPolicyFailure:

    @pytest.mark.unit
    @patch("backend.governance._check_policy_availability")
    @patch("backend.governance._check_audit_availability")
    def test_policy_unavailable_denies_destructive(self, mock_audit, mock_policy):
        mock_policy.return_value = MagicMock(available=False, error="conn_refused")
        mock_audit.return_value = MagicMock(available=True)

        decision = evaluate_action(
            action="delete_asset", risk_class=RiskClass.DESTRUCTIVE,
            actor_user_id=USER, org_id=ORG,
        )
        assert decision.state == DecisionState.GOVERNANCE_UNAVAILABLE
        assert decision.allowed is False


# =============================================================================
# Infrastructure Action — Fail-Closed
# =============================================================================


class TestInfrastructureActionFailClosed:

    @pytest.mark.unit
    @patch("backend.governance._check_policy_availability")
    @patch("backend.governance._check_audit_availability")
    def test_audit_unavailable_denies_infrastructure(self, mock_audit, mock_policy):
        mock_policy.return_value = MagicMock(available=True)
        mock_audit.return_value = MagicMock(available=False, error="db_timeout")

        decision = evaluate_action(
            action="launch_gpu", risk_class=RiskClass.INFRASTRUCTURE,
            actor_user_id=USER, org_id=ORG, estimated_cost_usd=2.0,
        )
        assert decision.state == DecisionState.GOVERNANCE_UNAVAILABLE
        assert decision.allowed is False


# =============================================================================
# Read-Only — Degraded Mode
# =============================================================================


class TestReadOnlyDegradedMode:

    @pytest.mark.unit
    def test_read_only_degraded_when_policy_fails(self):
        """Policy load raises → DEGRADED_ALLOWED for read-only."""
        with patch("backend.aios.governance.policies.get_policies", side_effect=Exception("timeout")):
            decision = evaluate_action(
                action="chat", risk_class=RiskClass.READ_ONLY,
                actor_user_id=USER, org_id=ORG,
            )
        assert decision.state == DecisionState.DEGRADED_ALLOWED
        assert decision.allowed is True
        assert decision.is_degraded is True

    @pytest.mark.unit
    def test_read_only_allowed_normally(self):
        """Healthy → ALLOWED (not degraded)."""
        decision = evaluate_action(
            action="chat", risk_class=RiskClass.READ_ONLY,
            actor_user_id=USER, org_id=ORG,
        )
        assert decision.state == DecisionState.ALLOWED
        assert decision.is_degraded is False


# =============================================================================
# Approval Required — Policy-Driven
# =============================================================================


class TestApprovalRequired:

    @pytest.mark.unit
    @patch("backend.governance._check_policy_availability")
    @patch("backend.governance._check_audit_availability")
    def test_destructive_requires_approval(self, mock_audit, mock_policy):
        mock_policy.return_value = MagicMock(available=True)
        mock_audit.return_value = MagicMock(available=True)

        with patch("backend.aios.governance.policies.get_policies", return_value={
            "require_delete_approval": True,
        }):
            decision = evaluate_action(
                action="delete_asset", risk_class=RiskClass.DESTRUCTIVE,
                actor_user_id=USER, org_id=ORG,
            )
        assert decision.state == DecisionState.APPROVAL_REQUIRED
        assert decision.allowed is False

    @pytest.mark.unit
    @patch("backend.governance._check_policy_availability")
    @patch("backend.governance._check_audit_availability")
    def test_publishing_requires_approval(self, mock_audit, mock_policy):
        mock_policy.return_value = MagicMock(available=True)
        mock_audit.return_value = MagicMock(available=True)

        with patch("backend.aios.governance.policies.get_policies", return_value={
            "require_publish_approval": True,
        }):
            decision = evaluate_action(
                action="publish_post", risk_class=RiskClass.PUBLISHING,
                actor_user_id=USER, org_id=ORG,
            )
        assert decision.state == DecisionState.APPROVAL_REQUIRED


# =============================================================================
# Budget Exceeded
# =============================================================================


class TestBudgetExceeded:

    @pytest.mark.unit
    @patch("backend.governance._check_policy_availability")
    @patch("backend.governance._check_budget_availability")
    @patch("backend.governance._check_audit_availability")
    def test_cost_exceeds_auto_approve_limit(self, mock_audit, mock_budget, mock_policy):
        mock_policy.return_value = MagicMock(available=True)
        mock_budget.return_value = MagicMock(available=True)
        mock_audit.return_value = MagicMock(available=True)

        with patch("backend.aios.governance.policies.get_policies", return_value={
            "max_auto_spend_usd": 5.0, "budget_daily_usd": 100.0,
        }):
            decision = evaluate_action(
                action="train_lora", risk_class=RiskClass.PAID,
                actor_user_id=USER, org_id=ORG, estimated_cost_usd=25.0,
            )
        assert decision.state == DecisionState.APPROVAL_REQUIRED
        assert "$25.00" in decision.reason


# =============================================================================
# Audit Persistence Failure
# =============================================================================


class TestAuditPersistenceFailure:

    @pytest.mark.unit
    @patch("backend.governance._check_policy_availability")
    @patch("backend.governance._check_audit_availability")
    @patch("backend.governance._persist_audit", return_value=False)
    def test_audit_failure_blocks_high_risk(self, mock_persist, mock_audit, mock_policy):
        mock_policy.return_value = MagicMock(available=True)
        mock_audit.return_value = MagicMock(available=True)

        with patch("backend.aios.governance.policies.get_policies", return_value={}):
            decision = evaluate_action(
                action="store_credential", risk_class=RiskClass.CREDENTIAL,
                actor_user_id=USER, org_id=ORG,
            )
        assert decision.state == DecisionState.AUDIT_FAILURE
        assert decision.allowed is False


# =============================================================================
# Audit Trail
# =============================================================================


class TestAuditTrail:

    @pytest.mark.unit
    def test_allowed_decision_recorded(self):
        evaluate_action(action="chat", risk_class=RiskClass.READ_ONLY, actor_user_id=USER, org_id=ORG)
        audit = get_governance_audit(org_id=ORG)
        assert len(audit) >= 1
        assert audit[0]["state"] == "allowed"

    @pytest.mark.unit
    @patch("backend.governance._check_policy_availability")
    @patch("backend.governance._check_audit_availability")
    def test_denied_decision_recorded(self, mock_audit, mock_policy):
        mock_policy.return_value = MagicMock(available=False, error="x")
        mock_audit.return_value = MagicMock(available=True)
        evaluate_action(action="launch_gpu", risk_class=RiskClass.INFRASTRUCTURE, actor_user_id=USER, org_id=ORG)
        audit = get_governance_audit(org_id=ORG)
        assert any(e["state"] == "governance_unavailable" for e in audit)


# =============================================================================
# Serialization
# =============================================================================


class TestSerialization:

    @pytest.mark.unit
    def test_to_dict_safe(self):
        d = GovernanceDecision(
            state=DecisionState.ALLOWED, risk_class=RiskClass.PAID,
            reason="ok", action="gen", actor_user_id=USER, org_id=ORG,
        )
        out = d.to_dict()
        assert out["state"] == "allowed"
        assert out["allowed"] is True
        assert out["request_id"].startswith("gov-")
        assert "secret" not in str(out).lower()

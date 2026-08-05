"""Unified governance enforcement boundary tests — Story 034.

Tests prove:
  - Side-effecting tools are blocked without context
  - Read-only tools bypass governance
  - Unknown tools are denied (fail-safe)
  - Viewer role cannot execute side effects
  - Policy-driven approval requirements work
  - Budget gate triggers approval
  - Missing actor/workspace denied
  - Arguments hash is stable (replay detection)
  - Governance decision includes full audit context
  - No supported bypass remains
"""

from unittest.mock import patch

import pytest

from backend.aios.governance.enforcement import (
    ActionEffect,
    GOVERNED_TOOLS,
    GovernanceApprovalRequired,
    GovernanceBlockedError,
    GovernanceOutcome,
    READ_ONLY_TOOLS,
    TOOL_EFFECTS,
    classify_tool,
    compute_arguments_hash,
    enforce_governance,
    is_governed,
    is_read_only,
)

TENANT_A = "org-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
USER_A = "user-aaaa"


# =============================================================================
# Tool Classification
# =============================================================================


@pytest.mark.unit
class TestToolClassification:
    """Verify tool effect classification is correct."""

    def test_generate_image_is_side_effect(self):
        assert classify_tool("generate_image") == ActionEffect.SIDE_EFFECT

    def test_train_lora_is_side_effect(self):
        assert classify_tool("train_lora") == ActionEffect.SIDE_EFFECT

    def test_launch_gpu_is_side_effect(self):
        assert classify_tool("launch_gpu_worker") == ActionEffect.SIDE_EFFECT

    def test_schedule_post_is_side_effect(self):
        assert classify_tool("schedule_post") == ActionEffect.SIDE_EFFECT

    def test_search_talent_is_read_only(self):
        assert classify_tool("search_talent") == ActionEffect.READ_ONLY

    def test_get_fleet_status_is_read_only(self):
        assert classify_tool("get_fleet_status") == ActionEffect.READ_ONLY

    def test_unknown_tool_returns_none(self):
        assert classify_tool("hacker_tool") is None

    def test_governed_and_readonly_are_disjoint(self):
        """No tool can be both governed and read-only."""
        assert GOVERNED_TOOLS.isdisjoint(READ_ONLY_TOOLS)

    def test_all_tools_classified(self):
        """Every tool in the registry has a valid effect."""
        for tool, effect in TOOL_EFFECTS.items():
            assert effect in (ActionEffect.SIDE_EFFECT, ActionEffect.READ_ONLY)


# =============================================================================
# Read-Only Bypass
# =============================================================================


@pytest.mark.unit
class TestReadOnlyBypass:
    """Verify read-only tools bypass governance cleanly."""

    def test_search_talent_bypasses(self):
        decision = enforce_governance(
            tool="search_talent",
            parameters={"query": "Melissa"},
            actor_id=USER_A,
            org_id=TENANT_A,
            source="test",
        )
        assert decision.outcome == GovernanceOutcome.BYPASS_READ_ONLY

    def test_read_only_even_without_role(self):
        """Read-only tools work even for viewer role."""
        decision = enforce_governance(
            tool="get_fleet_status",
            parameters={},
            actor_id=USER_A,
            org_id=TENANT_A,
            role="viewer",
            source="test",
        )
        assert decision.outcome == GovernanceOutcome.BYPASS_READ_ONLY


# =============================================================================
# Unknown Tool — Fail-Safe Deny
# =============================================================================


@pytest.mark.unit
class TestUnknownToolDenied:
    """Verify unknown tools are denied by default."""

    @patch("backend.aios.governance.enforcement._audit_decision")
    def test_unknown_tool_raises_blocked(self, mock_audit):
        with pytest.raises(GovernanceBlockedError, match="not registered"):
            enforce_governance(
                tool="evil_backdoor",
                parameters={"target": "production"},
                actor_id=USER_A,
                org_id=TENANT_A,
                source="test",
            )


# =============================================================================
# Missing Context — Denied
# =============================================================================


@pytest.mark.unit
class TestMissingContextDenied:
    """Verify missing actor/workspace blocks execution."""

    @patch("backend.aios.governance.enforcement._audit_decision")
    def test_missing_actor_denied(self, mock_audit):
        with pytest.raises(GovernanceBlockedError, match="Missing actor"):
            enforce_governance(
                tool="generate_image",
                parameters={"prompt": "test"},
                actor_id="",
                org_id=TENANT_A,
                source="test",
            )

    @patch("backend.aios.governance.enforcement._audit_decision")
    def test_missing_org_denied(self, mock_audit):
        with pytest.raises(GovernanceBlockedError, match="Missing workspace"):
            enforce_governance(
                tool="generate_image",
                parameters={"prompt": "test"},
                actor_id=USER_A,
                org_id="",
                source="test",
            )


# =============================================================================
# Role Enforcement
# =============================================================================


@pytest.mark.unit
class TestRoleEnforcement:
    """Verify viewer role cannot execute side effects."""

    @patch("backend.aios.governance.enforcement._audit_decision")
    def test_viewer_denied_side_effect(self, mock_audit):
        with pytest.raises(GovernanceBlockedError, match="insufficient"):
            enforce_governance(
                tool="generate_image",
                parameters={"prompt": "test"},
                actor_id=USER_A,
                org_id=TENANT_A,
                role="viewer",
                source="test",
            )

    @patch("backend.aios.governance.enforcement._audit_decision")
    @patch("backend.aios.governance.enforcement._load_policies")
    def test_editor_allowed(self, mock_policies, mock_audit):
        mock_policies.return_value = {"auto_approve_generation": True, "max_auto_spend_usd": 100.0}
        decision = enforce_governance(
            tool="generate_image",
            parameters={"prompt": "test"},
            actor_id=USER_A,
            org_id=TENANT_A,
            role="editor",
            source="test",
        )
        assert decision.outcome == GovernanceOutcome.ALLOW


# =============================================================================
# Policy-Driven Approval
# =============================================================================


@pytest.mark.unit
class TestPolicyApproval:
    """Verify policies correctly trigger approval requirements."""

    @patch("backend.aios.governance.enforcement._audit_decision")
    @patch("backend.aios.governance.enforcement._load_policies")
    def test_training_requires_approval(self, mock_policies, mock_audit):
        mock_policies.return_value = {"auto_approve_training": False, "max_auto_spend_usd": 100.0}
        with pytest.raises(GovernanceApprovalRequired, match="Training requires approval"):
            enforce_governance(
                tool="train_lora",
                parameters={"talent_id": "t1"},
                actor_id=USER_A,
                org_id=TENANT_A,
                role="editor",
                source="test",
            )

    @patch("backend.aios.governance.enforcement._audit_decision")
    @patch("backend.aios.governance.enforcement._load_policies")
    def test_publishing_requires_approval(self, mock_policies, mock_audit):
        mock_policies.return_value = {"require_publish_approval": True, "max_auto_spend_usd": 100.0}
        with pytest.raises(GovernanceApprovalRequired, match="Publishing requires approval"):
            enforce_governance(
                tool="schedule_post",
                parameters={"platform": "instagram"},
                actor_id=USER_A,
                org_id=TENANT_A,
                role="editor",
                source="test",
            )

    @patch("backend.aios.governance.enforcement._audit_decision")
    @patch("backend.aios.governance.enforcement._load_policies")
    def test_gpu_launch_requires_approval(self, mock_policies, mock_audit):
        mock_policies.return_value = {"auto_approve_gpu_launch": False, "max_auto_spend_usd": 100.0}
        with pytest.raises(GovernanceApprovalRequired, match="GPU operations require"):
            enforce_governance(
                tool="launch_gpu_worker",
                parameters={"max_price": 1.5},
                actor_id=USER_A,
                org_id=TENANT_A,
                role="admin",
                source="test",
            )


# =============================================================================
# Budget Gate
# =============================================================================


@pytest.mark.unit
class TestBudgetGate:
    """Verify budget exceeding triggers approval."""

    @patch("backend.aios.governance.enforcement._audit_decision")
    @patch("backend.aios.governance.enforcement._load_policies")
    def test_exceeds_budget_requires_approval(self, mock_policies, mock_audit):
        mock_policies.return_value = {"auto_approve_generation": True, "max_auto_spend_usd": 5.0}
        with pytest.raises(GovernanceApprovalRequired, match="exceeds auto-approval limit"):
            enforce_governance(
                tool="generate_image",
                parameters={"prompt": "expensive"},
                actor_id=USER_A,
                org_id=TENANT_A,
                role="editor",
                estimated_cost_usd=10.0,
                source="test",
            )

    @patch("backend.aios.governance.enforcement._audit_decision")
    @patch("backend.aios.governance.enforcement._load_policies")
    def test_within_budget_allowed(self, mock_policies, mock_audit):
        mock_policies.return_value = {"auto_approve_generation": True, "max_auto_spend_usd": 10.0}
        decision = enforce_governance(
            tool="generate_image",
            parameters={"prompt": "cheap"},
            actor_id=USER_A,
            org_id=TENANT_A,
            role="editor",
            estimated_cost_usd=2.0,
            source="test",
        )
        assert decision.outcome == GovernanceOutcome.ALLOW


# =============================================================================
# Arguments Hash (Replay Detection)
# =============================================================================


@pytest.mark.unit
class TestArgumentsHash:
    """Verify arguments hash is stable and unique."""

    def test_same_args_same_hash(self):
        h1 = compute_arguments_hash("generate_image", {"prompt": "test", "model": "flux"})
        h2 = compute_arguments_hash("generate_image", {"prompt": "test", "model": "flux"})
        assert h1 == h2

    def test_different_args_different_hash(self):
        h1 = compute_arguments_hash("generate_image", {"prompt": "test"})
        h2 = compute_arguments_hash("generate_image", {"prompt": "different"})
        assert h1 != h2

    def test_different_tool_different_hash(self):
        h1 = compute_arguments_hash("generate_image", {"prompt": "test"})
        h2 = compute_arguments_hash("train_lora", {"prompt": "test"})
        assert h1 != h2

    def test_order_independent(self):
        """JSON sort_keys makes hash order-independent."""
        h1 = compute_arguments_hash("tool", {"a": 1, "b": 2})
        h2 = compute_arguments_hash("tool", {"b": 2, "a": 1})
        assert h1 == h2


# =============================================================================
# Decision Audit Context
# =============================================================================


@pytest.mark.unit
class TestDecisionAuditContext:
    """Verify governance decisions include full audit information."""

    @patch("backend.aios.governance.enforcement._audit_decision")
    @patch("backend.aios.governance.enforcement._load_policies")
    def test_allow_decision_has_full_context(self, mock_policies, mock_audit):
        mock_policies.return_value = {"auto_approve_generation": True, "max_auto_spend_usd": 100.0}
        decision = enforce_governance(
            tool="generate_image",
            parameters={"prompt": "portrait"},
            actor_id=USER_A,
            org_id=TENANT_A,
            role="editor",
            estimated_cost_usd=0.5,
            source="hermes",
        )
        assert decision.actor_id == USER_A
        assert decision.org_id == TENANT_A
        assert decision.tool == "generate_image"
        assert decision.arguments_hash  # Non-empty
        assert decision.policy_version  # Non-empty
        assert decision.request_id.startswith("gov-")
        assert decision.timestamp  # Non-empty

    @patch("backend.aios.governance.enforcement._audit_decision")
    @patch("backend.aios.governance.enforcement._load_policies")
    def test_decision_to_dict(self, mock_policies, mock_audit):
        mock_policies.return_value = {"auto_approve_generation": True, "max_auto_spend_usd": 100.0}
        decision = enforce_governance(
            tool="generate_image",
            parameters={},
            actor_id=USER_A,
            org_id=TENANT_A,
            role="editor",
            source="mcp",
        )
        d = decision.to_dict()
        assert d["outcome"] == "allow"
        assert d["tool"] == "generate_image"
        assert d["actor_id"] == USER_A
        assert d["org_id"] == TENANT_A


# =============================================================================
# No Bypass — All Governed Tools Require Check
# =============================================================================


@pytest.mark.unit
class TestNoBypass:
    """Verify every side-effecting tool is governed."""

    def test_all_side_effect_tools_in_governed_set(self):
        """Every SIDE_EFFECT tool must be in GOVERNED_TOOLS."""
        for tool, effect in TOOL_EFFECTS.items():
            if effect == ActionEffect.SIDE_EFFECT:
                assert tool in GOVERNED_TOOLS, f"Side-effecting tool '{tool}' missing from GOVERNED_TOOLS"

    def test_is_governed_helper(self):
        assert is_governed("generate_image") is True
        assert is_governed("train_lora") is True
        assert is_governed("search_talent") is False

    def test_is_read_only_helper(self):
        assert is_read_only("search_talent") is True
        assert is_read_only("generate_image") is False

"""Durable approval service tests — Story 042.

Tests prove:
  - High-risk actions create approval records before execution
  - Approval binds to exact argument fingerprint
  - Single-use: consumed token cannot be reused
  - Expired approvals cannot be consumed
  - Argument mutation after approval is detected and blocked
  - Rejected approvals cannot execute
  - Revoked approvals cannot execute
  - Cross-workspace approvals impossible
  - Viewer role cannot approve
  - Double-approval (already consumed) blocked
  - Fingerprint is deterministic and order-independent
"""

import time

import pytest

from backend.aios.governance.durable_approval import (
    HIGH_RISK_ACTIONS,
    ApprovalInvalidError,
    ApprovalRecord,
    ApprovalStatus,
    _reset_store,
    approve,
    consume_authorization,
    create_approval_request,
    fingerprint_arguments,
    get_risk_class,
    reject,
    requires_approval,
    revoke,
    summarize_arguments,
)

TENANT_A = "org-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
TENANT_B = "org-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
USER_A = "user-aaaa"
USER_B = "user-bbbb"


@pytest.fixture(autouse=True)
def clean_store():
    """Reset in-memory store before each test."""
    _reset_store()
    yield
    _reset_store()


# =============================================================================
# Action Classification
# =============================================================================


@pytest.mark.unit
class TestActionClassification:
    """Verify high-risk action classification."""

    def test_train_lora_is_high_risk(self):
        assert requires_approval("train_lora") is True

    def test_launch_gpu_is_high_risk(self):
        assert requires_approval("launch_gpu_worker") is True

    def test_schedule_post_is_high_risk(self):
        assert requires_approval("schedule_post") is True

    def test_search_talent_is_not_high_risk(self):
        assert requires_approval("search_talent") is False

    def test_generate_image_is_not_high_risk(self):
        """Image generation is governed but NOT high-risk (auto-approvable)."""
        assert requires_approval("generate_image") is False


# =============================================================================
# Approval Creation
# =============================================================================


@pytest.mark.unit
class TestApprovalCreation:
    """Verify approval request creation."""

    def test_creates_pending_record(self):
        record = create_approval_request(
            org_id=TENANT_A, user_id=USER_A,
            action="train_lora", arguments={"talent_id": "t1", "steps": 1000},
            estimated_cost_usd=2.50,
        )
        assert record.status == ApprovalStatus.PENDING
        assert record.org_id == TENANT_A
        assert record.user_id == USER_A
        assert record.action == "train_lora"
        assert record.arguments_fingerprint  # Non-empty
        assert record.expires_at > time.time()

    def test_requires_org_id(self):
        with pytest.raises(ValueError, match="org_id"):
            create_approval_request(org_id="", user_id=USER_A, action="train_lora", arguments={})

    def test_requires_user_id(self):
        with pytest.raises(ValueError, match="user_id"):
            create_approval_request(org_id=TENANT_A, user_id="", action="train_lora", arguments={})

    def test_rejects_non_high_risk_action(self):
        with pytest.raises(ValueError, match="not classified"):
            create_approval_request(org_id=TENANT_A, user_id=USER_A, action="search_talent", arguments={})


# =============================================================================
# Argument Fingerprinting
# =============================================================================


@pytest.mark.unit
class TestFingerprinting:
    """Verify argument fingerprint behavior."""

    def test_same_args_same_fingerprint(self):
        fp1 = fingerprint_arguments("train_lora", {"talent_id": "t1", "steps": 1000})
        fp2 = fingerprint_arguments("train_lora", {"talent_id": "t1", "steps": 1000})
        assert fp1 == fp2

    def test_different_args_different_fingerprint(self):
        fp1 = fingerprint_arguments("train_lora", {"talent_id": "t1", "steps": 1000})
        fp2 = fingerprint_arguments("train_lora", {"talent_id": "t1", "steps": 2000})
        assert fp1 != fp2

    def test_order_independent(self):
        fp1 = fingerprint_arguments("x", {"a": 1, "b": 2})
        fp2 = fingerprint_arguments("x", {"b": 2, "a": 1})
        assert fp1 == fp2

    def test_action_name_affects_fingerprint(self):
        fp1 = fingerprint_arguments("train_lora", {"id": "1"})
        fp2 = fingerprint_arguments("delete_model", {"id": "1"})
        assert fp1 != fp2

    def test_summary_redacts_secrets(self):
        summary = summarize_arguments("rotate", {"api_key": "sk_live_abc123", "name": "test"})
        assert "sk_live_abc123" not in summary
        assert "***" in summary


# =============================================================================
# Approval and Execution Token
# =============================================================================


@pytest.mark.unit
class TestApprovalFlow:
    """Verify the approve → consume flow."""

    def test_approve_issues_token(self):
        record = create_approval_request(
            org_id=TENANT_A, user_id=USER_A,
            action="train_lora", arguments={"talent_id": "t1"},
        )
        approved = approve(record.id, USER_B, TENANT_A, role="admin")
        assert approved.status == ApprovalStatus.APPROVED
        assert approved.execution_token is not None
        assert approved.execution_token.startswith("exe-")
        assert approved.approver_id == USER_B

    def test_consume_token_succeeds(self):
        record = create_approval_request(
            org_id=TENANT_A, user_id=USER_A,
            action="train_lora", arguments={"talent_id": "t1"},
        )
        approved = approve(record.id, USER_B, TENANT_A, role="editor")
        consumed = consume_authorization(
            approved.execution_token, "train_lora", {"talent_id": "t1"}, TENANT_A
        )
        assert consumed.status == ApprovalStatus.CONSUMED
        assert consumed.consumed_at is not None


# =============================================================================
# Single-Use Enforcement
# =============================================================================


@pytest.mark.unit
class TestSingleUse:
    """Verify tokens cannot be reused."""

    def test_double_consume_blocked(self):
        record = create_approval_request(
            org_id=TENANT_A, user_id=USER_A,
            action="train_lora", arguments={"talent_id": "t1"},
        )
        approved = approve(record.id, USER_B, TENANT_A, role="editor")
        consume_authorization(approved.execution_token, "train_lora", {"talent_id": "t1"}, TENANT_A)

        # Second consume attempt
        with pytest.raises(ApprovalInvalidError, match="not consumable"):
            consume_authorization(approved.execution_token, "train_lora", {"talent_id": "t1"}, TENANT_A)


# =============================================================================
# Argument Mutation Detection
# =============================================================================


@pytest.mark.unit
class TestArgumentMutation:
    """Verify changed arguments after approval are detected."""

    def test_mutated_args_blocked(self):
        original_args = {"talent_id": "t1", "steps": 1000}
        record = create_approval_request(
            org_id=TENANT_A, user_id=USER_A,
            action="train_lora", arguments=original_args,
        )
        approved = approve(record.id, USER_B, TENANT_A, role="editor")

        # Try to execute with different arguments
        mutated_args = {"talent_id": "t1", "steps": 5000}  # Changed!
        with pytest.raises(ApprovalInvalidError, match="Arguments changed"):
            consume_authorization(approved.execution_token, "train_lora", mutated_args, TENANT_A)


# =============================================================================
# Expiry
# =============================================================================


@pytest.mark.unit
class TestExpiry:
    """Verify expired approvals cannot be consumed."""

    def test_expired_approval_blocked(self):
        record = create_approval_request(
            org_id=TENANT_A, user_id=USER_A,
            action="train_lora", arguments={"talent_id": "t1"},
        )
        approved = approve(record.id, USER_B, TENANT_A, role="editor")

        # Manually expire
        approved.expires_at = time.time() - 10

        with pytest.raises(ApprovalInvalidError, match="expired"):
            consume_authorization(approved.execution_token, "train_lora", {"talent_id": "t1"}, TENANT_A)

    def test_expired_pending_cannot_approve(self):
        record = create_approval_request(
            org_id=TENANT_A, user_id=USER_A,
            action="train_lora", arguments={"talent_id": "t1"},
        )
        # Manually expire
        record.expires_at = time.time() - 10

        with pytest.raises(ApprovalInvalidError, match="expired"):
            approve(record.id, USER_B, TENANT_A, role="editor")


# =============================================================================
# Rejection and Revocation
# =============================================================================


@pytest.mark.unit
class TestRejectionRevocation:
    """Verify rejected/revoked approvals cannot execute."""

    def test_rejected_cannot_approve(self):
        record = create_approval_request(
            org_id=TENANT_A, user_id=USER_A,
            action="train_lora", arguments={"talent_id": "t1"},
        )
        reject(record.id, USER_B, TENANT_A, reason="Too expensive")

        with pytest.raises(ApprovalInvalidError, match="Cannot approve"):
            approve(record.id, USER_B, TENANT_A, role="editor")

    def test_revoked_cannot_consume(self):
        record = create_approval_request(
            org_id=TENANT_A, user_id=USER_A,
            action="train_lora", arguments={"talent_id": "t1"},
        )
        approved = approve(record.id, USER_B, TENANT_A, role="editor")
        revoke(record.id, USER_B, TENANT_A)

        with pytest.raises(ApprovalInvalidError, match="not consumable"):
            consume_authorization(approved.execution_token, "train_lora", {"talent_id": "t1"}, TENANT_A)


# =============================================================================
# Cross-Workspace Isolation
# =============================================================================


@pytest.mark.unit
class TestCrossWorkspace:
    """Verify cross-tenant approval access is impossible."""

    def test_approve_wrong_workspace_fails(self):
        record = create_approval_request(
            org_id=TENANT_A, user_id=USER_A,
            action="train_lora", arguments={"talent_id": "t1"},
        )
        with pytest.raises(ApprovalInvalidError, match="not found"):
            approve(record.id, USER_B, TENANT_B, role="admin")

    def test_consume_wrong_workspace_fails(self):
        record = create_approval_request(
            org_id=TENANT_A, user_id=USER_A,
            action="train_lora", arguments={"talent_id": "t1"},
        )
        approved = approve(record.id, USER_B, TENANT_A, role="editor")

        with pytest.raises(ApprovalInvalidError, match="not found"):
            consume_authorization(approved.execution_token, "train_lora", {"talent_id": "t1"}, TENANT_B)


# =============================================================================
# Role Enforcement
# =============================================================================


@pytest.mark.unit
class TestRoleEnforcement:
    """Verify approver must be editor+."""

    def test_viewer_cannot_approve(self):
        record = create_approval_request(
            org_id=TENANT_A, user_id=USER_A,
            action="train_lora", arguments={"talent_id": "t1"},
        )
        with pytest.raises(ApprovalInvalidError, match="insufficient"):
            approve(record.id, USER_B, TENANT_A, role="viewer")

    def test_editor_can_approve(self):
        record = create_approval_request(
            org_id=TENANT_A, user_id=USER_A,
            action="train_lora", arguments={"talent_id": "t1"},
        )
        approved = approve(record.id, USER_B, TENANT_A, role="editor")
        assert approved.status == ApprovalStatus.APPROVED

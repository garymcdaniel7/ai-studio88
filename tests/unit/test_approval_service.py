"""Unit tests for AIOS Approval Service (Task 14.2).

Tests the governance approval workflow:
    - Creating approvals with 24h expiry
    - Approving pending approvals
    - Rejecting pending approvals
    - Expiring stale approvals
    - Tenant isolation (cross-org access denied)
    - Role enforcement (editor+ required)
    - APPROVAL_REQUIRED_ACTIONS classification
    - Cost threshold approval requirement

Validates: Requirements R30.1, R30.2, R30.3, R30.4, R30.5, R30.6, R30.7

Run with:
    pytest tests/unit/test_approval_service.py -v
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from backend.aios.approval_service import (
    APPROVAL_REQUIRED_ACTIONS,
    COST_APPROVAL_THRESHOLD_USD,
    ApprovalAlreadyResolvedError,
    ApprovalExpiredError,
    ApprovalNotFoundError,
    ApprovalService,
    InsufficientRoleError,
    PendingApproval,
    PendingApprovalStatus,
    _approval_store,
    _reset_store,
)


# =============================================================================
# Fixtures
# =============================================================================

ORG_A = str(uuid4())
ORG_B = str(uuid4())
USER_A = str(uuid4())
USER_B = str(uuid4())


@pytest.fixture(autouse=True)
def clean_store():
    """Reset the in-memory store between tests."""
    _reset_store()
    yield
    _reset_store()


# =============================================================================
# Creation Tests
# =============================================================================


class TestCreateApproval:
    """Tests for ApprovalService.create_approval."""

    @pytest.mark.unit
    def test_creates_pending_approval(self):
        """Creating an approval returns a record in PENDING status."""
        approval = ApprovalService.create_approval(
            org_id=ORG_A,
            user_id=USER_A,
            action_type="delete_permanent",
            estimated_cost_usd=0.0,
            parameters={"resource_id": "abc123"},
        )

        assert approval.status == PendingApprovalStatus.PENDING
        assert approval.org_id == ORG_A
        assert approval.requesting_user_id == USER_A
        assert approval.action_type == "delete_permanent"
        assert approval.parameters == {"resource_id": "abc123"}

    @pytest.mark.unit
    def test_sets_expires_at_24h(self):
        """Approval expires_at is set to approximately 24 hours from creation."""
        approval = ApprovalService.create_approval(
            org_id=ORG_A,
            user_id=USER_A,
            action_type="publish_social",
        )

        expires = datetime.fromisoformat(approval.expires_at)
        created = datetime.fromisoformat(approval.created_at)
        delta = expires - created

        # Should be very close to 24 hours
        assert timedelta(hours=23, minutes=59) <= delta <= timedelta(hours=24, minutes=1)

    @pytest.mark.unit
    def test_stores_estimated_cost(self):
        """Estimated cost is stored on the approval record."""
        approval = ApprovalService.create_approval(
            org_id=ORG_A,
            user_id=USER_A,
            action_type="spend_over_threshold",
            estimated_cost_usd=12.50,
        )

        assert approval.estimated_cost_usd == 12.50

    @pytest.mark.unit
    def test_requires_org_id(self):
        """Empty org_id raises ValueError."""
        with pytest.raises(ValueError, match="org_id"):
            ApprovalService.create_approval(
                org_id="",
                user_id=USER_A,
                action_type="delete_permanent",
            )

    @pytest.mark.unit
    def test_requires_user_id(self):
        """Empty user_id raises ValueError."""
        with pytest.raises(ValueError, match="user_id"):
            ApprovalService.create_approval(
                org_id=ORG_A,
                user_id="",
                action_type="delete_permanent",
            )

    @pytest.mark.unit
    def test_requires_action_type(self):
        """Empty action_type raises ValueError."""
        with pytest.raises(ValueError, match="action_type"):
            ApprovalService.create_approval(
                org_id=ORG_A,
                user_id=USER_A,
                action_type="",
            )


# =============================================================================
# Approve Tests
# =============================================================================


class TestApprove:
    """Tests for ApprovalService.approve."""

    @pytest.mark.unit
    def test_approves_pending(self):
        """Pending approval can be approved by editor+ role."""
        approval = ApprovalService.create_approval(
            org_id=ORG_A,
            user_id=USER_A,
            action_type="delete_permanent",
        )

        result = ApprovalService.approve(
            approval_id=approval.id,
            approver_user_id=USER_B,
            org_id=ORG_A,
            approver_role="admin",
        )

        assert result.status == PendingApprovalStatus.APPROVED
        assert result.resolved_by == USER_B
        assert result.resolved_at is not None

    @pytest.mark.unit
    def test_wrong_org_raises_not_found(self):
        """Cross-tenant access raises ApprovalNotFoundError."""
        approval = ApprovalService.create_approval(
            org_id=ORG_A,
            user_id=USER_A,
            action_type="delete_permanent",
        )

        with pytest.raises(ApprovalNotFoundError):
            ApprovalService.approve(
                approval_id=approval.id,
                approver_user_id=USER_B,
                org_id=ORG_B,
                approver_role="admin",
            )

    @pytest.mark.unit
    def test_nonexistent_id_raises_not_found(self):
        """Non-existent approval ID raises ApprovalNotFoundError."""
        with pytest.raises(ApprovalNotFoundError):
            ApprovalService.approve(
                approval_id="nonexistent-id",
                approver_user_id=USER_A,
                org_id=ORG_A,
                approver_role="admin",
            )

    @pytest.mark.unit
    def test_viewer_cannot_approve(self):
        """Viewer role raises InsufficientRoleError."""
        approval = ApprovalService.create_approval(
            org_id=ORG_A,
            user_id=USER_A,
            action_type="delete_permanent",
        )

        with pytest.raises(InsufficientRoleError):
            ApprovalService.approve(
                approval_id=approval.id,
                approver_user_id=USER_B,
                org_id=ORG_A,
                approver_role="viewer",
            )

    @pytest.mark.unit
    def test_expired_raises_error(self):
        """Expired approval raises ApprovalExpiredError."""
        approval = ApprovalService.create_approval(
            org_id=ORG_A,
            user_id=USER_A,
            action_type="delete_permanent",
        )
        # Force expiry
        approval.expires_at = (datetime.now(UTC) - timedelta(hours=1)).isoformat()

        with pytest.raises(ApprovalExpiredError):
            ApprovalService.approve(
                approval_id=approval.id,
                approver_user_id=USER_B,
                org_id=ORG_A,
                approver_role="admin",
            )

    @pytest.mark.unit
    def test_already_approved_raises_error(self):
        """Approving an already-approved record raises AlreadyResolved."""
        approval = ApprovalService.create_approval(
            org_id=ORG_A,
            user_id=USER_A,
            action_type="delete_permanent",
        )

        ApprovalService.approve(
            approval_id=approval.id,
            approver_user_id=USER_B,
            org_id=ORG_A,
            approver_role="admin",
        )

        with pytest.raises(ApprovalAlreadyResolvedError):
            ApprovalService.approve(
                approval_id=approval.id,
                approver_user_id=USER_B,
                org_id=ORG_A,
                approver_role="admin",
            )

    @pytest.mark.unit
    def test_editor_can_approve(self):
        """Editor role is sufficient to approve."""
        approval = ApprovalService.create_approval(
            org_id=ORG_A,
            user_id=USER_A,
            action_type="publish_social",
        )

        result = ApprovalService.approve(
            approval_id=approval.id,
            approver_user_id=USER_B,
            org_id=ORG_A,
            approver_role="editor",
        )
        assert result.status == PendingApprovalStatus.APPROVED

    @pytest.mark.unit
    def test_owner_can_approve(self):
        """Owner role can approve."""
        approval = ApprovalService.create_approval(
            org_id=ORG_A,
            user_id=USER_A,
            action_type="clone_voice",
        )

        result = ApprovalService.approve(
            approval_id=approval.id,
            approver_user_id=USER_B,
            org_id=ORG_A,
            approver_role="owner",
        )
        assert result.status == PendingApprovalStatus.APPROVED


# =============================================================================
# Reject Tests
# =============================================================================


class TestReject:
    """Tests for ApprovalService.reject."""

    @pytest.mark.unit
    def test_rejects_pending(self):
        """Pending approval can be rejected."""
        approval = ApprovalService.create_approval(
            org_id=ORG_A,
            user_id=USER_A,
            action_type="delete_permanent",
        )

        result = ApprovalService.reject(
            approval_id=approval.id,
            rejecter_user_id=USER_B,
            org_id=ORG_A,
            rejecter_role="admin",
            reason="Not authorized",
        )

        assert result.status == PendingApprovalStatus.REJECTED
        assert result.resolved_by == USER_B
        assert result.rejection_reason == "Not authorized"

    @pytest.mark.unit
    def test_reject_then_approve_raises(self):
        """Cannot approve a rejected approval."""
        approval = ApprovalService.create_approval(
            org_id=ORG_A,
            user_id=USER_A,
            action_type="delete_permanent",
        )

        ApprovalService.reject(
            approval_id=approval.id,
            rejecter_user_id=USER_B,
            org_id=ORG_A,
            rejecter_role="admin",
        )

        with pytest.raises(ApprovalAlreadyResolvedError):
            ApprovalService.approve(
                approval_id=approval.id,
                approver_user_id=USER_B,
                org_id=ORG_A,
                approver_role="admin",
            )

    @pytest.mark.unit
    def test_viewer_cannot_reject(self):
        """Viewer role cannot reject."""
        approval = ApprovalService.create_approval(
            org_id=ORG_A,
            user_id=USER_A,
            action_type="delete_permanent",
        )

        with pytest.raises(InsufficientRoleError):
            ApprovalService.reject(
                approval_id=approval.id,
                rejecter_user_id=USER_B,
                org_id=ORG_A,
                rejecter_role="viewer",
            )

    @pytest.mark.unit
    def test_expired_cannot_be_rejected(self):
        """Expired approval cannot be rejected."""
        approval = ApprovalService.create_approval(
            org_id=ORG_A,
            user_id=USER_A,
            action_type="delete_permanent",
        )
        approval.expires_at = (datetime.now(UTC) - timedelta(hours=1)).isoformat()

        with pytest.raises(ApprovalExpiredError):
            ApprovalService.reject(
                approval_id=approval.id,
                rejecter_user_id=USER_B,
                org_id=ORG_A,
                rejecter_role="admin",
            )


# =============================================================================
# Expiry Tests
# =============================================================================


class TestExpiry:
    """Tests for approval expiry (R30.3)."""

    @pytest.mark.unit
    def test_expire_stale_transitions_expired(self):
        """expire_stale marks past-due approvals as EXPIRED."""
        approval = ApprovalService.create_approval(
            org_id=ORG_A,
            user_id=USER_A,
            action_type="delete_permanent",
        )
        # Force expiry
        approval.expires_at = (datetime.now(UTC) - timedelta(hours=1)).isoformat()

        expired = ApprovalService.expire_stale()

        assert len(expired) == 1
        assert expired[0].id == approval.id
        assert expired[0].status == PendingApprovalStatus.EXPIRED

    @pytest.mark.unit
    def test_expire_stale_ignores_non_pending(self):
        """Already resolved approvals are not re-expired."""
        approval = ApprovalService.create_approval(
            org_id=ORG_A,
            user_id=USER_A,
            action_type="delete_permanent",
        )
        ApprovalService.approve(
            approval_id=approval.id,
            approver_user_id=USER_B,
            org_id=ORG_A,
            approver_role="admin",
        )
        # Force past expiry (should not matter since already approved)
        approval.expires_at = (datetime.now(UTC) - timedelta(hours=1)).isoformat()

        expired = ApprovalService.expire_stale()
        assert len(expired) == 0

    @pytest.mark.unit
    def test_expire_stale_leaves_fresh_pending(self):
        """Approvals not yet expired are left in pending state."""
        approval = ApprovalService.create_approval(
            org_id=ORG_A,
            user_id=USER_A,
            action_type="delete_permanent",
        )
        # expires_at is 24h in the future by default

        expired = ApprovalService.expire_stale()
        assert len(expired) == 0
        assert approval.status == PendingApprovalStatus.PENDING


# =============================================================================
# List Pending Tests
# =============================================================================


class TestListPending:
    """Tests for ApprovalService.list_pending."""

    @pytest.mark.unit
    def test_lists_pending_for_org(self):
        """list_pending returns only pending approvals for the given org."""
        ApprovalService.create_approval(
            org_id=ORG_A,
            user_id=USER_A,
            action_type="delete_permanent",
        )
        ApprovalService.create_approval(
            org_id=ORG_B,
            user_id=USER_B,
            action_type="publish_social",
        )

        pending_a = ApprovalService.list_pending(ORG_A)
        pending_b = ApprovalService.list_pending(ORG_B)

        assert len(pending_a) == 1
        assert len(pending_b) == 1
        assert pending_a[0].action_type == "delete_permanent"
        assert pending_b[0].action_type == "publish_social"

    @pytest.mark.unit
    def test_excludes_expired(self):
        """Expired approvals are not included in pending list."""
        approval = ApprovalService.create_approval(
            org_id=ORG_A,
            user_id=USER_A,
            action_type="delete_permanent",
        )
        approval.expires_at = (datetime.now(UTC) - timedelta(hours=1)).isoformat()

        pending = ApprovalService.list_pending(ORG_A)
        assert len(pending) == 0

    @pytest.mark.unit
    def test_excludes_resolved(self):
        """Approved/rejected approvals are not in pending list."""
        approval = ApprovalService.create_approval(
            org_id=ORG_A,
            user_id=USER_A,
            action_type="delete_permanent",
        )
        ApprovalService.approve(
            approval_id=approval.id,
            approver_user_id=USER_B,
            org_id=ORG_A,
            approver_role="admin",
        )

        pending = ApprovalService.list_pending(ORG_A)
        assert len(pending) == 0


# =============================================================================
# Tenant Isolation Tests (R30.5)
# =============================================================================


class TestTenantIsolation:
    """Tests for cross-tenant isolation."""

    @pytest.mark.unit
    def test_get_wrong_org_returns_none(self):
        """Cannot see another workspace's approval."""
        approval = ApprovalService.create_approval(
            org_id=ORG_A,
            user_id=USER_A,
            action_type="delete_permanent",
        )

        assert ApprovalService.get(approval.id, ORG_B) is None
        assert ApprovalService.get(approval.id, ORG_A) is not None

    @pytest.mark.unit
    def test_approve_wrong_org_raises(self):
        """Cannot approve another workspace's approval."""
        approval = ApprovalService.create_approval(
            org_id=ORG_A,
            user_id=USER_A,
            action_type="delete_permanent",
        )

        with pytest.raises(ApprovalNotFoundError):
            ApprovalService.approve(
                approval_id=approval.id,
                approver_user_id=USER_B,
                org_id=ORG_B,
                approver_role="admin",
            )

    @pytest.mark.unit
    def test_reject_wrong_org_raises(self):
        """Cannot reject another workspace's approval."""
        approval = ApprovalService.create_approval(
            org_id=ORG_A,
            user_id=USER_A,
            action_type="delete_permanent",
        )

        with pytest.raises(ApprovalNotFoundError):
            ApprovalService.reject(
                approval_id=approval.id,
                rejecter_user_id=USER_B,
                org_id=ORG_B,
                rejecter_role="admin",
            )


# =============================================================================
# Action Classification Tests (R30.2)
# =============================================================================


class TestActionClassification:
    """Tests for APPROVAL_REQUIRED_ACTIONS and requires_approval."""

    @pytest.mark.unit
    def test_approval_required_actions_defined(self):
        """All documented high-risk actions are in the set."""
        assert "delete_permanent" in APPROVAL_REQUIRED_ACTIONS
        assert "spend_over_threshold" in APPROVAL_REQUIRED_ACTIONS
        assert "launch_workers_bulk" in APPROVAL_REQUIRED_ACTIONS
        assert "publish_social" in APPROVAL_REQUIRED_ACTIONS
        assert "clone_voice" in APPROVAL_REQUIRED_ACTIONS
        assert "destructive_tool" in APPROVAL_REQUIRED_ACTIONS

    @pytest.mark.unit
    def test_requires_approval_for_classified_actions(self):
        """Actions in APPROVAL_REQUIRED_ACTIONS always require approval."""
        for action in APPROVAL_REQUIRED_ACTIONS:
            assert ApprovalService.requires_approval(action, 0.0) is True

    @pytest.mark.unit
    def test_requires_approval_for_high_cost(self):
        """Actions exceeding cost threshold require approval."""
        assert ApprovalService.requires_approval("generate_image", 10.0) is True
        assert ApprovalService.requires_approval("generate_image", 6.0) is True

    @pytest.mark.unit
    def test_no_approval_for_low_cost_safe_action(self):
        """Low-cost non-classified actions don't require approval."""
        assert ApprovalService.requires_approval("generate_image", 2.0) is False
        assert ApprovalService.requires_approval("list_models", 0.0) is False

    @pytest.mark.unit
    def test_cost_threshold_is_5_usd(self):
        """The cost threshold is $5 as documented."""
        assert COST_APPROVAL_THRESHOLD_USD == 5.0
        # Exactly $5 does not require approval (> not >=)
        assert ApprovalService.requires_approval("generate_image", 5.0) is False
        # Above $5 requires approval
        assert ApprovalService.requires_approval("generate_image", 5.01) is True


# =============================================================================
# Serialization Tests
# =============================================================================


class TestSerialization:
    """Tests for PendingApproval.to_dict."""

    @pytest.mark.unit
    def test_to_dict_includes_all_fields(self):
        """to_dict serializes all relevant fields."""
        approval = ApprovalService.create_approval(
            org_id=ORG_A,
            user_id=USER_A,
            action_type="delete_permanent",
            estimated_cost_usd=3.50,
            parameters={"target": "asset-xyz"},
        )

        data = approval.to_dict()

        assert data["id"] == approval.id
        assert data["org_id"] == ORG_A
        assert data["requesting_user_id"] == USER_A
        assert data["action_type"] == "delete_permanent"
        assert data["estimated_cost_usd"] == 3.50
        assert data["parameters"] == {"target": "asset-xyz"}
        assert data["status"] == "pending"
        assert data["resolved_by"] is None
        assert data["resolved_at"] is None
        assert data["is_expired"] is False

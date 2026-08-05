"""Unit tests for infrastructure authorization (Story 022).

Tests cover:
- Capability model: role→capability mapping correctness
- Role separation: viewer cannot admin, editor cannot destroy
- Cross-tenant isolation: forged resource IDs rejected
- Revoked access: mid-request role downgrade
- Multi-workspace: correct org resolution
- Service identity: callbacks cannot escalate to admin
- Audit events: mutations produce audit trail
- Approval hooks: destructive ops flagged

Run with:
    pytest tests/unit/test_infrastructure_auth.py -v
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from backend.auth import AuthUser
from backend.infrastructure.authorization import (
    APPROVAL_REQUIRED_ACTIONS,
    CAPABILITY_ROLE_MAP,
    ENDPOINT_CAPABILITIES,
    ApprovalCommand,
    InfraAuditEvent,
    InfraCapability,
    TenantContext,
    _audit_log,
    _resolve_tenant_context,
    create_approval_command,
    emit_audit_event,
    get_audit_log,
    require_infra_admin,
    require_infra_capability,
    require_infra_destructive,
    require_infra_operate,
    require_infra_read,
    verify_resource_ownership,
)
from backend.membership import OrgRole


# =============================================================================
# Capability Model Tests
# =============================================================================


class TestCapabilityModel:
    """Verify the capability→role mapping is correct."""

    @pytest.mark.unit
    def test_read_requires_viewer(self):
        assert CAPABILITY_ROLE_MAP[InfraCapability.READ] == OrgRole.VIEWER

    @pytest.mark.unit
    def test_operate_requires_editor(self):
        assert CAPABILITY_ROLE_MAP[InfraCapability.OPERATE] == OrgRole.EDITOR

    @pytest.mark.unit
    def test_admin_requires_admin(self):
        assert CAPABILITY_ROLE_MAP[InfraCapability.ADMIN] == OrgRole.ADMIN

    @pytest.mark.unit
    def test_destructive_requires_owner(self):
        assert CAPABILITY_ROLE_MAP[InfraCapability.DESTRUCTIVE] == OrgRole.OWNER

    @pytest.mark.unit
    def test_all_endpoints_have_capability_mapping(self):
        """Every entry in ENDPOINT_CAPABILITIES maps to a valid capability."""
        for endpoint, cap in ENDPOINT_CAPABILITIES.items():
            assert isinstance(cap, InfraCapability), f"{endpoint} has invalid capability"

    @pytest.mark.unit
    def test_spend_changing_endpoints_require_admin_or_above(self):
        """launch, stop, fleet-add, blacklist all require admin+."""
        spend_endpoints = [
            "launch_worker",
            "stop_worker",
            "add_fleet_worker",
            "add_to_blacklist",
            "update_fleet_config",
            "record_fleet_spend",
        ]
        for ep in spend_endpoints:
            assert ep in ENDPOINT_CAPABILITIES
            cap = ENDPOINT_CAPABILITIES[ep]
            required_role = CAPABILITY_ROLE_MAP[cap]
            assert required_role.has_privilege(OrgRole.ADMIN), (
                f"{ep} should require admin+ but requires {required_role.value}"
            )

    @pytest.mark.unit
    def test_destructive_endpoints_require_owner(self):
        """stop_fleet and save_api_keys require owner."""
        for ep in ["stop_fleet", "save_api_keys"]:
            assert ENDPOINT_CAPABILITIES[ep] == InfraCapability.DESTRUCTIVE

    @pytest.mark.unit
    def test_read_only_endpoints_allow_viewer(self):
        """Status/dashboard endpoints require only viewer."""
        read_endpoints = [
            "get_status",
            "get_dashboard",
            "get_cost_summary",
            "get_reputation",
            "get_fleet_status",
            "list_all_workers",
        ]
        for ep in read_endpoints:
            assert ENDPOINT_CAPABILITIES[ep] == InfraCapability.READ


# =============================================================================
# Role Separation Tests
# =============================================================================


class TestRoleSeparation:
    """Verify that each role can only access its authorized tier."""

    def _make_user(self, role: str, org_id: str = "org-123") -> AuthUser:
        return AuthUser(user_id="user-1", email="u@test.com", org_id=org_id, role=role)

    @pytest.mark.unit
    def test_viewer_can_read(self):
        """Viewer role passes the read capability check."""
        user = self._make_user("viewer")
        dep = require_infra_capability(InfraCapability.READ)
        ctx = dep(user)
        assert ctx.role == OrgRole.VIEWER

    @pytest.mark.unit
    def test_viewer_cannot_operate(self):
        """Viewer role fails the operate capability check."""
        user = self._make_user("viewer")
        dep = require_infra_capability(InfraCapability.OPERATE)
        with pytest.raises(HTTPException) as exc_info:
            dep(user)
        assert exc_info.value.status_code == 403
        assert "editor" in exc_info.value.detail.lower()

    @pytest.mark.unit
    def test_viewer_cannot_admin(self):
        """Viewer role fails the admin capability check."""
        user = self._make_user("viewer")
        dep = require_infra_capability(InfraCapability.ADMIN)
        with pytest.raises(HTTPException) as exc_info:
            dep(user)
        assert exc_info.value.status_code == 403

    @pytest.mark.unit
    def test_viewer_cannot_destroy(self):
        """Viewer role fails the destructive capability check."""
        user = self._make_user("viewer")
        dep = require_infra_capability(InfraCapability.DESTRUCTIVE)
        with pytest.raises(HTTPException) as exc_info:
            dep(user)
        assert exc_info.value.status_code == 403

    @pytest.mark.unit
    def test_editor_can_operate(self):
        """Editor role passes the operate capability check."""
        user = self._make_user("editor")
        dep = require_infra_capability(InfraCapability.OPERATE)
        ctx = dep(user)
        assert ctx.role == OrgRole.EDITOR

    @pytest.mark.unit
    def test_editor_cannot_admin(self):
        """Editor role fails the admin capability check."""
        user = self._make_user("editor")
        dep = require_infra_capability(InfraCapability.ADMIN)
        with pytest.raises(HTTPException) as exc_info:
            dep(user)
        assert exc_info.value.status_code == 403

    @pytest.mark.unit
    def test_admin_can_admin(self):
        """Admin role passes the admin capability check."""
        user = self._make_user("admin")
        dep = require_infra_capability(InfraCapability.ADMIN)
        ctx = dep(user)
        assert ctx.role == OrgRole.ADMIN

    @pytest.mark.unit
    def test_admin_cannot_destroy(self):
        """Admin role fails the destructive capability check."""
        user = self._make_user("admin")
        dep = require_infra_capability(InfraCapability.DESTRUCTIVE)
        with pytest.raises(HTTPException) as exc_info:
            dep(user)
        assert exc_info.value.status_code == 403

    @pytest.mark.unit
    def test_owner_can_destroy(self):
        """Owner role passes the destructive capability check."""
        user = self._make_user("owner")
        dep = require_infra_capability(InfraCapability.DESTRUCTIVE)
        ctx = dep(user)
        assert ctx.role == OrgRole.OWNER

    @pytest.mark.unit
    def test_owner_can_do_everything(self):
        """Owner passes all capability levels."""
        user = self._make_user("owner")
        for cap in InfraCapability:
            dep = require_infra_capability(cap)
            ctx = dep(user)
            assert ctx.role == OrgRole.OWNER


# =============================================================================
# Cross-Tenant Isolation Tests
# =============================================================================


class TestCrossTenantIsolation:
    """Verify resource ownership checks prevent cross-tenant access."""

    @pytest.mark.unit
    def test_same_org_passes(self):
        """Resource in same org as caller is allowed."""
        ctx = TenantContext(user_id="u1", org_id="org-A", role=OrgRole.ADMIN)
        # Should not raise
        verify_resource_ownership(ctx, "org-A", "worker", "w-123")

    @pytest.mark.unit
    def test_different_org_raises_404(self):
        """Resource in different org returns 404 (not 403) to avoid leaking."""
        ctx = TenantContext(user_id="u1", org_id="org-A", role=OrgRole.OWNER)
        with pytest.raises(HTTPException) as exc_info:
            verify_resource_ownership(ctx, "org-B", "worker", "w-456")
        # 404 prevents leaking resource existence
        assert exc_info.value.status_code == 404

    @pytest.mark.unit
    def test_none_org_resource_allowed(self):
        """Shared/system resources with no org_id are accessible."""
        ctx = TenantContext(user_id="u1", org_id="org-A", role=OrgRole.VIEWER)
        # Should not raise for system resources
        verify_resource_ownership(ctx, None, "system_model", "m-001")

    @pytest.mark.unit
    def test_dev_mode_skips_ownership(self):
        """Dev mode context skips ownership check."""
        ctx = TenantContext(user_id="dev-user-local", org_id="dev-org-local", role=OrgRole.OWNER)
        # Should not raise even for different org
        verify_resource_ownership(ctx, "some-other-org", "worker", "w-789")

    @pytest.mark.unit
    def test_forged_workspace_resource_pairing(self):
        """User forges a resource ID from another org — caught by ownership check."""
        ctx = TenantContext(user_id="attacker", org_id="org-evil", role=OrgRole.OWNER)
        with pytest.raises(HTTPException) as exc_info:
            verify_resource_ownership(ctx, "org-victim", "gpu_instance", "instance-42")
        assert exc_info.value.status_code == 404


# =============================================================================
# Tenant Context Resolution Tests
# =============================================================================


class TestTenantContextResolution:
    """Test _resolve_tenant_context edge cases."""

    @pytest.mark.unit
    def test_dev_user_gets_owner_context(self):
        """Dev user (AUTH_DEV_MODE) gets owner role with dev-org-local."""
        user = AuthUser(user_id="dev-user-local", email="dev@localhost", org_id=None, role="owner")
        ctx = _resolve_tenant_context(user)
        assert ctx.org_id == "dev-org-local"
        assert ctx.role == OrgRole.OWNER

    @pytest.mark.unit
    def test_user_without_org_raises_403(self):
        """Authenticated user with no org membership gets 403."""
        user = AuthUser(user_id="real-user", email="u@co.com", org_id=None, role="authenticated")
        with pytest.raises(HTTPException) as exc_info:
            _resolve_tenant_context(user)
        assert exc_info.value.status_code == 403

    @pytest.mark.unit
    def test_unknown_role_defaults_to_viewer(self):
        """Unknown role string maps to viewer (least privilege)."""
        user = AuthUser(
            user_id="u1", email="u@co.com", org_id="org-1", role="unknown_role"
        )
        ctx = _resolve_tenant_context(user)
        assert ctx.role == OrgRole.VIEWER

    @pytest.mark.unit
    def test_valid_role_resolution(self):
        """Standard roles resolve correctly."""
        for role_str in ["owner", "admin", "editor", "viewer"]:
            user = AuthUser(user_id="u1", email="u@co.com", org_id="org-1", role=role_str)
            ctx = _resolve_tenant_context(user)
            assert ctx.role == OrgRole(role_str)


# =============================================================================
# Multi-Workspace Role Tests
# =============================================================================


class TestMultiWorkspace:
    """Test users with different roles in different workspaces."""

    @pytest.mark.unit
    def test_admin_in_one_org_viewer_in_another(self):
        """User is admin in org-A, viewer in org-B — each context is independent."""
        user_org_a = AuthUser(user_id="u1", email="u@co.com", org_id="org-A", role="admin")
        user_org_b = AuthUser(user_id="u1", email="u@co.com", org_id="org-B", role="viewer")

        ctx_a = _resolve_tenant_context(user_org_a)
        ctx_b = _resolve_tenant_context(user_org_b)

        assert ctx_a.org_id == "org-A"
        assert ctx_a.role == OrgRole.ADMIN
        assert ctx_b.org_id == "org-B"
        assert ctx_b.role == OrgRole.VIEWER

    @pytest.mark.unit
    def test_admin_in_org_a_cannot_admin_org_b_resources(self):
        """Admin in org-A cannot access org-B resources."""
        ctx = TenantContext(user_id="u1", org_id="org-A", role=OrgRole.ADMIN)
        with pytest.raises(HTTPException) as exc_info:
            verify_resource_ownership(ctx, "org-B", "worker", "w-999")
        assert exc_info.value.status_code == 404


# =============================================================================
# Revoked Access Tests
# =============================================================================


class TestRevokedAccess:
    """Test behavior when role is downgraded or removed."""

    @pytest.mark.unit
    def test_revoked_to_viewer_cannot_launch(self):
        """User downgraded to viewer during session cannot launch workers."""
        user = AuthUser(user_id="u1", email="u@co.com", org_id="org-1", role="viewer")
        dep = require_infra_capability(InfraCapability.ADMIN)
        with pytest.raises(HTTPException) as exc_info:
            dep(user)
        assert exc_info.value.status_code == 403
        assert "admin" in exc_info.value.detail.lower()

    @pytest.mark.unit
    def test_revoked_completely_no_org(self):
        """User with membership revoked (no org_id) cannot access anything."""
        user = AuthUser(user_id="u1", email="u@co.com", org_id=None, role="authenticated")
        dep = require_infra_capability(InfraCapability.READ)
        with pytest.raises(HTTPException) as exc_info:
            dep(user)
        assert exc_info.value.status_code == 403


# =============================================================================
# Service Identity Tests
# =============================================================================


class TestServiceIdentity:
    """Test that service callbacks cannot escalate to admin."""

    @pytest.mark.unit
    def test_service_callback_with_viewer_role_cannot_admin(self):
        """A service callback authenticating as viewer cannot do admin ops."""
        service_user = AuthUser(
            user_id="service-worker-cb",
            email=None,
            org_id="org-service",
            role="viewer",
        )
        dep = require_infra_capability(InfraCapability.ADMIN)
        with pytest.raises(HTTPException) as exc_info:
            dep(service_user)
        assert exc_info.value.status_code == 403

    @pytest.mark.unit
    def test_unauthenticated_user_no_org_blocked(self):
        """User without org membership cannot access any infrastructure."""
        user = AuthUser(user_id="anon", email=None, org_id=None, role="authenticated")
        for cap in InfraCapability:
            dep = require_infra_capability(cap)
            with pytest.raises(HTTPException) as exc_info:
                dep(user)
            assert exc_info.value.status_code == 403


# =============================================================================
# Audit Event Tests
# =============================================================================


class TestAuditEvents:
    """Test audit event creation and logging."""

    @pytest.mark.unit
    def test_emit_audit_event_appends_to_log(self):
        """emit_audit_event adds to the in-memory log."""
        initial_count = len(_audit_log)
        event = InfraAuditEvent(
            actor_id="user-1",
            org_id="org-1",
            role="admin",
            action="test_action",
            capability="infra:admin",
        )
        emit_audit_event(event)
        assert len(_audit_log) > initial_count
        assert _audit_log[-1].action == "test_action"

    @pytest.mark.unit
    def test_audit_event_serialization(self):
        """Audit events serialize to dict correctly."""
        event = InfraAuditEvent(
            actor_id="u1",
            actor_email="u@test.com",
            org_id="org-1",
            role="admin",
            action="launch_worker",
            capability="infra:admin",
            resource_type="worker",
            resource_id="w-123",
        )
        d = event.to_dict()
        assert d["actor_id"] == "u1"
        assert d["action"] == "launch_worker"
        assert d["resource_id"] == "w-123"
        assert "timestamp" in d

    @pytest.mark.unit
    def test_denied_action_produces_audit_event(self):
        """Authorization denial emits an audit event with result=denied."""
        initial_count = len(_audit_log)
        user = AuthUser(user_id="u1", email="u@co.com", org_id="org-1", role="viewer")
        dep = require_infra_capability(InfraCapability.ADMIN)
        with pytest.raises(HTTPException):
            dep(user)

        # Find the denial event
        new_events = _audit_log[initial_count:]
        denial = next((e for e in new_events if e.result == "denied"), None)
        assert denial is not None
        assert denial.actor_id == "u1"
        assert denial.capability == "infra:admin"
        assert denial.denial_reason is not None

    @pytest.mark.unit
    def test_get_audit_log_returns_recent_first(self):
        """get_audit_log returns events in reverse chronological order."""
        events = get_audit_log(limit=10)
        if len(events) >= 2:
            # More recent events should come first
            assert events[0]["timestamp"] >= events[1]["timestamp"]


# =============================================================================
# Approval Integration Tests
# =============================================================================


class TestApprovalIntegration:
    """Test approval-required action detection and command generation."""

    @pytest.mark.unit
    def test_stop_fleet_requires_approval(self):
        assert "stop_fleet" in APPROVAL_REQUIRED_ACTIONS

    @pytest.mark.unit
    def test_save_api_keys_requires_approval(self):
        assert "save_api_keys" in APPROVAL_REQUIRED_ACTIONS

    @pytest.mark.unit
    def test_launch_worker_does_not_require_approval(self):
        assert "launch_worker" not in APPROVAL_REQUIRED_ACTIONS

    @pytest.mark.unit
    def test_create_approval_command(self):
        """Approval commands have token, expiry, and action details."""
        cmd = create_approval_command(
            action="stop_fleet",
            actor_id="u1",
            org_id="org-1",
            request_data={"confirm": True},
            ttl_seconds=300,
        )
        assert cmd.action == "stop_fleet"
        assert cmd.actor_id == "u1"
        assert cmd.org_id == "org-1"
        assert len(cmd.approval_token) > 0
        assert cmd.expires_at is not None
        assert cmd.approved is False


# =============================================================================
# Convenience Dependency Tests
# =============================================================================


class TestConvenienceDependencies:
    """Test the shortcut dependency functions."""

    @pytest.mark.unit
    def test_require_infra_read_accepts_viewer(self):
        user = AuthUser(user_id="u1", email="u@t.com", org_id="org-1", role="viewer")
        ctx = require_infra_read(user)
        assert ctx.role == OrgRole.VIEWER

    @pytest.mark.unit
    def test_require_infra_operate_rejects_viewer(self):
        user = AuthUser(user_id="u1", email="u@t.com", org_id="org-1", role="viewer")
        with pytest.raises(HTTPException) as exc_info:
            require_infra_operate(user)
        assert exc_info.value.status_code == 403

    @pytest.mark.unit
    def test_require_infra_admin_accepts_owner(self):
        user = AuthUser(user_id="u1", email="u@t.com", org_id="org-1", role="owner")
        ctx = require_infra_admin(user)
        assert ctx.role == OrgRole.OWNER

    @pytest.mark.unit
    def test_require_infra_destructive_rejects_admin(self):
        user = AuthUser(user_id="u1", email="u@t.com", org_id="org-1", role="admin")
        with pytest.raises(HTTPException) as exc_info:
            require_infra_destructive(user)
        assert exc_info.value.status_code == 403


# =============================================================================
# Duplicate Command Tests
# =============================================================================


class TestDuplicateCommands:
    """Test idempotency and duplicate request handling."""

    @pytest.mark.unit
    def test_duplicate_stop_produces_two_audit_events(self):
        """Two stop requests produce two separate audit events (not deduplicated)."""
        initial = len(_audit_log)
        for _ in range(2):
            emit_audit_event(InfraAuditEvent(
                actor_id="u1",
                org_id="org-1",
                role="admin",
                action="stop_worker",
                capability="infra:admin",
            ))
        assert len(_audit_log) - initial == 2


# =============================================================================
# Rate Limiting Tests
# =============================================================================


class TestRateLimiting:
    """Test per-org rate limiting for spend-changing operations."""

    @pytest.mark.unit
    def test_rate_limit_allows_within_threshold(self):
        """Requests within limit are allowed."""
        from backend.infrastructure.authorization import check_spend_rate_limit

        # Use a unique org_id to avoid contamination from other tests
        allowed, reason = check_spend_rate_limit("org-rate-test-ok")
        assert allowed is True
        assert reason == ""

    @pytest.mark.unit
    def test_rate_limit_blocks_after_exceeded(self):
        """Requests exceeding the limit are blocked."""
        from backend.infrastructure.authorization import (
            _RATE_LIMIT_MAX,
            _org_rate_limits,
            check_spend_rate_limit,
        )
        import time

        test_org = "org-rate-test-exceed"
        # Pre-fill with max entries
        now = time.time()
        _org_rate_limits[test_org] = [now - i for i in range(_RATE_LIMIT_MAX)]

        allowed, reason = check_spend_rate_limit(test_org)
        assert allowed is False
        assert "Rate limit exceeded" in reason

        # Cleanup
        del _org_rate_limits[test_org]

    @pytest.mark.unit
    def test_rate_limit_skips_dev_org(self):
        """Dev org is never rate limited."""
        from backend.infrastructure.authorization import check_spend_rate_limit

        allowed, reason = check_spend_rate_limit("dev-org-local")
        assert allowed is True

    @pytest.mark.unit
    def test_require_spend_rate_limit_raises_429(self):
        """require_spend_rate_limit raises 429 when limit exceeded."""
        import time

        from backend.infrastructure.authorization import (
            _RATE_LIMIT_MAX,
            _org_rate_limits,
            require_spend_rate_limit,
        )

        test_org = "org-rate-429-test"
        now = time.time()
        _org_rate_limits[test_org] = [now - i for i in range(_RATE_LIMIT_MAX)]

        ctx = TenantContext(user_id="u1", org_id=test_org, role=OrgRole.ADMIN)
        with pytest.raises(HTTPException) as exc_info:
            require_spend_rate_limit(ctx)
        assert exc_info.value.status_code == 429

        # Cleanup
        del _org_rate_limits[test_org]

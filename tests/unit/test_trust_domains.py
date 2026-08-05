"""Trust Domain Isolation Tests (Story 039).

Proves: domain resolution, deny-by-default, cross-domain denial,
founder isolation, customer cannot escalate, audit on violation.

Run with:
    pytest tests/unit/test_trust_domains.py -v
"""
from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest

from backend.trust_domains import (
    DOMAIN_PERMISSIONS,
    TrustDomain,
    _domain_audit,
    check_memory_access,
    check_prompt_access,
    check_tool_access,
    check_vault_access,
    get_domain_audit,
    resolve_trust_domain,
)

FOUNDER_ID = str(uuid4())
ADMIN_ID = str(uuid4())
EDITOR_ID = str(uuid4())
VIEWER_ID = str(uuid4())
ORG = str(uuid4())


@pytest.fixture(autouse=True)
def clean_and_set_founder():
    _domain_audit.clear()
    with patch("backend.trust_domains.FOUNDER_USER_IDS", frozenset({FOUNDER_ID})):
        yield
    _domain_audit.clear()


# =============================================================================
# Domain Resolution
# =============================================================================


class TestDomainResolution:

    @pytest.mark.unit
    def test_founder_resolved_by_user_id(self):
        resolved = resolve_trust_domain(user_id=FOUNDER_ID, org_id=ORG, role="owner")
        assert resolved.domain == TrustDomain.FOUNDER

    @pytest.mark.unit
    def test_admin_resolved_for_owner_role(self):
        resolved = resolve_trust_domain(user_id=ADMIN_ID, org_id=ORG, role="owner")
        assert resolved.domain == TrustDomain.ADMIN

    @pytest.mark.unit
    def test_admin_resolved_for_admin_role(self):
        resolved = resolve_trust_domain(user_id=ADMIN_ID, org_id=ORG, role="admin")
        assert resolved.domain == TrustDomain.ADMIN

    @pytest.mark.unit
    def test_customer_resolved_for_editor(self):
        resolved = resolve_trust_domain(user_id=EDITOR_ID, org_id=ORG, role="editor")
        assert resolved.domain == TrustDomain.CUSTOMER

    @pytest.mark.unit
    def test_customer_resolved_for_viewer(self):
        resolved = resolve_trust_domain(user_id=VIEWER_ID, org_id=ORG, role="viewer")
        assert resolved.domain == TrustDomain.CUSTOMER

    @pytest.mark.unit
    def test_system_resolved_for_no_user(self):
        resolved = resolve_trust_domain(user_id="", org_id=ORG, role="")
        assert resolved.domain == TrustDomain.SYSTEM

    @pytest.mark.unit
    def test_unknown_role_defaults_to_customer(self):
        resolved = resolve_trust_domain(user_id=str(uuid4()), org_id=ORG, role="unknown")
        assert resolved.domain == TrustDomain.CUSTOMER

    @pytest.mark.unit
    def test_resolution_includes_reason(self):
        resolved = resolve_trust_domain(user_id=FOUNDER_ID, org_id=ORG, role="owner")
        assert "founder" in resolved.resolution_reason


# =============================================================================
# Tool Access — Deny-by-Default
# =============================================================================


class TestToolAccess:

    @pytest.mark.unit
    def test_customer_can_generate_image(self):
        resolved = resolve_trust_domain(user_id=EDITOR_ID, org_id=ORG, role="editor")
        decision = check_tool_access(resolved, "generate_image")
        assert decision.allowed is True

    @pytest.mark.unit
    def test_customer_cannot_launch_gpu(self):
        """Infrastructure tools blocked for customers."""
        resolved = resolve_trust_domain(user_id=EDITOR_ID, org_id=ORG, role="editor")
        decision = check_tool_access(resolved, "launch_gpu")
        assert decision.allowed is False

    @pytest.mark.unit
    def test_customer_cannot_manage_credentials(self):
        resolved = resolve_trust_domain(user_id=EDITOR_ID, org_id=ORG, role="editor")
        decision = check_tool_access(resolved, "manage_credentials")
        assert decision.allowed is False

    @pytest.mark.unit
    def test_admin_can_launch_gpu(self):
        resolved = resolve_trust_domain(user_id=ADMIN_ID, org_id=ORG, role="admin")
        decision = check_tool_access(resolved, "launch_gpu")
        assert decision.allowed is True

    @pytest.mark.unit
    def test_founder_can_destroy_worker(self):
        resolved = resolve_trust_domain(user_id=FOUNDER_ID, org_id=ORG, role="owner")
        decision = check_tool_access(resolved, "destroy_worker")
        assert decision.allowed is True

    @pytest.mark.unit
    def test_admin_cannot_destroy_worker(self):
        """Only founder can destroy workers."""
        resolved = resolve_trust_domain(user_id=ADMIN_ID, org_id=ORG, role="admin")
        decision = check_tool_access(resolved, "destroy_worker")
        assert decision.allowed is False


# =============================================================================
# Prompt Access — Domain Isolation
# =============================================================================


class TestPromptAccess:

    @pytest.mark.unit
    def test_customer_can_use_creative_prompt(self):
        resolved = resolve_trust_domain(user_id=EDITOR_ID, org_id=ORG, role="editor")
        decision = check_prompt_access(resolved, "creative")
        assert decision.allowed is True

    @pytest.mark.unit
    def test_customer_cannot_use_admin_prompt(self):
        resolved = resolve_trust_domain(user_id=EDITOR_ID, org_id=ORG, role="editor")
        decision = check_prompt_access(resolved, "admin")
        assert decision.allowed is False

    @pytest.mark.unit
    def test_customer_cannot_use_founder_ops_prompt(self):
        resolved = resolve_trust_domain(user_id=EDITOR_ID, org_id=ORG, role="editor")
        decision = check_prompt_access(resolved, "founder_ops")
        assert decision.allowed is False

    @pytest.mark.unit
    def test_founder_can_use_all_prompts(self):
        resolved = resolve_trust_domain(user_id=FOUNDER_ID, org_id=ORG, role="owner")
        for prompt in ["creative", "admin", "founder_ops", "infrastructure", "diagnostics"]:
            assert check_prompt_access(resolved, prompt).allowed is True


# =============================================================================
# Memory Scope Isolation
# =============================================================================


class TestMemoryAccess:

    @pytest.mark.unit
    def test_customer_can_access_workspace_memory(self):
        resolved = resolve_trust_domain(user_id=EDITOR_ID, org_id=ORG, role="editor")
        assert check_memory_access(resolved, "workspace").allowed is True

    @pytest.mark.unit
    def test_customer_cannot_access_founder_memory(self):
        resolved = resolve_trust_domain(user_id=EDITOR_ID, org_id=ORG, role="editor")
        assert check_memory_access(resolved, "founder").allowed is False

    @pytest.mark.unit
    def test_customer_cannot_access_infrastructure_memory(self):
        resolved = resolve_trust_domain(user_id=EDITOR_ID, org_id=ORG, role="editor")
        assert check_memory_access(resolved, "infrastructure").allowed is False

    @pytest.mark.unit
    def test_founder_can_access_all_memory(self):
        resolved = resolve_trust_domain(user_id=FOUNDER_ID, org_id=ORG, role="owner")
        for scope in ["workspace", "user", "founder", "system", "infrastructure"]:
            assert check_memory_access(resolved, scope).allowed is True


# =============================================================================
# Vault Isolation
# =============================================================================


class TestVaultAccess:

    @pytest.mark.unit
    def test_customer_can_access_creative_vault(self):
        resolved = resolve_trust_domain(user_id=EDITOR_ID, org_id=ORG, role="editor")
        assert check_vault_access(resolved, "creative").allowed is True

    @pytest.mark.unit
    def test_customer_cannot_access_founder_private_vault(self):
        """Founder private vault NEVER exposed to customers."""
        resolved = resolve_trust_domain(user_id=EDITOR_ID, org_id=ORG, role="editor")
        assert check_vault_access(resolved, "founder_private").allowed is False

    @pytest.mark.unit
    def test_admin_cannot_access_founder_private_vault(self):
        """Even admins cannot access founder private knowledge."""
        resolved = resolve_trust_domain(user_id=ADMIN_ID, org_id=ORG, role="admin")
        assert check_vault_access(resolved, "founder_private").allowed is False

    @pytest.mark.unit
    def test_founder_can_access_private_vault(self):
        resolved = resolve_trust_domain(user_id=FOUNDER_ID, org_id=ORG, role="owner")
        assert check_vault_access(resolved, "founder_private").allowed is True


# =============================================================================
# Cross-Domain Audit
# =============================================================================


class TestCrossDomainAudit:

    @pytest.mark.unit
    def test_denied_tool_produces_audit(self):
        resolved = resolve_trust_domain(user_id=EDITOR_ID, org_id=ORG, role="editor")
        check_tool_access(resolved, "destroy_worker")

        audit = get_domain_audit(org_id=ORG)
        assert len(audit) >= 1
        assert audit[0]["event"] == "cross_domain_denial"
        assert audit[0]["resource_type"] == "tool"
        assert audit[0]["resource_name"] == "destroy_worker"

    @pytest.mark.unit
    def test_denied_vault_produces_audit(self):
        resolved = resolve_trust_domain(user_id=EDITOR_ID, org_id=ORG, role="editor")
        check_vault_access(resolved, "founder_private")

        audit = get_domain_audit(org_id=ORG)
        assert any(e["resource_name"] == "founder_private" for e in audit)

    @pytest.mark.unit
    def test_allowed_access_no_audit(self):
        """Allowed access does NOT produce violation audit entries."""
        _domain_audit.clear()
        resolved = resolve_trust_domain(user_id=EDITOR_ID, org_id=ORG, role="editor")
        check_tool_access(resolved, "generate_image")  # Allowed

        audit = get_domain_audit(org_id=ORG)
        assert len(audit) == 0


# =============================================================================
# Escalation Prevention
# =============================================================================


class TestEscalationPrevention:

    @pytest.mark.unit
    def test_customer_cannot_get_founder_permissions(self):
        """Even if role is spoofed, resolution uses validated auth."""
        # A customer user_id will never match FOUNDER_USER_IDS
        resolved = resolve_trust_domain(user_id=EDITOR_ID, org_id=ORG, role="editor")
        assert resolved.permissions.can_access_founder_knowledge is False
        assert "founder_private" not in resolved.permissions.allowed_vaults
        assert "destroy_worker" not in resolved.permissions.allowed_tools

    @pytest.mark.unit
    def test_admin_cannot_access_founder_knowledge(self):
        """Admin domain explicitly denies founder knowledge access."""
        perms = DOMAIN_PERMISSIONS[TrustDomain.ADMIN]
        assert perms.can_access_founder_knowledge is False
        assert "founder_private" not in perms.allowed_vaults
        assert "founder" not in perms.allowed_memory_scopes

    @pytest.mark.unit
    def test_all_domains_have_permissions_defined(self):
        """Every domain in the enum has a permissions entry."""
        for domain in TrustDomain:
            assert domain in DOMAIN_PERMISSIONS, f"Missing permissions for {domain}"

    @pytest.mark.unit
    def test_customer_infrastructure_visibility_false(self):
        """Customers cannot see infrastructure details."""
        perms = DOMAIN_PERMISSIONS[TrustDomain.CUSTOMER]
        assert perms.can_see_infrastructure is False
        assert perms.can_see_costs is False
        assert perms.can_manage_team is False

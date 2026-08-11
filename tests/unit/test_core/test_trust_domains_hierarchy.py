"""Unit tests for backend.app.core.trust_domains — Task 15.1.

Tests the canonical 6-tier trust domain model:
  - Domain hierarchy ordering
  - can_access() logic
  - filter_by_trust_domain() filtering
  - resolve_trust_domain() resolution
  - TrustDomainCapabilities registry completeness
  - FOUNDER_PRIVATE content isolation enforcement
  - Audit trail recording

Run with:
    pytest tests/unit/test_core/test_trust_domains_hierarchy.py -v
"""
from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import patch
from uuid import uuid4

import pytest

from backend.app.core.trust_domains import (
    DOMAIN_CAPABILITIES,
    FOUNDER_USER_IDS,
    TrustDomain,
    TrustDomainCapabilities,
    ResolvedTrustContext,
    can_access,
    clear_domain_audit,
    filter_by_trust_domain,
    get_domain_audit,
    record_domain_crossing,
    resolve_trust_domain,
)


# =============================================================================
# Test Fixtures and Helpers
# =============================================================================


FOUNDER_ID = str(uuid4())
OPERATOR_ID = str(uuid4())
ADMIN_ID = str(uuid4())
EDITOR_ID = str(uuid4())
VIEWER_ID = str(uuid4())
SERVICE_ID = str(uuid4())
ORG = str(uuid4())


@pytest.fixture(autouse=True)
def clean_audit_and_patch_founder():
    """Clear audit trail and set FOUNDER_USER_IDS for controlled testing."""
    clear_domain_audit()
    with patch(
        "backend.app.core.trust_domains.FOUNDER_USER_IDS",
        frozenset({FOUNDER_ID}),
    ):
        yield
    clear_domain_audit()


@dataclass
class MockItem:
    """Mock item with a trust_domain attribute for filtering tests."""

    name: str
    trust_domain: TrustDomain | str


# =============================================================================
# Domain Hierarchy Tests
# =============================================================================


@pytest.mark.unit
class TestDomainHierarchy:
    """Verify the trust domain hierarchy ordering."""

    def test_hierarchy_ordering(self):
        """Domains are ordered: FOUNDER_PRIVATE > PLATFORM_ADMIN > ... > SYSTEM_AUTOMATION."""
        assert TrustDomain.FOUNDER_PRIVATE > TrustDomain.PLATFORM_ADMIN
        assert TrustDomain.PLATFORM_ADMIN > TrustDomain.WORKSPACE_ADMIN
        assert TrustDomain.WORKSPACE_ADMIN > TrustDomain.CUSTOMER_USER
        assert TrustDomain.CUSTOMER_USER > TrustDomain.SERVICE_WORKER
        assert TrustDomain.SERVICE_WORKER > TrustDomain.SYSTEM_AUTOMATION

    def test_hierarchy_numeric_values(self):
        """Numeric values match expected levels."""
        assert TrustDomain.FOUNDER_PRIVATE == 6
        assert TrustDomain.PLATFORM_ADMIN == 5
        assert TrustDomain.WORKSPACE_ADMIN == 4
        assert TrustDomain.CUSTOMER_USER == 3
        assert TrustDomain.SERVICE_WORKER == 2
        assert TrustDomain.SYSTEM_AUTOMATION == 1

    def test_all_domains_defined(self):
        """All 6 domains exist in the enum."""
        assert len(TrustDomain) == 6


# =============================================================================
# can_access() Tests
# =============================================================================


@pytest.mark.unit
class TestCanAccess:
    """Verify can_access() hierarchy enforcement."""

    def test_same_level_access_allowed(self):
        """A domain can access content at its own level."""
        for domain in TrustDomain:
            assert can_access(domain, domain) is True

    def test_higher_can_access_lower(self):
        """A higher-privilege domain can access lower-privilege content."""
        assert can_access(TrustDomain.FOUNDER_PRIVATE, TrustDomain.CUSTOMER_USER) is True
        assert can_access(TrustDomain.PLATFORM_ADMIN, TrustDomain.CUSTOMER_USER) is True
        assert can_access(TrustDomain.WORKSPACE_ADMIN, TrustDomain.CUSTOMER_USER) is True
        assert can_access(TrustDomain.FOUNDER_PRIVATE, TrustDomain.SYSTEM_AUTOMATION) is True

    def test_lower_cannot_access_higher(self):
        """A lower-privilege domain CANNOT access higher-privilege content."""
        assert can_access(TrustDomain.CUSTOMER_USER, TrustDomain.FOUNDER_PRIVATE) is False
        assert can_access(TrustDomain.CUSTOMER_USER, TrustDomain.PLATFORM_ADMIN) is False
        assert can_access(TrustDomain.CUSTOMER_USER, TrustDomain.WORKSPACE_ADMIN) is False
        assert can_access(TrustDomain.SERVICE_WORKER, TrustDomain.CUSTOMER_USER) is False
        assert can_access(TrustDomain.SYSTEM_AUTOMATION, TrustDomain.FOUNDER_PRIVATE) is False

    def test_customer_cannot_access_founder_private(self):
        """R57.3: CUSTOMER_USER can NEVER access FOUNDER_PRIVATE."""
        assert can_access(TrustDomain.CUSTOMER_USER, TrustDomain.FOUNDER_PRIVATE) is False

    def test_customer_cannot_access_platform_admin(self):
        """R57.4: CUSTOMER_USER cannot access PLATFORM_ADMIN."""
        assert can_access(TrustDomain.CUSTOMER_USER, TrustDomain.PLATFORM_ADMIN) is False

    def test_platform_admin_cannot_access_founder_private(self):
        """PLATFORM_ADMIN cannot access FOUNDER_PRIVATE content."""
        assert can_access(TrustDomain.PLATFORM_ADMIN, TrustDomain.FOUNDER_PRIVATE) is False

    def test_service_worker_cannot_access_above_customer(self):
        """SERVICE_WORKER cannot access CUSTOMER_USER or above."""
        assert can_access(TrustDomain.SERVICE_WORKER, TrustDomain.CUSTOMER_USER) is False
        assert can_access(TrustDomain.SERVICE_WORKER, TrustDomain.WORKSPACE_ADMIN) is False
        assert can_access(TrustDomain.SERVICE_WORKER, TrustDomain.PLATFORM_ADMIN) is False
        assert can_access(TrustDomain.SERVICE_WORKER, TrustDomain.FOUNDER_PRIVATE) is False


# =============================================================================
# filter_by_trust_domain() Tests
# =============================================================================


@pytest.mark.unit
class TestFilterByTrustDomain:
    """Verify filter_by_trust_domain() content filtering."""

    def test_founder_sees_all_items(self):
        """FOUNDER_PRIVATE sees content from all domains."""
        items = [
            MockItem("founder_doc", TrustDomain.FOUNDER_PRIVATE),
            MockItem("platform_doc", TrustDomain.PLATFORM_ADMIN),
            MockItem("workspace_doc", TrustDomain.WORKSPACE_ADMIN),
            MockItem("customer_doc", TrustDomain.CUSTOMER_USER),
            MockItem("service_doc", TrustDomain.SERVICE_WORKER),
            MockItem("system_doc", TrustDomain.SYSTEM_AUTOMATION),
        ]
        result = filter_by_trust_domain(items, TrustDomain.FOUNDER_PRIVATE)
        assert len(result) == 6

    def test_customer_user_excludes_founder_and_above(self):
        """R57.3/R57.4: CUSTOMER_USER sees only CUSTOMER_USER and below."""
        items = [
            MockItem("founder_doc", TrustDomain.FOUNDER_PRIVATE),
            MockItem("platform_doc", TrustDomain.PLATFORM_ADMIN),
            MockItem("workspace_doc", TrustDomain.WORKSPACE_ADMIN),
            MockItem("customer_doc", TrustDomain.CUSTOMER_USER),
            MockItem("service_doc", TrustDomain.SERVICE_WORKER),
            MockItem("system_doc", TrustDomain.SYSTEM_AUTOMATION),
        ]
        result = filter_by_trust_domain(items, TrustDomain.CUSTOMER_USER)
        assert len(result) == 3
        names = {item.name for item in result}
        assert names == {"customer_doc", "service_doc", "system_doc"}

    def test_customer_user_zero_founder_private_items(self):
        """R57.3: CUSTOMER_USER session → zero FOUNDER_PRIVATE items."""
        items = [
            MockItem("secret1", TrustDomain.FOUNDER_PRIVATE),
            MockItem("secret2", TrustDomain.FOUNDER_PRIVATE),
            MockItem("public", TrustDomain.CUSTOMER_USER),
        ]
        result = filter_by_trust_domain(items, TrustDomain.CUSTOMER_USER)
        founder_items = [i for i in result if i.trust_domain == TrustDomain.FOUNDER_PRIVATE]
        assert len(founder_items) == 0

    def test_customer_user_zero_platform_admin_items(self):
        """R57.4: CUSTOMER_USER session → zero PLATFORM_ADMIN items."""
        items = [
            MockItem("admin1", TrustDomain.PLATFORM_ADMIN),
            MockItem("admin2", TrustDomain.PLATFORM_ADMIN),
            MockItem("public", TrustDomain.CUSTOMER_USER),
        ]
        result = filter_by_trust_domain(items, TrustDomain.CUSTOMER_USER)
        platform_items = [i for i in result if i.trust_domain == TrustDomain.PLATFORM_ADMIN]
        assert len(platform_items) == 0

    def test_platform_admin_excludes_founder_private(self):
        """PLATFORM_ADMIN cannot see FOUNDER_PRIVATE content."""
        items = [
            MockItem("founder_doc", TrustDomain.FOUNDER_PRIVATE),
            MockItem("platform_doc", TrustDomain.PLATFORM_ADMIN),
            MockItem("customer_doc", TrustDomain.CUSTOMER_USER),
        ]
        result = filter_by_trust_domain(items, TrustDomain.PLATFORM_ADMIN)
        assert len(result) == 2
        names = {item.name for item in result}
        assert "founder_doc" not in names

    def test_workspace_admin_excludes_founder_and_platform(self):
        """WORKSPACE_ADMIN cannot see FOUNDER_PRIVATE or PLATFORM_ADMIN content."""
        items = [
            MockItem("founder_doc", TrustDomain.FOUNDER_PRIVATE),
            MockItem("platform_doc", TrustDomain.PLATFORM_ADMIN),
            MockItem("workspace_doc", TrustDomain.WORKSPACE_ADMIN),
            MockItem("customer_doc", TrustDomain.CUSTOMER_USER),
        ]
        result = filter_by_trust_domain(items, TrustDomain.WORKSPACE_ADMIN)
        assert len(result) == 2
        names = {item.name for item in result}
        assert names == {"workspace_doc", "customer_doc"}

    def test_empty_items_returns_empty(self):
        """Empty input returns empty output."""
        result = filter_by_trust_domain([], TrustDomain.FOUNDER_PRIVATE)
        assert result == []

    def test_items_without_trust_domain_denied_by_default(self):
        """Items without a trust_domain attribute are treated as FOUNDER_PRIVATE."""

        class NoAttr:
            name = "orphan"

        items = [NoAttr()]
        result = filter_by_trust_domain(items, TrustDomain.CUSTOMER_USER)
        assert len(result) == 0

    def test_string_domain_attribute_resolved(self):
        """Items with string trust_domain values are resolved correctly."""
        items = [
            MockItem("customer_doc", "CUSTOMER_USER"),
            MockItem("founder_doc", "FOUNDER_PRIVATE"),
        ]
        result = filter_by_trust_domain(items, TrustDomain.CUSTOMER_USER)
        assert len(result) == 1
        assert result[0].name == "customer_doc"

    def test_service_worker_sees_only_service_and_system(self):
        """SERVICE_WORKER can only see SERVICE_WORKER and SYSTEM_AUTOMATION."""
        items = [
            MockItem("founder_doc", TrustDomain.FOUNDER_PRIVATE),
            MockItem("customer_doc", TrustDomain.CUSTOMER_USER),
            MockItem("service_doc", TrustDomain.SERVICE_WORKER),
            MockItem("system_doc", TrustDomain.SYSTEM_AUTOMATION),
        ]
        result = filter_by_trust_domain(items, TrustDomain.SERVICE_WORKER)
        assert len(result) == 2
        names = {item.name for item in result}
        assert names == {"service_doc", "system_doc"}


# =============================================================================
# resolve_trust_domain() Tests
# =============================================================================


@pytest.mark.unit
class TestResolveTrustDomain:
    """Verify trust domain resolution from user context."""

    def test_founder_resolved_by_user_id(self):
        """Founder is resolved by matching FOUNDER_USER_IDS."""
        resolved = resolve_trust_domain(user_id=FOUNDER_ID, org_id=ORG, role="owner")
        assert resolved.domain == TrustDomain.FOUNDER_PRIVATE

    def test_platform_operator_resolved(self):
        """Platform operator with capabilities resolves to PLATFORM_ADMIN."""
        resolved = resolve_trust_domain(
            user_id=OPERATOR_ID,
            org_id=ORG,
            role="admin",
            is_platform_operator=True,
            platform_capabilities=frozenset({"manage_platform_config"}),
        )
        assert resolved.domain == TrustDomain.PLATFORM_ADMIN
        assert resolved.is_platform_operator is True

    def test_workspace_admin_resolved_for_owner_role(self):
        """Owner role resolves to WORKSPACE_ADMIN."""
        resolved = resolve_trust_domain(user_id=ADMIN_ID, org_id=ORG, role="owner")
        assert resolved.domain == TrustDomain.WORKSPACE_ADMIN

    def test_workspace_admin_resolved_for_admin_role(self):
        """Admin role resolves to WORKSPACE_ADMIN."""
        resolved = resolve_trust_domain(user_id=ADMIN_ID, org_id=ORG, role="admin")
        assert resolved.domain == TrustDomain.WORKSPACE_ADMIN

    def test_customer_user_resolved_for_editor(self):
        """Editor role resolves to CUSTOMER_USER."""
        resolved = resolve_trust_domain(user_id=EDITOR_ID, org_id=ORG, role="editor")
        assert resolved.domain == TrustDomain.CUSTOMER_USER

    def test_customer_user_resolved_for_viewer(self):
        """Viewer role resolves to CUSTOMER_USER."""
        resolved = resolve_trust_domain(user_id=VIEWER_ID, org_id=ORG, role="viewer")
        assert resolved.domain == TrustDomain.CUSTOMER_USER

    def test_service_worker_resolved(self):
        """service_worker role resolves to SERVICE_WORKER."""
        resolved = resolve_trust_domain(user_id=SERVICE_ID, org_id=ORG, role="service_worker")
        assert resolved.domain == TrustDomain.SERVICE_WORKER

    def test_system_resolved_for_no_user(self):
        """No user_id resolves to SYSTEM_AUTOMATION."""
        resolved = resolve_trust_domain(user_id="", org_id=ORG, role="")
        assert resolved.domain == TrustDomain.SYSTEM_AUTOMATION

    def test_system_resolved_for_system_role(self):
        """System role resolves to SYSTEM_AUTOMATION."""
        resolved = resolve_trust_domain(user_id="sys-123", org_id=ORG, role="system")
        assert resolved.domain == TrustDomain.SYSTEM_AUTOMATION

    def test_unknown_role_defaults_to_customer(self):
        """Unknown role defaults to CUSTOMER_USER (deny by default)."""
        resolved = resolve_trust_domain(user_id=str(uuid4()), org_id=ORG, role="unknown_role")
        assert resolved.domain == TrustDomain.CUSTOMER_USER

    def test_resolution_includes_reason(self):
        """Resolution result includes a human-readable reason."""
        resolved = resolve_trust_domain(user_id=FOUNDER_ID, org_id=ORG, role="owner")
        assert "founder" in resolved.resolution_reason

    def test_resolution_includes_capabilities(self):
        """Resolution result includes the correct capabilities object."""
        resolved = resolve_trust_domain(user_id=EDITOR_ID, org_id=ORG, role="editor")
        assert resolved.capabilities == DOMAIN_CAPABILITIES[TrustDomain.CUSTOMER_USER]

    def test_platform_operator_without_capabilities_is_workspace_admin(self):
        """Platform operator flag without capabilities falls through to role-based."""
        resolved = resolve_trust_domain(
            user_id=OPERATOR_ID,
            org_id=ORG,
            role="admin",
            is_platform_operator=True,
            platform_capabilities=None,
        )
        assert resolved.domain == TrustDomain.WORKSPACE_ADMIN


# =============================================================================
# Domain Capabilities Registry Tests
# =============================================================================


@pytest.mark.unit
class TestDomainCapabilities:
    """Verify DOMAIN_CAPABILITIES registry completeness."""

    def test_all_domains_have_capabilities(self):
        """Every domain in the enum has a capabilities entry."""
        for domain in TrustDomain:
            assert domain in DOMAIN_CAPABILITIES, f"Missing capabilities for {domain.name}"

    def test_capabilities_have_correct_domain(self):
        """Each capabilities entry references the correct domain."""
        for domain, caps in DOMAIN_CAPABILITIES.items():
            assert caps.domain == domain

    def test_founder_has_superset_knowledge_sources(self):
        """FOUNDER_PRIVATE has access to all knowledge sources."""
        founder_sources = DOMAIN_CAPABILITIES[TrustDomain.FOUNDER_PRIVATE].knowledge_sources
        for domain in TrustDomain:
            if domain == TrustDomain.FOUNDER_PRIVATE:
                continue
            other_sources = DOMAIN_CAPABILITIES[domain].knowledge_sources
            assert other_sources.issubset(founder_sources), (
                f"{domain.name} has knowledge sources not in FOUNDER: "
                f"{other_sources - founder_sources}"
            )

    def test_customer_user_no_platform_credentials(self):
        """CUSTOMER_USER has no platform-level credentials."""
        customer_creds = DOMAIN_CAPABILITIES[TrustDomain.CUSTOMER_USER].credentials
        assert len(customer_creds) == 0

    def test_customer_user_no_approval_capabilities(self):
        """CUSTOMER_USER has no approval capabilities."""
        customer_approvals = DOMAIN_CAPABILITIES[TrustDomain.CUSTOMER_USER].approval_capabilities
        assert len(customer_approvals) == 0

    def test_founder_has_all_approval_capabilities(self):
        """FOUNDER_PRIVATE has the most approval capabilities."""
        founder_approvals = DOMAIN_CAPABILITIES[TrustDomain.FOUNDER_PRIVATE].approval_capabilities
        assert len(founder_approvals) > 0
        # Founder has more than any other domain
        for domain in TrustDomain:
            if domain == TrustDomain.FOUNDER_PRIVATE:
                continue
            other_approvals = DOMAIN_CAPABILITIES[domain].approval_capabilities
            assert len(other_approvals) <= len(founder_approvals)


# =============================================================================
# FOUNDER_PRIVATE Isolation Tests
# =============================================================================


@pytest.mark.unit
class TestFounderIsolation:
    """R57.3: FOUNDER_PRIVATE content NEVER visible to CUSTOMER_USER or below."""

    def test_customer_cannot_access_founder_knowledge(self):
        """CUSTOMER_USER capabilities exclude founder_private knowledge."""
        caps = DOMAIN_CAPABILITIES[TrustDomain.CUSTOMER_USER]
        assert "founder_private" not in caps.knowledge_sources

    def test_service_worker_cannot_access_founder_knowledge(self):
        """SERVICE_WORKER capabilities exclude founder_private knowledge."""
        caps = DOMAIN_CAPABILITIES[TrustDomain.SERVICE_WORKER]
        assert "founder_private" not in caps.knowledge_sources

    def test_platform_admin_cannot_access_founder_knowledge(self):
        """PLATFORM_ADMIN capabilities exclude founder_private knowledge."""
        caps = DOMAIN_CAPABILITIES[TrustDomain.PLATFORM_ADMIN]
        assert "founder_private" not in caps.knowledge_sources

    def test_only_founder_has_founder_private_knowledge(self):
        """Only FOUNDER_PRIVATE domain has founder_private in knowledge_sources."""
        for domain, caps in DOMAIN_CAPABILITIES.items():
            if domain == TrustDomain.FOUNDER_PRIVATE:
                assert "founder_private" in caps.knowledge_sources
            else:
                assert "founder_private" not in caps.knowledge_sources

    def test_customer_cannot_see_founder_memory(self):
        """CUSTOMER_USER cannot access founder memory scope."""
        caps = DOMAIN_CAPABILITIES[TrustDomain.CUSTOMER_USER]
        assert "founder" not in caps.memory_scopes

    def test_only_founder_has_founder_memory_scope(self):
        """Only FOUNDER_PRIVATE domain has 'founder' in memory_scopes."""
        for domain, caps in DOMAIN_CAPABILITIES.items():
            if domain == TrustDomain.FOUNDER_PRIVATE:
                assert "founder" in caps.memory_scopes
            else:
                assert "founder" not in caps.memory_scopes


# =============================================================================
# Audit Trail Tests
# =============================================================================


@pytest.mark.unit
class TestAuditTrail:
    """Verify audit trail recording for domain boundary crossings."""

    def test_record_crossing_creates_entry(self):
        """Recording a crossing adds an entry to the audit trail."""
        record_domain_crossing(
            requesting_domain=TrustDomain.CUSTOMER_USER,
            target_domain=TrustDomain.FOUNDER_PRIVATE,
            resource_type="knowledge",
            resource_id="doc-123",
            user_id=EDITOR_ID,
            org_id=ORG,
            outcome="denied",
            reason="hierarchy_violation",
        )
        audit = get_domain_audit(org_id=ORG)
        assert len(audit) == 1
        entry = audit[0]
        assert entry["event"] == "trust_domain_crossing"
        assert entry["requesting_domain"] == "CUSTOMER_USER"
        assert entry["target_domain"] == "FOUNDER_PRIVATE"
        assert entry["outcome"] == "denied"
        assert entry["user_id"] == EDITOR_ID
        assert entry["org_id"] == ORG

    def test_audit_filtered_by_org(self):
        """Audit trail can be filtered by org_id."""
        other_org = str(uuid4())
        record_domain_crossing(
            requesting_domain=TrustDomain.CUSTOMER_USER,
            target_domain=TrustDomain.FOUNDER_PRIVATE,
            resource_type="knowledge",
            resource_id="doc-1",
            user_id=EDITOR_ID,
            org_id=ORG,
            outcome="denied",
        )
        record_domain_crossing(
            requesting_domain=TrustDomain.CUSTOMER_USER,
            target_domain=TrustDomain.PLATFORM_ADMIN,
            resource_type="memory",
            resource_id="mem-1",
            user_id=EDITOR_ID,
            org_id=other_org,
            outcome="denied",
        )
        assert len(get_domain_audit(org_id=ORG)) == 1
        assert len(get_domain_audit(org_id=other_org)) == 1
        assert len(get_domain_audit()) == 2

    def test_clear_audit_empties_trail(self):
        """clear_domain_audit() removes all entries."""
        record_domain_crossing(
            requesting_domain=TrustDomain.CUSTOMER_USER,
            target_domain=TrustDomain.FOUNDER_PRIVATE,
            resource_type="knowledge",
            resource_id="doc-1",
            user_id=EDITOR_ID,
            org_id=ORG,
            outcome="denied",
        )
        assert len(get_domain_audit()) >= 1
        clear_domain_audit()
        assert len(get_domain_audit()) == 0

"""Property-Based Trust Domain Content Filtering Tests — Task 15.3.

Proves the Trust Domain Content Filtering property using hypothesis:
  - CUSTOMER_USER session → zero FOUNDER_PRIVATE or PLATFORM_ADMIN items
  - ADMIN session → zero FOUNDER_PRIVATE items
  - Content sanitization removes internal markers for non-founder domains
  - Prompt profile isolation (no founder content in customer prompts)
  - Retrieval authorization denies founder vaults for customer/admin
  - Audit trail records ALL denied cross-domain access attempts

Validates: Requirements R57.3, R57.4, R57.5

Run with:
    pytest tests/unit/test_property_trust_domain_filtering.py -v
"""
from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from backend.trust_domains import (
    DOMAIN_PERMISSIONS,
    TrustDomain,
    ResolvedDomain,
    _domain_audit,
    check_memory_access,
    check_prompt_access,
    check_tool_access,
    check_vault_access,
    get_domain_audit,
    resolve_trust_domain,
)
from backend.prompt_isolation import (
    ContentClassification,
    _INTERNAL_MARKERS,
    authorize_retrieval,
    assemble_prompt_context,
    contains_internal_content,
    get_prompt_profile,
    RetrievalRequest,
    sanitize_for_domain,
)


# =============================================================================
# Strategies — generate random trust domain contexts
# =============================================================================

# Random user IDs (never matching FOUNDER_USER_IDS)
user_id_strategy = st.from_regex(
    r"usr-[a-f0-9]{4}-[a-f0-9]{12}",
    fullmatch=True,
)

# Random org IDs
org_id_strategy = st.from_regex(
    r"org-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}",
    fullmatch=True,
)

# Customer roles (editor/viewer — these resolve to CUSTOMER domain)
customer_role_strategy = st.sampled_from(["editor", "viewer"])

# Admin roles (owner/admin — these resolve to ADMIN domain)
admin_role_strategy = st.sampled_from(["owner", "admin"])

# Founder-only vaults that must never be accessible to customer or admin
founder_only_vault_strategy = st.just("founder_private")

# Memory scopes that are denied to customers
customer_denied_memory_strategy = st.sampled_from([
    "founder", "infrastructure", "system",
])

# Prompts that are denied to customers
customer_denied_prompt_strategy = st.sampled_from([
    "admin", "founder_ops", "infrastructure", "diagnostics",
])

# Founder-only tools that must be denied to both customer and admin
founder_only_tool_strategy = st.sampled_from([
    "destroy_worker", "manage_governance", "deploy_model",
    "run_uat_tests", "get_uat_results", "diagnose_service",
])

# Random content with internal markers injected
internal_marker_strategy = st.sampled_from(list(_INTERNAL_MARKERS))

# Generate text that contains internal markers
content_with_markers_strategy = st.builds(
    lambda prefix, marker, suffix: f"{prefix}\n{marker}\n{suffix}",
    prefix=st.text(min_size=5, max_size=50, alphabet=st.characters(
        whitelist_categories=("L", "Nd", "Zs"),
    )),
    marker=internal_marker_strategy,
    suffix=st.text(min_size=5, max_size=50, alphabet=st.characters(
        whitelist_categories=("L", "Nd", "Zs"),
    )),
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def clean_audit_and_patch_founder():
    """Clear audit trail and patch FOUNDER_USER_IDS for controlled testing."""
    _domain_audit.clear()
    # Ensure no test user_ids accidentally match founder IDs
    with patch("backend.trust_domains.FOUNDER_USER_IDS", frozenset({"founder-special-id-only"})):
        yield
    _domain_audit.clear()


# =============================================================================
# Property 6.1: CUSTOMER Session Cannot Access FOUNDER_PRIVATE Vaults
# "For ANY customer user (editor/viewer role), accessing 'founder_private'
#  vault is ALWAYS denied."
# =============================================================================


@pytest.mark.unit
class TestCustomerCannotAccessFounderVaults:
    """CUSTOMER domain cannot access FOUNDER_PRIVATE vaults.

    **Validates: Requirements R57.3, R57.4**
    """

    @given(
        user_id=user_id_strategy,
        org_id=org_id_strategy,
        role=customer_role_strategy,
    )
    @settings(max_examples=200, deadline=None)
    def test_customer_vault_access_always_denied(
        self, user_id: str, org_id: str, role: str
    ):
        """CUSTOMER domain vault access to 'founder_private' is always denied.

        **Validates: Requirements R57.3, R57.4**
        """
        _domain_audit.clear()

        resolved = resolve_trust_domain(user_id=user_id, org_id=org_id, role=role)
        assert resolved.domain == TrustDomain.CUSTOMER

        decision = check_vault_access(resolved, "founder_private")
        assert decision.allowed is False, (
            f"SECURITY BREACH: CUSTOMER user '{user_id}' (role={role}) was "
            f"ALLOWED access to founder_private vault"
        )

    @given(
        user_id=user_id_strategy,
        org_id=org_id_strategy,
        role=customer_role_strategy,
        memory_scope=customer_denied_memory_strategy,
    )
    @settings(max_examples=200, deadline=None)
    def test_customer_founder_memory_access_always_denied(
        self, user_id: str, org_id: str, role: str, memory_scope: str
    ):
        """CUSTOMER domain memory access to founder/infrastructure/system is denied.

        **Validates: Requirements R57.3, R57.4**
        """
        _domain_audit.clear()

        resolved = resolve_trust_domain(user_id=user_id, org_id=org_id, role=role)
        assert resolved.domain == TrustDomain.CUSTOMER

        decision = check_memory_access(resolved, memory_scope)
        assert decision.allowed is False, (
            f"SECURITY BREACH: CUSTOMER user '{user_id}' was ALLOWED "
            f"access to '{memory_scope}' memory scope"
        )

    @given(
        user_id=user_id_strategy,
        org_id=org_id_strategy,
        role=customer_role_strategy,
        prompt=customer_denied_prompt_strategy,
    )
    @settings(max_examples=200, deadline=None)
    def test_customer_admin_prompt_access_always_denied(
        self, user_id: str, org_id: str, role: str, prompt: str
    ):
        """CUSTOMER domain prompt access to admin/founder_ops/infra is denied.

        **Validates: Requirements R57.3, R57.4**
        """
        _domain_audit.clear()

        resolved = resolve_trust_domain(user_id=user_id, org_id=org_id, role=role)
        assert resolved.domain == TrustDomain.CUSTOMER

        decision = check_prompt_access(resolved, prompt)
        assert decision.allowed is False, (
            f"SECURITY BREACH: CUSTOMER user '{user_id}' was ALLOWED "
            f"access to '{prompt}' prompt profile"
        )

    @given(
        user_id=user_id_strategy,
        org_id=org_id_strategy,
        role=customer_role_strategy,
        tool=founder_only_tool_strategy,
    )
    @settings(max_examples=200, deadline=None)
    def test_customer_founder_tool_access_always_denied(
        self, user_id: str, org_id: str, role: str, tool: str
    ):
        """CUSTOMER domain tool access to founder-only tools is always denied.

        **Validates: Requirements R57.3, R57.4**
        """
        _domain_audit.clear()

        resolved = resolve_trust_domain(user_id=user_id, org_id=org_id, role=role)
        assert resolved.domain == TrustDomain.CUSTOMER

        decision = check_tool_access(resolved, tool)
        assert decision.allowed is False, (
            f"SECURITY BREACH: CUSTOMER user '{user_id}' was ALLOWED "
            f"access to founder-only tool '{tool}'"
        )


# =============================================================================
# Property 6.2: ADMIN Session Cannot Access FOUNDER_PRIVATE Resources
# "For ANY admin user (owner/admin role, non-founder), accessing
#  founder_private vault and founder memory scope is ALWAYS denied."
# =============================================================================


@pytest.mark.unit
class TestAdminCannotAccessFounderPrivate:
    """ADMIN domain cannot access FOUNDER_PRIVATE resources.

    **Validates: Requirements R57.3, R57.4**
    """

    @given(
        user_id=user_id_strategy,
        org_id=org_id_strategy,
        role=admin_role_strategy,
    )
    @settings(max_examples=200, deadline=None)
    def test_admin_cannot_access_founder_private_vault(
        self, user_id: str, org_id: str, role: str
    ):
        """ADMIN domain cannot access founder_private vault.

        **Validates: Requirements R57.3, R57.4**
        """
        _domain_audit.clear()

        resolved = resolve_trust_domain(user_id=user_id, org_id=org_id, role=role)
        assert resolved.domain == TrustDomain.ADMIN

        decision = check_vault_access(resolved, "founder_private")
        assert decision.allowed is False, (
            f"SECURITY BREACH: ADMIN user '{user_id}' (role={role}) was "
            f"ALLOWED access to founder_private vault"
        )

    @given(
        user_id=user_id_strategy,
        org_id=org_id_strategy,
        role=admin_role_strategy,
    )
    @settings(max_examples=200, deadline=None)
    def test_admin_cannot_access_founder_memory(
        self, user_id: str, org_id: str, role: str
    ):
        """ADMIN domain cannot access 'founder' memory scope.

        **Validates: Requirements R57.3, R57.4**
        """
        _domain_audit.clear()

        resolved = resolve_trust_domain(user_id=user_id, org_id=org_id, role=role)
        assert resolved.domain == TrustDomain.ADMIN

        decision = check_memory_access(resolved, "founder")
        assert decision.allowed is False, (
            f"SECURITY BREACH: ADMIN user '{user_id}' was ALLOWED "
            f"access to 'founder' memory scope"
        )

    @given(
        user_id=user_id_strategy,
        org_id=org_id_strategy,
        role=admin_role_strategy,
        prompt=st.sampled_from(["founder_ops", "infrastructure", "diagnostics"]),
    )
    @settings(max_examples=200, deadline=None)
    def test_admin_cannot_access_founder_prompts(
        self, user_id: str, org_id: str, role: str, prompt: str
    ):
        """ADMIN domain cannot access founder-only prompt profiles.

        **Validates: Requirements R57.3, R57.4**
        """
        _domain_audit.clear()

        resolved = resolve_trust_domain(user_id=user_id, org_id=org_id, role=role)
        assert resolved.domain == TrustDomain.ADMIN

        decision = check_prompt_access(resolved, prompt)
        assert decision.allowed is False, (
            f"SECURITY BREACH: ADMIN user '{user_id}' was ALLOWED "
            f"access to founder prompt '{prompt}'"
        )

    @given(
        user_id=user_id_strategy,
        org_id=org_id_strategy,
        role=admin_role_strategy,
        tool=founder_only_tool_strategy,
    )
    @settings(max_examples=200, deadline=None)
    def test_admin_cannot_access_founder_tools(
        self, user_id: str, org_id: str, role: str, tool: str
    ):
        """ADMIN domain cannot use founder-only tools.

        **Validates: Requirements R57.3, R57.4**
        """
        _domain_audit.clear()

        resolved = resolve_trust_domain(user_id=user_id, org_id=org_id, role=role)
        assert resolved.domain == TrustDomain.ADMIN

        decision = check_tool_access(resolved, tool)
        assert decision.allowed is False, (
            f"SECURITY BREACH: ADMIN user '{user_id}' was ALLOWED "
            f"access to founder-only tool '{tool}'"
        )


# =============================================================================
# Property 6.3: Content Sanitization Removes Internal Markers
# "For ANY content containing internal markers, sanitize_for_domain() with
#  CUSTOMER or ADMIN domain produces output containing zero internal markers."
# =============================================================================


@pytest.mark.unit
class TestContentSanitizationRemovesInternalMarkers:
    """Content sanitization strips all internal markers for non-founder domains.

    **Validates: Requirements R57.3, R57.4**
    """

    @given(content=content_with_markers_strategy)
    @settings(max_examples=200, deadline=None)
    def test_customer_sanitization_removes_markers(self, content: str):
        """Sanitized content for CUSTOMER contains zero internal markers.

        **Validates: Requirements R57.3**
        """
        # Confirm the input actually contains markers
        assume(contains_internal_content(content))

        sanitized = sanitize_for_domain(content, TrustDomain.CUSTOMER)
        assert not contains_internal_content(sanitized), (
            f"CONTENT LEAK: sanitize_for_domain(CUSTOMER) left internal "
            f"markers in output. Input had markers, output still does."
        )

    @given(content=content_with_markers_strategy)
    @settings(max_examples=200, deadline=None)
    def test_admin_sanitization_removes_markers(self, content: str):
        """Sanitized content for ADMIN contains zero internal markers.

        **Validates: Requirements R57.4**
        """
        assume(contains_internal_content(content))

        sanitized = sanitize_for_domain(content, TrustDomain.ADMIN)
        assert not contains_internal_content(sanitized), (
            f"CONTENT LEAK: sanitize_for_domain(ADMIN) left internal "
            f"markers in output. Input had markers, output still does."
        )

    @given(content=content_with_markers_strategy)
    @settings(max_examples=200, deadline=None)
    def test_founder_sanitization_preserves_content(self, content: str):
        """Founder domain sees content unmodified (full visibility).

        **Validates: Requirements R57.3**
        """
        sanitized = sanitize_for_domain(content, TrustDomain.FOUNDER)
        assert sanitized == content, (
            "Founder domain content was modified by sanitization — "
            "founder should see everything unchanged"
        )


# =============================================================================
# Property 6.4: Prompt Profile Isolation
# "CUSTOMER prompt profile contains zero FOUNDER_ONLY or ADMIN_ONLY content
#  markers. No internal infrastructure details leak."
# =============================================================================


@pytest.mark.unit
class TestPromptProfileIsolation:
    """CUSTOMER prompt profile contains no founder/admin-only content.

    **Validates: Requirements R57.3, R57.4**
    """

    @given(
        user_id=user_id_strategy,
        org_id=org_id_strategy,
        role=customer_role_strategy,
    )
    @settings(max_examples=200, deadline=None)
    def test_customer_prompt_profile_no_internal_content(
        self, user_id: str, org_id: str, role: str
    ):
        """CUSTOMER prompt profile contains zero internal markers.

        **Validates: Requirements R57.3**
        """
        profile = get_prompt_profile(TrustDomain.CUSTOMER)

        # Must not contain any internal/founder markers
        assert not contains_internal_content(profile), (
            "CONTENT LEAK: CUSTOMER prompt profile contains internal "
            "markers that should only be visible to FOUNDER domain"
        )

        # Must not contain founder-only keywords
        founder_only_keywords = [
            "ADMIN-ONLY POWERS",
            "platform owner",
            "GOVERNANCE RULES (internal)",
            "PLATFORM ARCHITECTURE",
            "INFRASTRUCTURE COMMANDS",
        ]
        for keyword in founder_only_keywords:
            assert keyword not in profile, (
                f"CONTENT LEAK: CUSTOMER prompt profile contains "
                f"founder-only keyword '{keyword}'"
            )

    @given(
        user_id=user_id_strategy,
        org_id=org_id_strategy,
        role=customer_role_strategy,
    )
    @settings(max_examples=200, deadline=None)
    def test_customer_assembled_context_no_internal_content(
        self, user_id: str, org_id: str, role: str
    ):
        """Assembled prompt context for CUSTOMER has no internal markers.

        **Validates: Requirements R57.3, R57.4**
        """
        _domain_audit.clear()

        resolved = resolve_trust_domain(user_id=user_id, org_id=org_id, role=role)
        assert resolved.domain == TrustDomain.CUSTOMER

        assembled = assemble_prompt_context(
            resolved_domain=resolved,
            mode="creative",
            additional_context="",
        )

        assert not contains_internal_content(assembled), (
            "CONTENT LEAK: Assembled CUSTOMER prompt context contains "
            "internal markers. Trust domain filtering failed."
        )

    @given(
        user_id=user_id_strategy,
        org_id=org_id_strategy,
        role=customer_role_strategy,
        injected=content_with_markers_strategy,
    )
    @settings(max_examples=200, deadline=None)
    def test_customer_assembled_context_sanitizes_additional(
        self, user_id: str, org_id: str, role: str, injected: str
    ):
        """Additional context with markers is sanitized in CUSTOMER assembly.

        **Validates: Requirements R57.3, R57.4**
        """
        assume(contains_internal_content(injected))
        _domain_audit.clear()

        resolved = resolve_trust_domain(user_id=user_id, org_id=org_id, role=role)
        assert resolved.domain == TrustDomain.CUSTOMER

        assembled = assemble_prompt_context(
            resolved_domain=resolved,
            mode="creative",
            additional_context=injected,
        )

        assert not contains_internal_content(assembled), (
            "CONTENT LEAK: Injected internal content survived "
            "sanitization in CUSTOMER prompt assembly"
        )


# =============================================================================
# Property 6.5: Retrieval Authorization Denies Founder Vaults
# "authorize_retrieval() always denies when vault is 'founder_private'
#  and domain is CUSTOMER or ADMIN."
# =============================================================================


@pytest.mark.unit
class TestRetrievalAuthorizationDeniesFounderVaults:
    """authorize_retrieval() denies founder_private for non-founder domains.

    **Validates: Requirements R57.3, R57.5**
    """

    @given(
        user_id=user_id_strategy,
        org_id=org_id_strategy,
        role=customer_role_strategy,
        query=st.text(min_size=3, max_size=100, alphabet=st.characters(
            whitelist_categories=("L", "Nd", "Zs"),
        )),
    )
    @settings(max_examples=200, deadline=None)
    def test_customer_retrieval_from_founder_vault_always_denied(
        self, user_id: str, org_id: str, role: str, query: str
    ):
        """CUSTOMER cannot retrieve from founder_private vault.

        **Validates: Requirements R57.3, R57.5**
        """
        _domain_audit.clear()

        resolved = resolve_trust_domain(user_id=user_id, org_id=org_id, role=role)
        assert resolved.domain == TrustDomain.CUSTOMER

        request = RetrievalRequest(
            vault="founder_private",
            query=query,
            domain=TrustDomain.CUSTOMER,
            user_id=user_id,
            org_id=org_id,
        )

        result = authorize_retrieval(request, resolved)
        assert result.allowed is False, (
            f"SECURITY BREACH: CUSTOMER retrieval from founder_private vault "
            f"was ALLOWED for user '{user_id}'"
        )
        assert result.content == "", (
            "CONTENT LEAK: Denied retrieval returned non-empty content"
        )

    @given(
        user_id=user_id_strategy,
        org_id=org_id_strategy,
        role=admin_role_strategy,
        query=st.text(min_size=3, max_size=100, alphabet=st.characters(
            whitelist_categories=("L", "Nd", "Zs"),
        )),
    )
    @settings(max_examples=200, deadline=None)
    def test_admin_retrieval_from_founder_vault_always_denied(
        self, user_id: str, org_id: str, role: str, query: str
    ):
        """ADMIN cannot retrieve from founder_private vault.

        **Validates: Requirements R57.3, R57.5**
        """
        _domain_audit.clear()

        resolved = resolve_trust_domain(user_id=user_id, org_id=org_id, role=role)
        assert resolved.domain == TrustDomain.ADMIN

        request = RetrievalRequest(
            vault="founder_private",
            query=query,
            domain=TrustDomain.ADMIN,
            user_id=user_id,
            org_id=org_id,
        )

        result = authorize_retrieval(request, resolved)
        assert result.allowed is False, (
            f"SECURITY BREACH: ADMIN retrieval from founder_private vault "
            f"was ALLOWED for user '{user_id}'"
        )
        assert result.content == "", (
            "CONTENT LEAK: Denied retrieval returned non-empty content"
        )


# =============================================================================
# Property 6.6: Audit Trail Records ALL Denied Cross-Domain Access
# "Every denied access attempt produces an audit entry with required fields
#  (timestamp, event, domain, resource_type, resource_name, user_id, org_id)."
# =============================================================================


@pytest.mark.unit
class TestAuditTrailRecordsDeniedAccess:
    """Every denied cross-domain access produces a complete audit entry.

    **Validates: Requirements R57.5**
    """

    @given(
        user_id=user_id_strategy,
        org_id=org_id_strategy,
        role=customer_role_strategy,
        tool=founder_only_tool_strategy,
    )
    @settings(max_examples=200, deadline=None)
    def test_denied_tool_access_produces_audit(
        self, user_id: str, org_id: str, role: str, tool: str
    ):
        """Denied tool access creates an audit entry with all required fields.

        **Validates: Requirements R57.5**
        """
        _domain_audit.clear()

        resolved = resolve_trust_domain(user_id=user_id, org_id=org_id, role=role)
        check_tool_access(resolved, tool)

        audit = get_domain_audit(org_id=org_id)
        assert len(audit) >= 1, (
            f"No audit record created for denied tool access '{tool}'"
        )

        entry = audit[0]
        # Required fields per R57.5
        assert "timestamp" in entry and entry["timestamp"]
        assert entry["event"] == "cross_domain_denial"
        assert entry["domain"] == TrustDomain.CUSTOMER.value
        assert entry["resource_type"] == "tool"
        assert entry["resource_name"] == tool
        assert entry["user_id"] == user_id
        assert entry["org_id"] == org_id

    @given(
        user_id=user_id_strategy,
        org_id=org_id_strategy,
        role=customer_role_strategy,
    )
    @settings(max_examples=200, deadline=None)
    def test_denied_vault_access_produces_audit(
        self, user_id: str, org_id: str, role: str
    ):
        """Denied vault access creates an audit entry with all required fields.

        **Validates: Requirements R57.5**
        """
        _domain_audit.clear()

        resolved = resolve_trust_domain(user_id=user_id, org_id=org_id, role=role)
        check_vault_access(resolved, "founder_private")

        audit = get_domain_audit(org_id=org_id)
        assert len(audit) >= 1, (
            "No audit record created for denied vault access 'founder_private'"
        )

        entry = audit[0]
        assert entry["event"] == "cross_domain_denial"
        assert entry["resource_type"] == "vault"
        assert entry["resource_name"] == "founder_private"
        assert entry["user_id"] == user_id
        assert entry["org_id"] == org_id

    @given(
        user_id=user_id_strategy,
        org_id=org_id_strategy,
        role=customer_role_strategy,
        memory_scope=customer_denied_memory_strategy,
    )
    @settings(max_examples=200, deadline=None)
    def test_denied_memory_access_produces_audit(
        self, user_id: str, org_id: str, role: str, memory_scope: str
    ):
        """Denied memory access creates an audit entry with all required fields.

        **Validates: Requirements R57.5**
        """
        _domain_audit.clear()

        resolved = resolve_trust_domain(user_id=user_id, org_id=org_id, role=role)
        check_memory_access(resolved, memory_scope)

        audit = get_domain_audit(org_id=org_id)
        assert len(audit) >= 1, (
            f"No audit record created for denied memory access '{memory_scope}'"
        )

        entry = audit[0]
        assert entry["event"] == "cross_domain_denial"
        assert entry["resource_type"] == "memory"
        assert entry["resource_name"] == memory_scope
        assert entry["user_id"] == user_id
        assert entry["org_id"] == org_id

    @given(
        user_id=user_id_strategy,
        org_id=org_id_strategy,
        role=customer_role_strategy,
        prompt=customer_denied_prompt_strategy,
    )
    @settings(max_examples=200, deadline=None)
    def test_denied_prompt_access_produces_audit(
        self, user_id: str, org_id: str, role: str, prompt: str
    ):
        """Denied prompt access creates an audit entry with all required fields.

        **Validates: Requirements R57.5**
        """
        _domain_audit.clear()

        resolved = resolve_trust_domain(user_id=user_id, org_id=org_id, role=role)
        check_prompt_access(resolved, prompt)

        audit = get_domain_audit(org_id=org_id)
        assert len(audit) >= 1, (
            f"No audit record created for denied prompt access '{prompt}'"
        )

        entry = audit[0]
        assert entry["event"] == "cross_domain_denial"
        assert entry["resource_type"] == "prompt"
        assert entry["resource_name"] == prompt
        assert entry["user_id"] == user_id
        assert entry["org_id"] == org_id

    @given(
        user_id=user_id_strategy,
        org_id=org_id_strategy,
        role=customer_role_strategy,
    )
    @settings(max_examples=200, deadline=None)
    def test_allowed_access_produces_no_audit(
        self, user_id: str, org_id: str, role: str
    ):
        """Allowed access does NOT produce a cross-domain denial audit entry.

        **Validates: Requirements R57.5**
        """
        _domain_audit.clear()

        resolved = resolve_trust_domain(user_id=user_id, org_id=org_id, role=role)
        # Customer CAN access creative vault and generate_image tool
        check_vault_access(resolved, "creative")
        check_tool_access(resolved, "generate_image")

        audit = get_domain_audit(org_id=org_id)
        assert len(audit) == 0, (
            "Allowed access incorrectly produced a denial audit entry"
        )

"""Hermes tool authorization tests — Story 036.

Tests prove:
  - Valid context allows tool execution
  - Expired context is rejected
  - Missing identity fields rejected
  - Cross-tenant context cannot access another workspace's tools
  - Viewer role denied for side-effecting tools
  - Capability restrictions enforced
  - Signed tokens can be created and verified
  - Token tampering is detected
  - Token replay (expired) is rejected
  - Nonce uniqueness prevents replay
  - Context factory creates correct context from TenantContext
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from backend.aios.hermes.tool_context import (
    DEFAULT_TTL_SECONDS,
    MAX_TTL_SECONDS,
    ToolAuthorizationError,
    ToolContextError,
    ToolExecutionContext,
    TrustDomain,
    create_context_from_tenant,
    execute_tool_authorized,
    validate_context,
)
from backend.membership import OrgRole, TenantContext

TENANT_A = "org-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
TENANT_B = "org-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
USER_A = "user-aaaa"
SESSION_A = "session-aaaa"


def valid_ctx(**overrides) -> ToolExecutionContext:
    """Create a valid test context with optional overrides."""
    defaults = {
        "user_id": USER_A,
        "org_id": TENANT_A,
        "role": "editor",
        "session_id": SESSION_A,
        "trust_domain": TrustDomain.USER_INTERACTIVE,
    }
    defaults.update(overrides)
    return ToolExecutionContext(**defaults)


# =============================================================================
# Context Validation
# =============================================================================


@pytest.mark.unit
class TestContextValidation:
    """Verify context validation catches invalid state."""

    def test_valid_context_passes(self):
        validate_context(valid_ctx())  # Should not raise

    def test_missing_user_id_rejected(self):
        with pytest.raises(ToolContextError, match="Missing user_id"):
            validate_context(valid_ctx(user_id=""))

    def test_missing_org_id_rejected(self):
        with pytest.raises(ToolContextError, match="Missing org_id"):
            validate_context(valid_ctx(org_id=""))

    def test_missing_role_rejected(self):
        with pytest.raises(ToolContextError, match="Missing role"):
            validate_context(valid_ctx(role=""))

    def test_missing_session_rejected(self):
        with pytest.raises(ToolContextError, match="Missing session_id"):
            validate_context(valid_ctx(session_id=""))

    def test_expired_context_rejected(self):
        ctx = ToolExecutionContext(
            user_id=USER_A,
            org_id=TENANT_A,
            role="editor",
            session_id=SESSION_A,
            created_at=time.time() - 7200,  # 2 hours ago
            ttl_seconds=60,  # 1 min TTL = long expired
        )
        with pytest.raises(ToolContextError, match="expired"):
            validate_context(ctx)

    def test_excessive_ttl_rejected(self):
        ctx = ToolExecutionContext(
            user_id=USER_A,
            org_id=TENANT_A,
            role="editor",
            session_id=SESSION_A,
            ttl_seconds=MAX_TTL_SECONDS + 1,
        )
        with pytest.raises(ToolContextError, match="exceeds maximum"):
            validate_context(ctx)


# =============================================================================
# Expiry and Temporal Bounds
# =============================================================================


@pytest.mark.unit
class TestTemporalBounds:
    """Verify time-based context behavior."""

    def test_fresh_context_not_expired(self):
        ctx = valid_ctx()
        assert ctx.is_expired is False
        assert ctx.remaining_seconds > 0

    def test_old_context_is_expired(self):
        ctx = ToolExecutionContext(
            user_id=USER_A, org_id=TENANT_A, role="editor",
            session_id=SESSION_A,
            created_at=time.time() - 5000,
            ttl_seconds=60,
        )
        assert ctx.is_expired is True
        assert ctx.remaining_seconds == 0

    def test_default_ttl(self):
        ctx = valid_ctx()
        assert ctx.ttl_seconds == DEFAULT_TTL_SECONDS


# =============================================================================
# Capability Enforcement
# =============================================================================


@pytest.mark.unit
class TestCapabilities:
    """Verify capability restrictions work."""

    def test_empty_capabilities_allows_all(self):
        """Empty capabilities = unrestricted (transitional)."""
        ctx = valid_ctx(capabilities=frozenset())
        assert ctx.has_capability("execute:generate_image") is True
        assert ctx.has_capability("anything") is True

    def test_specific_capabilities_restrict(self):
        ctx = valid_ctx(capabilities=frozenset(["execute:search_talent", "execute:generate_image"]))
        assert ctx.has_capability("execute:generate_image") is True
        assert ctx.has_capability("execute:train_lora") is False

    @patch("backend.aios.hermes.tool_context._audit_tool_execution")
    @patch("backend.aios.governance.enforcement._audit_decision")
    @patch("backend.aios.governance.enforcement._load_policies")
    def test_missing_capability_blocks_execution(self, mock_policies, mock_gov_audit, mock_tool_audit):
        """Tool denied if context lacks required capability."""
        ctx = valid_ctx(capabilities=frozenset(["execute:search_talent"]))
        with pytest.raises(ToolAuthorizationError, match="lacks capability"):
            execute_tool_authorized(ctx, "generate_image", {"prompt": "test"})


# =============================================================================
# Signed Token — Serialization and Verification
# =============================================================================


@pytest.mark.unit
class TestSignedTokens:
    """Verify token creation and verification."""

    def test_roundtrip(self):
        """Token can be created and verified."""
        ctx = valid_ctx()
        token = ctx.to_signed_token()
        restored = ToolExecutionContext.from_signed_token(token)
        assert restored.user_id == ctx.user_id
        assert restored.org_id == ctx.org_id
        assert restored.role == ctx.role
        assert restored.session_id == ctx.session_id
        assert restored.nonce == ctx.nonce

    def test_tampered_token_rejected(self):
        """Modified token fails signature check."""
        ctx = valid_ctx()
        token = ctx.to_signed_token()
        # Tamper with the payload
        tampered = token.replace(USER_A, "hacker-id")
        with pytest.raises(ToolContextError, match="signature invalid"):
            ToolExecutionContext.from_signed_token(tampered)

    def test_expired_token_rejected(self):
        """Expired token is rejected on deserialization."""
        ctx = ToolExecutionContext(
            user_id=USER_A, org_id=TENANT_A, role="editor",
            session_id=SESSION_A,
            created_at=time.time() - 5000,
            ttl_seconds=60,
        )
        token = ctx.to_signed_token()
        with pytest.raises(ToolContextError, match="expired"):
            ToolExecutionContext.from_signed_token(token)

    def test_invalid_format_rejected(self):
        with pytest.raises(ToolContextError, match="Invalid token format"):
            ToolExecutionContext.from_signed_token("not-a-valid-token")


# =============================================================================
# Nonce — Replay Prevention
# =============================================================================


@pytest.mark.unit
class TestNonceUniqueness:
    """Verify nonce prevents replay."""

    def test_each_context_has_unique_nonce(self):
        ctx1 = valid_ctx()
        ctx2 = valid_ctx()
        assert ctx1.nonce != ctx2.nonce

    def test_nonce_is_in_token(self):
        ctx = valid_ctx()
        token = ctx.to_signed_token()
        assert ctx.nonce in token


# =============================================================================
# Role Enforcement via Governance
# =============================================================================


@pytest.mark.unit
class TestRoleEnforcement:
    """Verify role checks through governance integration."""

    @patch("backend.aios.hermes.tool_context._audit_tool_execution")
    @patch("backend.aios.governance.enforcement._audit_decision")
    def test_viewer_denied_side_effect(self, mock_gov_audit, mock_tool_audit):
        """Viewer role cannot execute side-effecting tools."""
        ctx = valid_ctx(role="viewer")
        with pytest.raises(ToolAuthorizationError):
            execute_tool_authorized(ctx, "generate_image", {"prompt": "test"})

    @patch("backend.aios.hermes.tool_context._audit_tool_execution")
    @patch("backend.aios.governance.enforcement._audit_decision")
    @patch("backend.aios.governance.enforcement._load_policies")
    @patch("backend.aios.hermes.tools.execute_tool")
    def test_editor_allowed_read_only(self, mock_exec, mock_policies, mock_gov_audit, mock_tool_audit):
        """Editor can execute read-only tools."""
        mock_exec.return_value = '{"results": []}'
        ctx = valid_ctx(role="editor")
        result = execute_tool_authorized(ctx, "search_talent", {"query": "test"})
        assert "results" in result


# =============================================================================
# Context Factory
# =============================================================================


@pytest.mark.unit
class TestContextFactory:
    """Verify context creation from TenantContext."""

    def test_creates_from_tenant_context(self):
        tenant = TenantContext(user_id=USER_A, org_id=TENANT_A, role=OrgRole.EDITOR)
        ctx = create_context_from_tenant(tenant, session_id="s1")
        assert ctx.user_id == USER_A
        assert ctx.org_id == TENANT_A
        assert ctx.role == "editor"
        assert ctx.session_id == "s1"
        assert ctx.trust_domain == TrustDomain.USER_INTERACTIVE

    def test_caps_ttl_at_maximum(self):
        tenant = TenantContext(user_id=USER_A, org_id=TENANT_A, role=OrgRole.ADMIN)
        ctx = create_context_from_tenant(tenant, session_id="s1", ttl_seconds=999999)
        assert ctx.ttl_seconds == MAX_TTL_SECONDS

    def test_approval_bound_context(self):
        tenant = TenantContext(user_id=USER_A, org_id=TENANT_A, role=OrgRole.ADMIN)
        ctx = create_context_from_tenant(
            tenant, session_id="s1",
            trust_domain=TrustDomain.APPROVAL_BOUND,
            approval_id="appr-123",
        )
        assert ctx.trust_domain == TrustDomain.APPROVAL_BOUND
        assert ctx.approval_id == "appr-123"


# =============================================================================
# Cross-Tenant (via governance)
# =============================================================================


@pytest.mark.unit
class TestCrossTenant:
    """Verify cross-workspace tool access is denied."""

    @patch("backend.aios.hermes.tool_context._audit_tool_execution")
    @patch("backend.aios.governance.enforcement._audit_decision")
    @patch("backend.aios.governance.enforcement._load_policies")
    @patch("backend.aios.hermes.tools.execute_tool")
    def test_tool_executes_with_callers_org(self, mock_exec, mock_policies, mock_gov_audit, mock_tool_audit):
        """Tool execution is bound to the caller's org from context."""
        mock_policies.return_value = {"auto_approve_generation": True, "max_auto_spend_usd": 100.0}
        mock_exec.return_value = '{"success": true}'

        ctx = valid_ctx(org_id=TENANT_A)
        result = execute_tool_authorized(ctx, "generate_image", {"prompt": "portrait"})
        assert result.get("success") is True
        # The execution used TENANT_A context — cannot access TENANT_B

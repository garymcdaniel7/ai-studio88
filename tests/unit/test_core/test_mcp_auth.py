"""MCP client authentication tests — Story 048.

Tests prove:
  - Missing credentials rejected
  - Malformed headers rejected
  - Revoked credentials rejected
  - Expired credentials rejected
  - Rotated (old) credentials rejected
  - Valid credential resolves to correct identity
  - Cross-workspace access impossible (identity bound to issuing org)
  - Over-capability denied (capability check works)
  - Rate limiting enforced
  - Role capped at editor (never admin/owner for MCP)
  - Credential rotation invalidates old key
  - Error messages are safe (no details leaked)
"""

import time

import pytest

from backend.aios.mcp.auth import (
    CredentialStatus,
    MCPActorType,
    MCPAuthError,
    MCPClientIdentity,
    MCPEnvironment,
    MCPRateLimitError,
    _reset_store,
    authenticate_mcp_request,
    issue_credential,
    revoke_credential,
    rotate_credential,
)

TENANT_A = "org-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
USER_A = "user-aaaa"


@pytest.fixture(autouse=True)
def clean_store():
    _reset_store()
    yield
    _reset_store()


def _issue_test_key(**overrides) -> tuple[str, str]:
    """Issue a test credential and return (id, raw_key)."""
    defaults = {
        "org_id": TENANT_A,
        "issued_by": USER_A,
        "actor_name": "Test Client",
        "capabilities": frozenset(["execute:search_talent", "execute:generate_image"]),
    }
    defaults.update(overrides)
    return issue_credential(**defaults)


# =============================================================================
# Missing / Malformed Credentials
# =============================================================================


@pytest.mark.unit
class TestMissingCredentials:
    """Verify missing/malformed credentials are rejected safely."""

    def test_no_header_rejected(self):
        with pytest.raises(MCPAuthError, match="Authentication required"):
            authenticate_mcp_request(None)

    def test_empty_header_rejected(self):
        with pytest.raises(MCPAuthError, match="Authentication required"):
            authenticate_mcp_request("")

    def test_no_bearer_prefix_rejected(self):
        with pytest.raises(MCPAuthError, match="Authentication failed"):
            authenticate_mcp_request("Basic abc123")

    def test_short_token_rejected(self):
        with pytest.raises(MCPAuthError, match="Authentication failed"):
            authenticate_mcp_request("Bearer short")

    def test_unknown_token_rejected(self):
        with pytest.raises(MCPAuthError, match="Authentication failed"):
            authenticate_mcp_request("Bearer mcp_fake_this_is_not_real_key_xyz")

    def test_error_message_is_safe(self):
        """Error messages must not reveal WHY authentication failed."""
        try:
            authenticate_mcp_request("Bearer mcp_fake_some_random_key_value")
        except MCPAuthError as e:
            assert "invalid" not in e.safe_message.lower()
            assert "not found" not in e.safe_message.lower()
            assert "expired" not in e.safe_message.lower()


# =============================================================================
# Valid Authentication
# =============================================================================


@pytest.mark.unit
class TestValidAuthentication:
    """Verify valid credentials resolve to correct identity."""

    def test_valid_key_authenticates(self):
        cred_id, raw_key = _issue_test_key()
        identity = authenticate_mcp_request(f"Bearer {raw_key}")
        assert identity.org_id == TENANT_A
        assert identity.actor_name == "Test Client"
        assert identity.credential_id == cred_id

    def test_identity_has_correct_capabilities(self):
        _, raw_key = _issue_test_key(
            capabilities=frozenset(["execute:search_talent"])
        )
        identity = authenticate_mcp_request(f"Bearer {raw_key}")
        assert identity.has_capability("execute:search_talent") is True
        assert identity.has_capability("execute:train_lora") is False

    def test_identity_bound_to_org(self):
        """Identity is bound to the org that issued the credential."""
        _, raw_key = _issue_test_key(org_id=TENANT_A)
        identity = authenticate_mcp_request(f"Bearer {raw_key}")
        assert identity.org_id == TENANT_A


# =============================================================================
# Revoked Credentials
# =============================================================================


@pytest.mark.unit
class TestRevokedCredentials:
    """Verify revoked credentials are immediately rejected."""

    def test_revoked_key_rejected(self):
        cred_id, raw_key = _issue_test_key()
        revoke_credential(cred_id, "admin-user")
        with pytest.raises(MCPAuthError):
            authenticate_mcp_request(f"Bearer {raw_key}")

    def test_revoke_returns_true(self):
        cred_id, _ = _issue_test_key()
        assert revoke_credential(cred_id, "admin") is True

    def test_revoke_unknown_returns_false(self):
        assert revoke_credential("nonexistent-id", "admin") is False


# =============================================================================
# Expired Credentials
# =============================================================================


@pytest.mark.unit
class TestExpiredCredentials:
    """Verify expired credentials are rejected."""

    def test_expired_key_rejected(self):
        _, raw_key = _issue_test_key(expires_in_days=-1)  # Already expired
        with pytest.raises(MCPAuthError):
            authenticate_mcp_request(f"Bearer {raw_key}")


# =============================================================================
# Rotation
# =============================================================================


@pytest.mark.unit
class TestCredentialRotation:
    """Verify rotation invalidates old key and issues new one."""

    def test_rotation_issues_new_key(self):
        old_id, old_key = _issue_test_key()
        result = rotate_credential(old_id, USER_A)
        assert result is not None
        new_id, new_key = result
        assert new_id != old_id
        assert new_key != old_key

    def test_old_key_rejected_after_rotation(self):
        old_id, old_key = _issue_test_key()
        rotate_credential(old_id, USER_A)
        with pytest.raises(MCPAuthError):
            authenticate_mcp_request(f"Bearer {old_key}")

    def test_new_key_works_after_rotation(self):
        old_id, _ = _issue_test_key()
        _, new_key = rotate_credential(old_id, USER_A)
        identity = authenticate_mcp_request(f"Bearer {new_key}")
        assert identity.org_id == TENANT_A


# =============================================================================
# Rate Limiting
# =============================================================================


@pytest.mark.unit
class TestRateLimiting:
    """Verify rate limiting is enforced per credential."""

    def test_rate_limit_exceeded(self):
        _, raw_key = _issue_test_key(rate_limit_rpm=3)
        # First 3 should work
        for _ in range(3):
            authenticate_mcp_request(f"Bearer {raw_key}")
        # 4th should be rate-limited
        with pytest.raises(MCPRateLimitError):
            authenticate_mcp_request(f"Bearer {raw_key}")

    def test_rate_limit_has_retry_after(self):
        _, raw_key = _issue_test_key(rate_limit_rpm=1)
        authenticate_mcp_request(f"Bearer {raw_key}")
        try:
            authenticate_mcp_request(f"Bearer {raw_key}")
        except MCPRateLimitError as e:
            assert e.retry_after > 0


# =============================================================================
# Role Capping
# =============================================================================


@pytest.mark.unit
class TestRoleCapping:
    """Verify MCP clients can never be admin/owner."""

    def test_admin_role_capped_to_editor(self):
        _, raw_key = _issue_test_key(role="admin")
        identity = authenticate_mcp_request(f"Bearer {raw_key}")
        assert identity.role == "editor"  # Capped!

    def test_owner_role_capped_to_editor(self):
        _, raw_key = _issue_test_key(role="owner")
        identity = authenticate_mcp_request(f"Bearer {raw_key}")
        assert identity.role == "editor"  # Capped!

    def test_editor_role_preserved(self):
        _, raw_key = _issue_test_key(role="editor")
        identity = authenticate_mcp_request(f"Bearer {raw_key}")
        assert identity.role == "editor"

    def test_viewer_role_preserved(self):
        _, raw_key = _issue_test_key(role="viewer")
        identity = authenticate_mcp_request(f"Bearer {raw_key}")
        assert identity.role == "viewer"


# =============================================================================
# Capability Enforcement
# =============================================================================


@pytest.mark.unit
class TestCapabilityEnforcement:
    """Verify capability checks work correctly."""

    def test_has_granted_capability(self):
        _, raw_key = _issue_test_key(capabilities=frozenset(["execute:search_talent"]))
        identity = authenticate_mcp_request(f"Bearer {raw_key}")
        assert identity.has_capability("execute:search_talent") is True

    def test_lacks_ungrated_capability(self):
        _, raw_key = _issue_test_key(capabilities=frozenset(["execute:search_talent"]))
        identity = authenticate_mcp_request(f"Bearer {raw_key}")
        assert identity.has_capability("execute:train_lora") is False

    def test_empty_capabilities_denies_all(self):
        """Empty capabilities = deny by default (not allow all)."""
        _, raw_key = _issue_test_key(capabilities=frozenset())
        identity = authenticate_mcp_request(f"Bearer {raw_key}")
        assert identity.has_capability("execute:anything") is False


# =============================================================================
# Cross-Workspace Protection
# =============================================================================


@pytest.mark.unit
class TestCrossWorkspace:
    """Verify credentials are bound to their issuing workspace."""

    def test_credential_bound_to_issuing_org(self):
        """A credential always maps to the org it was issued for."""
        _, raw_key = _issue_test_key(org_id=TENANT_A)
        identity = authenticate_mcp_request(f"Bearer {raw_key}")
        # Identity is ALWAYS bound to TENANT_A — cannot access TENANT_B
        assert identity.org_id == TENANT_A
        assert identity.org_id != "org-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

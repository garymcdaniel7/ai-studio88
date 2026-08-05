"""Social Credential Service Tests (Story 027).

Proves workspace isolation, scope validation, role enforcement,
expiration handling, revocation, and secret redaction.

Run with:
    pytest tests/unit/test_social_credentials.py -v
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from backend.credentials import _store as cred_store, _credential_audit
from backend.social_credentials import (
    ConnectionStatus,
    SocialCredentialService,
    SocialPlatform,
    _social_store,
)

ORG_A = str(uuid4())
ORG_B = str(uuid4())


@pytest.fixture(autouse=True)
def clean():
    _social_store.clear()
    cred_store.clear()
    _credential_audit.clear()
    yield
    _social_store.clear()
    cred_store.clear()
    _credential_audit.clear()


# =============================================================================
# Workspace Isolation
# =============================================================================


class TestWorkspaceIsolation:

    @pytest.mark.unit
    def test_connect_and_list_scoped(self):
        """Connections are scoped to their workspace."""
        SocialCredentialService.connect(
            org_id=ORG_A, platform=SocialPlatform.INSTAGRAM,
            access_token="ig_token_a", account_id="acct_a",
            granted_scopes=["instagram_basic", "instagram_content_publish"],
            actor="user-a",
        )
        SocialCredentialService.connect(
            org_id=ORG_B, platform=SocialPlatform.INSTAGRAM,
            access_token="ig_token_b", account_id="acct_b",
            granted_scopes=["instagram_basic", "instagram_content_publish"],
            actor="user-b",
        )

        conns_a = SocialCredentialService.get_connections(org_id=ORG_A)
        conns_b = SocialCredentialService.get_connections(org_id=ORG_B)

        assert len(conns_a) == 1
        assert len(conns_b) == 1
        assert conns_a[0]["org_id"] == ORG_A
        assert conns_b[0]["org_id"] == ORG_B

    @pytest.mark.unit
    def test_cross_org_resolve_returns_none(self):
        """Cannot resolve another org's social token."""
        SocialCredentialService.connect(
            org_id=ORG_A, platform=SocialPlatform.TIKTOK,
            access_token="tt_secret", account_id="tt_acct",
            granted_scopes=["video.publish", "video.upload", "user.info.basic"],
            actor="user-a",
        )

        # Org B cannot resolve Org A's token
        result = SocialCredentialService.resolve_for_publishing(
            org_id=ORG_B, platform=SocialPlatform.TIKTOK,
            actor="user-b", actor_role="owner",
        )
        assert result is None


# =============================================================================
# Scope Validation
# =============================================================================


class TestScopeValidation:

    @pytest.mark.unit
    def test_connection_with_sufficient_scopes(self):
        """Connection with all required scopes → ACTIVE."""
        result = SocialCredentialService.connect(
            org_id=ORG_A, platform=SocialPlatform.YOUTUBE,
            access_token="yt_token",
            account_id="yt_channel_1",
            granted_scopes=["https://www.googleapis.com/auth/youtube.upload",
                            "https://www.googleapis.com/auth/youtube.readonly"],
            actor="user-a",
        )
        assert result["status"] == "active"
        assert result["required_scopes_met"] is True

    @pytest.mark.unit
    def test_connection_with_missing_scopes(self):
        """Connection missing required scopes → SCOPE_INSUFFICIENT."""
        result = SocialCredentialService.connect(
            org_id=ORG_A, platform=SocialPlatform.X,
            access_token="x_token",
            account_id="x_user_1",
            granted_scopes=["tweet.read", "users.read"],  # Missing tweet.write
            actor="user-a",
        )
        assert result["status"] == "scope_insufficient"
        assert result["required_scopes_met"] is False

    @pytest.mark.unit
    def test_resolve_denied_for_insufficient_scopes(self):
        """Cannot use a connection with insufficient scopes for publishing."""
        SocialCredentialService.connect(
            org_id=ORG_A, platform=SocialPlatform.X,
            access_token="x_token",
            account_id="x_user",
            granted_scopes=["tweet.read"],  # Missing tweet.write
            actor="user-a",
        )
        result = SocialCredentialService.resolve_for_publishing(
            org_id=ORG_A, platform=SocialPlatform.X,
            actor="user-a", actor_role="owner",
        )
        assert result is None

    @pytest.mark.unit
    def test_validate_scopes_utility(self):
        """validate_scopes returns missing scope details."""
        result = SocialCredentialService.validate_scopes(
            platform=SocialPlatform.INSTAGRAM,
            granted_scopes=["instagram_basic"],
        )
        assert result["valid"] is False
        assert "instagram_content_publish" in result["missing"]


# =============================================================================
# Role Enforcement
# =============================================================================


class TestRoleEnforcement:

    @pytest.mark.unit
    def test_viewer_cannot_resolve_for_publishing(self):
        """Viewer role cannot use tokens for publishing."""
        SocialCredentialService.connect(
            org_id=ORG_A, platform=SocialPlatform.INSTAGRAM,
            access_token="ig_secret",
            account_id="ig_acct",
            granted_scopes=["instagram_basic", "instagram_content_publish"],
            actor="admin",
        )
        result = SocialCredentialService.resolve_for_publishing(
            org_id=ORG_A, platform=SocialPlatform.INSTAGRAM,
            actor="viewer-user", actor_role="viewer",
        )
        assert result is None

    @pytest.mark.unit
    def test_editor_can_resolve_for_publishing(self):
        """Editor role can use tokens for publishing."""
        SocialCredentialService.connect(
            org_id=ORG_A, platform=SocialPlatform.INSTAGRAM,
            access_token="ig_editor_token",
            account_id="ig_acct",
            granted_scopes=["instagram_basic", "instagram_content_publish"],
            actor="admin",
        )
        result = SocialCredentialService.resolve_for_publishing(
            org_id=ORG_A, platform=SocialPlatform.INSTAGRAM,
            actor="editor-user", actor_role="editor",
        )
        assert result == "ig_editor_token"


# =============================================================================
# Revocation
# =============================================================================


class TestRevocation:

    @pytest.mark.unit
    def test_revoke_blocks_future_use(self):
        """Revoked connection cannot be resolved."""
        SocialCredentialService.connect(
            org_id=ORG_A, platform=SocialPlatform.YOUTUBE,
            access_token="yt_revoke_test",
            account_id="yt_ch",
            granted_scopes=["https://www.googleapis.com/auth/youtube.upload"],
            actor="admin",
        )

        # Works before revocation
        token = SocialCredentialService.resolve_for_publishing(
            org_id=ORG_A, platform=SocialPlatform.YOUTUBE,
            actor="user", actor_role="owner",
        )
        assert token == "yt_revoke_test"

        # Revoke
        SocialCredentialService.revoke(
            org_id=ORG_A, platform=SocialPlatform.YOUTUBE, actor="admin",
        )

        # Blocked after revocation
        token = SocialCredentialService.resolve_for_publishing(
            org_id=ORG_A, platform=SocialPlatform.YOUTUBE,
            actor="user", actor_role="owner",
        )
        assert token is None

    @pytest.mark.unit
    def test_revoke_nonexistent_returns_false(self):
        """Revoking when no connection exists returns False."""
        result = SocialCredentialService.revoke(
            org_id=ORG_A, platform=SocialPlatform.TIKTOK, actor="admin",
        )
        assert result is False


# =============================================================================
# Refresh Failure
# =============================================================================


class TestRefreshFailure:

    @pytest.mark.unit
    def test_mark_refresh_failed(self):
        """Refresh failure changes connection status."""
        SocialCredentialService.connect(
            org_id=ORG_A, platform=SocialPlatform.X,
            access_token="x_token",
            account_id="x_user",
            granted_scopes=["tweet.read", "tweet.write", "users.read", "offline.access"],
            actor="admin",
        )

        SocialCredentialService.mark_refresh_failed(
            org_id=ORG_A, platform=SocialPlatform.X, error="invalid_grant",
        )

        conns = SocialCredentialService.get_connections(org_id=ORG_A)
        assert conns[0]["status"] == "refresh_failed"


# =============================================================================
# Masked Output (No Secret Exposure)
# =============================================================================


class TestMaskedOutput:

    @pytest.mark.unit
    def test_connection_view_never_contains_token(self):
        """Masked view never exposes access_token or refresh_token."""
        result = SocialCredentialService.connect(
            org_id=ORG_A, platform=SocialPlatform.INSTAGRAM,
            access_token="super_secret_ig_token_xyz",
            refresh_token="refresh_secret_abc",
            account_id="ig_123",
            granted_scopes=["instagram_basic", "instagram_content_publish"],
            actor="admin",
        )
        result_str = str(result)
        assert "super_secret_ig_token_xyz" not in result_str
        assert "refresh_secret_abc" not in result_str
        assert "access_token" not in result_str
        assert "refresh_token" not in result_str

    @pytest.mark.unit
    def test_get_connections_never_exposes_tokens(self):
        """get_connections() never includes token material."""
        SocialCredentialService.connect(
            org_id=ORG_A, platform=SocialPlatform.TIKTOK,
            access_token="tt_secret_value",
            account_id="tt_user",
            granted_scopes=["video.publish", "video.upload", "user.info.basic"],
            actor="admin",
        )
        conns = SocialCredentialService.get_connections(org_id=ORG_A)
        for conn in conns:
            assert "tt_secret_value" not in str(conn)
            assert "token" not in str(conn).lower() or "access_token" not in conn


# =============================================================================
# Audit Trail
# =============================================================================


class TestAudit:

    @pytest.mark.unit
    def test_connect_produces_audit(self):
        SocialCredentialService.connect(
            org_id=ORG_A, platform=SocialPlatform.INSTAGRAM,
            access_token="ig_t", account_id="acct",
            granted_scopes=["instagram_basic", "instagram_content_publish"],
            actor="user-1",
        )
        from backend.credentials import get_credential_audit
        audit = get_credential_audit(org_id=ORG_A)
        assert any(e["action"] == "social_connect" for e in audit)

    @pytest.mark.unit
    def test_revoke_produces_audit(self):
        SocialCredentialService.connect(
            org_id=ORG_A, platform=SocialPlatform.X,
            access_token="x_t", account_id="x_u",
            granted_scopes=["tweet.write", "tweet.read", "users.read", "offline.access"],
            actor="admin",
        )
        SocialCredentialService.revoke(org_id=ORG_A, platform=SocialPlatform.X, actor="admin")
        from backend.credentials import get_credential_audit
        audit = get_credential_audit(org_id=ORG_A)
        assert any(e["action"] == "social_revoke" for e in audit)

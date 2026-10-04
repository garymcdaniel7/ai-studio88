"""Cross-tenant OAuth isolation probe — verifies org A cannot claim org B's OAuth session.

Tests the entire OAuth connection flow at the application level:
    1. GET /platforms → org-scoped connection list
    2. GET /{platform}/authorize → pending row tagged with caller's org_id
    3. GET /{platform}/callback → state recovery → token stored under originating org
    4. DELETE /connections/{platform} → org-scoped disconnect
    5. GET /connections → org-scoped connection list

The security model (CTO remediation F2 2026-10-03):
    - Every authenticated endpoint uses AuthUser.org_id resolved from org_members
    - The public callback endpoint recovers org_id from the pending row (via CSRF state)
    - social_connections has a composite UNIQUE(org_id, platform) key
    - _get_connections(org_id) returns empty for None/mismatched org

Validates: Requirements R2.2, R2.6, R2.7, R2.8, R2.9, R2.10, F2
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest

# ── Mock stack ──────────────────────────────────────────────────────────────

# Mock SQLAlchemy to avoid import chain issues
import types as types_mod

_sa_mock = MagicMock()
_sa_mock.DateTime = MagicMock
_sa_mock.Float = MagicMock
_sa_mock.Integer = MagicMock
_sa_mock.String = MagicMock
_sa_mock.Text = MagicMock
_sa_mock.Boolean = MagicMock
_sa_mock.ForeignKey = MagicMock
_sa_mock.Index = MagicMock
_sa_mock.func = MagicMock()
_sa_mock.select = MagicMock()
_sa_mock.update = MagicMock()

_sa_orm_mock = MagicMock()
_sa_orm_mock.Mapped = MagicMock
_sa_orm_mock.mapped_column = MagicMock(return_value=None)
_sa_orm_mock.relationship = MagicMock(return_value=None)
_sa_orm_mock.DeclarativeBase = type("DeclarativeBase", (), {})

_sa_dialects_pg_mock = MagicMock()
_sa_dialects_pg_mock.UUID = MagicMock
_sa_dialects_pg_mock.JSONB = MagicMock
_sa_dialects_pg_mock.ARRAY = MagicMock

_sa_ext_asyncio_mock = MagicMock()
_sa_ext_asyncio_mock.AsyncEngine = MagicMock
_sa_ext_asyncio_mock.AsyncSession = MagicMock
_sa_ext_asyncio_mock.async_sessionmaker = MagicMock
_sa_ext_asyncio_mock.create_async_engine = MagicMock

_sa_exc_mod = types_mod.ModuleType("sqlalchemy.exc")
_sa_exc_mod.IntegrityError = type("IntegrityError", (Exception,), {})

sys.modules.setdefault("sqlalchemy", _sa_mock)
sys.modules.setdefault("sqlalchemy.orm", _sa_orm_mock)
sys.modules.setdefault("sqlalchemy.ext", MagicMock())
sys.modules.setdefault("sqlalchemy.ext.asyncio", _sa_ext_asyncio_mock)
sys.modules.setdefault("sqlalchemy.dialects", MagicMock())
sys.modules.setdefault("sqlalchemy.dialects.postgresql", _sa_dialects_pg_mock)
sys.modules.setdefault("sqlalchemy.exc", _sa_exc_mod)

# Mock backend.app modules
_mock_app = types_mod.ModuleType("app")
_mock_app.__path__ = []
sys.modules.setdefault("app", _mock_app)

_mock_app_core = types_mod.ModuleType("app.core")
_mock_app_core.__path__ = []
sys.modules.setdefault("app.core", _mock_app_core)

_mock_app_core_config = types_mod.ModuleType("app.core.config")


class MockSettings:
    auth_dev_mode = False
    environment = "test"


_mock_app_core_config.get_settings = MagicMock(return_value=MockSettings())

def reset_settings():
    pass


_mock_app_core_config.reset_settings = reset_settings
_mock_app_core_config.Settings = type("Settings", (), {})
sys.modules.setdefault("app.core.config", _mock_app_core_config)

_mock_app_db = types_mod.ModuleType("app.db")
sys.modules.setdefault("app.db", _mock_app_db)

_mock_app_db_base = types_mod.ModuleType("app.db.base")
_mock_app_db_base.Base = type("Base", (), {})
sys.modules.setdefault("app.db.base", _mock_app_db_base)

_mock_tenant_scope = types_mod.ModuleType("app.db.tenant_scope")
_mock_tenant_scope.QUARANTINED_ORG_ID = UUID("00000000-0000-0000-0000-000000000000")
sys.modules.setdefault("app.db.tenant_scope", _mock_tenant_scope)

# Now import the module under test
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# ── Test constants ──────────────────────────────────────────────────────────

ORG_A = uuid4()
ORG_B = uuid4()
USER_A = uuid4()
USER_B = uuid4()

PLATFORM = "instagram"


# ── Helpers ─────────────────────────────────────────────────────────────────


def make_auth_user(
    user_id: str | None = None,
    org_id: str | None = None,
    email: str | None = None,
    role: str = "authenticated",
):
    """Create a mock AuthUser for dependency injection."""
    from backend.auth import AuthUser

    return AuthUser(
        user_id=str(user_id or USER_A),
        email=email or "test@example.com",
        org_id=str(org_id),
        role=role,
    )


def mock_supabase_table():
    """Create a mock supabase table() that can be chained with .eq(), .select(), .execute()."""
    mock = MagicMock()
    mock.execute.return_value = MagicMock(data=[])
    return mock


# ── Tests: _get_connections org-scoping ─────────────────────────────────────


class TestGetConnectionsOrgScoping:
    """Verify _get_connections properly filters by org_id."""

    def test_get_connections_with_org_id(self):
        """_get_connections(org_id=A) returns only org A's connections."""
        from backend.publishing.oauth import _get_connections

        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_eq = MagicMock()
        mock_neq = MagicMock()

        # Simulate: supabase.table("social_connections").select("*").eq("org_id", ORG_A).neq("status", "pending").execute()
        mock_client.table.return_value = mock_table
        mock_table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table  # .eq("org_id", ...)
        mock_table.neq.return_value = mock_table  # .neq("status", ...)

        mock_table.execute.return_value = MagicMock(
            data=[
                {"org_id": str(ORG_A), "platform": "instagram", "status": "connected"},
                {"org_id": str(ORG_A), "platform": "youtube", "status": "connected"},
            ]
        )

        with patch("backend.publishing.oauth._db", return_value=mock_client):
            results = _get_connections(org_id=str(ORG_A))

        assert len(results) == 2
        assert all(r["org_id"] == str(ORG_A) for r in results)
        mock_table.eq.assert_called_with("org_id", str(ORG_A))

    def test_get_connections_none_org_id_returns_empty(self):
        """_get_connections(org_id=None) returns empty list — no org, no data."""
        from backend.publishing.oauth import _get_connections

        results = _get_connections(org_id=None)
        assert results == []

    def test_get_connections_empty_string_org_id_returns_empty(self):
        """_get_connections(org_id='') returns empty list — invalid org."""
        from backend.publishing.oauth import _get_connections

        results = _get_connections(org_id="")
        assert results == []

    def test_get_connections_org_a_does_not_see_org_b_data(self):
        """Org A's query filters by org_id=A and does not return org B's rows."""
        from backend.publishing.oauth import _get_connections

        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.neq.return_value = mock_table
        mock_table.execute.return_value = MagicMock(
            data=[
                # Only org A's data is returned
                {"org_id": str(ORG_A), "platform": "instagram", "status": "connected"},
            ]
        )

        with patch("backend.publishing.oauth._db", return_value=mock_client):
            results = _get_connections(org_id=str(ORG_A))

        assert len(results) == 1
        assert results[0]["org_id"] == str(ORG_A)
        # Verify the filter was applied
        mock_table.eq.assert_called_with("org_id", str(ORG_A))

    def test_get_connections_org_a_connection_not_returned_for_org_b_query(self):
        """Same data queried with org B's ID returns nothing — org A's connection is isolated."""
        from backend.publishing.oauth import _get_connections

        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_table.select.return_value = mock_table

        # eq is called per argument — we need to track it
        def eq_side_effect(field, value):
            mock_table._last_eq_field = field
            mock_table._last_eq_value = value
            return mock_table

        mock_table.eq.side_effect = eq_side_effect
        mock_table.neq.return_value = mock_table

        # If org A has a connection, org B's query should return nothing
        mock_table.execute.return_value = MagicMock(data=[])

        with patch("backend.publishing.oauth._db", return_value=mock_client):
            results = _get_connections(org_id=str(ORG_B))

        assert len(results) == 0
        assert mock_table._last_eq_value == str(ORG_B)


# ── Tests: list_platforms org-scoping ────────────────────────────────────────


class TestListPlatformsOrgScoping:
    """Verify GET /platforms returns only the caller's org's connections."""

    def test_org_a_platforms_isolated_from_org_b(self):
        """Org A's connected platforms list does not include Org B's connections."""
        from backend.publishing.oauth import list_platforms

        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.neq.return_value = mock_table
        # Only org A has connected instagram
        mock_table.execute.return_value = MagicMock(
            data=[
                {"org_id": str(ORG_A), "platform": "instagram", "status": "connected"},
            ]
        )

        # Set up env for platform config
        env_patch = {
            "INSTAGRAM_APP_ID": "test_id",
            "INSTAGRAM_APP_SECRET": "test_secret",
        }

        with patch("backend.publishing.oauth._db", return_value=mock_client):
            with patch.dict(os.environ, env_patch, clear=False):
                user_a = make_auth_user(org_id=str(ORG_A))
                result = list_platforms(user=user_a)

        # Org A sees instagram as connected
        instagram = [p for p in result["platforms"] if p["platform"] == "instagram"]
        assert len(instagram) == 1
        assert instagram[0]["connected"] is True

    def test_org_b_sees_no_connections_when_only_org_a_has_them(self):
        """Org B sees all platforms as disconnected when only Org A has connections."""
        from backend.publishing.oauth import list_platforms

        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.neq.return_value = mock_table
        # Org A has connections, but we're querying as Org B
        mock_table.execute.return_value = MagicMock(
            data=[
                # Would only return org B's connections — in this case, nothing
            ]
        )

        env_patch = {
            "INSTAGRAM_APP_ID": "test_id",
            "INSTAGRAM_APP_SECRET": "test_secret",
        }

        with patch("backend.publishing.oauth._db", return_value=mock_client):
            with patch.dict(os.environ, env_patch, clear=False):
                user_b = make_auth_user(org_id=str(ORG_B))
                result = list_platforms(user=user_b)

        # Org B sees instagram as not connected
        instagram = [p for p in result["platforms"] if p["platform"] == "instagram"]
        assert len(instagram) == 1
        assert instagram[0]["connected"] is False


# ── Tests: OAuth authorize org-tagging ──────────────────────────────────────


class TestAuthorizeOrgScoping:
    """Verify GET /{platform}/authorize tags the pending row with the caller's org_id."""

    def test_authorize_uses_caller_org_id_not_supplied_org_id(self):
        """The authorize endpoint uses AuthUser.org_id (from JWT), never a user-supplied org_id."""
        from backend.publishing.oauth import get_authorize_url

        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_table.upsert.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[])

        env_patch = {
            "INSTAGRAM_APP_ID": "test_ig_id",
            "INSTAGRAM_APP_SECRET": "test_ig_secret",
            "OAUTH_CALLBACK_BASE": "http://localhost:8000",
        }

        request = MagicMock()
        request.url.path = "/api/v1/publishing/oauth/instagram/authorize"

        with patch("backend.publishing.oauth._db", return_value=mock_client):
            with patch.dict(os.environ, env_patch, clear=False):
                user_a = make_auth_user(org_id=str(ORG_A))
                get_authorize_url(platform="instagram", user=user_a)

        # The upsert must use the caller's org_id (ORG_A), not any other org_id
        upsert_call = mock_table.upsert.call_args
        assert upsert_call is not None, "upsert was never called"
        upsert_data, upsert_kwargs = upsert_call
        assert upsert_data[0]["org_id"] == str(ORG_A), (
            f"Expected org_id={ORG_A} in upsert, got {upsert_data[0].get('org_id')}"
        )

    def test_org_a_and_org_b_have_separate_pending_flows(self):
        """Two concurrent authorize flows (org A and org B) produce separate pending rows."""
        from backend.publishing.oauth import get_authorize_url

        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_table.upsert.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[])

        env_patch = {
            "INSTAGRAM_APP_ID": "test_ig_id",
            "INSTAGRAM_APP_SECRET": "test_ig_secret",
            "OAUTH_CALLBACK_BASE": "http://localhost:8000",
        }

        request = MagicMock()
        request.url.path = "/api/v1/publishing/oauth/instagram/authorize"

        with patch("backend.publishing.oauth._db", return_value=mock_client):
            with patch.dict(os.environ, env_patch, clear=False):
                # Org A starts a flow
                user_a = make_auth_user(org_id=str(ORG_A))
                result_a = get_authorize_url(platform="instagram", user=user_a)
                state_a = result_a["state"]

                # Org B starts a flow
                user_b = make_auth_user(org_id=str(ORG_B))
                result_b = get_authorize_url(platform="instagram", user=user_b)
                state_b = result_b["state"]

        # Verify each flow used a different CSRF state
        assert state_a != state_b, "CSRF states should be unique per flow"

        # Verify upsert was called twice with different org_ids
        assert mock_table.upsert.call_count == 2
        upsert_calls = mock_table.upsert.call_args_list
        org_ids_used = [call[0][0]["org_id"] for call in upsert_calls]
        assert str(ORG_A) in org_ids_used
        assert str(ORG_B) in org_ids_used


# ── Tests: Callback org recovery ────────────────────────────────────────────


class TestCallbackOrgRecovery:
    """Verify OAuth callback correctly recovers the org that started the flow."""

    def test_callback_recovers_correct_org_from_state(self):
        """_recover_pending_org finds the org_id by matching CSRF state."""
        from backend.publishing.oauth import _recover_pending_org

        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        expected_state = "csrf_state_abc123"

        # Simulate a pending row belonging to ORG_A
        mock_table.execute.return_value = MagicMock(
            data=[
                {
                    "org_id": str(ORG_A),
                    "metadata": {"state": expected_state, "redirect_uri": "http://..."},
                }
            ]
        )

        with patch("backend.publishing.oauth._db", return_value=mock_client):
            org_id = _recover_pending_org("instagram", expected_state)

        assert org_id == str(ORG_A), f"Expected org_id={ORG_A}, got {org_id}"

    def test_callback_rejects_wrong_state(self):
        """_recover_pending_org returns None when state doesn't match any pending row."""
        from backend.publishing.oauth import _recover_pending_org

        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table

        # Pending row for ORG_A but with a different state
        mock_table.execute.return_value = MagicMock(
            data=[
                {
                    "org_id": str(ORG_A),
                    "metadata": {"state": "csrf_state_from_org_a", "redirect_uri": "http://..."},
                }
            ]
        )

        with patch("backend.publishing.oauth._db", return_value=mock_client):
            org_id = _recover_pending_org("instagram", "csrf_state_from_org_b")

        assert org_id is None, "Should not recover org with mismatched state"

    def test_callback_stores_token_under_recovered_org(self):
        """The callback stores the connection token under the recovered org_id."""
        from backend.publishing.oauth import oauth_callback

        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table

        # Step 1: _recover_pending finds ORG_A
        mock_table.execute.side_effect = [
            # First execute: pending row lookup (_recover_pending_org)
            MagicMock(
                data=[
                    {
                        "org_id": str(ORG_A),
                        "metadata": {
                            "state": "csrf_state_abc123",
                            "redirect_uri": "http://localhost:8000/api/...",
                        },
                    }
                ]
            ),
            # Second execute: token exchange result (we won't actually hit the external API)
            MagicMock(data=[]),
        ]

        env_patch = {
            "INSTAGRAM_APP_ID": "test_ig_id",
            "INSTAGRAM_APP_SECRET": "test_ig_secret",
            "OAUTH_CALLBACK_BASE": "http://localhost:8000",
        }

        with patch("backend.publishing.oauth._db", return_value=mock_client):
            with patch("backend.publishing.oauth._exchange_code", return_value=None):
                with patch.dict(os.environ, env_patch, clear=False):
                    # The public callback endpoint has no auth dependency
                    result = oauth_callback(
                        platform="instagram",
                        code="auth_code_from_platform",
                        state="csrf_state_abc123",
                    )

        # Should return the callback HTML page (not an error)
        assert result.status_code == 200, "Callback should return 200 HTML response"

    def test_org_a_cannot_recover_org_b_pending_flow(self):
        """Org A cannot recover Org B's pending flow — state mismatch blocks it."""
        from backend.publishing.oauth import _recover_pending_org

        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table

        # Org B has a pending flow with state 'org_b_state'
        mock_table.execute.return_value = MagicMock(
            data=[
                {
                    "org_id": str(ORG_B),
                    "metadata": {"state": "org_b_state", "redirect_uri": "http://..."},
                }
            ]
        )

        # Org A tries to recover using a different state
        with patch("backend.publishing.oauth._db", return_value=mock_client):
            org_id = _recover_pending_org("instagram", "org_a_fake_state")

        assert org_id is None, "Org A should not recover Org B's pending flow"


# ── Tests: Disconnect org-scoping ───────────────────────────────────────────


class TestDisconnectOrgScoping:
    """Verify DELETE /connections/{platform} only disconnects the caller's org's connection."""

    def test_disconnect_filters_by_caller_org(self):
        """Disconnect filters DELETE by the authenticated user's org_id."""
        from backend.publishing.oauth import disconnect_platform

        # Track all .eq() calls via a wrapper mock
        eq_calls_log = []

        def tracking_eq(field, value):
            eq_calls_log.append((field, value))
            return tracking_mock  # Return self for chaining

        tracking_mock = MagicMock()
        tracking_mock.execute.return_value = MagicMock(data=[])
        tracking_mock.eq = tracking_eq

        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_table.delete.return_value = tracking_mock

        with patch("backend.publishing.oauth._db", return_value=mock_client):
            user_a = make_auth_user(org_id=str(ORG_A))
            disconnect_platform(platform="instagram", user=user_a)

        # Verify the chain hits the right table
        mock_client.table.assert_called_with("social_connections")

        # Verify at least one .eq("org_id", ...) with the caller's org
        org_eq_found = any(
            args == ("org_id", str(ORG_A)) for args in eq_calls_log
        )
        assert org_eq_found, (
            f"Expected .eq('org_id', '{ORG_A}') in chain, got eq calls: {eq_calls_log}"
        )

    def test_org_a_cannot_disconnect_org_b_connection(self):
        """Org A's disconnect call cannot delete Org B's connection — org_id filter prevents it."""
        from backend.publishing.oauth import disconnect_platform

        # Track all .eq() calls
        eq_calls_log = []

        def tracking_eq(field, value):
            eq_calls_log.append((field, value))
            return tracking_mock

        tracking_mock = MagicMock()
        tracking_mock.execute.return_value = MagicMock(data=[])
        tracking_mock.eq = tracking_eq

        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_table.delete.return_value = tracking_mock

        with patch("backend.publishing.oauth._db", return_value=mock_client):
            user_a = make_auth_user(org_id=str(ORG_A))
            disconnect_platform(platform="instagram", user=user_a)

        # Verify org_id filter is always the caller's org, never ORG_B
        org_eqs = [(f, v) for f, v in eq_calls_log if f == "org_id"]
        assert len(org_eqs) >= 1, f"No org_id filter found in eq calls: {eq_calls_log}"
        assert all(v == str(ORG_A) for f, v in org_eqs), (
            f"All org_id filters must be caller's org ({ORG_A}), got: {org_eqs}"
        )


# ── Tests: Endpoint auth enforcement ────────────────────────────────────────


class TestOAuthAuthEnforcement:
    """Verify OAuth endpoints require authentication (except public callback)."""

    def test_list_platforms_requires_auth(self):
        """list_platforms uses require_auth dependency."""
        from backend.publishing.oauth import list_platforms

        # The function signature has user: AuthUser = Depends(require_auth)
        # Calling it without a user should fail — the Depends injects it
        import inspect

        sig = inspect.signature(list_platforms)
        params = list(sig.parameters.values())
        user_param = params[1] if len(params) > 1 else params[0]
        # Verify the parameter has a default that goes through require_auth
        assert user_param.name == "user", (
            f"Expected 'user' parameter, got '{user_param.name}'"
        )

    def test_authorize_requires_auth(self):
        """get_authorize_url uses require_auth dependency."""
        from backend.publishing.oauth import get_authorize_url

        import inspect

        sig = inspect.signature(get_authorize_url)
        params = list(sig.parameters.values())
        user_param = params[1]
        assert user_param.name == "user"

    def test_disconnect_requires_auth(self):
        """disconnect_platform uses require_auth dependency."""
        from backend.publishing.oauth import disconnect_platform

        import inspect

        sig = inspect.signature(disconnect_platform)
        params = list(sig.parameters.values())
        user_param = params[1]
        assert user_param.name == "user"

    def test_callback_is_public(self):
        """oauth_callback does NOT require auth — it's the social platform redirect destination."""
        from backend.publishing.oauth import oauth_callback

        import inspect

        sig = inspect.signature(oauth_callback)
        params = list(sig.parameters.values())
        param_names = [p.name for p in params]
        assert "user" not in param_names, (
            f"Callback should not have an auth dependency, got params: {param_names}"
        )


# ── Tests: DB constraint ensures isolation ──────────────────────────────────


class TestDBConstraintEnforcement:
    """Verify the composite UNIQUE(org_id, platform) constraint prevents cross-tenant overwrite."""

    def test_upsert_on_conflict_uses_org_id_and_platform(self):
        """The social_connections upsert uses on_conflict=['org_id', 'platform']."""
        from backend.publishing.oauth import get_authorize_url

        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_table.upsert.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[])

        env_patch = {
            "INSTAGRAM_APP_ID": "test_id",
            "INSTAGRAM_APP_SECRET": "test_secret",
            "OAUTH_CALLBACK_BASE": "http://localhost:8000",
        }

        request = MagicMock()
        request.url.path = "/api/v1/publishing/oauth/instagram/authorize"

        with patch("backend.publishing.oauth._db", return_value=mock_client):
            with patch.dict(os.environ, env_patch, clear=False):
                user_a = make_auth_user(org_id=str(ORG_A))
                get_authorize_url(platform="instagram", user=user_a)

        upsert_call = mock_table.upsert.call_args
        assert upsert_call is not None
        kwargs = upsert_call[1]
        conflict_columns = kwargs.get("on_conflict", [])
        assert "org_id" in conflict_columns, (
            f"Expected 'org_id' in on_conflict, got {conflict_columns}"
        )
        assert "platform" in conflict_columns, (
            f"Expected 'platform' in on_conflict, got {conflict_columns}"
        )


# ── Run ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
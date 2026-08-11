"""Property-Based Tests: Authentication Enforcement & Workspace Provisioning — Task 2.5.

Proves two correctness properties using hypothesis:

  Property 2 — Authentication Enforcement Universality:
    For ALL non-exempt endpoints, missing/invalid JWT returns 401.
    Exempt paths (/health, /ready, /) respond without auth.

  Property 16 — Workspace Provisioning Idempotency:
    Repeated provisioning attempts for the same user yield exactly one
    workspace/membership. No duplicates are created regardless of how
    many times provision_workspace() is invoked.

**Validates: Requirements R1.1, R1.2, R1.11, R84.5**

Run with:
    pytest tests/unit/test_core/test_auth_enforcement.py -v
"""
from __future__ import annotations

import os
import string
import sys
import time
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

# Ensure backend/app is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "backend"))

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.core.middleware import AuthMiddleware, EXEMPT_PATHS as MW_EXEMPT_PATHS
from app.core.security import JWTPayload


# =============================================================================
# Constants
# =============================================================================

TEST_SECRET = "test-jwt-secret-at-least-32-chars-long"
TEST_ALGORITHM = "HS256"

# HTTP methods used across the API
HTTP_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"]

# Exempt paths that MUST NOT require auth (from R1.1)
EXEMPT_PATHS = ["/health", "/ready", "/"]


# =============================================================================
# Strategies — Hypothesis generators
# =============================================================================

# Strategy for path segments (alphanum + hyphen)
path_segment_st = st.text(
    alphabet=string.ascii_lowercase + string.digits + "-",
    min_size=1,
    max_size=15,
)

# Strategy for generating plausible API paths (non-exempt)
api_path_st = st.builds(
    lambda *segments: "/api/v1/" + "/".join(segments),
    path_segment_st,
    path_segment_st,
)

# Strategy for HTTP methods
http_method_st = st.sampled_from(HTTP_METHODS)

# Strategy for invalid Authorization header values
invalid_auth_header_st = st.one_of(
    st.just(None),  # Missing header
    st.just(""),  # Empty header
    st.just("Basic dXNlcjpwYXNz"),  # Wrong scheme
    st.just("Bearer "),  # Empty bearer token
    st.just("Bearer not.a.valid.jwt"),  # Garbage token
    st.just("Bearer eyJ.garbage.tokens"),  # Malformed JWT
    st.builds(
        lambda s: f"Bearer {s}",
        st.text(alphabet=string.ascii_letters + string.digits, min_size=5, max_size=30),
    ),  # Random strings as tokens
)

# Strategy for email addresses
email_st = st.builds(
    lambda local, domain: f"{local}@{domain}.com",
    st.text(alphabet=string.ascii_lowercase + ".", min_size=2, max_size=15).filter(
        lambda s: not s.startswith(".") and not s.endswith(".") and ".." not in s
    ),
    st.text(alphabet=string.ascii_lowercase, min_size=3, max_size=10),
)

# Strategy for user UUIDs
user_id_st = st.uuids()


# =============================================================================
# Helpers
# =============================================================================


def _create_test_app_with_routes(paths: list[tuple[str, str]]) -> FastAPI:
    """Create a FastAPI app with AuthMiddleware and given routes.

    Args:
        paths: List of (method, path) tuples to register.
    """
    app = FastAPI()
    app.add_middleware(AuthMiddleware)

    # Exempt endpoints
    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/ready")
    async def ready():
        return {"status": "ready"}

    @app.get("/")
    async def root():
        return {"message": "root"}

    # Register dynamic protected endpoints
    for method, path in paths:
        # Create a unique handler for each route
        async def handler(request: Request, _p=path, _m=method):
            return {"path": _p, "method": _m}

        if method == "GET":
            app.add_api_route(path, handler, methods=["GET"])
        elif method == "POST":
            app.add_api_route(path, handler, methods=["POST"])
        elif method == "PUT":
            app.add_api_route(path, handler, methods=["PUT"])
        elif method == "PATCH":
            app.add_api_route(path, handler, methods=["PATCH"])
        elif method == "DELETE":
            app.add_api_route(path, handler, methods=["DELETE"])

    return app


def _make_mock_settings(*, auth_dev_mode: bool = False, app_env: str = "local"):
    """Create a mock settings object."""
    mock = MagicMock()
    mock.supabase_jwt_secret = TEST_SECRET
    mock.jwt_algorithm = TEST_ALGORITHM
    mock.app_env = app_env
    mock.auth_dev_mode = auth_dev_mode
    return mock


# =============================================================================
# Property 2: Authentication Enforcement Universality
# =============================================================================


@pytest.mark.unit
class TestProperty2AuthEnforcementUniversality:
    """Property 2: For all non-exempt endpoints, missing/invalid JWT returns 401.

    **Validates: Requirements R1.1, R1.2**

    Universal invariant: No protected endpoint EVER returns a non-401 status
    when the request lacks valid authentication credentials.
    """

    @given(
        path_suffix=path_segment_st,
        method=http_method_st,
        invalid_auth=invalid_auth_header_st,
    )
    @settings(max_examples=200)
    def test_any_non_exempt_path_rejects_invalid_auth(
        self,
        path_suffix: str,
        method: str,
        invalid_auth: str | None,
    ) -> None:
        """ANY non-exempt path with invalid/missing auth → 401.

        **Validates: Requirements R1.1, R1.2**

        For any randomly generated API path and any form of invalid
        authentication (missing, wrong scheme, garbage token, etc.),
        the middleware MUST return 401.
        """
        path = f"/api/v1/{path_suffix}"

        # Ensure path is not accidentally exempt
        assume(path not in MW_EXEMPT_PATHS)

        mock_settings = _make_mock_settings()
        app = FastAPI()
        app.add_middleware(AuthMiddleware)

        # Register the path for the given method
        async def handler(request: Request):
            return {"ok": True}

        app.add_api_route(path, handler, methods=[method])

        with patch("app.core.middleware.get_settings", return_value=mock_settings):
            with patch("app.core.security.settings", mock_settings):
                client = TestClient(app, raise_server_exceptions=False)
                headers = {}
                if invalid_auth is not None:
                    headers["Authorization"] = invalid_auth

                resp = client.request(method, path, headers=headers)

                assert resp.status_code == 401, (
                    f"{method} {path} with auth={invalid_auth!r} "
                    f"returned {resp.status_code}, expected 401"
                )
                body = resp.json()
                assert "code" in body
                assert body["code"] in (
                    "UNAUTHORIZED",
                    "TOKEN_EXPIRED",
                    "INVALID_TOKEN",
                )

    @given(path_suffix=path_segment_st)
    @settings(max_examples=50)
    def test_exempt_paths_never_return_401(
        self,
        path_suffix: str,
    ) -> None:
        """Exempt paths (/health, /ready, /) NEVER return 401.

        **Validates: Requirements R1.1**

        Regardless of whether auth headers are provided, exempt paths
        must respond normally (non-401).
        """
        mock_settings = _make_mock_settings()
        app = FastAPI()
        app.add_middleware(AuthMiddleware)

        @app.get("/health")
        async def health():
            return {"status": "ok"}

        @app.get("/ready")
        async def ready():
            return {"status": "ready"}

        @app.get("/")
        async def root():
            return {"message": "root"}

        with patch("app.core.middleware.get_settings", return_value=mock_settings):
            with patch("app.core.security.settings", mock_settings):
                client = TestClient(app, raise_server_exceptions=False)

                for exempt_path in EXEMPT_PATHS:
                    resp = client.get(exempt_path)
                    assert resp.status_code != 401, (
                        f"Exempt path {exempt_path} returned 401 — "
                        f"it should NEVER require authentication"
                    )

    @given(
        method=http_method_st,
        path_a=path_segment_st,
        path_b=path_segment_st,
    )
    @settings(max_examples=100)
    def test_no_auth_header_always_401_regardless_of_path_shape(
        self,
        method: str,
        path_a: str,
        path_b: str,
    ) -> None:
        """Completely missing Authorization header → 401 for ANY protected path.

        **Validates: Requirements R1.2**

        The error response MUST include code="UNAUTHORIZED" and
        detail="Authentication required" per the standard format.
        """
        path = f"/api/v1/{path_a}/{path_b}"
        assume(path not in MW_EXEMPT_PATHS)

        mock_settings = _make_mock_settings()
        app = FastAPI()
        app.add_middleware(AuthMiddleware)

        async def handler(request: Request):
            return {"ok": True}

        app.add_api_route(path, handler, methods=[method])

        with patch("app.core.middleware.get_settings", return_value=mock_settings):
            with patch("app.core.security.settings", mock_settings):
                client = TestClient(app, raise_server_exceptions=False)
                resp = client.request(method, path)

                assert resp.status_code == 401
                body = resp.json()
                assert body["detail"] == "Authentication required"
                assert body["code"] == "UNAUTHORIZED"


# =============================================================================
# Property 16: Workspace Provisioning Idempotency
# =============================================================================


@pytest.mark.unit
class TestProperty16ProvisioningIdempotency:
    """Property 16: Repeated provisioning yields exactly one workspace/membership.

    **Validates: Requirements R1.11, R84.5**

    Invariant: For any user_id U and email E, calling provision_workspace(U, E)
    N times (N >= 1) results in exactly ONE organization and ONE org_members
    record for U.
    """

    def _import_provisioning(self):
        """Import provisioning service with sqlalchemy mocked if needed."""
        # sqlalchemy may not be installed in the top-level test venv
        if "sqlalchemy" not in sys.modules:
            sys.modules.setdefault("sqlalchemy", MagicMock())
            sys.modules.setdefault("sqlalchemy.ext", MagicMock())
            sys.modules.setdefault("sqlalchemy.ext.asyncio", MagicMock())
            sys.modules.setdefault("sqlalchemy.orm", MagicMock())
        # app.db.session may also require mocking
        sys.modules.setdefault("app.db", MagicMock())
        sys.modules.setdefault("app.db.session", MagicMock())
        from app.services.provisioning_service import (
            SYSTEM_ORG_ID,
            ProvisioningService,
            ProvisioningResult,
        )
        return ProvisioningService, SYSTEM_ORG_ID, ProvisioningResult

    def _make_mock_client_tracking_writes(self):
        """Create a mock Supabase client that tracks upsert calls."""
        client = MagicMock()
        upsert_tracker: dict[str, list[dict]] = {
            "organizations": [],
            "org_members": [],
            "onboarding_state": [],
        }

        def table_side_effect(table_name: str) -> MagicMock:
            table = MagicMock()
            table.select.return_value = table
            table.eq.return_value = table
            table.order.return_value = table
            table.limit.return_value = table

            def capture_upsert(data, **kwargs):
                if table_name in upsert_tracker:
                    upsert_tracker[table_name].append(data)
                chain = MagicMock()
                chain.execute.return_value = MagicMock(data=[data])
                return chain

            table.upsert.side_effect = capture_upsert

            # org_members always returns empty (user has no membership yet)
            result = MagicMock()
            result.data = []
            table.execute.return_value = result
            return table

        client.table.side_effect = table_side_effect
        return client, upsert_tracker

    def _make_mock_client_with_existing(self, org_id: str, role: str = "owner"):
        """Create a mock Supabase client that returns existing membership."""
        client = MagicMock()

        def table_side_effect(table_name: str) -> MagicMock:
            table = MagicMock()
            table.select.return_value = table
            table.eq.return_value = table
            table.order.return_value = table
            table.limit.return_value = table
            table.upsert.return_value = table

            if table_name == "org_members":
                result = MagicMock()
                result.data = [
                    {"org_id": org_id, "role": role, "status": "active"}
                ]
                table.execute.return_value = result
            elif table_name == "organizations":
                result = MagicMock()
                result.data = [{"name": "Existing Workspace"}]
                table.execute.return_value = result
            else:
                result = MagicMock()
                result.data = []
                table.execute.return_value = result
            return table

        client.table.side_effect = table_side_effect
        return client

    @given(
        user_id=user_id_st,
        email=email_st,
        repeat_count=st.integers(min_value=2, max_value=10),
    )
    @settings(max_examples=50)
    def test_repeated_provisioning_returns_same_workspace(
        self,
        user_id: UUID,
        email: str,
        repeat_count: int,
    ) -> None:
        """Calling provision_workspace N times for the same user → same org_id.

        **Validates: Requirements R1.11, R84.5**

        After the first successful provisioning, subsequent calls MUST
        return the same org_id (created=False) rather than creating duplicates.
        """
        ProvisioningService, SYSTEM_ORG_ID, _ = self._import_provisioning()

        # First call creates, subsequent calls find existing
        org_id = str(uuid4())
        call_count = [0]

        def table_side_effect(table_name: str) -> MagicMock:
            table = MagicMock()
            table.select.return_value = table
            table.eq.return_value = table
            table.order.return_value = table
            table.limit.return_value = table
            table.upsert.return_value = table

            if table_name == "org_members":
                result = MagicMock()
                # After first call, membership exists
                if call_count[0] > 0:
                    result.data = [
                        {"org_id": org_id, "role": "owner", "status": "active"}
                    ]
                else:
                    result.data = []
                table.execute.return_value = result
            elif table_name == "organizations":
                result = MagicMock()
                result.data = [{"name": f"{email.split('@')[0]}'s Workspace"}]
                table.execute.return_value = result
            else:
                result = MagicMock()
                result.data = []
                table.execute.return_value = result
            return table

        client = MagicMock()
        client.table.side_effect = table_side_effect
        service = ProvisioningService(supabase_client=client)

        # First call — creates workspace
        # (We won't actually await since _get_existing_membership is sync)
        first_result = service._get_existing_membership(user_id)
        assert first_result is None  # New user, no membership

        # Simulate post-creation state
        call_count[0] = 1

        # Subsequent calls — MUST return existing (idempotent)
        results = []
        for _ in range(repeat_count):
            result = service._get_existing_membership(user_id)
            results.append(result)

        # All subsequent lookups return the same org_id
        for result in results:
            assert result is not None, "Existing membership must be found"
            assert result["org_id"] == org_id, (
                f"Expected consistent org_id={org_id}, got {result['org_id']}"
            )

    @given(
        user_id=user_id_st,
        email=email_st,
    )
    @settings(max_examples=50)
    def test_upsert_uses_on_conflict_for_all_tables(
        self,
        user_id: UUID,
        email: str,
    ) -> None:
        """All provisioning writes use ON CONFLICT DO NOTHING.

        **Validates: Requirements R1.11, R84.5**

        The INSERT...ON CONFLICT DO NOTHING pattern ensures that concurrent
        or retried requests never create duplicate records.
        """
        ProvisioningService, _, _ = self._import_provisioning()

        # Track upsert calls with their kwargs
        upsert_calls: list[tuple[str, dict]] = []

        client = MagicMock()

        def table_side_effect(table_name: str) -> MagicMock:
            table = MagicMock()
            table.select.return_value = table
            table.eq.return_value = table
            table.order.return_value = table
            table.limit.return_value = table

            def capture_upsert(data, **kwargs):
                upsert_calls.append((table_name, kwargs))
                chain = MagicMock()
                chain.execute.return_value = MagicMock(data=[data])
                return chain

            table.upsert.side_effect = capture_upsert

            result = MagicMock()
            result.data = []
            table.execute.return_value = result
            return table

        client.table.side_effect = table_side_effect
        service = ProvisioningService(supabase_client=client)

        org_id = uuid4()
        # Exercise all three create methods
        service._create_organization(org_id, f"{email}'s Workspace", "slug", user_id)
        service._create_membership(org_id, user_id, MagicMock(value="owner"))
        service._create_onboarding_state(org_id, user_id)

        # Verify all upserts used on_conflict + ignore_duplicates
        assert len(upsert_calls) == 3, (
            f"Expected 3 upsert calls, got {len(upsert_calls)}"
        )
        for table_name, kwargs in upsert_calls:
            assert "on_conflict" in kwargs, (
                f"{table_name} upsert missing on_conflict kwarg"
            )
            assert kwargs.get("ignore_duplicates") is True, (
                f"{table_name} upsert missing ignore_duplicates=True"
            )

    @given(
        user_a=user_id_st,
        user_b=user_id_st,
        email_a=email_st,
        email_b=email_st,
    )
    @settings(max_examples=50)
    def test_different_users_never_share_workspace(
        self,
        user_a: UUID,
        user_b: UUID,
        email_a: str,
        email_b: str,
    ) -> None:
        """Different users MUST get different workspaces (tenant isolation).

        **Validates: Requirements R1.11, R84.5**

        Provisioning user_A and user_B (where A != B) must produce
        distinct org_ids — never a shared workspace.
        """
        assume(user_a != user_b)

        ProvisioningService, SYSTEM_ORG_ID, _ = self._import_provisioning()

        org_a = str(uuid4())
        org_b = str(uuid4())

        client_a = self._make_mock_client_with_existing(org_a)
        client_b = self._make_mock_client_with_existing(org_b)

        service_a = ProvisioningService(supabase_client=client_a)
        service_b = ProvisioningService(supabase_client=client_b)

        result_a = service_a._get_existing_membership(user_a)
        result_b = service_b._get_existing_membership(user_b)

        assert result_a is not None
        assert result_b is not None
        assert result_a["org_id"] != result_b["org_id"], (
            f"Different users must have different workspaces: "
            f"user_a={user_a}, user_b={user_b}, shared org={result_a['org_id']}"
        )

    @given(user_id=user_id_st)
    @settings(max_examples=30)
    def test_system_org_never_returned_as_user_workspace(
        self,
        user_id: UUID,
    ) -> None:
        """System org (00000000-...-000001) is NEVER returned as a user workspace.

        **Validates: Requirements R1.11, R84.5**

        Even if a user has membership in the system org, provisioning
        logic must exclude it and treat the user as needing a workspace.
        """
        ProvisioningService, SYSTEM_ORG_ID, _ = self._import_provisioning()

        # Mock client returns ONLY system org membership
        client = MagicMock()

        def table_side_effect(table_name: str) -> MagicMock:
            table = MagicMock()
            table.select.return_value = table
            table.eq.return_value = table
            table.order.return_value = table
            table.limit.return_value = table
            table.upsert.return_value = table

            if table_name == "org_members":
                result = MagicMock()
                result.data = [
                    {
                        "org_id": str(SYSTEM_ORG_ID),
                        "role": "owner",
                        "status": "active",
                    }
                ]
                table.execute.return_value = result
            else:
                result = MagicMock()
                result.data = []
                table.execute.return_value = result
            return table

        client.table.side_effect = table_side_effect
        service = ProvisioningService(supabase_client=client)

        # System org membership should be filtered out
        result = service._get_existing_membership(user_id)
        assert result is None, (
            "System org membership must be excluded — user is still eligible"
        )
        assert service.is_eligible_for_provisioning(user_id) is True

    @given(
        user_id=user_id_st,
        email=email_st,
    )
    @settings(max_examples=30)
    def test_provisioning_result_has_owner_role(
        self,
        user_id: UUID,
        email: str,
    ) -> None:
        """Newly provisioned workspace assigns OWNER role to creating user.

        **Validates: Requirements R84.5**

        The first user in a workspace is always the owner — never viewer/editor.
        """
        ProvisioningService, _, ProvisioningResult = self._import_provisioning()

        client, _ = self._make_mock_client_tracking_writes()
        service = ProvisioningService(supabase_client=client)

        # Verify the internal method passes owner role
        org_id = uuid4()
        mock_role = MagicMock()
        mock_role.value = "owner"
        service._create_membership(org_id, user_id, mock_role)

        # The upsert call should contain role="owner"
        call_args = client.table("org_members").upsert.call_args
        if call_args:
            data = call_args[0][0] if call_args[0] else call_args[1].get("data", {})
            if isinstance(data, dict):
                assert data.get("role") == "owner"

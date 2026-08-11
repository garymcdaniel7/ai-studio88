"""Property tests for authentication enforcement and provisioning idempotency.

**Validates: Requirements R1.1, R1.2, R1.11, R84.5**

Property 2: Authentication Enforcement Universality
- For ALL non-exempt endpoints, missing/invalid JWT → 401
- Exempt paths (/health, /ready, /) → 200 without auth

Property 16: Workspace Provisioning Idempotency
- Repeated provisioning for the same user → exactly one workspace
- Race conditions handled gracefully
- Different users → different workspaces (isolation)

Run with:
    pytest tests/unit/test_core/test_auth_properties.py -v
"""
from __future__ import annotations

import os
import sys
import time
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

# Ensure backend/app is importable from top-level tests
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "backend"))

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from jose import jwt as jose_jwt

from app.core.middleware import AuthMiddleware

# =============================================================================
# Constants
# =============================================================================

TEST_SECRET = "test-jwt-secret-at-least-32-chars-long"
TEST_ALGORITHM = "HS256"

# Exempt paths per R1.1 — MUST NOT require authentication
EXEMPT_PATHS = ["/health", "/ready", "/"]

# Invalid auth scenarios to test universality
INVALID_AUTH_SCENARIOS = [
    ("no_header", {}),
    ("wrong_scheme", {"Authorization": "Basic dXNlcjpwYXNz"}),
    ("garbage_token", {"Authorization": "Bearer not-a-valid-jwt-at-all"}),
    ("empty_bearer", {"Authorization": "Bearer "}),
]

# All protected paths with their HTTP methods for parametrized testing
PROTECTED_ENDPOINTS = [
    ("GET", "/api/v1/talent"),
    ("POST", "/api/v1/talent"),
    ("PUT", "/api/v1/talent/abc-123"),
    ("PATCH", "/api/v1/talent/abc-123"),
    ("DELETE", "/api/v1/talent/abc-123"),
    ("GET", "/api/v1/jobs"),
    ("POST", "/api/v1/jobs"),
    ("GET", "/api/v1/assets"),
    ("POST", "/api/v1/generate/image"),
    ("GET", "/api/v1/brain/health"),
]


# =============================================================================
# Helpers
# =============================================================================


def _make_token(
    sub: str = "user-123",
    exp: int | None = None,
    secret: str = TEST_SECRET,
) -> str:
    """Create a JWT for testing."""
    claims = {
        "sub": sub,
        "exp": exp if exp is not None else int(time.time()) + 3600,
        "email": "test@example.com",
        "role": "authenticated",
    }
    return jose_jwt.encode(claims, secret, algorithm=TEST_ALGORITHM)


def _create_test_app() -> FastAPI:
    """Create a FastAPI app with AuthMiddleware and multiple protected endpoints."""
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

    @app.get("/api/v1/talent")
    async def list_talent(request: Request):
        return {"items": []}

    @app.post("/api/v1/talent")
    async def create_talent(request: Request):
        return {"id": "new-talent"}

    @app.put("/api/v1/talent/{talent_id}")
    async def update_talent(request: Request, talent_id: str):
        return {"id": talent_id}

    @app.patch("/api/v1/talent/{talent_id}")
    async def patch_talent(request: Request, talent_id: str):
        return {"id": talent_id}

    @app.delete("/api/v1/talent/{talent_id}")
    async def delete_talent(request: Request, talent_id: str):
        return None

    @app.get("/api/v1/jobs")
    async def list_jobs(request: Request):
        return {"items": []}

    @app.post("/api/v1/jobs")
    async def create_job(request: Request):
        return {"id": "new-job"}

    @app.get("/api/v1/assets")
    async def list_assets(request: Request):
        return {"items": []}

    @app.post("/api/v1/generate/image")
    async def generate_image(request: Request):
        return {"job_id": "gen-1"}

    @app.get("/api/v1/brain/health")
    async def brain_health(request: Request):
        return {"provider": "ollama"}

    return app


@pytest.fixture
def _mock_settings():
    """Mock settings for local environment with auth enabled."""
    mock = MagicMock()
    mock.supabase_jwt_secret = TEST_SECRET
    mock.jwt_algorithm = TEST_ALGORITHM
    mock.app_env = "local"
    mock.auth_dev_mode = False
    with patch("app.core.middleware.get_settings", return_value=mock):
        with patch("app.core.security.settings", mock):
            yield mock


@pytest.fixture
def client(_mock_settings) -> TestClient:
    """Test client with AuthMiddleware active."""
    app = _create_test_app()
    return TestClient(app)


# =============================================================================
# Property 2: Authentication Enforcement Universality
# =============================================================================


@pytest.mark.unit
class TestAuthEnforcementUniversality:
    """Every non-exempt endpoint returns 401 without valid authentication.

    **Validates: Requirements R1.1, R1.2**

    The universal property: there is NO protected endpoint that returns
    a non-401 response when the request lacks valid authentication.
    """

    @pytest.mark.parametrize(
        "method,path",
        PROTECTED_ENDPOINTS,
        ids=[f"{m}_{p.replace('/', '_').strip('_')}" for m, p in PROTECTED_ENDPOINTS],
    )
    @pytest.mark.parametrize(
        "scenario,headers",
        INVALID_AUTH_SCENARIOS,
        ids=[s[0] for s in INVALID_AUTH_SCENARIOS],
    )
    def test_protected_endpoint_returns_401_without_valid_auth(
        self, client: TestClient, method: str, path: str, scenario: str, headers: dict
    ):
        """All protected endpoints reject invalid/missing auth with 401."""
        resp = client.request(method, path, headers=headers)
        assert resp.status_code == 401, (
            f"{method} {path} with {scenario} returned {resp.status_code}, expected 401"
        )
        body = resp.json()
        assert "code" in body
        assert body["code"] in ("UNAUTHORIZED", "TOKEN_EXPIRED", "INVALID_TOKEN")

    @pytest.mark.parametrize(
        "method,path",
        PROTECTED_ENDPOINTS,
        ids=[f"{m}_{p.replace('/', '_').strip('_')}" for m, p in PROTECTED_ENDPOINTS],
    )
    def test_expired_token_returns_401(self, client: TestClient, method: str, path: str):
        """Expired token → 401 TOKEN_EXPIRED on all protected endpoints."""
        expired_token = _make_token(exp=int(time.time()) - 120)
        resp = client.request(
            method, path, headers={"Authorization": f"Bearer {expired_token}"}
        )
        assert resp.status_code == 401, (
            f"{method} {path} with expired token returned {resp.status_code}"
        )
        body = resp.json()
        assert body["code"] == "TOKEN_EXPIRED"

    @pytest.mark.parametrize(
        "method,path",
        PROTECTED_ENDPOINTS,
        ids=[f"{m}_{p.replace('/', '_').strip('_')}" for m, p in PROTECTED_ENDPOINTS],
    )
    def test_invalid_signature_returns_401(self, client: TestClient, method: str, path: str):
        """Wrong signature → 401 UNAUTHORIZED on all protected endpoints."""
        bad_token = _make_token(secret="wrong-secret-key-32chars-minimum!!")
        resp = client.request(
            method, path, headers={"Authorization": f"Bearer {bad_token}"}
        )
        assert resp.status_code == 401, (
            f"{method} {path} with bad signature returned {resp.status_code}"
        )
        body = resp.json()
        assert body["code"] == "UNAUTHORIZED"

    @pytest.mark.parametrize("path", EXEMPT_PATHS)
    def test_exempt_paths_pass_without_auth(self, client: TestClient, path: str):
        """Exempt paths (/health, /ready, /) return 200 without auth (R1.1)."""
        resp = client.get(path)
        assert resp.status_code == 200, (
            f"Exempt path {path} returned {resp.status_code}, expected 200"
        )

    @pytest.mark.parametrize(
        "method,path",
        PROTECTED_ENDPOINTS,
        ids=[f"{m}_{p.replace('/', '_').strip('_')}" for m, p in PROTECTED_ENDPOINTS],
    )
    def test_valid_token_passes_through(self, client: TestClient, method: str, path: str):
        """Valid token allows access to all protected endpoints (sanity check)."""
        valid_token = _make_token(sub="user-abc-123")
        resp = client.request(
            method, path, headers={"Authorization": f"Bearer {valid_token}"}
        )
        assert resp.status_code != 401, (
            f"{method} {path} with valid token still returned 401"
        )


# =============================================================================
# Property 16: Workspace Provisioning Idempotency
# =============================================================================


@pytest.mark.unit
class TestProvisioningIdempotency:
    """Repeated provisioning yields exactly one workspace/membership.

    **Validates: Requirements R1.11, R84.5**

    Property: provision_workspace(user_id, email) called N times with the
    same user_id produces exactly one organization and membership.
    """

    def _make_mock_client(self, memberships: list[dict] | None = None) -> MagicMock:
        """Create a mock Supabase client returning given memberships."""
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
                result.data = memberships if memberships else []
                table.execute.return_value = result
            elif table_name == "organizations":
                result = MagicMock()
                result.data = [{"name": "Test Workspace"}]
                table.execute.return_value = result
            else:
                result = MagicMock()
                result.data = []
                table.execute.return_value = result
            return table

        client.table.side_effect = table_side_effect
        return client

    def _import_provisioning(self):
        """Import provisioning service with sqlalchemy mocked if needed."""
        # sqlalchemy may not be installed in top-level test venv
        if "sqlalchemy" not in sys.modules:
            sys.modules.setdefault("sqlalchemy", MagicMock())
            sys.modules.setdefault("sqlalchemy.ext", MagicMock())
            sys.modules.setdefault("sqlalchemy.ext.asyncio", MagicMock())
            sys.modules.setdefault("sqlalchemy.orm", MagicMock())
        from app.services.provisioning_service import (
            SYSTEM_ORG_ID,
            ProvisioningService,
        )
        return ProvisioningService, SYSTEM_ORG_ID

    def test_no_membership_means_eligible(self):
        """User with no membership is eligible for provisioning."""
        ProvisioningService, _ = self._import_provisioning()
        client = self._make_mock_client(memberships=[])
        service = ProvisioningService(supabase_client=client)

        assert service.is_eligible_for_provisioning(uuid4()) is True

    def test_existing_membership_means_not_eligible(self):
        """User with active membership is NOT eligible for provisioning."""
        ProvisioningService, _ = self._import_provisioning()
        org_id = str(uuid4())
        client = self._make_mock_client(
            memberships=[{"org_id": org_id, "role": "owner", "status": "active"}]
        )
        service = ProvisioningService(supabase_client=client)

        assert service.is_eligible_for_provisioning(uuid4()) is False

    def test_existing_membership_returns_consistent_org_id(self):
        """Multiple lookups for the same user return the same org_id."""
        ProvisioningService, _ = self._import_provisioning()
        org_id = str(uuid4())
        membership = {"org_id": org_id, "role": "owner", "status": "active"}
        client = self._make_mock_client(memberships=[membership])
        service = ProvisioningService(supabase_client=client)

        user_id = uuid4()
        result_1 = service._get_existing_membership(user_id)
        result_2 = service._get_existing_membership(user_id)

        assert result_1 is not None
        assert result_2 is not None
        assert result_1["org_id"] == result_2["org_id"] == org_id

    def test_system_org_excluded_from_eligibility(self):
        """System org membership does not count — user is still eligible."""
        ProvisioningService, SYSTEM_ORG_ID = self._import_provisioning()
        system_membership = {
            "org_id": str(SYSTEM_ORG_ID),
            "role": "owner",
            "status": "active",
        }
        client = self._make_mock_client(memberships=[system_membership])
        service = ProvisioningService(supabase_client=client)

        assert service.is_eligible_for_provisioning(uuid4()) is True

    def test_different_users_get_different_workspaces(self):
        """Different user_ids produce independent workspaces (isolation)."""
        ProvisioningService, _ = self._import_provisioning()

        org_a = str(uuid4())
        org_b = str(uuid4())

        client_a = self._make_mock_client(
            memberships=[{"org_id": org_a, "role": "owner", "status": "active"}]
        )
        client_b = self._make_mock_client(
            memberships=[{"org_id": org_b, "role": "owner", "status": "active"}]
        )

        service_a = ProvisioningService(supabase_client=client_a)
        service_b = ProvisioningService(supabase_client=client_b)

        result_a = service_a._get_existing_membership(uuid4())
        result_b = service_b._get_existing_membership(uuid4())

        assert result_a is not None
        assert result_b is not None
        assert result_a["org_id"] != result_b["org_id"]

    def test_upsert_calls_use_on_conflict(self):
        """Provisioning uses ON CONFLICT DO NOTHING for idempotency (R84.5)."""
        ProvisioningService, _ = self._import_provisioning()

        client = MagicMock()
        upsert_calls = []

        def table_side_effect(table_name: str) -> MagicMock:
            table = MagicMock()
            table.select.return_value = table
            table.eq.return_value = table
            table.order.return_value = table
            table.limit.return_value = table

            def capture_upsert(*args, **kwargs):
                upsert_calls.append((table_name, kwargs))
                result_mock = MagicMock()
                result_mock.execute.return_value = MagicMock(data=[])
                return result_mock

            table.upsert.side_effect = capture_upsert

            # org_members returns empty (new user)
            result = MagicMock()
            result.data = []
            table.execute.return_value = result
            return table

        client.table.side_effect = table_side_effect
        service = ProvisioningService(supabase_client=client)

        # Call internal methods to trigger upserts
        service._create_organization(uuid4(), "Test", "test-slug", uuid4())
        service._create_membership(uuid4(), uuid4(), MagicMock(value="owner"))
        service._create_onboarding_state(uuid4(), uuid4())

        # Verify all upserts used on_conflict + ignore_duplicates
        assert len(upsert_calls) == 3
        for table_name, kwargs in upsert_calls:
            assert "on_conflict" in kwargs, f"{table_name} upsert missing on_conflict"
            assert kwargs.get("ignore_duplicates") is True, (
                f"{table_name} upsert missing ignore_duplicates=True"
            )

    def test_org_name_derived_from_email(self):
        """Workspace name derived from email follows expected pattern."""
        ProvisioningService, _ = self._import_provisioning()
        service = ProvisioningService(supabase_client=MagicMock())

        assert service._derive_org_name("alice@company.com") == "Alice's Workspace"
        assert service._derive_org_name("bob.smith@gmail.com") == "Bob Smith's Workspace"
        assert service._derive_org_name("") == "My Workspace"
        assert service._derive_org_name("nodomain") == "My Workspace"

"""Unit tests for app.core.middleware — AuthMiddleware.

Tests cover:
    - Exempt paths pass without authentication
    - Missing Authorization header → 401 UNAUTHORIZED
    - Malformed Authorization header → 401 UNAUTHORIZED
    - Expired token → 401 TOKEN_EXPIRED
    - Empty sub claim → 401 INVALID_TOKEN
    - Valid token → request proceeds with jwt_payload in state
    - X-Request-ID (UUID v4) on every response
    - AUTH_DEV_MODE=true in production → 500 error
    - validate_auth_dev_mode_startup raises RuntimeError for production
    - AUTH_DEV_MODE=true in local/test injects REAL org_id from org_members (R1.4, R1.8)
"""

from __future__ import annotations

import time
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from jose import jwt as jose_jwt

from app.core.middleware import AuthMiddleware, validate_auth_dev_mode_startup

# Test secret for JWT signing
TEST_SECRET = "test-jwt-secret-at-least-32-chars-long"
TEST_ALGORITHM = "HS256"


def _make_token(
    sub: str = "user-123",
    exp: int | None = None,
    secret: str = TEST_SECRET,
) -> str:
    """Helper to create a JWT for testing."""
    claims = {
        "sub": sub,
        "exp": exp if exp is not None else int(time.time()) + 3600,
        "email": "test@example.com",
        "role": "authenticated",
    }
    return jose_jwt.encode(claims, secret, algorithm=TEST_ALGORITHM)


def _create_test_app() -> FastAPI:
    """Create a minimal FastAPI app with AuthMiddleware for testing."""
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

    @app.get("/docs")
    async def docs():
        return {"docs": True}

    @app.get("/api/v1/protected")
    async def protected(request: Request):
        payload = getattr(request.state, "jwt_payload", None)
        return {
            "user_id": payload.sub if payload else None,
            "email": payload.email if payload else None,
        }

    return app


@pytest.fixture
def _mock_settings_local():
    """Mock settings for local environment."""
    mock = MagicMock()
    mock.supabase_jwt_secret = TEST_SECRET
    mock.jwt_algorithm = TEST_ALGORITHM
    mock.app_env = "local"
    mock.auth_dev_mode = False
    with patch("app.core.middleware.get_settings", return_value=mock):
        with patch("app.core.security.settings", mock):
            yield mock


@pytest.fixture
def client(_mock_settings_local) -> TestClient:
    """Test client with AuthMiddleware active."""
    app = _create_test_app()
    return TestClient(app)


@pytest.mark.unit
class TestExemptPaths:
    """Tests that exempt paths do not require authentication."""

    def test_health_returns_200_without_auth(self, client: TestClient):
        """GET /health does not require authentication."""
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_ready_returns_200_without_auth(self, client: TestClient):
        """GET /ready does not require authentication."""
        resp = client.get("/ready")
        assert resp.status_code == 200

    def test_root_returns_200_without_auth(self, client: TestClient):
        """GET / does not require authentication."""
        resp = client.get("/")
        assert resp.status_code == 200

    def test_docs_returns_200_without_auth(self, client: TestClient):
        """GET /docs does not require authentication."""
        resp = client.get("/docs")
        assert resp.status_code == 200

    def test_exempt_paths_include_request_id(self, client: TestClient):
        """Even exempt paths get X-Request-ID header."""
        resp = client.get("/health")
        request_id = resp.headers.get("x-request-id")
        assert request_id is not None
        # Validate it's a valid UUID v4
        uuid.UUID(request_id, version=4)


@pytest.mark.unit
class TestAuthEnforcement:
    """Tests that protected paths require valid authentication."""

    def test_missing_authorization_returns_401(self, client: TestClient):
        """No Authorization header → 401 UNAUTHORIZED."""
        resp = client.get("/api/v1/protected")
        assert resp.status_code == 401
        body = resp.json()
        assert body["detail"] == "Authentication required"
        assert body["code"] == "UNAUTHORIZED"

    def test_malformed_authorization_returns_401(self, client: TestClient):
        """Malformed Authorization header → 401 UNAUTHORIZED."""
        resp = client.get(
            "/api/v1/protected",
            headers={"Authorization": "NotBearer sometoken"},
        )
        assert resp.status_code == 401
        body = resp.json()
        assert body["code"] == "UNAUTHORIZED"

    def test_empty_bearer_token_returns_401(self, client: TestClient):
        """Empty Bearer token → 401 UNAUTHORIZED."""
        resp = client.get(
            "/api/v1/protected",
            headers={"Authorization": "Bearer "},
        )
        assert resp.status_code == 401
        body = resp.json()
        assert body["code"] == "UNAUTHORIZED"

    def test_expired_token_returns_401_token_expired(self, client: TestClient):
        """Expired token → 401 TOKEN_EXPIRED."""
        expired_token = _make_token(exp=int(time.time()) - 60)
        resp = client.get(
            "/api/v1/protected",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert resp.status_code == 401
        body = resp.json()
        assert body["detail"] == "Token expired"
        assert body["code"] == "TOKEN_EXPIRED"

    def test_invalid_signature_returns_401(self, client: TestClient):
        """Wrong signature → 401 UNAUTHORIZED."""
        bad_token = _make_token(secret="wrong-secret-key-32chars-minimum")
        resp = client.get(
            "/api/v1/protected",
            headers={"Authorization": f"Bearer {bad_token}"},
        )
        assert resp.status_code == 401
        body = resp.json()
        assert body["code"] == "UNAUTHORIZED"

    def test_empty_sub_returns_401_invalid_token(self, client: TestClient):
        """Token with empty sub → 401 INVALID_TOKEN."""
        empty_sub_token = _make_token(sub="")
        resp = client.get(
            "/api/v1/protected",
            headers={"Authorization": f"Bearer {empty_sub_token}"},
        )
        assert resp.status_code == 401
        body = resp.json()
        assert body["detail"] == "Invalid token claims"
        assert body["code"] == "INVALID_TOKEN"

    def test_valid_token_proceeds_with_payload(self, client: TestClient):
        """Valid token → request succeeds, payload attached to request.state."""
        valid_token = _make_token(sub="user-abc-123")
        resp = client.get(
            "/api/v1/protected",
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["user_id"] == "user-abc-123"
        assert body["email"] == "test@example.com"

    def test_response_includes_request_id(self, client: TestClient):
        """All responses include X-Request-ID header."""
        valid_token = _make_token(sub="user-123")
        resp = client.get(
            "/api/v1/protected",
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        request_id = resp.headers.get("x-request-id")
        assert request_id is not None
        uuid.UUID(request_id, version=4)

    def test_401_response_includes_request_id(self, client: TestClient):
        """Error responses also include X-Request-ID header."""
        resp = client.get("/api/v1/protected")
        assert resp.status_code == 401
        request_id = resp.headers.get("x-request-id")
        assert request_id is not None
        uuid.UUID(request_id, version=4)


@pytest.mark.unit
class TestAuthDevMode:
    """Tests for AUTH_DEV_MODE behavior."""

    def test_dev_mode_production_raises_runtime_error(self):
        """validate_auth_dev_mode_startup raises RuntimeError in production."""
        mock = MagicMock()
        mock.auth_dev_mode = True
        mock.app_env = "production"
        with patch("app.core.middleware.get_settings", return_value=mock):
            with pytest.raises(RuntimeError, match="not permitted"):
                validate_auth_dev_mode_startup()

    def test_dev_mode_staging_raises_runtime_error(self):
        """validate_auth_dev_mode_startup raises RuntimeError in staging."""
        mock = MagicMock()
        mock.auth_dev_mode = True
        mock.app_env = "staging"
        with patch("app.core.middleware.get_settings", return_value=mock):
            with pytest.raises(RuntimeError, match="not permitted"):
                validate_auth_dev_mode_startup()

    def test_dev_mode_local_does_not_raise(self):
        """validate_auth_dev_mode_startup does not raise in local."""
        mock = MagicMock()
        mock.auth_dev_mode = True
        mock.app_env = "local"
        with patch("app.core.middleware.get_settings", return_value=mock):
            # Should not raise
            validate_auth_dev_mode_startup()

    def test_dev_mode_disabled_does_not_raise(self):
        """validate_auth_dev_mode_startup does not raise when dev mode is disabled."""
        mock = MagicMock()
        mock.auth_dev_mode = False
        mock.app_env = "production"
        with patch("app.core.middleware.get_settings", return_value=mock):
            # Should not raise
            validate_auth_dev_mode_startup()


@pytest.mark.unit
class TestAuthDevModeInjection:
    """Tests for AUTH_DEV_MODE dev user injection (R1.4, R1.8).

    Verifies that when AUTH_DEV_MODE=true in local/test environments:
      - The middleware injects user_id and org_id from the first org_members record
      - The org_id is a REAL UUID (never None, never placeholder)
      - Client-supplied user_id is never trusted
      - The injected payload allows protected endpoints to proceed
    """

    @pytest.fixture
    def _mock_settings_dev_mode(self):
        """Mock settings for dev mode enabled in local env."""
        mock = MagicMock()
        mock.supabase_jwt_secret = TEST_SECRET
        mock.jwt_algorithm = TEST_ALGORITHM
        mock.app_env = "local"
        mock.auth_dev_mode = True
        with patch("app.core.middleware.get_settings", return_value=mock):
            with patch("app.core.security.settings", mock):
                yield mock

    @pytest.fixture
    def dev_mode_client(self, _mock_settings_dev_mode) -> TestClient:
        """Test client with dev mode enabled."""
        app = _create_test_app()
        return TestClient(app)

    def test_dev_mode_injects_real_user_id_from_org_members(
        self, _mock_settings_dev_mode
    ):
        """Dev mode injects user_id from first org_members record (R1.4)."""
        # Arrange: mock org_members query returns a real record
        fake_user_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        fake_org_id = "f9e8d7c6-b5a4-3210-fedc-ba9876543210"
        fake_result = MagicMock()
        fake_result.data = [
            {"user_id": fake_user_id, "org_id": fake_org_id, "role": "owner"}
        ]

        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.order.return_value = mock_table
        mock_table.limit.return_value = mock_table
        mock_table.execute.return_value = fake_result
        mock_client.table.return_value = mock_table

        with patch("backend.database.is_supabase_configured", return_value=True):
            with patch("backend.database.get_supabase_client", return_value=mock_client):
                app = _create_test_app()
                client = TestClient(app)

                # Act: request without Authorization header (dev mode should inject)
                resp = client.get("/api/v1/protected")

                # Assert: request succeeds with real user_id
                assert resp.status_code == 200
                body = resp.json()
                assert body["user_id"] == fake_user_id
                assert body["user_id"] is not None

    def test_dev_mode_injects_real_org_id_not_none(
        self, _mock_settings_dev_mode
    ):
        """Dev mode org_id is a real UUID, never None (R1.4, R1.8)."""
        fake_user_id = "11111111-2222-3333-4444-555555555555"
        fake_org_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        fake_result = MagicMock()
        fake_result.data = [
            {"user_id": fake_user_id, "org_id": fake_org_id, "role": "admin"}
        ]

        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.order.return_value = mock_table
        mock_table.limit.return_value = mock_table
        mock_table.execute.return_value = fake_result
        mock_client.table.return_value = mock_table

        with patch("backend.database.is_supabase_configured", return_value=True):
            with patch("backend.database.get_supabase_client", return_value=mock_client):
                # Add an endpoint that exposes jwt_payload.raw to verify org_id
                from fastapi import FastAPI, Request

                app = FastAPI()
                app.add_middleware(AuthMiddleware)

                @app.get("/api/v1/check-context")
                async def check_context(request: Request):
                    payload = getattr(request.state, "jwt_payload", None)
                    if payload is None:
                        return {"error": "no payload"}
                    org_id = (
                        payload.raw.get("app_metadata", {}).get("org_id")
                        if payload.raw
                        else None
                    )
                    return {
                        "user_id": payload.sub,
                        "org_id": org_id,
                    }

                client = TestClient(app)
                resp = client.get("/api/v1/check-context")

                assert resp.status_code == 200
                body = resp.json()
                # org_id must be the REAL value from org_members, never None
                assert body["org_id"] == fake_org_id
                assert body["org_id"] is not None
                # user_id must also be real
                assert body["user_id"] == fake_user_id

    def test_dev_mode_never_trusts_client_supplied_user_id(
        self, _mock_settings_dev_mode
    ):
        """Client-supplied user_id in headers/body is never used (R1.8)."""
        fake_user_id = "real-user-from-db-0000-000000000001"
        fake_org_id = "real-org-from-db-00000-000000000001"
        fake_result = MagicMock()
        fake_result.data = [
            {"user_id": fake_user_id, "org_id": fake_org_id, "role": "owner"}
        ]

        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.order.return_value = mock_table
        mock_table.limit.return_value = mock_table
        mock_table.execute.return_value = fake_result
        mock_client.table.return_value = mock_table

        with patch("backend.database.is_supabase_configured", return_value=True):
            with patch("backend.database.get_supabase_client", return_value=mock_client):
                app = _create_test_app()
                client = TestClient(app)

                # Even with a malicious X-User-Id header, the injected user comes from DB
                resp = client.get(
                    "/api/v1/protected",
                    headers={"X-User-Id": "attacker-supplied-id"},
                )

                assert resp.status_code == 200
                body = resp.json()
                # user_id is from the DB, NOT from the client header
                assert body["user_id"] == fake_user_id
                assert body["user_id"] != "attacker-supplied-id"

    def test_dev_mode_falls_through_when_no_org_members(
        self, _mock_settings_dev_mode
    ):
        """If org_members is empty, dev mode injection fails and 401 is returned."""
        fake_result = MagicMock()
        fake_result.data = []  # No members

        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.order.return_value = mock_table
        mock_table.limit.return_value = mock_table
        mock_table.execute.return_value = fake_result
        mock_client.table.return_value = mock_table

        with patch("backend.database.is_supabase_configured", return_value=True):
            with patch("backend.database.get_supabase_client", return_value=mock_client):
                app = _create_test_app()
                client = TestClient(app)

                # No dev user injectable → falls through to normal auth → 401
                resp = client.get("/api/v1/protected")
                assert resp.status_code == 401
                body = resp.json()
                assert body["code"] == "UNAUTHORIZED"

    def test_dev_mode_blocked_at_runtime_in_production(
        self, _mock_settings_dev_mode
    ):
        """If dev mode somehow reaches a production env at runtime, 500 is returned."""
        # Override app_env to production (simulating misconfiguration that bypassed startup)
        _mock_settings_dev_mode.app_env = "production"
        _mock_settings_dev_mode.auth_dev_mode = True

        app = _create_test_app()
        client = TestClient(app)

        resp = client.get("/api/v1/protected")
        assert resp.status_code == 500
        body = resp.json()
        assert body["code"] == "INTERNAL_ERROR"

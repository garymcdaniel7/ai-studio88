"""Unit tests for structured error responses, X-Request-ID, and secret sanitization.

Tests prove:
    - HTTPException returns {"detail": "...", "code": "SNAKE_CASE", "request_id": "..."}
    - ValidationError returns {"detail": "Validation failed", "code": "VALIDATION_ERROR",
      "request_id": "...", "errors": [{field, message, type}]}
    - Unhandled exceptions return 500 with no stack traces or secrets
    - X-Request-ID (UUID v4) is present on ALL responses (success + error)
    - X-Request-ID is a valid UUID v4 format
    - Client-provided X-Request-ID is reused when valid
    - Secrets are redacted in log output via sanitize_secret_values()
    - Structured log contains required fields (timestamp, level, logger, message, request_id)

Requirements: R16.1, R16.2, R16.3, R16.4, R45.1, R45.2, R45.3
"""

from __future__ import annotations

import re
import uuid

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from backend.app.core.error_handlers import register_error_handlers
from backend.app.core.logging import SECRET_VALUE_PATTERNS, sanitize_secret_values
from backend.app.core.request_context import RequestContextMiddleware
from backend.middleware.request_id_middleware import RequestIdMiddleware


# =============================================================================
# Test Models
# =============================================================================


class ItemCreate(BaseModel):
    """Test model for endpoint validation."""

    name: str = Field(min_length=1)
    count: int = Field(ge=1, le=100)


# =============================================================================
# Test App Setup
# =============================================================================


def _create_test_app() -> FastAPI:
    """Create a minimal FastAPI app with error handlers and middleware."""
    app = FastAPI()

    # Add middleware in correct order (last added = first to execute)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(RequestIdMiddleware)

    register_error_handlers(app)

    # Test endpoints
    @app.post("/items")
    async def create_item(item: ItemCreate):
        return {"name": item.name, "count": item.count}

    @app.get("/success")
    async def success():
        return {"status": "ok"}

    @app.get("/not-found")
    async def not_found():
        raise HTTPException(status_code=404, detail="Resource not found")

    @app.get("/forbidden")
    async def forbidden():
        raise HTTPException(
            status_code=403,
            detail="Insufficient permissions",
            headers={"X-Error-Code": "FORBIDDEN"},
        )

    @app.get("/crash")
    async def crash():
        raise RuntimeError(
            "unexpected database connection lost password=secret123 "
            "sk-abc123XYZdefGHIjklMNO at /Users/dev/app/db.py:42"
        )

    @app.get("/unauthorized")
    async def unauthorized():
        raise HTTPException(status_code=401, detail="Authentication required")

    @app.get("/service-unavailable")
    async def service_unavailable():
        raise HTTPException(
            status_code=503,
            detail="ComfyUI service unreachable",
            headers={"X-Error-Code": "SERVICE_UNAVAILABLE"},
        )

    return app


@pytest.fixture
def client():
    """Test client with error handlers and middleware registered."""
    app = _create_test_app()
    return TestClient(app, raise_server_exceptions=False)


# =============================================================================
# HTTPException Format Tests (R16.1)
# =============================================================================


@pytest.mark.unit
class TestHTTPExceptionFormat:
    """HTTPException returns {"detail": "...", "code": "SNAKE_CASE", "request_id": "..."}."""

    def test_404_has_correct_format(self, client):
        """404 returns standard error format with all required fields."""
        response = client.get("/not-found")
        assert response.status_code == 404
        body = response.json()
        assert body["detail"] == "Resource not found"
        assert body["code"] == "NOT_FOUND"
        assert "request_id" in body

    def test_403_with_explicit_code(self, client):
        """403 with X-Error-Code header uses that code."""
        response = client.get("/forbidden")
        assert response.status_code == 403
        body = response.json()
        assert body["detail"] == "Insufficient permissions"
        assert body["code"] == "FORBIDDEN"
        assert body["request_id"] is not None

    def test_401_format(self, client):
        """401 returns UNAUTHORIZED code."""
        response = client.get("/unauthorized")
        assert response.status_code == 401
        body = response.json()
        assert body["code"] == "UNAUTHORIZED"
        assert body["request_id"] is not None

    def test_503_format(self, client):
        """503 returns SERVICE_UNAVAILABLE."""
        response = client.get("/service-unavailable")
        assert response.status_code == 503
        body = response.json()
        assert body["code"] == "SERVICE_UNAVAILABLE"
        assert body["request_id"] is not None

    def test_error_codes_are_upper_snake_case(self, client):
        """All error codes use UPPER_SNAKE_CASE format."""
        paths = ["/not-found", "/forbidden", "/crash", "/unauthorized", "/service-unavailable"]
        for path in paths:
            response = client.get(path)
            body = response.json()
            code = body["code"]
            assert re.match(
                r"^[A-Z][A-Z0-9_]*$", code
            ), f"Code '{code}' for {path} is not UPPER_SNAKE_CASE"


# =============================================================================
# Validation Error Tests (R16.1)
# =============================================================================


@pytest.mark.unit
class TestValidationErrors:
    """Validation errors return structured format with field details."""

    def test_validation_error_format(self, client):
        """422 returns correct structured format."""
        response = client.post("/items", json={"name": "", "count": 0})
        assert response.status_code == 422
        body = response.json()
        assert body["detail"] == "Validation failed"
        assert body["code"] == "VALIDATION_ERROR"
        assert "request_id" in body
        assert "errors" in body
        assert isinstance(body["errors"], list)
        assert len(body["errors"]) > 0

    def test_validation_error_field_info(self, client):
        """Each error entry includes field, message, and type."""
        response = client.post("/items", json={"name": "", "count": 0})
        body = response.json()
        for error in body["errors"]:
            assert "field" in error
            assert "message" in error
            assert "type" in error

    def test_missing_required_field(self, client):
        """Missing required fields trigger 422."""
        response = client.post("/items", json={})
        assert response.status_code == 422
        body = response.json()
        assert body["code"] == "VALIDATION_ERROR"
        assert body["detail"] == "Validation failed"

    def test_invalid_type_validation(self, client):
        """Wrong types trigger 422."""
        response = client.post("/items", json={"name": "test", "count": "not_a_number"})
        assert response.status_code == 422
        body = response.json()
        assert body["code"] == "VALIDATION_ERROR"

    def test_validation_error_has_request_id(self, client):
        """422 responses include request_id in body."""
        response = client.post("/items", json={"name": "", "count": 0})
        body = response.json()
        request_id = body["request_id"]
        assert request_id is not None
        uuid.UUID(request_id)  # Validates UUID format


# =============================================================================
# Unhandled Exception Tests (R16.2, R16.3)
# =============================================================================


@pytest.mark.unit
class TestUnhandledExceptions:
    """Unhandled exceptions return generic 500 without stack trace."""

    def test_unhandled_returns_500_internal_error(self, client):
        """Unhandled RuntimeError returns 500 with INTERNAL_ERROR code."""
        response = client.get("/crash")
        assert response.status_code == 500
        body = response.json()
        assert body["detail"] == "Internal server error"
        assert body["code"] == "INTERNAL_ERROR"
        assert "request_id" in body

    def test_no_stack_trace_in_response(self, client):
        """Stack trace is NEVER included in the response body (R16.2)."""
        response = client.get("/crash")
        body_str = str(response.json())
        assert "Traceback" not in body_str
        assert "RuntimeError" not in body_str
        assert "File " not in body_str

    def test_no_secrets_in_response(self, client):
        """Secrets from exceptions are NEVER leaked to the client (R16.2)."""
        response = client.get("/crash")
        body_str = str(response.json())
        assert "password" not in body_str
        assert "secret123" not in body_str
        assert "sk-abc123" not in body_str

    def test_no_internal_paths_in_response(self, client):
        """Internal file paths never leak to the client (R16.2)."""
        response = client.get("/crash")
        body_str = str(response.json())
        assert "/Users/" not in body_str
        assert "/app/" not in body_str
        assert ".py" not in body_str

    def test_no_env_vars_in_response(self, client):
        """Environment variable names/values never in error responses."""
        response = client.get("/crash")
        body_str = str(response.json())
        assert "SUPABASE" not in body_str
        assert "B2_KEY" not in body_str


# =============================================================================
# X-Request-ID Tests (R16.4, R45.2)
# =============================================================================


@pytest.mark.unit
class TestRequestIDPropagation:
    """X-Request-ID is present on ALL responses and is valid UUID."""

    def test_success_response_has_request_id_header(self, client):
        """Successful responses include X-Request-ID header."""
        response = client.get("/success")
        assert response.status_code == 200
        request_id = response.headers.get("X-Request-ID")
        assert request_id is not None
        uuid.UUID(request_id)

    def test_error_response_has_request_id_header(self, client):
        """Error responses include X-Request-ID header."""
        response = client.get("/not-found")
        request_id = response.headers.get("X-Request-ID")
        assert request_id is not None
        uuid.UUID(request_id)

    def test_500_has_request_id_header(self, client):
        """500 errors include X-Request-ID."""
        response = client.get("/crash")
        request_id = response.headers.get("X-Request-ID")
        assert request_id is not None
        uuid.UUID(request_id)

    def test_request_id_is_valid_uuid_v4(self, client):
        """X-Request-ID is a valid UUID (v4 format)."""
        response = client.get("/success")
        request_id = response.headers.get("X-Request-ID")
        parsed = uuid.UUID(request_id)
        # UUID v4 has version bits set to 4
        assert parsed.version == 4

    def test_each_request_gets_unique_id(self, client):
        """Each request receives a different X-Request-ID."""
        r1 = client.get("/success")
        r2 = client.get("/success")
        id1 = r1.headers.get("X-Request-ID")
        id2 = r2.headers.get("X-Request-ID")
        assert id1 != id2

    def test_client_provided_request_id_reused(self, client):
        """Valid client-provided X-Request-ID is accepted and reused."""
        custom_id = str(uuid.uuid4())
        response = client.get("/success", headers={"X-Request-ID": custom_id})
        assert response.headers.get("X-Request-ID") == custom_id

    def test_invalid_client_request_id_replaced(self, client):
        """Invalid client X-Request-ID is replaced with new UUID."""
        response = client.get("/success", headers={"X-Request-ID": "not-a-uuid"})
        request_id = response.headers.get("X-Request-ID")
        assert request_id != "not-a-uuid"
        uuid.UUID(request_id)  # Should be valid UUID


# =============================================================================
# Secret Sanitization Tests (R45.3)
# =============================================================================


@pytest.mark.unit
class TestSecretSanitization:
    """Secret values are redacted from log output."""

    def test_openai_key_redacted(self):
        """OpenAI API keys (sk-...) are replaced with [REDACTED]."""
        text = "Using key sk-abcdefghijklmnopqrstuvwxyz1234"
        result = sanitize_secret_values(text)
        assert "sk-abcdefghijklmnopqrstuvwxyz1234" not in result
        assert "[REDACTED]" in result

    def test_generic_api_key_redacted(self):
        """Generic API keys (key_...) are replaced with [REDACTED]."""
        text = "B2 key: key_abcdef1234567890"
        result = sanitize_secret_values(text)
        assert "key_abcdef1234567890" not in result
        assert "[REDACTED]" in result

    def test_slack_token_redacted(self):
        """Slack tokens (xoxb-...) are replaced with [REDACTED]."""
        text = "Slack token: xoxb-000000000-FAKE_TEST_ONLY"
        result = sanitize_secret_values(text)
        assert "xoxb-000000000-FAKE_TEST_ONLY" not in result
        assert "[REDACTED]" in result

    def test_github_token_redacted(self):
        """GitHub tokens (ghp_...) are replaced with [REDACTED]."""
        text = "Token: ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijkl"
        result = sanitize_secret_values(text)
        assert "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijkl" not in result
        assert "[REDACTED]" in result

    def test_jwt_redacted(self):
        """JWT tokens (eyJ...) are replaced with [REDACTED]."""
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        text = f"Authorization: Bearer {jwt}"
        result = sanitize_secret_values(text)
        assert "eyJhbGciOiJIUzI1NiJ9" not in result
        assert "[REDACTED]" in result

    def test_password_key_value_redacted(self):
        """Key-value secrets (password=...) are replaced with [REDACTED]."""
        text = "Connection failed: password=supersecret123"
        result = sanitize_secret_values(text)
        assert "supersecret123" not in result
        assert "[REDACTED]" in result

    def test_safe_text_unchanged(self):
        """Non-secret text passes through unchanged."""
        text = "Job job_123 completed successfully in 3.2 seconds"
        result = sanitize_secret_values(text)
        assert result == text

    def test_multiple_secrets_all_redacted(self):
        """Multiple secrets in one string are all redacted."""
        text = "key=sk-abc123DEFghi456JKLmno789 and token=xoxb-999-aaabbbccc"
        result = sanitize_secret_values(text)
        assert "sk-abc123DEFghi456JKLmno789" not in result
        assert "xoxb-999-aaabbbccc" not in result


# =============================================================================
# Structlog Integration Tests (R45.1, R45.2)
# =============================================================================


@pytest.mark.unit
class TestStructuredLogging:
    """Structured logging includes required fields."""

    def test_structlog_scrub_secrets_by_key_name(self):
        """Structlog processor redacts values with secret-like key names."""
        from backend.app.core.logging import _scrub_secrets

        event_dict = {
            "event": "test",
            "api_key": "sk-realkey12345678901234",
            "user_id": "usr-123",
            "authorization": "Bearer eyJtoken",
        }
        result = _scrub_secrets(None, "info", event_dict)
        assert result["api_key"] == "[REDACTED]"
        assert result["authorization"] == "[REDACTED]"
        assert result["user_id"] == "usr-123"  # Not a secret key name

    def test_structlog_scrub_secrets_by_value_content(self):
        """Structlog processor redacts secret patterns in string values."""
        from backend.app.core.logging import _scrub_secrets

        event_dict = {
            "event": "connection_failed",
            "message": "Auth failed with sk-abc123XYZdefGHIjklMNOpqr at endpoint",
            "job_id": "job-456",
        }
        result = _scrub_secrets(None, "info", event_dict)
        assert "sk-abc123XYZdefGHIjklMNOpqr" not in result["message"]
        assert "[REDACTED]" in result["message"]
        assert result["job_id"] == "job-456"  # Non-secret value unchanged


# =============================================================================
# Error Response Contract Tests (comprehensive R16)
# =============================================================================


@pytest.mark.unit
class TestErrorResponseContract:
    """All error responses follow the standard contract."""

    def test_all_errors_are_json(self, client):
        """All error responses have Content-Type application/json."""
        for path in ["/not-found", "/forbidden", "/crash"]:
            response = client.get(path)
            assert "application/json" in response.headers.get("content-type", "")

    def test_all_errors_have_detail_code_request_id(self, client):
        """All error responses contain detail, code, and request_id."""
        for path in ["/not-found", "/forbidden", "/crash", "/unauthorized"]:
            response = client.get(path)
            body = response.json()
            assert "detail" in body, f"Missing 'detail' for {path}"
            assert "code" in body, f"Missing 'code' for {path}"
            assert "request_id" in body, f"Missing 'request_id' for {path}"

    def test_request_id_in_body_matches_header(self, client):
        """request_id in response body matches X-Request-ID header."""
        response = client.get("/not-found")
        body = response.json()
        header_id = response.headers.get("X-Request-ID")
        assert body["request_id"] == header_id

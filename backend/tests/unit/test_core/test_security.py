"""Unit tests for app.core.security — JWT validation.

Tests cover:
    - Valid token decoding with signature verification
    - Expired token raises ExpiredTokenError
    - Invalid signature raises InvalidTokenError
    - Empty/missing sub claim raises InvalidTokenError
    - Clock skew tolerance (30 seconds)
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from jose import jwt as jose_jwt

from app.core.security import (
    ExpiredTokenError,
    InvalidTokenError,
    JWTPayload,
    decode_supabase_jwt,
)

# Test secret for JWT signing
TEST_SECRET = "test-jwt-secret-at-least-32-chars-long"
TEST_ALGORITHM = "HS256"


def _make_token(
    sub: str = "user-123",
    exp: int | None = None,
    extra_claims: dict | None = None,
    secret: str = TEST_SECRET,
) -> str:
    """Helper to create a JWT for testing."""
    claims = {
        "sub": sub,
        "exp": exp if exp is not None else int(time.time()) + 3600,
        "email": "test@example.com",
        "role": "authenticated",
    }
    if extra_claims:
        claims.update(extra_claims)
    return jose_jwt.encode(claims, secret, algorithm=TEST_ALGORITHM)


@pytest.fixture
def _mock_settings():
    """Mock settings to use test JWT secret."""
    with patch("app.core.security.settings") as mock:
        mock.supabase_jwt_secret = TEST_SECRET
        mock.jwt_algorithm = TEST_ALGORITHM
        yield mock


@pytest.mark.unit
class TestDecodeSupabaseJWT:
    """Tests for decode_supabase_jwt function."""

    def test_valid_token_returns_payload(self, _mock_settings):
        """Valid token with all required claims returns JWTPayload."""
        token = _make_token(sub="user-abc-123")

        result = decode_supabase_jwt(token)

        assert isinstance(result, JWTPayload)
        assert result.sub == "user-abc-123"
        assert result.email == "test@example.com"
        assert result.role == "authenticated"
        assert result.exp > 0

    def test_expired_token_raises_expired_error(self, _mock_settings):
        """Token expired beyond 30s skew raises ExpiredTokenError."""
        # Token expired 60 seconds ago (beyond 30s tolerance)
        expired_time = int(time.time()) - 60
        token = _make_token(exp=expired_time)

        with pytest.raises(ExpiredTokenError):
            decode_supabase_jwt(token)

    def test_token_within_clock_skew_is_valid(self, _mock_settings):
        """Token expired within 30s window is still accepted."""
        # Token expired 10 seconds ago (within 30s tolerance)
        slightly_expired = int(time.time()) - 10
        token = _make_token(exp=slightly_expired)

        result = decode_supabase_jwt(token)
        assert result.sub == "user-123"

    def test_token_at_clock_skew_boundary(self, _mock_settings):
        """Token expired exactly at 30s boundary is accepted."""
        # Token expired exactly 29 seconds ago (within tolerance)
        boundary_time = int(time.time()) - 29
        token = _make_token(exp=boundary_time)

        result = decode_supabase_jwt(token)
        assert result.sub == "user-123"

    def test_invalid_signature_raises_invalid_error(self, _mock_settings):
        """Token signed with wrong key raises InvalidTokenError."""
        token = _make_token(secret="wrong-secret-key-here-32chars-xx")

        with pytest.raises(InvalidTokenError):
            decode_supabase_jwt(token)

    def test_malformed_token_raises_invalid_error(self, _mock_settings):
        """Completely malformed token raises InvalidTokenError."""
        with pytest.raises(InvalidTokenError):
            decode_supabase_jwt("not.a.valid.jwt.token")

    def test_empty_sub_raises_invalid_error(self, _mock_settings):
        """Token with empty sub claim raises InvalidTokenError."""
        token = _make_token(sub="")

        with pytest.raises(InvalidTokenError):
            decode_supabase_jwt(token)

    def test_whitespace_sub_raises_invalid_error(self, _mock_settings):
        """Token with whitespace-only sub claim raises InvalidTokenError."""
        # Create token with whitespace sub directly
        claims = {
            "sub": "   ",
            "exp": int(time.time()) + 3600,
        }
        token = jose_jwt.encode(claims, TEST_SECRET, algorithm=TEST_ALGORITHM)

        with pytest.raises(InvalidTokenError):
            decode_supabase_jwt(token)

    def test_missing_sub_raises_invalid_error(self, _mock_settings):
        """Token without sub claim raises InvalidTokenError."""
        claims = {
            "exp": int(time.time()) + 3600,
            "email": "test@example.com",
        }
        token = jose_jwt.encode(claims, TEST_SECRET, algorithm=TEST_ALGORITHM)

        with pytest.raises(InvalidTokenError):
            decode_supabase_jwt(token)

    def test_no_jwt_secret_configured_raises_invalid_error(self):
        """If JWT secret is not configured, raises InvalidTokenError."""
        with patch("app.core.security.settings") as mock:
            mock.supabase_jwt_secret = ""
            mock.jwt_algorithm = TEST_ALGORITHM

            token = _make_token()
            with pytest.raises(InvalidTokenError):
                decode_supabase_jwt(token)

    def test_payload_raw_field_contains_full_claims(self, _mock_settings):
        """JWTPayload.raw contains all claims from the token."""
        token = _make_token(
            sub="user-xyz",
            extra_claims={"app_metadata": {"org_id": "org-456"}},
        )

        result = decode_supabase_jwt(token)

        assert result.raw is not None
        assert result.raw["sub"] == "user-xyz"
        assert result.raw["app_metadata"]["org_id"] == "org-456"

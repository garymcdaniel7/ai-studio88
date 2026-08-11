"""Authentication and authorisation utilities.

Handles JWT validation, password hashing, and API key management.
All auth logic flows through Supabase — we validate their JWTs here.

Custom exceptions:
    ExpiredTokenError: Token has expired beyond clock skew tolerance.
    InvalidTokenError: Token is structurally invalid or missing required claims.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Maximum clock skew tolerance for JWT expiration checks (seconds)
JWT_CLOCK_SKEW_SECONDS = 30


# =============================================================================
# Custom Exceptions
# =============================================================================


class ExpiredTokenError(Exception):
    """Raised when a JWT has expired beyond the clock skew tolerance."""

    def __init__(self, message: str = "Token expired") -> None:
        self.message = message
        super().__init__(message)


class InvalidTokenError(Exception):
    """Raised when a JWT is structurally invalid or missing required claims."""

    def __init__(self, message: str = "Invalid token") -> None:
        self.message = message
        super().__init__(message)


# =============================================================================
# JWT Payload
# =============================================================================


@dataclass(frozen=True)
class JWTPayload:
    """Validated JWT payload containing essential claims.

    Attributes:
        sub: The subject claim (user ID from Supabase Auth).
        exp: Token expiration timestamp.
        email: User's email address (optional).
        role: Supabase role claim (e.g., 'authenticated').
        raw: The full decoded payload dictionary.
    """

    sub: str
    exp: int
    email: str | None = None
    role: str | None = None
    raw: dict[str, Any] | None = None


# =============================================================================
# JWT Validation
# =============================================================================


def decode_supabase_jwt(token: str) -> JWTPayload:
    """Decode and validate a Supabase JWT.

    Validates:
        - Signature against SUPABASE_JWT_SECRET
        - Expiration with 30-second clock skew tolerance
        - Non-empty 'sub' claim

    Args:
        token: The raw JWT string from the Authorization header.

    Returns:
        JWTPayload with validated claims.

    Raises:
        ExpiredTokenError: If token has expired beyond 30s clock skew.
        InvalidTokenError: If token cannot be decoded, has invalid signature,
                          or is missing/empty 'sub' claim.
    """
    jwt_secret = settings.supabase_jwt_secret
    if not jwt_secret:
        logger.error("jwt_secret_not_configured")
        raise InvalidTokenError("JWT secret not configured")

    try:
        payload = jwt.decode(
            token,
            jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={
                "verify_aud": False,
                "verify_exp": True,
                "leeway": JWT_CLOCK_SKEW_SECONDS,
            },
        )
    except JWTError as exc:
        error_str = str(exc).lower()
        # python-jose raises JWTError for both expired and invalid tokens
        if "expired" in error_str or "exp" in error_str:
            logger.warning("jwt_expired", error=str(exc))
            raise ExpiredTokenError("Token expired") from exc
        logger.warning("jwt_validation_failed", error=str(exc))
        raise InvalidTokenError("Invalid token") from exc

    # Validate non-empty sub claim
    sub = payload.get("sub")
    if not sub or not str(sub).strip():
        logger.warning("jwt_missing_sub_claim")
        raise InvalidTokenError("Token missing or empty 'sub' claim")

    exp = payload.get("exp", 0)

    return JWTPayload(
        sub=str(sub),
        exp=int(exp),
        email=payload.get("email"),
        role=payload.get("role"),
        raw=payload,
    )


def extract_user_id(payload: dict[str, Any]) -> str:
    """Extract the user ID (sub) from a raw JWT payload dict.

    This is a convenience function for code that works with raw dicts
    rather than JWTPayload objects.

    Raises:
        ValueError: If sub claim is missing.
    """
    user_id = payload.get("sub")
    if not user_id:
        raise ValueError("JWT missing 'sub' claim")
    return str(user_id)


def is_token_expired(payload: dict[str, Any]) -> bool:
    """Check if a raw JWT payload dict is expired (without clock skew)."""
    exp = payload.get("exp")
    if exp is None:
        return True
    return datetime.now(tz=UTC).timestamp() > exp


# =============================================================================
# Password hashing
# =============================================================================


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return pwd_context.verify(plain, hashed)


# =============================================================================
# API Keys
# =============================================================================


def generate_api_key() -> tuple[str, str]:
    """Generate a new API key and return (raw_key, hashed_key).

    The raw key is shown once and never stored.
    The hashed key is stored in the database.

    Returns:
        Tuple of (raw_key, hashed_key)
    """
    raw_key = f"as_{secrets.token_urlsafe(32)}"
    hashed_key = hashlib.sha256(raw_key.encode()).hexdigest()
    return raw_key, hashed_key


def hash_api_key(raw_key: str) -> str:
    """Hash a raw API key for database storage/lookup."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


def verify_api_key(raw_key: str, stored_hash: str) -> bool:
    """Verify a raw API key against its stored hash."""
    return secrets.compare_digest(
        hashlib.sha256(raw_key.encode()).hexdigest(),
        stored_hash,
    )


# =============================================================================
# Webhook signature verification
# =============================================================================


def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify an HMAC-SHA256 webhook signature.

    Args:
        payload: Raw request body bytes
        signature: Signature from request header (hex digest)
        secret: Shared webhook secret

    Returns:
        True if signature is valid
    """
    import hmac

    expected = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return secrets.compare_digest(expected, signature)

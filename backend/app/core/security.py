"""Authentication and authorisation utilities.

Handles JWT validation, password hashing, and API key management.
All auth logic flows through Supabase — we validate their JWTs here.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# =============================================================================
# JWT
# =============================================================================

def decode_supabase_jwt(token: str) -> dict[str, Any]:
    """Decode and validate a Supabase JWT.

    Raises:
        JWTError: If token is invalid or expired.
    """
    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"verify_aud": False},
        )
        return payload
    except JWTError as exc:
        logger.warning("jwt_validation_failed", error=str(exc))
        raise


def extract_user_id(payload: dict[str, Any]) -> str:
    """Extract the user ID (sub) from a JWT payload.

    Raises:
        ValueError: If sub claim is missing.
    """
    user_id = payload.get("sub")
    if not user_id:
        raise ValueError("JWT missing 'sub' claim")
    return str(user_id)


def is_token_expired(payload: dict[str, Any]) -> bool:
    """Check if a JWT payload is expired."""
    exp = payload.get("exp")
    if exp is None:
        return True
    return datetime.now(tz=timezone.utc).timestamp() > exp


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

    Usage:
        raw_key, hashed = generate_api_key()
        # Store hashed in DB, return raw to user
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

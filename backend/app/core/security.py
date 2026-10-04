"""Authentication and authorisation utilities.

Handles JWT validation, password hashing, and API key management.
All auth logic flows through Supabase — we validate their JWTs here.

Custom exceptions:
    ExpiredTokenError: Token has expired beyond clock skew tolerance.
    InvalidTokenError: Token is structurally invalid or missing required claims.
"""

from __future__ import annotations

import hashlib
import os
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


def _get_jwks_key(token: str) -> dict | None:
    """Return the Supabase JWKS public key dict for an ES256 token.

    Fetches the project's JWKS endpoint and resolves the key by kid.
    Caches keys for the lifetime of the process.
    """
    import json as _json
    from urllib.request import urlopen

    cache: dict = getattr(_get_jwks_key, "_cache", {})
    try:
        # Extract kid from token header
        header_str = token.split(".")[0]
        padding = 4 - len(header_str) % 4
        if padding != 4:
            header_str += "=" * padding
        import base64
        header = _json.loads(base64.urlsafe_b64decode(header_str))
        kid = header.get("kid")
        if not kid:
            return None
        if kid in cache:
            return cache[kid]

        # Fetch JWKS
        supabase_url = os.getenv("SUPABASE_URL", "")
        if not supabase_url:
            return None
        jwks_url = f"{supabase_url}/auth/v1/.well-known/jwks.json"
        resp = urlopen(jwks_url, timeout=5)
        jwks = _json.loads(resp.read().decode())
        for key_data in jwks.get("keys", []):
            if key_data.get("kid") == kid:
                cache[kid] = key_data
                _get_jwks_key._cache = cache
                return key_data
    except Exception as exc:
        logger.warning("jwks_fetch_failed", error=str(exc))
    return None


def _get_token_alg(token: str) -> str:
    """Extract the algorithm from a JWT header without validation."""
    import base64, json
    try:
        header_str = token.split(".")[0]
        padding = 4 - len(header_str) % 4
        if padding != 4:
            header_str += "=" * padding
        header = json.loads(base64.urlsafe_b64decode(header_str))
        return header.get("alg", "HS256")
    except Exception:
        return "HS256"


def decode_supabase_jwt(token: str) -> JWTPayload:
    """Decode and validate a Supabase JWT.

    Supports both HS256 (JWT secret) and ES256 (JWKS public key) tokens.
    Falls back to Supabase /auth/v1/user API when local decode fails.

    Validates:
        - Signature against the appropriate key (SUPABASE_JWT_SECRET or JWKS)
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
    alg = _get_token_alg(token)

    # For ES256 tokens, verify via JWKS
    if alg == "ES256":
        jwks_key = _get_jwks_key(token)
        if jwks_key is not None:
            try:
                # python-jose accepts JWK dicts directly for ES256 verification
                payload = jwt.decode(
                    token,
                    jwks_key,
                    algorithms=["ES256"],
                    options={
                        "verify_aud": False,
                        "verify_exp": True,
                        "leeway": JWT_CLOCK_SKEW_SECONDS,
                    },
                )
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
            except JWTError as exc:
                error_str = str(exc).lower()
                if "expired" in error_str or "exp" in error_str:
                    logger.warning("jwt_expired", error=str(exc))
                    raise ExpiredTokenError("Token expired") from exc
                logger.warning("jwt_es256_validation_failed", error=str(exc))
                raise InvalidTokenError("Invalid token") from exc
        # JWKS key not available — fall through to HS256 + API fallback

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

        # Local decode failed — try Supabase API fallback
        logger.warning("jwt_local_decode_failed_trying_api_fallback", error=str(exc))
        try:
            import os as _os
            import httpx as _httpx
            supabase_url = _os.getenv("SUPABASE_URL", "")
            service_key = _os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
            if supabase_url and service_key:
                resp = _httpx.get(
                    f"{supabase_url}/auth/v1/user",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "apikey": service_key,
                    },
                    timeout=5,
                )
                if resp.status_code == 200:
                    # Token validated by Supabase — extract user from response
                    user_data = resp.json()
                    user_id = user_data.get("id")
                    if user_id:
                        # Manually decode payload (we know it's valid now)
                        import base64, json as _json2
                        payload_b64 = token.split(".")[1]
                        padding = 4 - len(payload_b64) % 4
                        if padding != 4:
                            payload_b64 += "=" * padding
                        payload = _json2.loads(base64.urlsafe_b64decode(payload_b64))
                        exp = payload.get("exp", 0)
                        return JWTPayload(
                            sub=str(user_id),
                            exp=int(exp),
                            email=payload.get("email"),
                            role=payload.get("role"),
                            raw=payload,
                        )
        except Exception as fallback_err:
            logger.warning("jwt_api_fallback_failed", error=str(fallback_err))

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

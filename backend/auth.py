"""Authentication & Authorization — Supabase JWT validation.

Provides FastAPI dependencies for extracting and validating user identity
from Supabase-issued JWTs.

Usage in endpoints:
    from backend.auth import require_auth, optional_auth, AuthUser

    @router.get("/protected")
    def protected_endpoint(user: AuthUser = Depends(require_auth)):
        # user.user_id and user.org_id are guaranteed non-None
        ...

    @router.get("/optional")
    def optional_endpoint(user: AuthUser | None = Depends(optional_auth)):
        # user may be None if no token provided
        ...
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import jwt
from dotenv import load_dotenv
from fastapi import HTTPException, Request

load_dotenv(override=True)

# Supabase JWT secret for token validation
_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")

# Dev mode: when True, auth is optional (bypass for local development)
_AUTH_DEV_MODE = os.getenv("AUTH_DEV_MODE", "true").lower() in ("1", "true", "yes")


@dataclass
class AuthUser:
    """Authenticated user identity extracted from JWT."""

    user_id: str
    email: str | None = None
    org_id: str | None = None
    role: str = "authenticated"


def _decode_token(token: str) -> dict:
    """Decode and validate a Supabase JWT.

    Raises HTTPException(401) if token is invalid or expired.
    """
    if not _JWT_SECRET:
        raise HTTPException(
            status_code=500,
            detail="SUPABASE_JWT_SECRET not configured. Cannot validate tokens.",
        )

    try:
        payload = jwt.decode(
            token,
            _JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired. Please sign in again.")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


def _extract_user(payload: dict) -> AuthUser:
    """Extract AuthUser from decoded JWT payload."""
    user_id = payload.get("sub", "")
    email = payload.get("email")
    role = payload.get("role", "authenticated")

    # org_id can be in app_metadata.org_id or user_metadata.org_id
    app_metadata = payload.get("app_metadata", {})
    user_metadata = payload.get("user_metadata", {})
    org_id = (
        app_metadata.get("org_id")
        or user_metadata.get("org_id")
        or payload.get("org_id")
        or "default"
    )

    return AuthUser(
        user_id=user_id,
        email=email,
        org_id=org_id,
        role=role,
    )


def require_auth(request: Request) -> AuthUser:
    """FastAPI dependency: requires a valid Supabase JWT.

    Returns AuthUser on success, raises 401 on failure.
    In dev mode (AUTH_DEV_MODE=true), returns a default dev user if no token present.
    """
    auth_header = request.headers.get("Authorization", "")

    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        payload = _decode_token(token)
        return _extract_user(payload)

    # No token — check dev mode
    if _AUTH_DEV_MODE:
        return AuthUser(
            user_id="dev-user-local",
            email="dev@localhost",
            org_id="default",
            role="owner",
        )

    raise HTTPException(
        status_code=401,
        detail="Authentication required. Provide Authorization: Bearer <token>",
    )


def optional_auth(request: Request) -> AuthUser | None:
    """FastAPI dependency: validates JWT if present, returns None if absent.

    Never raises 401 — returns None for unauthenticated requests.
    Useful for endpoints that behave differently for auth vs anon users.
    """
    auth_header = request.headers.get("Authorization", "")

    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            payload = _decode_token(token)
            return _extract_user(payload)
        except HTTPException:
            return None

    # No token — check dev mode
    if _AUTH_DEV_MODE:
        return AuthUser(
            user_id="dev-user-local",
            email="dev@localhost",
            org_id="default",
            role="owner",
        )

    return None

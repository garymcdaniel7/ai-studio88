"""Authentication & Authorization — Supabase JWT validation.

Provides FastAPI dependencies for extracting and validating user identity
from Supabase-issued JWTs and resolving org membership.

Usage in endpoints:
    from backend.auth import require_auth, optional_auth, AuthUser

    @router.get("/protected")
    def protected_endpoint(user: AuthUser = Depends(require_auth)):
        # user.user_id is guaranteed non-None
        # user.org_id is resolved from org_members (or dev fallback)
        ...

    @router.get("/optional")
    def optional_endpoint(user: AuthUser | None = Depends(optional_auth)):
        # user may be None if no token provided
        ...

Membership resolution (Story 005):
    - Authenticated users: org_id resolved from org_members table
    - Dev mode: org_id resolved from org_members if available, else None
    - The "default" placeholder is NO LONGER used in production
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

import jwt
from dotenv import load_dotenv
from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

load_dotenv(override=True)

# Supabase JWT secret for token validation
_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")

# Dev mode: when True, auth is optional (bypass for local development)
_AUTH_DEV_MODE = os.getenv("AUTH_DEV_MODE", "true").lower() in ("1", "true", "yes")


@dataclass
class AuthUser:
    """Authenticated user identity extracted from JWT + membership."""

    user_id: str
    email: str | None = None
    org_id: str | None = None
    role: str = "authenticated"


def _decode_token(token: str) -> dict:
    """Decode and validate a Supabase JWT.

    Raises HTTPException(401) if token is invalid or expired.

    Supabase signs access tokens with ES256 (ECDSA) using its own signing
    key, NOT the HS256 project secret. For ES256 we verify against the
    project's JWKS endpoint; for older HS256 tokens we use the JWT secret.
    """
    if not _JWT_SECRET:
        raise HTTPException(
            status_code=500,
            detail="SUPABASE_JWT_SECRET not configured. Cannot validate tokens.",
        )

    try:
        # Determine the algorithm from the token header.
        try:
            header = jwt.get_unverified_header(token)
            alg = header.get("alg", "HS256")
        except Exception:
            alg = "HS256"

        if alg == "ES256":
            # Verify against Supabase's public signing key via JWKS.
            key = _get_supabase_jwks_key(token)
            if key is None:
                # Fall back to unverified decode only as a last resort —
                # never silently accept. Log and require the signature path.
                raise HTTPException(
                    status_code=503,
                    detail="Could not obtain Supabase JWT signing key for token verification.",
                )
        else:
            key = _JWT_SECRET

        payload = jwt.decode(
            token,
            key,
            algorithms=[alg],
            options={"verify_aud": False},
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired. Please sign in again.")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


# Cache the Supabase JWKS public key by its key-id (kid).
_jwks_key_cache: dict[str, object] = {}


def _get_supabase_jwks_key(token: str):
    """Return the Supabase JWT public signing key for the given token.

    Supabase signs ES256 access tokens with a project key exposed via its
    JWKS endpoint. PyJWKClient resolves the key id (kid) from the token and
    we cache the parsed key by kid.
    """
    try:
        kid = jwt.get_unverified_header(token).get("kid")
    except Exception:
        kid = None
    if kid and kid in _jwks_key_cache:
        return _jwks_key_cache[kid]

    supabase_url = os.getenv("SUPABASE_URL", "")
    if not supabase_url:
        return None

    try:
        from jwt import PyJWKClient

        client = PyJWKClient(
            f"{supabase_url}/auth/v1/.well-known/jwks.json",
            cache_keys=True,
        )
        signing_key = client.get_signing_key_from_jwt(token=token)
        if kid:
            _jwks_key_cache[kid] = signing_key.key
        return signing_key.key
    except Exception as exc:  # pragma: no cover - network/provider error
        logger.warning("Failed to load Supabase JWKS key: %s", exc)
        return None


def _extract_user(payload: dict) -> AuthUser:
    """Extract AuthUser from decoded JWT payload and resolve membership.

    org_id resolution order:
    1. Query org_members for the user's active membership
    2. Fall back to JWT app_metadata.org_id (for cases where org_members
       hasn't been populated yet — transitional)
    3. If nothing found: org_id remains None (tenant filtering disabled)

    The placeholder value "default" is NEVER returned.
    """
    user_id = payload.get("sub", "")
    email = payload.get("email")
    role = payload.get("role", "authenticated")

    # Attempt membership resolution from canonical org_members table
    org_id: str | None = None
    resolved_role: str | None = None

    # Extract JWT hint for preferred org (used for multi-workspace switching)
    app_metadata = payload.get("app_metadata", {})
    user_metadata = payload.get("user_metadata", {})
    jwt_org_hint = (
        app_metadata.get("org_id")
        or user_metadata.get("org_id")
        or payload.get("org_id")
    )
    # Reject placeholder values from JWT
    if jwt_org_hint in ("default", "org_development", None, ""):
        jwt_org_hint = None

    try:
        from backend.membership import resolve_membership

        ctx = resolve_membership(user_id, preferred_org_id=jwt_org_hint)
        org_id = ctx.org_id
        resolved_role = ctx.role.value
    except Exception:
        # Membership resolution failed — fall back to JWT hint if valid UUID
        if jwt_org_hint and len(jwt_org_hint) > 8:
            org_id = jwt_org_hint

    return AuthUser(
        user_id=user_id,
        email=email,
        org_id=org_id,
        role=resolved_role or role,
    )


def require_auth(request: Request) -> AuthUser:
    """FastAPI dependency: requires a valid Supabase JWT.

    Returns AuthUser on success, raises 401 on failure.
    In dev mode (AUTH_DEV_MODE=true), returns a dev user if no token present.
    Dev user has org_id=None (no tenant filtering) until org_members is populated.
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
            org_id=None,  # No tenant filtering in dev without membership
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
            org_id=None,  # No tenant filtering in dev without membership
            role="owner",
        )

    return None

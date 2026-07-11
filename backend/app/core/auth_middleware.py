"""Authentication middleware for all routers.

Provides an optional auth dependency that validates Supabase JWTs
when AUTH_REQUIRED=true is set. Defaults to permissive (no auth)
for development, strict for production.

Usage in any router:
    from backend.app.core.auth_middleware import optional_auth
    from fastapi import Depends

    @router.get("/endpoint")
    def my_endpoint(user_id: str | None = Depends(optional_auth)):
        ...

Environment:
    AUTH_REQUIRED=false  → all requests pass (development)
    AUTH_REQUIRED=true   → Bearer token validated against Supabase
"""

from __future__ import annotations

import os

from fastapi import Depends, Header, HTTPException, status

# Auth is optional in dev, required in production
AUTH_ENABLED = os.getenv("AUTH_REQUIRED", "false").lower() == "true"


async def optional_auth(
    authorization: str | None = Header(None, alias="Authorization"),
) -> str | None:
    """Validate auth token if AUTH_REQUIRED=true, otherwise pass through.

    Returns:
        user_id (str) if authenticated, None if in dev mode.
    """
    if not AUTH_ENABLED:
        return None  # Dev mode — no auth required

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required. Set AUTH_REQUIRED=false for development.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Extract token
    parts = authorization.split(" ")
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization format. Use: Bearer <token>",
        )

    token = parts[1]

    # Strategy 1: Decode JWT locally using Supabase JWT secret
    jwt_secret = os.getenv("SUPABASE_JWT_SECRET", "")
    if jwt_secret:
        try:
            from jose import jwt as jose_jwt

            payload = jose_jwt.decode(
                token,
                jwt_secret,
                algorithms=["HS256"],
                audience="authenticated",
            )
            user_id = payload.get("sub")
            if user_id:
                return user_id
        except Exception:
            pass  # Fall through to Strategy 2

    # Strategy 2: Validate token against Supabase auth endpoint
    supabase_url = os.getenv("SUPABASE_URL", "")
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if supabase_url and service_key:
        try:
            import httpx

            resp = httpx.get(
                f"{supabase_url}/auth/v1/user",
                headers={
                    "Authorization": f"Bearer {token}",
                    "apikey": service_key,
                },
                timeout=5,
            )
            if resp.status_code == 200:
                user_data = resp.json()
                return user_data.get("id")
        except Exception:
            pass

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
    )


# Convenience: use as Depends(optional_auth) in route handlers
AuthDep = Depends(optional_auth)

"""Tenant middleware — FastAPI dependency for resolving authenticated org_id.

This module provides a FastAPI dependency that:
    - Extracts org_id from the validated JWT (via org_members lookup)
    - NEVER accepts org_id from query params or request body (R2.10)
    - Rejects the quarantined UUID with HTTP 422 (R2.8)
    - Makes org_id available as a dependency for all route handlers

This is a thin wrapper that integrates the TenantContext resolution
from backend/app/core/dependencies.py with the quarantined UUID validation
from backend/tenant_context.py. It serves as the bridge between the
existing flat Supabase-direct endpoints and the new layered architecture.

Validates: Requirements R2.2, R2.6, R2.7, R2.8, R2.9, R2.10
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from backend.tenant_context import QUARANTINED_UUID, TenantValidationError, validate_org_id


# =============================================================================
# FastAPI Dependency
# =============================================================================


async def get_authenticated_org_id(request: Request) -> str:
    """Resolve the authenticated org_id from the request's JWT.

    This dependency:
        1. Checks if TenantContext was already resolved by the layered
           architecture (stored in request.state.tenant_context)
        2. Falls back to dev-mode resolution for legacy endpoints
        3. Rejects the quarantined UUID with HTTP 422
        4. Returns a validated, trusted org_id string

    The returned org_id is ALWAYS derived from the server-side JWT
    validation + org_members lookup. It is NEVER sourced from client
    request parameters (query string, path params, or body).

    Args:
        request: The incoming FastAPI request.

    Returns:
        The validated org_id string from TenantContext.

    Raises:
        HTTPException 401: If no authentication is present.
        HTTPException 403: If the user has no active org membership.
        HTTPException 422: If the resolved org_id is the quarantined UUID.

    Validates: R2.6, R2.8, R2.10
    """
    # Check if the new layered architecture has already resolved TenantContext
    tenant_ctx = getattr(request.state, "tenant_context", None)
    if tenant_ctx is not None:
        org_id = str(tenant_ctx.org_id)
        try:
            validate_org_id(org_id)
        except TenantValidationError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Invalid organization identifier. The provided org_id is a "
                    "reserved placeholder and cannot be used."
                ),
                headers={"X-Error-Code": "QUARANTINED_ORG_ID"},
            )
        return org_id

    # Fallback: resolve from dev mode or JWT directly
    # This handles the legacy endpoints that don't use the full middleware stack
    from backend.app.core.config import get_settings

    settings = get_settings()

    # Dev mode: inject org_id from first org_members record
    if settings.auth_dev_mode and settings.environment in ("local", "test"):
        from backend.database import get_supabase_client, is_supabase_configured

        if is_supabase_configured():
            client = get_supabase_client()
            result = (
                client.table("org_members")
                .select("org_id")
                .eq("status", "active")
                .order("created_at", desc=False)
                .limit(1)
                .execute()
            )
            if result.data:
                org_id = result.data[0]["org_id"]
                try:
                    validate_org_id(org_id)
                except TenantValidationError:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=(
                            "Invalid organization identifier. The resolved org_id "
                            "is a reserved placeholder and cannot be used."
                        ),
                        headers={"X-Error-Code": "QUARANTINED_ORG_ID"},
                    )
                return org_id

        # Dev mode but no Supabase — cannot resolve org_id
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Production/staging: require real JWT
    authorization = request.headers.get("authorization")
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = parts[1]

    try:
        from backend.app.core.security import (
            ExpiredTokenError,
            InvalidTokenError,
            decode_supabase_jwt,
        )

        payload = decode_supabase_jwt(token)
        user_id = payload.sub
    except ExpiredTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Resolve org_id from org_members
    from backend.database import get_supabase_client, is_supabase_configured

    if not is_supabase_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not configured",
        )

    client = get_supabase_client()
    result = (
        client.table("org_members")
        .select("org_id")
        .eq("user_id", user_id)
        .eq("status", "active")
        .order("created_at", desc=False)
        .limit(1)
        .execute()
    )

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No organization membership found",
            headers={"X-Error-Code": "NO_MEMBERSHIP"},
        )

    org_id = result.data[0]["org_id"]

    # Validate the resolved org_id (R2.8)
    try:
        validate_org_id(org_id)
    except TenantValidationError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Invalid organization identifier. The provided org_id is a "
                "reserved placeholder and cannot be used."
            ),
            headers={"X-Error-Code": "QUARANTINED_ORG_ID"},
        )

    return org_id


# Type alias for use in route handlers
AuthenticatedOrgIDDep = Annotated[str, Depends(get_authenticated_org_id)]

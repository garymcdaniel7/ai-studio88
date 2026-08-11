"""RBAC Middleware — FastAPI dependencies for role-based access control.

This module provides request-level role enforcement as a FastAPI dependency
that works alongside the tenant middleware. Once org_id is resolved,
the user's role is looked up from the org_members table and validated
against the endpoint's requirements.

Key components:
    - get_user_role(request) → Role: resolves role from org_members
    - RequireRole(minimum_role) → dependency class that returns 403 if insufficient
    - enforce_viewer_read_only() → blanket enforcement for viewer restrictions

The role resolution happens per-request and is cached on request.state
to avoid redundant database lookups within the same request lifecycle.

Validates: Requirements R3.1, R3.2, R3.3, R3.4, R3.5, R3.6
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from app.core.dependencies import (
    TenantContext,
    WorkspaceRole,
    get_tenant_context,
)
from app.core.logging import get_logger
from app.core.rbac import Role, has_permission, role_from_string

logger = get_logger(__name__)

# Resources where editor is blocked from DELETE (R3.4)
EDITOR_DELETE_BLOCKED_RESOURCES = frozenset({
    "talent",
    "model",
    "models",
    "lora",
    "credential",
    "credentials",
    "org-settings",
    "workspace-credentials",
    "connections",
})


# =============================================================================
# Role Resolution
# =============================================================================


async def get_user_role(request: Request) -> Role:
    """Resolve the authenticated user's role from TenantContext.

    The role is resolved from the org_members table via the
    get_tenant_context dependency. Once resolved, it is cached
    on request.state.resolved_role for the lifetime of the request.

    Args:
        request: The incoming FastAPI request.

    Returns:
        The user's Role enum value.

    Raises:
        HTTPException 401: If user is not authenticated.
        HTTPException 403: If user has no active membership.

    Validates: R3.5
    """
    # Check if already resolved in this request
    cached_role: Role | None = getattr(request.state, "resolved_role", None)
    if cached_role is not None:
        return cached_role

    # Resolve tenant context (handles auth + membership lookup)
    tenant_ctx: TenantContext | None = getattr(request.state, "tenant_context", None)
    if tenant_ctx is None:
        tenant_ctx = await get_tenant_context(request)

    # Convert WorkspaceRole to our Role enum
    role = role_from_string(tenant_ctx.role.value)

    # Cache for subsequent calls in this request
    request.state.resolved_role = role

    return role


UserRoleDep = Annotated[Role, Depends(get_user_role)]


# =============================================================================
# RequireRole — configurable minimum role dependency
# =============================================================================


class RequireRole:
    """FastAPI dependency class that enforces a minimum role level.

    Returns 403 with structured error body if the user's role
    does not meet the minimum requirement.

    Usage:
        @router.post("/resource", dependencies=[Depends(RequireRole(Role.EDITOR))])
        async def create_resource(...): ...

        @router.delete("/talent/{id}", dependencies=[Depends(RequireRole(Role.ADMIN))])
        async def delete_talent(...): ...

    Args:
        minimum_role: The minimum Role required for the operation.

    Validates: R3.1, R3.2, R3.3, R3.4
    """

    def __init__(self, minimum_role: Role) -> None:
        self.minimum_role = minimum_role

    async def __call__(self, request: Request) -> TenantContext:
        """Evaluate role and return TenantContext if permitted.

        Raises:
            HTTPException 403: If the user's role is below minimum.
        """
        # Resolve tenant context
        tenant_ctx: TenantContext | None = getattr(
            request.state, "tenant_context", None
        )
        if tenant_ctx is None:
            tenant_ctx = await get_tenant_context(request)

        # Convert and check
        user_role = role_from_string(tenant_ctx.role.value)

        if not has_permission(user_role, self.minimum_role):
            logger.warning(
                "rbac_require_role_blocked",
                user_id=str(tenant_ctx.user_id),
                org_id=str(tenant_ctx.org_id),
                user_role=user_role.value,
                required_role=self.minimum_role.value,
                method=request.method,
                path=request.url.path,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
                headers={"X-Error-Code": "FORBIDDEN"},
            )

        # Cache resolved role
        request.state.resolved_role = user_role

        return tenant_ctx


# =============================================================================
# Viewer Read-Only Enforcement
# =============================================================================


async def enforce_viewer_read_only(
    request: Request,
    tenant: TenantContext = Depends(get_tenant_context),
) -> TenantContext:
    """Enforce that viewers can only perform read operations.

    Viewers (role level 1) are blocked from:
    - POST (create)
    - PUT (full replace)
    - PATCH (partial update)
    - DELETE (remove)

    Only GET, HEAD, OPTIONS are permitted for viewers.

    Args:
        request: The incoming FastAPI request.
        tenant: The resolved TenantContext.

    Returns:
        The TenantContext if permitted.

    Raises:
        HTTPException 403: If viewer attempts a mutation.

    Validates: R3.2, R3.3
    """
    method = request.method.upper()
    user_role = role_from_string(tenant.role.value)

    # Read methods are always allowed for any authenticated user
    if method in ("GET", "HEAD", "OPTIONS"):
        return tenant

    # Mutation methods require at least EDITOR
    if not has_permission(user_role, Role.EDITOR):
        logger.warning(
            "rbac_viewer_mutation_blocked",
            user_id=str(tenant.user_id),
            org_id=str(tenant.org_id),
            role=user_role.value,
            method=method,
            path=request.url.path,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
            headers={"X-Error-Code": "FORBIDDEN"},
        )

    return tenant


ViewerReadOnlyDep = Annotated[TenantContext, Depends(enforce_viewer_read_only)]


# =============================================================================
# Editor DELETE Restriction
# =============================================================================


async def enforce_editor_delete_restriction(
    request: Request,
    tenant: TenantContext = Depends(get_tenant_context),
) -> TenantContext:
    """Enforce that editors cannot DELETE sensitive resources.

    Editors can POST/PUT/PATCH on any resource, but DELETE is restricted
    for certain resource types that require admin privileges:
    - talent, model, credential, org-settings

    The resource type is extracted from the request path.

    Args:
        request: The incoming FastAPI request.
        tenant: The resolved TenantContext.

    Returns:
        The TenantContext if permitted.

    Raises:
        HTTPException 403: If editor attempts DELETE on sensitive resource.

    Validates: R3.4
    """
    if request.method.upper() != "DELETE":
        return tenant

    user_role = role_from_string(tenant.role.value)

    # Admins and owners can DELETE anything
    if has_permission(user_role, Role.ADMIN):
        return tenant

    # Check if this is a sensitive resource
    path = request.url.path.lower()
    resource_type = _extract_resource_type(path)

    if resource_type in EDITOR_DELETE_BLOCKED_RESOURCES:
        logger.warning(
            "rbac_editor_delete_restricted",
            user_id=str(tenant.user_id),
            org_id=str(tenant.org_id),
            role=user_role.value,
            resource_type=resource_type,
            path=path,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
            headers={"X-Error-Code": "FORBIDDEN"},
        )

    return tenant


EditorDeleteRestrictionDep = Annotated[
    TenantContext, Depends(enforce_editor_delete_restriction)
]


# =============================================================================
# Helpers
# =============================================================================


def _extract_resource_type(path: str) -> str:
    """Extract the primary resource type from a URL path.

    Examples:
        /api/v1/talent/123 → "talent"
        /api/v1/models/abc → "models"
        /api/v1/org-settings → "org-settings"
        /api/v1/credentials/xyz → "credentials"

    Args:
        path: The URL path string.

    Returns:
        The resource type segment, or empty string if not determinable.
    """
    # Remove leading slash and split
    segments = [s for s in path.strip("/").split("/") if s]

    # Skip common prefixes: "api", "v1", "v2", etc.
    resource_segments = []
    for segment in segments:
        if segment in ("api", "v1", "v2"):
            continue
        resource_segments.append(segment)

    if not resource_segments:
        return ""

    # The first non-prefix segment is the resource type
    return resource_segments[0]

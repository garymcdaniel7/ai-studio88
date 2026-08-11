"""Role-Based Access Control enforcement.

Provides FastAPI dependencies for endpoint-level role enforcement.
Hierarchy: OWNER (4) > ADMIN (3) > EDITOR (2) > VIEWER (1)

Enforcement rules (R3.1-R3.6):
    - VIEWER: read-only access (GET only), blocked from all mutations (403)
    - EDITOR: read + write, blocked from DELETE on sensitive resources
    - ADMIN: full access except org-level destructive operations
    - OWNER: unrestricted access

Sensitive resources requiring ADMIN+ for DELETE:
    - talent (AI personas)
    - models/LoRA (trained ML models)
    - workspace_credentials (API keys, OAuth tokens)
    - org-settings (organization configuration)
    - connections (external service links)

Usage in endpoints:
    @router.post("/talent", dependencies=[Depends(require_editor)])
    async def create_talent(...): ...

    @router.delete("/talent/{id}", dependencies=[Depends(require_admin)])
    async def delete_talent(...): ...

    # Factory approach for custom requirements:
    @router.delete("/credentials/{id}", dependencies=[Depends(RoleChecker(Role.ADMIN))])
    async def delete_credential(...): ...

Requirements: R3.1, R3.2, R3.3, R3.4, R3.5, R3.6
"""

from __future__ import annotations

import enum
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from app.core.dependencies import (
    TenantContext,
    WorkspaceRole,
    get_tenant_context,
)
from app.core.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Role Enum with numeric hierarchy
# =============================================================================


class Role(str, enum.Enum):
    """Workspace roles with numeric hierarchy values.

    Higher numeric value = more privilege.
    Hierarchy: OWNER (4) > ADMIN (3) > EDITOR (2) > VIEWER (1)

    Validates: R3.1
    """

    OWNER = "owner"
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"

    @property
    def level(self) -> int:
        """Return numeric privilege level for comparison."""
        return _ROLE_LEVELS[self]

    def __ge__(self, other: "Role") -> bool:
        if not isinstance(other, Role):
            return NotImplemented
        return self.level >= other.level

    def __gt__(self, other: "Role") -> bool:
        if not isinstance(other, Role):
            return NotImplemented
        return self.level > other.level

    def __le__(self, other: "Role") -> bool:
        if not isinstance(other, Role):
            return NotImplemented
        return self.level <= other.level

    def __lt__(self, other: "Role") -> bool:
        if not isinstance(other, Role):
            return NotImplemented
        return self.level < other.level


_ROLE_LEVELS: dict[Role, int] = {
    Role.VIEWER: 1,
    Role.EDITOR: 2,
    Role.ADMIN: 3,
    Role.OWNER: 4,
}


def has_permission(user_role: Role, required_role: Role) -> bool:
    """Check if a user's role meets or exceeds the required role.

    Args:
        user_role: The user's current role.
        required_role: The minimum required role for the operation.

    Returns:
        True if user_role >= required_role in the hierarchy.

    Validates: R3.1
    """
    return user_role.level >= required_role.level


def role_from_string(role_str: str) -> Role:
    """Convert a string to a Role enum, defaulting to VIEWER for unknown values.

    Unknown or invalid role strings default to VIEWER (least privilege)
    to prevent privilege escalation from bad data.

    Args:
        role_str: The role string from org_members table.

    Returns:
        Corresponding Role enum value, or Role.VIEWER for unknown strings.
    """
    try:
        return Role(role_str.lower().strip())
    except (ValueError, AttributeError):
        logger.warning(
            "rbac_unknown_role_defaulting_to_viewer",
            provided_role=str(role_str),
        )
        return Role.VIEWER


# =============================================================================
# RoleChecker — configurable FastAPI dependency factory
# =============================================================================


class RoleChecker:
    """Configurable FastAPI dependency that enforces a minimum role.

    Usage as a dependency:
        @router.post("/resource", dependencies=[Depends(RoleChecker(Role.EDITOR))])
        async def create_resource(...): ...

        # Or with resource-specific DELETE enforcement:
        @router.delete(
            "/talent/{id}",
            dependencies=[Depends(RoleChecker(Role.ADMIN, resource_type="talent"))]
        )
        async def delete_talent(...): ...

    Args:
        minimum_role: The minimum Role required for the operation.
        resource_type: Optional resource type for context in error messages.

    Validates: R3.1, R3.2, R3.3, R3.4
    """

    def __init__(
        self,
        minimum_role: Role,
        resource_type: str | None = None,
    ) -> None:
        self.minimum_role = minimum_role
        self.resource_type = resource_type

    async def __call__(
        self,
        request: Request,
        tenant: TenantContext = Depends(get_tenant_context),
    ) -> TenantContext:
        """Evaluate the role check and return the TenantContext if permitted.

        Raises:
            HTTPException 403: If the user's role is below the minimum.
        """
        user_role = role_from_string(tenant.role.value)

        if not has_permission(user_role, self.minimum_role):
            resource_msg = (
                f" on {self.resource_type}" if self.resource_type else ""
            )
            logger.warning(
                "rbac_role_check_failed",
                user_id=str(tenant.user_id),
                org_id=str(tenant.org_id),
                user_role=user_role.value,
                required_role=self.minimum_role.value,
                resource_type=self.resource_type or "",
                path=request.url.path,
                method=request.method,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions{resource_msg}",
                headers={"X-Error-Code": "FORBIDDEN"},
            )

        return tenant


# =============================================================================
# Role enforcement dependencies (convenience wrappers)
# =============================================================================


async def require_viewer(
    request: Request,
    tenant: TenantContext = Depends(get_tenant_context),
) -> TenantContext:
    """Require at least VIEWER role (any authenticated user with membership).

    This is the minimum — any org member can read.
    """
    tenant.require_role(WorkspaceRole.VIEWER)
    return tenant


async def require_editor(
    request: Request,
    tenant: TenantContext = Depends(get_tenant_context),
) -> TenantContext:
    """Require at least EDITOR role for mutations (POST/PUT/PATCH).

    Viewers are blocked from creating, updating, or modifying resources.
    Returns 403 if the user has VIEWER role.

    Requirements: R3.2, R3.3
    """
    tenant.require_role(WorkspaceRole.EDITOR)
    return tenant


async def require_admin(
    request: Request,
    tenant: TenantContext = Depends(get_tenant_context),
) -> TenantContext:
    """Require at least ADMIN role for sensitive operations.

    Used for:
    - DELETE on sensitive resources (talent, models, credentials)
    - Organization settings modification
    - Member management
    - Connection management

    Requirements: R3.4, R3.5
    """
    tenant.require_role(WorkspaceRole.ADMIN)
    return tenant


async def require_owner(
    request: Request,
    tenant: TenantContext = Depends(get_tenant_context),
) -> TenantContext:
    """Require OWNER role for org-level destructive operations.

    Used for:
    - Organization deletion
    - Ownership transfer
    - Plan changes
    - Member removal (admin+)

    Requirements: R3.6
    """
    tenant.require_role(WorkspaceRole.OWNER)
    return tenant


# =============================================================================
# Annotated type aliases for clean endpoint signatures
# =============================================================================

ViewerDep = Annotated[TenantContext, Depends(require_viewer)]
EditorDep = Annotated[TenantContext, Depends(require_editor)]
AdminDep = Annotated[TenantContext, Depends(require_admin)]
OwnerDep = Annotated[TenantContext, Depends(require_owner)]


# =============================================================================
# HTTP method-aware enforcement
# =============================================================================


async def enforce_method_role(
    request: Request,
    tenant: TenantContext = Depends(get_tenant_context),
) -> TenantContext:
    """Enforce role based on HTTP method (defense-in-depth).

    - GET/HEAD/OPTIONS: VIEWER sufficient
    - POST/PUT/PATCH: requires EDITOR (R3.2)
    - DELETE: requires EDITOR (sensitive resources checked separately)

    This is applied as a router-level dependency for blanket enforcement.
    Individual endpoints can override with stricter requirements.

    Requirements: R3.2, R3.3
    """
    method = request.method.upper()
    user_role = role_from_string(tenant.role.value)

    if method in ("GET", "HEAD", "OPTIONS"):
        # Read operations — viewer is sufficient
        if not has_permission(user_role, Role.VIEWER):
            _raise_forbidden(tenant, request, Role.VIEWER)
    elif method == "DELETE":
        # DELETE requires at least editor; sensitive resources require admin
        if not has_permission(user_role, Role.EDITOR):
            _raise_forbidden(tenant, request, Role.EDITOR)
    else:
        # POST, PUT, PATCH — require editor
        if not has_permission(user_role, Role.EDITOR):
            _raise_forbidden(tenant, request, Role.EDITOR)

    return tenant


MethodRoleDep = Annotated[TenantContext, Depends(enforce_method_role)]


# =============================================================================
# Sensitive resource DELETE enforcement
# =============================================================================

# Resources that require ADMIN role for DELETE (R3.4)
ADMIN_DELETE_RESOURCES = frozenset({
    "talent",
    "models",
    "lora",
    "credentials",
    "connections",
    "org-settings",
    "workspace-credentials",
})


async def require_admin_for_delete(
    request: Request,
    tenant: TenantContext = Depends(get_tenant_context),
) -> TenantContext:
    """Require ADMIN role for DELETE on sensitive resources.

    Editors can create and update most resources, but cannot delete:
    - AI Talent (personas — deletion is destructive)
    - Models/LoRA (trained ML artifacts — expensive to recreate)
    - Credentials (API keys, OAuth tokens — security critical)
    - Organization settings (affects entire workspace)
    - Connections (external service links)

    Requirements: R3.4, R3.5
    """
    if request.method.upper() == "DELETE":
        user_role = role_from_string(tenant.role.value)
        if not has_permission(user_role, Role.ADMIN):
            logger.warning(
                "rbac_delete_blocked",
                user_id=str(tenant.user_id),
                org_id=str(tenant.org_id),
                role=tenant.role.value,
                path=request.url.path,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Deleting this resource requires admin privileges",
                headers={"X-Error-Code": "INSUFFICIENT_ROLE"},
            )
    else:
        # For non-DELETE methods, editor is sufficient
        user_role = role_from_string(tenant.role.value)
        if not has_permission(user_role, Role.EDITOR):
            _raise_forbidden(tenant, request, Role.EDITOR)

    return tenant


AdminDeleteDep = Annotated[TenantContext, Depends(require_admin_for_delete)]


# =============================================================================
# Role check utilities (for use in service layer)
# =============================================================================


def check_minimum_role(
    tenant: TenantContext,
    minimum: WorkspaceRole,
    action: str = "this action",
) -> None:
    """Check minimum role in service layer, raise 403 if insufficient.

    Args:
        tenant: The authenticated TenantContext.
        minimum: The minimum required role.
        action: Human-readable action description for error message.

    Raises:
        HTTPException: 403 if role is insufficient.
    """
    if not tenant.role.has_privilege(minimum):
        logger.warning(
            "rbac_action_blocked",
            user_id=str(tenant.user_id),
            org_id=str(tenant.org_id),
            role=tenant.role.value,
            required_role=minimum.value,
            action=action,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions: {action} requires {minimum.value} role or higher",
            headers={"X-Error-Code": "INSUFFICIENT_ROLE"},
        )


def is_at_least(tenant: TenantContext, minimum: WorkspaceRole) -> bool:
    """Check if tenant has at least the given role without raising.

    Useful for conditional logic in services where a lower role should
    see reduced data rather than be blocked entirely.
    """
    return tenant.role.has_privilege(minimum)


# =============================================================================
# Internal helpers
# =============================================================================


def _raise_forbidden(
    tenant: TenantContext,
    request: Request,
    required: Role,
) -> None:
    """Raise 403 with structured logging and error response."""
    logger.warning(
        "rbac_method_role_blocked",
        user_id=str(tenant.user_id),
        org_id=str(tenant.org_id),
        user_role=tenant.role.value,
        required_role=required.value,
        method=request.method,
        path=request.url.path,
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Insufficient permissions",
        headers={"X-Error-Code": "FORBIDDEN"},
    )

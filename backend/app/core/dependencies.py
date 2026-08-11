"""FastAPI dependency injection providers.

Provides:
    - TenantContext (frozen dataclass): resolved org_id + role for authenticated requests
    - WorkspaceRole enum: OWNER > ADMIN > EDITOR > VIEWER
    - TrustDomain enum: security compartments for access control
    - get_tenant_context(): resolves JWT → org_members lookup → TenantContext
    - CurrentUserIDDep: Annotated type alias for authenticated user_id (UUID)
    - TenantContextDep: Annotated type alias for full TenantContext

All shared dependencies live here. Use Depends() in route handlers.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.security import (
    ExpiredTokenError,
    InvalidTokenError,
    JWTPayload,
    decode_supabase_jwt,
)
from app.db.session import get_db_session

logger = get_logger(__name__)


# =============================================================================
# Enums
# =============================================================================


class WorkspaceRole(str, enum.Enum):
    """Organisation membership roles, ordered by privilege level.

    Hierarchy: OWNER > ADMIN > EDITOR > VIEWER
    """

    OWNER = "owner"
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"

    def has_privilege(self, required: "WorkspaceRole") -> bool:
        """Check if this role meets or exceeds the required privilege level."""
        hierarchy = [
            WorkspaceRole.VIEWER,
            WorkspaceRole.EDITOR,
            WorkspaceRole.ADMIN,
            WorkspaceRole.OWNER,
        ]
        return hierarchy.index(self) >= hierarchy.index(required)


class TrustDomain(str, enum.Enum):
    """Trust domain security compartments.

    Determines what knowledge, tools, credentials, and approval capabilities
    are accessible to an identity class.

    Hierarchy (higher includes more privilege):
        FOUNDER_PRIVATE > PLATFORM_ADMIN > WORKSPACE_ADMIN >
        CUSTOMER_USER > SERVICE_WORKER > SYSTEM_AUTOMATION
    """

    FOUNDER_PRIVATE = "FOUNDER_PRIVATE"
    PLATFORM_ADMIN = "PLATFORM_ADMIN"
    WORKSPACE_ADMIN = "WORKSPACE_ADMIN"
    CUSTOMER_USER = "CUSTOMER_USER"
    SERVICE_WORKER = "SERVICE_WORKER"
    SYSTEM_AUTOMATION = "SYSTEM_AUTOMATION"


# =============================================================================
# TenantContext
# =============================================================================


@dataclass(frozen=True)
class TenantContext:
    """Trusted execution context resolved from authentication + membership.

    This is the canonical identity for a request. All downstream operations
    (DB queries, storage, job dispatch) receive this context — never raw
    user-supplied org_id values.

    Attributes:
        user_id: Supabase auth user UUID (from JWT 'sub' claim).
        org_id: Resolved organisation UUID (from org_members lookup).
        role: User's role within this organisation.
        trust_domain: Security compartment for access control.
        email: User's email (from JWT, informational only).
    """

    user_id: UUID
    org_id: UUID
    role: WorkspaceRole
    trust_domain: TrustDomain
    email: str | None = None

    @property
    def is_owner(self) -> bool:
        """Check if user has owner role."""
        return self.role == WorkspaceRole.OWNER

    @property
    def is_admin_or_above(self) -> bool:
        """Check if user has admin or owner role."""
        return self.role.has_privilege(WorkspaceRole.ADMIN)

    @property
    def is_editor_or_above(self) -> bool:
        """Check if user has editor, admin, or owner role."""
        return self.role.has_privilege(WorkspaceRole.EDITOR)

    def require_role(self, minimum: WorkspaceRole) -> None:
        """Raise 403 if the user lacks the required role.

        Args:
            minimum: The minimum required workspace role.

        Raises:
            HTTPException: 403 if insufficient permissions.
        """
        if not self.role.has_privilege(minimum):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
                headers={"X-Error-Code": "FORBIDDEN"},
            )


# =============================================================================
# Settings
# =============================================================================

SettingsDep = Annotated[Settings, Depends(get_settings)]


# =============================================================================
# Database
# =============================================================================

DBSessionDep = Annotated[AsyncSession, Depends(get_db_session)]


# =============================================================================
# Authentication — extract user_id from JWT
# =============================================================================


async def get_current_user_id(
    request: Request,
) -> UUID:
    """Extract and validate the authenticated user ID from the Bearer token.

    This dependency is used when you only need the user_id (UUID) without
    full tenant context resolution.

    The JWT is validated by AuthMiddleware before reaching this point.
    If the middleware has already attached the payload to request state,
    we use it. Otherwise, we validate the token ourselves.

    Raises:
        HTTPException 401: If token is missing, invalid, or expired.
    """
    # Check if AuthMiddleware already validated and attached the payload
    jwt_payload: JWTPayload | None = getattr(request.state, "jwt_payload", None)
    if jwt_payload:
        return UUID(jwt_payload.sub)

    # Fallback: validate token ourselves (for endpoints not behind middleware)
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
        payload = decode_supabase_jwt(token)
        return UUID(payload.sub)
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


CurrentUserIDDep = Annotated[UUID, Depends(get_current_user_id)]


# =============================================================================
# Tenant Context Resolution
# =============================================================================


async def get_tenant_context(
    request: Request,
) -> TenantContext:
    """Resolve the full TenantContext for the authenticated user.

    Resolution flow:
        1. Extract user_id from validated JWT (via request.state or header)
        2. Query org_members for active membership
        3. Build TenantContext with resolved org_id and role

    Raises:
        HTTPException 401: If token is missing, invalid, or expired.
        HTTPException 403: If user has no active organisation membership.
    """
    # Check if AuthMiddleware already attached tenant context
    tenant_ctx: TenantContext | None = getattr(request.state, "tenant_context", None)
    if tenant_ctx:
        return tenant_ctx

    # Get user_id from JWT
    user_id = await get_current_user_id(request)

    # Resolve membership via org_members lookup
    settings = get_settings()

    # Use the existing membership resolution (Supabase client query)
    try:
        from backend.database import get_supabase_client, is_supabase_configured

        if not is_supabase_configured():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database not configured",
            )

        client = get_supabase_client()
        result = (
            client.table("org_members")
            .select("org_id, role, status")
            .eq("user_id", str(user_id))
            .eq("status", "active")
            .order("created_at", desc=False)
            .execute()
        )

        memberships = result.data or []

        if not memberships:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No organization membership found",
                headers={"X-Error-Code": "NO_MEMBERSHIP"},
            )

        # Filter out system org
        system_org_id = "00000000-0000-0000-0000-000000000001"
        user_memberships = [
            m for m in memberships if m["org_id"] != system_org_id
        ]

        if not user_memberships:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No organization membership found",
                headers={"X-Error-Code": "NO_MEMBERSHIP"},
            )

        membership = user_memberships[0]
        org_id = UUID(membership["org_id"])

        # Reject quarantined UUID at the dependency boundary (R2.8)
        from app.db.tenant_scope import QUARANTINED_ORG_ID

        if org_id == QUARANTINED_ORG_ID:
            logger.warning(
                "quarantined_org_id_in_membership",
                user_id=str(user_id),
                org_id=str(org_id),
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid organization identifier. The provided org_id is a reserved placeholder and cannot be used.",
                headers={"X-Error-Code": "QUARANTINED_ORG_ID"},
            )

        role = WorkspaceRole(membership["role"])

        # Determine trust domain based on role
        if role in (WorkspaceRole.OWNER, WorkspaceRole.ADMIN):
            trust_domain = TrustDomain.WORKSPACE_ADMIN
        else:
            trust_domain = TrustDomain.CUSTOMER_USER

        # Get email from JWT payload if available
        jwt_payload: JWTPayload | None = getattr(request.state, "jwt_payload", None)
        email = jwt_payload.email if jwt_payload else None

        return TenantContext(
            user_id=user_id,
            org_id=org_id,
            role=role,
            trust_domain=trust_domain,
            email=email,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("tenant_context_resolution_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from exc


TenantContextDep = Annotated[TenantContext, Depends(get_tenant_context)]


# =============================================================================
# Pagination
# =============================================================================


class PaginationParams:
    """Standard pagination query parameters."""

    def __init__(
        self,
        limit: int = 20,
        offset: int = 0,
    ) -> None:
        if limit < 1 or limit > 100:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="limit must be between 1 and 100",
            )
        if offset < 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="offset must be >= 0",
            )
        self.limit = limit
        self.offset = offset


PaginationDep = Annotated[PaginationParams, Depends(PaginationParams)]

"""Canonical Membership Resolution — Story 005.

This module is the SINGLE source of truth for resolving user→org membership.
All tenant-aware operations in the application MUST flow through this module.

Membership resolution order:
1. Query org_members table for user_id with status='active'
2. If user has exactly one active membership → use it
3. If user has multiple memberships → use the one specified in JWT app_metadata.org_id
4. If user has no active membership → fail with 403

The system org ('00000000-0000-0000-0000-000000000001') is never returned
for normal user requests. It is only accessible via the service layer.

Role hierarchy (higher includes lower):
    owner > admin > editor > viewer

Membership statuses:
    active       — full access according to role
    invited      — invitation sent, not yet accepted
    suspended    — temporarily blocked (admin action)
    deactivated  — permanently removed (cannot be reactivated)
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from uuid import UUID

from backend.database import is_supabase_configured


# =============================================================================
# Enums
# =============================================================================


class OrgRole(str, enum.Enum):
    """Organisation membership roles, ordered by privilege level."""

    OWNER = "owner"
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"

    def has_privilege(self, required: "OrgRole") -> bool:
        """Check if this role meets or exceeds the required privilege level."""
        hierarchy = [OrgRole.VIEWER, OrgRole.EDITOR, OrgRole.ADMIN, OrgRole.OWNER]
        return hierarchy.index(self) >= hierarchy.index(required)


class MembershipStatus(str, enum.Enum):
    """Membership lifecycle states."""

    ACTIVE = "active"
    INVITED = "invited"
    SUSPENDED = "suspended"
    DEACTIVATED = "deactivated"


# =============================================================================
# System Constants
# =============================================================================

# System org — owns shared resources (models, default workflows).
# Never returned for normal user membership resolution.
SYSTEM_ORG_ID = UUID("00000000-0000-0000-0000-000000000001")


# =============================================================================
# Trusted Execution Context
# =============================================================================


@dataclass(frozen=True)
class TenantContext:
    """Trusted execution context resolved from authentication + membership.

    This is the canonical identity for a request. All downstream operations
    (DB queries, storage, job dispatch) receive this context — never raw
    user-supplied org_id values.

    Fields:
        user_id: Supabase auth user UUID (from JWT 'sub' claim)
        org_id: Resolved organisation UUID (from org_members lookup)
        role: User's role within this organisation
        email: User's email (from JWT, informational only)
    """

    user_id: str
    org_id: str
    role: OrgRole
    email: str | None = None

    @property
    def is_owner(self) -> bool:
        return self.role == OrgRole.OWNER

    @property
    def is_admin_or_above(self) -> bool:
        return self.role.has_privilege(OrgRole.ADMIN)

    @property
    def is_editor_or_above(self) -> bool:
        return self.role.has_privilege(OrgRole.EDITOR)

    def require_role(self, minimum: OrgRole) -> None:
        """Raise 403 if the user lacks the required role.

        Usage:
            ctx.require_role(OrgRole.ADMIN)  # raises if viewer or editor
        """
        if not self.role.has_privilege(minimum):
            from fastapi import HTTPException, status

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires {minimum.value} role or higher. You have: {self.role.value}",
            )


# =============================================================================
# Membership Resolution
# =============================================================================


class MembershipError(Exception):
    """Raised when membership cannot be resolved."""

    def __init__(self, detail: str, status_code: int = 403) -> None:
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


def resolve_membership(user_id: str, preferred_org_id: str | None = None) -> TenantContext:
    """Resolve a user's active membership to produce a TenantContext.

    Args:
        user_id: The authenticated user's UUID (from JWT 'sub' claim).
        preferred_org_id: Optional org_id hint from JWT app_metadata
                          (used for multi-workspace users).

    Returns:
        TenantContext with resolved org_id and role.

    Raises:
        MembershipError: If user has no active membership.
    """
    if not is_supabase_configured():
        raise MembershipError(
            "Database not configured. Cannot resolve membership.",
            status_code=503,
        )

    from backend.database import get_supabase_client

    client = get_supabase_client()

    # Query all active memberships for this user
    result = (
        client.table("org_members")
        .select("org_id, role, status")
        .eq("user_id", user_id)
        .eq("status", "active")
        .execute()
    )

    memberships = result.data or []

    if not memberships:
        raise MembershipError(
            "No active organisation membership found. "
            "Contact your workspace administrator or create an organisation.",
        )

    # Filter out system org (never exposed to normal users)
    user_memberships = [
        m for m in memberships
        if m["org_id"] != str(SYSTEM_ORG_ID)
    ]

    if not user_memberships:
        raise MembershipError(
            "No active organisation membership found.",
        )

    # If preferred_org_id is specified and user has membership in it, use it
    if preferred_org_id and preferred_org_id not in ("default", "org_development"):
        for m in user_memberships:
            if m["org_id"] == preferred_org_id:
                return TenantContext(
                    user_id=user_id,
                    org_id=m["org_id"],
                    role=OrgRole(m["role"]),
                )

    # Otherwise, use the first active membership (most recently joined)
    # In the future, this could be the "last used" workspace
    membership = user_memberships[0]
    return TenantContext(
        user_id=user_id,
        org_id=membership["org_id"],
        role=OrgRole(membership["role"]),
    )


def resolve_membership_or_none(
    user_id: str | None,
    preferred_org_id: str | None = None,
) -> TenantContext | None:
    """Like resolve_membership but returns None instead of raising.

    Useful for optional-auth endpoints where unauthenticated requests
    should proceed without tenant context.
    """
    if not user_id:
        return None

    try:
        return resolve_membership(user_id, preferred_org_id)
    except MembershipError:
        return None

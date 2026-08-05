"""Data Access Migration Helpers — Story 009.

Provides helper functions for gradually migrating existing route handlers
from raw supabase.table() calls to the AuthorizedClient boundary.

These helpers bridge the current AuthUser-based auth (backend/auth.py) to
the AuthorizedClient, making migration incremental without rewriting all
routes at once.

Usage in an existing route:
    from backend.data_access_helpers import get_authorized_client

    @router.get("/talent/{talent_id}")
    def get_talent(talent_id: str, user: AuthUser = Depends(require_auth)):
        client = get_authorized_client(user)
        result = client.select_by_id("talent", talent_id)
        return result.data

For system operations (cron, workers):
    from backend.data_access import system_client, worker_client
    client = system_client(purpose="publish_scheduled", actor="cron:publisher")

MIGRATION STATUS:
    The following files have been migrated to use AuthorizedClient:
    - (none yet — this story establishes the pattern)

    The following files still use raw supabase.table() and are marked
    with # TODO(story-009): migrate to AuthorizedClient:
    - backend/api_v1.py (5 locations)
    - backend/infrastructure/router.py (5 locations)
    - backend/intelligence_engine/context.py (3 locations)
    - backend/training/router.py (multiple)
    - 19 files with _db() pattern (see inventory in Story 009 report)
"""

from __future__ import annotations

from backend.auth import AuthUser
from backend.data_access import (
    AuthorizedClient,
    AuthorizationError,
    SystemContext,
    WorkerContext,
    authorized_client,
    system_client,
)
from backend.membership import (
    MembershipError,
    OrgRole,
    TenantContext,
    resolve_membership_or_none,
)


def get_authorized_client(user: AuthUser | None) -> AuthorizedClient | None:
    """Bridge AuthUser (from auth.py) to AuthorizedClient.

    Resolves the user's membership to produce a TenantContext, then wraps
    it in an AuthorizedClient. Returns None if user is None or has no
    active membership (dev mode without org_members populated).

    For routes that REQUIRE authorization, use get_authorized_client_strict().

    Usage:
        client = get_authorized_client(user)
        if client:
            result = client.select("talent")
        else:
            # Fallback: unscoped access (dev mode)
            result = get_talent()
    """
    if not user:
        return None

    # If user already has a resolved org_id from the JWT/membership system
    if user.org_id and user.org_id not in ("default", "org_development"):
        # Build TenantContext directly from AuthUser
        try:
            role = OrgRole(user.role) if user.role in ("owner", "admin", "editor", "viewer") else OrgRole.VIEWER
        except ValueError:
            role = OrgRole.VIEWER

        ctx = TenantContext(
            user_id=user.user_id,
            org_id=user.org_id,
            role=role,
            email=user.email,
        )
        return AuthorizedClient(ctx)

    # Try resolving via org_members table
    ctx = resolve_membership_or_none(user.user_id)
    if ctx:
        return AuthorizedClient(ctx)

    return None


def get_authorized_client_strict(user: AuthUser) -> AuthorizedClient:
    """Bridge AuthUser to AuthorizedClient — raises if no membership.

    Use this for routes that MUST have tenant context.
    Raises HTTP 403 if membership cannot be resolved.

    Usage:
        @router.delete("/talent/{talent_id}")
        def delete_talent(talent_id: str, user: AuthUser = Depends(require_auth)):
            client = get_authorized_client_strict(user)
            client.delete("talent", talent_id)
            return {"deleted": True}
    """
    from fastapi import HTTPException, status

    client = get_authorized_client(user)
    if not client:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Active workspace membership required for this operation.",
        )
    return client


# Re-export for convenience
__all__ = [
    "get_authorized_client",
    "get_authorized_client_strict",
    "AuthorizedClient",
    "AuthorizationError",
    "SystemContext",
    "WorkerContext",
    "system_client",
]

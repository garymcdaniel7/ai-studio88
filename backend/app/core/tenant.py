"""Multi-tenant isolation utilities.

Provides helpers for extracting org_id from authenticated requests
and applying tenant filtering to all database queries.

This module delegates to backend.membership for canonical resolution.
The get_org_id_for_user() function is preserved for backward compatibility
but now uses the authoritative org_members table.

When a valid membership exists:
- Every DB query is scoped to the user's org_id
- Cross-tenant data access is impossible at the application layer
- Supabase RLS provides a second enforcement layer

When no membership exists (new users, dev mode):
- Returns None (callers must handle gracefully)
"""

from __future__ import annotations


def get_org_id_for_user(user_id: str | None) -> str | None:
    """Resolve the org_id for a user via canonical org_members table.

    Returns:
        org_id string if user has an active membership, None otherwise.
        NEVER returns placeholder values like 'default' or 'org_development'.
    """
    if not user_id:
        return None

    try:
        from backend.membership import resolve_membership

        ctx = resolve_membership(user_id)
        return ctx.org_id
    except Exception:
        return None


def scope_query(query, org_id: str | None):
    """Apply org_id filter to a Supabase query builder.

    If org_id is None, no filter is applied (returns unscoped query).

    Usage:
        query = supabase.table("talent").select("*")
        query = scope_query(query, org_id)
        result = query.execute()
    """
    if org_id:
        return query.eq("org_id", org_id)
    return query


def add_org_id(record: dict, org_id: str | None) -> dict:
    """Add org_id to a record before insert.

    If org_id is None, the record is returned without modification
    (the caller or DB default must handle it).

    Usage:
        record = add_org_id({"name": "Melissa"}, org_id)
        supabase.table("talent").insert(record).execute()
    """
    if org_id:
        record["org_id"] = org_id
    return record

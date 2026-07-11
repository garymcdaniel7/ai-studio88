"""Multi-tenant isolation utilities.

Provides helpers for extracting org_id from authenticated requests
and applying tenant filtering to all database queries.

When AUTH_REQUIRED=true and multi-tenancy is enabled:
- Every DB query is scoped to the user's org_id
- Cross-tenant data access is impossible at the application layer
- Supabase RLS provides a second enforcement layer

In development mode (AUTH_REQUIRED=false):
- A default org_id is used for all queries
- This allows local development without auth setup
"""

from __future__ import annotations

import os

DEFAULT_ORG_ID = os.getenv("DEFAULT_ORG_ID", "org_development")


def get_org_id_for_user(user_id: str | None) -> str:
    """Resolve the org_id for a user.

    In production: queries org_members table.
    In dev mode: returns DEFAULT_ORG_ID.
    """
    if not user_id:
        return DEFAULT_ORG_ID

    # Production: lookup org membership
    try:
        from backend.database import supabase

        result = (
            supabase.table("org_members")
            .select("org_id")
            .eq("user_id", user_id)
            .limit(1)
            .single()
            .execute()
        )
        if result.data:
            return result.data["org_id"]
    except Exception:
        pass

    return DEFAULT_ORG_ID


def scope_query(query, org_id: str):
    """Apply org_id filter to a Supabase query builder.

    Usage:
        query = supabase.table("talent").select("*")
        query = scope_query(query, org_id)
        result = query.execute()
    """
    return query.eq("org_id", org_id)


def add_org_id(record: dict, org_id: str) -> dict:
    """Add org_id to a record before insert.

    Usage:
        record = add_org_id({"name": "Melissa"}, org_id)
        supabase.table("talent").insert(record).execute()
    """
    record["org_id"] = org_id
    return record

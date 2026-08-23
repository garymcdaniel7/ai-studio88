"""Tenant-scoped AIOS memory service with defense-in-depth filtering."""

from __future__ import annotations

import logging
from typing import Any

from backend.tenant_context import validate_org_id

logger = logging.getLogger(__name__)


class AiosMemoryService:
    """CRUD and recency recall for the tenant-owned ``aios_memory`` table."""

    def __init__(self, db_client: Any | None = None) -> None:
        self._db_client = db_client

    def _db(self) -> Any:
        if self._db_client is not None:
            return self._db_client
        from backend.database import supabase

        return supabase

    def put(self, org_id: str, key: str, value: Any) -> dict:
        """Upsert one memory entry for a validated tenant."""
        org_id = validate_org_id(org_id)
        if not key.strip():
            raise ValueError("memory key is required")
        record = {"org_id": org_id, "key": key.strip(), "value": value}
        result = (
            self._db()
            .table("aios_memory")
            .upsert(record, on_conflict="org_id,key")
            .execute()
        )
        return result.data[0] if result.data else record

    def get(self, org_id: str, key: str) -> dict | None:
        """Read a memory entry only within the requesting tenant."""
        org_id = validate_org_id(org_id)
        result = (
            self._db()
            .table("aios_memory")
            .select("*")
            .eq("org_id", org_id)
            .eq("key", key)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    def delete(self, org_id: str, key: str) -> bool:
        """Delete one memory entry only within the requesting tenant."""
        org_id = validate_org_id(org_id)
        result = (
            self._db()
            .table("aios_memory")
            .delete()
            .eq("org_id", org_id)
            .eq("key", key)
            .execute()
        )
        return bool(result.data)

    def recall(self, org_id: str, limit: int = 5) -> list[dict]:
        """Return the most recently updated entries for one tenant."""
        org_id = validate_org_id(org_id)
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")
        result = (
            self._db()
            .table("aios_memory")
            .select("*")
            .eq("org_id", org_id)
            .order("updated_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []


def recall_context(org_id: str, limit: int = 5, db_client: Any | None = None) -> str:
    """Return formatted, tenant-scoped memory context for an AIOS prompt."""
    from backend.aios.persona import render_memory_context

    return render_memory_context(AiosMemoryService(db_client).recall(org_id, limit))

"""Durable repository contract for tenant-scoped compliance state."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Protocol


class ComplianceRepository(Protocol):
    """Persistence operations required by quarantine and takedown workflows."""

    def record_quarantine(
        self,
        *,
        org_id: str,
        asset_id: str | None,
        reason: str,
        source_type: str,
        matched_terms: Sequence[str],
        phash: str | None,
    ) -> dict[str, Any]:
        """Persist a quarantine event or update an indexed asset."""

    def get_quarantine(self, asset_id: str, org_id: str) -> dict[str, Any] | None:
        """Return a quarantined asset for its owning tenant."""

    def list_quarantines(self) -> list[dict[str, Any]]:
        """Return persisted quarantine records."""

    def register_asset(self, asset_id: str, org_id: str, phash: str) -> dict[str, Any]:
        """Persist an asset hash without marking the asset quarantined."""

    def get_asset_index(self, asset_id: str, org_id: str) -> dict[str, Any] | None:
        """Return an indexed asset only within its owning tenant."""

    def find_assets_by_phash_for_compliance(self, phash: str) -> list[dict[str, Any]]:
        """Run the explicitly privileged cross-tenant copy-sweep lookup."""

    def create_case(self, values: Mapping[str, Any]) -> dict[str, Any]:
        """Persist a new takedown case."""

    def get_case(self, case_id: str) -> dict[str, Any] | None:
        """Return a persisted takedown case by ID."""

    def update_case(self, case_id: str, org_id: str, values: Mapping[str, Any]) -> dict[str, Any]:
        """Persist a tenant-owned takedown state transition."""

    def list_open_cases(self) -> list[dict[str, Any]]:
        """Return received or escalated cases for SLA monitoring."""


class SupabaseComplianceRepository:
    """Synchronous Supabase repository using the backend service-role client."""

    def __init__(self, client: Any | None = None) -> None:
        """Create a repository, optionally with an injected Supabase client."""
        self._client = client

    @property
    def client(self) -> Any:
        """Lazily resolve the backend-only Supabase client."""
        if self._client is None:
            from backend.database import get_supabase_client

            self._client = get_supabase_client()
        return self._client

    def record_quarantine(
        self,
        *,
        org_id: str,
        asset_id: str | None,
        reason: str,
        source_type: str,
        matched_terms: Sequence[str],
        phash: str | None,
    ) -> dict[str, Any]:
        """Upsert a tenant asset quarantine without losing its original index row."""
        values = {
            "org_id": org_id,
            "asset_id": asset_id,
            "reason": reason,
            "source_type": source_type,
            "matched_terms": list(matched_terms),
            "phash": phash,
            "is_quarantined": True,
        }
        if asset_id is not None:
            existing = self.get_asset_index(asset_id, org_id)
            if existing is not None:
                values.pop("org_id")
                values.pop("asset_id")
                result = (
                    self.client.table("quarantined_assets")
                    .update(values)
                    .eq("id", existing["id"])
                    .eq("org_id", org_id)
                    .execute()
                )
                return result.data[0] if result.data else {**existing, **values}
        result = self.client.table("quarantined_assets").insert(values).execute()
        return result.data[0]

    def get_quarantine(self, asset_id: str, org_id: str) -> dict[str, Any] | None:
        """Read quarantine state with an explicit tenant predicate."""
        result = (
            self.client.table("quarantined_assets")
            .select("*")
            .eq("asset_id", asset_id)
            .eq("org_id", org_id)
            .eq("is_quarantined", True)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    def list_quarantines(self) -> list[dict[str, Any]]:
        """Read all quarantine evidence through the backend service-role client."""
        result = (
            self.client.table("quarantined_assets")
            .select("*")
            .eq("is_quarantined", True)
            .order("created_at")
            .execute()
        )
        return list(result.data or [])

    def register_asset(self, asset_id: str, org_id: str, phash: str) -> dict[str, Any]:
        """Upsert an asset hash while preserving an existing quarantine flag."""
        existing = self.get_asset_index(asset_id, org_id)
        if existing is not None:
            result = (
                self.client.table("quarantined_assets")
                .update({"phash": phash, "updated_at": datetime.utcnow().isoformat()})
                .eq("id", existing["id"])
                .eq("org_id", org_id)
                .execute()
            )
            return result.data[0] if result.data else {**existing, "phash": phash}
        result = (
            self.client.table("quarantined_assets")
            .insert(
                {
                    "org_id": org_id,
                    "asset_id": asset_id,
                    "phash": phash,
                    "reason": "asset-index",
                    "source_type": "asset_index",
                    "matched_terms": [],
                    "is_quarantined": False,
                }
            )
            .execute()
        )
        return result.data[0]

    def get_asset_index(self, asset_id: str, org_id: str) -> dict[str, Any] | None:
        """Read an indexed asset with tenant ownership enforced."""
        result = (
            self.client.table("quarantined_assets")
            .select("*")
            .eq("asset_id", asset_id)
            .eq("org_id", org_id)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    def find_assets_by_phash_for_compliance(self, phash: str) -> list[dict[str, Any]]:
        """Perform the service-role-only global pHash copy sweep."""
        result = (
            self.client.table("quarantined_assets")
            .select("asset_id,org_id,phash")
            .eq("phash", phash)
            .execute()
        )
        return [row for row in (result.data or []) if row.get("asset_id") is not None]

    def create_case(self, values: Mapping[str, Any]) -> dict[str, Any]:
        """Insert a takedown case and return the persisted row."""
        result = self.client.table("takedown_cases").insert(dict(values)).execute()
        return result.data[0]

    def get_case(self, case_id: str) -> dict[str, Any] | None:
        """Read one takedown case by its UUID."""
        result = (
            self.client.table("takedown_cases")
            .select("*")
            .eq("id", case_id)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    def update_case(self, case_id: str, org_id: str, values: Mapping[str, Any]) -> dict[str, Any]:
        """Update a case only when its tenant owner matches."""
        result = (
            self.client.table("takedown_cases")
            .update(dict(values))
            .eq("id", case_id)
            .eq("org_id", org_id)
            .execute()
        )
        return result.data[0] if result.data else {"id": case_id, "org_id": org_id, **values}

    def list_open_cases(self) -> list[dict[str, Any]]:
        """Return cases eligible for SLA monitoring."""
        result = (
            self.client.table("takedown_cases")
            .select("*")
            .in_("status", ["received", "escalated"])
            .execute()
        )
        return list(result.data or [])


_default_repository: ComplianceRepository | None = None


def get_compliance_repository() -> ComplianceRepository:
    """Return the process-wide durable repository, constructed lazily."""
    global _default_repository
    if _default_repository is None:
        _default_repository = SupabaseComplianceRepository()
    return _default_repository


def set_compliance_repository(repository: ComplianceRepository | None) -> None:
    """Override the repository for isolated tests or an application adapter."""
    global _default_repository
    _default_repository = repository

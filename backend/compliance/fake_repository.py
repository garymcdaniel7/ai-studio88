"""In-memory compliance repository used only by unit tests."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


class InMemoryComplianceRepository:
    """Deterministic fake implementing the durable compliance repository contract."""

    def __init__(self) -> None:
        """Initialize isolated quarantine, asset-index, and case stores."""
        self._quarantines: dict[tuple[str, str | None], dict[str, Any]] = {}
        self._assets: dict[tuple[str, str], dict[str, Any]] = {}
        self._cases: dict[str, dict[str, Any]] = {}

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
        """Persist or update a fake quarantine row."""
        key = (org_id, asset_id) if asset_id is not None else (org_id, str(uuid4()))
        row = self._quarantines.get(key)
        if row is None:
            row = {
                "id": str(uuid4()),
                "org_id": org_id,
                "asset_id": asset_id,
                "created_at": datetime.now(UTC),
            }
        row.update(
            {
                "reason": reason,
                "source_type": source_type,
                "matched_terms": list(matched_terms),
                "phash": phash,
                "is_quarantined": True,
                "updated_at": datetime.now(UTC),
            }
        )
        self._quarantines[key] = row
        if asset_id is not None:
            self._assets[(org_id, asset_id)] = row
        return dict(row)

    def get_quarantine(self, asset_id: str, org_id: str) -> dict[str, Any] | None:
        """Read a quarantined row for one tenant."""
        row = self._assets.get((org_id, asset_id))
        return dict(row) if row and row.get("is_quarantined") else None

    def list_quarantines(self) -> list[dict[str, Any]]:
        """Return only rows representing quarantine evidence."""
        return [dict(row) for row in self._quarantines.values() if row.get("is_quarantined")]

    def register_asset(self, asset_id: str, org_id: str, phash: str) -> dict[str, Any]:
        """Persist an asset hash without clearing quarantine state."""
        key = (org_id, asset_id)
        row = self._assets.get(key)
        if row is None:
            row = {
                "id": str(uuid4()),
                "org_id": org_id,
                "asset_id": asset_id,
                "reason": "asset-index",
                "source_type": "asset_index",
                "matched_terms": [],
                "is_quarantined": False,
                "created_at": datetime.now(UTC),
            }
            self._assets[key] = row
            self._quarantines[(org_id, asset_id)] = row
        row["phash"] = phash
        row["updated_at"] = datetime.now(UTC)
        return dict(row)

    def get_asset_index(self, asset_id: str, org_id: str) -> dict[str, Any] | None:
        """Read an indexed asset only within its tenant."""
        row = self._assets.get((org_id, asset_id))
        return dict(row) if row else None

    def find_assets_by_phash_for_compliance(self, phash: str) -> list[dict[str, Any]]:
        """Return all matching tenants through the explicit compliance seam."""
        return [
            {"asset_id": row["asset_id"], "org_id": row["org_id"], "phash": row["phash"]}
            for row in self._assets.values()
            if row.get("phash") == phash and row.get("asset_id") is not None
        ]

    def create_case(self, values: Mapping[str, Any]) -> dict[str, Any]:
        """Persist and return a copy of a fake takedown case."""
        row = dict(values)
        self._cases[str(row["id"])] = row
        return dict(row)

    def get_case(self, case_id: str) -> dict[str, Any] | None:
        """Read a fake case by ID."""
        row = self._cases.get(case_id)
        return dict(row) if row else None

    def update_case(self, case_id: str, org_id: str, values: Mapping[str, Any]) -> dict[str, Any]:
        """Update a fake case while checking its owning tenant."""
        row = self._cases[case_id]
        if row["org_id"] != org_id:
            raise PermissionError("case does not belong to organization")
        row.update(values)
        return dict(row)

    def list_open_cases(self) -> list[dict[str, Any]]:
        """Return fake cases that remain within the SLA workflow."""
        return [
            dict(row)
            for row in self._cases.values()
            if row["status"] in {"received", "escalated"}
        ]

    def clear_for_tests(self) -> None:
        """Reset fake state without exposing a production deletion operation."""
        self._quarantines.clear()
        self._assets.clear()
        self._cases.clear()

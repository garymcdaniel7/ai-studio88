"""Mocked AssetService lifecycle checks for Group 17.4."""

from __future__ import annotations

import importlib
import sys
import types
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from group_17_4_common import (
    ASSET_A,
    DELETION_A,
    JOB_A,
    ORG_A,
    ORG_B,
    TALENT_A,
    CheckResult,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


def _load_storage_leaf_module() -> types.ModuleType:
    """Load provider storage without unrelated circular aggregator imports."""
    package_name = "backend.app.providers"
    if package_name not in sys.modules:
        package = types.ModuleType(package_name)
        package.__path__ = [str(REPOSITORY_ROOT / "backend/app/providers")]
        sys.modules[package_name] = package
    return importlib.import_module("backend.app.providers.storage")


_provider_storage = _load_storage_leaf_module()
StorageProviderType = _provider_storage.StorageProviderType
from backend.app.services.asset_service import AssetNotFoundError, AssetService


class MemoryRepository:
    """In-memory AssetRepository recording lifecycle ordering and tenant scope."""

    def __init__(self) -> None:
        now = datetime.now(UTC).isoformat()
        self.asset = {
            "id": str(ASSET_A),
            "org_id": str(ORG_A),
            "storage_provider": "b2",
            "storage_key": f"{ORG_A}/images/{TALENT_A}/{JOB_A}/asset.webp",
            "content_type": "image/webp",
            "file_size_bytes": 128,
            "filename": "asset.webp",
            "asset_type": "image",
            "talent_id": str(TALENT_A),
            "job_id": str(JOB_A),
            "checksum_sha256": "local-checksum",
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        }
        self.pending: list[dict] = []
        self.events: list[str] = []

    async def get_by_id_and_org(self, asset_id: UUID, org_id: UUID) -> dict | None:
        """Return an asset only when both ID and trusted org match."""
        self.events.append("repository.get")
        if asset_id == ASSET_A and org_id == ORG_A:
            return dict(self.asset)
        return None

    async def list_assets(
        self,
        org_id: UUID,
        limit: int = 20,
        offset: int = 0,
        talent_id: UUID | None = None,
        job_id: UUID | None = None,
        asset_type: str | None = None,
    ) -> tuple[list[dict], int]:
        """List only records belonging to the requested organization."""
        self.events.append("repository.list")
        if org_id != ORG_A:
            return [], 0
        return [dict(self.asset)], 1

    async def soft_delete(self, asset_id: UUID, org_id: UUID) -> bool:
        """Record the database soft-delete before pending storage cleanup."""
        self.events.append("repository.soft_delete")
        if asset_id != ASSET_A or org_id != ORG_A:
            return False
        self.asset["deleted_at"] = datetime.now(UTC).isoformat()
        return True

    async def insert_pending_deletion(self, record: dict) -> dict:
        """Persist a pending deletion record without touching storage."""
        self.events.append("repository.pending_deletion")
        self.pending.append(dict(record, id=str(DELETION_A)))
        return self.pending[-1]

    async def get_pending_deletions(self, limit: int = 50) -> list[dict]:
        """Return the bounded pending deletion batch."""
        self.events.append("repository.get_pending")
        return [row for row in self.pending if "processed_at" not in row][:limit]

    async def mark_deletion_processed(
        self, deletion_id: UUID, error: str | None = None
    ) -> None:
        """Record worker completion or an actionable worker error."""
        self.events.append("repository.mark_processed")
        for row in self.pending:
            if row["id"] == str(deletion_id):
                row["processed_at"] = datetime.now(UTC).isoformat()
                row["error"] = error


class MemoryStorage:
    """In-memory storage provider that records worker deletion calls."""

    def __init__(self, events: list[str]) -> None:
        self.events = events

    async def delete(self, storage_key: str) -> None:
        """Record physical deletion only when the worker invokes it."""
        self.events.append("storage.delete")


async def check_asset_lifecycle() -> list[CheckResult]:
    """Run mocked tenant isolation, soft-delete ordering, and worker checks."""
    repository = MemoryRepository()
    events = repository.events
    provider = MemoryStorage(events)
    service = AssetService(repository, provider, StorageProviderType.B2)
    results: list[CheckResult] = []

    try:
        await service.get_asset(ASSET_A, ORG_B)
    except AssetNotFoundError:
        foreign_read_denied = True
    else:
        foreign_read_denied = False
    _, foreign_total = await service.list_assets(ORG_B)
    if foreign_read_denied and foreign_total == 0:
        results.append(
            CheckResult(
                "Org A/B isolation",
                "LOCAL-MOCK-PASS",
                "foreign read and list return no asset",
            )
        )
    else:
        results.append(CheckResult("Org A/B isolation", "FAIL", "foreign tenant could observe an asset"))

    await service.delete_asset(ASSET_A, ORG_A)
    before_worker = list(events)
    if (
        before_worker.index("repository.soft_delete")
        < before_worker.index("repository.pending_deletion")
        and "storage.delete" not in before_worker
        and repository.asset["deleted_at"] is not None
        and len(repository.pending) == 1
    ):
        results.append(
            CheckResult(
                "soft-delete-first ordering",
                "LOCAL-MOCK-PASS",
                "DB mark and pending row precede provider delete",
            )
        )
    else:
        results.append(
            CheckResult("soft-delete-first ordering", "FAIL", "provider deletion occurred too early")
        )

    processed = await service.process_pending_deletions(limit=1)
    after_worker = list(events)
    if (
        processed == 1
        and after_worker.index("storage.delete") > after_worker.index("repository.pending_deletion")
        and repository.pending[0].get("processed_at")
        and repository.pending[0].get("error") is None
    ):
        results.append(
            CheckResult(
                "pending-deletion worker",
                "LOCAL-MOCK-PASS",
                "bounded worker processed pending row after soft delete",
            )
        )
    else:
        results.append(
            CheckResult("pending-deletion worker", "FAIL", "pending deletion lifecycle mismatch")
        )
    return results

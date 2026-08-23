"""NCII takedown cases, durable pHash copy sweeps, and SLA clocks."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from backend.audit_chain import AuditChainService, AuditEventType
from backend.compliance.quarantine import (
    compute_perceptual_hash,
    quarantine_asset,
)
from backend.compliance.repository import (
    ComplianceRepository,
    get_compliance_repository,
)

TAKEDOWN_SLA_HOURS = 48
TAKEDOWN_ESCALATION_HOURS = 24


@dataclass(frozen=True, slots=True)
class IndexedAsset:
    """Minimal operator-side pHash index record."""

    asset_id: str
    org_id: str
    perceptual_hash: str


@dataclass
class TakedownCase:
    """Immutable-request, mutable-workflow representation of a takedown case."""

    id: str
    asset_id: str
    claimant_email: str
    reason: str
    org_id: str
    actor_user_id: str
    received_at: datetime
    sla_deadline: datetime
    escalation_at: datetime
    status: str = "received"
    affected_asset_ids: list[str] = field(default_factory=list)
    escalated_at: datetime | None = None
    removed_at: datetime | None = None
    sla_breached: bool = False

    def to_dict(self) -> dict[str, object]:
        """Serialize the case for API responses and audit summaries."""
        return {
            "id": self.id,
            "asset_id": self.asset_id,
            "claimant_email": self.claimant_email,
            "reason": self.reason,
            "org_id": self.org_id,
            "received_at": self.received_at.isoformat(),
            "sla_deadline": self.sla_deadline.isoformat(),
            "escalation_at": self.escalation_at.isoformat(),
            "status": self.status,
            "affected_asset_ids": list(self.affected_asset_ids),
            "escalated_at": self.escalated_at.isoformat() if self.escalated_at else None,
            "removed_at": self.removed_at.isoformat() if self.removed_at else None,
            "sla_breached": self.sla_breached,
        }


class TakedownService:
    """Manage durable takedown requests and their deterministic SLA workflow."""

    def __init__(self, repository: ComplianceRepository | None = None) -> None:
        """Create a service using the durable repository or an injected fake."""
        self._repository = repository or get_compliance_repository()

    def register_asset(self, asset_id: str, org_id: str, content: bytes) -> IndexedAsset:
        """Persist a generated asset's pHash for future authorized copy sweeps."""
        indexed = IndexedAsset(
            asset_id=asset_id,
            org_id=org_id,
            perceptual_hash=compute_perceptual_hash(content),
        )
        self._repository.register_asset(
            indexed.asset_id,
            indexed.org_id,
            indexed.perceptual_hash,
        )
        return indexed

    def submit(
        self,
        *,
        asset_id: str,
        claimant_email: str,
        reason: str,
        org_id: str,
        actor_user_id: str,
        now: datetime | None = None,
    ) -> TakedownCase:
        """Create a durable case with 24-hour escalation and 48-hour deadlines."""
        received_at = self._utc(now or datetime.now(UTC))
        case_values: dict[str, Any] = {
            "id": self._new_id(),
            "asset_id": asset_id,
            "claimant_email": claimant_email,
            "reason": reason,
            "org_id": org_id,
            "actor_user_id": actor_user_id,
            "received_at": received_at,
            "sla_started_at": received_at,
            "sla_deadline_at": received_at + timedelta(hours=TAKEDOWN_SLA_HOURS),
            "escalation_at": received_at + timedelta(hours=TAKEDOWN_ESCALATION_HOURS),
            "status": "received",
            "affected_asset_ids": [],
            "sla_breached": False,
        }
        case = self._from_row(self._repository.create_case(case_values))
        AuditChainService.emit(
            event_type=AuditEventType.SIDE_EFFECT,
            correlation_id=case.id,
            org_id=org_id,
            actor_user_id=actor_user_id,
            actor_role="authenticated",
            tool="compliance.takedown.submit",
            arguments={"asset_id": asset_id, "reason": reason},
            resource_ids=[asset_id, case.id],
            mandatory=True,
        )
        return case

    def process(self, case_id: str, *, now: datetime | None = None) -> TakedownCase:
        """Remove the target and identical copies, recording an immutable audit."""
        current_time = self._utc(now or datetime.now(UTC))
        row = self._repository.get_case(case_id)
        if row is None:
            raise KeyError(case_id)
        case = self._from_row(row)
        if case.status == "removed":
            return case

        indexed = self._repository.get_asset_index(case.asset_id, case.org_id)
        if indexed is None:
            matching_rows = [{"asset_id": case.asset_id, "org_id": case.org_id}]
        else:
            matching_rows = self._repository.find_assets_by_phash_for_compliance(
                str(indexed.get("phash") or "")
            )
        matching_ids = sorted(
            {str(item["asset_id"]) for item in matching_rows if item.get("asset_id") is not None}
            or {case.asset_id}
        )

        for item in matching_rows:
            asset_id = item.get("asset_id")
            if asset_id is None:
                continue
            quarantine_asset(
                str(asset_id),
                str(item.get("org_id") or case.org_id),
                reason=f"ncii-takedown:{case.id}",
                perceptual_hash=item.get("phash"),
                repository=self._repository,
            )

        escalated_at = case.escalated_at
        if current_time >= case.escalation_at and escalated_at is None:
            escalated_at = case.escalation_at
        changes: dict[str, Any] = {
            "affected_asset_ids": matching_ids,
            "sla_breached": current_time > case.sla_deadline,
            "status": "removed",
            "removed_at": current_time,
            "sla_completed_at": current_time,
            "escalated_at": escalated_at,
        }
        case = self._from_row(
            self._repository.update_case(case.id, case.org_id, changes)
        )
        AuditChainService.emit(
            event_type=AuditEventType.SIDE_EFFECT,
            correlation_id=case.id,
            org_id=case.org_id,
            actor_user_id="system",
            actor_role="compliance",
            tool="compliance.takedown.copy_sweep",
            result={"status": case.status, "affected_asset_ids": case.affected_asset_ids},
            resource_ids=case.affected_asset_ids,
            mandatory=True,
        )
        return case

    def run_sla_monitor(self, *, now: datetime | None = None) -> list[TakedownCase]:
        """Mark open cases escalated at 24h and breached at 48h durably."""
        current_time = self._utc(now or datetime.now(UTC))
        escalated: list[TakedownCase] = []
        for row in self._repository.list_open_cases():
            case = self._from_row(row)
            changes: dict[str, Any] = {}
            if current_time >= case.escalation_at and case.escalated_at is None:
                changes["escalated_at"] = current_time
                changes["status"] = "escalated"
            if current_time > case.sla_deadline and not case.sla_breached:
                changes["sla_breached"] = True
            if not changes:
                continue
            updated = self._repository.update_case(case.id, case.org_id, changes)
            updated_case = self._from_row(updated)
            if updated_case.status == "escalated":
                escalated.append(updated_case)
        return escalated

    def get_case(self, case_id: str) -> TakedownCase | None:
        """Return a durable case by ID."""
        row = self._repository.get_case(case_id)
        return self._from_row(row) if row is not None else None

    @staticmethod
    def _new_id() -> str:
        """Generate a case identifier without relying on database-only defaults."""
        import uuid

        return str(uuid.uuid4())

    @classmethod
    def _from_row(cls, row: dict[str, Any]) -> TakedownCase:
        """Hydrate the legacy public case shape from durable columns."""
        return TakedownCase(
            id=str(row["id"]),
            asset_id=str(row["asset_id"]),
            claimant_email=str(row["claimant_email"]),
            reason=str(row["reason"]),
            org_id=str(row["org_id"]),
            actor_user_id=str(row.get("actor_user_id") or ""),
            received_at=cls._parse_datetime(row["received_at"]),
            sla_deadline=cls._parse_datetime(row.get("sla_deadline_at") or row["sla_deadline"]),
            escalation_at=cls._parse_datetime(row["escalation_at"]),
            status=str(row.get("status") or "received"),
            affected_asset_ids=[str(value) for value in row.get("affected_asset_ids") or []],
            escalated_at=cls._parse_optional_datetime(row.get("escalated_at")),
            removed_at=cls._parse_optional_datetime(row.get("removed_at")),
            sla_breached=bool(row.get("sla_breached", False)),
        )

    @staticmethod
    def _parse_datetime(value: Any) -> datetime:
        """Parse a database timestamp and normalize it to UTC."""
        if isinstance(value, datetime):
            return TakedownService._utc(value)
        return TakedownService._utc(datetime.fromisoformat(str(value).replace("Z", "+00:00")))

    @staticmethod
    def _parse_optional_datetime(value: Any) -> datetime | None:
        """Parse nullable database timestamps."""
        return None if value is None else TakedownService._parse_datetime(value)

    @staticmethod
    def _utc(value: datetime) -> datetime:
        """Normalize naive staging-clock values to UTC."""
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


_takedown_service = TakedownService()


def get_takedown_service() -> TakedownService:
    """Return the process-wide durable takedown service."""
    return _takedown_service

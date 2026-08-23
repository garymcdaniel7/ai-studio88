"""NCII takedown cases, perceptual-hash copy sweeps, and SLA clocks."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from backend.audit_chain import AuditChainService, AuditEventType
from backend.compliance.quarantine import compute_perceptual_hash, quarantine_asset

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
    """Manage takedown requests and their deterministic staging-clock workflow."""

    def __init__(self) -> None:
        self._assets: dict[str, IndexedAsset] = {}
        self._hash_index: dict[str, set[str]] = {}
        self._cases: dict[str, TakedownCase] = {}
        self._lock = threading.RLock()

    def register_asset(self, asset_id: str, org_id: str, content: bytes) -> IndexedAsset:
        """Index a generated asset by its deterministic perceptual hash."""
        indexed = IndexedAsset(
            asset_id=asset_id,
            org_id=org_id,
            perceptual_hash=compute_perceptual_hash(content),
        )
        with self._lock:
            previous = self._assets.get(asset_id)
            if previous is not None:
                self._hash_index[previous.perceptual_hash].discard(asset_id)
            self._assets[asset_id] = indexed
            self._hash_index.setdefault(indexed.perceptual_hash, set()).add(asset_id)
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
        """Create a case with 24-hour escalation and 48-hour SLA deadlines."""
        received_at = self._utc(now or datetime.now(UTC))
        case = TakedownCase(
            id=str(uuid.uuid4()),
            asset_id=asset_id,
            claimant_email=claimant_email,
            reason=reason,
            org_id=org_id,
            actor_user_id=actor_user_id,
            received_at=received_at,
            sla_deadline=received_at + timedelta(hours=TAKEDOWN_SLA_HOURS),
            escalation_at=received_at + timedelta(hours=TAKEDOWN_ESCALATION_HOURS),
        )
        with self._lock:
            self._cases[case.id] = case

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
        with self._lock:
            case = self._cases[case_id]
            indexed = self._assets.get(case.asset_id)
            if indexed is None:
                matching_ids = {case.asset_id}
            else:
                matching_ids = set(self._hash_index.get(indexed.perceptual_hash, {case.asset_id}))
            case.affected_asset_ids = sorted(matching_ids)
            case.sla_breached = current_time > case.sla_deadline
            for asset_id in case.affected_asset_ids:
                asset = self._assets.get(asset_id)
                quarantine_asset(
                    asset_id,
                    asset.org_id if asset else case.org_id,
                    reason=f"ncii-takedown:{case.id}",
                    perceptual_hash=asset.perceptual_hash if asset else None,
                )
            case.status = "removed"
            case.removed_at = current_time
            if current_time >= case.escalation_at and case.escalated_at is None:
                case.escalated_at = case.escalation_at

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
        """Mark open cases escalated at 24h and breached at 48h."""
        current_time = self._utc(now or datetime.now(UTC))
        escalated: list[TakedownCase] = []
        with self._lock:
            for case in self._cases.values():
                if case.status == "removed":
                    continue
                if current_time >= case.escalation_at and case.escalated_at is None:
                    case.escalated_at = current_time
                    case.status = "escalated"
                    escalated.append(case)
                if current_time > case.sla_deadline:
                    case.sla_breached = True
        return escalated

    def get_case(self, case_id: str) -> TakedownCase | None:
        """Return a case by ID."""
        with self._lock:
            return self._cases.get(case_id)

    @staticmethod
    def _utc(value: datetime) -> datetime:
        """Normalize naive staging-clock values to UTC."""
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


_takedown_service = TakedownService()


def get_takedown_service() -> TakedownService:
    """Return the process-wide takedown service."""
    return _takedown_service

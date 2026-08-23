"""Unit coverage for AIOS persona, tenant memory, telemetry, craft, and mining."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from backend.aios.craft import CraftLibrary, find_identity_fields
from backend.aios.memory import AiosMemoryService
from backend.aios.miner import CraftMiner, distill_best_craft
from backend.aios.persona import POLICY_MARKER, inject_persona
from backend.aios.telemetry import GenerationTelemetry
from backend.context_precedence import ContextSource, Precedence, resolve_context


@dataclass
class Result:
    data: list[dict]
    count: int | None = None


class FakeQuery:
    def __init__(self, db: FakeDb, table: str) -> None:
        self.db = db
        self.table_name = table
        self.rows = db.rows.setdefault(table, [])
        self.filters: list[tuple[str, Any]] = []
        self.mode = "select"
        self.payload: dict | None = None
        self.or_filter: str | None = None
        self.limit_value: int | None = None

    def select(self, *_args: Any, **_kwargs: Any) -> FakeQuery:
        self.mode = "select"
        return self

    def insert(self, payload: dict) -> FakeQuery:
        self.mode, self.payload = "insert", payload
        return self

    def upsert(self, payload: dict, **_kwargs: Any) -> FakeQuery:
        self.mode, self.payload = "upsert", payload
        return self

    def update(self, payload: dict) -> FakeQuery:
        self.mode, self.payload = "update", payload
        return self

    def delete(self) -> FakeQuery:
        self.mode = "delete"
        return self

    def eq(self, key: str, value: Any) -> FakeQuery:
        self.filters.append((key, value))
        return self

    def or_(self, expression: str) -> FakeQuery:
        self.or_filter = expression
        return self

    def order(self, *_args: Any, **_kwargs: Any) -> FakeQuery:
        return self

    def limit(self, value: int) -> FakeQuery:
        self.limit_value = value
        return self

    def execute(self) -> Result:
        matched = [row for row in self.rows if all(row.get(k) == v for k, v in self.filters)]
        if self.or_filter:
            matched = [
                row
                for row in self.rows
                if row.get("global") is True
                or any(row.get("org_id") == part.split(".eq.", 1)[1] for part in self.or_filter.split(",") if "org_id.eq." in part)
            ]
        if self.mode == "insert":
            row = dict(self.payload or {})
            row.setdefault("id", f"{self.table_name}-{len(self.rows) + 1}")
            self.rows.append(row)
            return Result([row])
        if self.mode == "upsert":
            row = dict(self.payload or {})
            existing = next((r for r in self.rows if r.get("org_id") == row.get("org_id") and r.get("key") == row.get("key")), None)
            if existing:
                existing.update(row)
                return Result([existing])
            row.setdefault("id", f"{self.table_name}-{len(self.rows) + 1}")
            self.rows.append(row)
            return Result([row])
        if self.mode == "delete":
            deleted = [row for row in self.rows if row in matched]
            self.db.rows[self.table_name] = [row for row in self.rows if row not in matched]
            return Result(deleted)
        if self.mode == "update":
            for row in matched:
                row.update(self.payload or {})
            return Result(matched)
        if self.limit_value is not None:
            matched = matched[: self.limit_value]
        return Result(matched)


class FakeDb:
    def __init__(self) -> None:
        self.rows: dict[str, list[dict]] = {}

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self, name)


@pytest.mark.unit
def test_persona_injects_and_governance_wins() -> None:
    prompt = inject_persona("base model prompt", "BLOCK external publishing")
    assert "AIOS Soul" in prompt
    assert POLICY_MARKER in prompt
    assert prompt.index("AIOS Soul") < prompt.index("BLOCK external publishing")

    resolved = resolve_context(
        [
            ContextSource("action", "allow", Precedence.EXPLICIT_REQUEST),
            ContextSource("action", "block", Precedence.GOVERNANCE),
        ]
    )
    assert resolved.effective["action"] == "block"


@pytest.mark.unit
def test_memory_isolation_requires_and_filters_org() -> None:
    db = FakeDb()
    service = AiosMemoryService(db)
    service.put("org-a", "tone", {"value": "direct"})
    service.put("org-b", "tone", {"value": "warm"})

    assert service.get("org-a", "tone")["value"] == {"value": "direct"}
    assert service.get("org-a", "missing") is None
    assert service.get("org-b", "tone")["value"] == {"value": "warm"}
    with pytest.raises(ValueError):
        service.get("", "tone")


@pytest.mark.unit
def test_telemetry_hashes_prompt_and_writes_completion() -> None:
    db = FakeDb()
    event = GenerationTelemetry(db).record_event(
        "org-a", model="flux", prompt="private prompt", params={"steps": 4}, seed=7, duration_ms=120, cost_usd=0.02
    )
    assert event["org_id"] == "org-a"
    assert event["prompt_hash"] != "private prompt"
    assert len(event["prompt_hash"]) == 64


@pytest.mark.unit
def test_craft_visibility_and_global_identity_rule() -> None:
    db = FakeDb()
    library = CraftLibrary(db)
    library.create(model="flux", category="portrait", recipe={"camera": "85mm"}, is_global=True)
    library.create(model="flux", category="portrait", recipe={"camera": "35mm"}, org_id="org-a")
    assert len(library.list_visible("org-a")) == 2
    assert len(library.list_visible("org-b")) == 1
    assert find_identity_fields({"camera": {"talent_id": "private"}})
    with pytest.raises(ValueError, match="identity/IP"):
        library.create(model="flux", category="portrait", recipe={"talent_id": "private"}, is_global=True)


@pytest.mark.unit
def test_miner_drops_low_unrated_and_identity_but_selects_best() -> None:
    events = [
        {"id": "low", "model": "flux", "rating": 3, "params": {"steps": 8}},
        {"id": "private", "model": "flux", "rating": 5, "params": {"voice_profile_id": "secret"}},
        {"id": "best", "model": "flux", "rating": 5, "params": {"steps": 20, "camera": "close"}},
        {"id": "unrated", "model": "flux", "params": {"steps": 12}},
    ]
    draft = distill_best_craft(events)
    assert draft is not None
    assert draft.source_event_id == "best"
    assert CraftMiner().mine(events).recipe["camera"] == "close"

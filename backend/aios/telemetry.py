"""Durable generation telemetry at the canonical completion boundary."""

from __future__ import annotations

import hashlib
from typing import Any

from backend.tenant_context import validate_org_id


class GenerationTelemetry:
    """Write generation events and recipe ratings through an injectable client."""

    def __init__(self, db_client: Any | None = None) -> None:
        self._db_client = db_client

    def _db(self) -> Any:
        if self._db_client is not None:
            return self._db_client
        from backend.database import supabase

        return supabase

    @staticmethod
    def prompt_hash(prompt: str) -> str:
        """Return a stable, non-reversible prompt fingerprint."""
        return hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    def record_event(
        self,
        org_id: str,
        *,
        model: str,
        prompt: str,
        params: dict[str, Any] | None = None,
        seed: int | None = None,
        duration_ms: int = 0,
        cost_usd: float = 0.0,
        status: str = "completed",
    ) -> dict:
        """Persist one completed or explicitly failed generation event."""
        org_id = validate_org_id(org_id)
        if not model.strip():
            raise ValueError("model is required")
        if duration_ms < 0 or cost_usd < 0:
            raise ValueError("duration_ms and cost_usd cannot be negative")
        record = {
            "org_id": org_id,
            "model": model,
            "prompt_hash": self.prompt_hash(prompt),
            "params": params or {},
            "seed": seed,
            "duration_ms": duration_ms,
            "cost_usd": cost_usd,
            "status": status,
        }
        result = self._db().table("generation_events").insert(record).execute()
        return result.data[0] if result.data else record

    def record_rating(
        self,
        generation_event_id: str,
        rating: int,
        note: str = "",
        *,
        db_client: Any | None = None,
    ) -> dict:
        """Persist a 1–5 recipe rating for a generation event."""
        if not generation_event_id:
            raise ValueError("generation_event_id is required")
        if rating < 1 or rating > 5:
            raise ValueError("rating must be between 1 and 5")
        db = db_client or self._db()
        record = {
            "generation_event_id": generation_event_id,
            "rating": rating,
            "note": note,
        }
        result = db.table("recipe_ratings").insert(record).execute()
        return result.data[0] if result.data else record

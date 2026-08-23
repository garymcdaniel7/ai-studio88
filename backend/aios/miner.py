"""Manual, approval-gated mining of reusable craft from generation outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.aios.craft import find_identity_fields


@dataclass(frozen=True)
class CraftDraft:
    """A craft-only draft awaiting human promotion review."""

    model: str
    category: str
    recipe: dict[str, Any]
    source_event_id: str
    rating: int

    def to_dict(self) -> dict[str, Any]:
        """Serialize a draft for storage or approval parameters."""
        return {
            "model": self.model,
            "category": self.category,
            "recipe": self.recipe,
            "source_event_id": self.source_event_id,
            "rating": self.rating,
            "status": "draft",
        }


def distill_best_craft(events: list[dict[str, Any]], minimum_rating: int = 4) -> CraftDraft | None:
    """Choose the highest-rated recent generation and strip unsafe identity data."""
    candidates: list[tuple[int, dict[str, Any], dict[str, Any]]] = []
    for event in events:
        rating = event.get("rating")
        if not isinstance(rating, int) or rating < minimum_rating:
            continue
        recipe = event.get("recipe") or event.get("params") or {}
        if find_identity_fields(recipe):
            continue
        candidates.append((rating, event, recipe))
    if not candidates:
        return None
    rating, event, recipe = max(
        candidates,
        key=lambda item: (item[0], item[1].get("created_at", ""), item[1].get("id", "")),
    )
    return CraftDraft(
        model=str(event.get("model", "")),
        category=str(event.get("category", "generation")),
        recipe=recipe,
        source_event_id=str(event.get("id", "")),
        rating=rating,
    )


class CraftMiner:
    """Build drafts from supplied query results and enqueue manual approval."""

    def mine(self, events: list[dict[str, Any]], minimum_rating: int = 4) -> CraftDraft | None:
        """Distill one craft-only draft; this method performs no promotion."""
        return distill_best_craft(events, minimum_rating)

    def enqueue_promotion(self, draft: CraftDraft, *, org_id: str, session_id: str) -> dict:
        """Ask the existing governance queue for manual global promotion review."""
        from backend.aios.governance.queue import enqueue_approval

        return enqueue_approval(
            session_id=session_id,
            org_id=org_id,
            tool="craft.promote_global",
            parameters=draft.to_dict(),
            reasoning="Promote a human-reviewed craft-only recipe; no auto-promotion.",
            agent="aios-craft-miner",
        )

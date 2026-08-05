"""Memory Provenance & Truthful Labeling — Story 044.

Provides provenance-aware memory retrieval and prompt assembly.
Replaces the fabricated _production_memory defaults with truthful
retrieval from the durable memory_service (Story 040).

Rules:
1. NEVER present unstored data as "remembered" information
2. ALWAYS label memory items with their provenance type
3. Inferred content MUST be visually/textually distinct from confirmed facts
4. Empty memory produces a truthful "no memories" state (not fabricated defaults)
5. Prompt assembly separates confirmed facts from uncertain context

Provenance types (from memory_service.MemoryProvenance):
    user_confirmed  — User explicitly stated this (highest trust)
    inferred        — AI observed this from behavior (medium trust)
    imported        — Imported from external source (trust depends on source)
    system          — System-generated defaults (lowest trust, labeled as defaults)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Provenance Labels for Display
# =============================================================================


class ProvenanceLabel(str, Enum):
    """Human-readable labels for memory provenance in UI and prompts."""
    CONFIRMED = "confirmed"       # User said this explicitly
    OBSERVED = "observed"         # AI noticed this from usage patterns
    IMPORTED = "imported"         # Came from an external source
    SUGGESTED = "suggested"       # AI suggestion, not yet confirmed
    DEFAULT = "default"           # System default, never presented as learned


PROVENANCE_DISPLAY: dict[str, ProvenanceLabel] = {
    "user_confirmed": ProvenanceLabel.CONFIRMED,
    "inferred": ProvenanceLabel.OBSERVED,
    "imported": ProvenanceLabel.IMPORTED,
    "system": ProvenanceLabel.DEFAULT,
}

PROVENANCE_TRUST_ORDER = [
    ProvenanceLabel.CONFIRMED,   # Highest trust
    ProvenanceLabel.IMPORTED,
    ProvenanceLabel.OBSERVED,
    ProvenanceLabel.SUGGESTED,
    ProvenanceLabel.DEFAULT,     # Lowest trust
]


# =============================================================================
# Labeled Memory Item
# =============================================================================


@dataclass
class LabeledMemory:
    """A memory item with explicit provenance labeling for display."""
    category: str
    key: str
    value: Any
    label: ProvenanceLabel
    confidence: float
    source_description: str  # "You told me on Jul 15" or "Observed from your generations"
    is_confirmed: bool       # Only True for user_confirmed provenance
    can_be_used_in_prompts: bool  # Whether this is reliable enough for prompt injection

    def to_display_dict(self) -> dict:
        """Serialize for API/UI display with truthful labeling."""
        return {
            "category": self.category,
            "key": self.key,
            "value": self.value,
            "provenance": self.label.value,
            "confidence": self.confidence,
            "source": self.source_description,
            "confirmed": self.is_confirmed,
        }


# =============================================================================
# Truthful Memory Retrieval
# =============================================================================


def get_labeled_memories(
    org_id: str,
    user_id: str,
    category: str | None = None,
    min_confidence: float = 0.0,
) -> list[LabeledMemory]:
    """Retrieve memory items with truthful provenance labels.

    Returns ONLY items that actually exist in durable storage.
    NEVER fabricates or returns hardcoded defaults as "memories."
    Empty result = truthful "no memories" state.
    """
    if not org_id or not user_id:
        return []  # No context = no memories (truthful empty state)

    try:
        from backend.memory_service import (
            MemoryNamespace,
            recall,
        )
        from backend.membership import OrgRole, TenantContext

        # Create a minimal context for retrieval
        ctx = TenantContext(user_id=user_id, org_id=org_id, role=OrgRole.VIEWER)

        # Retrieve from durable store
        raw_items = recall(ctx, category=category)

        # Label each item with provenance
        labeled = []
        for item in raw_items:
            provenance_raw = item.get("provenance", "inferred")
            label = PROVENANCE_DISPLAY.get(provenance_raw, ProvenanceLabel.OBSERVED)
            confidence = float(item.get("confidence", 0.5))

            # Skip items below confidence threshold
            if confidence < min_confidence:
                continue

            labeled.append(LabeledMemory(
                category=item.get("category", ""),
                key=item.get("key", ""),
                value=item.get("value", {}),
                label=label,
                confidence=confidence,
                source_description=_describe_source(provenance_raw, item),
                is_confirmed=(provenance_raw == "user_confirmed"),
                can_be_used_in_prompts=(confidence >= 0.7 and provenance_raw != "system"),
            ))

        return labeled

    except Exception as e:
        logger.warning(f"Memory retrieval failed (truthful empty state): {e}")
        return []  # Failure = empty (never fabricate)


def get_empty_memory_state() -> dict:
    """Return the truthful "no memories" response.

    This replaces fabricated defaults. Clearly communicates that
    no preferences have been learned yet.
    """
    return {
        "status": "empty",
        "message": "No memories stored yet. I'll learn your preferences as we work together.",
        "items": [],
        "total": 0,
    }


# =============================================================================
# Prompt Assembly — Provenance-Aware Context Injection
# =============================================================================


def assemble_memory_context(
    org_id: str,
    user_id: str,
    max_items: int = 10,
) -> str:
    """Assemble memory context for LLM prompt injection.

    Rules:
    - CONFIRMED facts are injected as "Known facts about this user:"
    - OBSERVED patterns are injected as "Observed preferences (may be inaccurate):"
    - SUGGESTED/DEFAULT items are NEVER injected into prompts
    - Low-confidence items (< 0.7) are excluded from prompt context

    Returns a formatted string for prompt injection, or empty string
    if no reliable memory exists.
    """
    memories = get_labeled_memories(org_id, user_id, min_confidence=0.7)

    if not memories:
        return ""  # No reliable memory — don't inject anything

    # Separate by trust level
    confirmed = [m for m in memories if m.is_confirmed and m.can_be_used_in_prompts]
    observed = [m for m in memories if not m.is_confirmed and m.can_be_used_in_prompts]

    parts = []

    if confirmed:
        parts.append("Known facts about this user:")
        for m in confirmed[:max_items // 2]:
            val = _format_value(m.value)
            parts.append(f"  - {m.key}: {val}")

    if observed:
        parts.append("Observed preferences (may not be current):")
        for m in observed[:max_items // 2]:
            val = _format_value(m.value)
            parts.append(f"  - {m.key}: {val} (confidence: {m.confidence:.0%})")

    return "\n".join(parts)


# =============================================================================
# Production Memory API (replaces fabricated get_production_memory)
# =============================================================================


def get_production_memory_truthful(org_id: str, user_id: str) -> dict:
    """Get production memory with truthful provenance labeling.

    This REPLACES the old get_production_memory() which returned
    hardcoded fabricated defaults.

    Returns either labeled memories or an explicit empty state.
    """
    memories = get_labeled_memories(org_id, user_id)

    if not memories:
        return get_empty_memory_state()

    return {
        "status": "active",
        "items": [m.to_display_dict() for m in memories],
        "total": len(memories),
        "confirmed_count": sum(1 for m in memories if m.is_confirmed),
        "observed_count": sum(1 for m in memories if m.label == ProvenanceLabel.OBSERVED),
    }


# =============================================================================
# Helpers
# =============================================================================


def _describe_source(provenance: str, item: dict) -> str:
    """Generate a human-readable source description."""
    if provenance == "user_confirmed":
        return "You told me this"
    elif provenance == "inferred":
        return "Observed from your activity"
    elif provenance == "imported":
        return "Imported from external source"
    elif provenance == "system":
        return "System default (not learned)"
    return "Unknown source"


def _format_value(value: Any) -> str:
    """Format a memory value for display in prompts."""
    if isinstance(value, dict):
        v = value.get("v", value)
        if isinstance(v, list):
            return ", ".join(str(x) for x in v[:5])
        return str(v)[:100]
    if isinstance(value, list):
        return ", ".join(str(x) for x in value[:5])
    return str(value)[:100]

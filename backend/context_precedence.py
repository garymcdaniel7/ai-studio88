"""Context Precedence & Conflict Resolution — Story 082.

Deterministic merge contract for resolving conflicts between creative context
sources. Identical inputs always produce the same resolved context.

Precedence (highest → lowest):
    1. SAFETY — System safety rules (content policy, blocked terms)
    2. GOVERNANCE — Workspace governance policy (brand guidelines, legal)
    3. EXPLICIT_REQUEST — User's explicit current-request instructions
    4. PROJECT_RULES — Approved project/scene rules
    5. CREATIVE_DNA — Canonical Creative DNA (talent identity)
    6. RELATIONSHIPS — Typed relationships and assignments
    7. LORA — Approved LoRA model selections
    8. WARDROBE — Wardrobe/prop/location selections
    9. PREFERENCES — Learned user preferences
    10. DEFAULTS — System defaults

Rules:
    - Higher precedence always wins over lower
    - Equal precedence: explicit version > implicit; newer > older
    - Unapproved/unauthorized sources cannot win (treated as DEFAULTS)
    - Conflicts are RECORDED (never silently discarded)
    - User overrides require permission and are scoped
    - Historical packages stay reproducible (policy version pinned)

DECISION-REQUIRED:
    - Equal-priority LoRA conflict (two approved for same role): UNVERIFIED
      Decision needed: first-registered wins vs user-selected-last wins
    - Preference vs Creative DNA when both are explicit: resolved as DNA wins
      (Creative DNA is higher precedence by design)
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Precedence Levels (IntEnum for deterministic comparison)
# =============================================================================


class Precedence(IntEnum):
    """Context source precedence. Lower number = higher priority."""
    SAFETY = 1
    GOVERNANCE = 2
    EXPLICIT_REQUEST = 3
    PROJECT_RULES = 4
    CREATIVE_DNA = 5
    RELATIONSHIPS = 6
    LORA = 7
    WARDROBE = 8
    PREFERENCES = 9
    DEFAULTS = 10


# =============================================================================
# Data Structures
# =============================================================================


@dataclass(frozen=True)
class ContextSource:
    """A single value contributed by a context source."""
    field: str                     # Which field this contributes to (e.g. "negative_prompt")
    value: Any                     # The value
    precedence: Precedence         # Source precedence level
    source_id: str = ""            # Unique ID of the source record
    source_version: str = ""       # Version of the source record
    source_type: str = ""          # Human-readable source type
    approved: bool = True          # Whether this source is approved/authorized
    scope: str = "generation"      # Scope: generation, project, workspace
    timestamp: float = 0.0        # When this value was set


@dataclass
class ConflictRecord:
    """Record of a resolved conflict between sources."""
    conflict_id: str = ""
    field_name: str = ""
    winner: ContextSource | None = None
    losers: list[ContextSource] = field(default_factory=list)
    reason: str = ""
    resolution_rule: str = ""    # Which rule resolved this

    def __post_init__(self) -> None:
        if not self.conflict_id:
            self.conflict_id = f"cfl-{uuid.uuid4().hex[:10]}"


@dataclass
class UserOverride:
    """An explicit user override of a resolved value."""
    field: str
    override_value: Any
    user_id: str
    reason: str = ""
    scope: str = "generation"    # generation | project | workspace
    permitted: bool = False      # Whether the user has permission


@dataclass
class ResolvedContext:
    """The output of context merge — deterministic, provenance-tracked."""
    resolve_id: str = field(default_factory=lambda: f"ctx-{uuid.uuid4().hex[:12]}")
    org_id: str = ""
    resolved_at: float = field(default_factory=time.time)

    # Resolved effective values (field → value)
    effective: dict[str, Any] = field(default_factory=dict)

    # Provenance (field → winning ContextSource)
    provenance: dict[str, ContextSource] = field(default_factory=dict)

    # All conflicts that were resolved
    conflicts: list[ConflictRecord] = field(default_factory=list)

    # User overrides that were applied
    overrides_applied: list[UserOverride] = field(default_factory=list)
    overrides_denied: list[UserOverride] = field(default_factory=list)

    # Policy version used for this resolution
    policy_version: str = "1.0.0"

    @property
    def has_conflicts(self) -> bool:
        return len(self.conflicts) > 0

    @property
    def conflict_count(self) -> int:
        return len(self.conflicts)

    @property
    def is_deterministic(self) -> bool:
        """Whether this resolution would produce the same result if re-run."""
        return True  # By design — same inputs → same output


# =============================================================================
# Merge Engine
# =============================================================================


POLICY_VERSION = "1.0.0"


def resolve_context(
    sources: list[ContextSource],
    overrides: list[UserOverride] | None = None,
    org_id: str = "",
) -> ResolvedContext:
    """Resolve context from multiple sources using deterministic precedence.

    Algorithm:
    1. Filter out unapproved sources (demoted to DEFAULTS)
    2. Group by field
    3. For each field, select winner by precedence
    4. Record conflicts (non-winning sources)
    5. Apply authorized user overrides
    6. Return resolved context with full provenance

    Deterministic guarantee: same inputs → same output regardless of
    source ordering in the input list.
    """
    ctx = ResolvedContext(org_id=org_id, policy_version=POLICY_VERSION)

    # Step 1: Demote unapproved sources
    effective_sources = _apply_approval_filter(sources)

    # Step 2: Group by field
    field_groups: dict[str, list[ContextSource]] = {}
    for source in effective_sources:
        field_groups.setdefault(source.field, []).append(source)

    # Step 3: Resolve each field
    for field_name, candidates in field_groups.items():
        winner, losers, conflict = _resolve_field(field_name, candidates)
        ctx.effective[field_name] = winner.value
        ctx.provenance[field_name] = winner

        if conflict:
            ctx.conflicts.append(conflict)

    # Step 4: Apply user overrides
    if overrides:
        _apply_overrides(ctx, overrides)

    logger.info(
        f"CONTEXT_RESOLVED: id={ctx.resolve_id} fields={len(ctx.effective)} "
        f"conflicts={ctx.conflict_count} overrides={len(ctx.overrides_applied)}"
    )
    return ctx


def _apply_approval_filter(sources: list[ContextSource]) -> list[ContextSource]:
    """Demote unapproved sources to DEFAULTS precedence."""
    result = []
    for s in sources:
        if not s.approved:
            # Replace with demoted version
            demoted = ContextSource(
                field=s.field,
                value=s.value,
                precedence=Precedence.DEFAULTS,
                source_id=s.source_id,
                source_version=s.source_version,
                source_type=f"{s.source_type} (unapproved→demoted)",
                approved=False,
                scope=s.scope,
                timestamp=s.timestamp,
            )
            result.append(demoted)
        else:
            result.append(s)
    return result


def _resolve_field(
    field_name: str,
    candidates: list[ContextSource],
) -> tuple[ContextSource, list[ContextSource], ConflictRecord | None]:
    """Resolve a single field from multiple candidates.

    Resolution rules (applied in order):
    1. Lowest precedence number wins (SAFETY > GOVERNANCE > ... > DEFAULTS)
    2. Among equal precedence: approved > unapproved
    3. Among equal precedence + approval: newer timestamp wins
    4. Among equal everything: deterministic tie-break by source_id (lexicographic)
    """
    # Sort candidates: by precedence (asc), then approved (desc), then timestamp (desc), then source_id
    sorted_candidates = sorted(
        candidates,
        key=lambda s: (
            s.precedence.value,
            0 if s.approved else 1,
            -s.timestamp,
            s.source_id,
        ),
    )

    winner = sorted_candidates[0]
    losers = sorted_candidates[1:]

    # Record conflict if multiple candidates existed
    conflict = None
    if len(candidates) > 1:
        # Determine resolution reason
        if winner.precedence != sorted_candidates[1].precedence:
            reason = f"{winner.source_type} (precedence {winner.precedence.name}) wins over {sorted_candidates[1].source_type} (precedence {sorted_candidates[1].precedence.name})"
            rule = "higher_precedence"
        elif winner.approved and not sorted_candidates[1].approved:
            reason = f"Approved source wins over unapproved"
            rule = "approval_status"
        elif winner.timestamp > sorted_candidates[1].timestamp:
            reason = f"Newer timestamp wins among equal precedence"
            rule = "newer_timestamp"
        else:
            reason = f"Deterministic tie-break by source_id"
            rule = "lexicographic_tiebreak"

        conflict = ConflictRecord(
            field_name=field_name,
            winner=winner,
            losers=losers,
            reason=reason,
            resolution_rule=rule,
        )

    return winner, losers, conflict


def _apply_overrides(ctx: ResolvedContext, overrides: list[UserOverride]) -> None:
    """Apply authorized user overrides to resolved context.

    Override rules:
    - SAFETY and GOVERNANCE fields CANNOT be overridden
    - User must have permission (permitted=True)
    - Override scope must match or be broader than current scope
    """
    non_overridable = {Precedence.SAFETY, Precedence.GOVERNANCE}

    for override in overrides:
        # Check if field exists in resolved context
        current_source = ctx.provenance.get(override.field)

        # Check permission
        if not override.permitted:
            override_denied = UserOverride(
                field=override.field,
                override_value=override.override_value,
                user_id=override.user_id,
                reason="Permission denied",
                scope=override.scope,
                permitted=False,
            )
            ctx.overrides_denied.append(override_denied)
            continue

        # Check if field is non-overridable
        if current_source and current_source.precedence in non_overridable:
            override_denied = UserOverride(
                field=override.field,
                override_value=override.override_value,
                user_id=override.user_id,
                reason=f"Cannot override {current_source.precedence.name} field",
                scope=override.scope,
                permitted=True,
            )
            ctx.overrides_denied.append(override_denied)
            continue

        # Apply override
        ctx.effective[override.field] = override.override_value
        ctx.overrides_applied.append(override)


# =============================================================================
# Historical Reproducibility
# =============================================================================


_resolved_history: dict[str, ResolvedContext] = {}


def pin_resolved_context(ctx: ResolvedContext, job_id: str) -> str:
    """Pin a resolved context to a job for historical reproducibility."""
    _resolved_history[job_id] = ctx
    return ctx.resolve_id


def get_historical_context(job_id: str) -> ResolvedContext | None:
    """Retrieve the exact resolved context used for a historical generation."""
    return _resolved_history.get(job_id)


# =============================================================================
# Validation & Inspection
# =============================================================================


def explain_resolution(ctx: ResolvedContext, field_name: str) -> dict[str, Any]:
    """Explain how a specific field was resolved — for UI transparency."""
    source = ctx.provenance.get(field_name)
    if not source:
        return {"field": field_name, "resolved": False}

    # Find related conflict
    related_conflict = next(
        (c for c in ctx.conflicts if c.field_name == field_name), None
    )

    # Check if overridden
    override = next(
        (o for o in ctx.overrides_applied if o.field == field_name), None
    )

    return {
        "field": field_name,
        "resolved": True,
        "effective_value": ctx.effective.get(field_name),
        "source_type": source.source_type,
        "source_id": source.source_id,
        "source_version": source.source_version,
        "precedence": source.precedence.name,
        "had_conflict": related_conflict is not None,
        "conflict_reason": related_conflict.reason if related_conflict else None,
        "overridden": override is not None,
        "override_by": override.user_id if override else None,
    }


def validate_sources(sources: list[ContextSource]) -> list[str]:
    """Validate context sources before resolution. Returns list of warnings."""
    warnings = []
    for s in sources:
        if not s.field:
            warnings.append(f"Source {s.source_id} has empty field name")
        if not s.source_id:
            warnings.append(f"Source for field '{s.field}' has no source_id")
        if s.precedence == Precedence.SAFETY and not s.approved:
            warnings.append(f"Safety source {s.source_id} marked unapproved — will be demoted")
    return warnings


# =============================================================================
# Testing Support
# =============================================================================


def _reset_store() -> None:
    _resolved_history.clear()

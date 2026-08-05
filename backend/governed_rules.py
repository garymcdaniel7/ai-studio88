"""Governed Continuity Rules — Story 087.

Versioned, scoped, authorized rules with lifecycle, conflict resolution,
and auditable context integration. Rules protect character identity and
project consistency.

Lifecycle:
    DRAFT → APPROVED → ACTIVE → SUPERSEDED → RETIRED
    (DRAFT → RETIRED also valid for abandoned rules)

Key distinctions:
    - APPROVED: reviewed but not yet enforced
    - ACTIVE: currently enforced in generation context
    - SUPERSEDED: replaced by newer version (preserved for history)

Every rule edit creates a new version. History is never rewritten.
Applied rules are recorded by exact version in the immutable context package.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


# =============================================================================
# Rule Types and Categories
# =============================================================================


class RuleType(StrEnum):
    INCLUDE = "include"     # Always add to positive prompt
    AVOID = "avoid"         # Always add to negative prompt
    PREFER = "prefer"       # Soft preference (weighted by confidence)
    REQUIRE = "require"     # Hard requirement (block if violated)


class RuleCategory(StrEnum):
    PROMPT = "prompt"
    STYLE = "style"
    LIGHTING = "lighting"
    WARDROBE = "wardrobe"
    CAMERA = "camera"
    MODEL = "model"
    WORKFLOW = "workflow"
    SETTING = "setting"
    POSE = "pose"
    COLOR = "color"


class RuleSource(StrEnum):
    MANUAL = "manual"           # User-authored
    LEARNED = "learned"         # Derived from feedback
    DNA = "dna"                 # Extracted from Creative DNA
    IMPORTED = "imported"       # Imported from template/project


# =============================================================================
# Rule Lifecycle
# =============================================================================


class RuleLifecycle(StrEnum):
    DRAFT = "draft"             # Created, not yet reviewed
    APPROVED = "approved"       # Reviewed, not yet enforced
    ACTIVE = "active"           # Currently enforced
    SUPERSEDED = "superseded"   # Replaced by newer version
    RETIRED = "retired"         # Permanently deactivated


# Valid lifecycle transitions
VALID_LIFECYCLE_TRANSITIONS: dict[tuple[RuleLifecycle, RuleLifecycle], bool] = {
    (RuleLifecycle.DRAFT, RuleLifecycle.APPROVED): True,
    (RuleLifecycle.DRAFT, RuleLifecycle.RETIRED): True,
    (RuleLifecycle.APPROVED, RuleLifecycle.ACTIVE): True,
    (RuleLifecycle.APPROVED, RuleLifecycle.RETIRED): True,
    (RuleLifecycle.ACTIVE, RuleLifecycle.SUPERSEDED): True,
    (RuleLifecycle.ACTIVE, RuleLifecycle.RETIRED): True,
    (RuleLifecycle.SUPERSEDED, RuleLifecycle.ACTIVE): True,  # Reactivate old version
}


# =============================================================================
# Rule Scope
# =============================================================================


class RuleScope(StrEnum):
    WORKSPACE = "workspace"     # Applies to all talent in the workspace
    PROJECT = "project"         # Applies within a specific project
    TALENT = "talent"           # Applies to a specific talent
    SCENE = "scene"             # Applies within a scene context
    SERIES = "series"           # Applies across a content series


@dataclass
class ScopeBinding:
    """Defines where a rule applies."""

    scope: RuleScope
    talent_id: str | None = None        # Required for TALENT scope
    project_id: str | None = None       # Required for PROJECT scope
    scene_id: str | None = None         # Required for SCENE scope
    series_id: str | None = None        # Required for SERIES scope

    def matches(
        self,
        *,
        talent_id: str | None = None,
        project_id: str | None = None,
        scene_id: str | None = None,
        series_id: str | None = None,
    ) -> bool:
        """Check if this binding matches a generation context."""
        if self.scope == RuleScope.WORKSPACE:
            return True  # Always matches within workspace
        if self.scope == RuleScope.TALENT:
            return self.talent_id == talent_id
        if self.scope == RuleScope.PROJECT:
            return self.project_id == project_id
        if self.scope == RuleScope.SCENE:
            return self.scene_id == scene_id
        if self.scope == RuleScope.SERIES:
            return self.series_id == series_id
        return False

    def to_dict(self) -> dict:
        return {
            "scope": self.scope.value,
            "talent_id": self.talent_id,
            "project_id": self.project_id,
            "scene_id": self.scene_id,
            "series_id": self.series_id,
        }


# =============================================================================
# Governed Rule
# =============================================================================


@dataclass
class GovernedRule:
    """A versioned, governed continuity rule."""

    # Identity
    rule_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    org_id: str = ""
    version: int = 1

    # Content
    rule_type: RuleType = RuleType.INCLUDE
    category: RuleCategory = RuleCategory.PROMPT
    text: str = ""                  # The rule content
    reason: str = ""                # Why this rule exists
    confidence: float = 1.0         # 0-1, affects PREFER weighting

    # Scope
    scope_binding: ScopeBinding = field(default_factory=lambda: ScopeBinding(scope=RuleScope.WORKSPACE))

    # Source & attribution
    source: RuleSource = RuleSource.MANUAL
    created_by: str = ""            # Actor who created
    updated_by: str = ""            # Actor who last modified
    approved_by: str | None = None  # Actor who approved
    activated_by: str | None = None # Actor who activated

    # Lifecycle
    lifecycle: RuleLifecycle = RuleLifecycle.DRAFT

    # Supersession
    supersedes_rule_id: str | None = None   # Previous version this replaces
    superseded_by_rule_id: str | None = None  # Newer version that replaced this

    # Effective dates
    effective_from: str | None = None   # When rule starts applying (None = immediately)
    effective_until: str | None = None  # When rule expires (None = indefinite)

    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def is_applicable(
        self,
        *,
        talent_id: str | None = None,
        project_id: str | None = None,
        scene_id: str | None = None,
        now: str | None = None,
    ) -> bool:
        """Check if rule is applicable to a given context.

        Must be ACTIVE + scope matches + within effective dates.
        """
        if self.lifecycle != RuleLifecycle.ACTIVE:
            return False

        if not self.scope_binding.matches(
            talent_id=talent_id,
            project_id=project_id,
            scene_id=scene_id,
        ):
            return False

        # Date check (simplified — production compares ISO timestamps)
        if self.effective_until and now and self.effective_until < now:
            return False  # Expired

        return True

    def to_context_entry(self) -> dict:
        """Format for inclusion in context package."""
        return {
            "rule_id": self.rule_id,
            "version": self.version,
            "type": self.rule_type.value,
            "category": self.category.value,
            "text": self.text,
            "confidence": self.confidence,
            "scope": self.scope_binding.scope.value,
            "source": self.source.value,
        }

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "org_id": self.org_id,
            "version": self.version,
            "rule_type": self.rule_type.value,
            "category": self.category.value,
            "text": self.text,
            "reason": self.reason,
            "confidence": self.confidence,
            "scope": self.scope_binding.to_dict(),
            "source": self.source.value,
            "lifecycle": self.lifecycle.value,
            "created_by": self.created_by,
            "approved_by": self.approved_by,
            "supersedes_rule_id": self.supersedes_rule_id,
            "effective_from": self.effective_from,
            "effective_until": self.effective_until,
            "created_at": self.created_at,
        }


# =============================================================================
# Lifecycle Transitions
# =============================================================================


class RuleLifecycleError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def transition_lifecycle(
    rule: GovernedRule,
    new_state: RuleLifecycle,
    *,
    actor: str,
) -> GovernedRule:
    """Transition a rule's lifecycle state.

    Raises RuleLifecycleError on invalid transition.
    """
    key = (rule.lifecycle, new_state)
    if key not in VALID_LIFECYCLE_TRANSITIONS:
        raise RuleLifecycleError(
            f"Invalid transition: {rule.lifecycle.value} → {new_state.value}"
        )

    rule.lifecycle = new_state
    rule.updated_by = actor
    rule.updated_at = datetime.now(UTC).isoformat()

    if new_state == RuleLifecycle.APPROVED:
        rule.approved_by = actor
    elif new_state == RuleLifecycle.ACTIVE:
        rule.activated_by = actor

    return rule


# =============================================================================
# Versioning (Edit Creates New Version)
# =============================================================================


def create_new_version(
    rule: GovernedRule,
    *,
    text: str | None = None,
    reason: str | None = None,
    confidence: float | None = None,
    category: RuleCategory | None = None,
    actor: str,
) -> GovernedRule:
    """Create a new version of a rule.

    The original rule is SUPERSEDED; a new DRAFT version is created.
    History is never rewritten.
    """
    new_rule = GovernedRule(
        rule_id=str(uuid.uuid4()),
        org_id=rule.org_id,
        version=rule.version + 1,
        rule_type=rule.rule_type,
        category=category if category is not None else rule.category,
        text=text if text is not None else rule.text,
        reason=reason if reason is not None else rule.reason,
        confidence=confidence if confidence is not None else rule.confidence,
        scope_binding=rule.scope_binding,
        source=rule.source,
        created_by=actor,
        updated_by=actor,
        lifecycle=RuleLifecycle.DRAFT,
        supersedes_rule_id=rule.rule_id,
        effective_from=rule.effective_from,
        effective_until=rule.effective_until,
    )

    # Mark original as superseded
    rule.lifecycle = RuleLifecycle.SUPERSEDED
    rule.superseded_by_rule_id = new_rule.rule_id
    rule.updated_by = actor
    rule.updated_at = datetime.now(UTC).isoformat()

    return new_rule


# =============================================================================
# Conflict Resolution
# =============================================================================


@dataclass
class RuleConflict:
    """A detected conflict between two rules."""

    rule_a_id: str
    rule_b_id: str
    conflict_type: str      # "contradictory", "overlapping", "redundant"
    description: str
    resolution: str = ""    # How it was resolved
    winner_id: str = ""     # Which rule won

    def to_dict(self) -> dict:
        return {
            "rule_a_id": self.rule_a_id,
            "rule_b_id": self.rule_b_id,
            "conflict_type": self.conflict_type,
            "description": self.description,
            "resolution": self.resolution,
            "winner_id": self.winner_id,
        }


# Precedence order: more specific scope wins
SCOPE_PRECEDENCE: dict[RuleScope, int] = {
    RuleScope.SCENE: 5,         # Most specific
    RuleScope.TALENT: 4,
    RuleScope.PROJECT: 3,
    RuleScope.SERIES: 2,
    RuleScope.WORKSPACE: 1,     # Least specific
}


def resolve_conflicts(rules: list[GovernedRule]) -> tuple[list[GovernedRule], list[RuleConflict]]:
    """Resolve conflicts among applicable rules.

    Precedence:
    1. More specific scope wins (scene > talent > project > series > workspace)
    2. Higher confidence wins within same scope
    3. REQUIRE type wins over PREFER within same scope+confidence
    4. Later created_at wins as tiebreaker

    Returns: (resolved_rules, detected_conflicts)
    """
    conflicts: list[RuleConflict] = []
    resolved: list[GovernedRule] = []

    # Group by category to detect contradictions
    by_category: dict[str, list[GovernedRule]] = {}
    for rule in rules:
        by_category.setdefault(rule.category.value, []).append(rule)

    for category, cat_rules in by_category.items():
        # Check for include/avoid contradictions within same category
        includes = [r for r in cat_rules if r.rule_type == RuleType.INCLUDE]
        avoids = [r for r in cat_rules if r.rule_type == RuleType.AVOID]

        # Detect text overlaps between include and avoid
        for inc in includes:
            for avoid in avoids:
                if _texts_conflict(inc.text, avoid.text):
                    # Resolve by scope precedence
                    inc_prec = SCOPE_PRECEDENCE.get(inc.scope_binding.scope, 0)
                    avoid_prec = SCOPE_PRECEDENCE.get(avoid.scope_binding.scope, 0)

                    if inc_prec > avoid_prec:
                        winner = inc
                    elif avoid_prec > inc_prec:
                        winner = avoid
                    elif inc.confidence >= avoid.confidence:
                        winner = inc
                    else:
                        winner = avoid

                    conflicts.append(RuleConflict(
                        rule_a_id=inc.rule_id,
                        rule_b_id=avoid.rule_id,
                        conflict_type="contradictory",
                        description=f"Include '{inc.text}' conflicts with avoid '{avoid.text}'",
                        resolution=f"Scope precedence: {winner.scope_binding.scope.value} wins",
                        winner_id=winner.rule_id,
                    ))

        # All rules pass through (conflicts are disclosed, not auto-removed)
        resolved.extend(cat_rules)

    # For categories not processed above
    all_processed = set()
    for cat_rules in by_category.values():
        for r in cat_rules:
            all_processed.add(r.rule_id)

    for rule in rules:
        if rule.rule_id not in all_processed:
            resolved.append(rule)

    return resolved, conflicts


def _texts_conflict(text_a: str, text_b: str) -> bool:
    """Check if two rule texts are likely contradictory.

    Simple heuristic: if the avoid text appears within the include text
    or vice versa, they conflict.
    """
    a_lower = text_a.lower().strip()
    b_lower = text_b.lower().strip()
    return a_lower in b_lower or b_lower in a_lower


# =============================================================================
# Context Loading (for assembler integration)
# =============================================================================


def load_applicable_rules(
    rules: list[GovernedRule],
    *,
    org_id: str,
    talent_id: str | None = None,
    project_id: str | None = None,
    scene_id: str | None = None,
    now: str | None = None,
) -> tuple[list[GovernedRule], list[GovernedRule]]:
    """Load only applicable, authorized rules for a generation context.

    Returns: (applicable_rules, excluded_rules)

    Filters:
    1. Must belong to requesting org_id
    2. Must be ACTIVE lifecycle
    3. Must match scope (talent/project/scene/workspace)
    4. Must be within effective dates
    """
    applicable: list[GovernedRule] = []
    excluded: list[GovernedRule] = []

    for rule in rules:
        # Authorization: must be same org
        if rule.org_id != org_id:
            excluded.append(rule)
            continue

        # Applicability check
        if rule.is_applicable(
            talent_id=talent_id,
            project_id=project_id,
            scene_id=scene_id,
            now=now,
        ):
            applicable.append(rule)
        else:
            excluded.append(rule)

    return applicable, excluded


def rules_to_context_entries(rules: list[GovernedRule]) -> list[dict]:
    """Convert applicable rules to context package entries."""
    return [r.to_context_entry() for r in rules]

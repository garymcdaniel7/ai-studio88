"""Governed Continuity Rules Tests (Story 087).

Proves: versioning, scope filtering, conflict resolution, authorization,
lifecycle transitions, supersession, and context package inclusion.

Run with:
    pytest tests/unit/test_governed_rules.py -v
"""
from __future__ import annotations

import pytest

from backend.governed_rules import (
    SCOPE_PRECEDENCE,
    VALID_LIFECYCLE_TRANSITIONS,
    GovernedRule,
    RuleCategory,
    RuleConflict,
    RuleLifecycle,
    RuleLifecycleError,
    RuleScope,
    RuleSource,
    RuleType,
    ScopeBinding,
    create_new_version,
    load_applicable_rules,
    resolve_conflicts,
    rules_to_context_entries,
    transition_lifecycle,
)


# =============================================================================
# Helpers
# =============================================================================


def _make_rule(
    lifecycle: RuleLifecycle = RuleLifecycle.ACTIVE,
    scope: RuleScope = RuleScope.TALENT,
    talent_id: str | None = "talent-1",
    org_id: str = "org-123",
    **overrides,
) -> GovernedRule:
    defaults = {
        "org_id": org_id,
        "rule_type": RuleType.INCLUDE,
        "category": RuleCategory.WARDROBE,
        "text": "wearing red dress",
        "reason": "Character signature look",
        "confidence": 1.0,
        "source": RuleSource.MANUAL,
        "created_by": "user-1",
        "updated_by": "user-1",
        "lifecycle": lifecycle,
        "scope_binding": ScopeBinding(scope=scope, talent_id=talent_id),
    }
    defaults.update(overrides)
    return GovernedRule(**defaults)


# =============================================================================
# Lifecycle Transitions
# =============================================================================


class TestLifecycleTransitions:

    @pytest.mark.unit
    def test_draft_to_approved(self):
        """DRAFT → APPROVED is valid."""
        rule = _make_rule(lifecycle=RuleLifecycle.DRAFT)
        transition_lifecycle(rule, RuleLifecycle.APPROVED, actor="reviewer-1")
        assert rule.lifecycle == RuleLifecycle.APPROVED
        assert rule.approved_by == "reviewer-1"

    @pytest.mark.unit
    def test_approved_to_active(self):
        """APPROVED → ACTIVE is valid."""
        rule = _make_rule(lifecycle=RuleLifecycle.APPROVED)
        transition_lifecycle(rule, RuleLifecycle.ACTIVE, actor="admin-1")
        assert rule.lifecycle == RuleLifecycle.ACTIVE
        assert rule.activated_by == "admin-1"

    @pytest.mark.unit
    def test_active_to_superseded(self):
        """ACTIVE → SUPERSEDED is valid."""
        rule = _make_rule(lifecycle=RuleLifecycle.ACTIVE)
        transition_lifecycle(rule, RuleLifecycle.SUPERSEDED, actor="user-1")
        assert rule.lifecycle == RuleLifecycle.SUPERSEDED

    @pytest.mark.unit
    def test_active_to_retired(self):
        """ACTIVE → RETIRED is valid."""
        rule = _make_rule(lifecycle=RuleLifecycle.ACTIVE)
        transition_lifecycle(rule, RuleLifecycle.RETIRED, actor="admin-1")
        assert rule.lifecycle == RuleLifecycle.RETIRED

    @pytest.mark.unit
    def test_superseded_to_active_reactivate(self):
        """SUPERSEDED → ACTIVE (reactivate old version) is valid."""
        rule = _make_rule(lifecycle=RuleLifecycle.SUPERSEDED)
        transition_lifecycle(rule, RuleLifecycle.ACTIVE, actor="admin-1")
        assert rule.lifecycle == RuleLifecycle.ACTIVE

    @pytest.mark.unit
    def test_draft_to_active_invalid(self):
        """DRAFT → ACTIVE (skip approval) is invalid."""
        rule = _make_rule(lifecycle=RuleLifecycle.DRAFT)
        with pytest.raises(RuleLifecycleError) as exc_info:
            transition_lifecycle(rule, RuleLifecycle.ACTIVE, actor="user-1")
        assert "invalid" in exc_info.value.message.lower()

    @pytest.mark.unit
    def test_retired_to_active_invalid(self):
        """RETIRED → ACTIVE is invalid (cannot un-retire)."""
        rule = _make_rule(lifecycle=RuleLifecycle.RETIRED)
        with pytest.raises(RuleLifecycleError):
            transition_lifecycle(rule, RuleLifecycle.ACTIVE, actor="admin-1")


# =============================================================================
# Versioning
# =============================================================================


class TestVersioning:

    @pytest.mark.unit
    def test_new_version_increments(self):
        """New version has incremented version number."""
        original = _make_rule(lifecycle=RuleLifecycle.ACTIVE)
        original.version = 2
        new = create_new_version(original, text="wearing blue dress", actor="editor-1")
        assert new.version == 3
        assert new.text == "wearing blue dress"

    @pytest.mark.unit
    def test_new_version_is_draft(self):
        """New version starts as DRAFT."""
        original = _make_rule(lifecycle=RuleLifecycle.ACTIVE)
        new = create_new_version(original, actor="user-1")
        assert new.lifecycle == RuleLifecycle.DRAFT

    @pytest.mark.unit
    def test_original_superseded(self):
        """Original is marked SUPERSEDED after creating new version."""
        original = _make_rule(lifecycle=RuleLifecycle.ACTIVE)
        new = create_new_version(original, actor="user-1")
        assert original.lifecycle == RuleLifecycle.SUPERSEDED
        assert original.superseded_by_rule_id == new.rule_id

    @pytest.mark.unit
    def test_new_references_original(self):
        """New version references which rule it supersedes."""
        original = _make_rule(lifecycle=RuleLifecycle.ACTIVE)
        new = create_new_version(original, actor="user-1")
        assert new.supersedes_rule_id == original.rule_id

    @pytest.mark.unit
    def test_version_preserves_unchanged_fields(self):
        """New version inherits fields not explicitly changed."""
        original = _make_rule(
            lifecycle=RuleLifecycle.ACTIVE,
            text="original text", reason="original reason",
            confidence=0.9, category=RuleCategory.STYLE,
        )
        new = create_new_version(original, text="updated text", actor="u-1")
        assert new.text == "updated text"
        assert new.reason == "original reason"  # Preserved
        assert new.confidence == 0.9            # Preserved
        assert new.category == RuleCategory.STYLE  # Preserved

    @pytest.mark.unit
    def test_version_gets_new_id(self):
        """New version has a different rule_id."""
        original = _make_rule(lifecycle=RuleLifecycle.ACTIVE)
        new = create_new_version(original, actor="u-1")
        assert new.rule_id != original.rule_id


# =============================================================================
# Scope Filtering
# =============================================================================


class TestScopeFiltering:

    @pytest.mark.unit
    def test_workspace_scope_matches_everything(self):
        """WORKSPACE scope matches any talent/project."""
        rule = _make_rule(scope=RuleScope.WORKSPACE)
        assert rule.is_applicable(talent_id="any", project_id="any")

    @pytest.mark.unit
    def test_talent_scope_matches_correct_talent(self):
        """TALENT scope matches only the specified talent."""
        rule = _make_rule(scope=RuleScope.TALENT, talent_id="talent-1")
        assert rule.is_applicable(talent_id="talent-1")
        assert not rule.is_applicable(talent_id="talent-other")

    @pytest.mark.unit
    def test_project_scope_matches_correct_project(self):
        """PROJECT scope matches only the specified project."""
        binding = ScopeBinding(scope=RuleScope.PROJECT, project_id="proj-1")
        rule = _make_rule(scope=RuleScope.PROJECT)
        rule.scope_binding = binding
        assert rule.is_applicable(project_id="proj-1")
        assert not rule.is_applicable(project_id="proj-other")

    @pytest.mark.unit
    def test_inactive_rule_never_applicable(self):
        """Non-ACTIVE rules are never applicable."""
        rule = _make_rule(lifecycle=RuleLifecycle.DRAFT)
        assert not rule.is_applicable(talent_id="talent-1")

    @pytest.mark.unit
    def test_expired_rule_not_applicable(self):
        """Rule past effective_until is not applicable."""
        rule = _make_rule(lifecycle=RuleLifecycle.ACTIVE)
        rule.effective_until = "2020-01-01T00:00:00Z"
        assert not rule.is_applicable(talent_id="talent-1", now="2025-06-01T00:00:00Z")

    @pytest.mark.unit
    def test_non_expired_rule_applicable(self):
        """Rule before effective_until is applicable."""
        rule = _make_rule(lifecycle=RuleLifecycle.ACTIVE)
        rule.effective_until = "2030-01-01T00:00:00Z"
        assert rule.is_applicable(talent_id="talent-1", now="2025-06-01T00:00:00Z")


# =============================================================================
# Authorization (load_applicable_rules)
# =============================================================================


class TestAuthorization:

    @pytest.mark.unit
    def test_same_org_rules_loaded(self):
        """Rules from requesting org are loaded."""
        rules = [_make_rule(org_id="org-123")]
        applicable, excluded = load_applicable_rules(
            rules, org_id="org-123", talent_id="talent-1",
        )
        assert len(applicable) == 1

    @pytest.mark.unit
    def test_different_org_excluded(self):
        """Rules from other orgs are excluded."""
        rules = [_make_rule(org_id="org-other")]
        applicable, excluded = load_applicable_rules(
            rules, org_id="org-123", talent_id="talent-1",
        )
        assert len(applicable) == 0
        assert len(excluded) == 1

    @pytest.mark.unit
    def test_mixed_orgs_filtered(self):
        """Only requesting org's rules are loaded."""
        rules = [
            _make_rule(org_id="org-123", text="my rule"),
            _make_rule(org_id="org-evil", text="their rule"),
        ]
        applicable, _ = load_applicable_rules(
            rules, org_id="org-123", talent_id="talent-1",
        )
        assert len(applicable) == 1
        assert applicable[0].text == "my rule"

    @pytest.mark.unit
    def test_only_active_rules_applicable(self):
        """Only ACTIVE lifecycle rules pass."""
        rules = [
            _make_rule(lifecycle=RuleLifecycle.ACTIVE, text="active"),
            _make_rule(lifecycle=RuleLifecycle.DRAFT, text="draft"),
            _make_rule(lifecycle=RuleLifecycle.RETIRED, text="retired"),
        ]
        applicable, excluded = load_applicable_rules(
            rules, org_id="org-123", talent_id="talent-1",
        )
        assert len(applicable) == 1
        assert applicable[0].text == "active"


# =============================================================================
# Conflict Resolution
# =============================================================================


class TestConflictResolution:

    @pytest.mark.unit
    def test_no_conflicts_clean(self):
        """Non-conflicting rules produce no conflicts."""
        rules = [
            _make_rule(text="wearing red dress", rule_type=RuleType.INCLUDE),
            _make_rule(text="outdoor setting", rule_type=RuleType.INCLUDE, category=RuleCategory.SETTING),
        ]
        resolved, conflicts = resolve_conflicts(rules)
        assert len(conflicts) == 0
        assert len(resolved) == 2

    @pytest.mark.unit
    def test_contradictory_include_avoid_detected(self):
        """Include and avoid with overlapping text are detected."""
        rules = [
            _make_rule(text="red dress", rule_type=RuleType.INCLUDE, category=RuleCategory.WARDROBE),
            _make_rule(text="red dress", rule_type=RuleType.AVOID, category=RuleCategory.WARDROBE),
        ]
        _, conflicts = resolve_conflicts(rules)
        assert len(conflicts) == 1
        assert conflicts[0].conflict_type == "contradictory"

    @pytest.mark.unit
    def test_more_specific_scope_wins(self):
        """Talent-scoped rule wins over workspace-scoped."""
        workspace_rule = _make_rule(
            text="casual clothes", rule_type=RuleType.INCLUDE,
            scope=RuleScope.WORKSPACE, talent_id=None,
            category=RuleCategory.WARDROBE,
        )
        talent_rule = _make_rule(
            text="casual clothes", rule_type=RuleType.AVOID,
            scope=RuleScope.TALENT, talent_id="talent-1",
            category=RuleCategory.WARDROBE,
        )
        _, conflicts = resolve_conflicts([workspace_rule, talent_rule])
        assert len(conflicts) == 1
        assert conflicts[0].winner_id == talent_rule.rule_id

    @pytest.mark.unit
    def test_same_scope_higher_confidence_wins(self):
        """Within same scope, higher confidence wins."""
        rule_a = _make_rule(
            text="formal wear", rule_type=RuleType.INCLUDE,
            confidence=0.9, category=RuleCategory.WARDROBE,
        )
        rule_b = _make_rule(
            text="formal wear", rule_type=RuleType.AVOID,
            confidence=0.5, category=RuleCategory.WARDROBE,
        )
        _, conflicts = resolve_conflicts([rule_a, rule_b])
        assert len(conflicts) == 1
        assert conflicts[0].winner_id == rule_a.rule_id

    @pytest.mark.unit
    def test_different_categories_no_conflict(self):
        """Rules in different categories don't conflict."""
        rules = [
            _make_rule(text="bright", rule_type=RuleType.INCLUDE, category=RuleCategory.LIGHTING),
            _make_rule(text="bright", rule_type=RuleType.AVOID, category=RuleCategory.COLOR),
        ]
        _, conflicts = resolve_conflicts(rules)
        assert len(conflicts) == 0


# =============================================================================
# Context Package Inclusion
# =============================================================================


class TestContextInclusion:

    @pytest.mark.unit
    def test_context_entry_format(self):
        """to_context_entry includes rule_id, version, type, text."""
        rule = _make_rule(text="always wear hat")
        rule.version = 3
        entry = rule.to_context_entry()
        assert entry["rule_id"] == rule.rule_id
        assert entry["version"] == 3
        assert entry["type"] == "include"
        assert entry["text"] == "always wear hat"
        assert entry["category"] == "wardrobe"

    @pytest.mark.unit
    def test_rules_to_context_entries_list(self):
        """rules_to_context_entries produces list of entries."""
        rules = [
            _make_rule(text="rule A"),
            _make_rule(text="rule B"),
        ]
        entries = rules_to_context_entries(rules)
        assert len(entries) == 2
        assert entries[0]["text"] == "rule A"
        assert entries[1]["text"] == "rule B"

    @pytest.mark.unit
    def test_context_entry_serializable(self):
        """Context entries are JSON-serializable."""
        import json
        rule = _make_rule()
        json.dumps(rule.to_context_entry())

    @pytest.mark.unit
    def test_full_rule_serializable(self):
        """to_dict() is JSON-serializable."""
        import json
        rule = _make_rule()
        json.dumps(rule.to_dict())


# =============================================================================
# Scope Precedence
# =============================================================================


class TestScopePrecedence:

    @pytest.mark.unit
    def test_scene_highest_precedence(self):
        """SCENE has highest precedence."""
        assert SCOPE_PRECEDENCE[RuleScope.SCENE] > SCOPE_PRECEDENCE[RuleScope.TALENT]

    @pytest.mark.unit
    def test_workspace_lowest_precedence(self):
        """WORKSPACE has lowest precedence."""
        assert SCOPE_PRECEDENCE[RuleScope.WORKSPACE] < SCOPE_PRECEDENCE[RuleScope.PROJECT]

    @pytest.mark.unit
    def test_all_scopes_have_precedence(self):
        """Every scope has a defined precedence value."""
        for scope in RuleScope:
            assert scope in SCOPE_PRECEDENCE

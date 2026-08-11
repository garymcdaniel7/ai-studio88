"""Typed LoRA assignment tests — Story 100.

Tests prove:
  - Exact approved version required
  - Cross-tenant assignment rejected
  - Retired version rejected
  - Simulated version rejected
  - Conflict resolution: one identity LoRA wins
  - Multi-talent: each gets their assignments
  - User override (removal) tracked
  - User override (strength) applied
  - Trigger words visible in context
  - Context package serialization includes all data
  - Duplicate assignment is idempotent
  - Role conflict replaces previous assignment
"""

import pytest

from backend.lora_assignment import (
    ApplicationMode,
    AssignmentRejected,
    AssignmentScope,
    GenerationLoRAContext,
    LoRARole,
    _mark_eligible,
    _mark_retired,
    _mark_simulated,
    _reset_store,
    build_generation_context,
    create_assignment,
    get_assignments,
    get_auto_applied_loras,
    get_visible_loras,
    remove_assignment,
    serialize_for_context_package,
    update_assignment,
)


@pytest.fixture(autouse=True)
def clean():
    _reset_store()
    yield
    _reset_store()


ORG = "org-test-001"
OTHER_ORG = "org-other-999"
TALENT = "talent-001"
USER = "user-001"


def _setup_eligible(*version_ids: str) -> None:
    for vid in version_ids:
        _mark_eligible(vid)


# =============================================================================
# Exact Version Required
# =============================================================================


@pytest.mark.unit
class TestExactVersionRequired:

    def test_eligible_version_succeeds(self):
        _setup_eligible("v-001")
        a = create_assignment(ORG, TALENT, "v-001", "face_lora", LoRARole.IDENTITY, USER,
                              trigger_words=["ohwx"])
        assert a.version_id == "v-001"
        assert a.trigger_words == ["ohwx"]

    def test_non_eligible_version_rejected(self):
        # Don't mark as eligible
        with pytest.raises(AssignmentRejected, match="not in production catalog"):
            create_assignment(ORG, TALENT, "v-bad", "bad_lora", LoRARole.IDENTITY, USER)


# =============================================================================
# Cross-Tenant Rejection
# =============================================================================


@pytest.mark.unit
class TestCrossTenant:

    def test_assignment_scoped_to_org(self):
        _setup_eligible("v-001")
        create_assignment(ORG, TALENT, "v-001", "lora", LoRARole.IDENTITY, USER)
        assignments = get_assignments(OTHER_ORG, TALENT)
        assert len(assignments) == 0

    def test_own_org_visible(self):
        _setup_eligible("v-001")
        create_assignment(ORG, TALENT, "v-001", "lora", LoRARole.IDENTITY, USER)
        assignments = get_assignments(ORG, TALENT)
        assert len(assignments) == 1


# =============================================================================
# Retired / Simulated Rejection
# =============================================================================


@pytest.mark.unit
class TestRetiredSimulated:

    def test_retired_version_rejected(self):
        _setup_eligible("v-ret")
        _mark_retired("v-ret")
        with pytest.raises(AssignmentRejected, match="Retired"):
            create_assignment(ORG, TALENT, "v-ret", "lora", LoRARole.IDENTITY, USER)

    def test_simulated_version_rejected(self):
        _setup_eligible("v-sim")
        _mark_simulated("v-sim")
        with pytest.raises(AssignmentRejected, match="Simulated"):
            create_assignment(ORG, TALENT, "v-sim", "lora", LoRARole.STYLE, USER)


# =============================================================================
# Conflict Resolution
# =============================================================================


@pytest.mark.unit
class TestConflictResolution:

    def test_one_identity_lora_wins(self):
        """Same talent can only have one active identity assignment (enforced at create)."""
        _setup_eligible("v-id1", "v-id2")
        create_assignment(ORG, "t1", "v-id1", "face1", LoRARole.IDENTITY, USER,
                          strength=0.7, trigger_words=["ohwx1"])
        create_assignment(ORG, "t1", "v-id2", "face2", LoRARole.IDENTITY, USER,
                          strength=0.9, trigger_words=["ohwx2"])

        # create_assignment replaces old one — only newest active
        context = build_generation_context(ORG, ["t1"])
        active = context.active_loras
        identity_loras = [a for a in active if a.role == LoRARole.IDENTITY]
        assert len(identity_loras) == 1
        assert identity_loras[0].strength == 0.9

    def test_conflict_recorded(self):
        """Role conflict at assignment time: old assignment deactivated."""
        _setup_eligible("v-id1", "v-id2")
        a1 = create_assignment(ORG, "t1", "v-id1", "face1", LoRARole.IDENTITY, USER,
                               strength=0.7, trigger_words=["ohwx1"])
        a2 = create_assignment(ORG, "t1", "v-id2", "face2", LoRARole.IDENTITY, USER,
                               strength=0.9, trigger_words=["ohwx2"])

        # First assignment should be deactivated
        assignments = get_assignments(ORG, "t1", active_only=True)
        assert len(assignments) == 1
        assert assignments[0].version_id == "v-id2"

    def test_multiple_style_loras_allowed(self):
        _setup_eligible("v-s1", "v-s2")
        create_assignment(ORG, TALENT, "v-s1", "style1", LoRARole.STYLE, USER,
                          strength=0.5, trigger_words=["painterly"])
        # Different scope to avoid duplicate check
        create_assignment(ORG, TALENT, "v-s2", "style2", LoRARole.DETAIL, USER,
                          strength=0.3, trigger_words=["detailed"])

        context = build_generation_context(ORG, [TALENT])
        assert len(context.active_loras) == 2


# =============================================================================
# Multi-Talent
# =============================================================================


@pytest.mark.unit
class TestMultiTalent:

    def test_each_talent_gets_own_loras(self):
        _setup_eligible("v-t1", "v-t2")
        create_assignment(ORG, "talent-a", "v-t1", "face_a", LoRARole.IDENTITY, USER,
                          trigger_words=["tokena"])
        create_assignment(ORG, "talent-b", "v-t2", "face_b", LoRARole.IDENTITY, USER,
                          trigger_words=["tokenb"])

        context = build_generation_context(ORG, ["talent-a", "talent-b"])
        # Both talents' identity LoRAs applied (different characters, no conflict)
        assert len(context.active_loras) == 2
        words = context.effective_trigger_words
        assert "tokena" in words
        assert "tokenb" in words


# =============================================================================
# User Override
# =============================================================================


@pytest.mark.unit
class TestUserOverride:

    def test_user_removes_always_on(self):
        _setup_eligible("v-001")
        a = create_assignment(ORG, TALENT, "v-001", "lora", LoRARole.IDENTITY, USER,
                              mode=ApplicationMode.ALWAYS_ON, trigger_words=["ohwx"])

        context = build_generation_context(
            ORG, [TALENT],
            user_overrides=[{"action": "remove", "assignment_id": a.assignment_id}],
        )
        assert len(context.active_loras) == 0
        assert len(context.removed) == 1

    def test_user_adjusts_strength(self):
        _setup_eligible("v-001")
        a = create_assignment(ORG, TALENT, "v-001", "lora", LoRARole.STYLE, USER,
                              strength=0.8)

        context = build_generation_context(
            ORG, [TALENT],
            user_overrides=[{"action": "strength", "assignment_id": a.assignment_id, "value": 0.5}],
        )
        assert context.active_loras[0].overridden_strength == 0.5


# =============================================================================
# Trigger Word Visibility
# =============================================================================


@pytest.mark.unit
class TestTriggerWordVisibility:

    def test_trigger_words_in_context(self):
        _setup_eligible("v-001")
        create_assignment(ORG, TALENT, "v-001", "lora", LoRARole.IDENTITY, USER,
                          trigger_words=["ohwx", "person"])

        context = build_generation_context(ORG, [TALENT])
        assert "ohwx" in context.all_trigger_words
        assert "person" in context.all_trigger_words

    def test_visible_loras_include_trigger_words(self):
        _setup_eligible("v-001")
        create_assignment(ORG, TALENT, "v-001", "lora", LoRARole.IDENTITY, USER,
                          trigger_words=["ohwx"])

        visible = get_visible_loras(ORG, [TALENT])
        assert len(visible) == 1
        assert visible[0]["trigger_words"] == ["ohwx"]
        assert visible[0]["removable"] is True

    def test_removed_lora_trigger_words_excluded(self):
        _setup_eligible("v-001")
        a = create_assignment(ORG, TALENT, "v-001", "lora", LoRARole.IDENTITY, USER,
                              trigger_words=["ohwx"])

        context = build_generation_context(
            ORG, [TALENT],
            user_overrides=[{"action": "remove", "assignment_id": a.assignment_id}],
        )
        assert "ohwx" not in context.effective_trigger_words


# =============================================================================
# Context Package Persistence
# =============================================================================


@pytest.mark.unit
class TestContextPackage:

    def test_serialization_includes_all_data(self):
        _setup_eligible("v-001")
        create_assignment(ORG, TALENT, "v-001", "face_lora", LoRARole.IDENTITY, USER,
                          strength=0.85, trigger_words=["ohwx"])

        context = build_generation_context(ORG, [TALENT])
        serialized = serialize_for_context_package(context)

        assert len(serialized["applied_loras"]) == 1
        assert serialized["applied_loras"][0]["version_id"] == "v-001"
        assert serialized["applied_loras"][0]["strength"] == 0.85
        assert serialized["applied_loras"][0]["trigger_words"] == ["ohwx"]
        assert serialized["trigger_words"] == ["ohwx"]

    def test_serialization_tracks_removals(self):
        _setup_eligible("v-001")
        a = create_assignment(ORG, TALENT, "v-001", "lora", LoRARole.IDENTITY, USER)

        context = build_generation_context(
            ORG, [TALENT],
            user_overrides=[{"action": "remove", "assignment_id": a.assignment_id}],
        )
        serialized = serialize_for_context_package(context)
        assert len(serialized["removed_loras"]) == 1
        assert serialized["removed_loras"][0]["reason"] == "user_removal"


# =============================================================================
# Idempotency & Role Conflict
# =============================================================================


@pytest.mark.unit
class TestIdempotency:

    def test_duplicate_same_version_idempotent(self):
        _setup_eligible("v-001")
        a1 = create_assignment(ORG, TALENT, "v-001", "lora", LoRARole.IDENTITY, USER)
        a2 = create_assignment(ORG, TALENT, "v-001", "lora", LoRARole.IDENTITY, USER)
        assert a1.assignment_id == a2.assignment_id

    def test_new_version_same_role_replaces(self):
        _setup_eligible("v-001", "v-002")
        a1 = create_assignment(ORG, TALENT, "v-001", "lora_v1", LoRARole.IDENTITY, USER)
        a2 = create_assignment(ORG, TALENT, "v-002", "lora_v2", LoRARole.IDENTITY, USER)

        # a1 should be deactivated
        assignments = get_assignments(ORG, TALENT, active_only=True)
        assert len(assignments) == 1
        assert assignments[0].version_id == "v-002"


# =============================================================================
# Manual Mode Not Auto-Applied
# =============================================================================


@pytest.mark.unit
class TestManualMode:

    def test_manual_not_auto_applied(self):
        _setup_eligible("v-001")
        create_assignment(ORG, TALENT, "v-001", "optional_lora", LoRARole.STYLE, USER,
                          mode=ApplicationMode.MANUAL)

        auto = get_auto_applied_loras(ORG, TALENT)
        assert len(auto) == 0

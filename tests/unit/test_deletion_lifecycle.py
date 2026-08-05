"""Deletion Lifecycle Tests (Story 069).

Proves: all valid transitions, dependency blocks, cross-tenant denial,
restore behavior, idempotent operations, purge-hold enforcement, and
audit recording.

Run with:
    pytest tests/unit/test_deletion_lifecycle.py -v
"""
from __future__ import annotations

import pytest

from backend.deletion_lifecycle import (
    DEFAULT_VISIBLE_STATES,
    DEPENDENCY_RULES,
    RESTORABLE_STATES,
    SUPPORTED_ENTITIES,
    TERMINAL_STATES,
    VALID_TRANSITIONS,
    DependencyCheck,
    EntityLifecycle,
    HoldType,
    LifecycleState,
    PurgeBlockedError,
    TransitionAction,
    TransitionError,
    TransitionRecord,
    all_states_filter,
    apply_transition,
    check_dependencies,
    default_query_filter,
    idempotent_restore,
    idempotent_trash,
    trash_query_filter,
    validate_transition,
    verify_tenant_access,
)


# =============================================================================
# Helpers
# =============================================================================


def _make_entity(
    entity_type: str = "ai_talent",
    state: LifecycleState = LifecycleState.ACTIVE,
    org_id: str = "org-123",
    retention_policy: str = "UNVERIFIED",
) -> EntityLifecycle:
    return EntityLifecycle(
        entity_type=entity_type,
        entity_id="entity-abc",
        org_id=org_id,
        state=state,
        retention_policy=retention_policy,
    )


# =============================================================================
# Valid Transitions
# =============================================================================


class TestValidTransitions:

    @pytest.mark.unit
    def test_active_to_trashed(self):
        """ACTIVE + TRASH → TRASHED."""
        entity = _make_entity(state=LifecycleState.ACTIVE)
        record = apply_transition(
            entity, TransitionAction.TRASH,
            actor_id="user-1", reason="No longer needed",
        )
        assert entity.state == LifecycleState.TRASHED
        assert record.prior_state == LifecycleState.ACTIVE
        assert record.new_state == LifecycleState.TRASHED
        assert entity.trashed_at is not None
        assert entity.trashed_by == "user-1"

    @pytest.mark.unit
    def test_active_to_archived(self):
        """ACTIVE + ARCHIVE → ARCHIVED."""
        entity = _make_entity(state=LifecycleState.ACTIVE)
        apply_transition(
            entity, TransitionAction.ARCHIVE,
            actor_id="user-1", reason="Completed project",
        )
        assert entity.state == LifecycleState.ARCHIVED

    @pytest.mark.unit
    def test_archived_to_active(self):
        """ARCHIVED + UNARCHIVE → ACTIVE."""
        entity = _make_entity(state=LifecycleState.ARCHIVED)
        apply_transition(
            entity, TransitionAction.UNARCHIVE,
            actor_id="user-1", reason="Reopened",
        )
        assert entity.state == LifecycleState.ACTIVE

    @pytest.mark.unit
    def test_archived_to_trashed(self):
        """ARCHIVED + TRASH → TRASHED."""
        entity = _make_entity(state=LifecycleState.ARCHIVED)
        apply_transition(
            entity, TransitionAction.TRASH,
            actor_id="user-1", reason="Cleanup",
        )
        assert entity.state == LifecycleState.TRASHED

    @pytest.mark.unit
    def test_trashed_to_active_restore(self):
        """TRASHED + RESTORE → ACTIVE."""
        entity = _make_entity(state=LifecycleState.TRASHED)
        record = apply_transition(
            entity, TransitionAction.RESTORE,
            actor_id="user-1", reason="Mistake",
        )
        assert entity.state == LifecycleState.ACTIVE
        assert entity.trashed_at is None
        assert record.action == TransitionAction.RESTORE

    @pytest.mark.unit
    def test_trashed_to_purge_pending(self):
        """TRASHED + APPROVE_PURGE → PURGE_PENDING (with valid policy)."""
        entity = _make_entity(state=LifecycleState.TRASHED, retention_policy="30_days")
        apply_transition(
            entity, TransitionAction.APPROVE_PURGE,
            actor_id="admin-1", reason="Retention expired",
        )
        assert entity.state == LifecycleState.PURGE_PENDING

    @pytest.mark.unit
    def test_purge_pending_to_purged(self):
        """PURGE_PENDING + PURGE → PURGED."""
        entity = _make_entity(state=LifecycleState.PURGE_PENDING, retention_policy="30_days")
        apply_transition(
            entity, TransitionAction.PURGE,
            actor_id="system", reason="Scheduled cleanup",
        )
        assert entity.state == LifecycleState.PURGED

    @pytest.mark.unit
    def test_hold_placed_from_active(self):
        """ACTIVE + PLACE_HOLD → HOLD."""
        entity = _make_entity(state=LifecycleState.ACTIVE)
        apply_transition(
            entity, TransitionAction.PLACE_HOLD,
            actor_id="legal-1", reason="Litigation hold",
            hold_type=HoldType.LEGAL,
        )
        assert entity.state == LifecycleState.HOLD
        assert len(entity.active_holds) == 1
        assert entity.active_holds[0]["hold_type"] == "legal"

    @pytest.mark.unit
    def test_hold_released_returns_to_trashed(self):
        """HOLD + RELEASE_HOLD → TRASHED."""
        entity = _make_entity(state=LifecycleState.HOLD)
        entity.active_holds = [{"hold_type": "legal", "placed_by": "legal-1"}]
        apply_transition(
            entity, TransitionAction.RELEASE_HOLD,
            actor_id="legal-1", reason="Case resolved",
        )
        assert entity.state == LifecycleState.TRASHED
        assert len(entity.active_holds) == 0

    @pytest.mark.unit
    def test_purge_pending_can_restore(self):
        """PURGE_PENDING + RESTORE → ACTIVE (last chance recovery)."""
        entity = _make_entity(state=LifecycleState.PURGE_PENDING, retention_policy="30_days")
        apply_transition(
            entity, TransitionAction.RESTORE,
            actor_id="user-1", reason="Changed my mind",
        )
        assert entity.state == LifecycleState.ACTIVE


# =============================================================================
# Invalid Transitions
# =============================================================================


class TestInvalidTransitions:

    @pytest.mark.unit
    def test_purged_is_terminal(self):
        """PURGED state allows no transitions."""
        entity = _make_entity(state=LifecycleState.PURGED)
        with pytest.raises(TransitionError) as exc_info:
            apply_transition(
                entity, TransitionAction.RESTORE,
                actor_id="user-1", reason="Try to recover",
            )
        assert "terminal" in exc_info.value.message.lower()

    @pytest.mark.unit
    def test_active_cannot_restore(self):
        """ACTIVE + RESTORE is invalid (nothing to restore)."""
        entity = _make_entity(state=LifecycleState.ACTIVE)
        with pytest.raises(TransitionError) as exc_info:
            apply_transition(
                entity, TransitionAction.RESTORE,
                actor_id="user-1", reason="test",
            )
        assert exc_info.value.code == "INVALID_TRANSITION"

    @pytest.mark.unit
    def test_active_cannot_purge(self):
        """ACTIVE + PURGE is invalid (must trash first)."""
        entity = _make_entity(state=LifecycleState.ACTIVE)
        with pytest.raises(TransitionError):
            apply_transition(
                entity, TransitionAction.PURGE,
                actor_id="user-1", reason="test",
            )

    @pytest.mark.unit
    def test_trash_requires_reason(self):
        """TRASH action requires a reason."""
        entity = _make_entity(state=LifecycleState.ACTIVE)
        with pytest.raises(TransitionError) as exc_info:
            apply_transition(
                entity, TransitionAction.TRASH,
                actor_id="user-1", reason="",
            )
        assert "reason" in exc_info.value.message.lower()

    @pytest.mark.unit
    def test_hold_requires_type(self):
        """PLACE_HOLD requires hold_type."""
        entity = _make_entity(state=LifecycleState.ACTIVE)
        with pytest.raises(TransitionError) as exc_info:
            apply_transition(
                entity, TransitionAction.PLACE_HOLD,
                actor_id="user-1", reason="Some hold",
                hold_type=None,
            )
        assert "hold type" in exc_info.value.message.lower()


# =============================================================================
# Dependency Blocking
# =============================================================================


class TestDependencyBlocking:

    @pytest.mark.unit
    def test_talent_with_active_models_blocks_purge(self):
        """Talent with active LoRA models cannot be purge-approved."""
        entity = _make_entity(
            entity_type="ai_talent",
            state=LifecycleState.TRASHED,
            retention_policy="30_days",
        )
        active_children = {"lora_models": ["model-1", "model-2"]}

        with pytest.raises(PurgeBlockedError) as exc_info:
            apply_transition(
                entity, TransitionAction.APPROVE_PURGE,
                actor_id="admin-1", reason="Cleanup",
                active_children=active_children,
            )
        assert "dependencies" in exc_info.value.message.lower()

    @pytest.mark.unit
    def test_project_with_assets_blocks_purge(self):
        """Project with active assets cannot be purge-approved."""
        entity = _make_entity(
            entity_type="projects",
            state=LifecycleState.TRASHED,
            retention_policy="30_days",
        )
        active_children = {"assets": ["asset-1"]}

        with pytest.raises(PurgeBlockedError):
            apply_transition(
                entity, TransitionAction.APPROVE_PURGE,
                actor_id="admin-1", reason="Cleanup",
                active_children=active_children,
            )

    @pytest.mark.unit
    def test_no_dependencies_allows_purge(self):
        """Entity with no active children can be purge-approved."""
        entity = _make_entity(
            entity_type="ai_talent",
            state=LifecycleState.TRASHED,
            retention_policy="30_days",
        )
        active_children: dict[str, list[str]] = {}

        apply_transition(
            entity, TransitionAction.APPROVE_PURGE,
            actor_id="admin-1", reason="Cleanup",
            active_children=active_children,
        )
        assert entity.state == LifecycleState.PURGE_PENDING

    @pytest.mark.unit
    def test_dependency_check_function(self):
        """check_dependencies correctly identifies blocking deps."""
        result = check_dependencies(
            "ai_talent", "talent-1",
            active_children={"lora_models": ["m1"], "campaigns": ["c1", "c2"]},
        )
        assert result.has_dependencies is True
        assert result.blocks_purge is True
        assert len(result.blocking_dependencies) == 2

    @pytest.mark.unit
    def test_dependency_check_no_deps(self):
        """check_dependencies with no active children returns clean."""
        result = check_dependencies("ai_talent", "talent-1", active_children={})
        assert result.has_dependencies is False
        assert result.blocks_purge is False


# =============================================================================
# Purge Hold Enforcement
# =============================================================================


class TestPurgeHoldEnforcement:

    @pytest.mark.unit
    def test_unverified_retention_blocks_purge_approval(self):
        """UNVERIFIED retention policy blocks purge approval."""
        entity = _make_entity(
            state=LifecycleState.TRASHED,
            retention_policy="UNVERIFIED",
        )
        with pytest.raises(PurgeBlockedError) as exc_info:
            apply_transition(
                entity, TransitionAction.APPROVE_PURGE,
                actor_id="admin-1", reason="Cleanup",
            )
        assert "unverified" in exc_info.value.message.lower()

    @pytest.mark.unit
    def test_active_hold_blocks_purge_approval(self):
        """Active holds block purge approval."""
        entity = _make_entity(
            state=LifecycleState.TRASHED,
            retention_policy="30_days",
        )
        entity.active_holds = [{"hold_type": "legal", "reason": "Case pending"}]

        with pytest.raises(PurgeBlockedError) as exc_info:
            apply_transition(
                entity, TransitionAction.APPROVE_PURGE,
                actor_id="admin-1", reason="Cleanup",
            )
        assert "hold" in exc_info.value.message.lower()

    @pytest.mark.unit
    def test_hold_added_after_approval_blocks_purge(self):
        """Hold added after PURGE_PENDING blocks actual purge."""
        entity = _make_entity(
            state=LifecycleState.PURGE_PENDING,
            retention_policy="30_days",
        )
        entity.active_holds = [{"hold_type": "audit", "reason": "New requirement"}]

        with pytest.raises(PurgeBlockedError):
            apply_transition(
                entity, TransitionAction.PURGE,
                actor_id="system", reason="Scheduled",
            )

    @pytest.mark.unit
    def test_defined_policy_allows_purge(self):
        """Defined retention policy allows purge approval."""
        entity = _make_entity(
            state=LifecycleState.TRASHED,
            retention_policy="30_days",
        )
        apply_transition(
            entity, TransitionAction.APPROVE_PURGE,
            actor_id="admin-1", reason="Expired",
        )
        assert entity.state == LifecycleState.PURGE_PENDING


# =============================================================================
# Cross-Tenant Denial
# =============================================================================


class TestTenantIsolation:

    @pytest.mark.unit
    def test_same_org_access_allowed(self):
        """Same org_id grants access."""
        entity = _make_entity(org_id="org-123")
        assert verify_tenant_access(entity, "org-123") is True

    @pytest.mark.unit
    def test_different_org_denied(self):
        """Different org_id denies access."""
        entity = _make_entity(org_id="org-123")
        assert verify_tenant_access(entity, "org-456") is False

    @pytest.mark.unit
    def test_cross_tenant_cannot_trash(self):
        """Cross-tenant user should be denied before transition.
        (In production, the service layer checks verify_tenant_access first.)
        """
        entity = _make_entity(org_id="org-123")
        # Simulate service layer check
        assert verify_tenant_access(entity, "org-evil") is False

    @pytest.mark.unit
    def test_trashed_entity_still_isolated(self):
        """Trashed entities remain org-isolated."""
        entity = _make_entity(org_id="org-123", state=LifecycleState.TRASHED)
        assert verify_tenant_access(entity, "org-456") is False
        assert verify_tenant_access(entity, "org-123") is True


# =============================================================================
# Idempotent Operations
# =============================================================================


class TestIdempotent:

    @pytest.mark.unit
    def test_trash_already_trashed_is_noop(self):
        """Trashing an already-trashed entity is a no-op."""
        entity = _make_entity(state=LifecycleState.TRASHED)
        result = idempotent_trash(entity, actor_id="user-1", reason="Again")
        assert result is None
        assert entity.state == LifecycleState.TRASHED

    @pytest.mark.unit
    def test_trash_purged_is_noop(self):
        """Trashing a purged entity is a no-op."""
        entity = _make_entity(state=LifecycleState.PURGED)
        result = idempotent_trash(entity, actor_id="user-1", reason="test")
        assert result is None

    @pytest.mark.unit
    def test_restore_already_active_is_noop(self):
        """Restoring an active entity is a no-op."""
        entity = _make_entity(state=LifecycleState.ACTIVE)
        result = idempotent_restore(entity, actor_id="user-1")
        assert result is None

    @pytest.mark.unit
    def test_restore_from_hold_raises(self):
        """Cannot restore from HOLD state (must release hold first)."""
        entity = _make_entity(state=LifecycleState.HOLD)
        with pytest.raises(TransitionError) as exc_info:
            idempotent_restore(entity, actor_id="user-1")
        assert "not_restorable" == exc_info.value.code.lower()

    @pytest.mark.unit
    def test_repeated_trash_restore_cycle(self):
        """Entity can be trashed and restored multiple times."""
        entity = _make_entity(state=LifecycleState.ACTIVE)

        idempotent_trash(entity, actor_id="user-1", reason="First delete")
        assert entity.state == LifecycleState.TRASHED

        idempotent_restore(entity, actor_id="user-1", reason="Oops")
        assert entity.state == LifecycleState.ACTIVE

        idempotent_trash(entity, actor_id="user-1", reason="Second delete")
        assert entity.state == LifecycleState.TRASHED

        idempotent_restore(entity, actor_id="user-1", reason="Oops again")
        assert entity.state == LifecycleState.ACTIVE
        assert len(entity.transitions) == 4


# =============================================================================
# Audit Recording
# =============================================================================


class TestAuditRecording:

    @pytest.mark.unit
    def test_transition_records_all_fields(self):
        """Every transition records actor, reason, timestamp, and states."""
        entity = _make_entity(state=LifecycleState.ACTIVE)
        record = apply_transition(
            entity, TransitionAction.TRASH,
            actor_id="user-42", actor_role="editor", reason="Cleanup old talent",
        )
        assert record.actor_id == "user-42"
        assert record.actor_role == "editor"
        assert record.reason == "Cleanup old talent"
        assert record.prior_state == LifecycleState.ACTIVE
        assert record.new_state == LifecycleState.TRASHED
        assert record.timestamp is not None
        assert record.entity_type == "ai_talent"

    @pytest.mark.unit
    def test_transitions_accumulate(self):
        """Entity accumulates full transition history."""
        entity = _make_entity(state=LifecycleState.ACTIVE)
        apply_transition(entity, TransitionAction.ARCHIVE, actor_id="u1", reason="Done")
        apply_transition(entity, TransitionAction.TRASH, actor_id="u2", reason="Remove")
        apply_transition(entity, TransitionAction.RESTORE, actor_id="u1", reason="Oops")

        assert len(entity.transitions) == 3
        states = [(t.prior_state, t.new_state) for t in entity.transitions]
        assert states == [
            (LifecycleState.ACTIVE, LifecycleState.ARCHIVED),
            (LifecycleState.ARCHIVED, LifecycleState.TRASHED),
            (LifecycleState.TRASHED, LifecycleState.ACTIVE),
        ]

    @pytest.mark.unit
    def test_record_serializable(self):
        """TransitionRecord.to_dict() is JSON-serializable."""
        import json
        entity = _make_entity(state=LifecycleState.ACTIVE)
        record = apply_transition(
            entity, TransitionAction.PLACE_HOLD,
            actor_id="legal-1", reason="Litigation",
            hold_type=HoldType.LEGAL, hold_expires_at="2027-01-01T00:00:00Z",
        )
        d = record.to_dict()
        json.dumps(d)  # Should not raise
        assert d["hold_type"] == "legal"
        assert d["hold_expires_at"] == "2027-01-01T00:00:00Z"


# =============================================================================
# Query Filters
# =============================================================================


class TestQueryFilters:

    @pytest.mark.unit
    def test_default_filter_excludes_trashed(self):
        """Default queries exclude trashed, held, purge-pending, purged."""
        visible = default_query_filter()
        assert "active" in visible
        assert "archived" in visible
        assert "trashed" not in visible
        assert "hold" not in visible
        assert "purge_pending" not in visible
        assert "purged" not in visible

    @pytest.mark.unit
    def test_trash_filter_shows_only_trashed(self):
        """Trash view shows only trashed records."""
        visible = trash_query_filter()
        assert visible == {"trashed"}

    @pytest.mark.unit
    def test_all_states_excludes_purged(self):
        """Admin view shows everything except purged."""
        visible = all_states_filter()
        assert "purged" not in visible
        assert "active" in visible
        assert "trashed" in visible
        assert "hold" in visible


# =============================================================================
# Supported Entities Configuration
# =============================================================================


class TestConfiguration:

    @pytest.mark.unit
    def test_all_entities_have_unverified_policy(self):
        """All supported entities start with UNVERIFIED retention (DECISION-REQUIRED)."""
        for name, config in SUPPORTED_ENTITIES.items():
            assert config["retention_policy"] == "UNVERIFIED", (
                f"{name} should have UNVERIFIED retention until policy defined"
            )

    @pytest.mark.unit
    def test_supported_entities_complete(self):
        """All required entities are in the supported list."""
        required = {"assets", "ai_talent", "projects", "lora_models",
                    "brain_conversations", "workflows", "campaigns"}
        assert required.issubset(set(SUPPORTED_ENTITIES.keys()))

    @pytest.mark.unit
    def test_dependency_rules_reference_supported_entities(self):
        """Dependency rules reference valid entity types."""
        for entity_type, rules in DEPENDENCY_RULES.items():
            assert entity_type in SUPPORTED_ENTITIES
            for rule in rules:
                assert rule["dependent_type"] in SUPPORTED_ENTITIES

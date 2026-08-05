"""LoRA Promotion & Rollback Tests (Story 097).

Proves: one-active enforcement, concurrent promotion safety, rollback,
authorization, audit trail, idempotency, and state transitions.

Run with:
    pytest tests/unit/test_lora_promotion.py -v
"""
from __future__ import annotations

import threading

import pytest

from backend.lora_promotion import (
    PROMOTION_ROLES,
    AuthorizationError,
    LoRARole,
    PromotableVersion,
    PromotionAudit,
    PromotionError,
    RollbackError,
    VersionState,
    clear_registry,
    get_active_version,
    get_active_version_id,
    get_all_active_versions,
    get_promotion_history,
    promote,
    register_version,
    rollback,
    validate_promotion,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def _clean():
    clear_registry()
    yield
    clear_registry()


def _make_version(
    version_id: str = "v-1",
    state: VersionState = VersionState.VERIFIED,
    version_number: int = 1,
    **overrides,
) -> PromotableVersion:
    defaults = {
        "version_id": version_id,
        "org_id": "org-123",
        "talent_id": "talent-1",
        "role": LoRARole.PRIMARY,
        "state": state,
        "version_number": version_number,
        "output_checksum": "sha256_valid",
        "base_model_id": "flux-dev",
        "base_model_version": "1.0",
        "is_simulation": False,
        "lineage_id": "lineage-1",
    }
    defaults.update(overrides)
    v = PromotableVersion(**defaults)
    register_version(v)
    return v


# =============================================================================
# One-Active Enforcement
# =============================================================================


class TestOneActiveEnforcement:

    @pytest.mark.unit
    def test_promote_sets_active(self):
        """Promoting a version makes it the active one."""
        v = _make_version("v-1")
        promote(version_id="v-1", actor_id="admin-1", actor_role="admin", reason="Initial")
        active = get_active_version("org-123", "talent-1", LoRARole.PRIMARY)
        assert active is not None
        assert active.version_id == "v-1"
        assert active.state == VersionState.ACTIVE

    @pytest.mark.unit
    def test_promotion_supersedes_prior(self):
        """Promoting a new version supersedes the previous active."""
        v1 = _make_version("v-1", version_number=1)
        v2 = _make_version("v-2", version_number=2)
        promote(version_id="v-1", actor_id="admin-1", actor_role="admin")
        promote(version_id="v-2", actor_id="admin-1", actor_role="admin")

        assert v1.state == VersionState.SUPERSEDED
        assert v2.state == VersionState.ACTIVE
        assert get_active_version_id("org-123", "talent-1", LoRARole.PRIMARY) == "v-2"

    @pytest.mark.unit
    def test_only_one_active_per_talent_role(self):
        """Cannot have two active versions for same talent/role."""
        _make_version("v-1", version_number=1)
        _make_version("v-2", version_number=2)
        _make_version("v-3", version_number=3)

        promote(version_id="v-1", actor_id="admin-1", actor_role="admin")
        promote(version_id="v-2", actor_id="admin-1", actor_role="admin")
        promote(version_id="v-3", actor_id="admin-1", actor_role="admin")

        # Only v-3 should be active
        active_id = get_active_version_id("org-123", "talent-1", LoRARole.PRIMARY)
        assert active_id == "v-3"

    @pytest.mark.unit
    def test_different_roles_independent(self):
        """Different roles have independent active versions."""
        v_primary = _make_version("v-p", role=LoRARole.PRIMARY)
        v_style = _make_version("v-s", role=LoRARole.STYLE)

        promote(version_id="v-p", actor_id="admin-1", actor_role="admin")
        promote(version_id="v-s", actor_id="admin-1", actor_role="admin")

        assert get_active_version_id("org-123", "talent-1", LoRARole.PRIMARY) == "v-p"
        assert get_active_version_id("org-123", "talent-1", LoRARole.STYLE) == "v-s"

    @pytest.mark.unit
    def test_different_talents_independent(self):
        """Different talents have independent active versions."""
        v1 = _make_version("v-t1", talent_id="talent-1")
        v2 = _make_version("v-t2", talent_id="talent-2")

        promote(version_id="v-t1", actor_id="admin-1", actor_role="admin")
        promote(version_id="v-t2", actor_id="admin-1", actor_role="admin")

        assert get_active_version_id("org-123", "talent-1", LoRARole.PRIMARY) == "v-t1"
        assert get_active_version_id("org-123", "talent-2", LoRARole.PRIMARY) == "v-t2"


# =============================================================================
# Concurrent Promotion
# =============================================================================


class TestConcurrency:

    @pytest.mark.unit
    def test_concurrent_promotions_one_wins(self):
        """Under concurrency, exactly one version ends up active."""
        versions = []
        for i in range(5):
            v = _make_version(f"v-{i}", version_number=i + 1)
            versions.append(v)

        errors: list[Exception] = []
        results: list[PromotionAudit] = []

        def promote_one(vid: str) -> None:
            try:
                r = promote(version_id=vid, actor_id="admin", actor_role="admin")
                results.append(r)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=promote_one, args=(f"v-{i}",)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Exactly one version is active
        active_id = get_active_version_id("org-123", "talent-1", LoRARole.PRIMARY)
        assert active_id is not None
        active_count = sum(1 for v in versions if v.state == VersionState.ACTIVE)
        assert active_count == 1


# =============================================================================
# Idempotency
# =============================================================================


class TestIdempotency:

    @pytest.mark.unit
    def test_promote_already_active_is_noop(self):
        """Promoting the already-active version succeeds without change."""
        _make_version("v-1")
        promote(version_id="v-1", actor_id="admin-1", actor_role="admin")

        # Promote again
        audit = promote(version_id="v-1", actor_id="admin-1", actor_role="admin")
        assert audit.success is True
        assert "idempotent" in audit.reason.lower() or audit.prior_active_version_id == "v-1"

    @pytest.mark.unit
    def test_rollback_to_already_active_is_noop(self):
        """Rolling back to already-active version is idempotent."""
        _make_version("v-1")
        promote(version_id="v-1", actor_id="admin-1", actor_role="admin")

        audit = rollback(
            org_id="org-123", talent_id="talent-1", role=LoRARole.PRIMARY,
            target_version_id="v-1", actor_id="admin-1", actor_role="admin",
        )
        assert audit.success is True


# =============================================================================
# Rollback
# =============================================================================


class TestRollback:

    @pytest.mark.unit
    def test_rollback_reactivates_prior(self):
        """Rollback reactivates a superseded version."""
        v1 = _make_version("v-1", version_number=1)
        v2 = _make_version("v-2", version_number=2)

        promote(version_id="v-1", actor_id="admin-1", actor_role="admin")
        promote(version_id="v-2", actor_id="admin-1", actor_role="admin")
        assert v1.state == VersionState.SUPERSEDED

        rollback(
            org_id="org-123", talent_id="talent-1", role=LoRARole.PRIMARY,
            target_version_id="v-1", actor_id="admin-1", actor_role="admin",
            reason="v2 quality regression",
        )
        assert v1.state == VersionState.ACTIVE
        assert v2.state == VersionState.SUPERSEDED
        assert get_active_version_id("org-123", "talent-1", LoRARole.PRIMARY) == "v-1"

    @pytest.mark.unit
    def test_rollback_retired_version_fails(self):
        """Cannot rollback to a RETIRED version."""
        v1 = _make_version("v-1", state=VersionState.RETIRED)
        with pytest.raises(RollbackError) as exc_info:
            rollback(
                org_id="org-123", talent_id="talent-1", role=LoRARole.PRIMARY,
                target_version_id="v-1", actor_id="admin-1", actor_role="admin",
            )
        assert "not eligible" in exc_info.value.message

    @pytest.mark.unit
    def test_rollback_simulation_fails(self):
        """Cannot rollback to a simulation version."""
        _make_version("v-sim", state=VersionState.SUPERSEDED, is_simulation=True)
        with pytest.raises(RollbackError) as exc_info:
            rollback(
                org_id="org-123", talent_id="talent-1", role=LoRARole.PRIMARY,
                target_version_id="v-sim", actor_id="admin-1", actor_role="admin",
            )
        assert "simulation" in exc_info.value.message.lower()

    @pytest.mark.unit
    def test_rollback_wrong_talent_fails(self):
        """Cannot rollback to version belonging to different talent."""
        _make_version("v-other", talent_id="talent-other", state=VersionState.SUPERSEDED)
        with pytest.raises(RollbackError):
            rollback(
                org_id="org-123", talent_id="talent-1", role=LoRARole.PRIMARY,
                target_version_id="v-other", actor_id="admin-1", actor_role="admin",
            )

    @pytest.mark.unit
    def test_rollback_no_checksum_fails(self):
        """Cannot rollback to version without verified artifact."""
        _make_version("v-nochk", state=VersionState.SUPERSEDED, output_checksum="")
        with pytest.raises(RollbackError) as exc_info:
            rollback(
                org_id="org-123", talent_id="talent-1", role=LoRARole.PRIMARY,
                target_version_id="v-nochk", actor_id="admin-1", actor_role="admin",
            )
        assert "artifact" in exc_info.value.message.lower()


# =============================================================================
# Authorization
# =============================================================================


class TestAuthorization:

    @pytest.mark.unit
    def test_admin_can_promote(self):
        """Admin role can promote."""
        _make_version("v-1")
        audit = promote(version_id="v-1", actor_id="admin-1", actor_role="admin")
        assert audit.success is True

    @pytest.mark.unit
    def test_owner_can_promote(self):
        """Owner role can promote."""
        _make_version("v-1")
        audit = promote(version_id="v-1", actor_id="owner-1", actor_role="owner")
        assert audit.success is True

    @pytest.mark.unit
    def test_editor_cannot_promote(self):
        """Editor role cannot promote."""
        _make_version("v-1")
        with pytest.raises(AuthorizationError):
            promote(version_id="v-1", actor_id="editor-1", actor_role="editor")

    @pytest.mark.unit
    def test_editor_cannot_rollback(self):
        """Editor role cannot rollback."""
        _make_version("v-1", state=VersionState.SUPERSEDED)
        with pytest.raises(AuthorizationError):
            rollback(
                org_id="org-123", talent_id="talent-1", role=LoRARole.PRIMARY,
                target_version_id="v-1", actor_id="editor-1", actor_role="editor",
            )

    @pytest.mark.unit
    def test_simulation_cannot_promote(self):
        """Simulation version cannot be promoted."""
        _make_version("v-sim", is_simulation=True)
        with pytest.raises(PromotionError) as exc_info:
            promote(version_id="v-sim", actor_id="admin-1", actor_role="admin")
        assert "simulation" in exc_info.value.message.lower()

    @pytest.mark.unit
    def test_unverified_cannot_promote(self):
        """Version in wrong state cannot be promoted."""
        _make_version("v-active", state=VersionState.ACTIVE)
        with pytest.raises(PromotionError):
            promote(version_id="v-active", actor_id="admin-1", actor_role="admin")


# =============================================================================
# Audit Trail
# =============================================================================


class TestAudit:

    @pytest.mark.unit
    def test_promotion_creates_audit(self):
        """Successful promotion creates audit record."""
        _make_version("v-1")
        promote(version_id="v-1", actor_id="admin-1", actor_role="admin", reason="Go live")

        history = get_promotion_history("org-123", "talent-1")
        assert len(history) == 1
        assert history[0].action == "promote"
        assert history[0].actor_id == "admin-1"
        assert history[0].reason == "Go live"
        assert history[0].success is True

    @pytest.mark.unit
    def test_rollback_creates_audit(self):
        """Rollback creates audit record."""
        v1 = _make_version("v-1", version_number=1)
        v2 = _make_version("v-2", version_number=2)
        promote(version_id="v-1", actor_id="admin-1", actor_role="admin")
        promote(version_id="v-2", actor_id="admin-1", actor_role="admin")
        rollback(
            org_id="org-123", talent_id="talent-1", role=LoRARole.PRIMARY,
            target_version_id="v-1", actor_id="admin-1", actor_role="admin",
            reason="Quality regression",
        )

        history = get_promotion_history("org-123", "talent-1")
        rollbacks = [a for a in history if a.action == "rollback"]
        assert len(rollbacks) == 1
        assert rollbacks[0].reason == "Quality regression"
        assert rollbacks[0].new_active_version_id == "v-1"
        assert rollbacks[0].prior_active_version_id == "v-2"

    @pytest.mark.unit
    def test_failed_promotion_audited(self):
        """Failed promotion attempt is also audited."""
        _make_version("v-bad", state=VersionState.RETIRED)
        with pytest.raises(PromotionError):
            promote(version_id="v-bad", actor_id="admin-1", actor_role="admin")

        history = get_promotion_history("org-123", "talent-1")
        assert len(history) == 1
        assert history[0].success is False
        assert history[0].error is not None

    @pytest.mark.unit
    def test_audit_serializable(self):
        """PromotionAudit.to_dict() is JSON-serializable."""
        import json
        _make_version("v-1")
        audit = promote(version_id="v-1", actor_id="admin-1", actor_role="admin")
        json.dumps(audit.to_dict())

    @pytest.mark.unit
    def test_get_all_active_versions(self):
        """get_all_active_versions returns org-scoped map."""
        _make_version("v-1", talent_id="t-1")
        _make_version("v-2", talent_id="t-2")
        promote(version_id="v-1", actor_id="admin", actor_role="admin")
        promote(version_id="v-2", actor_id="admin", actor_role="admin")

        active = get_all_active_versions("org-123")
        assert len(active) == 2
        assert "t-1:primary" in active
        assert "t-2:primary" in active

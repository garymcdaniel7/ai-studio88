"""Release versioning tests — Story 062.

Tests prove:
  - Release manifest is immutable (frozen dataclass)
  - Release ID format is correct
  - Commit SHA required for creation
  - Migration compatibility correctly classified
  - Rollback blocked for CONTRACT migrations
  - Rollback allowed for EXPAND migrations
  - MIGRATE requires reverse migration
  - Version info exposed without secrets
  - Rollback rehearsal records evidence
  - Promotion blocked without security gate
  - Manifest hash is deterministic
"""

import pytest

from backend.release_manifest import (
    MigrationKind,
    ReleaseManifest,
    RollbackSafety,
    _reset_store,
    approve_for_promotion,
    check_rollback_compatibility,
    create_release,
    evaluate_rollback_safety,
    generate_release_id,
    get_version_info,
    rehearse_rollback,
    set_active_release,
)


@pytest.fixture(autouse=True)
def clean():
    _reset_store()
    yield
    _reset_store()


# =============================================================================
# Release Creation
# =============================================================================


@pytest.mark.unit
class TestReleaseCreation:

    def test_creates_manifest_with_id(self):
        m = create_release("abc123def", "gary", backend_image="sha256:abc")
        assert m.release_id.startswith("rel-")
        assert "abc123d" in m.release_id
        assert m.commit_sha == "abc123def"
        assert m.created_by == "gary"

    def test_requires_commit_sha(self):
        with pytest.raises(ValueError, match="commit_sha"):
            create_release("", "gary")

    def test_requires_created_by(self):
        with pytest.raises(ValueError, match="created_by"):
            create_release("abc123", "")

    def test_manifest_is_immutable(self):
        m = create_release("abc", "gary")
        with pytest.raises(Exception):  # FrozenInstanceError
            m.commit_sha = "tampered"

    def test_release_id_format(self):
        rid = generate_release_id("deadbeef123")
        assert rid.startswith("rel-")
        assert "deadbee" in rid
        assert len(rid) > 15


# =============================================================================
# Migration Compatibility
# =============================================================================


@pytest.mark.unit
class TestMigrationCompatibility:

    def test_expand_is_safe(self):
        safety, reason = evaluate_rollback_safety(MigrationKind.EXPAND)
        assert safety == RollbackSafety.SAFE
        assert reason is None

    def test_migrate_requires_reverse(self):
        safety, reason = evaluate_rollback_safety(MigrationKind.MIGRATE)
        assert safety == RollbackSafety.REQUIRES_REVERSE
        assert "reverse" in reason.lower()

    def test_contract_blocks_rollback(self):
        safety, reason = evaluate_rollback_safety(MigrationKind.CONTRACT)
        assert safety == RollbackSafety.BLOCKED
        assert "irreversible" in reason.lower()


# =============================================================================
# Rollback Compatibility Check
# =============================================================================


@pytest.mark.unit
class TestRollbackCompatibility:

    def test_expand_rollback_compatible(self):
        r1 = create_release("aaa", "gary", migration_kind=MigrationKind.EXPAND)
        r2 = create_release("bbb", "gary", migration_kind=MigrationKind.EXPAND)
        result = check_rollback_compatibility(r2.release_id, r1.release_id)
        assert result["compatible"] is True
        assert result["requires_reverse_migration"] is False

    def test_contract_rollback_blocked(self):
        r1 = create_release("aaa", "gary", migration_kind=MigrationKind.EXPAND)
        r2 = create_release("bbb", "gary", migration_kind=MigrationKind.CONTRACT)
        result = check_rollback_compatibility(r2.release_id, r1.release_id)
        assert result["compatible"] is False
        assert "irreversible" in result["reason"].lower()

    def test_migrate_rollback_needs_reverse(self):
        r1 = create_release("aaa", "gary", migration_kind=MigrationKind.EXPAND)
        r2 = create_release("bbb", "gary", migration_kind=MigrationKind.MIGRATE)
        result = check_rollback_compatibility(r2.release_id, r1.release_id)
        assert result["compatible"] is True
        assert result["requires_reverse_migration"] is True

    def test_unknown_release_not_compatible(self):
        create_release("aaa", "gary")
        result = check_rollback_compatibility("nonexistent", "also-nonexistent")
        assert result["compatible"] is False


# =============================================================================
# Rollback Rehearsal
# =============================================================================


@pytest.mark.unit
class TestRollbackRehearsal:

    def test_rehearsal_passes_for_expand(self):
        r1 = create_release("aaa", "gary", migration_kind=MigrationKind.EXPAND)
        r2 = create_release("bbb", "gary", migration_kind=MigrationKind.EXPAND)
        result = rehearse_rollback(r2.release_id, r1.release_id)
        assert result.executed is True
        assert result.success is True
        assert not result.errors

    def test_rehearsal_blocked_for_contract(self):
        r1 = create_release("aaa", "gary", migration_kind=MigrationKind.EXPAND)
        r2 = create_release("bbb", "gary", migration_kind=MigrationKind.CONTRACT)
        result = rehearse_rollback(r2.release_id, r1.release_id)
        assert result.executed is False
        assert result.success is False
        assert "blocked" in result.errors[0].lower()


# =============================================================================
# Version Propagation
# =============================================================================


@pytest.mark.unit
class TestVersionPropagation:

    def test_dev_local_when_no_release(self):
        info = get_version_info()
        assert info["release_id"] == "dev-local"

    def test_active_release_exposed(self):
        m = create_release("abc123", "gary", migrations_version="037")
        set_active_release(m.release_id)
        info = get_version_info()
        assert info["release_id"] == m.release_id
        assert info["commit_sha"] == "abc123"[:7]
        assert info["migrations_version"] == "037"

    def test_no_secrets_in_version_info(self):
        m = create_release("abc123", "gary", backend_image="sha256:secret_digest")
        set_active_release(m.release_id)
        info = get_version_info()
        assert "secret_digest" not in str(info)
        assert "backend_image" not in info


# =============================================================================
# Promotion Approval
# =============================================================================


@pytest.mark.unit
class TestPromotionApproval:

    def test_approved_with_security_gate(self):
        m = create_release("abc", "gary", security_gate_passed=True)
        result = approve_for_promotion(m.release_id, "admin")
        assert result["approved"] is True

    def test_blocked_without_security_gate(self):
        m = create_release("abc", "gary", security_gate_passed=False)
        result = approve_for_promotion(m.release_id, "admin")
        assert result["approved"] is False
        assert "Security gate" in str(result["issues"])

    def test_blocked_irreversible_without_acknowledgment(self):
        m = create_release("abc", "gary", migration_kind=MigrationKind.CONTRACT, security_gate_passed=True)
        result = approve_for_promotion(m.release_id, "admin")
        assert result["approved"] is False
        assert "irreversible" in str(result["issues"]).lower()


# =============================================================================
# Manifest Integrity
# =============================================================================


@pytest.mark.unit
class TestManifestIntegrity:

    def test_manifest_hash_deterministic(self):
        m = create_release("abc", "gary", backend_image="img:1", migrations_version="005")
        h1 = m.manifest_hash
        h2 = m.manifest_hash
        assert h1 == h2
        assert len(h1) == 16

    def test_different_content_different_hash(self):
        m1 = create_release("abc", "gary", backend_image="img:1")
        m2 = create_release("def", "gary", backend_image="img:2")
        assert m1.manifest_hash != m2.manifest_hash

    def test_to_dict_serializable(self):
        m = create_release("abc123", "gary", deployment_targets=("staging", "production"))
        d = m.to_dict()
        assert d["release_id"] == m.release_id
        assert d["deployment_targets"] == ["staging", "production"]
        assert d["migration_kind"] == "expand"

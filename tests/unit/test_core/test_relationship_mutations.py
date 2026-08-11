"""Authenticated relationship mutations tests — Story 106.

Tests prove:
  - Cross-tenant source/target rejected
  - Stale version → conflict response
  - Deletion of already-deleted is idempotent
  - Membership revoked → rejected
  - Invalid relationship type rejected
  - Duplicate submit returns existing (idempotent)
  - Source archived → rejected
  - Rollback: rejected mutation doesn't change state
  - Viewer role cannot mutate
  - Audit events recorded for all attempts
"""

import pytest

from backend.relationship_mutations import (
    MemberRole,
    MutationAction,
    MutationRequest,
    MutationResult,
    _archive_entity,
    _register_entity_owner,
    _register_membership,
    _reset_store,
    execute_mutation,
    get_audit_log,
    get_confirmed_relationships,
)


@pytest.fixture(autouse=True)
def clean():
    _reset_store()
    yield
    _reset_store()


ORG = "org-test-001"
OTHER_ORG = "org-other-999"
USER = "user-001"


def _setup_user(user_id: str = USER, org_id: str = ORG, role: MemberRole = MemberRole.EDITOR):
    _register_membership(user_id, org_id, role)


def _create_request(**overrides) -> MutationRequest:
    defaults = dict(
        org_id=ORG,
        user_id=USER,
        user_role=MemberRole.EDITOR,
        action=MutationAction.CREATE,
        rel_type="wears",
        source_id="talent-001",
        source_type="talent",
        target_id="wardrobe-001",
        target_type="wardrobe",
    )
    defaults.update(overrides)
    return MutationRequest(**defaults)


# =============================================================================
# Happy Path
# =============================================================================


@pytest.mark.unit
class TestHappyPath:

    def test_create_confirmed(self):
        _setup_user()
        req = _create_request()
        resp = execute_mutation(req)
        assert resp.is_success
        assert resp.relationship_id is not None
        assert resp.current_version == 1

    def test_update_increments_version(self):
        _setup_user()
        create_resp = execute_mutation(_create_request())
        update_req = MutationRequest(
            org_id=ORG, user_id=USER, user_role=MemberRole.EDITOR,
            action=MutationAction.UPDATE,
            relationship_id=create_resp.relationship_id,
            expected_version=1,
            rel_type="holds",
        )
        resp = execute_mutation(update_req)
        assert resp.is_success
        assert resp.current_version == 2

    def test_delete_confirmed(self):
        _setup_user()
        create_resp = execute_mutation(_create_request())
        delete_req = MutationRequest(
            org_id=ORG, user_id=USER, user_role=MemberRole.EDITOR,
            action=MutationAction.DELETE,
            relationship_id=create_resp.relationship_id,
        )
        resp = execute_mutation(delete_req)
        assert resp.is_success


# =============================================================================
# Cross-Tenant
# =============================================================================


@pytest.mark.unit
class TestCrossTenant:

    def test_cross_tenant_source_rejected(self):
        _setup_user()
        _register_entity_owner("talent-evil", OTHER_ORG)
        req = _create_request(source_id="talent-evil")
        resp = execute_mutation(req)
        assert resp.result == MutationResult.REJECTED
        assert resp.error_code == "OWNERSHIP_VIOLATION"

    def test_cross_tenant_target_rejected(self):
        _setup_user()
        _register_entity_owner("wardrobe-evil", OTHER_ORG)
        req = _create_request(target_id="wardrobe-evil")
        resp = execute_mutation(req)
        assert resp.result == MutationResult.REJECTED
        assert resp.error_code == "OWNERSHIP_VIOLATION"


# =============================================================================
# Stale Version (Conflict)
# =============================================================================


@pytest.mark.unit
class TestStaleVersion:

    def test_stale_version_on_update(self):
        _setup_user()
        create_resp = execute_mutation(_create_request())
        # Update with wrong version
        update_req = MutationRequest(
            org_id=ORG, user_id=USER, user_role=MemberRole.EDITOR,
            action=MutationAction.UPDATE,
            relationship_id=create_resp.relationship_id,
            expected_version=99,  # Wrong!
        )
        resp = execute_mutation(update_req)
        assert resp.result == MutationResult.CONFLICT
        assert resp.error_code == "VERSION_CONFLICT"
        assert resp.current_version == 1

    def test_stale_version_on_delete(self):
        _setup_user()
        create_resp = execute_mutation(_create_request())
        delete_req = MutationRequest(
            org_id=ORG, user_id=USER, user_role=MemberRole.EDITOR,
            action=MutationAction.DELETE,
            relationship_id=create_resp.relationship_id,
            expected_version=99,
        )
        resp = execute_mutation(delete_req)
        assert resp.result == MutationResult.CONFLICT


# =============================================================================
# Already Deleted (Idempotent)
# =============================================================================


@pytest.mark.unit
class TestAlreadyDeleted:

    def test_delete_already_deleted_idempotent(self):
        _setup_user()
        create_resp = execute_mutation(_create_request())
        delete_req = MutationRequest(
            org_id=ORG, user_id=USER, user_role=MemberRole.EDITOR,
            action=MutationAction.DELETE,
            relationship_id=create_resp.relationship_id,
        )
        execute_mutation(delete_req)
        # Second delete — idempotent
        resp = execute_mutation(delete_req)
        assert resp.is_success

    def test_update_deleted_rejected(self):
        _setup_user()
        create_resp = execute_mutation(_create_request())
        delete_req = MutationRequest(
            org_id=ORG, user_id=USER, user_role=MemberRole.EDITOR,
            action=MutationAction.DELETE,
            relationship_id=create_resp.relationship_id,
        )
        execute_mutation(delete_req)
        # Try to update deleted
        update_req = MutationRequest(
            org_id=ORG, user_id=USER, user_role=MemberRole.EDITOR,
            action=MutationAction.UPDATE,
            relationship_id=create_resp.relationship_id,
        )
        resp = execute_mutation(update_req)
        assert resp.result == MutationResult.REJECTED
        assert resp.error_code == "ALREADY_DELETED"


# =============================================================================
# Membership Revoked
# =============================================================================


@pytest.mark.unit
class TestMembershipRevoked:

    def test_no_membership_rejected(self):
        # Don't register membership
        req = _create_request()
        resp = execute_mutation(req)
        assert resp.result == MutationResult.REJECTED
        assert resp.error_code == "MEMBERSHIP_REQUIRED"

    def test_viewer_cannot_mutate(self):
        _register_membership(USER, ORG, MemberRole.VIEWER)
        req = _create_request(user_role=MemberRole.VIEWER)
        resp = execute_mutation(req)
        assert resp.result == MutationResult.REJECTED
        assert resp.error_code == "INSUFFICIENT_ROLE"


# =============================================================================
# Invalid Type
# =============================================================================


@pytest.mark.unit
class TestInvalidType:

    def test_invalid_rel_type_rejected(self):
        _setup_user()
        req = _create_request(rel_type="made_up_type")
        resp = execute_mutation(req)
        assert resp.result == MutationResult.REJECTED
        assert resp.error_code == "INVALID_TYPE"

    def test_valid_type_accepted(self):
        _setup_user()
        req = _create_request(rel_type="friends_with")
        resp = execute_mutation(req)
        assert resp.is_success


# =============================================================================
# Duplicate Submit (Idempotent)
# =============================================================================


@pytest.mark.unit
class TestDuplicateSubmit:

    def test_duplicate_create_returns_existing(self):
        _setup_user()
        req = _create_request()
        r1 = execute_mutation(req)
        r2 = execute_mutation(req)
        assert r1.relationship_id == r2.relationship_id
        assert r2.is_success


# =============================================================================
# Source Archived
# =============================================================================


@pytest.mark.unit
class TestSourceArchived:

    def test_archived_source_blocks_create(self):
        _setup_user()
        _archive_entity("talent-001")
        req = _create_request(source_id="talent-001")
        resp = execute_mutation(req)
        assert resp.result == MutationResult.REJECTED
        assert resp.error_code == "SOURCE_ARCHIVED"


# =============================================================================
# Rollback (failed mutations don't change state)
# =============================================================================


@pytest.mark.unit
class TestRollback:

    def test_failed_create_no_state_change(self):
        _setup_user()
        _register_entity_owner("talent-evil", OTHER_ORG)
        req = _create_request(source_id="talent-evil")
        execute_mutation(req)
        # No relationship created
        confirmed = get_confirmed_relationships(ORG)
        assert len(confirmed) == 0

    def test_conflict_no_state_change(self):
        _setup_user()
        create_resp = execute_mutation(_create_request())
        # Try update with wrong version
        update_req = MutationRequest(
            org_id=ORG, user_id=USER, user_role=MemberRole.EDITOR,
            action=MutationAction.UPDATE,
            relationship_id=create_resp.relationship_id,
            expected_version=99,
            rel_type="holds",
        )
        execute_mutation(update_req)
        # Relationship type unchanged
        rels = get_confirmed_relationships(ORG)
        assert rels[0].rel_type == "wears"  # Original type preserved


# =============================================================================
# Audit Events
# =============================================================================


@pytest.mark.unit
class TestAuditEvents:

    def test_success_audited(self):
        _setup_user()
        execute_mutation(_create_request())
        log = get_audit_log(ORG)
        assert len(log) == 1
        assert log[0].result == MutationResult.CONFIRMED

    def test_failure_audited(self):
        # No membership — will fail
        execute_mutation(_create_request())
        log = get_audit_log(ORG)
        assert len(log) == 1
        assert log[0].result == MutationResult.REJECTED

    def test_all_attempts_audited(self):
        _setup_user()
        execute_mutation(_create_request())
        execute_mutation(_create_request(rel_type="invalid_garbage"))
        log = get_audit_log(ORG)
        assert len(log) == 2
        results = {e.result for e in log}
        assert MutationResult.CONFIRMED in results
        assert MutationResult.REJECTED in results

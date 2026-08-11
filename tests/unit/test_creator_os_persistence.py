"""Creator OS Durable Persistence Tests (Story 121).

Proves: tenant isolation, lifecycle transitions, version conflicts,
cross-tenant denial, pagination, search, and record types.

Run with:
    pytest tests/unit/test_creator_os_persistence.py -v
"""
from __future__ import annotations

import pytest

from backend.creator_os_persistence import (
    LifecycleState,
    PaginatedResult,
    RecordNotFoundError,
    RecordType,
    TenantAccessError,
    VersionConflictError,
    archive_record,
    clear_store,
    count_records,
    create_record,
    get_record,
    list_records,
    restore_record,
    search_records,
    trash_record,
    update_record,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def _clean():
    clear_store()
    yield
    clear_store()


def _create(record_type: RecordType = RecordType.CAMPAIGN, org_id: str = "org-1", **data_overrides):
    data = {"name": "Test Campaign", "status": "draft"}
    data.update(data_overrides)
    return create_record(
        record_type=record_type, org_id=org_id,
        created_by="user-1", data=data,
    )


# =============================================================================
# Tenant Isolation
# =============================================================================


class TestTenantIsolation:

    @pytest.mark.unit
    def test_create_requires_org_id(self):
        """Cannot create without org_id."""
        with pytest.raises(TenantAccessError):
            create_record(record_type=RecordType.CAMPAIGN, org_id="", created_by="u", data={})

    @pytest.mark.unit
    def test_create_requires_actor(self):
        """Cannot create without created_by."""
        with pytest.raises(TenantAccessError):
            create_record(record_type=RecordType.CAMPAIGN, org_id="org-1", created_by="", data={})

    @pytest.mark.unit
    def test_get_cross_tenant_denied(self):
        """Cannot read record from another org."""
        record = _create(org_id="org-1")
        with pytest.raises(TenantAccessError):
            get_record(record.id, org_id="org-evil")

    @pytest.mark.unit
    def test_update_cross_tenant_denied(self):
        """Cannot update record from another org."""
        record = _create(org_id="org-1")
        with pytest.raises(TenantAccessError):
            update_record(record.id, org_id="org-evil", updated_by="u", expected_version=1, data={})

    @pytest.mark.unit
    def test_list_only_own_org(self):
        """Listing returns only requesting org's records."""
        _create(org_id="org-1", name="A")
        _create(org_id="org-1", name="B")
        _create(org_id="org-2", name="C")

        result = list_records(org_id="org-1")
        assert result.total == 2

    @pytest.mark.unit
    def test_trash_cross_tenant_denied(self):
        """Cannot trash record from another org."""
        record = _create(org_id="org-1")
        with pytest.raises(TenantAccessError):
            trash_record(record.id, org_id="org-evil", actor="u")

    @pytest.mark.unit
    def test_search_scoped_to_org(self):
        """Search only returns records from requesting org."""
        _create(org_id="org-1", name="Alpha Campaign")
        _create(org_id="org-2", name="Alpha Other")
        results = search_records(org_id="org-1", query="alpha")
        assert len(results) == 1


# =============================================================================
# Lifecycle
# =============================================================================


class TestLifecycle:

    @pytest.mark.unit
    def test_new_record_is_active(self):
        """New records start in ACTIVE state."""
        record = _create()
        assert record.lifecycle_state == LifecycleState.ACTIVE

    @pytest.mark.unit
    def test_trash_moves_to_trashed(self):
        """Trashing moves record to TRASHED state."""
        record = _create()
        trash_record(record.id, org_id="org-1", actor="user-1")
        assert record.lifecycle_state == LifecycleState.TRASHED

    @pytest.mark.unit
    def test_trash_idempotent(self):
        """Trashing already-trashed record is idempotent."""
        record = _create()
        trash_record(record.id, org_id="org-1", actor="user-1")
        trash_record(record.id, org_id="org-1", actor="user-1")  # No error
        assert record.lifecycle_state == LifecycleState.TRASHED

    @pytest.mark.unit
    def test_restore_from_trashed(self):
        """Restoring trashed record returns to ACTIVE."""
        record = _create()
        trash_record(record.id, org_id="org-1", actor="user-1")
        restore_record(record.id, org_id="org-1", actor="user-1")
        assert record.lifecycle_state == LifecycleState.ACTIVE

    @pytest.mark.unit
    def test_archive_record(self):
        """Archiving moves to ARCHIVED state."""
        record = _create()
        archive_record(record.id, org_id="org-1", actor="user-1")
        assert record.lifecycle_state == LifecycleState.ARCHIVED

    @pytest.mark.unit
    def test_trashed_excluded_from_default_list(self):
        """Default listing excludes trashed records."""
        r1 = _create(name="Keep")
        r2 = _create(name="Delete")
        trash_record(r2.id, org_id="org-1", actor="user-1")
        result = list_records(org_id="org-1")
        assert result.total == 1
        assert result.items[0].data["name"] == "Keep"

    @pytest.mark.unit
    def test_cannot_update_trashed(self):
        """Cannot update a trashed record."""
        record = _create()
        trash_record(record.id, org_id="org-1", actor="user-1")
        with pytest.raises(RecordNotFoundError):
            update_record(record.id, org_id="org-1", updated_by="u", expected_version=record.version, data={"name": "changed"})


# =============================================================================
# Version Conflicts
# =============================================================================


class TestVersionConflicts:

    @pytest.mark.unit
    def test_update_with_correct_version(self):
        """Update succeeds with matching version."""
        record = _create()
        updated = update_record(
            record.id, org_id="org-1", updated_by="user-2",
            expected_version=1, data={"name": "Updated"},
        )
        assert updated.version == 2
        assert updated.data["name"] == "Updated"
        assert updated.updated_by == "user-2"

    @pytest.mark.unit
    def test_stale_write_rejected(self):
        """Update with stale version raises VersionConflictError."""
        record = _create()
        update_record(record.id, org_id="org-1", updated_by="u", expected_version=1, data={"name": "v2"})
        with pytest.raises(VersionConflictError) as exc_info:
            update_record(record.id, org_id="org-1", updated_by="u", expected_version=1, data={"name": "stale"})
        assert exc_info.value.expected == 1
        assert exc_info.value.actual == 2

    @pytest.mark.unit
    def test_version_increments_on_trash(self):
        """Version increments when trashing."""
        record = _create()
        assert record.version == 1
        trash_record(record.id, org_id="org-1", actor="user-1")
        assert record.version == 2

    @pytest.mark.unit
    def test_version_increments_on_restore(self):
        """Version increments when restoring."""
        record = _create()
        trash_record(record.id, org_id="org-1", actor="user-1")
        restore_record(record.id, org_id="org-1", actor="user-1")
        assert record.version == 3

    @pytest.mark.unit
    def test_concurrent_updates_one_wins(self):
        """Two updates with same expected_version — one wins, one fails."""
        record = _create()
        # First succeeds
        update_record(record.id, org_id="org-1", updated_by="u-A", expected_version=1, data={"name": "A"})
        # Second fails (stale)
        with pytest.raises(VersionConflictError):
            update_record(record.id, org_id="org-1", updated_by="u-B", expected_version=1, data={"name": "B"})


# =============================================================================
# Pagination
# =============================================================================


class TestPagination:

    @pytest.mark.unit
    def test_default_limit(self):
        """Default limit is 20."""
        for i in range(25):
            _create(name=f"Item {i}")
        result = list_records(org_id="org-1")
        assert result.limit == 20
        assert len(result.items) == 20
        assert result.total == 25

    @pytest.mark.unit
    def test_custom_limit_offset(self):
        """Custom limit and offset work."""
        for i in range(10):
            _create(name=f"Item {i}")
        result = list_records(org_id="org-1", limit=3, offset=2)
        assert len(result.items) == 3
        assert result.offset == 2
        assert result.total == 10

    @pytest.mark.unit
    def test_filter_by_record_type(self):
        """Can filter by record type."""
        _create(record_type=RecordType.CAMPAIGN, name="Camp")
        _create(record_type=RecordType.BRAND, name="Brand")
        _create(record_type=RecordType.NOTIFICATION, name="Notif")

        result = list_records(org_id="org-1", record_type=RecordType.CAMPAIGN)
        assert result.total == 1
        assert result.items[0].record_type == RecordType.CAMPAIGN

    @pytest.mark.unit
    def test_count_records(self):
        """count_records returns correct total."""
        _create(record_type=RecordType.CAMPAIGN)
        _create(record_type=RecordType.CAMPAIGN)
        _create(record_type=RecordType.BRAND)
        assert count_records(org_id="org-1", record_type=RecordType.CAMPAIGN) == 2
        assert count_records(org_id="org-1") == 3

    @pytest.mark.unit
    def test_paginated_result_serializable(self):
        """PaginatedResult.to_dict() is JSON-serializable."""
        import json
        _create()
        result = list_records(org_id="org-1")
        json.dumps(result.to_dict())


# =============================================================================
# Record Types
# =============================================================================


class TestRecordTypes:

    @pytest.mark.unit
    def test_all_record_types_creatable(self):
        """All 6 record types can be created."""
        for rt in RecordType:
            record = create_record(
                record_type=rt, org_id="org-1", created_by="user-1",
                data={"name": f"Test {rt.value}"},
            )
            assert record.record_type == rt

    @pytest.mark.unit
    def test_record_serializable(self):
        """CreatorOSRecord.to_dict() is JSON-serializable."""
        import json
        record = _create()
        json.dumps(record.to_dict())


# =============================================================================
# Search
# =============================================================================


class TestSearch:

    @pytest.mark.unit
    def test_search_finds_matching(self):
        """Search finds records with matching data."""
        _create(name="Summer Campaign 2026")
        _create(name="Winter Sale")
        results = search_records(org_id="org-1", query="summer")
        assert len(results) == 1

    @pytest.mark.unit
    def test_search_excludes_trashed(self):
        """Search excludes trashed records."""
        record = _create(name="Deleted Campaign")
        trash_record(record.id, org_id="org-1", actor="user-1")
        results = search_records(org_id="org-1", query="deleted")
        assert len(results) == 0

    @pytest.mark.unit
    def test_search_respects_limit(self):
        """Search respects limit parameter."""
        for i in range(10):
            _create(name=f"Match {i}")
        results = search_records(org_id="org-1", query="match", limit=3)
        assert len(results) == 3

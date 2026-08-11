"""Unit tests for OrgIdBackfillService — quarantine, classify, and backfill.

Tests cover:
    - Table classification: founder-only vs ambiguous vs no-nulls
    - Bulk assignment SQL generation for founder-only tables
    - Quarantine SQL generation for ambiguous tables
    - NOT NULL constraint only applied after all NULLs resolved
    - Quarantine resolution validation (assigned/system/purged)
    - Full backfill plan generation
    - Edge cases: system org, quarantined UUID rejection

Requirements: R5.6, R69.1, R69.2, R69.3, R69.4, R69.5, R69.6, R2.1
"""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest

# =============================================================================
# Mock external dependencies BEFORE importing the service module.
# structlog may not be installed in the test venv.
# =============================================================================

sys.modules.setdefault("structlog", MagicMock())

from app.services.org_id_backfill import (
    CATEGORY_A_TABLES,
    QUARANTINED_UUID,
    SYSTEM_ORG_ID,
    BackfillResult,
    OrgIdBackfillService,
    OwnershipClassification,
    QuarantineResolution,
    TableClassification,
    TableNullAudit,
    TableOwnershipType,
)


# =============================================================================
# Fixtures
# =============================================================================

FOUNDER_ORG_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
OTHER_ORG_ID = UUID("11111111-2222-3333-4444-555555555555")


@pytest.fixture
def service() -> OrgIdBackfillService:
    """Create a backfill service with a test founder org_id."""
    return OrgIdBackfillService(founder_org_id=FOUNDER_ORG_ID)


# =============================================================================
# Test: Service Initialization
# =============================================================================


class TestServiceInitialization:
    """Test OrgIdBackfillService construction validation."""

    def test_valid_founder_org_id(self) -> None:
        """Service initializes with a valid founder org_id."""
        svc = OrgIdBackfillService(founder_org_id=FOUNDER_ORG_ID)
        assert svc.founder_org_id == FOUNDER_ORG_ID

    def test_rejects_quarantined_uuid(self) -> None:
        """Cannot use quarantined placeholder as founder org_id."""
        with pytest.raises(ValueError, match="quarantined placeholder"):
            OrgIdBackfillService(founder_org_id=QUARANTINED_UUID)

    def test_rejects_system_org_uuid(self) -> None:
        """Cannot use system org as founder org_id."""
        with pytest.raises(ValueError, match="system org UUID"):
            OrgIdBackfillService(founder_org_id=SYSTEM_ORG_ID)


# =============================================================================
# Test: Table Classification (R69.1)
# =============================================================================


class TestTableClassification:
    """Test classify_table() logic per R69.1 and R5.6.

    **Validates: Requirements R5.6, R69.1**
    """

    def test_no_null_rows_classified_as_ready(self, service: OrgIdBackfillService) -> None:
        """Table with zero NULL org_id is ready for NOT NULL constraint."""
        audit = TableNullAudit(
            table_name="talent",
            null_count=0,
            total_count=50,
            has_org_id_column=True,
            is_nullable=True,
            distinct_org_ids=[FOUNDER_ORG_ID],
        )
        result = service.classify_table(audit)
        assert result.ownership_type == TableOwnershipType.NO_NULL_ROWS
        assert "ready for NOT NULL" in result.reason

    def test_founder_only_single_org(self, service: OrgIdBackfillService) -> None:
        """Table with only founder's org data classified as FOUNDER_ONLY."""
        audit = TableNullAudit(
            table_name="assets",
            null_count=10,
            total_count=100,
            has_org_id_column=True,
            is_nullable=True,
            distinct_org_ids=[FOUNDER_ORG_ID, None],
        )
        result = service.classify_table(audit)
        assert result.ownership_type == TableOwnershipType.FOUNDER_ONLY
        assert "founder org" in result.reason
        assert result.null_count == 10

    def test_founder_only_no_orgs_at_all(self, service: OrgIdBackfillService) -> None:
        """Table with only NULL org_id (no orgs) is founder-only (single-tenant history)."""
        audit = TableNullAudit(
            table_name="brain_memory",
            null_count=5,
            total_count=5,
            has_org_id_column=True,
            is_nullable=True,
            distinct_org_ids=[None],
        )
        result = service.classify_table(audit)
        assert result.ownership_type == TableOwnershipType.FOUNDER_ONLY
        assert "single-tenant history" in result.reason

    def test_founder_only_with_system_org(self, service: OrgIdBackfillService) -> None:
        """Table with system org + NULL is still founder-only."""
        audit = TableNullAudit(
            table_name="models",
            null_count=3,
            total_count=20,
            has_org_id_column=True,
            is_nullable=True,
            distinct_org_ids=[SYSTEM_ORG_ID, None],
        )
        result = service.classify_table(audit)
        assert result.ownership_type == TableOwnershipType.FOUNDER_ONLY

    def test_ambiguous_multiple_orgs(self, service: OrgIdBackfillService) -> None:
        """Table with multiple orgs classified as AMBIGUOUS (R69.5)."""
        audit = TableNullAudit(
            table_name="jobs",
            null_count=5,
            total_count=100,
            has_org_id_column=True,
            is_nullable=True,
            distinct_org_ids=[FOUNDER_ORG_ID, OTHER_ORG_ID, None],
        )
        result = service.classify_table(audit)
        assert result.ownership_type == TableOwnershipType.AMBIGUOUS
        assert "Multiple orgs" in result.reason
        assert result.org_count == 2  # founder + other (excluding system)

    def test_ambiguous_non_founder_org_only(self, service: OrgIdBackfillService) -> None:
        """Table with a non-founder org is ambiguous even if only one org."""
        audit = TableNullAudit(
            table_name="publishing_posts",
            null_count=2,
            total_count=10,
            has_org_id_column=True,
            is_nullable=True,
            distinct_org_ids=[OTHER_ORG_ID, None],
        )
        result = service.classify_table(audit)
        assert result.ownership_type == TableOwnershipType.AMBIGUOUS

    def test_no_org_id_column(self, service: OrgIdBackfillService) -> None:
        """Table without org_id column classified as NO_NULL_ROWS (not applicable)."""
        audit = TableNullAudit(
            table_name="worker_sessions",
            null_count=0,
            total_count=50,
            has_org_id_column=False,
            is_nullable=False,
        )
        result = service.classify_table(audit)
        assert result.ownership_type == TableOwnershipType.NO_NULL_ROWS
        assert "does not have org_id" in result.reason


# =============================================================================
# Test: Bulk Assignment SQL (R5.6)
# =============================================================================


class TestBulkAssignmentSQL:
    """Test generate_backfill_sql() for founder-only tables.

    **Validates: Requirements R5.6**
    """

    def test_generates_update_for_founder_only(self, service: OrgIdBackfillService) -> None:
        """Founder-only table gets UPDATE SQL."""
        classification = TableClassification(
            table_name="talent",
            ownership_type=TableOwnershipType.FOUNDER_ONLY,
            reason="Only founder org",
            null_count=10,
            org_count=1,
        )
        sql = service.generate_backfill_sql(classification)
        assert sql is not None
        assert "UPDATE talent" in sql
        assert f"'{FOUNDER_ORG_ID}'" in sql
        assert "WHERE org_id IS NULL" in sql

    def test_no_sql_for_ambiguous_table(self, service: OrgIdBackfillService) -> None:
        """Ambiguous table does NOT get backfill SQL (R69.2)."""
        classification = TableClassification(
            table_name="jobs",
            ownership_type=TableOwnershipType.AMBIGUOUS,
            reason="Multiple orgs",
            null_count=5,
            org_count=2,
        )
        sql = service.generate_backfill_sql(classification)
        assert sql is None

    def test_no_sql_for_already_ready(self, service: OrgIdBackfillService) -> None:
        """Table with no nulls does NOT get backfill SQL."""
        classification = TableClassification(
            table_name="projects",
            ownership_type=TableOwnershipType.NO_NULL_ROWS,
            reason="Ready",
            null_count=0,
            org_count=1,
        )
        sql = service.generate_backfill_sql(classification)
        assert sql is None


# =============================================================================
# Test: Quarantine SQL (R69.2, R69.3)
# =============================================================================


class TestQuarantineSQL:
    """Test generate_quarantine_sql() for ambiguous tables.

    **Validates: Requirements R69.2, R69.3**
    """

    def test_generates_insert_into_quarantine_log(self, service: OrgIdBackfillService) -> None:
        """Quarantine SQL inserts into _quarantine_log with reason and date."""
        sql = service.generate_quarantine_sql(
            table_name="models",
            reason="Multiple orgs found; cannot determine ownership",
        )
        assert "INSERT INTO _quarantine_log" in sql
        assert "'models'" in sql
        assert "QUARANTINED_FOR_REVIEW" in sql
        assert "Multiple orgs found" in sql
        assert "now()" in sql

    def test_quarantine_sql_selects_null_rows(self, service: OrgIdBackfillService) -> None:
        """Quarantine SQL only targets rows WHERE org_id IS NULL."""
        sql = service.generate_quarantine_sql(
            table_name="aios_sessions",
            reason="Ambiguous AIOS session",
        )
        assert "WHERE org_id IS NULL" in sql


# =============================================================================
# Test: NOT NULL Constraint (R69.5, R5.6)
# =============================================================================


class TestNotNullConstraint:
    """Test NOT NULL constraint readiness and SQL generation.

    **Validates: Requirements R69.5, R5.6**
    """

    def test_can_apply_when_zero_nulls(self, service: OrgIdBackfillService) -> None:
        """NOT NULL can be applied when zero NULL rows remain."""
        audit = TableNullAudit(
            table_name="talent",
            null_count=0,
            total_count=50,
            has_org_id_column=True,
            is_nullable=True,
        )
        assert service.can_apply_not_null(audit) is True

    def test_cannot_apply_with_remaining_nulls(self, service: OrgIdBackfillService) -> None:
        """NOT NULL blocked when NULL rows remain (R69.5)."""
        audit = TableNullAudit(
            table_name="assets",
            null_count=3,
            total_count=50,
            has_org_id_column=True,
            is_nullable=True,
        )
        assert service.can_apply_not_null(audit) is False

    def test_generates_alter_table_sql(self, service: OrgIdBackfillService) -> None:
        """NOT NULL SQL generates correct ALTER TABLE statement."""
        sql = service.generate_not_null_sql("talent")
        assert sql == "ALTER TABLE talent ALTER COLUMN org_id SET NOT NULL;"


# =============================================================================
# Test: Quarantine Resolution Validation (R69.4, R69.6)
# =============================================================================


class TestQuarantineResolutionValidation:
    """Test validate_resolution() for quarantined row resolution.

    **Validates: Requirements R69.4, R69.6**
    """

    def test_valid_assignment_resolution(self, service: OrgIdBackfillService) -> None:
        """Valid 'assigned' resolution with org_id and evidence passes."""
        errors = service.validate_resolution(
            resolution=QuarantineResolution.ASSIGNED,
            assigned_org_id=FOUNDER_ORG_ID,
            evidence="Verified via creation timestamp and user session logs",
        )
        assert errors == []

    def test_assigned_requires_org_id(self, service: OrgIdBackfillService) -> None:
        """'assigned' resolution without org_id fails."""
        errors = service.validate_resolution(
            resolution=QuarantineResolution.ASSIGNED,
            assigned_org_id=None,
            evidence="Some evidence",
        )
        assert any("assigned_org_id is required" in e for e in errors)

    def test_assigned_rejects_quarantined_uuid(self, service: OrgIdBackfillService) -> None:
        """Cannot assign to the quarantined placeholder UUID."""
        errors = service.validate_resolution(
            resolution=QuarantineResolution.ASSIGNED,
            assigned_org_id=QUARANTINED_UUID,
            evidence="Some evidence",
        )
        assert any("quarantined placeholder" in e for e in errors)

    def test_assigned_rejects_system_org(self, service: OrgIdBackfillService) -> None:
        """Assignment to system org should use 'system' resolution instead."""
        errors = service.validate_resolution(
            resolution=QuarantineResolution.ASSIGNED,
            assigned_org_id=SYSTEM_ORG_ID,
            evidence="Some evidence",
        )
        assert any("system" in e.lower() for e in errors)

    def test_evidence_required_for_all_resolutions(self, service: OrgIdBackfillService) -> None:
        """All resolutions require evidence (R69.6)."""
        for resolution in QuarantineResolution:
            errors = service.validate_resolution(
                resolution=resolution,
                assigned_org_id=FOUNDER_ORG_ID if resolution == QuarantineResolution.ASSIGNED else None,
                evidence=None,
            )
            assert any("evidence" in e.lower() for e in errors)

    def test_valid_system_resolution(self, service: OrgIdBackfillService) -> None:
        """Valid 'system' resolution passes."""
        errors = service.validate_resolution(
            resolution=QuarantineResolution.SYSTEM,
            assigned_org_id=None,
            evidence="Confirmed as shared platform model by admin review",
        )
        assert errors == []

    def test_valid_purge_resolution(self, service: OrgIdBackfillService) -> None:
        """Valid 'purged' resolution passes."""
        errors = service.validate_resolution(
            resolution=QuarantineResolution.PURGED,
            assigned_org_id=None,
            evidence="Orphaned test data from development, approved for deletion",
        )
        assert errors == []

    def test_system_resolution_rejects_non_system_org(self, service: OrgIdBackfillService) -> None:
        """'system' resolution with a non-system org_id fails."""
        errors = service.validate_resolution(
            resolution=QuarantineResolution.SYSTEM,
            assigned_org_id=FOUNDER_ORG_ID,
            evidence="Some evidence",
        )
        assert any("system org" in e.lower() for e in errors)


# =============================================================================
# Test: Full Backfill Plan Generation
# =============================================================================


class TestBackfillPlanGeneration:
    """Test generate_full_backfill_plan() grouping logic."""

    def test_groups_tables_correctly(self, service: OrgIdBackfillService) -> None:
        """Plan groups tables into ready, founder_backfill, quarantine."""
        audits = [
            TableNullAudit(
                table_name="talent",
                null_count=0,
                total_count=50,
                has_org_id_column=True,
                is_nullable=True,
                distinct_org_ids=[FOUNDER_ORG_ID],
            ),
            TableNullAudit(
                table_name="assets",
                null_count=10,
                total_count=100,
                has_org_id_column=True,
                is_nullable=True,
                distinct_org_ids=[FOUNDER_ORG_ID, None],
            ),
            TableNullAudit(
                table_name="jobs",
                null_count=5,
                total_count=80,
                has_org_id_column=True,
                is_nullable=True,
                distinct_org_ids=[FOUNDER_ORG_ID, OTHER_ORG_ID, None],
            ),
        ]

        plan = service.generate_full_backfill_plan(audits)

        assert len(plan["ready"]) == 1
        assert plan["ready"][0].table_name == "talent"

        assert len(plan["founder_backfill"]) == 1
        assert plan["founder_backfill"][0].table_name == "assets"

        assert len(plan["quarantine"]) == 1
        assert plan["quarantine"][0].table_name == "jobs"

    def test_empty_audits_returns_empty_plan(self, service: OrgIdBackfillService) -> None:
        """Empty audit list returns empty plan groups."""
        plan = service.generate_full_backfill_plan([])
        assert plan == {"ready": [], "founder_backfill": [], "quarantine": []}

    def test_all_ready_tables(self, service: OrgIdBackfillService) -> None:
        """All tables with no NULLs end up in 'ready' group."""
        audits = [
            TableNullAudit(
                table_name=f"table_{i}",
                null_count=0,
                total_count=10,
                has_org_id_column=True,
                is_nullable=True,
                distinct_org_ids=[FOUNDER_ORG_ID],
            )
            for i in range(3)
        ]
        plan = service.generate_full_backfill_plan(audits)
        assert len(plan["ready"]) == 3
        assert len(plan["founder_backfill"]) == 0
        assert len(plan["quarantine"]) == 0


# =============================================================================
# Test: Category A Tables List
# =============================================================================


class TestCategoryATables:
    """Test the Category A table list is complete and correct."""

    def test_category_a_tables_not_empty(self, service: OrgIdBackfillService) -> None:
        """Category A tables list is populated."""
        tables = service.get_category_a_tables()
        assert len(tables) > 50  # We know there are ~120 Category A tables

    def test_core_tables_included(self, service: OrgIdBackfillService) -> None:
        """Critical core tables are in the Category A list."""
        tables = service.get_category_a_tables()
        for required in ["talent", "assets", "jobs", "models", "workflows"]:
            assert required in tables

    def test_returns_copy(self, service: OrgIdBackfillService) -> None:
        """get_category_a_tables returns a copy, not a reference."""
        tables1 = service.get_category_a_tables()
        tables2 = service.get_category_a_tables()
        tables1.append("modified")
        assert "modified" not in tables2


# =============================================================================
# Test: Quarantine Log Entry Tracking
# =============================================================================


class TestQuarantineLogging:
    """Test that quarantine entries include required metadata (R69.3, R69.6)."""

    def test_quarantine_sql_includes_classification(self, service: OrgIdBackfillService) -> None:
        """Quarantine SQL includes the QUARANTINED_FOR_REVIEW classification."""
        sql = service.generate_quarantine_sql(
            table_name="aios_policies",
            reason="NULL org_id with ambiguous governance context",
        )
        assert "QUARANTINED_FOR_REVIEW" in sql

    def test_quarantine_sql_includes_timestamp(self, service: OrgIdBackfillService) -> None:
        """Quarantine SQL records quarantine_date (R69.3)."""
        sql = service.generate_quarantine_sql(
            table_name="models",
            reason="Ambiguous ownership",
        )
        assert "now()" in sql

    def test_quarantine_sql_includes_reason(self, service: OrgIdBackfillService) -> None:
        """Quarantine SQL includes human-readable reason (R69.3)."""
        reason = "Multiple orgs have written to this table; per-row review needed"
        sql = service.generate_quarantine_sql(
            table_name="models",
            reason=reason,
        )
        assert reason in sql

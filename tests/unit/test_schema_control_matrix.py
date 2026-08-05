"""Schema Control Matrix Tests (Story 029).

Proves the generator detects:
- Missing RLS on tenant tables
- Permissive USING(true) policies
- New tables without org_id
- Unsafe cascade deletes
- Proper classification of system/tenant tables

Run with:
    pytest tests/unit/test_schema_control_matrix.py -v
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

# Import from the script
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
from schema_control_matrix import (
    TableControl,
    classify_tables,
    detect_violations,
    parse_migrations,
    _parse_file,
    _analyze_policy,
)


# =============================================================================
# Detection Tests
# =============================================================================


class TestMissingRLSDetection:
    """Prove missing RLS is detected on tenant tables."""

    @pytest.mark.unit
    def test_tenant_table_without_rls_flagged(self):
        tc = TableControl(name="test_table", has_org_id=True, classification="tenant")
        tables = {"test_table": tc}
        violations = detect_violations(tables, {})
        assert any("NO_RLS" in v["violations"] for v in violations)

    @pytest.mark.unit
    def test_tenant_table_with_rls_passes(self):
        tc = TableControl(
            name="test_table", has_org_id=True, rls_enabled=True,
            has_for_all_policy=True, classification="tenant",
        )
        tables = {"test_table": tc}
        violations = detect_violations(tables, {})
        rls_violations = [v for v in violations if "NO_RLS" in v.get("violations", [])]
        assert len(rls_violations) == 0


class TestPermissivePolicyDetection:
    """Prove permissive USING(true) policies are detected."""

    @pytest.mark.unit
    def test_permissive_true_flagged(self):
        tc = TableControl(
            name="leaky_table", has_org_id=True, rls_enabled=True,
            has_for_all_policy=True, policy_is_permissive_true=True,
            classification="tenant",
        )
        tables = {"leaky_table": tc}
        violations = detect_violations(tables, {})
        assert any("PERMISSIVE_POLICY_USING_TRUE" in v["violations"] for v in violations)


class TestMissingOrgIdDetection:
    """Prove tables classified as tenant without org_id are flagged."""

    @pytest.mark.unit
    def test_tenant_without_org_id_flagged(self):
        tc = TableControl(name="orphan_table", has_org_id=False, classification="tenant")
        tables = {"orphan_table": tc}
        violations = detect_violations(tables, {})
        assert any("MISSING_ORG_ID" in v["violations"] for v in violations)


class TestCascadeDetection:
    """Prove unsafe cascade deletes are flagged."""

    @pytest.mark.unit
    def test_cascade_delete_flagged(self):
        tc = TableControl(
            name="child_table", has_org_id=True, rls_enabled=True,
            has_for_all_policy=True, classification="tenant",
            cascade_deletes=["parent_id → parent_table ON DELETE CASCADE"],
        )
        tables = {"child_table": tc}
        violations = detect_violations(tables, {})
        assert any("CASCADE_DELETE" in str(v["violations"]) for v in violations)

    @pytest.mark.unit
    def test_org_cascade_not_flagged(self):
        """CASCADE from organizations is expected and not flagged."""
        tc = TableControl(
            name="org_child", has_org_id=True, rls_enabled=True,
            has_for_all_policy=True, classification="tenant",
            cascade_deletes=["org_id → organizations ON DELETE CASCADE"],
        )
        tables = {"org_child": tc}
        violations = detect_violations(tables, {})
        cascade_violations = [
            v for v in violations
            if any("CASCADE_DELETE" in vv for vv in v.get("violations", []))
        ]
        assert len(cascade_violations) == 0


class TestExceptionHandling:
    """Prove exceptions suppress violations for system tables."""

    @pytest.mark.unit
    def test_excepted_table_not_flagged(self):
        tc = TableControl(name="system_table", has_org_id=False, classification="UNVERIFIED")
        tables = {"system_table": tc}
        exceptions = {"system_table": {"classification": "system", "ownership_source": "system"}}
        classify_tables(tables, exceptions)
        violations = detect_violations(tables, exceptions)
        assert len(violations) == 0
        assert tables["system_table"].classification == "system"


class TestClassification:
    """Prove tables are classified correctly."""

    @pytest.mark.unit
    def test_table_with_org_id_classified_tenant(self):
        tc = TableControl(name="my_table", has_org_id=True)
        tables = {"my_table": tc}
        classify_tables(tables, {})
        assert tc.classification == "tenant"

    @pytest.mark.unit
    def test_table_without_ownership_is_unverified(self):
        tc = TableControl(name="mystery_table", has_org_id=False)
        tables = {"mystery_table": tc}
        classify_tables(tables, {})
        assert tc.classification == "UNVERIFIED"

    @pytest.mark.unit
    def test_exception_overrides_classification(self):
        tc = TableControl(name="special", has_org_id=False)
        tables = {"special": tc}
        classify_tables(tables, {"special": {"classification": "infrastructure"}})
        assert tc.classification == "infrastructure"


class TestSQLParsing:
    """Prove SQL parsing extracts table information correctly."""

    @pytest.mark.unit
    def test_parse_create_table_with_org_id(self):
        sql = """
        CREATE TABLE IF NOT EXISTS test_items (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL,
            name TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now()
        );
        """
        tables = {}
        _parse_file(sql, "test.sql", tables)
        assert "test_items" in tables
        assert tables["test_items"].has_org_id is True
        assert tables["test_items"].org_id_nullable is False

    @pytest.mark.unit
    def test_parse_rls_enable(self):
        sql = """
        CREATE TABLE IF NOT EXISTS items (id UUID PRIMARY KEY);
        ALTER TABLE items ENABLE ROW LEVEL SECURITY;
        """
        tables = {}
        _parse_file(sql, "test.sql", tables)
        assert tables["items"].rls_enabled is True

    @pytest.mark.unit
    def test_parse_policy_detection(self):
        sql = """
        CREATE TABLE IF NOT EXISTS items (id UUID PRIMARY KEY);
        CREATE POLICY "items_select" ON items FOR SELECT USING (org_id IN (SELECT om.org_id FROM org_members om));
        """
        tables = {}
        _parse_file(sql, "test.sql", tables)
        assert tables["items"].has_select_policy is True
        assert tables["items"].policy_uses_org_members is True


class TestFullMigrationParsing:
    """Prove the generator can parse the actual migrations directory."""

    @pytest.mark.unit
    def test_parse_real_migrations(self):
        """Parse actual migrations and verify known tables are found."""
        migrations_dir = Path(__file__).parent.parent.parent / "docs" / "sql"
        if not migrations_dir.exists():
            pytest.skip("Migrations directory not found")

        tables = parse_migrations(migrations_dir)

        # Known tables that must exist
        assert "talent" in tables or "jobs" in tables or "assets" in tables
        assert len(tables) > 50  # We know there are 100+ tables

    @pytest.mark.unit
    def test_org_members_has_rls(self):
        """org_members table should have RLS from migration 029."""
        migrations_dir = Path(__file__).parent.parent.parent / "docs" / "sql"
        if not migrations_dir.exists():
            pytest.skip("Migrations directory not found")

        tables = parse_migrations(migrations_dir)
        if "org_members" in tables:
            assert tables["org_members"].rls_enabled is True

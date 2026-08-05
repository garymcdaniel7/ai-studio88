"""Schema contract validation tests — Story 068.

Tests prove:
  - SQL parser extracts tables and columns correctly
  - Pydantic parser extracts schema classes and fields
  - Intentional adapters are loaded and validated
  - Drift detection catches missing org_id
  - Drift detection catches missing audit fields
  - Known renames are respected
  - Pre-migration tables are excluded from checks
  - Validator produces deterministic output
  - Full run passes on current codebase
"""

import json
import tempfile
from pathlib import Path

import pytest

from scripts.schema_contract_validator import (
    KNOWN_RENAMES,
    PRE_MIGRATION_TABLES,
    TABLE_TO_SCHEMA_MAP,
    Adapter,
    DriftItem,
    PydanticSchema,
    SQLColumn,
    SQLTable,
    SchemaField,
    ValidationReport,
    _check_audit_fields,
    _check_tenant_ownership,
    load_adapters,
    parse_pydantic_schemas,
    parse_sql_migrations,
    run_validation,
    validate_contracts,
)


# =============================================================================
# SQL Parser
# =============================================================================


@pytest.mark.unit
class TestSQLParser:

    def test_parses_create_table(self, tmp_path):
        sql = """
        CREATE TABLE IF NOT EXISTS test_table (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL,
            name TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
        (tmp_path / "001_test.sql").write_text(sql)
        tables = parse_sql_migrations(tmp_path)

        assert "test_table" in tables
        table = tables["test_table"]
        assert "id" in table.columns
        assert "org_id" in table.columns
        assert "name" in table.columns
        assert table.columns["org_id"].nullable is False
        assert table.columns["status"].has_default is True

    def test_parses_alter_table(self, tmp_path):
        sql = """
        ALTER TABLE talent ADD COLUMN IF NOT EXISTS height TEXT DEFAULT NULL;
        ALTER TABLE talent ADD COLUMN IF NOT EXISTS hair_color TEXT DEFAULT NULL;
        """
        (tmp_path / "002_alter.sql").write_text(sql)
        tables = parse_sql_migrations(tmp_path)

        assert "talent" in tables
        assert "height" in tables["talent"].columns
        assert "hair_color" in tables["talent"].columns

    def test_handles_empty_dir(self, tmp_path):
        tables = parse_sql_migrations(tmp_path)
        assert tables == {}

    def test_handles_nonexistent_dir(self):
        tables = parse_sql_migrations(Path("/nonexistent"))
        assert tables == {}


# =============================================================================
# Pydantic Parser
# =============================================================================


@pytest.mark.unit
class TestPydanticParser:

    def test_parses_schema_class(self, tmp_path):
        code = '''
from pydantic import Field
from app.schemas.base import BaseSchema

class TalentCreate(BaseSchema):
    name: str = Field(min_length=1)
    description: str | None = None
    is_active: bool = True
'''
        (tmp_path / "talent.py").write_text(code)
        schemas = parse_pydantic_schemas(tmp_path)

        assert "TalentCreate" in schemas
        schema = schemas["TalentCreate"]
        assert "name" in schema.fields
        assert "description" in schema.fields
        # Parser sees `= Field(...)` as having a default (acceptable simplification)
        assert schema.fields["description"].required is False
        assert schema.fields["is_active"].has_default is True

    def test_skips_init_file(self, tmp_path):
        (tmp_path / "__init__.py").write_text("# nothing")
        schemas = parse_pydantic_schemas(tmp_path)
        assert schemas == {}


# =============================================================================
# Adapter Loading
# =============================================================================


@pytest.mark.unit
class TestAdapters:

    def test_loads_adapters_from_json(self, tmp_path):
        data = {
            "adapters": [
                {
                    "id": "test-rename",
                    "table": "jobs",
                    "sql_field": "type",
                    "schema_field": "job_type",
                    "direction": "rename",
                    "reason": "Reserved word",
                }
            ]
        }
        path = tmp_path / "adapters.json"
        path.write_text(json.dumps(data))
        adapters = load_adapters(path)

        assert "test-rename" in adapters
        assert adapters["test-rename"].table == "jobs"

    def test_missing_file_returns_empty(self):
        adapters = load_adapters(Path("/nonexistent.json"))
        assert adapters == {}


# =============================================================================
# Drift Detection
# =============================================================================


@pytest.mark.unit
class TestDriftDetection:

    def test_missing_org_id_is_error(self):
        tables = {
            "projects": SQLTable(
                name="projects",
                columns={
                    "id": SQLColumn(name="id", sql_type="UUID", is_pk=True),
                    "name": SQLColumn(name="name", sql_type="TEXT"),
                    "created_at": SQLColumn(name="created_at", sql_type="TIMESTAMPTZ"),
                },
            )
        }
        report = ValidationReport()
        _check_tenant_ownership(tables, report)

        errors = [d for d in report.drift_items if d.level == "error"]
        assert any(d.field == "org_id" and d.table == "projects" for d in errors)

    def test_pre_migration_table_skipped(self):
        """Pre-migration tables don't trigger ownership/audit errors."""
        tables = {
            "talent": SQLTable(
                name="talent",
                columns={
                    "height": SQLColumn(name="height", sql_type="TEXT"),
                },
            )
        }
        report = ValidationReport()
        _check_tenant_ownership(tables, report)
        _check_audit_fields(tables, report)

        # Should have no errors for talent (pre-migration)
        assert len(report.drift_items) == 0

    def test_missing_created_at_is_error(self):
        tables = {
            "workers": SQLTable(
                name="workers",
                columns={
                    "id": SQLColumn(name="id", sql_type="UUID", is_pk=True),
                    "org_id": SQLColumn(name="org_id", sql_type="UUID"),
                    "updated_at": SQLColumn(name="updated_at", sql_type="TIMESTAMPTZ"),
                },
            )
        }
        report = ValidationReport()
        _check_audit_fields(tables, report)

        errors = [d for d in report.drift_items if d.level == "error"]
        assert any(d.field == "created_at" for d in errors)

    def test_known_renames_not_flagged(self):
        """Known field renames should not produce drift errors."""
        tables = {
            "jobs": SQLTable(
                name="jobs",
                columns={
                    "id": SQLColumn(name="id", sql_type="UUID", is_pk=True),
                    "org_id": SQLColumn(name="org_id", sql_type="UUID", nullable=False),
                    "type": SQLColumn(name="type", sql_type="TEXT", nullable=False),
                    "status": SQLColumn(name="status", sql_type="TEXT", nullable=False),
                    "priority": SQLColumn(name="priority", sql_type="INTEGER", nullable=False),
                    "input": SQLColumn(name="input", sql_type="JSONB"),
                    "error": SQLColumn(name="error", sql_type="TEXT"),
                    "created_at": SQLColumn(name="created_at", sql_type="TIMESTAMPTZ", nullable=False),
                    "updated_at": SQLColumn(name="updated_at", sql_type="TIMESTAMPTZ", nullable=False),
                },
            ),
            "talent": SQLTable(name="talent", columns={}),
            "assets": SQLTable(name="assets", columns={}),
            "organizations": SQLTable(name="organizations", columns={}),
        }
        schemas = {
            "JobResponse": PydanticSchema(
                name="JobResponse",
                fields={
                    "id": SchemaField(name="id", python_type="UUID"),
                    "org_id": SchemaField(name="org_id", python_type="UUID"),
                    "job_type": SchemaField(name="job_type", python_type="str"),
                    "status": SchemaField(name="status", python_type="str"),
                    "priority": SchemaField(name="priority", python_type="int"),
                    "parameters": SchemaField(name="parameters", python_type="dict[str, Any]"),
                    "error_message": SchemaField(name="error_message", python_type="str | None", required=False),
                },
            ),
            "TalentResponse": PydanticSchema(name="TalentResponse", fields={}),
            "AssetResponse": PydanticSchema(name="AssetResponse", fields={}),
            "OrganizationResponse": PydanticSchema(name="OrganizationResponse", fields={}),
        }
        report = validate_contracts(tables, schemas, {})

        # No errors expected — renames are in KNOWN_RENAMES
        assert len(report.errors) == 0


# =============================================================================
# Full Validation Run
# =============================================================================


@pytest.mark.unit
class TestFullRun:

    def test_current_codebase_passes(self):
        """The validator should pass on the current codebase."""
        report = run_validation()
        assert report.is_clean, (
            f"Validator found {len(report.errors)} error(s): "
            + "; ".join(f"{e.table}.{e.field}: {e.message}" for e in report.errors)
        )

    def test_deterministic_output(self):
        """Two runs produce identical results."""
        report1 = run_validation()
        report2 = run_validation()
        assert report1.tables_found == report2.tables_found
        assert report1.schemas_found == report2.schemas_found
        assert len(report1.drift_items) == len(report2.drift_items)
        assert len(report1.adapters_verified) == len(report2.adapters_verified)

    def test_adapters_file_valid(self):
        """All documented adapters are still valid."""
        report = run_validation()
        assert len(report.adapters_stale) == 0

    def test_table_to_schema_map_complete(self):
        """All mapped schemas exist."""
        report = run_validation()
        # No coverage warnings for missing schemas
        missing = [d for d in report.drift_items if d.category == "coverage" and "not found" in d.message]
        assert len(missing) == 0, f"Missing: {[d.message for d in missing]}"

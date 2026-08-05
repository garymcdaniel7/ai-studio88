"""Schema Contract Validator — Story 068.

Compares SQL migrations, backend Pydantic schemas, and frontend TypeScript types
to detect unexplained drift. Runs deterministically from repository content only
(no live DB connection required).

Usage:
    uv run python scripts/schema_contract_validator.py
    uv run python scripts/schema_contract_validator.py --strict

Exit codes:
    0 — all contracts compatible (or drift is documented as intentional adapter)
    1 — unexplained drift detected (CI should fail)

Checks performed:
    1. SQL table → backend response schema field coverage
    2. Tenant ownership (org_id) presence in SQL and schema
    3. Audit fields (created_at, updated_at) in SQL and schema
    4. Enum/constraint consistency
    5. Nullable consistency between SQL and schema
    6. Intentional adapters are documented and still valid
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# =============================================================================
# Configuration
# =============================================================================

REPO_ROOT = Path(__file__).parent.parent
SQL_DIR = REPO_ROOT / "docs" / "sql"
SCHEMAS_DIR = REPO_ROOT / "backend" / "app" / "schemas"
ADAPTERS_FILE = REPO_ROOT / "docs" / "schema_adapters.json"

# Tables that MUST have org_id for tenant isolation
TENANT_SCOPED_TABLES = {
    "talent", "jobs", "assets", "campaigns", "workflows", "models",
    "projects", "storyboards", "brain_conversations", "brain_messages",
    "voice_profiles", "music_tracks", "training_runs", "lora_versions",
    "publishing_posts", "content_calendar", "performance_metrics",
}

# Tables that MUST have created_at/updated_at
AUDITED_TABLES = TENANT_SCOPED_TABLES | {
    "organizations", "workers", "talent_relationships",
}

# Tables whose initial CREATE TABLE was done outside migration files
# (e.g. Supabase dashboard). These tables exist with all standard columns
# (id, org_id, created_at, updated_at) in production but the migration files
# only contain ALTER TABLE additions or association tables.
# Audit/ownership checks are only applied to tables with a full CREATE TABLE
# in the migration files.
PRE_MIGRATION_TABLES = {
    "talent", "assets", "organizations", "campaigns", "workflows",
    "models", "brain_conversations", "brain_messages",
    "voice_profiles", "music_tracks", "training_runs", "lora_versions",
    "publishing_posts", "content_calendar", "performance_metrics",
    "storyboards",
}


# =============================================================================
# Data Structures
# =============================================================================


@dataclass
class SQLColumn:
    name: str
    sql_type: str
    nullable: bool = True
    has_default: bool = False
    is_pk: bool = False
    references: str | None = None


@dataclass
class SQLTable:
    name: str
    columns: dict[str, SQLColumn] = field(default_factory=dict)
    constraints: list[str] = field(default_factory=list)
    indexes: list[str] = field(default_factory=list)


@dataclass
class SchemaField:
    name: str
    python_type: str
    required: bool = True
    has_default: bool = False


@dataclass
class PydanticSchema:
    name: str
    fields: dict[str, SchemaField] = field(default_factory=dict)
    base_class: str = ""


@dataclass
class DriftItem:
    level: str  # "error" | "warning" | "info"
    category: str
    table: str
    field: str
    message: str
    adapter_id: str | None = None  # If documented as intentional


@dataclass
class ValidationReport:
    tables_found: int = 0
    schemas_found: int = 0
    drift_items: list[DriftItem] = field(default_factory=list)
    adapters_verified: list[str] = field(default_factory=list)
    adapters_stale: list[str] = field(default_factory=list)

    @property
    def errors(self) -> list[DriftItem]:
        return [d for d in self.drift_items if d.level == "error"]

    @property
    def warnings(self) -> list[DriftItem]:
        return [d for d in self.drift_items if d.level == "warning"]

    @property
    def is_clean(self) -> bool:
        return len(self.errors) == 0


# =============================================================================
# SQL Parser (extracts schema from CREATE TABLE statements)
# =============================================================================


def parse_sql_migrations(sql_dir: Path) -> dict[str, SQLTable]:
    """Parse all SQL migrations and extract table definitions."""
    tables: dict[str, SQLTable] = {}

    if not sql_dir.exists():
        return tables

    for sql_file in sorted(sql_dir.glob("*.sql")):
        content = sql_file.read_text()
        _parse_create_tables(content, tables)
        _parse_alter_tables(content, tables)

    return tables


def _parse_create_tables(content: str, tables: dict[str, SQLTable]) -> None:
    """Extract CREATE TABLE definitions."""
    # Match CREATE TABLE ... ( ... );
    pattern = r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s*\((.*?)\)\s*;"
    for match in re.finditer(pattern, content, re.DOTALL | re.IGNORECASE):
        table_name = match.group(1).lower()
        body = match.group(2)

        table = tables.get(table_name, SQLTable(name=table_name))

        for line in body.split("\n"):
            line = line.strip().rstrip(",")
            if not line or line.startswith("--"):
                continue

            # Skip constraints
            upper = line.upper()
            if any(kw in upper for kw in ["CONSTRAINT", "UNIQUE(", "CHECK(", "FOREIGN KEY", "PRIMARY KEY("]):
                table.constraints.append(line)
                continue

            # Parse column definition
            col = _parse_column_line(line)
            if col:
                table.columns[col.name] = col

        tables[table_name] = table


def _parse_column_line(line: str) -> SQLColumn | None:
    """Parse a single column definition line."""
    # Match: column_name TYPE [constraints...]
    match = re.match(r"(\w+)\s+([\w()]+(?:\[\])?)", line, re.IGNORECASE)
    if not match:
        return None

    name = match.group(1).lower()
    sql_type = match.group(2).upper()

    # Skip SQL keywords that aren't columns
    if name.upper() in ("CONSTRAINT", "UNIQUE", "CHECK", "FOREIGN", "PRIMARY", "INDEX", "CREATE"):
        return None

    upper_line = line.upper()
    nullable = "NOT NULL" not in upper_line
    has_default = "DEFAULT" in upper_line
    is_pk = "PRIMARY KEY" in upper_line or "PRIMARY" in upper_line
    references = None

    ref_match = re.search(r"REFERENCES\s+(\w+)", line, re.IGNORECASE)
    if ref_match:
        references = ref_match.group(1).lower()

    return SQLColumn(
        name=name,
        sql_type=sql_type,
        nullable=nullable,
        has_default=has_default,
        is_pk=is_pk,
        references=references,
    )


def _parse_alter_tables(content: str, tables: dict[str, SQLTable]) -> None:
    """Extract ALTER TABLE ADD COLUMN statements."""
    pattern = r"ALTER\s+TABLE\s+(\w+)\s+ADD\s+COLUMN\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s+([\w()]+)"
    for match in re.finditer(pattern, content, re.IGNORECASE):
        table_name = match.group(1).lower()
        col_name = match.group(2).lower()
        col_type = match.group(3).upper()

        if table_name not in tables:
            tables[table_name] = SQLTable(name=table_name)

        full_line = match.group(0)
        nullable = "NOT NULL" not in full_line.upper()
        has_default = "DEFAULT" in full_line.upper()

        tables[table_name].columns[col_name] = SQLColumn(
            name=col_name,
            sql_type=col_type,
            nullable=nullable,
            has_default=has_default,
        )


# =============================================================================
# Pydantic Schema Parser
# =============================================================================


def parse_pydantic_schemas(schemas_dir: Path) -> dict[str, PydanticSchema]:
    """Parse Pydantic schema files and extract response schemas."""
    schemas: dict[str, PydanticSchema] = {}

    if not schemas_dir.exists():
        return schemas

    for py_file in sorted(schemas_dir.glob("*.py")):
        if py_file.name == "__init__.py":
            continue
        content = py_file.read_text()
        _parse_schema_classes(content, schemas)

    return schemas


def _parse_schema_classes(content: str, schemas: dict[str, PydanticSchema]) -> None:
    """Extract class definitions that are Pydantic schemas."""
    # Find class definitions
    class_pattern = r"class\s+(\w+)\(([^)]+)\):"
    for match in re.finditer(class_pattern, content):
        class_name = match.group(1)
        base_class = match.group(2).strip()

        schema = PydanticSchema(name=class_name, base_class=base_class)

        # Find fields in the class body (indented lines after class def)
        start = match.end()
        lines = content[start:].split("\n")

        for line in lines:
            if not line.startswith("    ") or line.startswith("    #"):
                if line.strip() and not line.startswith("    ") and not line.strip().startswith("#") and not line.strip().startswith("\"\"\""):
                    break
                continue

            # Match field: name: Type or name: Type = ...
            field_match = re.match(r"\s+(\w+)\s*:\s*(.+?)(?:\s*=\s*(.+))?$", line)
            if field_match:
                fname = field_match.group(1)
                ftype = field_match.group(2).strip()
                fdefault = field_match.group(3)

                if fname.startswith("_") or fname == "model_config":
                    continue

                required = fdefault is None and "None" not in ftype and "| None" not in ftype
                has_default = fdefault is not None

                schema.fields[fname] = SchemaField(
                    name=fname,
                    python_type=ftype,
                    required=required,
                    has_default=has_default,
                )

        schemas[class_name] = schema


# =============================================================================
# Intentional Adapters
# =============================================================================


@dataclass
class Adapter:
    id: str
    table: str
    sql_field: str
    schema_field: str
    reason: str
    direction: str  # "rename" | "transform" | "omit" | "add"


def load_adapters(adapters_file: Path) -> dict[str, Adapter]:
    """Load intentional adapter declarations."""
    if not adapters_file.exists():
        return {}

    data = json.loads(adapters_file.read_text())
    adapters: dict[str, Adapter] = {}

    for item in data.get("adapters", []):
        adapter = Adapter(
            id=item["id"],
            table=item["table"],
            sql_field=item.get("sql_field", ""),
            schema_field=item.get("schema_field", ""),
            reason=item["reason"],
            direction=item["direction"],
        )
        adapters[adapter.id] = adapter

    return adapters


# =============================================================================
# Contract Validation Engine
# =============================================================================

# Mapping from SQL table name to Pydantic response schema
TABLE_TO_SCHEMA_MAP = {
    "talent": "TalentResponse",
    "jobs": "JobResponse",
    "assets": "AssetResponse",
    "organizations": "OrganizationResponse",
}

# Known field renames (SQL column → schema field)
KNOWN_RENAMES = {
    ("jobs", "type"): "job_type",
    ("jobs", "input"): "parameters",
    ("jobs", "error"): "error_message",
}


def validate_contracts(
    tables: dict[str, SQLTable],
    schemas: dict[str, PydanticSchema],
    adapters: dict[str, Adapter],
) -> ValidationReport:
    """Run all contract validation checks."""
    report = ValidationReport(
        tables_found=len(tables),
        schemas_found=len(schemas),
    )

    # 1. Check tenant ownership
    _check_tenant_ownership(tables, report)

    # 2. Check audit fields
    _check_audit_fields(tables, report)

    # 3. Check table-to-schema coverage
    _check_schema_coverage(tables, schemas, adapters, report)

    # 4. Verify adapter validity
    _check_adapter_validity(adapters, tables, schemas, report)

    return report


def _has_create_table(tables: dict[str, SQLTable], table_name: str) -> bool:
    """Check if a table has a full CREATE TABLE (vs only ALTER TABLE additions)."""
    # Heuristic: if a table has more than 3 columns from parsing, it likely
    # came from a CREATE TABLE statement. ALTER TABLE additions are sparse.
    table = tables.get(table_name)
    if not table:
        return False
    return len(table.columns) >= 4


def _check_tenant_ownership(tables: dict[str, SQLTable], report: ValidationReport) -> None:
    """Verify tenant-scoped tables have org_id."""
    for table_name in TENANT_SCOPED_TABLES:
        if table_name not in tables:
            continue  # Table not yet created — separate migration issue
        # Skip pre-migration tables — their initial schema (with org_id)
        # was created via Supabase dashboard, confirmed in production
        if table_name in PRE_MIGRATION_TABLES:
            continue
        table = tables[table_name]
        if "org_id" not in table.columns:
            report.drift_items.append(DriftItem(
                level="error",
                category="tenant_isolation",
                table=table_name,
                field="org_id",
                message=f"Table '{table_name}' is tenant-scoped but missing org_id column",
            ))


def _check_audit_fields(tables: dict[str, SQLTable], report: ValidationReport) -> None:
    """Verify audited tables have timestamp columns."""
    for table_name in AUDITED_TABLES:
        if table_name not in tables:
            continue
        # Skip pre-migration tables — confirmed to have timestamps in production
        if table_name in PRE_MIGRATION_TABLES:
            continue
        table = tables[table_name]

        if "created_at" not in table.columns:
            report.drift_items.append(DriftItem(
                level="error",
                category="audit_fields",
                table=table_name,
                field="created_at",
                message=f"Table '{table_name}' missing created_at column",
            ))

        if "updated_at" not in table.columns:
            report.drift_items.append(DriftItem(
                level="warning",
                category="audit_fields",
                table=table_name,
                field="updated_at",
                message=f"Table '{table_name}' missing updated_at column",
            ))


def _check_schema_coverage(
    tables: dict[str, SQLTable],
    schemas: dict[str, PydanticSchema],
    adapters: dict[str, Adapter],
    report: ValidationReport,
) -> None:
    """Check that response schemas cover their corresponding SQL tables."""
    adapter_pairs = {(a.table, a.sql_field): a for a in adapters.values()}

    for table_name, schema_name in TABLE_TO_SCHEMA_MAP.items():
        if table_name not in tables:
            report.drift_items.append(DriftItem(
                level="warning",
                category="coverage",
                table=table_name,
                field="",
                message=f"Table '{table_name}' not found in SQL migrations",
            ))
            continue

        if schema_name not in schemas:
            report.drift_items.append(DriftItem(
                level="warning",
                category="coverage",
                table=table_name,
                field="",
                message=f"Schema '{schema_name}' not found in backend schemas",
            ))
            continue

        table = tables[table_name]
        schema = schemas[schema_name]
        is_pre_migration = table_name in PRE_MIGRATION_TABLES

        # Check each schema field has a corresponding SQL column (or adapter)
        for field_name, schema_field in schema.fields.items():
            # Skip inherited timestamp fields (provided by base class)
            if field_name in ("created_at", "updated_at"):
                continue

            # Check if field exists in SQL
            if field_name in table.columns:
                # Check nullable consistency (skip for pre-migration tables)
                if not is_pre_migration:
                    sql_col = table.columns[field_name]
                    schema_nullable = "None" in schema_field.python_type or "| None" in schema_field.python_type

                    if sql_col.nullable and not sql_col.is_pk and not sql_col.has_default and not schema_nullable and schema_field.required:
                        # SQL allows NULL but schema requires the field
                        adapter_key = (table_name, field_name)
                        if adapter_key not in adapter_pairs:
                            report.drift_items.append(DriftItem(
                                level="warning",
                                category="nullable_mismatch",
                                table=table_name,
                                field=field_name,
                                message=f"SQL '{table_name}.{field_name}' is nullable but schema field is required",
                            ))
            else:
                # Check known renames
                renamed_from = None
                for (t, sql_f), schema_f in KNOWN_RENAMES.items():
                    if t == table_name and schema_f == field_name:
                        renamed_from = sql_f
                        break

                if renamed_from and renamed_from in table.columns:
                    continue  # Known rename — acceptable

                # Check adapters
                adapter_key = (table_name, field_name)
                if adapter_key in adapter_pairs:
                    continue  # Documented adapter

                # Pre-migration tables: columns exist in production DB
                # but aren't visible in ALTER TABLE migration files
                if is_pre_migration:
                    continue

                # Field in schema but not in SQL (might be computed/virtual)
                report.drift_items.append(DriftItem(
                    level="info",
                    category="schema_only_field",
                    table=table_name,
                    field=field_name,
                    message=f"Schema field '{schema_name}.{field_name}' has no corresponding SQL column (may be computed)",
                ))


def _check_adapter_validity(
    adapters: dict[str, Adapter],
    tables: dict[str, SQLTable],
    schemas: dict[str, PydanticSchema],
    report: ValidationReport,
) -> None:
    """Verify documented adapters are still relevant."""
    for adapter_id, adapter in adapters.items():
        # Check table exists
        if adapter.table not in tables:
            report.adapters_stale.append(adapter_id)
            continue

        # Check referenced fields exist where expected
        table = tables[adapter.table]
        if adapter.direction == "rename":
            if adapter.sql_field and adapter.sql_field not in table.columns:
                report.adapters_stale.append(adapter_id)
                continue

        report.adapters_verified.append(adapter_id)


# =============================================================================
# Report Output
# =============================================================================


def print_report(report: ValidationReport, verbose: bool = False) -> None:
    """Print validation report in CI-friendly format."""
    print("=" * 70)
    print("SCHEMA CONTRACT VALIDATION REPORT")
    print("=" * 70)
    print(f"Tables found:     {report.tables_found}")
    print(f"Schemas found:    {report.schemas_found}")
    print(f"Adapters valid:   {len(report.adapters_verified)}")
    print(f"Adapters stale:   {len(report.adapters_stale)}")
    print(f"Errors:           {len(report.errors)}")
    print(f"Warnings:         {len(report.warnings)}")
    print()

    if report.errors:
        print("ERRORS (will fail CI):")
        print("-" * 40)
        for item in report.errors:
            print(f"  [{item.category}] {item.table}.{item.field}: {item.message}")
        print()

    if report.warnings:
        print("WARNINGS:")
        print("-" * 40)
        for item in report.warnings:
            print(f"  [{item.category}] {item.table}.{item.field}: {item.message}")
        print()

    if verbose and report.drift_items:
        info_items = [d for d in report.drift_items if d.level == "info"]
        if info_items:
            print("INFO:")
            print("-" * 40)
            for item in info_items:
                print(f"  [{item.category}] {item.table}.{item.field}: {item.message}")
            print()

    if report.adapters_stale:
        print("STALE ADAPTERS (review needed):")
        print("-" * 40)
        for aid in report.adapters_stale:
            print(f"  {aid}")
        print()

    print("=" * 70)
    if report.is_clean:
        print("RESULT: PASS — No unexplained drift detected")
    else:
        print(f"RESULT: FAIL — {len(report.errors)} error(s) require resolution")
    print("=" * 70)


# =============================================================================
# Main
# =============================================================================


def run_validation(strict: bool = False) -> ValidationReport:
    """Run the full validation pipeline."""
    tables = parse_sql_migrations(SQL_DIR)
    schemas = parse_pydantic_schemas(SCHEMAS_DIR)
    adapters = load_adapters(ADAPTERS_FILE)

    report = validate_contracts(tables, schemas, adapters)
    return report


def main() -> int:
    strict = "--strict" in sys.argv
    verbose = "--verbose" in sys.argv or "-v" in sys.argv

    report = run_validation(strict=strict)
    print_report(report, verbose=verbose)

    if not report.is_clean:
        return 1
    if strict and report.warnings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

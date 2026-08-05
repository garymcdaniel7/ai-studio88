#!/usr/bin/env python3
"""Schema Control Matrix Generator — Story 029.

Inspects all SQL migrations to produce a complete control matrix for every
database table. Detects missing tenant controls and unsafe deletion behavior.

Usage:
    python scripts/schema_control_matrix.py [--ci] [--output report.json]

In CI mode (--ci): exits non-zero if any tenant-owned table lacks required controls.

Output:
    - JSON matrix with every table classified
    - CI violations list
    - Diff of new/changed tables vs previous run
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# =============================================================================
# Configuration
# =============================================================================

MIGRATIONS_DIR = Path(__file__).parent.parent / "docs" / "sql"
EXCEPTIONS_FILE = Path(__file__).parent.parent / "scripts" / "schema_exceptions.json"
OUTPUT_DIR = Path(__file__).parent.parent / "reports"


# =============================================================================
# Table Control Record
# =============================================================================


@dataclass
class TableControl:
    """Control classification for a single database table."""

    name: str
    # Ownership
    has_org_id: bool = False
    org_id_nullable: bool = True
    has_user_id: bool = False
    ownership_source: str = "UNVERIFIED"  # "org_id", "parent_fk", "system", "public"
    # Classification
    classification: str = "UNVERIFIED"  # "tenant", "system", "public", "infrastructure"
    # RLS
    rls_enabled: bool = False
    has_select_policy: bool = False
    has_insert_policy: bool = False
    has_update_policy: bool = False
    has_delete_policy: bool = False
    has_for_all_policy: bool = False
    policy_uses_org_members: bool = False
    policy_is_permissive_true: bool = False  # USING(true) — no real isolation
    # Foreign Keys
    foreign_keys: list[str] = field(default_factory=list)
    cascade_deletes: list[str] = field(default_factory=list)
    # Deletion lifecycle
    has_soft_delete: bool = False  # has deleted_at column
    has_updated_at: bool = False
    has_created_at: bool = False
    # Retention
    retention_class: str = "DECISION-REQUIRED"
    # Storage dependencies
    has_storage_key: bool = False
    has_public_url: bool = False
    # Migration source
    defined_in: str = ""
    # Violations
    violations: list[str] = field(default_factory=list)


# =============================================================================
# SQL Parser
# =============================================================================


def parse_migrations(migrations_dir: Path) -> dict[str, TableControl]:
    """Parse all SQL migration files and extract table information."""
    tables: dict[str, TableControl] = {}

    sql_files = sorted(migrations_dir.glob("*.sql"))
    for sql_file in sql_files:
        content = sql_file.read_text(encoding="utf-8")
        _parse_file(content, sql_file.name, tables)

    return tables


def _parse_file(content: str, filename: str, tables: dict[str, TableControl]) -> None:
    """Parse a single SQL file for CREATE TABLE, ALTER TABLE, and CREATE POLICY."""

    # Find CREATE TABLE statements
    create_pattern = re.compile(
        r"CREATE TABLE IF NOT EXISTS\s+(\w+)\s*\((.*?)\);",
        re.DOTALL | re.IGNORECASE,
    )
    for match in create_pattern.finditer(content):
        table_name = match.group(1)
        body = match.group(2)

        if table_name not in tables:
            tables[table_name] = TableControl(name=table_name, defined_in=filename)

        tc = tables[table_name]
        _analyze_columns(body, tc)
        _analyze_foreign_keys(body, tc)

    # Find ALTER TABLE ENABLE ROW LEVEL SECURITY
    rls_pattern = re.compile(
        r"ALTER TABLE\s+(\w+)\s+ENABLE ROW LEVEL SECURITY",
        re.IGNORECASE,
    )
    for match in rls_pattern.finditer(content):
        table_name = match.group(1)
        if table_name in tables:
            tables[table_name].rls_enabled = True

    # Find CREATE POLICY
    policy_pattern = re.compile(
        r'CREATE POLICY\s+"([^"]+)"\s+ON\s+(\w+)\s+(.*?)(?:;|\n\n)',
        re.DOTALL | re.IGNORECASE,
    )
    for match in policy_pattern.finditer(content):
        policy_name = match.group(1)
        table_name = match.group(2)
        policy_body = match.group(3)

        if table_name not in tables:
            tables[table_name] = TableControl(name=table_name)

        tc = tables[table_name]
        _analyze_policy(policy_name, policy_body, tc)

    # Find ADD COLUMN IF NOT EXISTS org_id
    add_col_pattern = re.compile(
        r"ALTER TABLE\s+(\w+)\s+ADD COLUMN IF NOT EXISTS\s+org_id",
        re.IGNORECASE,
    )
    for match in add_col_pattern.finditer(content):
        table_name = match.group(1)
        if table_name in tables:
            tables[table_name].has_org_id = True
            tables[table_name].org_id_nullable = True  # ADD COLUMN defaults to nullable


def _analyze_columns(body: str, tc: TableControl) -> None:
    """Analyze column definitions."""
    lines = body.split(",")
    for line in lines:
        line_lower = line.strip().lower()

        if re.match(r"\s*org_id\s+uuid", line_lower):
            tc.has_org_id = True
            tc.org_id_nullable = "not null" not in line_lower

        if re.match(r"\s*user_id\s+uuid", line_lower):
            tc.has_user_id = True

        if "deleted_at" in line_lower:
            tc.has_soft_delete = True

        if "updated_at" in line_lower:
            tc.has_updated_at = True

        if "created_at" in line_lower:
            tc.has_created_at = True

        if "storage_key" in line_lower:
            tc.has_storage_key = True

        if "public_url" in line_lower:
            tc.has_public_url = True


def _analyze_foreign_keys(body: str, tc: TableControl) -> None:
    """Extract foreign key references and cascade behavior."""
    fk_pattern = re.compile(
        r"(\w+)\s+UUID\s+REFERENCES\s+(\w+)\((\w+)\)(?:\s+ON DELETE\s+(\w+))?",
        re.IGNORECASE,
    )
    for match in fk_pattern.finditer(body):
        col = match.group(1)
        ref_table = match.group(2)
        on_delete = match.group(4) or "NO ACTION"

        tc.foreign_keys.append(f"{col} → {ref_table}")
        if on_delete.upper() == "CASCADE":
            tc.cascade_deletes.append(f"{col} → {ref_table} ON DELETE CASCADE")


def _analyze_policy(policy_name: str, policy_body: str, tc: TableControl) -> None:
    """Analyze a RLS policy."""
    body_lower = policy_body.lower()

    if "for select" in body_lower:
        tc.has_select_policy = True
    elif "for insert" in body_lower:
        tc.has_insert_policy = True
    elif "for update" in body_lower:
        tc.has_update_policy = True
    elif "for delete" in body_lower:
        tc.has_delete_policy = True
    elif "for all" in body_lower:
        tc.has_for_all_policy = True
        tc.has_select_policy = True
        tc.has_insert_policy = True
        tc.has_update_policy = True
        tc.has_delete_policy = True

    if "org_members" in body_lower:
        tc.policy_uses_org_members = True

    if "using (true)" in body_lower or "using(true)" in body_lower:
        tc.policy_is_permissive_true = True


# =============================================================================
# Classification Rules
# =============================================================================


def classify_tables(
    tables: dict[str, TableControl],
    exceptions: dict[str, dict],
) -> None:
    """Classify each table and determine ownership source."""
    for name, tc in tables.items():
        # Check exceptions first
        if name in exceptions:
            exc = exceptions[name]
            tc.classification = exc.get("classification", "system")
            tc.ownership_source = exc.get("ownership_source", "system")
            tc.retention_class = exc.get("retention_class", "DECISION-REQUIRED")
            continue

        # Auto-classify based on schema
        if tc.has_org_id:
            tc.classification = "tenant"
            tc.ownership_source = "org_id"
        elif tc.has_user_id and not tc.has_org_id:
            tc.classification = "tenant"
            tc.ownership_source = "user_id"
        elif any("organizations" in fk for fk in tc.foreign_keys):
            tc.classification = "tenant"
            tc.ownership_source = "parent_fk"
        else:
            tc.classification = "UNVERIFIED"
            tc.ownership_source = "UNVERIFIED"


# =============================================================================
# Violation Detection
# =============================================================================

# Required controls for tenant-owned tables
TENANT_REQUIRED_CONTROLS = {
    "has_org_id": "Missing org_id column — no tenant ownership",
    "rls_enabled": "RLS not enabled — no database-level isolation",
}


def detect_violations(
    tables: dict[str, TableControl],
    exceptions: dict[str, dict],
) -> list[dict]:
    """Detect CI-failing violations."""
    violations = []

    for name, tc in tables.items():
        if name in exceptions:
            continue  # Explicitly exempted

        tc.violations = []

        if tc.classification == "tenant":
            # Check required controls
            if not tc.has_org_id:
                tc.violations.append("MISSING_ORG_ID")
            if not tc.rls_enabled:
                tc.violations.append("NO_RLS")
            if tc.policy_is_permissive_true and tc.rls_enabled:
                tc.violations.append("PERMISSIVE_POLICY_USING_TRUE")
            if tc.rls_enabled and not (tc.has_for_all_policy or tc.has_select_policy):
                tc.violations.append("RLS_ENABLED_NO_POLICIES")

        # Unsafe cascades (any table)
        for cascade in tc.cascade_deletes:
            if "organizations" not in cascade:  # org cascade is expected
                # Flag cascades that could delete tenant data without audit
                tc.violations.append(f"CASCADE_DELETE:{cascade}")

        if tc.violations:
            violations.append({
                "table": name,
                "classification": tc.classification,
                "violations": tc.violations,
                "defined_in": tc.defined_in,
            })

    return violations


# =============================================================================
# Report Generation
# =============================================================================


def generate_report(
    tables: dict[str, TableControl],
    violations: list[dict],
    exceptions: dict[str, dict],
) -> dict:
    """Generate the full control matrix report."""
    # Summary stats
    total = len(tables)
    tenant_count = sum(1 for t in tables.values() if t.classification == "tenant")
    system_count = sum(1 for t in tables.values() if t.classification in ("system", "public", "infrastructure"))
    unverified_count = sum(1 for t in tables.values() if t.classification == "UNVERIFIED")
    rls_count = sum(1 for t in tables.values() if t.rls_enabled)
    violation_count = len(violations)

    return {
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "summary": {
            "total_tables": total,
            "tenant_owned": tenant_count,
            "system_public": system_count,
            "unverified": unverified_count,
            "rls_enabled": rls_count,
            "violations": violation_count,
            "exceptions": len(exceptions),
        },
        "violations": violations,
        "tables": {name: asdict(tc) for name, tc in sorted(tables.items())},
        "exceptions_applied": list(exceptions.keys()),
    }


# =============================================================================
# Exceptions Loading
# =============================================================================


def load_exceptions(path: Path) -> dict[str, dict]:
    """Load version-controlled exceptions file."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


# =============================================================================
# Main
# =============================================================================


def main() -> int:
    """Run the schema control matrix generator.

    Returns exit code: 0 = pass, 1 = violations found (CI failure).
    """
    import argparse

    parser = argparse.ArgumentParser(description="Schema Control Matrix Generator")
    parser.add_argument("--ci", action="store_true", help="Fail on violations (CI mode)")
    parser.add_argument("--output", type=str, default="", help="Output JSON path")
    args = parser.parse_args()

    # Parse migrations
    if not MIGRATIONS_DIR.exists():
        print(f"ERROR: Migrations directory not found: {MIGRATIONS_DIR}")
        return 1

    tables = parse_migrations(MIGRATIONS_DIR)
    exceptions = load_exceptions(EXCEPTIONS_FILE)

    # Classify
    classify_tables(tables, exceptions)

    # Detect violations
    violations = detect_violations(tables, exceptions)

    # Generate report
    report = generate_report(tables, violations, exceptions)

    # Output
    output_path = Path(args.output) if args.output else OUTPUT_DIR / "schema_control_matrix.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    # Print summary
    s = report["summary"]
    print(f"\n{'='*60}")
    print(f"  SCHEMA CONTROL MATRIX")
    print(f"{'='*60}")
    print(f"  Tables: {s['total_tables']}")
    print(f"  Tenant-owned: {s['tenant_owned']}")
    print(f"  System/Public: {s['system_public']}")
    print(f"  UNVERIFIED: {s['unverified']}")
    print(f"  RLS enabled: {s['rls_enabled']}")
    print(f"  Violations: {s['violations']}")
    print(f"  Exceptions: {s['exceptions']}")
    print(f"  Report: {output_path}")
    print(f"{'='*60}\n")

    if violations and args.ci:
        print("CI FAILURE — Violations detected:\n")
        for v in violations[:20]:
            print(f"  ❌ {v['table']}: {', '.join(v['violations'])}")
        if len(violations) > 20:
            print(f"  ... and {len(violations) - 20} more")
        return 1

    if violations:
        print(f"⚠️  {len(violations)} violations found (not in CI mode — informational only)\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Populate the _migration_ledger table with checksums for all SQL migration files.

This script:
1. Reads all .sql files in docs/sql/ (date-based naming convention)
2. Computes SHA-256 checksum of each file
3. Classifies each migration:
   - Ghost table migrations (20260808_001 through _010): status='baseline' (already in live DB)
   - Template migrations (contain "DO NOT APPLY"): status='template'
   - All others: status='pending' (need evaluation)
4. Inserts a record into _migration_ledger for each file

IMPORTANT: This does NOT execute any schema changes. It only populates the
ledger with metadata for migration tracking purposes.

Usage:
    # Dry run (prints what would be inserted, no DB changes)
    python -m backend.scripts.populate_migration_ledger --dry-run

    # Execute against Supabase (requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)
    python -m backend.scripts.populate_migration_ledger

    # Output SQL INSERT statements to stdout
    python -m backend.scripts.populate_migration_ledger --sql-only

Requirements: R5.4, R5.9, R5.10
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Relative path from project root to SQL migration files
MIGRATIONS_DIR = "docs/sql"

# Ghost table migrations that are already applied to the live database
GHOST_TABLE_MIGRATIONS = {
    "20260808_001_ghost_table_talent",
    "20260808_002_ghost_table_assets",
    "20260808_003_ghost_table_service_settings",
    "20260808_004_ghost_table_collections",
    "20260808_005_ghost_table_prompts",
    "20260808_006_ghost_table_products",
    "20260808_007_ghost_table_content_calendar",
    "20260808_008_ghost_table_campaigns",
    "20260808_009_ghost_table_performance_memory",
    "20260808_010_ghost_table_workflow_dna",
}

# Pattern to detect template migrations that should NOT be applied
TEMPLATE_PATTERN = re.compile(r"DO NOT APPLY", re.IGNORECASE)

# Pattern to extract migration_id from filename (strip .sql extension)
MIGRATION_ID_PATTERN = re.compile(r"^(\d{8}_\d{3}_.+)\.sql$")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class MigrationRecord:
    """Represents a single migration file and its metadata."""

    migration_id: str
    filename: str
    sha256_checksum: str
    status: str
    notes: str


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def find_project_root() -> Path:
    """Find the project root by looking for docs/sql/ directory."""
    # Try relative to this script
    script_dir = Path(__file__).resolve().parent
    # backend/scripts/ -> backend/ -> project root
    candidate = script_dir.parent.parent
    if (candidate / MIGRATIONS_DIR).is_dir():
        return candidate

    # Try current working directory
    cwd = Path.cwd()
    if (cwd / MIGRATIONS_DIR).is_dir():
        return cwd

    # Walk up from cwd
    for parent in cwd.parents:
        if (parent / MIGRATIONS_DIR).is_dir():
            return parent

    raise FileNotFoundError(
        f"Cannot find {MIGRATIONS_DIR}/ directory. "
        "Run this script from the project root or ensure docs/sql/ exists."
    )


def compute_sha256(filepath: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def is_template_migration(filepath: Path) -> bool:
    """Check if a migration file contains 'DO NOT APPLY' marker."""
    try:
        content = filepath.read_text(encoding="utf-8")
        return bool(TEMPLATE_PATTERN.search(content))
    except (OSError, UnicodeDecodeError):
        return False


def classify_migration(migration_id: str, filepath: Path) -> tuple[str, str]:
    """Classify a migration and return (status, notes).

    Returns:
        Tuple of (status, notes) where status is one of:
        - 'baseline': Ghost table migrations already in live DB
        - 'template': Template migrations that should NOT be applied
        - 'pending': Other migrations that need evaluation
    """
    if migration_id in GHOST_TABLE_MIGRATIONS:
        return "baseline", "Ghost table migration. Already exists in live DB (Task 1.2)."

    if is_template_migration(filepath):
        return "template", "Template migration. DO NOT APPLY automatically."

    return "pending", "Needs evaluation before application."


def scan_migrations(migrations_dir: Path) -> list[MigrationRecord]:
    """Scan all .sql files and create migration records."""
    records: list[MigrationRecord] = []

    sql_files = sorted(migrations_dir.glob("*.sql"))

    for filepath in sql_files:
        match = MIGRATION_ID_PATTERN.match(filepath.name)
        if not match:
            # Skip non-migration files (e.g., MIGRATION_RENAMING_MAP.md)
            continue

        migration_id = match.group(1)
        sha256_checksum = compute_sha256(filepath)
        status, notes = classify_migration(migration_id, filepath)

        records.append(
            MigrationRecord(
                migration_id=migration_id,
                filename=filepath.name,
                sha256_checksum=sha256_checksum,
                status=status,
                notes=notes,
            )
        )

    return records


# ---------------------------------------------------------------------------
# Output modes
# ---------------------------------------------------------------------------


def print_dry_run(records: list[MigrationRecord]) -> None:
    """Print a human-readable summary of what would be inserted."""
    print("=" * 80)
    print("MIGRATION LEDGER — DRY RUN")
    print("=" * 80)
    print(f"\nTotal migrations found: {len(records)}")
    print()

    # Summary by status
    status_counts: dict[str, int] = {}
    for rec in records:
        status_counts[rec.status] = status_counts.get(rec.status, 0) + 1

    print("Status breakdown:")
    for status, count in sorted(status_counts.items()):
        print(f"  {status:12s}: {count}")
    print()

    # Detailed listing
    print(f"{'Migration ID':<55} {'Status':<10} {'SHA-256 (first 12)'}")
    print("-" * 80)
    for rec in records:
        print(f"{rec.migration_id:<55} {rec.status:<10} {rec.sha256_checksum[:12]}...")

    print()
    print("No changes were made. Use --sql-only to generate SQL or run without flags to execute.")


def generate_sql(records: list[MigrationRecord]) -> str:
    """Generate SQL INSERT statements for all migration records."""
    lines: list[str] = []
    lines.append("-- Generated by backend/scripts/populate_migration_ledger.py")
    lines.append("-- This populates _migration_ledger with checksums and status for all migrations.")
    lines.append("")
    lines.append("-- Ensure the table exists first")
    lines.append("CREATE TABLE IF NOT EXISTS _migration_ledger (")
    lines.append("    migration_id      TEXT PRIMARY KEY,")
    lines.append("    sha256_checksum   TEXT NOT NULL,")
    lines.append("    applied_at        TIMESTAMPTZ NOT NULL DEFAULT now(),")
    lines.append("    status            TEXT DEFAULT 'applied',")
    lines.append("    notes             TEXT")
    lines.append(");")
    lines.append("")
    lines.append("-- Insert/update all migration records")

    for rec in records:
        # Escape single quotes in notes
        escaped_notes = rec.notes.replace("'", "''")
        lines.append(
            f"INSERT INTO _migration_ledger (migration_id, sha256_checksum, status, notes) "
            f"VALUES ('{rec.migration_id}', '{rec.sha256_checksum}', '{rec.status}', "
            f"'{escaped_notes}') "
            f"ON CONFLICT (migration_id) DO UPDATE SET "
            f"sha256_checksum = EXCLUDED.sha256_checksum, "
            f"status = EXCLUDED.status, "
            f"notes = EXCLUDED.notes;"
        )

    lines.append("")
    return "\n".join(lines)


def execute_against_supabase(records: list[MigrationRecord]) -> None:
    """Execute the ledger population against the live Supabase database.

    Requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables.
    """
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

    if not supabase_url or not supabase_key:
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set.", file=sys.stderr)
        print("Set these in your .env file or export them before running.", file=sys.stderr)
        print("\nAlternatively, use --sql-only to generate SQL statements.", file=sys.stderr)
        sys.exit(1)

    try:
        from supabase import create_client
    except ImportError:
        print("ERROR: supabase package not installed.", file=sys.stderr)
        print("Install with: pip install supabase", file=sys.stderr)
        sys.exit(1)

    client = create_client(supabase_url, supabase_key)

    print(f"Connecting to Supabase: {supabase_url[:40]}...")
    print(f"Populating _migration_ledger with {len(records)} records...")
    print()

    success_count = 0
    error_count = 0

    for rec in records:
        try:
            client.table("_migration_ledger").upsert(
                {
                    "migration_id": rec.migration_id,
                    "sha256_checksum": rec.sha256_checksum,
                    "status": rec.status,
                    "notes": rec.notes,
                },
                on_conflict="migration_id",
            ).execute()
            success_count += 1
            print(f"  [OK] {rec.migration_id} ({rec.status})")
        except Exception as e:
            error_count += 1
            print(f"  [FAIL] {rec.migration_id}: {e}", file=sys.stderr)

    print()
    print(f"Done. {success_count} inserted/updated, {error_count} failed.")

    if error_count > 0:
        print("\nWARNING: Some records failed. Check errors above.", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    """Main entry point for the migration ledger population script."""
    parser = argparse.ArgumentParser(
        description="Populate _migration_ledger with SHA-256 checksums for all SQL migrations.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Status classifications:
  baseline  - Ghost table migrations (20260808_001-010), already in live DB
  template  - Contains "DO NOT APPLY" marker, skipped by automation
  pending   - Needs evaluation before application

Examples:
  %(prog)s --dry-run          Show what would be inserted
  %(prog)s --sql-only         Output SQL INSERT statements
  %(prog)s                    Execute against Supabase (requires env vars)
""",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be inserted without making changes",
    )
    parser.add_argument(
        "--sql-only",
        action="store_true",
        help="Output SQL INSERT statements to stdout",
    )
    parser.add_argument(
        "--migrations-dir",
        type=str,
        default=None,
        help="Override path to migrations directory (default: auto-detect)",
    )

    args = parser.parse_args()

    # Find migrations directory
    if args.migrations_dir:
        migrations_dir = Path(args.migrations_dir)
    else:
        project_root = find_project_root()
        migrations_dir = project_root / MIGRATIONS_DIR

    if not migrations_dir.is_dir():
        print(f"ERROR: Migrations directory not found: {migrations_dir}", file=sys.stderr)
        sys.exit(1)

    # Scan and classify all migrations
    records = scan_migrations(migrations_dir)

    if not records:
        print("WARNING: No migration files found.", file=sys.stderr)
        sys.exit(1)

    # Execute based on mode
    if args.dry_run:
        print_dry_run(records)
    elif args.sql_only:
        sql = generate_sql(records)
        print(sql)
    else:
        execute_against_supabase(records)


if __name__ == "__main__":
    main()

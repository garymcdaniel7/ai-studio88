"""Verify org_id backfill completeness across all Category A tables.

Queries the database and reports any remaining NULL org_id rows.
Run this BEFORE applying migration 045 (NOT NULL constraints).

Usage:
    # Using Supabase CLI (recommended — no local env needed):
    python scripts/verify_org_id_backfill.py --supabase-cli

    # Using direct connection (requires SUPABASE_URL in .env):
    python scripts/verify_org_id_backfill.py

    # Dry run (just print the queries):
    python scripts/verify_org_id_backfill.py --dry-run

    # JSON output for CI:
    python scripts/verify_org_id_backfill.py --json

Exit codes:
    0 — All tables have zero NULL org_id rows (safe to apply NOT NULL)
    1 — One or more tables still have NULL org_id rows (DO NOT apply NOT NULL)
    2 — Script error (connection failure, missing table, etc.)

Requirements: R5.6, R69.5, R2.1
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# All Category A tables that should have org_id NOT NULL after migrations 040-045.
# Organized by migration group for clarity.
CATEGORY_A_TABLES: list[str] = [
    # Core content (migration 042)
    "talent",
    "assets",
    "jobs",
    "models",
    "workflows",
    # Existing nullable (migration 041)
    "aios_approvals",
    "aios_policies",
    "aios_sessions",
    "brain_collections",
    "brain_conversations",
    "brain_embeddings",
    "cost_records",
    "job_costs",
    "workflow_dna",
    "brain_memory",
    # Video (migration 043)
    "video_projects",
    "video_shots",
    "video_renders",
    "timeline_tracks",
    "timeline_clips",
    "timeline_exports",
    # Audio (migration 043)
    "voice_profiles",
    "voice_samples",
    "voice_datasets",
    "voice_dna",
    "voice_training_jobs",
    "voice_versions",
    "audio_clips",
    "lip_sync_jobs",
    "music_tracks_db",
    "sound_effects",
    "songs",
    "soundtrack_cues",
    # Publishing (migration 043)
    "publishing_accounts",
    "publishing_posts",
    "analytics_snapshots",
    # Brain (migration 044)
    "brain_sessions",
    "brain_messages",
    "brain_plans",
    # Creative (migration 044)
    "creative_dna",
    "creative_rules",
    "continuity_notes",
    "generation_feedback",
    "prompt_history",
    "style_preferences",
    "learning_events",
    "prompts",
    # Performance (migration 044)
    "performance_dna",
    "performance_memory",
    "quality_scores",
    "production_insights",
    # Cinematic (migration 044)
    "sequences",
    "cinematic_timelines",
    "cinematic_tracks",
    "cinematic_items",
    "cinematic_renders",
    "editing_operations",
    "storyboard_panels",
    # Company (migration 044)
    "brands",
    "campaigns",
    "content_calendar",
    "products",
    "series",
    # Asset intelligence (migration 044)
    "visual_dna",
    "asset_collections",
    "collection_items",
    "asset_relationships",
    "wardrobes",
    "outfits",
    "collections",
    # Remaining (migration 044)
    "talent_assets",
    "talent_relationships",
    "talent_voices",
    "workflow_runs",
    "lora_versions",
    "lora_evaluations",
    # Training (from 20260804_009)
    "training_datasets",
    "training_images",
    "training_jobs",
]


@dataclass
class TableResult:
    """Result of checking a single table."""

    table_name: str
    has_org_id_column: bool = False
    null_count: int = 0
    total_rows: int = 0
    error: str | None = None


@dataclass
class VerificationReport:
    """Full verification report."""

    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    tables_checked: int = 0
    tables_ready: int = 0
    tables_with_nulls: int = 0
    tables_missing_column: int = 0
    tables_with_errors: int = 0
    total_null_rows: int = 0
    results: list[TableResult] = field(default_factory=list)

    @property
    def is_safe_to_apply_not_null(self) -> bool:
        """Whether it's safe to run migration 045."""
        return (
            self.tables_with_nulls == 0
            and self.tables_missing_column == 0
            and self.tables_with_errors == 0
        )


def build_verification_query() -> str:
    """Build a single SQL query that checks all tables at once."""
    parts: list[str] = []
    for table in CATEGORY_A_TABLES:
        parts.append(
            f"SELECT '{table}' AS table_name, "
            f"(SELECT count(*) FROM information_schema.columns "
            f"WHERE table_schema='public' AND table_name='{table}' "
            f"AND column_name='org_id') AS has_column, "
            f"CASE WHEN EXISTS (SELECT 1 FROM information_schema.columns "
            f"WHERE table_schema='public' AND table_name='{table}' "
            f"AND column_name='org_id') "
            f"THEN (SELECT count(*) FROM public.\"{table}\" WHERE org_id IS NULL) "
            f"ELSE -1 END AS null_count, "
            f"CASE WHEN EXISTS (SELECT 1 FROM information_schema.tables "
            f"WHERE table_schema='public' AND table_name='{table}') "
            f"THEN (SELECT count(*) FROM public.\"{table}\") "
            f"ELSE -1 END AS total_rows"
        )
    return " UNION ALL ".join(parts) + " ORDER BY table_name;"


def run_via_supabase_cli(query: str) -> str:
    """Execute query via `supabase db query --linked`."""
    result = subprocess.run(
        ["supabase", "db", "query", "--linked", query],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"supabase db query failed: {result.stderr}")
    return result.stdout


def run_via_psql(query: str) -> str:
    """Execute query via psql using SUPABASE_URL from environment."""
    db_url = os.environ.get("SUPABASE_URL") or os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError(
            "Neither SUPABASE_URL nor DATABASE_URL is set. "
            "Use --supabase-cli or set the environment variable."
        )

    # Convert supabase URL to direct postgres connection if needed
    # Supabase URLs look like: https://xxx.supabase.co
    # We need the postgres connection string from SUPABASE_DB_URL or similar
    postgres_url = os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL")
    if not postgres_url:
        raise RuntimeError(
            "Set SUPABASE_DB_URL or DATABASE_URL to a postgresql:// connection string, "
            "or use --supabase-cli instead."
        )

    result = subprocess.run(
        ["psql", postgres_url, "-t", "-A", "-F", "|", "-c", query],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"psql query failed: {result.stderr}")
    return result.stdout


def parse_results(raw_output: str) -> list[TableResult]:
    """Parse query output into structured results."""
    results: list[TableResult] = []

    for line in raw_output.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("-") or line.startswith("("):
            continue

        # Handle pipe-delimited output from psql -F "|"
        # or space-delimited from supabase cli
        parts = [p.strip() for p in line.split("|") if p.strip()]
        if len(parts) < 4:
            # Try space/tab delimited
            parts = line.split()

        if len(parts) < 4:
            continue

        table_name = parts[0]
        if table_name not in CATEGORY_A_TABLES:
            continue

        try:
            has_column = int(parts[1]) > 0
            null_count = int(parts[2])
            total_rows = int(parts[3])
        except (ValueError, IndexError):
            results.append(TableResult(
                table_name=table_name,
                error=f"Could not parse output: {line}",
            ))
            continue

        results.append(TableResult(
            table_name=table_name,
            has_org_id_column=has_column,
            null_count=max(0, null_count),  # -1 means column doesn't exist
            total_rows=max(0, total_rows),
        ))

    return results


def generate_report(results: list[TableResult]) -> VerificationReport:
    """Generate a structured report from query results."""
    report = VerificationReport(results=results)
    report.tables_checked = len(results)

    for r in results:
        if r.error:
            report.tables_with_errors += 1
        elif not r.has_org_id_column:
            report.tables_missing_column += 1
        elif r.null_count > 0:
            report.tables_with_nulls += 1
            report.total_null_rows += r.null_count
        else:
            report.tables_ready += 1

    return report


def print_report(report: VerificationReport, as_json: bool = False) -> None:
    """Print the verification report."""
    if as_json:
        output = {
            "timestamp": report.timestamp,
            "safe_to_apply_not_null": report.is_safe_to_apply_not_null,
            "summary": {
                "tables_checked": report.tables_checked,
                "tables_ready": report.tables_ready,
                "tables_with_nulls": report.tables_with_nulls,
                "tables_missing_column": report.tables_missing_column,
                "tables_with_errors": report.tables_with_errors,
                "total_null_rows": report.total_null_rows,
            },
            "failures": [
                {
                    "table": r.table_name,
                    "issue": r.error or (
                        f"missing org_id column" if not r.has_org_id_column
                        else f"{r.null_count} NULL rows"
                    ),
                    "null_count": r.null_count,
                    "total_rows": r.total_rows,
                }
                for r in report.results
                if r.error or not r.has_org_id_column or r.null_count > 0
            ],
        }
        print(json.dumps(output, indent=2))
        return

    print("=" * 70)
    print("  org_id Backfill Verification Report")
    print(f"  Generated: {report.timestamp}")
    print("=" * 70)
    print()

    # Summary
    status = "PASS" if report.is_safe_to_apply_not_null else "FAIL"
    print(f"  Status: {status}")
    print(f"  Tables checked:        {report.tables_checked}")
    print(f"  Tables ready (0 NULL): {report.tables_ready}")
    print(f"  Tables with NULLs:     {report.tables_with_nulls}")
    print(f"  Tables missing column: {report.tables_missing_column}")
    print(f"  Tables with errors:    {report.tables_with_errors}")
    print(f"  Total NULL rows:       {report.total_null_rows}")
    print()

    # Details for failures
    failures = [
        r for r in report.results
        if r.error or not r.has_org_id_column or r.null_count > 0
    ]
    if failures:
        print("-" * 70)
        print("  FAILURES (must fix before applying migration 045)")
        print("-" * 70)
        print(f"  {'Table':<30} {'Issue':<30} {'Rows':<10}")
        print(f"  {'-'*28:<30} {'-'*28:<30} {'-'*8:<10}")
        for r in failures:
            if r.error:
                issue = f"ERROR: {r.error[:28]}"
            elif not r.has_org_id_column:
                issue = "Missing org_id column"
            else:
                issue = f"{r.null_count} NULL org_id rows"
            print(f"  {r.table_name:<30} {issue:<30} {r.total_rows:<10}")
        print()

    # Success details
    if report.tables_ready > 0:
        print("-" * 70)
        print(f"  READY ({report.tables_ready} tables with 0 NULL org_id)")
        print("-" * 70)
        ready_tables = [r for r in report.results if r.has_org_id_column and r.null_count == 0 and not r.error]
        for r in ready_tables:
            print(f"  {r.table_name:<30} {r.total_rows:>8} rows")
        print()

    # Quarantine summary
    print("-" * 70)
    if report.is_safe_to_apply_not_null:
        print("  VERDICT: Safe to apply migration 045 (NOT NULL constraints)")
    else:
        print("  VERDICT: NOT safe to apply migration 045")
        print("  ACTION:  Run migrations 041-044 first, then re-verify")
    print("=" * 70)


def print_dry_run() -> None:
    """Print the verification query without executing it."""
    print("-- Verification query for org_id backfill completeness")
    print("-- Run this against the database to check NULL org_id rows")
    print()
    query = build_verification_query()
    print(query)


def main() -> int:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Verify org_id backfill completeness across all Category A tables."
    )
    parser.add_argument(
        "--supabase-cli",
        action="store_true",
        help="Use `supabase db query --linked` for execution",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the verification query without executing",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON (for CI integration)",
    )
    args = parser.parse_args()

    if args.dry_run:
        print_dry_run()
        return 0

    query = build_verification_query()

    try:
        if args.supabase_cli:
            raw_output = run_via_supabase_cli(query)
        else:
            raw_output = run_via_psql(query)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    except FileNotFoundError as e:
        print(f"ERROR: Command not found: {e}", file=sys.stderr)
        print("Install the Supabase CLI or psql, or use --dry-run.", file=sys.stderr)
        return 2
    except subprocess.TimeoutExpired:
        print("ERROR: Query timed out after 120 seconds", file=sys.stderr)
        return 2

    results = parse_results(raw_output)

    if not results:
        print("WARNING: No results parsed from query output.", file=sys.stderr)
        print("Raw output:", file=sys.stderr)
        print(raw_output[:2000], file=sys.stderr)
        return 2

    report = generate_report(results)
    print_report(report, as_json=args.json)

    return 0 if report.is_safe_to_apply_not_null else 1


if __name__ == "__main__":
    sys.exit(main())

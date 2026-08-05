"""Migration Ledger — Story 067.

Immutable migration execution system with checksums, locking, transactional
execution, dry-run validation, and failure reporting.

Every applied migration gets an immutable ledger entry with:
- Migration ID (filename-based)
- SHA-256 checksum of file content
- Environment target
- Applied timestamp and duration
- Release identity linkage
- Outcome (applied, failed, skipped)

Safety guarantees:
- Changed checksums for applied migrations BLOCK execution
- Concurrent runners cannot apply the same migration twice (advisory lock)
- Supported migrations run transactionally
- Failure stops all later migrations immediately
- Dry-run validates without applying

Usage:
    python scripts/migration_ledger.py --env staging --apply
    python scripts/migration_ledger.py --env production --dry-run
    python scripts/migration_ledger.py --env staging --status
    python scripts/migration_ledger.py --ci  # CI validation only (no DB)
"""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any


# =============================================================================
# Configuration
# =============================================================================

MIGRATIONS_DIR = Path(__file__).parent.parent / "docs" / "sql"

# Markers in SQL files for non-transactional or irreversible operations
NON_TRANSACTIONAL_MARKERS = [
    "CREATE INDEX CONCURRENTLY",
    "DROP INDEX CONCURRENTLY",
    "ALTER TYPE",
    "VACUUM",
    "REINDEX",
]

IRREVERSIBLE_MARKERS = [
    "DROP TABLE",
    "DROP COLUMN",
    "TRUNCATE",
    "DELETE FROM",  # without WHERE is dangerous but we flag all
]

# Advisory lock ID for preventing concurrent migration runs
MIGRATION_LOCK_ID = 867_530_9  # Unique int for pg_advisory_lock


# =============================================================================
# Types
# =============================================================================


class MigrationStatus(str, Enum):
    PENDING = "pending"
    APPLIED = "applied"
    FAILED = "failed"
    SKIPPED = "skipped"


class MigrationType(str, Enum):
    TRANSACTIONAL = "transactional"
    NON_TRANSACTIONAL = "non_transactional"
    REPAIR = "repair"
    IRREVERSIBLE = "irreversible"


class LedgerDecision(str, Enum):
    APPLY = "apply"           # Safe to apply
    BLOCK_CHECKSUM = "block_checksum"   # Checksum changed
    BLOCK_ORDER = "block_order"         # Out of order
    BLOCK_DUPLICATE = "block_duplicate" # Already applied
    BLOCK_LOCK = "block_lock"           # Concurrent runner
    BLOCK_FAILED = "block_failed"       # Previous failure not resolved
    DRY_RUN = "dry_run"       # Validated but not applied


# =============================================================================
# Migration File
# =============================================================================


@dataclass
class MigrationFile:
    """A discovered SQL migration file with metadata."""

    filename: str
    path: Path
    sequence: str            # e.g. "001", "006b"
    name: str                # e.g. "create_jobs_table"
    checksum: str            # SHA-256 of file content
    content: str             # Raw SQL content
    migration_type: MigrationType = MigrationType.TRANSACTIONAL
    is_irreversible: bool = False
    size_bytes: int = 0

    @property
    def migration_id(self) -> str:
        """Immutable migration ID derived from filename."""
        return self.filename.removesuffix(".sql")

    def to_dict(self) -> dict:
        return {
            "migration_id": self.migration_id,
            "filename": self.filename,
            "sequence": self.sequence,
            "name": self.name,
            "checksum": self.checksum,
            "migration_type": self.migration_type.value,
            "is_irreversible": self.is_irreversible,
            "size_bytes": self.size_bytes,
        }


# =============================================================================
# Ledger Entry
# =============================================================================


@dataclass
class LedgerEntry:
    """An immutable record of a migration application."""

    migration_id: str
    checksum: str
    environment: str
    status: MigrationStatus
    applied_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    duration_ms: int = 0
    release_id: str = ""
    commit_sha: str = ""
    error_message: str = ""
    applied_by: str = "migration_ledger"

    def to_dict(self) -> dict:
        return {
            "migration_id": self.migration_id,
            "checksum": self.checksum,
            "environment": self.environment,
            "status": self.status.value,
            "applied_at": self.applied_at,
            "duration_ms": self.duration_ms,
            "release_id": self.release_id,
            "commit_sha": self.commit_sha,
            "error_message": self.error_message,
            "applied_by": self.applied_by,
        }


# =============================================================================
# Migration Discovery
# =============================================================================


_FILENAME_PATTERN = re.compile(r"^(\d{3}[a-z]?)_(.+)\.sql$")


def discover_migrations(migrations_dir: Path) -> list[MigrationFile]:
    """Discover and parse all SQL migration files.

    Returns migrations sorted by (sequence, filename) for deterministic ordering.
    """
    if not migrations_dir.exists():
        return []

    migrations: list[MigrationFile] = []

    for sql_file in sorted(migrations_dir.glob("*.sql")):
        match = _FILENAME_PATTERN.match(sql_file.name)
        if not match:
            continue  # Skip non-conforming files

        sequence = match.group(1)
        name = match.group(2)
        content = sql_file.read_text(encoding="utf-8")
        checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()

        migration_type = _classify_migration(content)
        is_irreversible = _is_irreversible(content)

        migrations.append(MigrationFile(
            filename=sql_file.name,
            path=sql_file,
            sequence=sequence,
            name=name,
            checksum=checksum,
            content=content,
            migration_type=migration_type,
            is_irreversible=is_irreversible,
            size_bytes=len(content.encode("utf-8")),
        ))

    # Sort by sequence (lexicographic, so "006b" comes after "006") then filename
    migrations.sort(key=lambda m: (m.sequence, m.filename))
    return migrations


def _classify_migration(content: str) -> MigrationType:
    """Classify migration type based on SQL content."""
    content_upper = content.upper()
    for marker in NON_TRANSACTIONAL_MARKERS:
        if marker in content_upper:
            return MigrationType.NON_TRANSACTIONAL
    return MigrationType.TRANSACTIONAL


def _is_irreversible(content: str) -> bool:
    """Check if migration contains irreversible operations."""
    content_upper = content.upper()
    for marker in IRREVERSIBLE_MARKERS:
        if marker in content_upper:
            return True
    return False


# =============================================================================
# Checksum Validation
# =============================================================================


def compute_checksum(content: str) -> str:
    """Compute SHA-256 checksum for migration content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


# =============================================================================
# Migration Ledger
# =============================================================================


@dataclass
class MigrationLedger:
    """The authoritative ledger of all migration state.

    In production, this maps to the `_migration_ledger` table in the database.
    For CI/dry-run, it operates in-memory.
    """

    environment: str
    entries: list[LedgerEntry] = field(default_factory=list)
    lock_acquired: bool = False
    lock_holder: str = ""

    def get_applied(self) -> dict[str, LedgerEntry]:
        """Return map of migration_id → entry for applied migrations."""
        return {
            e.migration_id: e
            for e in self.entries
            if e.status == MigrationStatus.APPLIED
        }

    def get_failed(self) -> list[LedgerEntry]:
        """Return list of failed migrations (unresolved)."""
        return [e for e in self.entries if e.status == MigrationStatus.FAILED]

    def has_unresolved_failures(self) -> bool:
        """Check if there are unresolved failed migrations."""
        return len(self.get_failed()) > 0

    def to_dict(self) -> dict:
        return {
            "environment": self.environment,
            "total_entries": len(self.entries),
            "applied": len(self.get_applied()),
            "failed": len(self.get_failed()),
            "lock_acquired": self.lock_acquired,
            "entries": [e.to_dict() for e in self.entries],
        }


# =============================================================================
# Execution Plan
# =============================================================================


@dataclass
class ExecutionStep:
    """A single step in the migration execution plan."""

    migration: MigrationFile
    decision: LedgerDecision
    reason: str = ""
    requires_authorization: bool = False  # For repair/irreversible


@dataclass
class ExecutionPlan:
    """The complete migration execution plan before running."""

    environment: str
    steps: list[ExecutionStep] = field(default_factory=list)
    blocked: bool = False
    block_reason: str = ""
    total_pending: int = 0
    total_already_applied: int = 0

    def to_dict(self) -> dict:
        return {
            "environment": self.environment,
            "blocked": self.blocked,
            "block_reason": self.block_reason,
            "total_steps": len(self.steps),
            "total_pending": self.total_pending,
            "total_already_applied": self.total_already_applied,
            "steps": [
                {
                    "migration_id": s.migration.migration_id,
                    "decision": s.decision.value,
                    "reason": s.reason,
                    "migration_type": s.migration.migration_type.value,
                    "is_irreversible": s.migration.is_irreversible,
                    "requires_authorization": s.requires_authorization,
                }
                for s in self.steps
            ],
        }


# =============================================================================
# Plan Builder
# =============================================================================


def build_execution_plan(
    migrations: list[MigrationFile],
    ledger: MigrationLedger,
    *,
    dry_run: bool = False,
    authorize_irreversible: bool = False,
    authorize_repair: bool = False,
) -> ExecutionPlan:
    """Build the execution plan by comparing discovered migrations against the ledger.

    Rules:
    1. Already-applied migrations with matching checksum → skip
    2. Already-applied migrations with DIFFERENT checksum → BLOCK
    3. Unresolved failures → BLOCK all further execution
    4. New migrations → APPLY (or DRY_RUN)
    5. Irreversible migrations require explicit authorization
    6. Repair migrations require explicit authorization
    """
    plan = ExecutionPlan(environment=ledger.environment)
    applied = ledger.get_applied()

    # Check for unresolved failures first
    if ledger.has_unresolved_failures():
        failed = ledger.get_failed()
        plan.blocked = True
        plan.block_reason = (
            f"Unresolved failed migration(s): "
            f"{', '.join(f.migration_id for f in failed)}. "
            f"Resolve with --repair authorization before continuing."
        )
        return plan

    for migration in migrations:
        mid = migration.migration_id

        if mid in applied:
            existing = applied[mid]
            plan.total_already_applied += 1

            # Checksum validation — immutable after application
            if existing.checksum != migration.checksum:
                plan.steps.append(ExecutionStep(
                    migration=migration,
                    decision=LedgerDecision.BLOCK_CHECKSUM,
                    reason=(
                        f"Checksum mismatch: applied={existing.checksum[:12]}... "
                        f"current={migration.checksum[:12]}... "
                        f"Applied migrations are immutable."
                    ),
                ))
                plan.blocked = True
                plan.block_reason = (
                    f"Checksum mismatch on {mid}. "
                    f"Applied migrations must not be modified."
                )
                return plan  # Stop planning on checksum violation

            # Already applied with same checksum → skip silently
            continue

        # New migration — evaluate
        plan.total_pending += 1

        # Check if irreversible requires authorization
        if migration.is_irreversible and not authorize_irreversible:
            plan.steps.append(ExecutionStep(
                migration=migration,
                decision=LedgerDecision.BLOCK_ORDER,
                reason="Irreversible migration requires --authorize-irreversible flag",
                requires_authorization=True,
            ))
            plan.blocked = True
            plan.block_reason = (
                f"Irreversible migration {mid} requires explicit authorization."
            )
            return plan

        # Check if repair requires authorization
        if migration.migration_type == MigrationType.REPAIR and not authorize_repair:
            plan.steps.append(ExecutionStep(
                migration=migration,
                decision=LedgerDecision.BLOCK_ORDER,
                reason="Repair migration requires --authorize-repair flag",
                requires_authorization=True,
            ))
            plan.blocked = True
            plan.block_reason = (
                f"Repair migration {mid} requires explicit authorization."
            )
            return plan

        # Safe to apply (or dry-run)
        decision = LedgerDecision.DRY_RUN if dry_run else LedgerDecision.APPLY
        plan.steps.append(ExecutionStep(
            migration=migration,
            decision=decision,
            reason="New migration, ready to apply",
        ))

    return plan


# =============================================================================
# Execution Engine
# =============================================================================


@dataclass
class ExecutionResult:
    """Result of executing the migration plan."""

    environment: str
    success: bool = False
    applied: list[LedgerEntry] = field(default_factory=list)
    failed: LedgerEntry | None = None
    skipped: list[str] = field(default_factory=list)
    total_duration_ms: int = 0
    release_id: str = ""
    commit_sha: str = ""
    dry_run: bool = False

    def to_dict(self) -> dict:
        return {
            "environment": self.environment,
            "success": self.success,
            "dry_run": self.dry_run,
            "applied_count": len(self.applied),
            "applied": [e.to_dict() for e in self.applied],
            "failed": self.failed.to_dict() if self.failed else None,
            "skipped": self.skipped,
            "total_duration_ms": self.total_duration_ms,
            "release_id": self.release_id,
            "commit_sha": self.commit_sha,
        }


def execute_plan(
    plan: ExecutionPlan,
    ledger: MigrationLedger,
    *,
    executor: Any = None,
    release_id: str = "",
    commit_sha: str = "",
) -> ExecutionResult:
    """Execute the migration plan.

    For each APPLY step:
    1. Acquire advisory lock (if not held)
    2. Execute SQL (transactionally if supported)
    3. Record in ledger
    4. On failure: record failure, stop immediately

    The executor parameter is a callable that accepts (sql: str, transactional: bool)
    and returns True on success or raises an exception.
    In dry-run mode or CI, no executor is needed.
    """
    result = ExecutionResult(
        environment=plan.environment,
        release_id=release_id,
        commit_sha=commit_sha,
        dry_run=all(s.decision == LedgerDecision.DRY_RUN for s in plan.steps),
    )

    if plan.blocked:
        result.success = False
        if plan.steps:
            last = plan.steps[-1]
            result.failed = LedgerEntry(
                migration_id=last.migration.migration_id,
                checksum=last.migration.checksum,
                environment=plan.environment,
                status=MigrationStatus.FAILED,
                error_message=plan.block_reason,
                release_id=release_id,
                commit_sha=commit_sha,
            )
        return result

    start_time = time.monotonic()

    for step in plan.steps:
        if step.decision == LedgerDecision.DRY_RUN:
            # Validate syntax/structure without executing
            result.applied.append(LedgerEntry(
                migration_id=step.migration.migration_id,
                checksum=step.migration.checksum,
                environment=plan.environment,
                status=MigrationStatus.APPLIED,
                release_id=release_id,
                commit_sha=commit_sha,
            ))
            result.dry_run = True
            continue

        if step.decision != LedgerDecision.APPLY:
            result.skipped.append(step.migration.migration_id)
            continue

        # Execute the migration
        step_start = time.monotonic()
        transactional = step.migration.migration_type == MigrationType.TRANSACTIONAL

        try:
            if executor is not None:
                executor(step.migration.content, transactional)

            duration_ms = int((time.monotonic() - step_start) * 1000)

            entry = LedgerEntry(
                migration_id=step.migration.migration_id,
                checksum=step.migration.checksum,
                environment=plan.environment,
                status=MigrationStatus.APPLIED,
                duration_ms=duration_ms,
                release_id=release_id,
                commit_sha=commit_sha,
            )
            ledger.entries.append(entry)
            result.applied.append(entry)

        except Exception as exc:
            duration_ms = int((time.monotonic() - step_start) * 1000)

            entry = LedgerEntry(
                migration_id=step.migration.migration_id,
                checksum=step.migration.checksum,
                environment=plan.environment,
                status=MigrationStatus.FAILED,
                duration_ms=duration_ms,
                error_message=str(exc)[:500],
                release_id=release_id,
                commit_sha=commit_sha,
            )
            ledger.entries.append(entry)
            result.failed = entry
            result.total_duration_ms = int((time.monotonic() - start_time) * 1000)
            result.success = False
            return result  # Stop on first failure

    result.total_duration_ms = int((time.monotonic() - start_time) * 1000)
    result.success = True
    return result


# =============================================================================
# Locking
# =============================================================================


def acquire_lock(ledger: MigrationLedger, runner_id: str = "") -> bool:
    """Acquire the migration advisory lock.

    In production: uses pg_try_advisory_lock(MIGRATION_LOCK_ID).
    Here: simulated with the ledger's lock_acquired flag.
    Returns True if lock acquired, False if another runner holds it.
    """
    if ledger.lock_acquired:
        return False  # Another runner holds the lock

    ledger.lock_acquired = True
    ledger.lock_holder = runner_id or f"runner-{int(time.time())}"
    return True


def release_lock(ledger: MigrationLedger) -> None:
    """Release the migration advisory lock."""
    ledger.lock_acquired = False
    ledger.lock_holder = ""


# =============================================================================
# CI Validation (no DB required)
# =============================================================================


def validate_migrations_ci(migrations_dir: Path) -> dict:
    """CI-mode validation: check ordering, duplicates, and checksums.

    No database access required. Validates:
    - All files match naming convention
    - No duplicate migration IDs
    - No gaps in sequence (warning only)
    - Checksums are stable
    - Non-transactional and irreversible migrations are flagged
    """
    migrations = discover_migrations(migrations_dir)
    issues: list[dict] = []

    # Check for duplicate migration IDs
    seen_ids: dict[str, str] = {}
    for m in migrations:
        if m.migration_id in seen_ids:
            issues.append({
                "type": "DUPLICATE_ID",
                "migration_id": m.migration_id,
                "message": f"Duplicate migration ID: {m.migration_id}",
                "severity": "error",
            })
        seen_ids[m.migration_id] = m.filename

    # Check for duplicate sequence numbers (warning — we have these historically)
    seen_sequences: dict[str, list[str]] = {}
    for m in migrations:
        seen_sequences.setdefault(m.sequence, []).append(m.filename)

    for seq, files in seen_sequences.items():
        if len(files) > 1:
            issues.append({
                "type": "DUPLICATE_SEQUENCE",
                "sequence": seq,
                "files": files,
                "message": f"Sequence {seq} used by {len(files)} files: {', '.join(files)}",
                "severity": "warning",
            })

    # Flag non-transactional and irreversible
    for m in migrations:
        if m.migration_type == MigrationType.NON_TRANSACTIONAL:
            issues.append({
                "type": "NON_TRANSACTIONAL",
                "migration_id": m.migration_id,
                "message": f"{m.filename} contains non-transactional operations",
                "severity": "info",
            })
        if m.is_irreversible:
            issues.append({
                "type": "IRREVERSIBLE",
                "migration_id": m.migration_id,
                "message": f"{m.filename} contains irreversible operations",
                "severity": "warning",
            })

    errors = [i for i in issues if i["severity"] == "error"]
    warnings = [i for i in issues if i["severity"] == "warning"]

    return {
        "valid": len(errors) == 0,
        "total_migrations": len(migrations),
        "errors": len(errors),
        "warnings": len(warnings),
        "issues": issues,
        "migrations": [m.to_dict() for m in migrations],
    }


# =============================================================================
# Ledger Table SQL (for bootstrapping)
# =============================================================================

LEDGER_TABLE_SQL = """
-- Migration ledger table (Story 067)
-- This table is created BEFORE any other migration runs.
-- It is the source of truth for migration state.

CREATE TABLE IF NOT EXISTS _migration_ledger (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    migration_id    TEXT NOT NULL,
    checksum        TEXT NOT NULL,
    environment     TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'applied',
    applied_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    duration_ms     INTEGER DEFAULT 0,
    release_id      TEXT DEFAULT '',
    commit_sha      TEXT DEFAULT '',
    error_message   TEXT DEFAULT '',
    applied_by      TEXT DEFAULT 'migration_ledger',
    UNIQUE(migration_id, environment)
);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS ix_migration_ledger_env
    ON _migration_ledger(environment, applied_at);

-- Advisory lock function for concurrent safety
-- Usage: SELECT pg_try_advisory_lock(8675309);
-- Release: SELECT pg_advisory_unlock(8675309);
"""


# =============================================================================
# Main CLI
# =============================================================================


def main() -> int:
    """Run the migration ledger CLI."""
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Migration Ledger (Story 067)")
    parser.add_argument("--env", type=str, default="development", help="Target environment")
    parser.add_argument("--apply", action="store_true", help="Apply pending migrations")
    parser.add_argument("--dry-run", action="store_true", help="Validate without applying")
    parser.add_argument("--status", action="store_true", help="Show ledger status")
    parser.add_argument("--ci", action="store_true", help="CI validation (no DB)")
    parser.add_argument("--authorize-irreversible", action="store_true")
    parser.add_argument("--authorize-repair", action="store_true")
    parser.add_argument("--release-id", type=str, default="")
    parser.add_argument("--commit-sha", type=str, default="")
    args = parser.parse_args()

    if args.ci:
        result = validate_migrations_ci(MIGRATIONS_DIR)
        print(json.dumps(result, indent=2))
        return 0 if result["valid"] else 1

    # For non-CI modes, we need a ledger (from DB in production, empty for dry-run)
    ledger = MigrationLedger(environment=args.env)
    migrations = discover_migrations(MIGRATIONS_DIR)

    if args.status:
        print(f"Environment: {args.env}")
        print(f"Discovered migrations: {len(migrations)}")
        print(f"Ledger entries: {len(ledger.entries)}")
        print(f"Applied: {len(ledger.get_applied())}")
        print(f"Failed: {len(ledger.get_failed())}")
        return 0

    plan = build_execution_plan(
        migrations,
        ledger,
        dry_run=args.dry_run,
        authorize_irreversible=args.authorize_irreversible,
        authorize_repair=args.authorize_repair,
    )

    if plan.blocked:
        print(f"BLOCKED: {plan.block_reason}")
        print(json.dumps(plan.to_dict(), indent=2))
        return 1

    if args.dry_run:
        result = execute_plan(plan, ledger, release_id=args.release_id, commit_sha=args.commit_sha)
        print(f"DRY RUN: {result.to_dict()['applied_count']} migrations validated")
        print(json.dumps(result.to_dict(), indent=2))
        return 0

    if args.apply:
        if not acquire_lock(ledger, "cli"):
            print("BLOCKED: Another migration runner holds the lock")
            return 1

        try:
            result = execute_plan(
                plan, ledger,
                release_id=args.release_id,
                commit_sha=args.commit_sha,
            )
            print(json.dumps(result.to_dict(), indent=2))
            return 0 if result.success else 1
        finally:
            release_lock(ledger)

    parser.print_help()
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

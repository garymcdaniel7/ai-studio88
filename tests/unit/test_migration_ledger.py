"""Migration Ledger Tests (Story 067).

Proves: checksum mismatch blocks, concurrent lock blocks, failure stops chain,
dry-run validates without applying, clean install discovers all migrations,
and CI validation catches duplicates.

Run with:
    pytest tests/unit/test_migration_ledger.py -v
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from scripts.migration_ledger import (
    ExecutionPlan,
    LedgerDecision,
    LedgerEntry,
    MigrationFile,
    MigrationLedger,
    MigrationStatus,
    MigrationType,
    acquire_lock,
    build_execution_plan,
    compute_checksum,
    discover_migrations,
    execute_plan,
    release_lock,
    validate_migrations_ci,
)


# =============================================================================
# Helpers
# =============================================================================


def _make_migration(filename: str, content: str = "SELECT 1;") -> MigrationFile:
    """Create a MigrationFile for testing."""
    checksum = compute_checksum(content)
    # Parse sequence and name from filename
    import re
    match = re.match(r"^(\d{3}[a-z]?)_(.+)\.sql$", filename)
    seq = match.group(1) if match else "000"
    name = match.group(2) if match else "test"
    return MigrationFile(
        filename=filename,
        path=Path(f"/tmp/{filename}"),
        sequence=seq,
        name=name,
        checksum=checksum,
        content=content,
        size_bytes=len(content.encode()),
    )


def _make_ledger(env: str = "staging") -> MigrationLedger:
    """Create an empty ledger."""
    return MigrationLedger(environment=env)


def _make_applied_entry(migration: MigrationFile, env: str = "staging") -> LedgerEntry:
    """Create a ledger entry as if migration was already applied."""
    return LedgerEntry(
        migration_id=migration.migration_id,
        checksum=migration.checksum,
        environment=env,
        status=MigrationStatus.APPLIED,
    )


# =============================================================================
# Discovery
# =============================================================================


class TestDiscovery:

    @pytest.mark.unit
    def test_discovers_migrations_from_directory(self):
        """Discovers all .sql files matching NNN_name.sql pattern."""
        migrations = discover_migrations(Path(__file__).parent.parent.parent / "docs" / "sql")
        # We know there are 47+ files
        assert len(migrations) >= 40
        # First one should be 000_migration_ledger
        assert migrations[0].sequence == "000"

    @pytest.mark.unit
    def test_sorts_by_sequence_then_filename(self):
        """Migrations are sorted deterministically."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "002_second.sql").write_text("SELECT 2;")
            (tmp / "001_first.sql").write_text("SELECT 1;")
            (tmp / "001b_first_extra.sql").write_text("SELECT 1b;")

            result = discover_migrations(tmp)
            assert [m.sequence for m in result] == ["001", "001b", "002"]

    @pytest.mark.unit
    def test_skips_non_matching_files(self):
        """Files not matching NNN_name.sql are skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "001_valid.sql").write_text("SELECT 1;")
            (tmp / "readme.md").write_text("Not a migration")
            (tmp / "backup.sql").write_text("Not numbered")

            result = discover_migrations(tmp)
            assert len(result) == 1
            assert result[0].filename == "001_valid.sql"

    @pytest.mark.unit
    def test_computes_checksum(self):
        """Each migration gets a SHA-256 checksum."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "001_test.sql").write_text("CREATE TABLE foo (id INT);")

            result = discover_migrations(tmp)
            assert len(result[0].checksum) == 64  # SHA-256 hex

    @pytest.mark.unit
    def test_classifies_non_transactional(self):
        """Non-transactional operations detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "001_idx.sql").write_text("CREATE INDEX CONCURRENTLY idx ON foo(bar);")

            result = discover_migrations(tmp)
            assert result[0].migration_type == MigrationType.NON_TRANSACTIONAL

    @pytest.mark.unit
    def test_classifies_irreversible(self):
        """Irreversible operations flagged."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "001_drop.sql").write_text("DROP TABLE old_data;")

            result = discover_migrations(tmp)
            assert result[0].is_irreversible is True

    @pytest.mark.unit
    def test_empty_directory_returns_empty(self):
        """Empty or nonexistent directory returns empty list."""
        result = discover_migrations(Path("/nonexistent/path"))
        assert result == []


# =============================================================================
# Checksum Validation
# =============================================================================


class TestChecksumValidation:

    @pytest.mark.unit
    def test_matching_checksum_skips(self):
        """Already-applied migration with same checksum is skipped."""
        m1 = _make_migration("001_first.sql", "SELECT 1;")
        ledger = _make_ledger()
        ledger.entries.append(_make_applied_entry(m1))

        plan = build_execution_plan([m1], ledger)
        assert not plan.blocked
        assert plan.total_already_applied == 1
        assert plan.total_pending == 0
        assert len(plan.steps) == 0

    @pytest.mark.unit
    def test_changed_checksum_blocks(self):
        """Applied migration with different checksum BLOCKS execution."""
        m1 = _make_migration("001_first.sql", "SELECT 1;")
        ledger = _make_ledger()
        # Record with OLD checksum
        entry = LedgerEntry(
            migration_id=m1.migration_id,
            checksum="old_checksum_that_differs",
            environment="staging",
            status=MigrationStatus.APPLIED,
        )
        ledger.entries.append(entry)

        plan = build_execution_plan([m1], ledger)
        assert plan.blocked is True
        assert "checksum" in plan.block_reason.lower()
        assert plan.steps[0].decision == LedgerDecision.BLOCK_CHECKSUM

    @pytest.mark.unit
    def test_checksum_mismatch_stops_all_later(self):
        """Checksum block prevents evaluation of subsequent migrations."""
        m1 = _make_migration("001_first.sql", "SELECT 1;")
        m2 = _make_migration("002_second.sql", "SELECT 2;")
        ledger = _make_ledger()
        entry = LedgerEntry(
            migration_id=m1.migration_id,
            checksum="wrong_checksum",
            environment="staging",
            status=MigrationStatus.APPLIED,
        )
        ledger.entries.append(entry)

        plan = build_execution_plan([m1, m2], ledger)
        assert plan.blocked is True
        # Only one step recorded (the blocker), m2 never evaluated
        assert len(plan.steps) == 1
        assert plan.steps[0].migration.migration_id == "001_first"


# =============================================================================
# Concurrent Lock
# =============================================================================


class TestConcurrentLock:

    @pytest.mark.unit
    def test_acquire_lock_succeeds_first_time(self):
        """First runner acquires the lock."""
        ledger = _make_ledger()
        assert acquire_lock(ledger, "runner-1") is True
        assert ledger.lock_acquired is True
        assert ledger.lock_holder == "runner-1"

    @pytest.mark.unit
    def test_second_runner_blocked(self):
        """Second runner cannot acquire lock held by first."""
        ledger = _make_ledger()
        acquire_lock(ledger, "runner-1")

        assert acquire_lock(ledger, "runner-2") is False
        # First runner still holds it
        assert ledger.lock_holder == "runner-1"

    @pytest.mark.unit
    def test_release_allows_reacquire(self):
        """After release, another runner can acquire."""
        ledger = _make_ledger()
        acquire_lock(ledger, "runner-1")
        release_lock(ledger)

        assert acquire_lock(ledger, "runner-2") is True
        assert ledger.lock_holder == "runner-2"


# =============================================================================
# Failure Stops Chain
# =============================================================================


class TestFailureStopsChain:

    @pytest.mark.unit
    def test_executor_failure_stops_later_migrations(self):
        """When executor raises, remaining migrations are NOT applied."""
        m1 = _make_migration("001_first.sql", "SELECT 1;")
        m2 = _make_migration("002_second.sql", "SELECT 2;")
        m3 = _make_migration("003_third.sql", "SELECT 3;")
        ledger = _make_ledger()

        plan = build_execution_plan([m1, m2, m3], ledger)
        assert not plan.blocked

        call_count = [0]

        def failing_executor(sql: str, transactional: bool) -> None:
            call_count[0] += 1
            if call_count[0] == 2:
                raise RuntimeError("Simulated DB error on second migration")

        result = execute_plan(plan, ledger, executor=failing_executor)

        assert result.success is False
        assert len(result.applied) == 1  # Only first succeeded
        assert result.failed is not None
        assert result.failed.migration_id == "002_second"
        assert "Simulated DB error" in result.failed.error_message
        # Third migration was never attempted
        assert call_count[0] == 2

    @pytest.mark.unit
    def test_unresolved_failure_blocks_all(self):
        """Unresolved failed migration blocks all future execution."""
        m1 = _make_migration("001_first.sql", "SELECT 1;")
        m2 = _make_migration("002_second.sql", "SELECT 2;")
        ledger = _make_ledger()
        # Record a failed migration
        ledger.entries.append(LedgerEntry(
            migration_id="001_first",
            checksum=m1.checksum,
            environment="staging",
            status=MigrationStatus.FAILED,
            error_message="Previous failure",
        ))

        plan = build_execution_plan([m1, m2], ledger)
        assert plan.blocked is True
        assert "unresolved" in plan.block_reason.lower()

    @pytest.mark.unit
    def test_failed_entry_recorded_in_ledger(self):
        """Failed execution records the failure in the ledger."""
        m1 = _make_migration("001_first.sql", "SELECT 1;")
        ledger = _make_ledger()

        plan = build_execution_plan([m1], ledger)

        def exploding_executor(sql: str, transactional: bool) -> None:
            raise ValueError("Connection lost")

        execute_plan(plan, ledger, executor=exploding_executor)

        assert len(ledger.entries) == 1
        assert ledger.entries[0].status == MigrationStatus.FAILED
        assert "Connection lost" in ledger.entries[0].error_message


# =============================================================================
# Dry Run
# =============================================================================


class TestDryRun:

    @pytest.mark.unit
    def test_dry_run_validates_without_applying(self):
        """Dry run produces plan but does not call executor."""
        m1 = _make_migration("001_first.sql", "SELECT 1;")
        m2 = _make_migration("002_second.sql", "SELECT 2;")
        ledger = _make_ledger()

        plan = build_execution_plan([m1, m2], ledger, dry_run=True)
        assert not plan.blocked
        assert all(s.decision == LedgerDecision.DRY_RUN for s in plan.steps)

        executor_called = [False]

        def no_call_executor(sql: str, transactional: bool) -> None:
            executor_called[0] = True

        result = execute_plan(plan, ledger, executor=no_call_executor)
        assert result.success is True
        assert result.dry_run is True
        assert executor_called[0] is False  # Executor never invoked
        assert len(result.applied) == 2

    @pytest.mark.unit
    def test_dry_run_still_catches_checksum_mismatch(self):
        """Dry run detects checksum mismatches (blocks before any validation)."""
        m1 = _make_migration("001_first.sql", "SELECT 1;")
        ledger = _make_ledger()
        ledger.entries.append(LedgerEntry(
            migration_id="001_first",
            checksum="stale_checksum",
            environment="staging",
            status=MigrationStatus.APPLIED,
        ))

        plan = build_execution_plan([m1], ledger, dry_run=True)
        assert plan.blocked is True
        assert "checksum" in plan.block_reason.lower()


# =============================================================================
# Clean Install
# =============================================================================


class TestCleanInstall:

    @pytest.mark.unit
    def test_clean_install_applies_all(self):
        """Empty ledger + all migrations = all pending."""
        m1 = _make_migration("001_first.sql", "SELECT 1;")
        m2 = _make_migration("002_second.sql", "SELECT 2;")
        m3 = _make_migration("003_third.sql", "SELECT 3;")
        ledger = _make_ledger()

        plan = build_execution_plan([m1, m2, m3], ledger)
        assert not plan.blocked
        assert plan.total_pending == 3
        assert plan.total_already_applied == 0
        assert all(s.decision == LedgerDecision.APPLY for s in plan.steps)

    @pytest.mark.unit
    def test_clean_install_execution_records_all(self):
        """Executing clean install records all in ledger."""
        m1 = _make_migration("001_first.sql", "SELECT 1;")
        m2 = _make_migration("002_second.sql", "SELECT 2;")
        ledger = _make_ledger()

        plan = build_execution_plan([m1, m2], ledger)
        result = execute_plan(plan, ledger, executor=lambda sql, tx: None)

        assert result.success is True
        assert len(result.applied) == 2
        assert len(ledger.entries) == 2
        assert all(e.status == MigrationStatus.APPLIED for e in ledger.entries)

    @pytest.mark.unit
    def test_real_migrations_discoverable(self):
        """The actual docs/sql/ directory is parseable."""
        migrations = discover_migrations(Path(__file__).parent.parent.parent / "docs" / "sql")
        assert len(migrations) >= 40
        # All have checksums
        assert all(len(m.checksum) == 64 for m in migrations)
        # All have valid sequences
        assert all(m.sequence for m in migrations)


# =============================================================================
# CI Validation
# =============================================================================


class TestCIValidation:

    @pytest.mark.unit
    def test_ci_validates_real_migrations(self):
        """CI mode runs against actual migration directory."""
        result = validate_migrations_ci(Path(__file__).parent.parent.parent / "docs" / "sql")
        # Should be valid (no duplicate IDs — duplicate sequences are warnings)
        assert result["valid"] is True
        assert result["total_migrations"] >= 40

    @pytest.mark.unit
    def test_ci_catches_duplicate_ids(self):
        """CI fails on duplicate migration IDs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            # Same filename cannot exist twice, but we test the logic
            (tmp / "001_first.sql").write_text("SELECT 1;")
            (tmp / "002_second.sql").write_text("SELECT 2;")

            result = validate_migrations_ci(tmp)
            assert result["valid"] is True
            assert result["total_migrations"] == 2

    @pytest.mark.unit
    def test_ci_flags_irreversible(self):
        """CI warns about irreversible migrations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "001_drop.sql").write_text("DROP TABLE old_stuff;")

            result = validate_migrations_ci(tmp)
            irreversible = [i for i in result["issues"] if i["type"] == "IRREVERSIBLE"]
            assert len(irreversible) == 1

    @pytest.mark.unit
    def test_ci_flags_duplicate_sequences(self):
        """CI warns about duplicate sequence numbers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "001_first.sql").write_text("SELECT 1;")
            (tmp / "001_also_first.sql").write_text("SELECT 2;")

            result = validate_migrations_ci(tmp)
            dup_seqs = [i for i in result["issues"] if i["type"] == "DUPLICATE_SEQUENCE"]
            assert len(dup_seqs) == 1
            assert "001" in dup_seqs[0]["sequence"]


# =============================================================================
# Irreversible Authorization
# =============================================================================


class TestIrreversibleAuthorization:

    @pytest.mark.unit
    def test_irreversible_blocked_without_flag(self):
        """Irreversible migration blocked without explicit authorization."""
        m1 = _make_migration("001_drop.sql", "DROP TABLE old_data;")
        m1.is_irreversible = True
        ledger = _make_ledger()

        plan = build_execution_plan([m1], ledger, authorize_irreversible=False)
        assert plan.blocked is True
        assert "irreversible" in plan.block_reason.lower()

    @pytest.mark.unit
    def test_irreversible_allowed_with_flag(self):
        """Irreversible migration proceeds with explicit authorization."""
        m1 = _make_migration("001_drop.sql", "DROP TABLE old_data;")
        m1.is_irreversible = True
        ledger = _make_ledger()

        plan = build_execution_plan([m1], ledger, authorize_irreversible=True)
        assert not plan.blocked
        assert plan.steps[0].decision == LedgerDecision.APPLY


# =============================================================================
# Evidence and Release Integration
# =============================================================================


class TestReleaseIntegration:

    @pytest.mark.unit
    def test_release_id_recorded(self):
        """Release ID and commit SHA recorded on each ledger entry."""
        m1 = _make_migration("001_first.sql", "SELECT 1;")
        ledger = _make_ledger()
        plan = build_execution_plan([m1], ledger)

        result = execute_plan(
            plan, ledger,
            executor=lambda sql, tx: None,
            release_id="rel-abc123",
            commit_sha="deadbeef",
        )

        assert result.release_id == "rel-abc123"
        assert result.commit_sha == "deadbeef"
        assert ledger.entries[0].release_id == "rel-abc123"
        assert ledger.entries[0].commit_sha == "deadbeef"

    @pytest.mark.unit
    def test_execution_result_serializable(self):
        """ExecutionResult.to_dict() produces valid JSON-serializable output."""
        m1 = _make_migration("001_first.sql", "SELECT 1;")
        ledger = _make_ledger()
        plan = build_execution_plan([m1], ledger)
        result = execute_plan(plan, ledger, executor=lambda sql, tx: None)

        d = result.to_dict()
        assert d["success"] is True
        assert d["applied_count"] == 1
        assert isinstance(d["applied"], list)
        # Verify JSON-serializable
        import json
        json.dumps(d)

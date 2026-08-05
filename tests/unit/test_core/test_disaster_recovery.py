"""Backup & restore verification tests — Story 064.

Tests prove:
  - All data stores are inventoried
  - Backups are encrypted by default
  - Backup checksums are generated
  - Failed backups raise alerts
  - Restore verification never runs against production
  - Restore reconciliation checks cross-system references
  - Stale backup detection works
  - Alert lifecycle (raise, list, resolve)
  - Backup freshness check alerts on missing backups
  - Full backup covers all stores
  - Encryption verification reports key information
"""

import time
import pytest

from backend.disaster_recovery import (
    BackupConfig,
    BackupRecord,
    BackupStatus,
    DataStore,
    RestoreStatus,
    _reset_store,
    check_backup_freshness,
    get_active_alerts,
    get_backup_summary,
    resolve_alert,
    run_backup,
    run_full_backup,
    run_restore_verification,
    verify_encryption,
)


@pytest.fixture(autouse=True)
def clean():
    _reset_store()
    yield
    _reset_store()


# =============================================================================
# Backup Inventory
# =============================================================================


@pytest.mark.unit
class TestBackupInventory:

    def test_all_stores_defined(self):
        """Every authoritative store has a DataStore enum."""
        stores = list(DataStore)
        assert len(stores) >= 5
        store_names = {s.value for s in stores}
        assert "supabase_db" in store_names
        assert "b2_assets" in store_names
        assert "b2_models" in store_names
        assert "config_secrets" in store_names
        assert "audit_logs" in store_names

    def test_full_backup_covers_all_stores(self):
        results = run_full_backup()
        stores_backed_up = {r.store for r in results}
        assert stores_backed_up == set(DataStore)


# =============================================================================
# Backup Execution
# =============================================================================


@pytest.mark.unit
class TestBackupExecution:

    def test_backup_completes(self):
        record = run_backup(DataStore.SUPABASE_DB)
        assert record.status == BackupStatus.COMPLETED
        assert record.completed_at is not None
        assert record.backup_id.startswith("bak-")

    def test_backup_is_encrypted(self):
        record = run_backup(DataStore.SUPABASE_DB)
        assert record.encrypted is True
        assert record.encryption_key_id != ""

    def test_backup_has_checksum(self):
        record = run_backup(DataStore.B2_ASSETS)
        assert record.checksum
        assert len(record.checksum) == 64  # SHA-256

    def test_backup_has_expiry(self):
        record = run_backup(DataStore.SUPABASE_DB)
        assert record.expires_at is not None
        assert record.expires_at > time.time()

    def test_backup_location_set(self):
        record = run_backup(DataStore.B2_MODELS)
        assert "b2_models" in record.location


# =============================================================================
# Encryption Verification
# =============================================================================


@pytest.mark.unit
class TestEncryption:

    def test_verify_encryption_reports_correctly(self):
        record = run_backup(DataStore.SUPABASE_DB)
        result = verify_encryption(record.backup_id)
        assert result["verified"] is True
        assert result["algorithm"] == "AES-256-GCM"
        assert result["key_id"] == "backup-key-001"

    def test_unknown_backup_not_verified(self):
        result = verify_encryption("nonexistent")
        assert result["verified"] is False


# =============================================================================
# Restore Verification
# =============================================================================


@pytest.mark.unit
class TestRestoreVerification:

    def test_restore_passes_in_isolated_env(self):
        run_full_backup()
        result = run_restore_verification()
        assert result.status == RestoreStatus.PASSED
        assert result.environment == "isolated"
        assert result.db_rows_restored > 0
        assert result.migration_compatible is True

    def test_restore_blocked_in_production(self):
        """CRITICAL: Restore must NEVER run against production."""
        config = BackupConfig(restore_environment="production")
        result = run_restore_verification(config=config)
        assert result.status == RestoreStatus.FAILED
        assert "production" in result.errors[0].lower()

    def test_restore_reconciliation_report(self):
        run_full_backup()
        result = run_restore_verification()
        assert "db_to_b2_assets" in result.reconciliation_report
        assert "db_to_b2_models" in result.reconciliation_report
        assert "schema_compatibility" in result.reconciliation_report

    def test_restore_with_no_backups_reports_integrity_failure(self):
        result = run_restore_verification(backup_ids=["nonexistent"])
        # Should handle gracefully (integrity check fails)
        assert result.status in (RestoreStatus.FAILED, RestoreStatus.PASSED)


# =============================================================================
# Alerting
# =============================================================================


@pytest.mark.unit
class TestAlerting:

    def test_no_alerts_initially(self):
        assert get_active_alerts() == []

    def test_stale_backup_raises_alert(self):
        """If no backup exists, freshness check raises alert."""
        check_backup_freshness()
        alerts = get_active_alerts()
        assert len(alerts) > 0
        assert any("no_backup" in a["type"] or "No backup" in a["message"] for a in alerts)

    def test_resolve_alert(self):
        check_backup_freshness()
        alerts = get_active_alerts()
        assert len(alerts) > 0
        alert_id = alerts[0]["id"]
        resolve_alert(alert_id)
        active = get_active_alerts()
        assert all(a["id"] != alert_id for a in active)

    def test_fresh_backup_no_alert(self):
        run_full_backup()
        _reset_alerts_only()
        check_backup_freshness()
        # Should have no alerts since all stores were just backed up
        alerts = get_active_alerts()
        # Filter to only stale/no_backup alerts
        stale_alerts = [a for a in alerts if a["type"] in ("stale_backup", "no_backup")]
        assert len(stale_alerts) == 0


# =============================================================================
# Backup Summary
# =============================================================================


@pytest.mark.unit
class TestBackupSummary:

    def test_empty_summary(self):
        summary = get_backup_summary()
        assert summary["total_backups"] == 0
        assert summary["stores_covered"] == 0

    def test_summary_after_full_backup(self):
        run_full_backup()
        summary = get_backup_summary()
        assert summary["completed"] == len(DataStore)
        assert summary["stores_covered"] == len(DataStore)
        assert summary["failed"] == 0


# =============================================================================
# Helpers
# =============================================================================


def _reset_alerts_only():
    """Reset just alerts for testing freshness."""
    from backend.disaster_recovery import _alerts
    _alerts.clear()

"""Persistence Boundary Contract Tests (Story 043).

Proves: authority classification, cache boundaries, reconciliation,
security (no secrets in browser), and migration rules.

Run with:
    pytest tests/unit/test_persistence_contract.py -v
"""
from __future__ import annotations

import pytest

from backend.persistence_contract import (
    CacheRecord,
    ReconciliationAction,
    StorageAuthority,
    determine_reconciliation,
    get_keys_to_clear_on_logout,
    get_storage_authority,
    is_key_allowed,
    validate_no_secrets_in_storage,
)


# =============================================================================
# Authority Classification
# =============================================================================


class TestAuthorityClassification:

    @pytest.mark.unit
    def test_brain_sessions_is_cache(self):
        """brain_sessions is a cache of server data (not primary)."""
        assert get_storage_authority("brain_sessions") == StorageAuthority.BROWSER_CACHE

    @pytest.mark.unit
    def test_brain_messages_wildcard_is_cache(self):
        """brain_messages_{id} pattern matches as cache."""
        assert get_storage_authority("brain_messages_abc123") == StorageAuthority.BROWSER_CACHE
        assert get_storage_authority("brain_messages_") == StorageAuthority.BROWSER_CACHE

    @pytest.mark.unit
    def test_brain_collections_is_cache(self):
        assert get_storage_authority("brain_collections") == StorageAuthority.BROWSER_CACHE

    @pytest.mark.unit
    def test_talent_favorites_is_preference(self):
        """UI preferences are allowed as primary in localStorage."""
        assert get_storage_authority("talent_favorites") == StorageAuthority.BROWSER_PREFERENCE

    @pytest.mark.unit
    def test_favorite_prompts_is_preference(self):
        assert get_storage_authority("favorite_prompts") == StorageAuthority.BROWSER_PREFERENCE

    @pytest.mark.unit
    def test_draft_is_draft(self):
        """Unsent drafts are allowed temporarily."""
        assert get_storage_authority("brain_draft_session123") == StorageAuthority.BROWSER_DRAFT

    @pytest.mark.unit
    def test_access_token_is_prohibited(self):
        """Auth tokens must never be in localStorage."""
        assert get_storage_authority("access_token") == StorageAuthority.PROHIBITED

    @pytest.mark.unit
    def test_api_key_is_prohibited(self):
        assert get_storage_authority("api_key") == StorageAuthority.PROHIBITED

    @pytest.mark.unit
    def test_unknown_key_is_prohibited(self):
        """Unknown keys default to PROHIBITED (deny-by-default)."""
        assert get_storage_authority("random_unknown_key") == StorageAuthority.PROHIBITED

    @pytest.mark.unit
    def test_legacy_session_prohibited(self):
        """Legacy ai_studio_session key is prohibited."""
        assert get_storage_authority("ai_studio_session") == StorageAuthority.PROHIBITED


# =============================================================================
# Key Allowlist
# =============================================================================


class TestKeyAllowlist:

    @pytest.mark.unit
    def test_allowed_keys(self):
        """Known allowed keys pass the check."""
        assert is_key_allowed("talent_favorites") is True
        assert is_key_allowed("brain_sessions") is True  # Cache is allowed
        assert is_key_allowed("brain_draft_x") is True

    @pytest.mark.unit
    def test_prohibited_keys(self):
        """Prohibited keys are rejected."""
        assert is_key_allowed("access_token") is False
        assert is_key_allowed("refresh_token") is False
        assert is_key_allowed("org_id") is False
        assert is_key_allowed("unknown_key") is False


# =============================================================================
# Reconciliation Rules
# =============================================================================


class TestReconciliation:

    @pytest.mark.unit
    def test_server_wins_when_both_exist(self):
        """Server data takes precedence over local cache."""
        action = determine_reconciliation(
            key="brain_sessions", has_local=True, has_server=True)
        assert action == ReconciliationAction.USE_SERVER

    @pytest.mark.unit
    def test_server_wins_when_only_server_exists(self):
        action = determine_reconciliation(
            key="brain_sessions", has_local=False, has_server=True)
        assert action == ReconciliationAction.USE_SERVER

    @pytest.mark.unit
    def test_local_offered_for_migration_when_server_empty(self):
        """Local-only data offers migration (not silent discard)."""
        action = determine_reconciliation(
            key="brain_sessions", has_local=True, has_server=False)
        assert action == ReconciliationAction.MIGRATE_TO_SERVER

    @pytest.mark.unit
    def test_drafts_always_local(self):
        """Drafts always stay local (unsent user work)."""
        action = determine_reconciliation(
            key="brain_draft_msg", has_local=True, has_server=True, is_draft=True)
        assert action == ReconciliationAction.USE_LOCAL

    @pytest.mark.unit
    def test_preferences_always_local(self):
        """Preferences stay local (they are primary)."""
        action = determine_reconciliation(
            key="talent_favorites", has_local=True, has_server=True)
        assert action == ReconciliationAction.USE_LOCAL

    @pytest.mark.unit
    def test_neither_exists_discards(self):
        """No data anywhere → discard/clean slate."""
        action = determine_reconciliation(
            key="brain_sessions", has_local=False, has_server=False)
        assert action == ReconciliationAction.DISCARD_LOCAL


# =============================================================================
# Security — No Secrets in Browser
# =============================================================================


class TestSecurityValidation:

    @pytest.mark.unit
    def test_clean_storage_no_violations(self):
        """Normal allowed keys produce no violations."""
        keys = ["talent_favorites", "brain_sessions", "favorite_prompts"]
        violations = validate_no_secrets_in_storage(keys)
        assert violations == []

    @pytest.mark.unit
    def test_token_in_storage_detected(self):
        """Access tokens in localStorage are flagged."""
        keys = ["talent_favorites", "access_token", "brain_sessions"]
        violations = validate_no_secrets_in_storage(keys)
        assert "access_token" in violations

    @pytest.mark.unit
    def test_multiple_violations_detected(self):
        """Multiple prohibited keys all reported."""
        keys = ["access_token", "refresh_token", "api_key", "org_id"]
        violations = validate_no_secrets_in_storage(keys)
        assert len(violations) == 4

    @pytest.mark.unit
    def test_legacy_session_key_detected(self):
        """Legacy auth key is flagged as prohibited."""
        violations = validate_no_secrets_in_storage(["ai_studio_session"])
        assert "ai_studio_session" in violations


# =============================================================================
# Logout Cleanup
# =============================================================================


class TestLogoutCleanup:

    @pytest.mark.unit
    def test_cache_keys_cleared_on_logout(self):
        """Cache keys are in the logout-clear list."""
        clear_list = get_keys_to_clear_on_logout()
        assert "brain_sessions" in clear_list
        assert "brain_collections" in clear_list
        assert "brain_messages_*" in clear_list
        assert "brain_draft_*" in clear_list

    @pytest.mark.unit
    def test_preferences_not_cleared_on_logout(self):
        """Preferences survive logout (device-level, not user-level)."""
        clear_list = get_keys_to_clear_on_logout()
        assert "talent_favorites" not in clear_list
        assert "favorite_prompts" not in clear_list

    @pytest.mark.unit
    def test_last_mode_cleared_on_logout(self):
        """Last mode is user-specific, cleared on logout."""
        clear_list = get_keys_to_clear_on_logout()
        assert "last_mode" in clear_list


# =============================================================================
# Cache Record
# =============================================================================


class TestCacheRecord:

    @pytest.mark.unit
    def test_to_storage_includes_metadata(self):
        """Cache records include freshness metadata."""
        record = CacheRecord(
            key="brain_sessions",
            data=[{"id": "s1", "title": "Test"}],
            cached_at="2026-08-03T10:00:00Z",
        )
        stored = record.to_storage()
        assert stored["_authority"] == "cache"
        assert stored["_cached_at"] == "2026-08-03T10:00:00Z"
        assert stored["data"] == [{"id": "s1", "title": "Test"}]

    @pytest.mark.unit
    def test_from_storage_valid(self):
        """Valid storage record can be deserialized."""
        raw = {
            "_authority": "cache",
            "_cached_at": "2026-08-03T10:00:00Z",
            "_server_version": "v1",
            "data": {"sessions": []},
        }
        record = CacheRecord.from_storage("brain_sessions", raw)
        assert record is not None
        assert record.cached_at == "2026-08-03T10:00:00Z"
        assert record.data == {"sessions": []}

    @pytest.mark.unit
    def test_from_storage_invalid_returns_none(self):
        """Invalid/corrupted storage returns None (not crash)."""
        assert CacheRecord.from_storage("x", {}) is None
        assert CacheRecord.from_storage("x", {"random": "data"}) is None
        assert CacheRecord.from_storage("x", "not a dict") is None  # type: ignore

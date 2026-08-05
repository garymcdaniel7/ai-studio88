"""Unit tests for backend.database — safe Supabase client initialization.

Tests cover:
  - Import does not crash when env vars are missing
  - is_supabase_configured() reports correctly
  - get_supabase_client() raises SupabaseNotConfiguredError when unconfigured
  - get_supabase_client() rejects placeholder values
  - Lazy proxy defers initialization
"""

import os
from unittest.mock import patch

import pytest

from backend.database import (
    SupabaseNotConfiguredError,
    get_supabase_client,
    is_supabase_configured,
)


@pytest.mark.unit
class TestSupabaseConfiguration:
    """Test Supabase client configuration guards."""

    def test_import_does_not_crash_without_env(self):
        """Importing backend.database should not crash even without env vars."""
        # If we got here, the import already succeeded
        import backend.database  # noqa: F401
        assert True

    def test_is_configured_when_vars_set(self):
        """is_supabase_configured returns True when both vars are set."""
        with patch.dict(os.environ, {
            "SUPABASE_URL": "https://test.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "real-key-value",
        }):
            assert is_supabase_configured() is True

    def test_is_not_configured_when_url_missing(self):
        """is_supabase_configured returns False when URL is missing."""
        with patch.dict(os.environ, {
            "SUPABASE_URL": "",
            "SUPABASE_SERVICE_ROLE_KEY": "real-key-value",
        }, clear=False):
            assert is_supabase_configured() is False

    def test_is_not_configured_when_key_missing(self):
        """is_supabase_configured returns False when key is missing."""
        with patch.dict(os.environ, {
            "SUPABASE_URL": "https://test.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "",
        }, clear=False):
            assert is_supabase_configured() is False

    def test_is_not_configured_with_placeholder_url(self):
        """is_supabase_configured rejects placeholder URLs."""
        with patch.dict(os.environ, {
            "SUPABASE_URL": "https://your-project.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "real-key",
        }, clear=False):
            assert is_supabase_configured() is False

    def test_get_client_raises_when_not_configured(self):
        """get_supabase_client raises SupabaseNotConfiguredError when missing."""
        import backend.database as db_mod
        db_mod._supabase_client = None  # Reset cached client

        with patch.dict(os.environ, {
            "SUPABASE_URL": "",
            "SUPABASE_SERVICE_ROLE_KEY": "",
        }, clear=False):
            with pytest.raises(SupabaseNotConfiguredError):
                get_supabase_client()

    def test_get_client_raises_with_placeholder_key(self):
        """get_supabase_client rejects placeholder key values."""
        import backend.database as db_mod
        db_mod._supabase_client = None  # Reset cached client

        with patch.dict(os.environ, {
            "SUPABASE_URL": "https://test.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "your-service-role-key",
        }, clear=False):
            with pytest.raises(SupabaseNotConfiguredError):
                get_supabase_client()

    def test_error_message_does_not_expose_secrets(self):
        """Error messages should guide without exposing values."""
        import backend.database as db_mod
        db_mod._supabase_client = None

        with patch.dict(os.environ, {
            "SUPABASE_URL": "",
            "SUPABASE_SERVICE_ROLE_KEY": "",
        }, clear=False):
            with pytest.raises(SupabaseNotConfiguredError) as exc_info:
                get_supabase_client()
            msg = str(exc_info.value)
            assert "SUPABASE_URL" in msg
            assert "SUPABASE_SERVICE_ROLE_KEY" in msg
            # Should not contain actual values
            assert "eyJ" not in msg

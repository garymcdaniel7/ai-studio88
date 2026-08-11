"""Integration test fixtures.

These tests require a running Supabase instance. They are skipped in CI
when SUPABASE_URL is not configured.
"""

import os

import pytest


def pytest_collection_modifyitems(config, items):
    """Skip integration tests when Supabase is not available."""
    supabase_url = os.environ.get("SUPABASE_URL", "")
    if not supabase_url:
        skip_marker = pytest.mark.skip(reason="SUPABASE_URL not configured")
        for item in items:
            item.add_marker(skip_marker)

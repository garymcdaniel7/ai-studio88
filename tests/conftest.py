"""Test configuration and fixtures for AI Studio.

Run tests with:
    pytest tests/unit/ -v
    pytest tests/ --cov=backend --cov-report=term-missing
"""
from __future__ import annotations

import os
import sys

import pytest

# Ensure backend is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def api_client():
    """Create a test client for the FastAPI app."""
    from fastapi.testclient import TestClient
    from backend.main import app
    return TestClient(app)


@pytest.fixture
def mock_supabase(mocker):
    """Mock the Supabase client for unit tests."""
    mock = mocker.patch("backend.database.supabase")
    return mock

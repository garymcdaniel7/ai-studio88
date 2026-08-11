"""Root test configuration and shared fixtures."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

# Ensure the backend package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    """Reset the settings cache before each test to allow env overrides."""
    from app.core.config import reset_settings

    reset_settings()
    yield
    reset_settings()


@pytest.fixture
def mock_env_local():
    """Set environment to local with auth_dev_mode disabled."""
    env = {
        "APP_ENV": "local",
        "AUTH_DEV_MODE": "false",
        "SUPABASE_JWT_SECRET": "test-jwt-secret-at-least-32-chars-long",
        "SUPABASE_URL": "http://localhost:54321",
        "SUPABASE_SERVICE_ROLE_KEY": "test-service-key",
    }
    with patch.dict(os.environ, env, clear=False):
        yield env


@pytest.fixture
def mock_env_production():
    """Set environment to production with required config."""
    env = {
        "APP_ENV": "production",
        "AUTH_DEV_MODE": "false",
        "AUTH_REQUIRED": "true",
        "DEBUG": "false",
        "SECRET_KEY": "a" * 64,
        "SUPABASE_URL": "https://project.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "real-service-role-key-here",
        "SUPABASE_JWT_SECRET": "real-jwt-secret-at-least-32-chars-long",
        "SUPABASE_ANON_KEY": "real-anon-key-here",
        "B2_KEY_ID": "real-b2-key-id",
        "B2_APPLICATION_KEY": "real-b2-app-key",
        "DATABASE_URL": "postgres://host:5432/db",
        "REDIS_URL": "redis://redis-host:6379",
        "ALLOWED_ORIGINS": "https://app.example.com",
        "GENERATION_PROVIDER": "comfyui",
        "API_BASE_URL": "https://api.example.com",
    }
    with patch.dict(os.environ, env, clear=False):
        yield env

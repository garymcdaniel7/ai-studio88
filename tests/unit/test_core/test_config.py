"""Unit tests for backend.app.core.config — environment profiles and validation.

Tests cover:
  - Valid local/test profile startup
  - Production rejects placeholder secrets
  - Production rejects localhost dependencies
  - Production rejects simulation modes
  - Production rejects debug=true
  - Production rejects auth_required=false
  - Production rejects short secrets (<16 chars)
  - Production rejects missing Credential Broker configuration
  - Optional capability unavailable is allowed
  - Capability readiness reports correctly
  - Secret redaction (no values in error messages)
  - Degraded mode starts with warnings for non-critical services
"""

import os
from unittest.mock import patch

import pytest

from backend.app.core.config import (
    CapabilityStatus,
    Settings,
    _MIN_SECRET_LENGTH,
    _is_localhost,
    _is_placeholder,
    _is_short_secret,
    reset_settings,
)


# =============================================================================
# Helpers
# =============================================================================


def _base_env(**overrides: str) -> dict[str, str]:
    """Return a minimal valid local environment for testing."""
    base = {
        "APP_ENV": "local",
        "SECRET_KEY": "test-secret-key-that-is-at-least-32-chars-long",
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_ANON_KEY": "test-anon-key-value",
        "SUPABASE_SERVICE_ROLE_KEY": "test-service-role-key",
        "SUPABASE_JWT_SECRET": "test-jwt-secret-value-abc123",
        "DATABASE_URL": "postgresql://postgres:pass@db.test.supabase.co:5432/postgres",
        "B2_KEY_ID": "test-b2-key",
        "B2_APPLICATION_KEY": "test-b2-app-key",
        "B2_BUCKET_NAME": "test-bucket",
        "REDIS_URL": "redis://localhost:6379/0",
        "ALLOWED_ORIGINS": "http://localhost:3000",
        "DEBUG": "true",
    }
    base.update(overrides)
    return base


def _prod_env(**overrides: str) -> dict[str, str]:
    """Return a minimal valid production environment."""
    base = {
        "APP_ENV": "production",
        "SECRET_KEY": "real-production-secret-key-64chars-0123456789abcdef0123456789abcd",
        "SUPABASE_URL": "https://prod.supabase.co",
        "SUPABASE_ANON_KEY": "real-anon-key-production",
        "SUPABASE_SERVICE_ROLE_KEY": "real-service-role-key-production",
        "SUPABASE_JWT_SECRET": "real-jwt-secret-production-value",
        "DATABASE_URL": "postgresql://postgres:pass@db.prod.supabase.co:5432/postgres",
        "B2_KEY_ID": "real-b2-key-prod",
        "B2_APPLICATION_KEY": "real-b2-app-key-prod",
        "B2_BUCKET_NAME": "prod-bucket",
        "REDIS_URL": "redis://redis.internal:6379/0",
        "API_BASE_URL": "https://api.ai-studio.com",
        "ALLOWED_ORIGINS": "https://app.ai-studio.com",
        "DEBUG": "false",
        "AUTH_REQUIRED": "true",
        "GENERATION_PROVIDER": "comfyui",
        "VAST_API_KEY": "real-vast-key-production",
        "TRAINING_PROVIDER": "vast",
        "VOICE_PROVIDER": "elevenlabs",
        "ELEVENLABS_API_KEY": "real-el-key",
        "ELEVENLABS_LIVE": "true",
        "CREDENTIAL_BROKER_URL": "https://broker.internal:9000",
    }
    base.update(overrides)
    return base


# =============================================================================
# Placeholder Detection
# =============================================================================


@pytest.mark.unit
class TestPlaceholderDetection:
    """Test _is_placeholder helper."""

    def test_empty_string(self):
        assert _is_placeholder("") is True

    def test_whitespace_only(self):
        assert _is_placeholder("   ") is True

    def test_placeholder_prefix(self):
        assert _is_placeholder("placeholder-jwt-secret") is True

    def test_your_prefix(self):
        assert _is_placeholder("your-stripe-secret-key") is True

    def test_change_me(self):
        assert _is_placeholder("change_me_generate_with_openssl") is True

    def test_changeme_exact(self):
        assert _is_placeholder("changeme") is True

    def test_your_key_here(self):
        assert _is_placeholder("your-key-here") is True

    def test_xxx(self):
        assert _is_placeholder("xxx") is True

    def test_sk_test_your(self):
        assert _is_placeholder("sk_test_your-stripe-key") is True

    def test_real_value(self):
        assert _is_placeholder("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9") is False

    def test_real_hex_key(self):
        assert _is_placeholder("08339a2465a8084fd99769920704d995") is False


# =============================================================================
# Localhost Detection
# =============================================================================


@pytest.mark.unit
class TestLocalhostDetection:
    """Test _is_localhost helper."""

    def test_localhost(self):
        assert _is_localhost("http://localhost:8000") is True

    def test_127(self):
        assert _is_localhost("http://127.0.0.1:8000") is True

    def test_0000(self):
        assert _is_localhost("http://0.0.0.0:8000") is True

    def test_real_url(self):
        assert _is_localhost("https://api.production.com") is False

    def test_redis_internal(self):
        assert _is_localhost("redis://redis.internal:6379") is False


# =============================================================================
# Local Profile (valid)
# =============================================================================


@pytest.mark.unit
class TestLocalProfile:
    """Test local profile loads without errors."""

    def test_local_loads_successfully(self):
        """Local profile should accept dev defaults without error."""
        env = _base_env()
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()  # type: ignore[call-arg]
            assert settings.app_env == "local"
            assert settings.is_local is True
            assert settings.is_production is False

    def test_development_alias(self):
        """'development' should normalize to 'local'."""
        env = _base_env(APP_ENV="development")
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()  # type: ignore[call-arg]
            assert settings.app_env == "local"
            assert settings.is_local is True

    def test_local_allows_simulation(self):
        """Simulation mode is fine in local."""
        env = _base_env(GENERATION_PROVIDER="simulation")
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()  # type: ignore[call-arg]
            assert settings.generation_provider == "simulation"

    def test_local_allows_debug(self):
        """Debug is fine in local."""
        env = _base_env(DEBUG="true")
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()  # type: ignore[call-arg]
            assert settings.debug is True


# =============================================================================
# Production Profile (validation)
# =============================================================================


@pytest.mark.unit
class TestProductionProfile:
    """Test production profile rejects unsafe configuration."""

    def test_valid_production_loads(self):
        """A fully configured production env should load."""
        env = _prod_env()
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()  # type: ignore[call-arg]
            assert settings.app_env == "production"
            assert settings.is_production is True

    def test_rejects_placeholder_secret_key(self):
        """Production rejects placeholder SECRET_KEY."""
        env = _prod_env(SECRET_KEY="change_me_generate_with_openssl_rand_hex_32")
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValueError, match="SECRET_KEY contains a placeholder"):
                Settings()  # type: ignore[call-arg]

    def test_rejects_missing_secret_key(self):
        """Production rejects empty SECRET_KEY."""
        env = _prod_env(SECRET_KEY="")
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValueError, match="SECRET_KEY is required"):
                Settings()  # type: ignore[call-arg]

    def test_rejects_short_secret_key(self):
        """Production rejects SECRET_KEY shorter than 32 chars."""
        env = _prod_env(SECRET_KEY="too-short-key")
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValueError, match="SECRET_KEY must be at least 32"):
                Settings()  # type: ignore[call-arg]

    def test_rejects_debug_true(self):
        """Production rejects DEBUG=true."""
        env = _prod_env(DEBUG="true")
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValueError, match="DEBUG must be false"):
                Settings()  # type: ignore[call-arg]

    def test_rejects_auth_required_false(self):
        """Production rejects AUTH_REQUIRED=false."""
        env = _prod_env(AUTH_REQUIRED="false")
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValueError, match="AUTH_REQUIRED must be true"):
                Settings()  # type: ignore[call-arg]

    def test_rejects_localhost_redis(self):
        """Production rejects localhost Redis."""
        env = _prod_env(REDIS_URL="redis://localhost:6379/0")
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValueError, match="REDIS_URL points to localhost"):
                Settings()  # type: ignore[call-arg]

    def test_rejects_localhost_api_url(self):
        """Production rejects localhost API_BASE_URL."""
        env = _prod_env(API_BASE_URL="http://localhost:8000")
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValueError, match="API_BASE_URL points to localhost"):
                Settings()  # type: ignore[call-arg]

    def test_rejects_simulation_generation(self):
        """Production rejects simulation generation provider."""
        env = _prod_env(GENERATION_PROVIDER="simulation")
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValueError, match="GENERATION_PROVIDER cannot be 'simulation'"):
                Settings()  # type: ignore[call-arg]

    def test_rejects_missing_b2_key(self):
        """Production rejects missing B2 credentials."""
        env = _prod_env(B2_KEY_ID="", B2_APPLICATION_KEY="")
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValueError, match="B2_KEY_ID is required"):
                Settings()  # type: ignore[call-arg]

    def test_rejects_wildcard_origins(self):
        """Production rejects wildcard CORS origins."""
        env = _prod_env(ALLOWED_ORIGINS="*")
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValueError, match="ALLOWED_ORIGINS cannot contain"):
                Settings()  # type: ignore[call-arg]

    def test_rejects_no_gpu_with_comfyui(self):
        """Production with comfyui generation needs a GPU provider key."""
        env = _prod_env(
            GENERATION_PROVIDER="comfyui",
            VAST_API_KEY="",
            VASTAI_API_KEY="",
            RUNPOD_API_KEY="",
        )
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValueError, match="GPU provider"):
                Settings()  # type: ignore[call-arg]


# =============================================================================
# Capability Readiness
# =============================================================================


@pytest.mark.unit
class TestCapabilityReadiness:
    """Test capability status reporting."""

    def test_local_reports_capabilities(self):
        """Local profile should report all capabilities."""
        env = _base_env()
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()  # type: ignore[call-arg]
            caps = settings.get_capability_status()
            assert len(caps) >= 8
            names = [c.name for c in caps]
            assert "database" in names
            assert "storage" in names
            assert "gpu" in names
            assert "llm" in names

    def test_configured_database(self):
        """Database should be CONFIGURED when URL is set."""
        env = _base_env()
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()  # type: ignore[call-arg]
            caps = {c.name: c for c in settings.get_capability_status()}
            assert caps["database"].status == CapabilityStatus.CONFIGURED

    def test_unavailable_gpu_when_no_key(self):
        """GPU should be UNAVAILABLE when no API key is set."""
        env = _base_env(VAST_API_KEY="", VASTAI_API_KEY="", RUNPOD_API_KEY="")
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()  # type: ignore[call-arg]
            caps = {c.name: c for c in settings.get_capability_status()}
            assert caps["gpu"].status == CapabilityStatus.UNAVAILABLE

    def test_degraded_generation_in_simulation(self):
        """Generation should be DEGRADED in simulation mode."""
        env = _base_env(GENERATION_PROVIDER="simulation")
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()  # type: ignore[call-arg]
            caps = {c.name: c for c in settings.get_capability_status()}
            assert caps["generation"].status == CapabilityStatus.DEGRADED

    def test_readiness_summary_no_secrets(self):
        """Readiness summary must not contain secret values."""
        env = _base_env()
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()  # type: ignore[call-arg]
            summary = settings.get_readiness_summary()
            summary_str = str(summary)
            # Ensure no actual secrets leak
            assert "test-service-role-key" not in summary_str
            assert "test-jwt-secret" not in summary_str
            assert "test-b2-app-key" not in summary_str

    def test_readiness_ready_when_critical_configured(self):
        """Ready=True when database and auth are configured."""
        env = _base_env()
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()  # type: ignore[call-arg]
            summary = settings.get_readiness_summary()
            assert summary["ready"] is True

    def test_readiness_not_ready_when_database_missing(self):
        """Ready=False when database is not configured."""
        env = _base_env(SUPABASE_URL="")
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()  # type: ignore[call-arg]
            summary = settings.get_readiness_summary()
            assert summary["ready"] is False


# =============================================================================
# Test Profile
# =============================================================================


@pytest.mark.unit
class TestTestProfile:
    """Test the 'test' profile."""

    def test_test_profile_loads(self):
        """Test profile should load without production constraints."""
        env = _base_env(APP_ENV="test")
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()  # type: ignore[call-arg]
            assert settings.app_env == "test"
            assert settings.is_test is True


# =============================================================================
# Error Message Safety
# =============================================================================


@pytest.mark.unit
class TestErrorMessageSafety:
    """Ensure error messages don't expose secret values."""

    def test_production_error_no_secret_values(self):
        """Production validation errors should not contain actual secret values."""
        env = _prod_env(SECRET_KEY="")
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValueError) as exc_info:
                Settings()  # type: ignore[call-arg]
            error_msg = str(exc_info.value)
            # Should NOT contain the actual values from env
            assert "real-service-role-key-production" not in error_msg
            assert "real-jwt-secret-production-value" not in error_msg
            # Should contain helpful variable names
            assert "SECRET_KEY" in error_msg


# =============================================================================
# Short Secret Detection
# =============================================================================


@pytest.mark.unit
class TestShortSecretDetection:
    """Test _is_short_secret helper and production validation for short values."""

    def test_short_value(self):
        """Values shorter than _MIN_SECRET_LENGTH are detected."""
        assert _is_short_secret("abc") is True
        assert _is_short_secret("short") is True
        assert _is_short_secret("a" * 15) is True

    def test_minimum_length_passes(self):
        """Values at or above minimum length pass."""
        assert _is_short_secret("a" * 16) is False
        assert _is_short_secret("a" * 32) is False

    def test_empty_not_short(self):
        """Empty strings handled by _is_placeholder, not _is_short_secret."""
        assert _is_short_secret("") is False

    def test_production_rejects_short_jwt_secret(self):
        """Production rejects SUPABASE_JWT_SECRET shorter than 16 chars."""
        env = _prod_env(SUPABASE_JWT_SECRET="short123")
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValueError, match="SUPABASE_JWT_SECRET is too short"):
                Settings()  # type: ignore[call-arg]

    def test_production_rejects_short_service_role_key(self):
        """Production rejects SUPABASE_SERVICE_ROLE_KEY shorter than 16 chars."""
        env = _prod_env(SUPABASE_SERVICE_ROLE_KEY="tiny")
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValueError, match="SUPABASE_SERVICE_ROLE_KEY is too short"):
                Settings()  # type: ignore[call-arg]

    def test_production_rejects_short_supabase_url(self):
        """Production rejects SUPABASE_URL shorter than 16 chars."""
        env = _prod_env(SUPABASE_URL="http://x.io")
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValueError, match="SUPABASE_URL is too short"):
                Settings()  # type: ignore[call-arg]

    def test_minimum_secret_length_constant(self):
        """Minimum secret length is 16 as per R9 spec."""
        assert _MIN_SECRET_LENGTH == 16


# =============================================================================
# Credential Broker Validation
# =============================================================================


@pytest.mark.unit
class TestCredentialBrokerValidation:
    """Test Credential Broker configuration validation per R9.7."""

    def test_production_rejects_missing_credential_broker(self):
        """Production rejects missing Credential Broker configuration."""
        env = _prod_env(CREDENTIAL_BROKER_URL="", CREDENTIAL_BROKER_ENABLED="false")
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValueError, match="CREDENTIAL_BROKER"):
                Settings()  # type: ignore[call-arg]

    def test_production_accepts_credential_broker_url(self):
        """Production accepts when CREDENTIAL_BROKER_URL is set."""
        env = _prod_env(CREDENTIAL_BROKER_URL="https://broker.internal:9000")
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()  # type: ignore[call-arg]
            assert settings.credential_broker_configured is True

    def test_production_accepts_credential_broker_enabled(self):
        """Production accepts when CREDENTIAL_BROKER_ENABLED is true."""
        env = _prod_env(CREDENTIAL_BROKER_URL="", CREDENTIAL_BROKER_ENABLED="true")
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()  # type: ignore[call-arg]
            assert settings.credential_broker_configured is True

    def test_local_allows_missing_credential_broker(self):
        """Local profile allows missing Credential Broker (dev convenience)."""
        env = _base_env(CREDENTIAL_BROKER_URL="", CREDENTIAL_BROKER_ENABLED="false")
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()  # type: ignore[call-arg]
            # In local/test mode, credential_broker_configured returns True
            assert settings.credential_broker_configured is True


# =============================================================================
# Degraded Mode for Non-Critical Services
# =============================================================================


@pytest.mark.unit
class TestDegradedMode:
    """Test degraded mode warnings for non-critical services."""

    def test_warns_when_gpu_unavailable(self):
        """Platform starts with warning when GPU provider is not configured."""
        env = _base_env(VAST_API_KEY="", VASTAI_API_KEY="", RUNPOD_API_KEY="")
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()  # type: ignore[call-arg]
            warnings = settings.non_critical_service_warnings
            assert any("GPU" in w for w in warnings)

    def test_warns_when_voice_unavailable(self):
        """Platform starts with warning when voice provider is not configured."""
        env = _base_env(VOICE_PROVIDER="simulation", ELEVENLABS_API_KEY="")
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()  # type: ignore[call-arg]
            warnings = settings.non_critical_service_warnings
            assert any("voice" in w.lower() or "Voice" in w for w in warnings)

    def test_warns_when_training_in_simulation(self):
        """Platform starts with warning when training is in simulation mode."""
        env = _base_env(TRAINING_PROVIDER="simulation")
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()  # type: ignore[call-arg]
            warnings = settings.non_critical_service_warnings
            assert any("training" in w.lower() or "Training" in w for w in warnings)

    def test_no_warnings_when_all_configured(self):
        """No warnings when all non-critical services are configured."""
        env = _base_env(
            VAST_API_KEY="real-key-value-here",
            VOICE_PROVIDER="elevenlabs",
            ELEVENLABS_API_KEY="real-elevenlabs-key",
            TRAINING_PROVIDER="vast",
            BRAIN_PROVIDER="ollama",
        )
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()  # type: ignore[call-arg]
            warnings = settings.non_critical_service_warnings
            assert len(warnings) == 0

    def test_local_starts_despite_warnings(self):
        """Local env starts fine even with multiple unavailable services."""
        env = _base_env(
            VAST_API_KEY="",
            VASTAI_API_KEY="",
            RUNPOD_API_KEY="",
            VOICE_PROVIDER="simulation",
            TRAINING_PROVIDER="simulation",
            ELEVENLABS_API_KEY="",
        )
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()  # type: ignore[call-arg]
            # Should load without raising
            assert settings.is_local is True
            # But should produce warnings
            assert len(settings.non_critical_service_warnings) > 0


# =============================================================================
# AUTH_DEV_MODE in Production (explicit test)
# =============================================================================


@pytest.mark.unit
class TestAuthDevModeProduction:
    """Test AUTH_DEV_MODE is rejected in production/staging per R1.5."""

    def test_production_rejects_auth_dev_mode(self):
        """Production refuses to start with AUTH_DEV_MODE=true."""
        env = _prod_env(AUTH_DEV_MODE="true")
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValueError, match="AUTH_DEV_MODE"):
                Settings()  # type: ignore[call-arg]

    def test_staging_rejects_auth_dev_mode(self):
        """Staging refuses to start with AUTH_DEV_MODE=true."""
        env = _prod_env(APP_ENV="staging", AUTH_DEV_MODE="true")
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValueError, match="AUTH_DEV_MODE"):
                Settings()  # type: ignore[call-arg]

    def test_local_allows_auth_dev_mode(self):
        """Local allows AUTH_DEV_MODE=true (dev convenience)."""
        env = _base_env(AUTH_DEV_MODE="true")
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()  # type: ignore[call-arg]
            assert settings.auth_dev_mode is True

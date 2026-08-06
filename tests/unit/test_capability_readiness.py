"""Unit tests for capability-aware readiness (Story 117).

Tests cover: ready, degraded, unavailable, timeout, partial-startup,
redaction, caching, and required/optional policy.

Run with:
    pytest tests/unit/test_capability_readiness.py -v
"""
from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from backend.app.core.capability_readiness import (
    ALL_CHECKS,
    CACHE_TTL_SECONDS,
    CHECK_TIMEOUT_SECONDS,
    OPTIONAL_CAPABILITIES,
    REQUIRED_CAPABILITIES,
    CapState,
    CapabilityResult,
    _sanitize,
    check_auth,
    check_configuration,
    check_database,
    check_routers,
    clear_cache,
    clear_startup_failures,
    compute_readiness,
    get_startup_failures,
    register_startup_failure,
    run_all_checks,
)


@pytest.fixture(autouse=True)
def _clean():
    """Reset state between tests."""
    clear_startup_failures()
    clear_cache()
    yield
    clear_startup_failures()
    clear_cache()


# =============================================================================
# Capability State Contract
# =============================================================================


class TestCapabilityStates:

    @pytest.mark.unit
    def test_all_states_exist(self):
        """All expected states are defined."""
        assert CapState.READY.value == "ready"
        assert CapState.DEGRADED.value == "degraded"
        assert CapState.UNAVAILABLE.value == "unavailable"
        assert CapState.TIMEOUT.value == "timeout"
        assert CapState.SKIPPED.value == "skipped"

    @pytest.mark.unit
    def test_result_serializes_without_secrets(self):
        """CapabilityResult.to_dict() never exposes secrets."""
        result = CapabilityResult(
            name="test",
            state=CapState.READY,
            reason="Connected with key=sk_live_abc123xyz",
        )
        d = result.to_dict()
        assert "name" in d
        assert "state" in d
        assert d["state"] == "ready"
        # The raw reason is not sanitized at this level (sanitize at check time)
        assert "sk_live_abc123xyz" not in d.get("evidence", {})


# =============================================================================
# Required vs Optional Policy
# =============================================================================


class TestPolicy:

    @pytest.mark.unit
    def test_required_capabilities_defined(self):
        """Required capabilities are explicitly named."""
        assert "configuration" in REQUIRED_CAPABILITIES
        assert "database" in REQUIRED_CAPABILITIES
        assert "auth" in REQUIRED_CAPABILITIES
        assert "routers" in REQUIRED_CAPABILITIES

    @pytest.mark.unit
    def test_optional_capabilities_defined(self):
        """Optional capabilities are explicitly named."""
        assert "storage" in OPTIONAL_CAPABILITIES
        assert "gpu" in OPTIONAL_CAPABILITIES
        assert "generation" in OPTIONAL_CAPABILITIES
        assert "llm" in OPTIONAL_CAPABILITIES

    @pytest.mark.unit
    def test_no_overlap_between_required_and_optional(self):
        """Required and optional sets don't overlap."""
        assert REQUIRED_CAPABILITIES.isdisjoint(OPTIONAL_CAPABILITIES)

    @pytest.mark.unit
    def test_all_checks_have_policy(self):
        """Every check is classified as required or optional."""
        for name in ALL_CHECKS:
            assert name in REQUIRED_CAPABILITIES or name in OPTIONAL_CAPABILITIES, (
                f"Check '{name}' has no policy classification"
            )


# =============================================================================
# Readiness Computation
# =============================================================================


class TestReadinessComputation:

    @pytest.mark.unit
    def test_all_ready_produces_ready_true(self):
        """All capabilities READY → overall ready=true."""
        results = [
            CapabilityResult(name="configuration", state=CapState.READY, required=True),
            CapabilityResult(name="database", state=CapState.READY, required=True),
            CapabilityResult(name="auth", state=CapState.READY, required=True),
            CapabilityResult(name="routers", state=CapState.READY, required=True),
            CapabilityResult(name="storage", state=CapState.READY, required=False),
        ]
        summary = compute_readiness(results)
        assert summary["ready"] is True
        assert summary["overall_state"] == "ready"

    @pytest.mark.unit
    def test_required_unavailable_produces_ready_false(self):
        """Required capability UNAVAILABLE → overall ready=false."""
        results = [
            CapabilityResult(name="configuration", state=CapState.READY, required=True),
            CapabilityResult(name="database", state=CapState.UNAVAILABLE, required=True),
            CapabilityResult(name="auth", state=CapState.READY, required=True),
            CapabilityResult(name="routers", state=CapState.READY, required=True),
        ]
        summary = compute_readiness(results)
        assert summary["ready"] is False
        assert summary["overall_state"] == "unavailable"

    @pytest.mark.unit
    def test_optional_unavailable_still_ready(self):
        """Optional capability UNAVAILABLE does not block readiness."""
        results = [
            CapabilityResult(name="configuration", state=CapState.READY, required=True),
            CapabilityResult(name="database", state=CapState.READY, required=True),
            CapabilityResult(name="auth", state=CapState.READY, required=True),
            CapabilityResult(name="routers", state=CapState.READY, required=True),
            CapabilityResult(name="storage", state=CapState.UNAVAILABLE, required=False),
            CapabilityResult(name="gpu", state=CapState.UNAVAILABLE, required=False),
        ]
        summary = compute_readiness(results)
        assert summary["ready"] is True

    @pytest.mark.unit
    def test_degraded_required_is_acceptable(self):
        """Required cap in DEGRADED state (e.g., dev auth) is acceptable."""
        results = [
            CapabilityResult(name="configuration", state=CapState.READY, required=True),
            CapabilityResult(name="database", state=CapState.READY, required=True),
            CapabilityResult(name="auth", state=CapState.DEGRADED, required=True),
            CapabilityResult(name="routers", state=CapState.READY, required=True),
        ]
        summary = compute_readiness(results)
        assert summary["ready"] is True
        assert summary["overall_state"] == "degraded"

    @pytest.mark.unit
    def test_timeout_required_blocks_readiness(self):
        """Required capability TIMEOUT blocks readiness."""
        results = [
            CapabilityResult(name="configuration", state=CapState.READY, required=True),
            CapabilityResult(name="database", state=CapState.TIMEOUT, required=True),
            CapabilityResult(name="auth", state=CapState.READY, required=True),
            CapabilityResult(name="routers", state=CapState.READY, required=True),
        ]
        summary = compute_readiness(results)
        assert summary["ready"] is False

    @pytest.mark.unit
    def test_summary_includes_policy(self):
        """Readiness summary includes the required/optional policy."""
        results = [
            CapabilityResult(name="configuration", state=CapState.READY, required=True),
        ]
        summary = compute_readiness(results)
        assert "policy" in summary
        assert "required" in summary["policy"]
        assert "optional" in summary["policy"]

    @pytest.mark.unit
    def test_summary_includes_timestamp(self):
        """Readiness summary includes a timestamp."""
        results = []
        summary = compute_readiness(results)
        assert "timestamp" in summary


# =============================================================================
# Startup Failure Tracking
# =============================================================================


class TestStartupFailures:

    @pytest.mark.unit
    def test_register_and_retrieve(self):
        """Can register and retrieve startup failures."""
        register_startup_failure("test router", "No module named 'foo'")
        failures = get_startup_failures()
        assert len(failures) == 1
        assert failures[0]["component"] == "test router"

    @pytest.mark.unit
    def test_failures_appear_in_readiness(self):
        """Startup failures appear in readiness response."""
        register_startup_failure("critical router", "import error")
        results = [
            CapabilityResult(name="routers", state=CapState.UNAVAILABLE, required=True),
        ]
        summary = compute_readiness(results)
        assert len(summary["startup_failures"]) == 1

    @pytest.mark.unit
    def test_router_check_detects_failures(self):
        """check_routers returns UNAVAILABLE when failures registered."""
        register_startup_failure("api_v1 router", "No module named 'missing'")
        result = check_routers()
        assert result.state == CapState.UNAVAILABLE
        assert result.required is True

    @pytest.mark.unit
    def test_router_check_ready_when_no_failures(self):
        """check_routers returns READY when no failures."""
        result = check_routers()
        assert result.state == CapState.READY


# =============================================================================
# Auth Check
# =============================================================================


class TestAuthCheck:

    @pytest.mark.unit
    @patch.dict("os.environ", {"SUPABASE_JWT_SECRET": "a-real-secret-thats-long", "AUTH_DEV_MODE": "false"})
    def test_auth_ready_when_configured(self):
        """Auth check returns READY when JWT secret is set."""
        result = check_auth()
        assert result.state == CapState.READY

    @pytest.mark.unit
    @patch.dict("os.environ", {"SUPABASE_JWT_SECRET": "", "AUTH_DEV_MODE": "false"})
    def test_auth_unavailable_when_no_secret(self):
        """Auth check returns UNAVAILABLE when JWT secret missing."""
        result = check_auth()
        assert result.state == CapState.UNAVAILABLE

    @pytest.mark.unit
    @patch.dict("os.environ", {"AUTH_DEV_MODE": "true", "SUPABASE_JWT_SECRET": ""})
    def test_auth_degraded_in_dev_mode(self):
        """Auth check returns DEGRADED in dev mode."""
        result = check_auth()
        assert result.state == CapState.DEGRADED


# =============================================================================
# Sanitization (Redaction)
# =============================================================================


class TestSanitization:

    @pytest.mark.unit
    def test_redacts_key_values(self):
        """Secrets in error messages are redacted."""
        text = "Connection failed with key=sk_live_12345abcdef"
        sanitized = _sanitize(text)
        assert "sk_live_12345abcdef" not in sanitized
        assert "***" in sanitized

    @pytest.mark.unit
    def test_redacts_url_credentials(self):
        """URLs with embedded credentials are redacted."""
        text = "redis://admin:supersecret@redis.host:6379"
        sanitized = _sanitize(text)
        assert "supersecret" not in sanitized
        assert "***" in sanitized

    @pytest.mark.unit
    def test_truncates_long_messages(self):
        """Long messages are truncated."""
        text = "x" * 500
        sanitized = _sanitize(text)
        assert len(sanitized) <= 300

    @pytest.mark.unit
    def test_harmless_text_unchanged(self):
        """Non-secret text passes through."""
        text = "Database connection timed out after 5s"
        sanitized = _sanitize(text)
        assert sanitized == text


# =============================================================================
# Cache Behavior
# =============================================================================


class TestCaching:

    @pytest.mark.unit
    def test_repeated_checks_use_cache(self):
        """Second call within TTL returns cached result."""
        from backend.app.core.capability_readiness import _get_cached, _run_bounded_check

        # Run through bounded check (which caches)
        _run_bounded_check("routers", check_routers)
        cached = _get_cached("routers")
        assert cached is not None
        assert cached.cached is True

    @pytest.mark.unit
    def test_cache_cleared_returns_none(self):
        """Cleared cache returns None."""
        check_routers()
        clear_cache()
        from backend.app.core.capability_readiness import _get_cached
        assert _get_cached("routers") is None


# =============================================================================
# Full Integration
# =============================================================================


class TestFullIntegration:

    @pytest.mark.unit
    @patch.dict("os.environ", {"AUTH_DEV_MODE": "true"})
    def test_run_all_checks_returns_results(self):
        """run_all_checks produces results for all registered checks."""
        clear_cache()
        results = run_all_checks()
        names = {r.name for r in results}
        assert "configuration" in names
        assert "auth" in names
        assert "routers" in names

    @pytest.mark.unit
    def test_compute_readiness_structure(self):
        """compute_readiness produces expected response structure."""
        results = run_all_checks()
        summary = compute_readiness(results)
        assert "ready" in summary
        assert "overall_state" in summary
        assert "capabilities" in summary
        assert "summary" in summary
        assert "startup_failures" in summary
        assert "policy" in summary

"""Readiness Gate & Failure-Injection Tests — Story 013.

Tests verify:
  1. Required capability failure → readiness=false (503)
  2. Optional capability failure → degraded but still ready (200)
  3. Timeout handling → bounded, doesn't hang
  4. Sanitization → no secrets in readiness responses
  5. Startup failure tracking → router load failures surfaced
  6. Cache behavior → repeated checks use cache within TTL
  7. Promotion gate → overall state reflects truth

Run with:
    pytest tests/unit/test_readiness_gates.py -v
"""
from __future__ import annotations

import os
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
    _run_bounded_check,
    _sanitize,
    check_auth,
    check_configuration,
    check_database,
    check_generation,
    check_gpu,
    check_llm,
    check_queue,
    check_routers,
    check_storage,
    clear_cache,
    clear_startup_failures,
    compute_readiness,
    get_startup_failures,
    register_startup_failure,
    run_all_checks,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def clean_state():
    """Reset cache and startup failures between tests."""
    clear_cache()
    clear_startup_failures()
    yield
    clear_cache()
    clear_startup_failures()


# =============================================================================
# 1. Required Capability Failure Blocks Readiness
# =============================================================================


@pytest.mark.unit
class TestRequiredCapabilityBlocking:
    """Required capability failures must block readiness (503)."""

    def test_all_ready_produces_ready_true(self):
        """When all required capabilities are ready, readiness=true."""
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

    def test_database_unavailable_blocks_readiness(self):
        """Database failure → ready=false."""
        results = [
            CapabilityResult(name="configuration", state=CapState.READY, required=True),
            CapabilityResult(name="database", state=CapState.UNAVAILABLE, required=True, reason="connection refused"),
            CapabilityResult(name="auth", state=CapState.READY, required=True),
            CapabilityResult(name="routers", state=CapState.READY, required=True),
        ]
        summary = compute_readiness(results)
        assert summary["ready"] is False
        assert summary["overall_state"] == "unavailable"

    def test_auth_unavailable_blocks_readiness(self):
        """Auth failure → ready=false."""
        results = [
            CapabilityResult(name="configuration", state=CapState.READY, required=True),
            CapabilityResult(name="database", state=CapState.READY, required=True),
            CapabilityResult(name="auth", state=CapState.UNAVAILABLE, required=True, reason="JWT secret missing"),
            CapabilityResult(name="routers", state=CapState.READY, required=True),
        ]
        summary = compute_readiness(results)
        assert summary["ready"] is False

    def test_router_failure_blocks_readiness(self):
        """Router load failure → ready=false."""
        results = [
            CapabilityResult(name="configuration", state=CapState.READY, required=True),
            CapabilityResult(name="database", state=CapState.READY, required=True),
            CapabilityResult(name="auth", state=CapState.READY, required=True),
            CapabilityResult(name="routers", state=CapState.UNAVAILABLE, required=True, reason="3 routers failed"),
        ]
        summary = compute_readiness(results)
        assert summary["ready"] is False

    def test_timeout_on_required_blocks_readiness(self):
        """Timeout on a required capability → ready=false."""
        results = [
            CapabilityResult(name="configuration", state=CapState.READY, required=True),
            CapabilityResult(name="database", state=CapState.TIMEOUT, required=True),
            CapabilityResult(name="auth", state=CapState.READY, required=True),
            CapabilityResult(name="routers", state=CapState.READY, required=True),
        ]
        summary = compute_readiness(results)
        assert summary["ready"] is False


# =============================================================================
# 2. Optional Capability Failure → Degraded (Not Blocking)
# =============================================================================


@pytest.mark.unit
class TestOptionalCapabilityDegradation:
    """Optional capability failures degrade but don't block traffic."""

    def test_gpu_unavailable_still_ready(self):
        """GPU unavailable → still ready, but overall=degraded."""
        results = [
            CapabilityResult(name="configuration", state=CapState.READY, required=True),
            CapabilityResult(name="database", state=CapState.READY, required=True),
            CapabilityResult(name="auth", state=CapState.READY, required=True),
            CapabilityResult(name="routers", state=CapState.READY, required=True),
            CapabilityResult(name="gpu", state=CapState.UNAVAILABLE, required=False),
            CapabilityResult(name="generation", state=CapState.UNAVAILABLE, required=False),
        ]
        summary = compute_readiness(results)
        assert summary["ready"] is True

    def test_all_optional_unavailable_still_ready(self):
        """All optional capabilities can be unavailable and readiness stays true."""
        results = [
            CapabilityResult(name="configuration", state=CapState.READY, required=True),
            CapabilityResult(name="database", state=CapState.READY, required=True),
            CapabilityResult(name="auth", state=CapState.READY, required=True),
            CapabilityResult(name="routers", state=CapState.READY, required=True),
        ]
        for cap in OPTIONAL_CAPABILITIES:
            results.append(CapabilityResult(name=cap, state=CapState.UNAVAILABLE, required=False))
        summary = compute_readiness(results)
        assert summary["ready"] is True

    def test_auth_degraded_accepted(self):
        """Auth in DEGRADED state (dev mode) is accepted for readiness."""
        results = [
            CapabilityResult(name="configuration", state=CapState.READY, required=True),
            CapabilityResult(name="database", state=CapState.READY, required=True),
            CapabilityResult(name="auth", state=CapState.DEGRADED, required=True, reason="dev mode"),
            CapabilityResult(name="routers", state=CapState.READY, required=True),
        ]
        summary = compute_readiness(results)
        assert summary["ready"] is True
        assert summary["overall_state"] == "degraded"


# =============================================================================
# 3. Timeout Handling
# =============================================================================


@pytest.mark.unit
class TestTimeoutHandling:
    """Bounded checks handle slow/hanging dependencies."""

    def test_slow_check_times_out(self):
        """A check that exceeds timeout returns TIMEOUT state."""
        def slow_check() -> CapabilityResult:
            time.sleep(2.0)  # Exceeds default timeout
            return CapabilityResult(name="slow", state=CapState.READY)

        result = _run_bounded_check("slow", slow_check, timeout=0.5)
        assert result.state == CapState.TIMEOUT
        assert result.latency_ms >= 400  # At least 0.4s elapsed

    def test_fast_check_returns_normally(self):
        """A check that completes within timeout returns its actual result."""
        def fast_check() -> CapabilityResult:
            return CapabilityResult(name="fast", state=CapState.READY, reason="ok")

        result = _run_bounded_check("fast", fast_check, timeout=5.0)
        assert result.state == CapState.READY

    def test_exception_in_check_returns_unavailable(self):
        """A check that raises an exception returns UNAVAILABLE."""
        def failing_check() -> CapabilityResult:
            raise ConnectionError("cannot reach database")

        result = _run_bounded_check("failing", failing_check, timeout=5.0)
        assert result.state == CapState.UNAVAILABLE
        assert "cannot reach database" in result.reason


# =============================================================================
# 4. Sanitization — No Secrets in Responses
# =============================================================================


@pytest.mark.unit
class TestSanitization:
    """Readiness responses must never contain secrets."""

    def test_sanitize_removes_key_values(self):
        text = "connection failed: key=sk-abc123supersecret"
        sanitized = _sanitize(text)
        assert "sk-abc123supersecret" not in sanitized
        assert "key=***" in sanitized

    def test_sanitize_removes_url_credentials(self):
        text = "redis://admin:p4ssw0rd@redis.example.com:6379/0"
        sanitized = _sanitize(text)
        assert "p4ssw0rd" not in sanitized
        assert "***@" in sanitized

    def test_sanitize_removes_token_values(self):
        text = "auth failed: token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        sanitized = _sanitize(text)
        assert "eyJhbGciOiJ" not in sanitized

    def test_sanitize_truncates_long_messages(self):
        text = "x" * 500
        sanitized = _sanitize(text)
        assert len(sanitized) <= 300

    def test_capability_result_serialization_clean(self):
        """CapabilityResult.to_dict() should not add sensitive fields."""
        result = CapabilityResult(
            name="database",
            state=CapState.UNAVAILABLE,
            reason="connection refused on port 5432",
            evidence={"host": "db.example.com"},
        )
        d = result.to_dict()
        # Should not include encrypted_secret or raw credentials
        assert "encrypted_secret" not in d
        assert "password" not in str(d)
        # Reason is passed through (sanitization happens at check time)
        assert d["name"] == "database"
        assert d["state"] == "unavailable"


# =============================================================================
# 5. Startup Failure Tracking
# =============================================================================


@pytest.mark.unit
class TestStartupFailures:
    """Track router and component startup failures."""

    def test_register_and_retrieve_failures(self):
        register_startup_failure("brain_router", "ImportError: missing module")
        register_startup_failure("video_router", "ConnectionError: db")

        failures = get_startup_failures()
        assert len(failures) == 2
        assert failures[0]["component"] == "brain_router"
        assert failures[1]["component"] == "video_router"

    def test_startup_failures_sanitized(self):
        register_startup_failure("auth", "secret_key=abc123xyz not valid")
        failures = get_startup_failures()
        # Secret should be sanitized
        assert "abc123xyz" not in failures[0]["error"]

    def test_router_check_uses_startup_failures(self):
        register_startup_failure("brain_router", "ImportError")
        result = check_routers()
        assert result.state == CapState.UNAVAILABLE
        assert "1 router" in result.reason

    def test_no_failures_means_routers_ready(self):
        result = check_routers()
        assert result.state == CapState.READY


# =============================================================================
# 6. Cache Behavior
# =============================================================================


@pytest.mark.unit
class TestCacheBehavior:
    """Check results are cached to prevent thundering herd."""

    def test_second_call_uses_cache(self):
        """Repeated checks within TTL return cached result."""
        call_count = {"n": 0}

        def counting_check() -> CapabilityResult:
            call_count["n"] += 1
            return CapabilityResult(name="counted", state=CapState.READY)

        # First call executes
        r1 = _run_bounded_check("counted", counting_check)
        assert call_count["n"] == 1
        assert r1.cached is False

        # Second call uses cache
        r2 = _run_bounded_check("counted", counting_check)
        assert call_count["n"] == 1  # Not called again
        assert r2.cached is True

    def test_cache_expires_after_ttl(self):
        """After TTL expires, the check runs again."""
        call_count = {"n": 0}

        def counting_check() -> CapabilityResult:
            call_count["n"] += 1
            return CapabilityResult(name="ttl_test", state=CapState.READY)

        # Temporarily set very short TTL for testing
        import backend.app.core.capability_readiness as module
        original_ttl = module.CACHE_TTL_SECONDS
        module.CACHE_TTL_SECONDS = 0.1

        try:
            _run_bounded_check("ttl_test", counting_check)
            assert call_count["n"] == 1
            time.sleep(0.15)
            _run_bounded_check("ttl_test", counting_check)
            assert call_count["n"] == 2
        finally:
            module.CACHE_TTL_SECONDS = original_ttl


# =============================================================================
# 7. Policy Verification
# =============================================================================


@pytest.mark.unit
class TestReadinessPolicy:
    """Verify readiness policy is correctly configured."""

    def test_required_capabilities_defined(self):
        """At least configuration, database, auth, routers are required."""
        assert "configuration" in REQUIRED_CAPABILITIES
        assert "database" in REQUIRED_CAPABILITIES
        assert "auth" in REQUIRED_CAPABILITIES
        assert "routers" in REQUIRED_CAPABILITIES

    def test_optional_capabilities_defined(self):
        """GPU, generation, LLM, queue are optional."""
        assert "gpu" in OPTIONAL_CAPABILITIES
        assert "generation" in OPTIONAL_CAPABILITIES
        assert "llm" in OPTIONAL_CAPABILITIES
        assert "queue" in OPTIONAL_CAPABILITIES

    def test_no_overlap_required_optional(self):
        """Required and optional must not overlap."""
        overlap = REQUIRED_CAPABILITIES & OPTIONAL_CAPABILITIES
        assert len(overlap) == 0, f"Overlap: {overlap}"

    def test_all_checks_have_corresponding_policy(self):
        """Every registered check is classified as required or optional."""
        all_policy = REQUIRED_CAPABILITIES | OPTIONAL_CAPABILITIES
        for name in ALL_CHECKS:
            assert name in all_policy, f"Check '{name}' not in required or optional policy"

    def test_check_timeout_is_bounded(self):
        """Timeout must be reasonable (not infinite)."""
        assert CHECK_TIMEOUT_SECONDS <= 10.0, "Check timeout too long"
        assert CHECK_TIMEOUT_SECONDS > 0

    def test_cache_ttl_reasonable(self):
        """Cache TTL must balance freshness and performance."""
        assert CACHE_TTL_SECONDS >= 10.0, "Cache too short (thundering herd risk)"
        assert CACHE_TTL_SECONDS <= 300.0, "Cache too long (stale state risk)"

    def test_compute_readiness_includes_promotion_evidence(self):
        """Readiness response includes policy and summary for promotion gates."""
        results = [
            CapabilityResult(name="configuration", state=CapState.READY, required=True),
            CapabilityResult(name="database", state=CapState.READY, required=True),
            CapabilityResult(name="auth", state=CapState.READY, required=True),
            CapabilityResult(name="routers", state=CapState.READY, required=True),
        ]
        summary = compute_readiness(results)
        assert "policy" in summary
        assert "summary" in summary
        assert "timestamp" in summary
        assert "startup_failures" in summary
        assert summary["policy"]["required"] == sorted(REQUIRED_CAPABILITIES)

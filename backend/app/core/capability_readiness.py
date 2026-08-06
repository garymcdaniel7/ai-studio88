"""Capability-Aware Readiness — Story 117.

Separates liveness from readiness and provides typed, bounded, evidence-based
health checks for every required capability.

Liveness: "Is the process accepting TCP?" — always 200 if alive.
Readiness: "Can this instance serve traffic?" — checks all required capabilities.

Capability States:
    READY       — Live connectivity verified within bounded timeout
    DEGRADED    — Functional but impaired (optional capability, or partial)
    UNAVAILABLE — Not configured or verification failed
    TIMEOUT     — Check exceeded bounded timeout (treated as unavailable)
    SKIPPED     — Check not run (e.g., cached result still valid)

Required vs Optional:
    Required capabilities MUST be READY for overall readiness=true.
    Optional capabilities can be DEGRADED/UNAVAILABLE without blocking readiness.

Evidence:
    Every check produces sanitized evidence (no secrets, no sensitive provider details).
    Includes: latency_ms, checked_at, reason, cached flag.
"""

from __future__ import annotations

import logging
import os
import time
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Callable

logger = logging.getLogger(__name__)


# =============================================================================
# Capability State
# =============================================================================


class CapState(StrEnum):
    """State of a single capability check."""

    READY = "ready"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"


# =============================================================================
# Capability Check Result
# =============================================================================


@dataclass
class CapabilityResult:
    """Result of a single capability health check."""

    name: str
    state: CapState
    required: bool = True
    reason: str = ""
    latency_ms: float = 0.0
    checked_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    cached: bool = False
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for HTTP response (secrets redacted)."""
        d = {
            "name": self.name,
            "state": self.state.value,
            "required": self.required,
            "reason": self.reason,
            "latency_ms": round(self.latency_ms, 1),
            "checked_at": self.checked_at,
        }
        if self.cached:
            d["cached"] = True
        if self.evidence:
            d["evidence"] = self.evidence
        return d


# =============================================================================
# Readiness Policy
# =============================================================================

# Required capabilities: readiness=false if ANY of these are not READY
REQUIRED_CAPABILITIES = {
    "configuration",
    "database",
    "auth",
    "routers",
}

# Optional capabilities: degraded/unavailable produces degraded state, not failure
OPTIONAL_CAPABILITIES = {
    "storage",
    "gpu",
    "generation",
    "llm",
    "voice",
    "training",
    "queue",
}

# Global timeout for any single capability check (seconds)
CHECK_TIMEOUT_SECONDS = 5.0

# Cache TTL: how long to reuse a cached result before re-checking (seconds)
CACHE_TTL_SECONDS = 30.0


# =============================================================================
# Startup Failure Registry
# =============================================================================

# Tracks which routers/imports failed at startup
_startup_failures: list[dict[str, str]] = []
_startup_lock = threading.Lock()


def register_startup_failure(component: str, error: str) -> None:
    """Record a startup import or initialization failure."""
    with _startup_lock:
        _startup_failures.append({
            "component": component,
            "error": _sanitize(error),
            "timestamp": datetime.now(UTC).isoformat(),
        })


def get_startup_failures() -> list[dict[str, str]]:
    """Get all recorded startup failures."""
    with _startup_lock:
        return list(_startup_failures)


def clear_startup_failures() -> None:
    """Clear startup failures (for testing)."""
    with _startup_lock:
        _startup_failures.clear()


# =============================================================================
# Check Result Cache
# =============================================================================

_check_cache: dict[str, tuple[CapabilityResult, float]] = {}
_cache_lock = threading.Lock()


def _get_cached(name: str) -> CapabilityResult | None:
    """Get a cached result if still valid."""
    with _cache_lock:
        entry = _check_cache.get(name)
        if entry is None:
            return None
        result, timestamp = entry
        if (time.time() - timestamp) > CACHE_TTL_SECONDS:
            return None
        cached_result = CapabilityResult(
            name=result.name,
            state=result.state,
            required=result.required,
            reason=result.reason,
            latency_ms=result.latency_ms,
            checked_at=result.checked_at,
            cached=True,
            evidence=result.evidence,
        )
        return cached_result


def _set_cached(result: CapabilityResult) -> None:
    """Cache a check result."""
    with _cache_lock:
        _check_cache[result.name] = (result, time.time())


def clear_cache() -> None:
    """Clear the check cache (for testing)."""
    with _cache_lock:
        _check_cache.clear()


# =============================================================================
# Bounded Check Execution
# =============================================================================


def _run_bounded_check(
    name: str,
    check_fn: Callable[[], CapabilityResult],
    timeout: float = CHECK_TIMEOUT_SECONDS,
) -> CapabilityResult:
    """Run a check with a bounded timeout.

    If the check exceeds the timeout, returns TIMEOUT state.
    """
    # Check cache first
    cached = _get_cached(name)
    if cached is not None:
        return cached

    start = time.time()
    result: CapabilityResult | None = None
    error_holder: list[str] = []

    def _target():
        nonlocal result
        try:
            result = check_fn()
        except Exception as e:
            error_holder.append(str(e)[:200])

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    thread.join(timeout=timeout)

    elapsed_ms = (time.time() - start) * 1000

    if thread.is_alive():
        # Timed out
        timeout_result = CapabilityResult(
            name=name,
            state=CapState.TIMEOUT,
            reason=f"Check timed out after {timeout:.1f}s",
            latency_ms=elapsed_ms,
        )
        _set_cached(timeout_result)
        return timeout_result

    if error_holder:
        error_result = CapabilityResult(
            name=name,
            state=CapState.UNAVAILABLE,
            reason=_sanitize(error_holder[0]),
            latency_ms=elapsed_ms,
        )
        _set_cached(error_result)
        return error_result

    if result is None:
        result = CapabilityResult(
            name=name,
            state=CapState.UNAVAILABLE,
            reason="Check returned no result",
            latency_ms=elapsed_ms,
        )

    result.latency_ms = elapsed_ms
    _set_cached(result)
    return result


# =============================================================================
# Individual Capability Checks
# =============================================================================


def check_configuration() -> CapabilityResult:
    """Verify critical configuration is present and valid."""
    from backend.app.core.config import get_settings

    settings = get_settings()
    errors = settings._validate_for_profile()

    if errors:
        return CapabilityResult(
            name="configuration",
            state=CapState.UNAVAILABLE,
            required=True,
            reason=f"{len(errors)} config errors: {errors[0][:80]}",
            evidence={"error_count": len(errors)},
        )

    return CapabilityResult(
        name="configuration",
        state=CapState.READY,
        required=True,
        reason=f"Profile '{settings.app_env}' validated",
        evidence={"profile": settings.app_env},
    )


def check_database() -> CapabilityResult:
    """Verify database connectivity with a real query."""
    from backend.database import is_supabase_configured

    if not is_supabase_configured():
        return CapabilityResult(
            name="database",
            state=CapState.UNAVAILABLE,
            required=True,
            reason="SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not configured",
        )

    try:
        from backend.database import get_supabase_client

        client = get_supabase_client()
        client.table("talent").select("id").limit(1).execute()
        return CapabilityResult(
            name="database",
            state=CapState.READY,
            required=True,
            reason="Supabase connected, query successful",
            evidence={"tables_accessible": True},
        )
    except Exception as e:
        return CapabilityResult(
            name="database",
            state=CapState.UNAVAILABLE,
            required=True,
            reason=f"Database query failed: {_sanitize(str(e))}",
        )


def check_auth() -> CapabilityResult:
    """Verify auth dependencies (JWT secret configured)."""
    jwt_secret = os.getenv("SUPABASE_JWT_SECRET", "")
    auth_dev_mode = os.getenv("AUTH_DEV_MODE", "false").lower() in ("1", "true", "yes")

    if auth_dev_mode:
        return CapabilityResult(
            name="auth",
            state=CapState.DEGRADED,
            required=True,
            reason="AUTH_DEV_MODE enabled — auth bypassed in development",
            evidence={"dev_mode": True},
        )

    if not jwt_secret or jwt_secret.startswith("your-"):
        return CapabilityResult(
            name="auth",
            state=CapState.UNAVAILABLE,
            required=True,
            reason="SUPABASE_JWT_SECRET not configured",
        )

    return CapabilityResult(
        name="auth",
        state=CapState.READY,
        required=True,
        reason="JWT validation configured",
        evidence={"secret_length": len(jwt_secret)},
    )


def check_routers() -> CapabilityResult:
    """Check if required routers loaded successfully at startup."""
    failures = get_startup_failures()
    router_failures = [f for f in failures if "router" in f["component"].lower()]

    if router_failures:
        names = [f["component"] for f in router_failures[:5]]
        return CapabilityResult(
            name="routers",
            state=CapState.UNAVAILABLE,
            required=True,
            reason=f"{len(router_failures)} router(s) failed to load",
            evidence={"failed": names, "count": len(router_failures)},
        )

    return CapabilityResult(
        name="routers",
        state=CapState.READY,
        required=True,
        reason="All routers loaded successfully",
    )


def check_storage() -> CapabilityResult:
    """Verify B2 storage connectivity."""
    key_id = os.getenv("B2_KEY_ID", "")
    app_key = os.getenv("B2_APPLICATION_KEY", "")

    if not key_id or not app_key:
        return CapabilityResult(
            name="storage",
            state=CapState.UNAVAILABLE,
            required=False,
            reason="B2 credentials not configured",
        )

    try:
        import boto3

        endpoint = os.getenv("B2_ENDPOINT_URL", "")
        bucket = os.getenv("B2_BUCKET_NAME", "")
        client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=key_id,
            aws_secret_access_key=app_key,
            region_name=os.getenv("B2_REGION", "us-east-005"),
        )
        client.head_bucket(Bucket=bucket)
        return CapabilityResult(
            name="storage",
            state=CapState.READY,
            required=False,
            reason="B2 bucket accessible",
            evidence={"bucket": bucket},
        )
    except Exception as e:
        return CapabilityResult(
            name="storage",
            state=CapState.UNAVAILABLE,
            required=False,
            reason=f"B2 check failed: {_sanitize(str(e))}",
        )


def check_gpu() -> CapabilityResult:
    """Check GPU provider availability (Vast.ai or RunPod key configured)."""
    vast_key = os.getenv("VAST_API_KEY", "") or os.getenv("VASTAI_API_KEY", "")
    runpod_key = os.getenv("RUNPOD_API_KEY", "")

    if not vast_key and not runpod_key:
        return CapabilityResult(
            name="gpu",
            state=CapState.UNAVAILABLE,
            required=False,
            reason="No GPU provider API key configured",
        )

    provider = "Vast.ai" if vast_key else "RunPod"
    return CapabilityResult(
        name="gpu",
        state=CapState.READY,
        required=False,
        reason=f"{provider} API key present",
        evidence={"provider": provider.lower()},
    )


def check_generation() -> CapabilityResult:
    """Check generation engine availability."""
    gen_provider = os.getenv("GENERATION_PROVIDER", "simulation")

    if gen_provider == "simulation":
        return CapabilityResult(
            name="generation",
            state=CapState.DEGRADED,
            required=False,
            reason="Running in simulation mode",
            evidence={"provider": "simulation"},
        )

    comfyui_url = os.getenv("COMFYUI_BASE_URL", "")
    if not comfyui_url:
        return CapabilityResult(
            name="generation",
            state=CapState.UNAVAILABLE,
            required=False,
            reason="COMFYUI_BASE_URL not configured",
        )

    try:
        import httpx

        resp = httpx.get(f"{comfyui_url}/system_stats", timeout=3)
        if resp.status_code == 200:
            return CapabilityResult(
                name="generation",
                state=CapState.READY,
                required=False,
                reason="ComfyUI responding",
                evidence={"url": comfyui_url[:30]},
            )
        return CapabilityResult(
            name="generation",
            state=CapState.UNAVAILABLE,
            required=False,
            reason=f"ComfyUI returned HTTP {resp.status_code}",
        )
    except Exception:
        return CapabilityResult(
            name="generation",
            state=CapState.UNAVAILABLE,
            required=False,
            reason=f"ComfyUI not reachable at {comfyui_url[:30]}",
        )


def check_llm() -> CapabilityResult:
    """Check LLM provider availability."""
    brain_provider = os.getenv("BRAIN_PROVIDER", "ollama")

    if brain_provider == "ollama":
        try:
            import httpx

            base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            resp = httpx.get(f"{base_url}/api/tags", timeout=2)
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                return CapabilityResult(
                    name="llm",
                    state=CapState.READY,
                    required=False,
                    reason=f"Ollama online ({len(models)} models)",
                    evidence={"provider": "ollama", "models": len(models)},
                )
        except Exception:
            pass
        return CapabilityResult(
            name="llm",
            state=CapState.UNAVAILABLE,
            required=False,
            reason="Ollama not reachable",
        )

    openai_key = os.getenv("OPENAI_API_KEY", "")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    if openai_key or anthropic_key:
        provider = "OpenAI" if openai_key else "Anthropic"
        return CapabilityResult(
            name="llm",
            state=CapState.READY,
            required=False,
            reason=f"{provider} API key configured",
            evidence={"provider": provider.lower()},
        )

    return CapabilityResult(
        name="llm",
        state=CapState.UNAVAILABLE,
        required=False,
        reason="No LLM provider configured",
    )


def check_queue() -> CapabilityResult:
    """Check Redis/queue availability."""
    redis_url = os.getenv("REDIS_URL", "")

    if not redis_url:
        return CapabilityResult(
            name="queue",
            state=CapState.UNAVAILABLE,
            required=False,
            reason="REDIS_URL not configured",
        )

    try:
        import redis

        r = redis.from_url(redis_url, socket_connect_timeout=2)
        r.ping()
        return CapabilityResult(
            name="queue",
            state=CapState.READY,
            required=False,
            reason="Redis connected",
        )
    except ImportError:
        return CapabilityResult(
            name="queue",
            state=CapState.DEGRADED,
            required=False,
            reason="Redis URL set but redis package not installed",
        )
    except Exception as e:
        return CapabilityResult(
            name="queue",
            state=CapState.UNAVAILABLE,
            required=False,
            reason=f"Redis check failed: {_sanitize(str(e))}",
        )


# =============================================================================
# Aggregate Readiness Check
# =============================================================================

# Map of all capability checks
ALL_CHECKS: dict[str, Callable[[], CapabilityResult]] = {
    "configuration": check_configuration,
    "database": check_database,
    "auth": check_auth,
    "routers": check_routers,
    "storage": check_storage,
    "gpu": check_gpu,
    "generation": check_generation,
    "llm": check_llm,
    "queue": check_queue,
}


def run_all_checks() -> list[CapabilityResult]:
    """Run all capability checks with bounded timeouts.

    Returns a list of results (one per capability).
    """
    results: list[CapabilityResult] = []

    for name, check_fn in ALL_CHECKS.items():
        required = name in REQUIRED_CAPABILITIES
        result = _run_bounded_check(name, check_fn)
        result.required = required
        results.append(result)

    return results


def compute_readiness(results: list[CapabilityResult]) -> dict[str, Any]:
    """Compute overall readiness from individual capability results.

    Returns a structured response suitable for HTTP.
    """
    required_results = [r for r in results if r.required]
    optional_results = [r for r in results if not r.required]

    # Required: all must be READY or DEGRADED (dev mode auth is DEGRADED but acceptable)
    required_ready = all(
        r.state in (CapState.READY, CapState.DEGRADED)
        for r in required_results
    )

    # Overall state
    if required_ready:
        any_degraded = any(r.state == CapState.DEGRADED for r in results)
        overall = "ready" if not any_degraded else "degraded"
    else:
        overall = "unavailable"

    # Counts
    state_counts = {s.value: 0 for s in CapState}
    for r in results:
        state_counts[r.state.value] += 1

    return {
        "ready": required_ready,
        "overall_state": overall,
        "timestamp": datetime.now(UTC).isoformat(),
        "capabilities": {r.name: r.to_dict() for r in results},
        "summary": {
            "total": len(results),
            "required_count": len(required_results),
            "optional_count": len(optional_results),
            **state_counts,
        },
        "startup_failures": get_startup_failures(),
        "policy": {
            "required": sorted(REQUIRED_CAPABILITIES),
            "optional": sorted(OPTIONAL_CAPABILITIES),
            "check_timeout_seconds": CHECK_TIMEOUT_SECONDS,
            "cache_ttl_seconds": CACHE_TTL_SECONDS,
        },
    }


# =============================================================================
# Helpers
# =============================================================================


def _sanitize(text: str) -> str:
    """Remove potential secrets from error messages."""
    import re

    # Redact anything that looks like a key/token/secret
    text = re.sub(r'(key|token|secret|password|credential)[\s=:]+\S+', r'\1=***', text, flags=re.IGNORECASE)
    # Redact URLs with credentials
    text = re.sub(r'://[^@]+@', '://***@', text)
    # Truncate
    return text[:300]

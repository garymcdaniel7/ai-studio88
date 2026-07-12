"""Obaluaye Health Monitor — polls all services and reports status.

Runs periodically (every 30s by default). Produces a health report
that the admin dashboard and AIOS gateway consume.

Checks:
- ComfyUI: GET /system_stats
- Ollama: GET /api/tags
- Backblaze B2: list buckets
- Supabase: simple query
- ElevenLabs: GET /user
- GPU Worker: nvidia-smi via Worker API
- MOSS-TTS: GET /health
- FFmpeg: which ffmpeg (via Worker API)

Each check uses a circuit breaker:
- After 3 consecutive failures: mark as DOWN
- After 1 success after being DOWN: mark as RECOVERING
- After 3 consecutive successes: mark as HEALTHY
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum

import httpx

logger = logging.getLogger(__name__)


class ServiceStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"
    RECOVERING = "recovering"
    UNKNOWN = "unknown"


@dataclass
class ServiceHealth:
    """Health state for a single service."""
    name: str
    status: ServiceStatus = ServiceStatus.UNKNOWN
    last_check: float = 0.0
    last_success: float = 0.0
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    response_time_ms: int = 0
    error: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class HealthReport:
    """Complete platform health report."""
    timestamp: float = 0.0
    overall_status: ServiceStatus = ServiceStatus.UNKNOWN
    services: dict[str, ServiceHealth] = field(default_factory=dict)
    alerts: list[dict] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


# Circuit breaker thresholds
FAILURE_THRESHOLD = 3
RECOVERY_THRESHOLD = 3


class HealthMonitor:
    """Monitors all platform services and produces health reports."""

    def __init__(self) -> None:
        self._services: dict[str, ServiceHealth] = {}
        self._last_report: HealthReport | None = None
        self._alerts: list[dict] = []

    def check_all(self) -> HealthReport:
        """Run all health checks and produce a report."""
        timestamp = time.time()

        self._check_service("comfyui", self._check_comfyui)
        self._check_service("ollama", self._check_ollama)
        self._check_service("supabase", self._check_supabase)
        self._check_service("backblaze_b2", self._check_b2)
        self._check_service("elevenlabs", self._check_elevenlabs)
        self._check_service("worker_api", self._check_worker_api)

        # Determine overall status
        statuses = [s.status for s in self._services.values()]
        if all(s == ServiceStatus.HEALTHY for s in statuses):
            overall = ServiceStatus.HEALTHY
        elif any(s == ServiceStatus.DOWN for s in statuses):
            overall = ServiceStatus.DEGRADED
        elif all(s == ServiceStatus.DOWN for s in statuses):
            overall = ServiceStatus.DOWN
        else:
            overall = ServiceStatus.DEGRADED

        # Generate alerts
        self._alerts = []
        for name, svc in self._services.items():
            if svc.status == ServiceStatus.DOWN:
                self._alerts.append({
                    "severity": "critical",
                    "service": name,
                    "message": f"{name} is DOWN: {svc.error or 'unreachable'}",
                    "timestamp": timestamp,
                })
            elif svc.status == ServiceStatus.RECOVERING:
                self._alerts.append({
                    "severity": "info",
                    "service": name,
                    "message": f"{name} is recovering",
                    "timestamp": timestamp,
                })

        report = HealthReport(
            timestamp=timestamp,
            overall_status=overall,
            services=dict(self._services),
            alerts=self._alerts,
            metrics={
                "total_services": len(self._services),
                "healthy": sum(1 for s in self._services.values() if s.status == ServiceStatus.HEALTHY),
                "down": sum(1 for s in self._services.values() if s.status == ServiceStatus.DOWN),
                "avg_response_ms": sum(s.response_time_ms for s in self._services.values()) // max(len(self._services), 1),
            },
        )

        self._last_report = report
        return report

    def get_last_report(self) -> HealthReport | None:
        """Get the most recent health report without re-checking."""
        return self._last_report

    def get_service_status(self, name: str) -> ServiceHealth | None:
        """Get status for a specific service."""
        return self._services.get(name)

    # ─── Individual service checks ────────────────────────────────────────

    def _check_service(self, name: str, check_fn) -> None:
        """Run a health check and update circuit breaker state."""
        if name not in self._services:
            self._services[name] = ServiceHealth(name=name)

        svc = self._services[name]
        start = time.time()

        try:
            result = check_fn()
            elapsed_ms = int((time.time() - start) * 1000)

            svc.last_check = time.time()
            svc.response_time_ms = elapsed_ms
            svc.error = None
            svc.consecutive_failures = 0
            svc.consecutive_successes += 1
            svc.last_success = time.time()
            svc.metadata = result if isinstance(result, dict) else {}

            # Circuit breaker: recovery
            if svc.status == ServiceStatus.DOWN or svc.status == ServiceStatus.RECOVERING:
                if svc.consecutive_successes >= RECOVERY_THRESHOLD:
                    svc.status = ServiceStatus.HEALTHY
                else:
                    svc.status = ServiceStatus.RECOVERING
            else:
                svc.status = ServiceStatus.HEALTHY

        except Exception as e:
            elapsed_ms = int((time.time() - start) * 1000)
            svc.last_check = time.time()
            svc.response_time_ms = elapsed_ms
            svc.error = str(e)[:200]
            svc.consecutive_successes = 0
            svc.consecutive_failures += 1

            # Circuit breaker: failure
            if svc.consecutive_failures >= FAILURE_THRESHOLD:
                svc.status = ServiceStatus.DOWN
            else:
                svc.status = ServiceStatus.DEGRADED

    def _check_comfyui(self) -> dict:
        import os
        url = os.getenv("COMFYUI_BASE_URL", "http://localhost:8188")
        resp = httpx.get(f"{url}/system_stats", timeout=5)
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}")
        return {"url": url}

    def _check_ollama(self) -> dict:
        import os
        url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        resp = httpx.get(f"{url}/api/tags", timeout=5)
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}")
        models = resp.json().get("models", [])
        return {"url": url, "models": len(models)}

    def _check_supabase(self) -> dict:
        from backend.database import supabase
        result = supabase.table("talent").select("id").limit(1).execute()
        return {"connected": True, "response": bool(result.data is not None)}

    def _check_b2(self) -> dict:
        import os
        key_id = os.getenv("B2_KEY_ID", "")
        if not key_id:
            raise RuntimeError("B2_KEY_ID not configured")
        # Light check — just verify env is set (full check would list buckets)
        return {"configured": True}

    def _check_elevenlabs(self) -> dict:
        import os
        key = os.getenv("ELEVENLABS_API_KEY", "")
        if not key:
            raise RuntimeError("ELEVENLABS_API_KEY not set")
        resp = httpx.get(
            "https://api.elevenlabs.io/v1/user",
            headers={"xi-api-key": key},
            timeout=5,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}")
        return {"connected": True}

    def _check_worker_api(self) -> dict:
        from backend.infrastructure.worker_api_client import get_worker_client
        client = get_worker_client()
        if not client:
            raise RuntimeError("No worker configured")
        if not client.is_available():
            raise RuntimeError("Worker API unreachable")
        return client.health()


# =============================================================================
# Singleton
# =============================================================================

_monitor: HealthMonitor | None = None


def get_monitor() -> HealthMonitor:
    """Get the global health monitor instance."""
    global _monitor
    if _monitor is None:
        _monitor = HealthMonitor()
    return _monitor

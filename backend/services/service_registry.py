"""Service Registry — Story 051.

Defines the canonical service boundaries, entrypoints, health contracts,
scaling rules, and shared dependencies for AI Studio.

Each service is independently deployable. In local dev, all services run
in one process (start.sh). In staging/production, they deploy separately.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


# =============================================================================
# Service Definitions
# =============================================================================


class ServiceRole(str, Enum):
    """Scaling and leadership behavior."""

    STATELESS = "stateless"      # Horizontally scalable, any number of replicas
    SINGLETON = "singleton"      # Exactly one active instance (leader election)
    SCALABLE_WORKER = "scalable_worker"  # Multiple replicas consuming from queue


class ServiceStatus(str, Enum):
    """Service health states."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    STARTING = "starting"
    STOPPING = "stopping"


@dataclass(frozen=True)
class ServiceDefinition:
    """A deployable service boundary."""

    name: str
    role: ServiceRole
    description: str
    entrypoint: str
    port: int = 0
    # Responsibilities
    responsibilities: tuple[str, ...] = ()
    # Shared dependencies
    requires_supabase: bool = True
    requires_redis: bool = False
    requires_gpu: bool = False
    # Health
    health_endpoint: str = ""
    readiness_endpoint: str = ""
    # Scaling
    min_replicas: int = 1
    max_replicas: int = 1
    # Shutdown
    graceful_shutdown_seconds: int = 30


# =============================================================================
# Service Map
# =============================================================================

SERVICES: dict[str, ServiceDefinition] = {
    "frontend": ServiceDefinition(
        name="frontend",
        role=ServiceRole.STATELESS,
        description="Next.js frontend — serves UI, proxies API calls",
        entrypoint="cd frontend && npm run start",
        port=3000,
        responsibilities=(
            "Serve React pages",
            "Handle client-side routing",
            "Proxy authenticated API calls",
            "Manage browser auth state",
        ),
        requires_supabase=False,  # Uses public anon key only
        health_endpoint="/",
        min_replicas=1,
        max_replicas=10,
        graceful_shutdown_seconds=10,
    ),

    "api": ServiceDefinition(
        name="api",
        role=ServiceRole.STATELESS,
        description="FastAPI backend — handles HTTP requests, NO daemon threads",
        entrypoint="uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000",
        port=8000,
        responsibilities=(
            "Handle HTTP requests/responses",
            "Validate auth and resolve membership",
            "Queue jobs for workers (via Supabase or Redis)",
            "Return immediate responses",
            "Serve health/readiness probes",
        ),
        requires_supabase=True,
        health_endpoint="/health",
        readiness_endpoint="/ready",
        min_replicas=1,
        max_replicas=10,
        graceful_shutdown_seconds=30,
    ),

    "orchestrator": ServiceDefinition(
        name="orchestrator",
        role=ServiceRole.SINGLETON,
        description="GPU lifecycle manager — owns worker state, boot/stop/reconnect",
        entrypoint="uv run python -m backend.services.orchestrator_main",
        port=8001,
        responsibilities=(
            "Own GPU worker lifecycle (boot, reconnect, stop, destroy)",
            "Maintain worker session state",
            "Auto-provision on demand",
            "Monitor worker health",
            "Route generation requests to available workers",
            "Cost tracking for active sessions",
        ),
        requires_supabase=True,
        requires_gpu=False,  # Manages GPUs remotely, doesn't need one locally
        health_endpoint="/health",
        min_replicas=1,
        max_replicas=1,  # SINGLETON — only one can own GPU state
        graceful_shutdown_seconds=60,  # Time to gracefully stop workers
    ),

    "worker": ServiceDefinition(
        name="worker",
        role=ServiceRole.SCALABLE_WORKER,
        description="Background job processor — long-running training, model downloads, etc.",
        entrypoint="uv run python -m backend.services.worker_main",
        port=0,  # No HTTP port — consumes from queue
        responsibilities=(
            "Execute LoRA training jobs",
            "Download and cache models",
            "Process video renders",
            "Execute approved governance actions",
            "Long-running tasks that survive API restarts",
        ),
        requires_supabase=True,
        requires_redis=True,  # Job queue consumption
        health_endpoint="",  # Health via heartbeat, not HTTP
        min_replicas=1,
        max_replicas=5,
        graceful_shutdown_seconds=300,  # Training can take minutes to checkpoint
    ),

    "scheduler": ServiceDefinition(
        name="scheduler",
        role=ServiceRole.SINGLETON,
        description="Periodic task scheduler — health checks, UAT, publishing, cleanup",
        entrypoint="uv run python -m backend.services.scheduler_main",
        port=8002,
        responsibilities=(
            "Ise health monitoring (30s interval)",
            "Ise UAT test scheduling (hourly)",
            "Scheduled social publishing",
            "Stale job cleanup",
            "Cost alert checks",
            "Credential expiration checks",
        ),
        requires_supabase=True,
        health_endpoint="/health",
        min_replicas=1,
        max_replicas=1,  # SINGLETON — prevent duplicate scheduling
        graceful_shutdown_seconds=15,
    ),

    "migration": ServiceDefinition(
        name="migration",
        role=ServiceRole.SINGLETON,
        description="Database migration runner — applies schema changes",
        entrypoint="uv run python -m backend.services.migration_main",
        port=0,
        responsibilities=(
            "Apply SQL migrations to Supabase",
            "Verify schema state",
            "Run data backfills",
        ),
        requires_supabase=True,
        min_replicas=0,  # Only runs on deploy
        max_replicas=1,
        graceful_shutdown_seconds=600,  # Migrations can be slow
    ),
}


# =============================================================================
# Service Health Contract
# =============================================================================


@dataclass
class HealthCheck:
    """Standard health check response."""

    service: str
    status: ServiceStatus
    version: str = "1.0.0"
    uptime_seconds: float = 0.0
    checks: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "service": self.service,
            "status": self.status.value,
            "version": self.version,
            "uptime_seconds": round(self.uptime_seconds, 1),
            "checks": self.checks,
        }


# =============================================================================
# Topology
# =============================================================================


@dataclass(frozen=True)
class EnvironmentTopology:
    """How services are deployed in each environment."""

    environment: str
    description: str
    services: dict[str, int]  # service_name → replica count
    shared_process: bool  # True = all in one process (local dev)


TOPOLOGIES: dict[str, EnvironmentTopology] = {
    "local": EnvironmentTopology(
        environment="local",
        description="All services in one process via start.sh (development)",
        services={
            "frontend": 1,
            "api": 1,
            "orchestrator": 1,  # In-process singleton
            "worker": 0,  # Threads (legacy) until queue is set up
            "scheduler": 1,  # In-process threads (legacy)
            "migration": 0,  # Manual
        },
        shared_process=True,
    ),
    "staging": EnvironmentTopology(
        environment="staging",
        description="Separate processes, single machine (Railway/Render)",
        services={
            "frontend": 1,
            "api": 1,
            "orchestrator": 1,
            "worker": 1,
            "scheduler": 1,
            "migration": 0,  # Run on deploy
        },
        shared_process=False,
    ),
    "production": EnvironmentTopology(
        environment="production",
        description="Fully separated, horizontally scaled",
        services={
            "frontend": 2,
            "api": 2,
            "orchestrator": 1,
            "worker": 2,
            "scheduler": 1,
            "migration": 0,
        },
        shared_process=False,
    ),
}


# =============================================================================
# Query Helpers
# =============================================================================


def get_service(name: str) -> ServiceDefinition | None:
    """Get a service definition by name."""
    return SERVICES.get(name)


def get_singletons() -> list[str]:
    """Get names of services that must be singletons."""
    return [name for name, svc in SERVICES.items() if svc.role == ServiceRole.SINGLETON]


def get_topology(environment: str) -> EnvironmentTopology | None:
    """Get deployment topology for an environment."""
    return TOPOLOGIES.get(environment)


def get_all_services() -> list[dict]:
    """Get all service definitions as dicts (for admin dashboard)."""
    return [
        {
            "name": svc.name,
            "role": svc.role.value,
            "description": svc.description,
            "port": svc.port,
            "responsibilities": list(svc.responsibilities),
            "scaling": f"{svc.min_replicas}-{svc.max_replicas}",
            "singleton": svc.role == ServiceRole.SINGLETON,
        }
        for svc in SERVICES.values()
    ]

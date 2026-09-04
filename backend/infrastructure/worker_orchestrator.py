"""Worker Orchestrator — Manages the lifecycle of GPU workers.

Refactored to use the ComputeProvider Protocol (R13.1) for provider-agnostic
compute management, with Supabase-backed durable state (R13.8), health checks
every 60s (R13.10), 3-strike termination (R13.11), fleet limits (R13.12),
and guaranteed cleanup in finally blocks (R13.5).

Validates: Requirements R13.5, R13.6, R13.7, R13.8, R13.9, R13.10, R13.11, R13.12
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from backend.app.providers.compute import (
    ComputeProvider,
    ComputeProviderError,
    ComputeRequirements,
    HealthState,
    InstanceHandle,
    InstanceState,
    ProvisionError,
    TerminateError,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

HEALTH_CHECK_INTERVAL_SECONDS = 60
"""Health check interval per R13.10."""

MAX_CONSECUTIVE_HEALTH_FAILURES = 3
"""Terminate after this many consecutive failures per R13.11."""

DEFAULT_FLEET_MAX_INSTANCES = 3
"""Default maximum concurrent workers per org per R13.12."""

DEFAULT_FLEET_IDLE_TIMEOUT_MINUTES = 15
"""Default idle timeout per R13.6."""

BOOT_TIMEOUT_SECONDS = 300
"""5 minutes boot timeout per R13.9."""

MAX_PROVISION_RETRIES = 3
"""Maximum retry attempts on different hosts per R13.9."""

BLACKLIST_DURATION_HOURS = 24
"""Host blacklist duration after boot failure per R13.9."""


# =============================================================================
# Data Models
# =============================================================================


@dataclass
class WorkerInstance:
    """A tracked worker instance — persisted to Supabase.

    This is the canonical state record for a provisioned compute instance.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    org_id: str = ""
    provider_name: str = ""
    provider_instance_id: str = ""
    gpu_name: str = ""
    gpu_vram_gb: float = 0.0
    host: str = ""
    port: int = 0
    status: str = "provisioning"
    hourly_rate: float = 0.0
    current_job_id: str | None = None
    consecutive_health_failures: int = 0
    last_health_check_at: str | None = None
    last_job_completed_at: str | None = None
    total_cost_usd: float = 0.0
    jobs_completed: int = 0
    metadata: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    terminated_at: str | None = None

    def to_db_row(self) -> dict[str, Any]:
        """Convert to a dict suitable for Supabase insert/update."""
        return {
            "id": self.id,
            "org_id": self.org_id,
            "provider_name": self.provider_name,
            "provider_instance_id": self.provider_instance_id,
            "gpu_name": self.gpu_name,
            "gpu_vram_gb": self.gpu_vram_gb,
            "host": self.host,
            "port": self.port,
            "status": self.status,
            "hourly_rate": self.hourly_rate,
            "current_job_id": self.current_job_id,
            "consecutive_health_failures": self.consecutive_health_failures,
            "last_health_check_at": self.last_health_check_at,
            "last_job_completed_at": self.last_job_completed_at,
            "total_cost_usd": self.total_cost_usd,
            "jobs_completed": self.jobs_completed,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "terminated_at": self.terminated_at,
        }


    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> "WorkerInstance":
        """Construct from a Supabase row."""
        return cls(
            id=row.get("id", str(uuid.uuid4())),
            org_id=row.get("org_id", ""),
            provider_name=row.get("provider_name", ""),
            provider_instance_id=row.get("provider_instance_id", ""),
            gpu_name=row.get("gpu_name", ""),
            gpu_vram_gb=row.get("gpu_vram_gb", 0.0),
            host=row.get("host", ""),
            port=row.get("port", 0),
            status=row.get("status", "unknown"),
            hourly_rate=row.get("hourly_rate", 0.0),
            current_job_id=row.get("current_job_id"),
            consecutive_health_failures=row.get("consecutive_health_failures", 0),
            last_health_check_at=row.get("last_health_check_at"),
            last_job_completed_at=row.get("last_job_completed_at"),
            total_cost_usd=row.get("total_cost_usd", 0.0),
            jobs_completed=row.get("jobs_completed", 0),
            metadata=row.get("metadata") or {},
            created_at=row.get("created_at", datetime.now(UTC).isoformat()),
            updated_at=row.get("updated_at", datetime.now(UTC).isoformat()),
            terminated_at=row.get("terminated_at"),
        )


# =============================================================================
# Supabase State Store
# =============================================================================


class WorkerStateStore:
    """Persists worker instance state to Supabase (R13.8).

    All state mutations go through this store, ensuring that worker state
    survives backend restarts. Uses the `worker_instances` table.
    """

    TABLE = "worker_instances"

    def __init__(self) -> None:
        self._client = None

    def _get_client(self):
        """Lazy Supabase client access."""
        if self._client is None:
            from backend.database import get_supabase_client
            self._client = get_supabase_client()
        return self._client

    def create(self, instance: WorkerInstance) -> WorkerInstance:
        """Insert a new worker instance record."""
        client = self._get_client()
        client.table(self.TABLE).insert(instance.to_db_row()).execute()
        logger.info(
            "worker_instance_created",
            extra={"worker_id": instance.id, "org_id": instance.org_id},
        )
        return instance

    def update(self, instance: WorkerInstance) -> WorkerInstance:
        """Update an existing worker instance record."""
        instance.updated_at = datetime.now(UTC).isoformat()
        client = self._get_client()
        client.table(self.TABLE).update(
            instance.to_db_row()
        ).eq("id", instance.id).execute()
        return instance


    def get_by_id(self, instance_id: str) -> WorkerInstance | None:
        """Get a worker instance by ID."""
        client = self._get_client()
        result = (
            client.table(self.TABLE)
            .select("*")
            .eq("id", instance_id)
            .execute()
        )
        if result.data:
            return WorkerInstance.from_db_row(result.data[0])
        return None

    def list_active_for_org(self, org_id: str) -> list[WorkerInstance]:
        """List all non-terminated workers for an org."""
        client = self._get_client()
        result = (
            client.table(self.TABLE)
            .select("*")
            .eq("org_id", org_id)
            .neq("status", "terminated")
            .neq("status", "failed")
            .order("created_at", desc=True)
            .execute()
        )
        return [WorkerInstance.from_db_row(row) for row in result.data]

    def count_active_for_org(self, org_id: str) -> int:
        """Count non-terminated workers for an org (for fleet limits)."""
        client = self._get_client()
        result = (
            client.table(self.TABLE)
            .select("id", count="exact")
            .eq("org_id", org_id)
            .neq("status", "terminated")
            .neq("status", "failed")
            .execute()
        )
        return result.count if result.count is not None else len(result.data)


    def list_all_active(self) -> list[WorkerInstance]:
        """List all non-terminated workers (for health check loop)."""
        client = self._get_client()
        result = (
            client.table(self.TABLE)
            .select("*")
            .in_("status", ["provisioning", "booting", "ready", "busy", "idle"])
            .order("created_at", desc=True)
            .execute()
        )
        return [WorkerInstance.from_db_row(row) for row in result.data]

    def mark_terminated(self, instance_id: str) -> None:
        """Mark a worker as terminated."""
        now = datetime.now(UTC).isoformat()
        client = self._get_client()
        client.table(self.TABLE).update({
            "status": "terminated",
            "terminated_at": now,
            "updated_at": now,
        }).eq("id", instance_id).execute()

    def get_daily_spend_for_org(self, org_id: str) -> float:
        """Calculate total GPU spend for an org today (R13.7)."""
        today_start = datetime.now(UTC).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).isoformat()
        client = self._get_client()
        result = (
            client.table(self.TABLE)
            .select("total_cost_usd")
            .eq("org_id", org_id)
            .gte("created_at", today_start)
            .execute()
        )
        return sum(row.get("total_cost_usd", 0.0) for row in result.data)


# =============================================================================
# Provider Registry
# =============================================================================


class ComputeProviderRegistry:
    """Registry of available ComputeProvider implementations.

    Providers are registered by name and looked up at runtime.
    """

    def __init__(self) -> None:
        self._providers: dict[str, ComputeProvider] = {}

    def register(self, name: str, provider: ComputeProvider) -> None:
        """Register a compute provider by name."""
        self._providers[name] = provider
        logger.info(f"Registered compute provider: {name}")

    def get(self, name: str) -> ComputeProvider | None:
        """Get a provider by name."""
        return self._providers.get(name)

    def list_names(self) -> list[str]:
        """List all registered provider names."""
        return list(self._providers.keys())

    @property
    def providers(self) -> dict[str, ComputeProvider]:
        """All registered providers."""
        return self._providers


# =============================================================================
# Worker Orchestrator
# =============================================================================


class WorkerOrchestrator:
    """Orchestrates GPU worker lifecycle using ComputeProvider interface.

    Responsibilities (R13.5-R13.12):
    - Provision workers via provider-agnostic interface
    - Track state in Supabase (durable across restarts)
    - Enforce fleet limits per org (fleet_max_instances)
    - Terminate idle workers (fleet_idle_timeout)
    - Health check every 60s; 3 consecutive failures → terminate + re-queue
    - Always terminate in finally blocks
    - Track daily GPU spend; reject launches when budget exceeded

    Usage:
        orchestrator = WorkerOrchestrator(registry, store)
        instance = await orchestrator.provision_worker(org_id, requirements)
        status = await orchestrator.get_status(org_id)
        await orchestrator.terminate_worker(instance.id)
    """

    def __init__(
        self,
        registry: ComputeProviderRegistry,
        store: WorkerStateStore | None = None,
        fleet_max_instances: int = DEFAULT_FLEET_MAX_INSTANCES,
        fleet_idle_timeout_minutes: int = DEFAULT_FLEET_IDLE_TIMEOUT_MINUTES,
        daily_budget_usd: float = 10.0,
    ) -> None:
        self._registry = registry
        self._store = store or WorkerStateStore()
        self._fleet_max_instances = fleet_max_instances
        self._fleet_idle_timeout_minutes = fleet_idle_timeout_minutes
        self._daily_budget_usd = daily_budget_usd
        self._health_check_task: asyncio.Task | None = None


    # ─── Fleet Limit Enforcement (R13.12) ─────────────────────────────────

    def _check_fleet_limit(self, org_id: str) -> None:
        """Raise if org has reached fleet_max_instances.

        Validates: R13.12
        """
        active_count = self._store.count_active_for_org(org_id)
        if active_count >= self._fleet_max_instances:
            raise FleetLimitExceededError(
                f"Fleet limit reached: {active_count}/{self._fleet_max_instances} "
                f"concurrent workers for org {org_id[:8]}..."
            )

    def _check_daily_budget(self, org_id: str) -> None:
        """Raise if org has exceeded daily GPU budget.

        Validates: R13.7
        """
        daily_spend = self._store.get_daily_spend_for_org(org_id)
        if daily_spend >= self._daily_budget_usd:
            raise DailyBudgetExceededError(
                f"Daily GPU budget exceeded: ${daily_spend:.2f} / "
                f"${self._daily_budget_usd:.2f} for org {org_id[:8]}..."
            )


    # ─── Provision (R13.5, R13.9) ─────────────────────────────────────────

    async def provision_worker(
        self,
        org_id: str,
        requirements: ComputeRequirements,
        preferred_provider: str | None = None,
    ) -> WorkerInstance:
        """Provision a new compute worker.

        Enforces fleet limits and daily budget before provisioning.
        Uses finally block to guarantee cleanup on failure.
        Retries up to MAX_PROVISION_RETRIES on different hosts (R13.9).

        Args:
            org_id: Organization requesting the worker.
            requirements: GPU/workload requirements.
            preferred_provider: Provider name override.

        Returns:
            The provisioned WorkerInstance with Supabase-persisted state.

        Raises:
            FleetLimitExceededError: If org is at max workers.
            DailyBudgetExceededError: If daily GPU budget exceeded.
            ProvisionError: If provisioning fails after retries.
        """
        # Pre-flight checks
        self._check_fleet_limit(org_id)
        self._check_daily_budget(org_id)

        # Select provider
        provider_name = preferred_provider or self._select_provider(requirements)
        provider = self._registry.get(provider_name)
        if provider is None:
            raise ComputeProviderError(
                f"Provider '{provider_name}' not registered",
                provider=provider_name,
            )

        # Create instance record in Supabase (status=provisioning)
        instance = WorkerInstance(
            org_id=org_id,
            provider_name=provider_name,
            status="provisioning",
            metadata={"workload_type": requirements.workload_type},
        )
        self._store.create(instance)


        # Attempt provisioning with retries (R13.9)
        last_error: Exception | None = None
        for attempt in range(1, MAX_PROVISION_RETRIES + 1):
            try:
                handle: InstanceHandle = await provider.provision(requirements)

                # Update instance with provider details
                instance.provider_instance_id = handle.instance_id
                instance.host = handle.host
                instance.port = handle.port
                instance.status = "ready"
                instance.gpu_name = requirements.workload_type
                instance.gpu_vram_gb = requirements.vram_gb
                self._store.update(instance)

                logger.info(
                    "worker_provisioned",
                    extra={
                        "worker_id": instance.id,
                        "org_id": org_id,
                        "provider": provider_name,
                        "attempt": attempt,
                    },
                )
                return instance

            except ProvisionError as exc:
                last_error = exc
                logger.warning(
                    "provision_attempt_failed",
                    extra={
                        "worker_id": instance.id,
                        "org_id": org_id,
                        "provider": provider_name,
                        "attempt": attempt,
                        "error": str(exc),
                    },
                )
                # Blacklist failed host (R13.9)
                self._blacklist_host(provider_name, str(exc))

                if attempt >= MAX_PROVISION_RETRIES:
                    break
                # Brief backoff before retry
                await asyncio.sleep(2 * attempt)


        # All retries exhausted — mark failed
        instance.status = "failed"
        instance.metadata["error"] = str(last_error) if last_error else "Unknown"
        self._store.update(instance)
        raise ProvisionError(
            f"Provisioning failed after {MAX_PROVISION_RETRIES} attempts: {last_error}",
            provider=provider_name,
        )


    # ─── Terminate (R13.5) ────────────────────────────────────────────────

    async def terminate_worker(self, instance_id: str) -> None:
        """Terminate a worker instance.

        Always executes termination in a finally-safe pattern (R13.5).
        Records session cost before termination.

        Args:
            instance_id: The worker instance ID to terminate.
        """
        instance = self._store.get_by_id(instance_id)
        if instance is None:
            logger.warning(f"terminate_worker: instance {instance_id} not found")
            return

        if instance.status in ("terminated", "failed"):
            return

        provider = self._registry.get(instance.provider_name)
        try:
            if provider and instance.provider_instance_id:
                await provider.terminate(instance.provider_instance_id)
        except TerminateError as exc:
            logger.error(
                "terminate_failed",
                extra={
                    "worker_id": instance_id,
                    "provider": instance.provider_name,
                    "error": str(exc),
                },
            )
        finally:
            # Always mark as terminated in DB regardless of provider response
            self._record_session_cost(instance)
            instance.status = "terminated"
            instance.terminated_at = datetime.now(UTC).isoformat()
            self._store.update(instance)
            logger.info(
                "worker_terminated",
                extra={"worker_id": instance_id, "org_id": instance.org_id},
            )


    # ─── Health Checks (R13.10, R13.11) ───────────────────────────────────

    async def health_check_worker(self, instance_id: str) -> HealthState:
        """Perform a health check on a single worker.

        If 3 consecutive failures are detected, terminates the worker
        and re-queues any in-progress job (R13.11).

        Returns:
            The health state after the check.
        """
        instance = self._store.get_by_id(instance_id)
        if instance is None or instance.status in ("terminated", "failed"):
            return HealthState.UNREACHABLE

        provider = self._registry.get(instance.provider_name)
        if provider is None:
            return HealthState.UNREACHABLE

        try:
            health = await provider.health_check(instance.provider_instance_id)
            instance.last_health_check_at = datetime.now(UTC).isoformat()

            if health.state in (HealthState.HEALTHY, HealthState.DEGRADED):
                instance.consecutive_health_failures = 0
                self._store.update(instance)
                return health.state
            else:
                instance.consecutive_health_failures += 1
                self._store.update(instance)
        except ComputeProviderError:
            instance.consecutive_health_failures += 1
            instance.last_health_check_at = datetime.now(UTC).isoformat()
            self._store.update(instance)


        # 3 consecutive failures → terminate + re-queue (R13.11)
        if instance.consecutive_health_failures >= MAX_CONSECUTIVE_HEALTH_FAILURES:
            logger.warning(
                "worker_unresponsive_terminating",
                extra={
                    "worker_id": instance_id,
                    "failures": instance.consecutive_health_failures,
                    "job_id": instance.current_job_id,
                },
            )
            # Re-queue any in-progress job before terminating
            if instance.current_job_id:
                self._requeue_job(instance.current_job_id, instance.org_id)

            await self.terminate_worker(instance_id)
            return HealthState.UNREACHABLE

        return HealthState.UNHEALTHY


    async def run_health_check_loop(self) -> None:
        """Background loop: health check all active workers every 60s.

        Validates: R13.10

        This should be started as an asyncio task on application startup.
        """
        logger.info("Health check loop started (interval=%ds)", HEALTH_CHECK_INTERVAL_SECONDS)
        while True:
            try:
                instances = self._store.list_all_active()
                for instance in instances:
                    if instance.status in ("ready", "busy", "idle"):
                        await self.health_check_worker(instance.id)
                # Also check for idle timeout (R13.6)
                await self._check_idle_timeouts(instances)
            except Exception as exc:
                logger.error(f"Health check loop error: {exc}")
            await asyncio.sleep(HEALTH_CHECK_INTERVAL_SECONDS)

    async def _check_idle_timeouts(self, instances: list[WorkerInstance]) -> None:
        """Terminate workers that have been idle beyond fleet_idle_timeout.

        Validates: R13.6
        """
        now = datetime.now(UTC)
        timeout_seconds = self._fleet_idle_timeout_minutes * 60

        for instance in instances:
            if instance.status != "idle" or instance.current_job_id:
                continue
            # Determine last activity time
            last_active = instance.last_job_completed_at or instance.created_at
            try:
                last_dt = datetime.fromisoformat(last_active)
            except (ValueError, TypeError):
                continue

            idle_seconds = (now - last_dt).total_seconds()
            if idle_seconds >= timeout_seconds:
                logger.info(
                    "idle_timeout_terminating",
                    extra={
                        "worker_id": instance.id,
                        "idle_seconds": idle_seconds,
                    },
                )
                await self.terminate_worker(instance.id)


    # ─── Job Execution with Guaranteed Cleanup (R13.5) ────────────────────

    def assign_job(self, instance_id: str, job_id: str) -> None:
        """Mark a worker as busy with a job."""
        instance = self._store.get_by_id(instance_id)
        if instance is None:
            raise ComputeProviderError(f"Worker {instance_id} not found")
        instance.current_job_id = job_id
        instance.status = "busy"
        self._store.update(instance)

    def release_job(self, instance_id: str) -> None:
        """Mark a worker as idle after job completion."""
        instance = self._store.get_by_id(instance_id)
        if instance is None:
            return
        instance.current_job_id = None
        instance.status = "idle"
        instance.jobs_completed += 1
        instance.last_job_completed_at = datetime.now(UTC).isoformat()
        self._store.update(instance)


    # ─── Status & Queries ─────────────────────────────────────────────────

    def get_status(self, org_id: str) -> dict[str, Any]:
        """Get orchestrator status for an org."""
        instances = self._store.list_active_for_org(org_id)
        return {
            "active_workers": len(instances),
            "fleet_max_instances": self._fleet_max_instances,
            "fleet_idle_timeout_minutes": self._fleet_idle_timeout_minutes,
            "daily_budget_usd": self._daily_budget_usd,
            "daily_spend_usd": self._store.get_daily_spend_for_org(org_id),
            "workers": [
                {
                    "id": i.id,
                    "provider": i.provider_name,
                    "gpu_name": i.gpu_name,
                    "status": i.status,
                    "host": i.host,
                    "port": i.port,
                    "current_job_id": i.current_job_id,
                    "hourly_rate": i.hourly_rate,
                    "total_cost_usd": i.total_cost_usd,
                    "jobs_completed": i.jobs_completed,
                    "consecutive_health_failures": i.consecutive_health_failures,
                    "created_at": i.created_at,
                }
                for i in instances
            ],
        }

    def get_worker(self, instance_id: str) -> WorkerInstance | None:
        """Get a single worker instance by ID."""
        return self._store.get_by_id(instance_id)


    # ─── Internal Helpers ─────────────────────────────────────────────────

    def _select_provider(self, requirements: ComputeRequirements) -> str:
        """Select the best provider for the given requirements.

        Prefers providers that satisfy all required capabilities.
        Falls back to first registered provider if none satisfy all caps.
        """
        for name, provider in self._registry.providers.items():
            if provider.capabilities.satisfies(requirements.required_capabilities):
                return name
        # Fall back to first available
        names = self._registry.list_names()
        if not names:
            raise ComputeProviderError("No compute providers registered")
        return names[0]

    def _blacklist_host(self, provider_name: str, error_msg: str) -> None:
        """Blacklist a host for 24 hours after boot failure (R13.9)."""
        try:
            from backend.infrastructure.provider_reputation import (
                get_reputation_engine,
            )
            engine = get_reputation_engine()
            engine.record_attempt({
                "host_id": f"{provider_name}_failed_{int(time.time())}",
                "provider": provider_name,
                "status": "failed",
                "failure_reason": error_msg[:200],
            })
        except Exception as exc:
            logger.debug(f"Could not record blacklist: {exc}")

    def _requeue_job(self, job_id: str, org_id: str) -> None:
        """Re-queue a job that was on an unresponsive worker (R13.11)."""
        try:
            from backend.database import get_supabase_client
            client = get_supabase_client()
            client.table("jobs").update({
                "status": "queued",
                "worker_id": None,
                "worker_name": None,
                "updated_at": datetime.now(UTC).isoformat(),
            }).eq("id", job_id).eq("org_id", org_id).execute()
            logger.info(
                "job_requeued",
                extra={"job_id": job_id, "org_id": org_id},
            )
        except Exception as exc:
            logger.error(f"Failed to requeue job {job_id}: {exc}")


    def _record_session_cost(self, instance: WorkerInstance) -> None:
        """Calculate and record the total session cost before termination."""
        if not instance.created_at or instance.hourly_rate <= 0:
            return
        try:
            created = datetime.fromisoformat(instance.created_at)
            elapsed_hours = (datetime.now(UTC) - created).total_seconds() / 3600
            instance.total_cost_usd = round(elapsed_hours * instance.hourly_rate, 4)
        except (ValueError, TypeError):
            pass

    # ─── Lifecycle ────────────────────────────────────────────────────────

    def start_health_checks(self) -> None:
        """Start the background health check loop.

        Call this on application startup.
        """
        if self._health_check_task is None or self._health_check_task.done():
            loop = asyncio.get_event_loop()
            self._health_check_task = loop.create_task(
                self.run_health_check_loop()
            )

    # ─── Backward Compatibility (legacy router consumers) ────────────────

    @property
    def session(self) -> LegacyWorkerSession | None:
        """Legacy property: returns first active worker as a session.

        Deprecated — use get_status() or get_worker() instead.
        """
        try:
            instances = self._store.list_all_active()
            if instances:
                return LegacyWorkerSession.from_worker_instance(instances[0])
        except Exception:
            pass
        return None

    @property
    def is_active(self) -> bool:
        """Legacy property: whether any worker is active."""
        try:
            instances = self._store.list_all_active()
            return len(instances) > 0
        except Exception:
            return False

    def launch_worker(self, **kwargs) -> dict[str, Any]:
        """Legacy sync interface — returns status dict for router.

        Deprecated — use provision_worker() instead.
        """
        return {
            "status": "deprecated",
            "message": (
                "launch_worker() is deprecated. "
                "Use POST /api/v1/infrastructure/provision with async interface."
            ),
        }

    def stop_worker(self) -> dict[str, Any]:
        """Legacy sync interface — returns status dict for router.

        Deprecated — use terminate_worker() instead.
        """
        return {
            "status": "deprecated",
            "message": (
                "stop_worker() is deprecated. "
                "Use DELETE /api/v1/infrastructure/workers/{id} with async interface."
            ),
        }

    def get_connection_log(self) -> list[dict[str, Any]]:
        """Legacy connection log — returns empty list.

        Connection race logging is now handled by provider_reputation.
        """
        return []

    async def shutdown(self) -> None:
        """Graceful shutdown — cancel health check loop."""
        if self._health_check_task and not self._health_check_task.done():
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass


# =============================================================================
# Exceptions
# =============================================================================


class FleetLimitExceededError(Exception):
    """Raised when an org has reached fleet_max_instances (R13.12)."""
    pass


class DailyBudgetExceededError(Exception):
    """Raised when an org has exceeded daily GPU budget (R13.7)."""
    pass


# =============================================================================
# Module-level singleton
# =============================================================================

_orchestrator: WorkerOrchestrator | None = None
_registry: ComputeProviderRegistry | None = None


def get_provider_registry() -> ComputeProviderRegistry:
    """Get or create the global ComputeProviderRegistry.

    On first creation, registers the Thunder Compute provider (the platform's
    single GPU provider — RunPod + Vast.ai retired). Registration is lazy so
    the module imports cleanly even without an API key configured; calls
    fail with a clear error if the key is missing.
    """
    global _registry
    if _registry is None:
        _registry = ComputeProviderRegistry()
        try:
            from backend.app.providers.thunder_provider import ThunderComputeProvider

            _registry.register("thundercompute", ThunderComputeProvider())
            logger.info("compute_provider_registered: thundercompute")
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("compute_provider_register_failed: %s", str(exc))
    return _registry


def get_orchestrator() -> WorkerOrchestrator:
    """Get or create the global WorkerOrchestrator singleton."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = WorkerOrchestrator(
            registry=get_provider_registry(),
        )
    return _orchestrator


# =============================================================================
# Backward Compatibility Layer
# =============================================================================
# The following classes and properties maintain compatibility with the existing
# router.py and other consumers that use the old WorkerOrchestrator API.
# These will be deprecated once the router is migrated to the async interface.


@dataclass
class LegacyWorkerSession:
    """Backward-compatible WorkerSession for existing router consumers."""

    id: str = ""
    instance_id: int | None = None
    worker_name: str = ""
    gpu_name: str = ""
    ssh_host: str = ""
    ssh_port: int = 0
    comfyui_url: str | None = None
    status: str = "pending"
    progress_message: str = ""
    models_loaded: list[str] = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    ended_at: str | None = None
    total_cost: float = 0.0
    hourly_rate: float = 0.0
    jobs_completed: int = 0
    metadata: dict = field(default_factory=dict)

    @classmethod
    def from_worker_instance(cls, instance: WorkerInstance) -> "LegacyWorkerSession":
        """Create from a WorkerInstance for backward compat."""
        return cls(
            id=instance.id,
            instance_id=int(instance.provider_instance_id)
                if instance.provider_instance_id and instance.provider_instance_id.isdigit()
                else None,
            worker_name=f"{instance.provider_name}-{instance.gpu_name}-{instance.id[:8]}",
            gpu_name=instance.gpu_name,
            ssh_host=instance.host,
            ssh_port=instance.port,
            comfyui_url=f"http://{instance.host}:{instance.port}" if instance.host else None,
            status=instance.status,
            progress_message=f"Worker {instance.status}",
            started_at=instance.created_at,
            ended_at=instance.terminated_at,
            total_cost=instance.total_cost_usd,
            hourly_rate=instance.hourly_rate,
            jobs_completed=instance.jobs_completed,
            metadata=instance.metadata,
        )

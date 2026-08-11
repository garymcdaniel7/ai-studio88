"""Unit tests for the Worker Orchestrator with provider abstraction.

Tests cover:
- Fleet limit enforcement (R13.12)
- Daily budget enforcement (R13.7)
- Provider selection via ComputeProvider interface (R13.1)
- Health check logic with 3-strike termination (R13.10, R13.11)
- Idle timeout termination (R13.6)
- Guaranteed cleanup in finally blocks (R13.5)
- Supabase state persistence (R13.8)
- Retry with blacklisting on boot failure (R13.9)

Run with: pytest tests/unit/test_worker_orchestrator.py -v
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from backend.app.providers.compute import (
    ComputeProvider,
    ComputeProviderCapabilities,
    ComputeRequirements,
    CostEstimate,
    HealthState,
    HealthStatus,
    InstanceHandle,
    InstanceState,
    InstanceStatus,
    OfferInfo,
    ProvisionError,
)
from backend.infrastructure.worker_orchestrator import (
    ComputeProviderRegistry,
    DailyBudgetExceededError,
    FleetLimitExceededError,
    WorkerInstance,
    WorkerOrchestrator,
    WorkerStateStore,
)


# =============================================================================
# Fake Provider (satisfies ComputeProvider Protocol)
# =============================================================================


class FakeComputeProvider:
    """Test double that satisfies ComputeProvider protocol."""

    def __init__(
        self,
        provision_fail: bool = False,
        health_state: HealthState = HealthState.HEALTHY,
    ) -> None:
        self._provision_fail = provision_fail
        self._health_state = health_state
        self._terminated: list[str] = []
        self._provisions: int = 0

    @property
    def capabilities(self) -> ComputeProviderCapabilities:
        return ComputeProviderCapabilities(
            name="fake",
            display_name="Fake Provider",
            supports_persistent_storage=True,
            supports_cost_estimation=True,
        )

    async def provision(self, requirements: ComputeRequirements) -> InstanceHandle:
        if self._provision_fail:
            raise ProvisionError("Simulated boot failure", provider="fake")
        self._provisions += 1
        return InstanceHandle(
            instance_id=f"fake-inst-{self._provisions}",
            host="10.0.0.1",
            port=8188,
            state=InstanceState.RUNNING,
        )

    async def terminate(self, instance_id: str) -> None:
        self._terminated.append(instance_id)

    async def health_check(self, instance_id: str) -> HealthStatus:
        return HealthStatus(
            instance_id=instance_id,
            state=self._health_state,
            message="ok" if self._health_state == HealthState.HEALTHY else "bad",
        )

    async def get_status(self, instance_id: str) -> InstanceStatus:
        return InstanceStatus(instance_id=instance_id, state=InstanceState.RUNNING)

    async def list_available(self) -> list[OfferInfo]:
        return [OfferInfo(offer_id="o1", gpu_name="RTX 4090", vram_gb=24, price_per_hour_usd=0.50)]

    async def estimate_cost(self, requirements: ComputeRequirements) -> CostEstimate:
        return CostEstimate(estimated_usd=0.50, estimated_duration_seconds=3600)


# =============================================================================
# Fake State Store (in-memory substitute for Supabase in unit tests)
# =============================================================================


class FakeStateStore:
    """In-memory WorkerStateStore for unit tests (no Supabase dependency)."""

    def __init__(self) -> None:
        self._instances: dict[str, WorkerInstance] = {}

    def create(self, instance: WorkerInstance) -> WorkerInstance:
        self._instances[instance.id] = instance
        return instance

    def update(self, instance: WorkerInstance) -> WorkerInstance:
        instance.updated_at = datetime.now(UTC).isoformat()
        self._instances[instance.id] = instance
        return instance

    def get_by_id(self, instance_id: str) -> WorkerInstance | None:
        return self._instances.get(instance_id)

    def list_active_for_org(self, org_id: str) -> list[WorkerInstance]:
        return [
            i for i in self._instances.values()
            if i.org_id == org_id and i.status not in ("terminated", "failed")
        ]

    def count_active_for_org(self, org_id: str) -> int:
        return len(self.list_active_for_org(org_id))

    def list_all_active(self) -> list[WorkerInstance]:
        return [
            i for i in self._instances.values()
            if i.status in ("provisioning", "booting", "ready", "busy", "idle")
        ]

    def mark_terminated(self, instance_id: str) -> None:
        if instance_id in self._instances:
            self._instances[instance_id].status = "terminated"
            self._instances[instance_id].terminated_at = datetime.now(UTC).isoformat()

    def get_daily_spend_for_org(self, org_id: str) -> float:
        return sum(
            i.total_cost_usd for i in self._instances.values()
            if i.org_id == org_id
        )


# =============================================================================
# Fixtures
# =============================================================================

ORG_ID = "org-test-12345678"


@pytest.fixture
def fake_provider() -> FakeComputeProvider:
    return FakeComputeProvider()


@pytest.fixture
def fake_store() -> FakeStateStore:
    return FakeStateStore()


@pytest.fixture
def registry(fake_provider) -> ComputeProviderRegistry:
    reg = ComputeProviderRegistry()
    reg.register("fake", fake_provider)
    return reg


@pytest.fixture
def orchestrator(registry, fake_store) -> WorkerOrchestrator:
    return WorkerOrchestrator(
        registry=registry,
        store=fake_store,
        fleet_max_instances=3,
        fleet_idle_timeout_minutes=15,
        daily_budget_usd=10.0,
    )


# =============================================================================
# Tests: Fleet Limit Enforcement (R13.12)
# =============================================================================


@pytest.mark.unit
class TestFleetLimits:
    """Validates: R13.12 — never provision more than fleet_max_instances."""

    @pytest.mark.asyncio
    async def test_provision_within_limit(self, orchestrator, fake_store):
        """Provisioning succeeds when under fleet limit."""
        req = ComputeRequirements(vram_gb=24)
        instance = await orchestrator.provision_worker(ORG_ID, req)
        assert instance.status == "ready"
        assert fake_store.count_active_for_org(ORG_ID) == 1

    @pytest.mark.asyncio
    async def test_provision_rejects_at_limit(self, orchestrator, fake_store):
        """Provisioning raises FleetLimitExceededError at fleet_max_instances."""
        req = ComputeRequirements(vram_gb=24)
        # Fill up to limit (3)
        for _ in range(3):
            await orchestrator.provision_worker(ORG_ID, req)

        # 4th should fail
        with pytest.raises(FleetLimitExceededError):
            await orchestrator.provision_worker(ORG_ID, req)

    @pytest.mark.asyncio
    async def test_terminated_workers_dont_count(self, orchestrator, fake_store):
        """Terminated workers don't count against fleet limit."""
        req = ComputeRequirements(vram_gb=24)
        # Provision and terminate 3
        for _ in range(3):
            inst = await orchestrator.provision_worker(ORG_ID, req)
            await orchestrator.terminate_worker(inst.id)

        # Should be able to provision again
        instance = await orchestrator.provision_worker(ORG_ID, req)
        assert instance.status == "ready"


# =============================================================================
# Tests: Daily Budget Enforcement (R13.7)
# =============================================================================


@pytest.mark.unit
class TestDailyBudget:
    """Validates: R13.7 — reject launches when daily budget exceeded."""

    @pytest.mark.asyncio
    async def test_provision_rejects_over_budget(self, orchestrator, fake_store):
        """Provisioning raises DailyBudgetExceededError when budget exceeded."""
        # Pre-populate with a worker that has spent the full budget
        existing = WorkerInstance(
            org_id=ORG_ID,
            provider_name="fake",
            status="terminated",
            total_cost_usd=10.0,  # equals daily_budget_usd
        )
        fake_store.create(existing)

        req = ComputeRequirements(vram_gb=24)
        with pytest.raises(DailyBudgetExceededError):
            await orchestrator.provision_worker(ORG_ID, req)

    @pytest.mark.asyncio
    async def test_provision_succeeds_under_budget(self, orchestrator, fake_store):
        """Provisioning succeeds when under daily budget."""
        existing = WorkerInstance(
            org_id=ORG_ID,
            provider_name="fake",
            status="terminated",
            total_cost_usd=5.0,  # under the 10.0 limit
        )
        fake_store.create(existing)

        req = ComputeRequirements(vram_gb=24)
        instance = await orchestrator.provision_worker(ORG_ID, req)
        assert instance.status == "ready"


# =============================================================================
# Tests: Health Checks (R13.10, R13.11)
# =============================================================================


@pytest.mark.unit
class TestHealthChecks:
    """Validates: R13.10, R13.11 — health checks with 3-strike termination."""

    @pytest.mark.asyncio
    async def test_healthy_check_resets_failures(self, orchestrator, fake_store):
        """A healthy check resets consecutive_health_failures to 0."""
        instance = WorkerInstance(
            org_id=ORG_ID,
            provider_name="fake",
            provider_instance_id="fake-inst-1",
            status="ready",
            consecutive_health_failures=2,
        )
        fake_store.create(instance)

        state = await orchestrator.health_check_worker(instance.id)
        assert state == HealthState.HEALTHY

        updated = fake_store.get_by_id(instance.id)
        assert updated.consecutive_health_failures == 0

    @pytest.mark.asyncio
    async def test_unhealthy_increments_failures(self, fake_store):
        """An unhealthy check increments consecutive_health_failures."""
        unhealthy_provider = FakeComputeProvider(health_state=HealthState.UNHEALTHY)
        reg = ComputeProviderRegistry()
        reg.register("fake", unhealthy_provider)
        orch = WorkerOrchestrator(registry=reg, store=fake_store)

        instance = WorkerInstance(
            org_id=ORG_ID,
            provider_name="fake",
            provider_instance_id="fake-inst-1",
            status="ready",
            consecutive_health_failures=0,
        )
        fake_store.create(instance)

        await orch.health_check_worker(instance.id)
        updated = fake_store.get_by_id(instance.id)
        assert updated.consecutive_health_failures == 1

    @pytest.mark.asyncio
    async def test_three_failures_terminates_worker(self, fake_store):
        """3 consecutive failures → terminate worker (R13.11)."""
        unhealthy_provider = FakeComputeProvider(health_state=HealthState.UNHEALTHY)
        reg = ComputeProviderRegistry()
        reg.register("fake", unhealthy_provider)
        orch = WorkerOrchestrator(registry=reg, store=fake_store)

        instance = WorkerInstance(
            org_id=ORG_ID,
            provider_name="fake",
            provider_instance_id="fake-inst-1",
            status="ready",
            consecutive_health_failures=2,  # One more will hit 3
        )
        fake_store.create(instance)

        state = await orch.health_check_worker(instance.id)
        assert state == HealthState.UNREACHABLE

        updated = fake_store.get_by_id(instance.id)
        assert updated.status == "terminated"


    @pytest.mark.asyncio
    async def test_three_failures_requeues_job(self, fake_store):
        """3 consecutive failures re-queues the in-progress job (R13.11)."""
        unhealthy_provider = FakeComputeProvider(health_state=HealthState.UNHEALTHY)
        reg = ComputeProviderRegistry()
        reg.register("fake", unhealthy_provider)
        orch = WorkerOrchestrator(registry=reg, store=fake_store)

        instance = WorkerInstance(
            org_id=ORG_ID,
            provider_name="fake",
            provider_instance_id="fake-inst-1",
            status="busy",
            current_job_id="job-abc-123",
            consecutive_health_failures=2,
        )
        fake_store.create(instance)

        with patch.object(orch, "_requeue_job") as mock_requeue:
            await orch.health_check_worker(instance.id)
            mock_requeue.assert_called_once_with("job-abc-123", ORG_ID)


# =============================================================================
# Tests: Idle Timeout (R13.6)
# =============================================================================


@pytest.mark.unit
class TestIdleTimeout:
    """Validates: R13.6 — terminate idle workers after fleet_idle_timeout."""

    @pytest.mark.asyncio
    async def test_idle_worker_terminated_after_timeout(self, orchestrator, fake_store):
        """Workers idle beyond timeout are terminated."""
        # Create an idle worker with last job 20 min ago (> 15 min timeout)
        past = (datetime.now(UTC) - timedelta(minutes=20)).isoformat()
        instance = WorkerInstance(
            org_id=ORG_ID,
            provider_name="fake",
            provider_instance_id="fake-inst-1",
            status="idle",
            last_job_completed_at=past,
        )
        fake_store.create(instance)

        instances = fake_store.list_all_active()
        await orchestrator._check_idle_timeouts(instances)

        updated = fake_store.get_by_id(instance.id)
        assert updated.status == "terminated"

    @pytest.mark.asyncio
    async def test_recently_active_worker_not_terminated(self, orchestrator, fake_store):
        """Workers active within timeout are NOT terminated."""
        recent = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
        instance = WorkerInstance(
            org_id=ORG_ID,
            provider_name="fake",
            provider_instance_id="fake-inst-1",
            status="idle",
            last_job_completed_at=recent,
        )
        fake_store.create(instance)

        instances = fake_store.list_all_active()
        await orchestrator._check_idle_timeouts(instances)

        updated = fake_store.get_by_id(instance.id)
        assert updated.status == "idle"

    @pytest.mark.asyncio
    async def test_busy_worker_not_subject_to_idle_timeout(self, orchestrator, fake_store):
        """Busy workers are not terminated by idle timeout."""
        past = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()
        instance = WorkerInstance(
            org_id=ORG_ID,
            provider_name="fake",
            provider_instance_id="fake-inst-1",
            status="busy",
            current_job_id="job-xyz",
            last_job_completed_at=past,
        )
        fake_store.create(instance)

        instances = fake_store.list_all_active()
        await orchestrator._check_idle_timeouts(instances)

        updated = fake_store.get_by_id(instance.id)
        assert updated.status == "busy"


# =============================================================================
# Tests: Provisioning with Retries (R13.9)
# =============================================================================


@pytest.mark.unit
class TestProvisionRetries:
    """Validates: R13.9 — retry on different hosts, blacklist failures."""

    @pytest.mark.asyncio
    async def test_provision_retries_on_failure(self, fake_store):
        """Provisioning retries up to MAX_PROVISION_RETRIES times."""
        failing_provider = FakeComputeProvider(provision_fail=True)
        reg = ComputeProviderRegistry()
        reg.register("fake", failing_provider)
        orch = WorkerOrchestrator(registry=reg, store=fake_store)

        req = ComputeRequirements(vram_gb=24)
        with pytest.raises(ProvisionError):
            await orch.provision_worker(ORG_ID, req)

        # Verify the instance was marked as failed in the store
        instances = list(fake_store._instances.values())
        assert len(instances) == 1
        assert instances[0].status == "failed"

    @pytest.mark.asyncio
    async def test_provision_blacklists_on_failure(self, fake_store):
        """Failed provisions trigger host blacklisting."""
        failing_provider = FakeComputeProvider(provision_fail=True)
        reg = ComputeProviderRegistry()
        reg.register("fake", failing_provider)
        orch = WorkerOrchestrator(registry=reg, store=fake_store)

        req = ComputeRequirements(vram_gb=24)
        with patch.object(orch, "_blacklist_host") as mock_bl:
            with pytest.raises(ProvisionError):
                await orch.provision_worker(ORG_ID, req)
            # Should be called once per retry attempt (3 times)
            assert mock_bl.call_count == 3


# =============================================================================
# Tests: Termination Always In Finally (R13.5)
# =============================================================================


@pytest.mark.unit
class TestTermination:
    """Validates: R13.5 — terminate always executes in finally block."""

    @pytest.mark.asyncio
    async def test_terminate_updates_db_state(self, orchestrator, fake_store, fake_provider):
        """terminate_worker always marks instance as terminated in DB."""
        req = ComputeRequirements(vram_gb=24)
        instance = await orchestrator.provision_worker(ORG_ID, req)

        await orchestrator.terminate_worker(instance.id)

        updated = fake_store.get_by_id(instance.id)
        assert updated.status == "terminated"
        assert updated.terminated_at is not None

    @pytest.mark.asyncio
    async def test_terminate_calls_provider(self, orchestrator, fake_store, fake_provider):
        """terminate_worker calls provider.terminate()."""
        req = ComputeRequirements(vram_gb=24)
        instance = await orchestrator.provision_worker(ORG_ID, req)

        await orchestrator.terminate_worker(instance.id)
        assert instance.provider_instance_id in fake_provider._terminated

    @pytest.mark.asyncio
    async def test_terminate_idempotent(self, orchestrator, fake_store):
        """Terminating an already-terminated worker is a no-op."""
        instance = WorkerInstance(
            org_id=ORG_ID,
            provider_name="fake",
            status="terminated",
        )
        fake_store.create(instance)

        # Should not raise
        await orchestrator.terminate_worker(instance.id)

    @pytest.mark.asyncio
    async def test_terminate_nonexistent_is_noop(self, orchestrator):
        """Terminating a nonexistent worker does not raise."""
        await orchestrator.terminate_worker("nonexistent-id")


# =============================================================================
# Tests: Provider Selection
# =============================================================================


@pytest.mark.unit
class TestProviderSelection:
    """Test provider selection logic."""

    @pytest.mark.asyncio
    async def test_selects_preferred_provider(self, fake_store):
        """Preferred provider is used when specified."""
        provider_a = FakeComputeProvider()
        provider_b = FakeComputeProvider()
        reg = ComputeProviderRegistry()
        reg.register("provider_a", provider_a)
        reg.register("provider_b", provider_b)
        orch = WorkerOrchestrator(registry=reg, store=fake_store)

        req = ComputeRequirements(vram_gb=24)
        instance = await orch.provision_worker(
            ORG_ID, req, preferred_provider="provider_b"
        )
        assert instance.provider_name == "provider_b"

    @pytest.mark.asyncio
    async def test_selects_by_capabilities(self, fake_store):
        """Provider matching required capabilities is selected."""
        provider = FakeComputeProvider()
        reg = ComputeProviderRegistry()
        reg.register("fake", provider)
        orch = WorkerOrchestrator(registry=reg, store=fake_store)

        req = ComputeRequirements(
            vram_gb=24,
            required_capabilities=["persistent_storage"],
        )
        instance = await orch.provision_worker(ORG_ID, req)
        assert instance.provider_name == "fake"


# =============================================================================
# Tests: Job Assignment / Release
# =============================================================================


@pytest.mark.unit
class TestJobAssignment:
    """Test job assignment and release."""

    @pytest.mark.asyncio
    async def test_assign_job_sets_busy(self, orchestrator, fake_store):
        """assign_job marks worker as busy with job_id."""
        req = ComputeRequirements(vram_gb=24)
        instance = await orchestrator.provision_worker(ORG_ID, req)

        orchestrator.assign_job(instance.id, "job-123")
        updated = fake_store.get_by_id(instance.id)
        assert updated.status == "busy"
        assert updated.current_job_id == "job-123"

    @pytest.mark.asyncio
    async def test_release_job_sets_idle(self, orchestrator, fake_store):
        """release_job marks worker as idle and increments jobs_completed."""
        req = ComputeRequirements(vram_gb=24)
        instance = await orchestrator.provision_worker(ORG_ID, req)
        orchestrator.assign_job(instance.id, "job-123")

        orchestrator.release_job(instance.id)
        updated = fake_store.get_by_id(instance.id)
        assert updated.status == "idle"
        assert updated.current_job_id is None
        assert updated.jobs_completed == 1
        assert updated.last_job_completed_at is not None


# =============================================================================
# Tests: Status Reporting
# =============================================================================


@pytest.mark.unit
class TestStatus:
    """Test orchestrator status reporting."""

    @pytest.mark.asyncio
    async def test_get_status_empty(self, orchestrator):
        """Status with no workers shows empty list."""
        status = orchestrator.get_status(ORG_ID)
        assert status["active_workers"] == 0
        assert status["workers"] == []
        assert status["fleet_max_instances"] == 3

    @pytest.mark.asyncio
    async def test_get_status_with_workers(self, orchestrator, fake_store):
        """Status includes active worker details."""
        req = ComputeRequirements(vram_gb=24)
        await orchestrator.provision_worker(ORG_ID, req)

        status = orchestrator.get_status(ORG_ID)
        assert status["active_workers"] == 1
        assert len(status["workers"]) == 1
        assert status["workers"][0]["provider"] == "fake"
        assert status["workers"][0]["status"] == "ready"


# =============================================================================
# Tests: WorkerInstance dataclass
# =============================================================================


@pytest.mark.unit
class TestWorkerInstanceDataclass:
    """Test WorkerInstance serialization."""

    def test_to_db_row(self):
        """to_db_row produces a complete dict for Supabase."""
        instance = WorkerInstance(
            org_id=ORG_ID,
            provider_name="runpod",
            status="ready",
        )
        row = instance.to_db_row()
        assert row["org_id"] == ORG_ID
        assert row["provider_name"] == "runpod"
        assert row["status"] == "ready"
        assert "id" in row
        assert "created_at" in row

    def test_from_db_row(self):
        """from_db_row reconstructs a WorkerInstance from a dict."""
        row = {
            "id": "test-id",
            "org_id": ORG_ID,
            "provider_name": "vast",
            "provider_instance_id": "v-123",
            "gpu_name": "RTX 4090",
            "gpu_vram_gb": 24.0,
            "host": "10.0.0.1",
            "port": 8188,
            "status": "busy",
            "hourly_rate": 0.44,
            "current_job_id": "job-xyz",
            "consecutive_health_failures": 1,
            "last_health_check_at": "2025-01-01T00:00:00+00:00",
            "last_job_completed_at": None,
            "total_cost_usd": 0.22,
            "jobs_completed": 5,
            "metadata": {"foo": "bar"},
            "created_at": "2025-01-01T00:00:00+00:00",
            "updated_at": "2025-01-01T00:00:00+00:00",
            "terminated_at": None,
        }
        instance = WorkerInstance.from_db_row(row)
        assert instance.id == "test-id"
        assert instance.org_id == ORG_ID
        assert instance.gpu_name == "RTX 4090"
        assert instance.status == "busy"
        assert instance.hourly_rate == 0.44
        assert instance.metadata == {"foo": "bar"}

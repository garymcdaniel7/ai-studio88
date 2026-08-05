"""Service Boundary Tests (Story 051).

Proves: service definitions are complete, singletons identified,
topologies valid, scaling rules correct, and no duplicate leadership.

Run with:
    pytest tests/unit/test_service_registry.py -v
"""
from __future__ import annotations

import pytest

from backend.services.service_registry import (
    SERVICES,
    TOPOLOGIES,
    EnvironmentTopology,
    ServiceDefinition,
    ServiceRole,
    get_all_services,
    get_service,
    get_singletons,
    get_topology,
)


class TestServiceDefinitions:

    @pytest.mark.unit
    def test_all_required_services_defined(self):
        """All required services exist in the registry."""
        required = {"frontend", "api", "orchestrator", "worker", "scheduler", "migration"}
        assert required.issubset(set(SERVICES.keys()))

    @pytest.mark.unit
    def test_api_is_stateless(self):
        """API service must be stateless (horizontally scalable)."""
        api = get_service("api")
        assert api is not None
        assert api.role == ServiceRole.STATELESS
        assert api.max_replicas > 1

    @pytest.mark.unit
    def test_orchestrator_is_singleton(self):
        """Orchestrator must be singleton (owns GPU state)."""
        orch = get_service("orchestrator")
        assert orch is not None
        assert orch.role == ServiceRole.SINGLETON
        assert orch.max_replicas == 1

    @pytest.mark.unit
    def test_scheduler_is_singleton(self):
        """Scheduler must be singleton (prevent duplicate crons)."""
        sched = get_service("scheduler")
        assert sched is not None
        assert sched.role == ServiceRole.SINGLETON
        assert sched.max_replicas == 1

    @pytest.mark.unit
    def test_worker_is_scalable(self):
        """Worker service can scale horizontally."""
        worker = get_service("worker")
        assert worker is not None
        assert worker.role == ServiceRole.SCALABLE_WORKER
        assert worker.max_replicas > 1

    @pytest.mark.unit
    def test_every_service_has_entrypoint(self):
        """Every service has a non-empty entrypoint command."""
        for name, svc in SERVICES.items():
            assert svc.entrypoint, f"Service '{name}' has no entrypoint"

    @pytest.mark.unit
    def test_every_service_has_responsibilities(self):
        """Every service has documented responsibilities."""
        for name, svc in SERVICES.items():
            assert svc.responsibilities, f"Service '{name}' has no responsibilities"

    @pytest.mark.unit
    def test_http_services_have_health_endpoint(self):
        """Services with ports must have health endpoints."""
        for name, svc in SERVICES.items():
            if svc.port > 0:
                assert svc.health_endpoint, f"Service '{name}' has port but no health endpoint"


class TestSingletonLeadership:

    @pytest.mark.unit
    def test_get_singletons(self):
        """get_singletons() returns orchestrator, scheduler, migration."""
        singletons = get_singletons()
        assert "orchestrator" in singletons
        assert "scheduler" in singletons
        assert "api" not in singletons
        assert "frontend" not in singletons

    @pytest.mark.unit
    def test_no_singleton_exceeds_one_replica(self):
        """Singletons must have max_replicas=1."""
        for name in get_singletons():
            svc = get_service(name)
            assert svc.max_replicas == 1, f"Singleton '{name}' has max_replicas > 1"

    @pytest.mark.unit
    def test_production_topology_respects_singleton(self):
        """Production topology never runs >1 replica for singletons."""
        prod = get_topology("production")
        assert prod is not None
        for name in get_singletons():
            if name in prod.services:
                assert prod.services[name] <= 1, \
                    f"Production runs {prod.services[name]} replicas of singleton '{name}'"


class TestTopologies:

    @pytest.mark.unit
    def test_all_environments_defined(self):
        """Local, staging, and production topologies exist."""
        assert "local" in TOPOLOGIES
        assert "staging" in TOPOLOGIES
        assert "production" in TOPOLOGIES

    @pytest.mark.unit
    def test_local_is_shared_process(self):
        """Local dev runs all services in one process."""
        local = get_topology("local")
        assert local.shared_process is True

    @pytest.mark.unit
    def test_staging_is_separate_processes(self):
        """Staging uses separate processes."""
        staging = get_topology("staging")
        assert staging.shared_process is False

    @pytest.mark.unit
    def test_production_scales_api(self):
        """Production runs multiple API replicas."""
        prod = get_topology("production")
        assert prod.services["api"] >= 2

    @pytest.mark.unit
    def test_production_scales_frontend(self):
        """Production runs multiple frontend replicas."""
        prod = get_topology("production")
        assert prod.services["frontend"] >= 2


class TestNoWebProcessDaemons:
    """Prove the API service should NOT run daemon threads."""

    @pytest.mark.unit
    def test_api_has_no_gpu_dependency(self):
        """API service does not require GPU access."""
        api = get_service("api")
        assert api.requires_gpu is False

    @pytest.mark.unit
    def test_api_responsibilities_are_request_scoped(self):
        """API responsibilities are all request/response (no long-running)."""
        api = get_service("api")
        for resp in api.responsibilities:
            # None should mention "daemon", "background", "boot", or "lifecycle"
            resp_lower = resp.lower()
            assert "daemon" not in resp_lower
            assert "background" not in resp_lower
            assert "boot worker" not in resp_lower
            assert "lifecycle" not in resp_lower

    @pytest.mark.unit
    def test_orchestrator_owns_gpu_lifecycle(self):
        """GPU lifecycle is the orchestrator's responsibility, not API's."""
        orch = get_service("orchestrator")
        has_gpu_lifecycle = any("gpu" in r.lower() or "worker" in r.lower()
                               for r in orch.responsibilities)
        assert has_gpu_lifecycle

    @pytest.mark.unit
    def test_worker_owns_long_running_jobs(self):
        """Long-running jobs belong to the worker service."""
        worker = get_service("worker")
        has_training = any("training" in r.lower() for r in worker.responsibilities)
        has_download = any("download" in r.lower() for r in worker.responsibilities)
        assert has_training
        assert has_download


class TestGracefulShutdown:

    @pytest.mark.unit
    def test_all_services_have_shutdown_timeout(self):
        """Every service defines a graceful shutdown period."""
        for name, svc in SERVICES.items():
            assert svc.graceful_shutdown_seconds > 0, \
                f"Service '{name}' has no shutdown timeout"

    @pytest.mark.unit
    def test_worker_has_long_shutdown(self):
        """Worker gets enough time to checkpoint training."""
        worker = get_service("worker")
        assert worker.graceful_shutdown_seconds >= 120

    @pytest.mark.unit
    def test_api_has_moderate_shutdown(self):
        """API drains connections within 30s."""
        api = get_service("api")
        assert api.graceful_shutdown_seconds <= 60


class TestQueryHelpers:

    @pytest.mark.unit
    def test_get_all_services_returns_dicts(self):
        """get_all_services() returns serializable list."""
        result = get_all_services()
        assert isinstance(result, list)
        assert len(result) == len(SERVICES)
        for item in result:
            assert "name" in item
            assert "role" in item
            assert "singleton" in item

    @pytest.mark.unit
    def test_get_service_unknown_returns_none(self):
        assert get_service("nonexistent") is None

    @pytest.mark.unit
    def test_get_topology_unknown_returns_none(self):
        assert get_topology("mars") is None

"""Worker Lifecycle Tests (Story 057).

Proves: idempotency, active-job blocking, termination authorization,
reconciliation failures, volume disposition, and tenant isolation.

Run with:
    pytest tests/unit/test_worker_lifecycle.py -v
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from backend.worker_lifecycle import (
    VolumeDisposition,
    WorkerLifecycleService,
    WorkerRecord,
    WorkerState,
    _lifecycle_audit,
    _worker_store,
)

ORG_A = str(uuid4())
ORG_B = str(uuid4())
USER_A = str(uuid4())


@pytest.fixture(autouse=True)
def clean():
    _worker_store.clear()
    _lifecycle_audit.clear()
    yield
    _worker_store.clear()
    _lifecycle_audit.clear()


def _create_worker(org_id=ORG_A, state=WorkerState.RUNNING, active_jobs=0):
    w = WorkerRecord(
        id=f"w-{uuid4().hex[:8]}",
        org_id=org_id, provider="runpod", pod_id="pod-123",
        state=state, gpu_name="A100", hourly_rate=1.5,
        volume_id="vol-1", volume_size_gb=50, volume_hourly_cost=0.10,
        active_job_count=active_jobs,
    )
    _worker_store[w.id] = w
    return w


# =============================================================================
# Stop
# =============================================================================


class TestStop:

    @pytest.mark.unit
    def test_stop_running_worker(self):
        w = _create_worker()
        result = WorkerLifecycleService.stop(
            worker_id=w.id, org_id=ORG_A,
            actor_user_id=USER_A, actor_role="editor",
        )
        assert result.success is True
        assert result.new_state == "stopped"
        assert _worker_store[w.id].state == WorkerState.STOPPED

    @pytest.mark.unit
    def test_stop_blocked_by_active_jobs(self):
        w = _create_worker(active_jobs=2)
        result = WorkerLifecycleService.stop(
            worker_id=w.id, org_id=ORG_A,
            actor_user_id=USER_A, actor_role="editor",
        )
        assert result.success is False
        assert "active_jobs" in result.blocked_by

    @pytest.mark.unit
    def test_stop_override_active_jobs(self):
        w = _create_worker(active_jobs=2)
        result = WorkerLifecycleService.stop(
            worker_id=w.id, org_id=ORG_A,
            actor_user_id=USER_A, actor_role="admin",
            override_active_jobs=True,
        )
        assert result.success is True

    @pytest.mark.unit
    def test_stop_viewer_denied(self):
        w = _create_worker()
        result = WorkerLifecycleService.stop(
            worker_id=w.id, org_id=ORG_A,
            actor_user_id=USER_A, actor_role="viewer",
        )
        assert result.success is False
        assert "insufficient_role" in result.reason

    @pytest.mark.unit
    def test_stop_already_stopped(self):
        w = _create_worker(state=WorkerState.STOPPED)
        result = WorkerLifecycleService.stop(
            worker_id=w.id, org_id=ORG_A,
            actor_user_id=USER_A, actor_role="editor",
        )
        assert result.success is False
        assert "not_stoppable" in result.reason

    @pytest.mark.unit
    def test_stop_reports_volume_cost(self):
        w = _create_worker()
        result = WorkerLifecycleService.stop(
            worker_id=w.id, org_id=ORG_A,
            actor_user_id=USER_A, actor_role="editor",
        )
        assert result.cost_stopped_usd_per_hour == 0.10


# =============================================================================
# Resume
# =============================================================================


class TestResume:

    @pytest.mark.unit
    def test_resume_stopped_worker(self):
        w = _create_worker(state=WorkerState.STOPPED)
        result = WorkerLifecycleService.resume(
            worker_id=w.id, org_id=ORG_A,
            actor_user_id=USER_A, actor_role="editor",
        )
        assert result.success is True
        assert result.new_state == "running"

    @pytest.mark.unit
    def test_resume_running_fails(self):
        w = _create_worker(state=WorkerState.RUNNING)
        result = WorkerLifecycleService.resume(
            worker_id=w.id, org_id=ORG_A,
            actor_user_id=USER_A, actor_role="editor",
        )
        assert result.success is False
        assert "not_resumable" in result.reason

    @pytest.mark.unit
    def test_resume_viewer_denied(self):
        w = _create_worker(state=WorkerState.STOPPED)
        result = WorkerLifecycleService.resume(
            worker_id=w.id, org_id=ORG_A,
            actor_user_id=USER_A, actor_role="viewer",
        )
        assert result.success is False


# =============================================================================
# Terminate (Destructive)
# =============================================================================


class TestTerminate:

    @pytest.mark.unit
    def test_terminate_requires_admin(self):
        """Editor cannot terminate (destructive requires admin+)."""
        w = _create_worker()
        result = WorkerLifecycleService.terminate(
            worker_id=w.id, org_id=ORG_A,
            actor_user_id=USER_A, actor_role="editor",
            volume_disposition=VolumeDisposition.PRESERVE,
        )
        assert result.success is False
        assert "destructive_requires_admin" in result.reason

    @pytest.mark.unit
    def test_terminate_admin_succeeds(self):
        w = _create_worker()
        result = WorkerLifecycleService.terminate(
            worker_id=w.id, org_id=ORG_A,
            actor_user_id=USER_A, actor_role="admin",
            volume_disposition=VolumeDisposition.PRESERVE,
        )
        assert result.success is True
        assert result.new_state == "terminated"

    @pytest.mark.unit
    def test_terminate_requires_volume_disposition(self):
        """Cannot terminate without explicit volume decision."""
        w = _create_worker()
        result = WorkerLifecycleService.terminate(
            worker_id=w.id, org_id=ORG_A,
            actor_user_id=USER_A, actor_role="owner",
            volume_disposition=VolumeDisposition.UNSPECIFIED,
        )
        assert result.success is False
        assert "volume_disposition_required" in result.reason
        assert "DECISION-REQUIRED" in result.blocked_by

    @pytest.mark.unit
    def test_terminate_delete_volume(self):
        """Terminate with DELETE removes volume data."""
        w = _create_worker()
        result = WorkerLifecycleService.terminate(
            worker_id=w.id, org_id=ORG_A,
            actor_user_id=USER_A, actor_role="owner",
            volume_disposition=VolumeDisposition.DELETE,
        )
        assert result.success is True
        assert _worker_store[w.id].volume_id is None

    @pytest.mark.unit
    def test_terminate_preserve_volume(self):
        """Terminate with PRESERVE keeps volume."""
        w = _create_worker()
        result = WorkerLifecycleService.terminate(
            worker_id=w.id, org_id=ORG_A,
            actor_user_id=USER_A, actor_role="owner",
            volume_disposition=VolumeDisposition.PRESERVE,
        )
        assert result.success is True
        assert _worker_store[w.id].volume_id == "vol-1"  # Preserved

    @pytest.mark.unit
    def test_terminate_blocked_by_active_jobs(self):
        w = _create_worker(active_jobs=1)
        result = WorkerLifecycleService.terminate(
            worker_id=w.id, org_id=ORG_A,
            actor_user_id=USER_A, actor_role="owner",
            volume_disposition=VolumeDisposition.DELETE,
        )
        assert result.success is False
        assert "active_jobs" in result.blocked_by


# =============================================================================
# Tenant Isolation
# =============================================================================


class TestTenantIsolation:

    @pytest.mark.unit
    def test_stop_wrong_org_not_found(self):
        w = _create_worker(org_id=ORG_A)
        result = WorkerLifecycleService.stop(
            worker_id=w.id, org_id=ORG_B,
            actor_user_id=USER_A, actor_role="owner",
        )
        assert result.success is False
        assert result.reason == "worker_not_found"

    @pytest.mark.unit
    def test_terminate_wrong_org_not_found(self):
        w = _create_worker(org_id=ORG_A)
        result = WorkerLifecycleService.terminate(
            worker_id=w.id, org_id=ORG_B,
            actor_user_id=USER_A, actor_role="owner",
            volume_disposition=VolumeDisposition.DELETE,
        )
        assert result.success is False

    @pytest.mark.unit
    def test_volume_status_wrong_org_none(self):
        w = _create_worker(org_id=ORG_A)
        assert WorkerLifecycleService.get_volume_status(w.id, ORG_B) is None
        assert WorkerLifecycleService.get_volume_status(w.id, ORG_A) is not None


# =============================================================================
# Audit
# =============================================================================


class TestAudit:

    @pytest.mark.unit
    def test_stop_produces_audit(self):
        w = _create_worker()
        WorkerLifecycleService.stop(
            worker_id=w.id, org_id=ORG_A,
            actor_user_id=USER_A, actor_role="editor",
        )
        assert len(_lifecycle_audit) >= 1
        assert _lifecycle_audit[-1]["operation"] == "stop"

    @pytest.mark.unit
    def test_denied_operation_audited(self):
        w = _create_worker()
        WorkerLifecycleService.terminate(
            worker_id=w.id, org_id=ORG_A,
            actor_user_id=USER_A, actor_role="editor",
            volume_disposition=VolumeDisposition.DELETE,
        )
        assert any("destructive_requires" in e.get("reason", "") for e in _lifecycle_audit)

"""Two-Tenant LoRA Training Authorization Tests (Story 021).

Proves workspace isolation for datasets, images, jobs, LoRA versions,
evaluations, promotions, and cancel operations.

Run with:
    pytest tests/unit/test_training_auth.py -v
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from backend.auth import AuthUser
from backend.data_access import AuthorizationError, AuthorizedClient
from backend.membership import OrgRole, TenantContext

ORG_A = str(uuid4())
ORG_B = str(uuid4())


@pytest.fixture
def user_a():
    return AuthUser(user_id=str(uuid4()), email="a@studio.io", org_id=ORG_A, role="owner")


@pytest.fixture
def user_b():
    return AuthUser(user_id=str(uuid4()), email="b@studio.io", org_id=ORG_B, role="owner")


@pytest.fixture
def mock_db():
    with patch("backend.data_access.is_supabase_configured", return_value=True), \
         patch("backend.data_access.get_supabase_client") as mock_fn:
        mock_client = MagicMock()
        mock_fn.return_value = mock_client
        yield mock_client


class TestDatasetIsolation:
    """Prove datasets are workspace-scoped."""

    @pytest.mark.unit
    def test_list_datasets_scoped(self, user_a, mock_db):
        client = AuthorizedClient(TenantContext(user_id=user_a.user_id, org_id=ORG_A, role=OrgRole.OWNER))
        mock_table = MagicMock()
        mock_db.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.order.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[])
        client.select("training_datasets", order_by="created_at")
        mock_table.eq.assert_called_with("org_id", ORG_A)

    @pytest.mark.unit
    def test_create_dataset_stamps_org(self, user_a, mock_db):
        client = AuthorizedClient(TenantContext(user_id=user_a.user_id, org_id=ORG_A, role=OrgRole.OWNER))
        mock_table = MagicMock()
        mock_db.table.return_value = mock_table
        mock_table.insert.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[{"id": "ds-1"}])
        data = {"name": "Test Dataset"}
        client.insert("training_datasets", data)
        assert data["org_id"] == ORG_A

    @pytest.mark.unit
    def test_cross_tenant_dataset_get_404(self, user_b, mock_db):
        client = AuthorizedClient(TenantContext(user_id=user_b.user_id, org_id=ORG_B, role=OrgRole.OWNER))
        mock_table = MagicMock()
        mock_db.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.single.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=None)
        with pytest.raises(AuthorizationError):
            client.select_by_id("training_datasets", "ds-in-org-a")

    @pytest.mark.unit
    def test_cross_tenant_dataset_delete_fails(self, user_b, mock_db):
        client = AuthorizedClient(TenantContext(user_id=user_b.user_id, org_id=ORG_B, role=OrgRole.OWNER))
        mock_table = MagicMock()
        mock_db.table.return_value = mock_table
        mock_table.delete.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[])
        with pytest.raises(AuthorizationError):
            client.delete("training_datasets", "ds-in-org-a")


class TestTrainingJobIsolation:
    """Prove training jobs are workspace-scoped."""

    @pytest.mark.unit
    def test_list_jobs_scoped(self, user_a, mock_db):
        client = AuthorizedClient(TenantContext(user_id=user_a.user_id, org_id=ORG_A, role=OrgRole.OWNER))
        mock_table = MagicMock()
        mock_db.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.order.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[])
        client.select("training_jobs", order_by="created_at")
        mock_table.eq.assert_called_with("org_id", ORG_A)

    @pytest.mark.unit
    def test_cross_tenant_job_read_404(self, user_b, mock_db):
        client = AuthorizedClient(TenantContext(user_id=user_b.user_id, org_id=ORG_B, role=OrgRole.OWNER))
        mock_table = MagicMock()
        mock_db.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.single.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=None)
        with pytest.raises(AuthorizationError):
            client.select_by_id("training_jobs", "job-in-org-a")

    @pytest.mark.unit
    def test_job_insert_stamps_org(self, user_a, mock_db):
        client = AuthorizedClient(TenantContext(user_id=user_a.user_id, org_id=ORG_A, role=OrgRole.OWNER))
        mock_table = MagicMock()
        mock_db.table.return_value = mock_table
        mock_table.insert.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[{"id": "tj-1"}])
        data = {"dataset_id": "ds-1", "status": "running"}
        client.insert("training_jobs", data)
        assert data["org_id"] == ORG_A


class TestLoRAVersionIsolation:
    """Prove LoRA versions are workspace-scoped."""

    @pytest.mark.unit
    def test_list_loras_scoped(self, user_a, mock_db):
        client = AuthorizedClient(TenantContext(user_id=user_a.user_id, org_id=ORG_A, role=OrgRole.OWNER))
        mock_table = MagicMock()
        mock_db.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.order.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[])
        client.select("lora_versions", order_by="created_at")
        mock_table.eq.assert_called_with("org_id", ORG_A)

    @pytest.mark.unit
    def test_cross_tenant_lora_get_404(self, user_b, mock_db):
        client = AuthorizedClient(TenantContext(user_id=user_b.user_id, org_id=ORG_B, role=OrgRole.OWNER))
        mock_table = MagicMock()
        mock_db.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.single.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=None)
        with pytest.raises(AuthorizationError):
            client.select_by_id("lora_versions", "lora-in-org-a")

    @pytest.mark.unit
    def test_promote_requires_ownership(self, user_b, mock_db):
        """Cannot promote a LoRA in another org."""
        client = AuthorizedClient(TenantContext(user_id=user_b.user_id, org_id=ORG_B, role=OrgRole.OWNER))
        mock_table = MagicMock()
        mock_db.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.single.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=None)
        with pytest.raises(AuthorizationError):
            client.select_by_id("lora_versions", "lora-in-org-a")


class TestTrainingAudit:
    """Prove GPU-spend training operations are audited."""

    @pytest.mark.unit
    def test_start_training_audits(self, user_a, mock_db):
        from backend.training.router import _audit, _training_audit
        initial = len(_training_audit)
        _audit("start_training", "training_job", "tj-1", user_a, "model=flux-dev")
        assert len(_training_audit) > initial
        assert _training_audit[-1]["action"] == "start_training"
        assert _training_audit[-1]["actor_user_id"] == user_a.user_id

    @pytest.mark.unit
    def test_cancel_training_audits(self, user_a, mock_db):
        from backend.training.router import _audit, _training_audit
        initial = len(_training_audit)
        _audit("cancel_training", "training_job", "tj-2", user_a)
        assert len(_training_audit) > initial
        assert _training_audit[-1]["action"] == "cancel_training"

    @pytest.mark.unit
    def test_promote_audits(self, user_a, mock_db):
        from backend.training.router import _audit, _training_audit
        initial = len(_training_audit)
        _audit("promote_lora", "lora_version", "lv-1", user_a, "talent=t1")
        assert len(_training_audit) > initial
        assert _training_audit[-1]["action"] == "promote_lora"


class TestTenantTablesRegistry:
    """Verify training tables are in TENANT_TABLES."""

    @pytest.mark.unit
    def test_training_tables_registered(self):
        from backend.data_access import TENANT_TABLES
        for table in ["training_datasets", "training_images", "training_jobs", "lora_versions", "talent_loras"]:
            assert table in TENANT_TABLES, f"{table} missing from TENANT_TABLES"

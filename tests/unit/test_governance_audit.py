"""Unit tests for Governance Audit Service — Task 14.3.

Verifies:
- GovernanceAuditService.persist_evaluation() correctly transforms and stores records
- GovernanceAuditService.batch_persist() flushes in-memory buffer
- GovernanceAuditService.query_evaluations() with filters and pagination
- GET /aios/v1/governance/audit returns paginated evaluation records
- Integration with GovernanceBoundary's in-memory audit trail

Validates: Requirements R59.6, R59.7
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.aios.governance_audit import (
    EvaluationFilters,
    EvaluationPage,
    GovernanceAuditService,
)
from backend.aios.governance_boundary import (
    Decision,
    GovernanceBoundary,
    GovernanceRequest,
    RiskClassification,
    TenantContext,
    clear_evaluation_audit,
    get_evaluation_audit,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def clean_audit():
    """Clear audit trail before/after each test."""
    clear_evaluation_audit()
    yield
    clear_evaluation_audit()


@pytest.fixture
def boundary() -> GovernanceBoundary:
    """Default governance boundary instance."""
    return GovernanceBoundary()


@pytest.fixture
def audit_service() -> GovernanceAuditService:
    """GovernanceAuditService instance."""
    return GovernanceAuditService()


@pytest.fixture
def sample_evaluation() -> dict:
    """A sample evaluation record as produced by _record_evaluation()."""
    return {
        "evaluation_id": "eval-abc123def456",
        "correlation_id": "gov-1234567890abcdef",
        "timestamp": "2026-08-12T10:00:00+00:00",
        "action_type": "generate_image",
        "identity": "usr-test-001",
        "trust_domain": "CUSTOMER_USER",
        "org_id": "org-test-1234",
        "role": "editor",
        "risk_classification": "medium_impact",
        "decision": "allow",
        "denial_reason": None,
        "required_approval_type": None,
        "is_degraded": False,
        "failed_checks": [],
        "estimated_cost_usd": 1.50,
    }


@pytest.fixture
def sample_denial_evaluation() -> dict:
    """A sample denial evaluation record."""
    return {
        "evaluation_id": "eval-denial-789012",
        "correlation_id": "gov-feedbeef01234567",
        "timestamp": "2026-08-12T10:05:00+00:00",
        "action_type": "delete_model",
        "identity": "usr-attacker-999",
        "trust_domain": "CUSTOMER_USER",
        "org_id": "org-test-1234",
        "role": "viewer",
        "risk_classification": "destructive",
        "decision": "deny",
        "denial_reason": "Actor does not own the target resource",
        "required_approval_type": None,
        "is_degraded": False,
        "failed_checks": ["resource_ownership"],
        "estimated_cost_usd": 0.0,
    }


# =============================================================================
# Test: _evaluation_to_row() transformation
# =============================================================================


@pytest.mark.unit
class TestEvaluationToRow:
    """Verify the in-memory evaluation dict is correctly mapped to a DB row."""

    def test_maps_all_fields(self, audit_service: GovernanceAuditService, sample_evaluation: dict):
        row = audit_service._evaluation_to_row(sample_evaluation)

        assert row["evaluation_id"] == "eval-abc123def456"
        assert row["correlation_id"] == "gov-1234567890abcdef"
        assert row["action_type"] == "generate_image"
        assert row["identity"] == "usr-test-001"
        assert row["trust_domain"] == "CUSTOMER_USER"
        assert row["org_id"] == "org-test-1234"
        assert row["role"] == "editor"
        assert row["risk_classification"] == "medium_impact"
        assert row["decision"] == "allow"
        assert row["denial_reason"] is None
        assert row["required_approval_type"] is None
        assert row["is_degraded"] is False
        assert row["failed_checks"] == []
        assert row["estimated_cost_usd"] == 1.50
        assert row["created_at"] == "2026-08-12T10:00:00+00:00"

    def test_handles_denial_with_reason(
        self, audit_service: GovernanceAuditService, sample_denial_evaluation: dict
    ):
        row = audit_service._evaluation_to_row(sample_denial_evaluation)

        assert row["decision"] == "deny"
        assert row["denial_reason"] == "Actor does not own the target resource"
        assert row["failed_checks"] == ["resource_ownership"]
        assert row["risk_classification"] == "destructive"

    def test_handles_missing_optional_fields(self, audit_service: GovernanceAuditService):
        minimal = {
            "evaluation_id": "eval-minimal",
            "action_type": "list_assets",
            "decision": "allow",
            "risk_classification": "read_only",
        }
        row = audit_service._evaluation_to_row(minimal)

        assert row["evaluation_id"] == "eval-minimal"
        assert row["action_type"] == "list_assets"
        assert row["decision"] == "allow"
        assert row["identity"] is None
        assert row["trust_domain"] is None
        assert row["org_id"] is None
        assert row["role"] is None
        assert row["is_degraded"] is False
        assert row["failed_checks"] == []

    def test_missing_timestamp_excluded_from_row(self, audit_service: GovernanceAuditService):
        evaluation = {
            "evaluation_id": "eval-no-ts",
            "action_type": "test",
            "decision": "allow",
            "risk_classification": "read_only",
        }
        row = audit_service._evaluation_to_row(evaluation)
        assert "created_at" not in row


# =============================================================================
# Test: persist_evaluation()
# =============================================================================


@pytest.mark.unit
class TestPersistEvaluation:
    """Verify individual evaluation persistence to Supabase."""

    @pytest.mark.asyncio
    async def test_persist_calls_supabase_insert(
        self, audit_service: GovernanceAuditService, sample_evaluation: dict
    ):
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_insert = MagicMock()
        mock_execute = MagicMock()

        mock_client.table.return_value = mock_table
        mock_table.insert.return_value = mock_insert
        mock_insert.execute.return_value = MagicMock(data=[sample_evaluation])

        audit_service._client = mock_client

        result = await audit_service.persist_evaluation(sample_evaluation)

        mock_client.table.assert_called_once_with("governance_evaluations")
        mock_table.insert.assert_called_once()
        assert result == sample_evaluation

    @pytest.mark.asyncio
    async def test_persist_returns_none_on_failure(
        self, audit_service: GovernanceAuditService, sample_evaluation: dict
    ):
        mock_client = MagicMock()
        mock_client.table.side_effect = Exception("Connection refused")
        audit_service._client = mock_client

        result = await audit_service.persist_evaluation(sample_evaluation)
        assert result is None

    @pytest.mark.asyncio
    async def test_persist_returns_none_when_no_data(
        self, audit_service: GovernanceAuditService, sample_evaluation: dict
    ):
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_insert = MagicMock()
        mock_execute = MagicMock()

        mock_client.table.return_value = mock_table
        mock_table.insert.return_value = mock_insert
        mock_insert.execute.return_value = MagicMock(data=None)

        audit_service._client = mock_client

        result = await audit_service.persist_evaluation(sample_evaluation)
        assert result is None


# =============================================================================
# Test: batch_persist()
# =============================================================================


@pytest.mark.unit
class TestBatchPersist:
    """Verify batch persistence from in-memory buffer."""

    @pytest.mark.asyncio
    async def test_batch_persist_with_explicit_list(
        self, audit_service: GovernanceAuditService, sample_evaluation: dict
    ):
        evaluations = [sample_evaluation, sample_evaluation]

        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_insert = MagicMock()

        mock_client.table.return_value = mock_table
        mock_table.insert.return_value = mock_insert
        mock_insert.execute.return_value = MagicMock(data=evaluations)

        audit_service._client = mock_client

        count = await audit_service.batch_persist(evaluations)
        assert count == 2

    @pytest.mark.asyncio
    async def test_batch_persist_empty_list_returns_zero(
        self, audit_service: GovernanceAuditService
    ):
        count = await audit_service.batch_persist([])
        assert count == 0

    @pytest.mark.asyncio
    async def test_batch_persist_none_reads_from_in_memory(
        self, audit_service: GovernanceAuditService, boundary: GovernanceBoundary
    ):
        """When evaluations=None, reads and clears the in-memory buffer."""
        # Generate some evaluations via the boundary
        request = GovernanceRequest(
            action_type="generate_image",
            identity="usr-1",
            trust_domain="CUSTOMER_USER",
            tenant_context=TenantContext(org_id="org-1", role="editor"),
            risk_classification=RiskClassification.MEDIUM_IMPACT,
            estimated_cost_usd=2.0,
            budget_available=100.0,
            provider_capability=True,
            compute_availability_state="enabled",
            feature_rollout_status=True,
        )
        boundary.evaluate(request)
        boundary.evaluate(request)

        # Confirm buffer has entries
        assert len(get_evaluation_audit()) == 2

        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_insert = MagicMock()
        mock_client.table.return_value = mock_table
        mock_table.insert.return_value = mock_insert
        mock_insert.execute.return_value = MagicMock(data=[{}, {}])

        audit_service._client = mock_client

        count = await audit_service.batch_persist(None)
        assert count == 2

        # Buffer should be cleared
        assert len(get_evaluation_audit()) == 0

    @pytest.mark.asyncio
    async def test_batch_persist_falls_back_to_individual_on_error(
        self, audit_service: GovernanceAuditService, sample_evaluation: dict
    ):
        """If batch insert fails, falls back to individual inserts."""
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_insert = MagicMock()

        # First call (batch) fails
        mock_client.table.return_value = mock_table
        mock_table.insert.side_effect = [
            Exception("Batch failed"),  # batch attempt
            mock_insert,  # individual fallback 1
            mock_insert,  # individual fallback 2
        ]
        mock_insert.execute.return_value = MagicMock(data=[sample_evaluation])

        audit_service._client = mock_client

        count = await audit_service.batch_persist([sample_evaluation, sample_evaluation])
        assert count == 2


# =============================================================================
# Test: query_evaluations()
# =============================================================================


@pytest.mark.unit
class TestQueryEvaluations:
    """Verify paginated evaluation queries."""

    @pytest.mark.asyncio
    async def test_query_returns_evaluation_page(self, audit_service: GovernanceAuditService):
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_select = MagicMock()
        mock_eq = MagicMock()
        mock_order = MagicMock()
        mock_limit = MagicMock()
        mock_offset = MagicMock()

        mock_client.table.return_value = mock_table
        mock_table.select.return_value = mock_select
        mock_select.eq.return_value = mock_eq
        mock_eq.order.return_value = mock_order
        mock_order.limit.return_value = mock_limit
        mock_limit.offset.return_value = mock_offset
        mock_offset.execute.return_value = MagicMock(
            data=[{"evaluation_id": "eval-1", "decision": "allow"}],
            count=1,
        )

        audit_service._client = mock_client

        page = await audit_service.query_evaluations(org_id="org-test", limit=20, offset=0)

        assert isinstance(page, EvaluationPage)
        assert len(page.items) == 1
        assert page.total == 1
        assert page.limit == 20
        assert page.offset == 0

    @pytest.mark.asyncio
    async def test_query_clamps_limit(self, audit_service: GovernanceAuditService):
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_select = MagicMock()
        mock_eq = MagicMock()
        mock_order = MagicMock()
        mock_limit = MagicMock()
        mock_offset = MagicMock()

        mock_client.table.return_value = mock_table
        mock_table.select.return_value = mock_select
        mock_select.eq.return_value = mock_eq
        mock_eq.order.return_value = mock_order
        mock_order.limit.return_value = mock_limit
        mock_limit.offset.return_value = mock_offset
        mock_offset.execute.return_value = MagicMock(data=[], count=0)

        audit_service._client = mock_client

        # Limit over 100 should be clamped
        page = await audit_service.query_evaluations(org_id="org-test", limit=500)
        assert page.limit == 100

        # Limit below 1 should be clamped
        page = await audit_service.query_evaluations(org_id="org-test", limit=-5)
        assert page.limit == 1

    @pytest.mark.asyncio
    async def test_query_applies_filters(self, audit_service: GovernanceAuditService):
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_select = MagicMock()

        # Build a chain where each .eq() returns the same mock
        mock_chain = MagicMock()
        mock_chain.eq.return_value = mock_chain
        mock_chain.gte.return_value = mock_chain
        mock_chain.lte.return_value = mock_chain
        mock_chain.order.return_value = mock_chain
        mock_chain.limit.return_value = mock_chain
        mock_chain.offset.return_value = mock_chain
        mock_chain.execute.return_value = MagicMock(data=[], count=0)

        mock_client.table.return_value = mock_table
        mock_table.select.return_value = mock_select
        mock_select.eq.return_value = mock_chain

        audit_service._client = mock_client

        filters = EvaluationFilters(
            action_type="generate_image",
            decision="deny",
        )
        page = await audit_service.query_evaluations(
            org_id="org-test", filters=filters
        )

        assert isinstance(page, EvaluationPage)

    @pytest.mark.asyncio
    async def test_query_returns_empty_on_error(self, audit_service: GovernanceAuditService):
        mock_client = MagicMock()
        mock_client.table.side_effect = Exception("DB down")
        audit_service._client = mock_client

        page = await audit_service.query_evaluations(org_id="org-test")

        assert page.items == []
        assert page.total == 0


# =============================================================================
# Test: Integration with GovernanceBoundary in-memory audit
# =============================================================================


@pytest.mark.unit
class TestGovernanceBoundaryIntegration:
    """Verify audit service works with the boundary's in-memory trail."""

    def test_boundary_populates_in_memory_audit(self, boundary: GovernanceBoundary):
        """Every evaluate() call adds to the in-memory audit trail."""
        request = GovernanceRequest(
            action_type="test_action",
            identity="usr-int-1",
            trust_domain="CUSTOMER_USER",
            tenant_context=TenantContext(org_id="org-int-1", role="editor"),
            risk_classification=RiskClassification.MEDIUM_IMPACT,
            estimated_cost_usd=1.0,
            budget_available=50.0,
            provider_capability=True,
            compute_availability_state="enabled",
            feature_rollout_status=True,
        )
        boundary.evaluate(request)

        audit = get_evaluation_audit()
        assert len(audit) == 1
        entry = audit[0]
        assert entry["action_type"] == "test_action"
        assert entry["identity"] == "usr-int-1"
        assert entry["org_id"] == "org-int-1"
        assert entry["decision"] == "allow"

    def test_audit_entry_has_all_required_fields_for_persistence(
        self, boundary: GovernanceBoundary
    ):
        """The in-memory entry has all fields needed by _evaluation_to_row()."""
        request = GovernanceRequest(
            action_type="delete_asset",
            identity="usr-check-1",
            trust_domain="PLATFORM_ADMIN",
            tenant_context=TenantContext(org_id="org-check-1", role="admin"),
            role="admin",
            risk_classification=RiskClassification.HIGH_IMPACT,
            estimated_cost_usd=0.0,
            resource_ownership=True,
            provider_capability=True,
            compute_availability_state="enabled",
            feature_rollout_status=True,
        )
        boundary.evaluate(request)

        audit = get_evaluation_audit()
        entry = audit[0]

        # All fields that the audit table expects
        required_keys = {
            "evaluation_id",
            "correlation_id",
            "timestamp",
            "action_type",
            "identity",
            "trust_domain",
            "org_id",
            "role",
            "risk_classification",
            "decision",
            "denial_reason",
            "required_approval_type",
            "is_degraded",
            "failed_checks",
            "estimated_cost_usd",
        }
        assert required_keys.issubset(entry.keys())

    def test_denial_includes_denial_reason(self, boundary: GovernanceBoundary):
        """Denied evaluations include the denial reason in the audit entry."""
        request = GovernanceRequest(
            action_type="generate_image",
            identity=None,
            trust_domain="CUSTOMER_USER",
            tenant_context=TenantContext(org_id="org-deny-1", role="editor"),
            risk_classification=RiskClassification.HIGH_IMPACT,
        )
        boundary.evaluate(request)

        audit = get_evaluation_audit()
        entry = audit[0]
        assert entry["decision"] == "deny"
        assert entry["denial_reason"] is not None
        assert "identity" in entry["denial_reason"].lower() or "identity" in entry["failed_checks"]


# =============================================================================
# Test: API endpoint /aios/v1/governance/audit
# =============================================================================


@pytest.mark.unit
class TestGovernanceAuditEndpoint:
    """Verify the GET /aios/v1/governance/audit endpoint behavior."""

    def test_returns_empty_when_no_evaluations(self, api_client):
        response = api_client.get("/aios/v1/governance/audit")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["limit"] == 20
        assert data["offset"] == 0

    def test_returns_evaluations_after_boundary_calls(self, api_client):
        boundary = GovernanceBoundary()
        request = GovernanceRequest(
            action_type="generate_image",
            identity="usr-api-1",
            trust_domain="CUSTOMER_USER",
            tenant_context=TenantContext(org_id="org-api-1", role="editor"),
            risk_classification=RiskClassification.MEDIUM_IMPACT,
            estimated_cost_usd=2.0,
            budget_available=100.0,
            provider_capability=True,
            compute_availability_state="enabled",
            feature_rollout_status=True,
        )
        boundary.evaluate(request)

        response = api_client.get("/aios/v1/governance/audit")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["action_type"] == "generate_image"
        assert data["items"][0]["decision"] == "allow"

    def test_pagination_limit_and_offset(self, api_client):
        boundary = GovernanceBoundary()
        for i in range(5):
            request = GovernanceRequest(
                action_type=f"action_{i}",
                identity="usr-pag",
                trust_domain="CUSTOMER_USER",
                tenant_context=TenantContext(org_id="org-pag", role="editor"),
                risk_classification=RiskClassification.LOW_IMPACT,
            )
            boundary.evaluate(request)

        response = api_client.get("/aios/v1/governance/audit?limit=2&offset=1")
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 2
        assert data["offset"] == 1
        assert len(data["items"]) == 2
        assert data["total"] == 5

    def test_filter_by_decision(self, api_client):
        boundary = GovernanceBoundary()

        # Allow
        allow_req = GovernanceRequest(
            action_type="list_assets",
            identity="usr-filter",
            trust_domain="CUSTOMER_USER",
            tenant_context=TenantContext(org_id="org-filter", role="viewer"),
            risk_classification=RiskClassification.READ_ONLY,
        )
        boundary.evaluate(allow_req)

        # Deny
        deny_req = GovernanceRequest(
            action_type="delete_model",
            identity=None,
            risk_classification=RiskClassification.HIGH_IMPACT,
        )
        boundary.evaluate(deny_req)

        response = api_client.get("/aios/v1/governance/audit?decision=deny")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["decision"] == "deny"

    def test_filter_by_action_type(self, api_client):
        boundary = GovernanceBoundary()

        req1 = GovernanceRequest(
            action_type="generate_image",
            identity="usr-1",
            trust_domain="CUSTOMER_USER",
            tenant_context=TenantContext(org_id="org-1", role="editor"),
            risk_classification=RiskClassification.READ_ONLY,
        )
        req2 = GovernanceRequest(
            action_type="train_lora",
            identity="usr-1",
            trust_domain="CUSTOMER_USER",
            tenant_context=TenantContext(org_id="org-1", role="editor"),
            risk_classification=RiskClassification.READ_ONLY,
        )
        boundary.evaluate(req1)
        boundary.evaluate(req2)

        response = api_client.get("/aios/v1/governance/audit?action_type=train_lora")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["action_type"] == "train_lora"

    @pytest.fixture
    def api_client(self):
        """Create a test client for the FastAPI app."""
        from fastapi.testclient import TestClient
        from backend.main import app

        return TestClient(app)

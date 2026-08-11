"""Unit tests for Platform Admin API endpoints.

Tests cover:
    - R33.9: All operator actions logged with full audit trail
    - R33.10: /platform-admin returns 404 for non-operators
    - Operator CRUD: list, grant, revoke
    - Support session lifecycle: list, request, approve, revoke
    - Capability enforcement per endpoint

No I/O, no DB — services are fully mocked via dependency overrides.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.endpoints.platform_admin import (
    PlatformOperatorDep,
    require_platform_operator,
    router,
)
from app.core.dependencies import CurrentUserIDDep, DBSessionDep, PaginationDep
from app.db.session import get_db_session
from app.models.platform_operator import CapabilityGroup, PlatformOperator
from app.models.support_session import SupportSession, SupportSessionStatus


# =============================================================================
# Fixtures
# =============================================================================


def _make_operator(
    user_id: uuid.UUID | None = None,
    capability_grants: list[str] | None = None,
    granted_by: uuid.UUID | None = None,
    revoked_at: datetime | None = None,
) -> PlatformOperator:
    """Create a mock PlatformOperator for testing."""
    op = PlatformOperator()
    op.id = uuid.uuid4()
    op.user_id = user_id or uuid.uuid4()
    op.capability_grants = capability_grants or [
        CapabilityGroup.FOUNDER_AUTHORITY.value,
    ]
    op.granted_by = granted_by or uuid.uuid4()
    op.granted_at = datetime.now(UTC)
    op.revoked_at = revoked_at
    op.created_at = datetime.now(UTC)
    op.updated_at = datetime.now(UTC)
    return op


def _make_support_session(
    session_id: uuid.UUID | None = None,
    operator_user_id: uuid.UUID | None = None,
    target_org_id: uuid.UUID | None = None,
    status: str = SupportSessionStatus.REQUESTED.value,
) -> SupportSession:
    """Create a mock SupportSession for testing."""
    session = SupportSession()
    session.id = session_id or uuid.uuid4()
    session.operator_user_id = operator_user_id or uuid.uuid4()
    session.target_org_id = target_org_id or uuid.uuid4()
    session.reason = "Customer reported data sync issue"
    session.requested_capabilities = ["tenant_support"]
    session.approved_capabilities = None
    session.permitted_surfaces = ["job_history", "cost_records"]
    session.permitted_actions = ["view"]
    session.approved_by = None
    session.started_at = datetime.now(UTC)
    session.expires_at = datetime.now(UTC) + timedelta(hours=1)
    session.ended_at = None
    session.status = status
    session.created_at = datetime.now(UTC)
    session.updated_at = datetime.now(UTC)
    return session


@pytest.fixture
def founder_operator() -> PlatformOperator:
    """An operator with Founder Authority (full access)."""
    return _make_operator(
        capability_grants=[CapabilityGroup.FOUNDER_AUTHORITY.value],
    )


@pytest.fixture
def observer_operator() -> PlatformOperator:
    """An operator with Platform Observe only."""
    return _make_operator(
        capability_grants=[CapabilityGroup.PLATFORM_OBSERVE.value],
    )


@pytest.fixture
def support_operator() -> PlatformOperator:
    """An operator with Tenant Support + Escalation."""
    return _make_operator(
        capability_grants=[
            CapabilityGroup.TENANT_SUPPORT.value,
            CapabilityGroup.TENANT_ACCESS_ESCALATION.value,
        ],
    )


@pytest.fixture
def mock_db() -> AsyncMock:
    """Create a mock AsyncSession."""
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.execute = AsyncMock()
    db.scalar = AsyncMock()
    return db


def _create_test_app(operator: PlatformOperator | None, mock_db: AsyncMock) -> FastAPI:
    """Create a test FastAPI app with dependency overrides."""
    app = FastAPI()
    app.include_router(router)

    async def override_operator():
        if operator is None:
            from fastapi import HTTPException, status

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Not found",
            )
        return operator

    async def override_db():
        yield mock_db

    app.dependency_overrides[require_platform_operator] = override_operator
    app.dependency_overrides[get_db_session] = override_db

    return app


# =============================================================================
# Tests: Non-operator receives 404 on all routes
# =============================================================================


@pytest.mark.unit
class TestPlatformAdminAccessControl:
    """Verify that non-operators receive 404 on /platform-admin routes."""

    def test_non_operator_gets_404_on_list_operators(self, mock_db):
        """R33.10: Non-operators get 404, not 403."""
        app = _create_test_app(operator=None, mock_db=mock_db)
        client = TestClient(app)

        resp = client.get("/platform-admin/operators")
        assert resp.status_code == 404

    def test_non_operator_gets_404_on_grant_operator(self, mock_db):
        """R33.10: POST /operators returns 404 for non-operators."""
        app = _create_test_app(operator=None, mock_db=mock_db)
        client = TestClient(app)

        resp = client.post(
            "/platform-admin/operators",
            json={
                "user_id": str(uuid.uuid4()),
                "capability_grants": ["platform_observe"],
            },
        )
        assert resp.status_code == 404

    def test_non_operator_gets_404_on_delete_operator(self, mock_db):
        """R33.10: DELETE /operators/{id} returns 404 for non-operators."""
        app = _create_test_app(operator=None, mock_db=mock_db)
        client = TestClient(app)

        resp = client.delete(f"/platform-admin/operators/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_non_operator_gets_404_on_support_sessions(self, mock_db):
        """R33.10: GET /support-sessions returns 404 for non-operators."""
        app = _create_test_app(operator=None, mock_db=mock_db)
        client = TestClient(app)

        resp = client.get("/platform-admin/support-sessions")
        assert resp.status_code == 404

    def test_non_operator_gets_404_on_request_session(self, mock_db):
        """R33.10: POST /support-sessions returns 404 for non-operators."""
        app = _create_test_app(operator=None, mock_db=mock_db)
        client = TestClient(app)

        resp = client.post(
            "/platform-admin/support-sessions",
            json={
                "target_org_id": str(uuid.uuid4()),
                "reason": "Customer needs help with data issue",
                "duration_minutes": 60,
            },
        )
        assert resp.status_code == 404


# =============================================================================
# Tests: Operator Endpoints
# =============================================================================


@pytest.mark.unit
class TestListOperators:
    """Test GET /platform-admin/operators."""

    def test_list_operators_with_observe_capability(
        self, founder_operator, mock_db,
    ):
        """Operator with observe capability can list operators."""
        app = _create_test_app(operator=founder_operator, mock_db=mock_db)
        client = TestClient(app)

        with patch(
            "app.api.v1.endpoints.platform_admin.PlatformOperatorService"
        ) as MockService:
            mock_svc = MockService.return_value
            mock_svc.list_operators = AsyncMock(
                return_value=([founder_operator], 1)
            )
            mock_svc.log_action = AsyncMock()

            resp = client.get("/platform-admin/operators")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1

    def test_list_operators_without_observe_returns_404(
        self, mock_db,
    ):
        """Operator WITHOUT observe capability gets 404."""
        # Operator with only escalation cap — no observe
        limited_op = _make_operator(
            capability_grants=[CapabilityGroup.TENANT_ACCESS_ESCALATION.value],
        )
        app = _create_test_app(operator=limited_op, mock_db=mock_db)
        client = TestClient(app)

        resp = client.get("/platform-admin/operators")
        assert resp.status_code == 404


@pytest.mark.unit
class TestGrantOperator:
    """Test POST /platform-admin/operators."""

    def test_grant_operator_with_founder_authority(
        self, founder_operator, mock_db,
    ):
        """Founder can grant operator capabilities."""
        app = _create_test_app(operator=founder_operator, mock_db=mock_db)
        client = TestClient(app)

        new_user_id = uuid.uuid4()
        new_op = _make_operator(
            user_id=new_user_id,
            capability_grants=[CapabilityGroup.PLATFORM_OBSERVE.value],
            granted_by=founder_operator.user_id,
        )

        with patch(
            "app.api.v1.endpoints.platform_admin.PlatformOperatorService"
        ) as MockService:
            mock_svc = MockService.return_value
            mock_svc.grant_capabilities = AsyncMock(return_value=new_op)

            resp = client.post(
                "/platform-admin/operators",
                json={
                    "user_id": str(new_user_id),
                    "capability_grants": ["platform_observe"],
                },
            )

        assert resp.status_code == 201
        data = resp.json()
        assert data["user_id"] == str(new_user_id)

    def test_grant_operator_without_founder_returns_404(
        self, observer_operator, mock_db,
    ):
        """Operator without Founder Authority cannot grant."""
        app = _create_test_app(operator=observer_operator, mock_db=mock_db)
        client = TestClient(app)

        resp = client.post(
            "/platform-admin/operators",
            json={
                "user_id": str(uuid.uuid4()),
                "capability_grants": ["platform_observe"],
            },
        )
        assert resp.status_code == 404

    def test_grant_operator_duplicate_returns_409(
        self, founder_operator, mock_db,
    ):
        """Granting to user with active record returns 409."""
        from app.services.platform_operator_service import OperatorAlreadyExistsError

        app = _create_test_app(operator=founder_operator, mock_db=mock_db)
        client = TestClient(app)

        target_user_id = uuid.uuid4()

        with patch(
            "app.api.v1.endpoints.platform_admin.PlatformOperatorService"
        ) as MockService:
            mock_svc = MockService.return_value
            mock_svc.grant_capabilities = AsyncMock(
                side_effect=OperatorAlreadyExistsError(target_user_id)
            )

            resp = client.post(
                "/platform-admin/operators",
                json={
                    "user_id": str(target_user_id),
                    "capability_grants": ["platform_observe"],
                },
            )

        assert resp.status_code == 409


@pytest.mark.unit
class TestRevokeOperator:
    """Test DELETE /platform-admin/operators/{id}."""

    def test_revoke_operator_with_founder_authority(
        self, founder_operator, mock_db,
    ):
        """Founder can revoke an operator."""
        app = _create_test_app(operator=founder_operator, mock_db=mock_db)
        client = TestClient(app)

        target_id = uuid.uuid4()
        revoked_op = _make_operator(revoked_at=datetime.now(UTC))

        with patch(
            "app.api.v1.endpoints.platform_admin.PlatformOperatorService"
        ) as MockService:
            mock_svc = MockService.return_value
            mock_svc.revoke = AsyncMock(return_value=revoked_op)

            resp = client.delete(f"/platform-admin/operators/{target_id}")

        assert resp.status_code == 204

    def test_revoke_nonexistent_operator_returns_404(
        self, founder_operator, mock_db,
    ):
        """Revoking a non-existent operator returns 404."""
        from app.services.platform_operator_service import OperatorNotFoundError

        app = _create_test_app(operator=founder_operator, mock_db=mock_db)
        client = TestClient(app)

        target_id = uuid.uuid4()

        with patch(
            "app.api.v1.endpoints.platform_admin.PlatformOperatorService"
        ) as MockService:
            mock_svc = MockService.return_value
            mock_svc.revoke = AsyncMock(
                side_effect=OperatorNotFoundError(str(target_id))
            )

            resp = client.delete(f"/platform-admin/operators/{target_id}")

        assert resp.status_code == 404

    def test_revoke_without_founder_returns_404(
        self, observer_operator, mock_db,
    ):
        """Operator without Founder Authority cannot revoke."""
        app = _create_test_app(operator=observer_operator, mock_db=mock_db)
        client = TestClient(app)

        resp = client.delete(f"/platform-admin/operators/{uuid.uuid4()}")
        assert resp.status_code == 404


# =============================================================================
# Tests: Support Session Endpoints
# =============================================================================


@pytest.mark.unit
class TestListSupportSessions:
    """Test GET /platform-admin/support-sessions."""

    def test_list_sessions_with_tenant_support(
        self, support_operator, mock_db,
    ):
        """Operator with Tenant Support can list sessions."""
        app = _create_test_app(operator=support_operator, mock_db=mock_db)
        client = TestClient(app)

        session = _make_support_session()

        with patch(
            "app.api.v1.endpoints.platform_admin.SupportSessionService"
        ) as MockSS, patch(
            "app.api.v1.endpoints.platform_admin.PlatformOperatorService"
        ) as MockOp:
            MockSS.return_value.list_sessions = AsyncMock(
                return_value=([session], 1)
            )
            MockOp.return_value.log_action = AsyncMock()

            resp = client.get("/platform-admin/support-sessions")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1

    def test_list_sessions_without_tenant_support_returns_404(
        self, mock_db,
    ):
        """Operator without Tenant Support cannot list sessions."""
        limited_op = _make_operator(
            capability_grants=[CapabilityGroup.PLATFORM_OBSERVE.value],
        )
        app = _create_test_app(operator=limited_op, mock_db=mock_db)
        client = TestClient(app)

        resp = client.get("/platform-admin/support-sessions")
        assert resp.status_code == 404


@pytest.mark.unit
class TestRequestSupportSession:
    """Test POST /platform-admin/support-sessions."""

    def test_request_session_with_escalation_capability(
        self, support_operator, mock_db,
    ):
        """Operator with Tenant Access Escalation can request a session."""
        app = _create_test_app(operator=support_operator, mock_db=mock_db)
        client = TestClient(app)

        session = _make_support_session(
            operator_user_id=support_operator.user_id,
        )

        with patch(
            "app.api.v1.endpoints.platform_admin.SupportSessionService"
        ) as MockSS, patch(
            "app.api.v1.endpoints.platform_admin.PlatformOperatorService"
        ) as MockOp:
            MockSS.return_value.request_session = AsyncMock(
                return_value=session
            )
            MockOp.return_value.log_action = AsyncMock()

            resp = client.post(
                "/platform-admin/support-sessions",
                json={
                    "target_org_id": str(session.target_org_id),
                    "reason": "Customer reported data sync issue",
                    "permitted_surfaces": ["job_history"],
                    "permitted_actions": ["view"],
                    "duration_minutes": 60,
                },
            )

        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "requested"

    def test_request_session_without_escalation_returns_404(
        self, observer_operator, mock_db,
    ):
        """Operator without Escalation capability cannot request sessions."""
        app = _create_test_app(operator=observer_operator, mock_db=mock_db)
        client = TestClient(app)

        resp = client.post(
            "/platform-admin/support-sessions",
            json={
                "target_org_id": str(uuid.uuid4()),
                "reason": "Need to check a customer issue with their workspace",
                "duration_minutes": 30,
            },
        )
        assert resp.status_code == 404


@pytest.mark.unit
class TestApproveSupportSession:
    """Test POST /platform-admin/support-sessions/{id}/approve."""

    def test_approve_session_with_founder_authority(
        self, founder_operator, mock_db,
    ):
        """Founder can approve a support session."""
        app = _create_test_app(operator=founder_operator, mock_db=mock_db)
        client = TestClient(app)

        session = _make_support_session(
            status=SupportSessionStatus.ACTIVE.value,
        )
        session.approved_by = founder_operator.user_id
        session.approved_capabilities = ["tenant_support"]

        with patch(
            "app.api.v1.endpoints.platform_admin.SupportSessionService"
        ) as MockSS, patch(
            "app.api.v1.endpoints.platform_admin.PlatformOperatorService"
        ) as MockOp:
            MockSS.return_value.approve_session = AsyncMock(
                return_value=session
            )
            MockOp.return_value.log_action = AsyncMock()

            resp = client.post(
                f"/platform-admin/support-sessions/{session.id}/approve",
                json={},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["approved_by"] == str(founder_operator.user_id)

    def test_approve_session_not_found_returns_404(
        self, founder_operator, mock_db,
    ):
        """Approving a non-existent session returns 404."""
        from app.services.support_session_service import SessionNotFoundError

        app = _create_test_app(operator=founder_operator, mock_db=mock_db)
        client = TestClient(app)

        session_id = uuid.uuid4()

        with patch(
            "app.api.v1.endpoints.platform_admin.SupportSessionService"
        ) as MockSS:
            MockSS.return_value.approve_session = AsyncMock(
                side_effect=SessionNotFoundError(session_id)
            )

            resp = client.post(
                f"/platform-admin/support-sessions/{session_id}/approve",
                json={},
            )

        assert resp.status_code == 404

    def test_approve_without_founder_returns_404(
        self, observer_operator, mock_db,
    ):
        """Operator without Founder Authority cannot approve."""
        app = _create_test_app(operator=observer_operator, mock_db=mock_db)
        client = TestClient(app)

        resp = client.post(
            f"/platform-admin/support-sessions/{uuid.uuid4()}/approve",
            json={},
        )
        assert resp.status_code == 404


@pytest.mark.unit
class TestRevokeSupportSession:
    """Test POST /platform-admin/support-sessions/{id}/revoke."""

    def test_revoke_session_with_founder(
        self, founder_operator, mock_db,
    ):
        """Founder can revoke a support session."""
        app = _create_test_app(operator=founder_operator, mock_db=mock_db)
        client = TestClient(app)

        session = _make_support_session(
            status=SupportSessionStatus.REVOKED.value,
        )
        session.ended_at = datetime.now(UTC)

        with patch(
            "app.api.v1.endpoints.platform_admin.SupportSessionService"
        ) as MockSS, patch(
            "app.api.v1.endpoints.platform_admin.PlatformOperatorService"
        ) as MockOp:
            MockSS.return_value.revoke_session = AsyncMock(
                return_value=session
            )
            MockOp.return_value.log_action = AsyncMock()

            resp = client.post(
                f"/platform-admin/support-sessions/{session.id}/revoke",
                json={"reason": "Access no longer needed"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "revoked"

    def test_revoke_session_with_tenant_support(
        self, support_operator, mock_db,
    ):
        """Operator with Tenant Support can also revoke sessions."""
        app = _create_test_app(operator=support_operator, mock_db=mock_db)
        client = TestClient(app)

        session = _make_support_session(
            status=SupportSessionStatus.REVOKED.value,
        )
        session.ended_at = datetime.now(UTC)

        with patch(
            "app.api.v1.endpoints.platform_admin.SupportSessionService"
        ) as MockSS, patch(
            "app.api.v1.endpoints.platform_admin.PlatformOperatorService"
        ) as MockOp:
            MockSS.return_value.revoke_session = AsyncMock(
                return_value=session
            )
            MockOp.return_value.log_action = AsyncMock()

            resp = client.post(
                f"/platform-admin/support-sessions/{session.id}/revoke",
                json={"reason": "Access no longer needed"},
            )

        assert resp.status_code == 200

    def test_revoke_session_without_capability_returns_404(
        self, observer_operator, mock_db,
    ):
        """Operator without Founder/Support cannot revoke sessions."""
        app = _create_test_app(operator=observer_operator, mock_db=mock_db)
        client = TestClient(app)

        resp = client.post(
            f"/platform-admin/support-sessions/{uuid.uuid4()}/revoke",
            json={"reason": "test"},
        )
        assert resp.status_code == 404

    def test_revoke_invalid_transition_returns_409(
        self, founder_operator, mock_db,
    ):
        """Revoking a session in terminal state returns 409."""
        from app.services.support_session_service import InvalidTransitionError

        app = _create_test_app(operator=founder_operator, mock_db=mock_db)
        client = TestClient(app)

        session_id = uuid.uuid4()

        with patch(
            "app.api.v1.endpoints.platform_admin.SupportSessionService"
        ) as MockSS:
            MockSS.return_value.revoke_session = AsyncMock(
                side_effect=InvalidTransitionError(
                    session_id, "expired", "revoked"
                )
            )

            resp = client.post(
                f"/platform-admin/support-sessions/{session_id}/revoke",
                json={"reason": "too late"},
            )

        assert resp.status_code == 409


# =============================================================================
# Tests: Audit Logging
# =============================================================================


@pytest.mark.unit
class TestAuditLogging:
    """Verify that all actions are logged per R33.9."""

    def test_list_operators_logs_action(
        self, founder_operator, mock_db,
    ):
        """GET /operators logs a list_operators action."""
        app = _create_test_app(operator=founder_operator, mock_db=mock_db)
        client = TestClient(app)

        with patch(
            "app.api.v1.endpoints.platform_admin.PlatformOperatorService"
        ) as MockService:
            mock_svc = MockService.return_value
            mock_svc.list_operators = AsyncMock(return_value=([], 0))
            mock_svc.log_action = AsyncMock()

            client.get("/platform-admin/operators")

            mock_svc.log_action.assert_called_once()
            call_kwargs = mock_svc.log_action.call_args[1]
            assert call_kwargs["action_type"] == "list_operators"
            assert call_kwargs["operator_user_id"] == founder_operator.user_id
            assert call_kwargs["capability_used"] == "platform_observe"

    def test_request_session_logs_action(
        self, support_operator, mock_db,
    ):
        """POST /support-sessions logs a request_support_session action."""
        app = _create_test_app(operator=support_operator, mock_db=mock_db)
        client = TestClient(app)

        session = _make_support_session(
            operator_user_id=support_operator.user_id,
        )

        with patch(
            "app.api.v1.endpoints.platform_admin.SupportSessionService"
        ) as MockSS, patch(
            "app.api.v1.endpoints.platform_admin.PlatformOperatorService"
        ) as MockOp:
            MockSS.return_value.request_session = AsyncMock(
                return_value=session
            )
            mock_op_svc = MockOp.return_value
            mock_op_svc.log_action = AsyncMock()

            client.post(
                "/platform-admin/support-sessions",
                json={
                    "target_org_id": str(session.target_org_id),
                    "reason": "Customer reported data sync issue",
                    "duration_minutes": 60,
                },
            )

            mock_op_svc.log_action.assert_called_once()
            call_kwargs = mock_op_svc.log_action.call_args[1]
            assert call_kwargs["action_type"] == "request_support_session"
            assert call_kwargs["capability_used"] == "tenant_access_escalation"
            assert call_kwargs["target_org_id"] == session.target_org_id

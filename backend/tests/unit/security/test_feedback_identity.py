"""Authenticated identity and tenant isolation tests for feedback APIs."""
from __future__ import annotations

import inspect
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from backend.api_v1 import (
    router,
    submit_feedback,
    v1_get_durable_feedback,
    v1_submit_durable_feedback,
)
from backend.auth import AuthUser, require_auth
from backend.durable_feedback import clear_store, get_feedback
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

ORG_A = "11111111-1111-1111-1111-111111111111"
ORG_B = "22222222-2222-2222-2222-222222222222"
USER_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
USER_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
ASSET_ID = "asset-1"
JOB_ID = "job-1"
TALENT_ID = "talent-1"


@pytest.fixture(autouse=True)
def clean_feedback_store() -> None:
    """Keep in-memory durable feedback isolated between tests."""
    clear_store()
    yield
    clear_store()


def auth_user(org_id: str = ORG_A, user_id: str = USER_A) -> AuthUser:
    """Build a validated-auth stand-in for one tenant."""
    return AuthUser(user_id=user_id, email="user@example.test", org_id=org_id, role="owner")


def owned_reference_rows() -> dict[str, SimpleNamespace]:
    """Return successful org-scoped lookup results for all lineage references."""
    row = SimpleNamespace(data=[{"id": "owned"}])
    return {"asset": row, "job": row, "talent": row}


@pytest.mark.unit
def test_durable_feedback_uses_auth_identity_and_ignores_client_fields() -> None:
    """Body identity selectors cannot change persisted actor or tenant."""
    rows = owned_reference_rows()
    body = {
        "org_id": ORG_B,
        "user_id": USER_B,
        "asset_org_id": ORG_B,
        "asset_id": ASSET_ID,
        "job_id": JOB_ID,
        "talent_id": TALENT_ID,
        "rating_value": 5,
        "idempotency_key": "identity-test",
    }
    with (
        patch("backend.api_v1.get_asset_by_id", return_value=rows["asset"]),
        patch("backend.api_v1.get_job_by_id", return_value=rows["job"]),
        patch("backend.api_v1.get_talent_by_id", return_value=rows["talent"]),
    ):
        response = v1_submit_durable_feedback(body, auth_user())

    record = get_feedback(response["feedback_id"])
    assert record is not None
    assert record.org_id == ORG_A
    assert record.user_id == USER_A
    assert record.asset_id == ASSET_ID


@pytest.mark.unit
def test_cross_tenant_asset_returns_safe_not_found_without_persistence() -> None:
    """A foreign asset is indistinguishable from a missing asset."""
    body = {"asset_id": ASSET_ID, "rating_value": 4}
    with patch("backend.api_v1.get_asset_by_id", return_value=SimpleNamespace(data=[])), pytest.raises(
        HTTPException
    ) as denied:
        v1_submit_durable_feedback(body, auth_user(ORG_B, USER_B))

    assert denied.value.status_code == 404
    assert get_feedback("does-not-exist") is None


@pytest.mark.unit
def test_cross_tenant_feedback_detail_returns_safe_not_found() -> None:
    """A feedback ID owned by another tenant is not disclosed."""
    rows = owned_reference_rows()
    with (
        patch("backend.api_v1.get_asset_by_id", return_value=rows["asset"]),
        patch("backend.api_v1.get_job_by_id", return_value=rows["job"]),
        patch("backend.api_v1.get_talent_by_id", return_value=rows["talent"]),
    ):
        created = v1_submit_durable_feedback(
            {"asset_id": ASSET_ID, "rating_value": 4}, auth_user(ORG_A, USER_A)
        )

    with pytest.raises(HTTPException) as denied:
        v1_get_durable_feedback(created["feedback_id"], auth_user(ORG_B, USER_B))

    assert denied.value.status_code == 404
    assert "org" not in str(denied.value.detail).lower()


@pytest.mark.unit
def test_learning_signal_uses_auth_identity_and_strips_client_selectors() -> None:
    """Legacy learning records carry trusted actor/org and safe context only."""
    data = {
        "agent": "akose",
        "output_type": "generation",
        "rating": 5,
        "org_id": ORG_B,
        "user_id": USER_B,
        "context": {
            "prompt": "portrait",
            "org_id": ORG_B,
            "nested": {"user_id": USER_B, "safe": True},
        },
    }
    with patch(
        "backend.aios.learning.record_feedback",
        return_value={"ok": True},
    ) as record_feedback:
        result = submit_feedback(data, auth_user())

    assert result == {"ok": True}
    record_feedback.assert_called_once_with(
        "akose",
        "generation",
        {"prompt": "portrait", "nested": {"safe": True}},
        5,
        user_id=USER_A,
        org_id=ORG_A,
    )


@pytest.mark.unit
def test_lookup_errors_return_safe_not_found_without_secret_details() -> None:
    """Unexpected ownership lookup errors never expose provider/error text."""
    body = {"asset_id": ASSET_ID, "rating_value": 4}
    with patch(
        "backend.api_v1.get_asset_by_id",
        side_effect=RuntimeError("service_role_key=do-not-return"),
    ), pytest.raises(HTTPException) as denied:
        v1_submit_durable_feedback(body, auth_user())

    assert denied.value.status_code == 404
    assert "service_role_key" not in str(denied.value.detail)
    assert "do-not-return" not in str(denied.value.detail)


@pytest.mark.unit
def test_feedback_handlers_require_auth_dependency() -> None:
    """Feedback submission has explicit route-level bearer authentication."""
    parameter = inspect.signature(v1_submit_durable_feedback).parameters["user"]
    assert parameter.default.dependency is require_auth


@pytest.mark.unit
def test_missing_auth_returns_401_before_feedback_handler() -> None:
    """An unauthenticated request cannot reach feedback persistence."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    with patch(
        "backend.auth._authoritative_policy",
        return_value=SimpleNamespace(allows_dev_fallback=False),
    ):
        response = TestClient(app, raise_server_exceptions=False).post(
            "/api/v1/feedback/durable",
            json={"asset_id": ASSET_ID, "rating_value": 4},
        )

    assert response.status_code == 401
    assert "service_role" not in response.text.lower()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("foreign_field", "lookup"),
    [("job_id", "get_job_by_id"), ("talent_id", "get_talent_by_id")],
)
def test_cross_tenant_job_and_talent_references_are_not_accepted(
    foreign_field: str,
    lookup: str,
) -> None:
    """Every optional lineage reference is checked in the trusted tenant."""
    rows = owned_reference_rows()
    body = {"asset_id": ASSET_ID, "rating_value": 4, foreign_field: "foreign"}
    patches = {
        "backend.api_v1.get_asset_by_id": patch(
            "backend.api_v1.get_asset_by_id", return_value=rows["asset"]
        ),
        f"backend.api_v1.{lookup}": patch(
            f"backend.api_v1.{lookup}", return_value=SimpleNamespace(data=[])
        ),
    }
    with (
        patches["backend.api_v1.get_asset_by_id"],
        patches[f"backend.api_v1.{lookup}"],
        pytest.raises(HTTPException) as denied,
    ):
        v1_submit_durable_feedback(body, auth_user(ORG_B, USER_B))

    assert denied.value.status_code == 404


@pytest.mark.unit
def test_learning_engine_keeps_feedback_counts_tenant_scoped() -> None:
    """Legacy learning state does not aggregate one tenant into another."""
    from backend.aios.learning import AgentLearning

    engine = AgentLearning()
    engine.record_feedback("akose", "generation", {"style": "a"}, 5, USER_A, ORG_A)
    result_b = engine.record_feedback("akose", "generation", {"style": "b"}, 1, USER_B, ORG_B)

    assert result_b["total_feedback_for_agent"] == 1
    assert engine.get_agent_preferences("akose", org_id=ORG_A)["total_feedback"] == 1
    assert engine.get_agent_preferences("akose", org_id=ORG_B)["total_feedback"] == 1
    assert engine.get_all_agent_stats(org_id=ORG_A)["akose"]["total_feedback"] == 1

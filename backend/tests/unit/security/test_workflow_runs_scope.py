"""Unit tests for trusted organization scoping of workflow runs."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from backend.database import (
    create_workflow_run,
    get_workflow_run,
    update_workflow_run,
)
from backend.tenant_context import TenantValidationError


@pytest.fixture
def supabase_query() -> MagicMock:
    """Return a fluent Supabase query double with a successful response."""
    query = MagicMock()
    query.select.return_value = query
    query.insert.return_value = query
    query.update.return_value = query
    query.eq.return_value = query
    query.single.return_value = query
    query.execute.return_value = SimpleNamespace(data=[{"id": "run-1"}])
    return query


@pytest.mark.unit
def test_create_workflow_run_injects_trusted_org_without_mutating_input(
    supabase_query: MagicMock,
) -> None:
    """Creates always attribute the row to the validated trusted organization."""
    payload = {"workflow_id": "workflow-1", "status": "running"}

    with patch("backend.database.supabase") as supabase:
        supabase.table.return_value = supabase_query
        create_workflow_run(payload, "org-b")

    supabase.table.assert_called_once_with("workflow_runs")
    supabase_query.insert.assert_called_once_with(
        {"workflow_id": "workflow-1", "status": "running", "org_id": "org-b"}
    )
    assert payload == {"workflow_id": "workflow-1", "status": "running"}


@pytest.mark.unit
def test_get_workflow_run_applies_id_and_org_predicates(
    supabase_query: MagicMock,
) -> None:
    """Reads cannot resolve a run outside the trusted organization."""
    with patch("backend.database.supabase") as supabase:
        supabase.table.return_value = supabase_query
        get_workflow_run("run-1", "org-b")

    assert supabase_query.eq.call_args_list == [
        (("id", "run-1"),),
        (("org_id", "org-b"),),
    ]
    supabase_query.single.assert_called_once_with()


@pytest.mark.unit
def test_update_workflow_run_scopes_mutation_and_preserves_ownership(
    supabase_query: MagicMock,
) -> None:
    """Updates filter by organization and discard client ownership changes."""
    payload = {"status": "completed", "org_id": "org-a"}

    with patch("backend.database.supabase") as supabase:
        supabase.table.return_value = supabase_query
        update_workflow_run("run-1", payload, "org-b")

    supabase_query.update.assert_called_once()
    update_payload = supabase_query.update.call_args.args[0]
    assert update_payload["status"] == "completed"
    assert update_payload["updated_at"] == "now()"
    assert "org_id" not in update_payload
    assert supabase_query.eq.call_args_list == [
        (("id", "run-1"),),
        (("org_id", "org-b"),),
    ]
    assert payload == {"status": "completed", "org_id": "org-a"}


@pytest.mark.unit
@pytest.mark.parametrize(
    ("operation", "args"),
    [
        (create_workflow_run, ({"status": "running"}, None)),
        (get_workflow_run, ("run-1", None)),
        (update_workflow_run, ("run-1", {"status": "completed"}, None)),
    ],
)
def test_workflow_run_helpers_reject_missing_org_before_database(
    operation, args: tuple[object, ...]
) -> None:
    """Missing trusted tenant context cannot reach the Supabase client."""
    with (
        patch("backend.database.supabase") as supabase,
        pytest.raises(TenantValidationError),
    ):
        operation(*args)

    supabase.table.assert_not_called()

"""Unit coverage for worker organization context and lifecycle predicates."""
from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit

ORG_ID = "12345678-1234-5678-1234-567812345678"
JOB_ID = "87654321-4321-8765-4321-876543218765"


class RecordingQuery:
    """Minimal Supabase query-builder double with filter recording."""

    def __init__(self, response: SimpleNamespace) -> None:
        self.filters: list[tuple[str, object]] = []
        self.response = response

    def select(self, *_columns: object) -> RecordingQuery:
        return self

    def update(self, _payload: dict) -> RecordingQuery:
        return self

    def delete(self) -> RecordingQuery:
        return self

    def eq(self, name: str, value: object) -> RecordingQuery:
        self.filters.append((name, value))
        return self

    def order(self, *_args: object, **_kwargs: object) -> RecordingQuery:
        return self

    def limit(self, _limit: int) -> RecordingQuery:
        return self

    def execute(self) -> SimpleNamespace:
        return self.response


class RecordingSupabase:
    """Supabase double that returns configured rows for each query."""

    def __init__(self, *responses: SimpleNamespace) -> None:
        self.responses = list(responses)
        self.queries: list[RecordingQuery] = []

    def table(self, _table_name: str) -> RecordingQuery:
        response = self.responses.pop(0) if self.responses else SimpleNamespace(data=[])
        query = RecordingQuery(response)
        self.queries.append(query)
        return query


def test_worker_rejects_missing_and_malformed_org_before_database_access() -> None:
    """Direct worker construction fails closed without touching the database."""
    from backend import database
    from backend.worker import Worker

    database_client = MagicMock()
    with patch.object(database, "supabase", database_client):
        with pytest.raises(ValueError, match="org-id is required"):
            Worker(org_id=None)
        with pytest.raises(ValueError, match="valid UUID"):
            Worker(org_id="not-a-uuid")

    database_client.table.assert_not_called()


def test_worker_normalizes_valid_org_uuid() -> None:
    """A valid CLI UUID is the only organization context retained by the worker."""
    from backend.worker import Worker

    worker = Worker(org_id=ORG_ID.upper())

    assert worker.org_id == ORG_ID


@pytest.mark.parametrize("argv", [["worker"], ["worker", "--org-id", "not-a-uuid"]])
def test_worker_cli_rejects_missing_or_malformed_org_before_startup(
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
) -> None:
    """Argparse rejects absent or malformed organization input before Worker.run."""
    import backend.worker as worker_module

    monkeypatch.setattr(sys, "argv", argv)
    worker_constructor = MagicMock(side_effect=AssertionError("worker started unexpectedly"))
    monkeypatch.setattr(worker_module, "Worker", worker_constructor)

    with pytest.raises(SystemExit) as exc_info:
        worker_module.main()

    assert exc_info.value.code == 2
    worker_constructor.assert_not_called()


def test_worker_cli_passes_valid_org_to_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    """A valid required UUID reaches Worker and no environment fallback is used."""
    import backend.worker as worker_module

    monkeypatch.setattr(sys, "argv", ["worker", "--org-id", ORG_ID])
    worker = MagicMock()
    monkeypatch.setattr(worker_module, "Worker", worker)
    monkeypatch.setattr(worker_module.signal, "signal", lambda *_args: None)

    worker_module.main()

    worker.assert_called_once_with(name="worker", poll_interval=3, org_id=ORG_ID)
    worker.return_value.run.assert_called_once_with()


def test_all_worker_lifecycle_queries_bind_trusted_org() -> None:
    """Poll, claim, complete, and fail each constrain jobs by the trusted org."""
    from backend import database

    poll_client = RecordingSupabase(SimpleNamespace(data=[]))
    with patch.object(database, "supabase", poll_client):
        database.get_jobs(ORG_ID)
    assert poll_client.queries[0].filters.count(("org_id", ORG_ID)) == 1

    claim_client = RecordingSupabase(
        SimpleNamespace(data=[{"id": JOB_ID, "attempts": 0}]),
        SimpleNamespace(data=[{"id": JOB_ID, "org_id": ORG_ID}]),
    )
    with patch.object(database, "supabase", claim_client):
        database.claim_next_job("worker", "worker-1", ORG_ID)
    assert all(("org_id", ORG_ID) in query.filters for query in claim_client.queries)

    for operation in ("complete", "fail"):
        client = RecordingSupabase(SimpleNamespace(data=[{"id": JOB_ID, "org_id": ORG_ID}]))
        with patch.object(database, "supabase", client):
            if operation == "complete":
                database.complete_job(JOB_ID, {"ok": True}, ORG_ID)
            else:
                database.fail_job(JOB_ID, "expected failure", ORG_ID)
        assert client.queries[0].filters.count(("org_id", ORG_ID)) == 1


@pytest.mark.parametrize("operation", ["poll", "claim", "complete", "fail"])
def test_null_worker_context_makes_zero_database_calls(operation: str) -> None:
    """Missing job context fails before any service-role query is created."""
    from backend import database

    client = MagicMock()
    with patch.object(database, "supabase", client), pytest.raises(
        ValueError, match="org_id is required"
    ):
        if operation == "poll":
            database.get_jobs(None)
        elif operation == "claim":
            database.claim_next_job("worker", "worker-1", None)
        elif operation == "complete":
            database.complete_job(JOB_ID, {}, None)
        else:
            database.fail_job(JOB_ID, "failure", None)

    client.table.assert_not_called()


def test_action_generation_receives_command_org_context() -> None:
    """The direct action caller forwards durable command org_id to generation."""
    from backend.action_commands import _exec_generate_image
    from backend.engine.generation_engine import GenerationEngine

    engine = MagicMock(spec=GenerationEngine)
    engine.generate_and_register.return_value = {"id": "asset-1"}
    params = {"prompt": "a portrait", "org_id": "client-controlled-value"}

    with patch("backend.engine.generation_engine.GenerationEngine", return_value=engine):
        result = _exec_generate_image(params, ORG_ID)

    engine.generate_and_register.assert_called_once()
    assert engine.generate_and_register.call_args.kwargs["org_id"] == ORG_ID
    assert result["asset_id"] == "asset-1"


def test_action_command_execute_forwards_durable_org_to_dispatch() -> None:
    """Approved commands cannot omit org context when dispatching generation."""
    from backend.action_commands import ActionCommand, ActionCommandService, CommandStatus

    command = ActionCommand(
        id="command-1",
        idempotency_key="key-1",
        org_id=ORG_ID,
        user_id="user-1",
        session_id="session-1",
        tool="generate_image",
        parameters={"prompt": "a portrait"},
        status=CommandStatus.APPROVED,
    )
    with patch("backend.action_commands._exec_generate_image", return_value={}) as executor:
        ActionCommandService.execute(command)

    executor.assert_called_once_with(command.parameters, ORG_ID)

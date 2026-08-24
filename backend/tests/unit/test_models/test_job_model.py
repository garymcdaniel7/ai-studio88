"""Focused tests for the Job ORM model schema vs the live Supabase jobs table.

The live ``public.jobs`` table is the source of truth. These tests assert that
the SQLAlchemy Job model maps exactly to those live columns (no drifted names
like ``job_type`` / ``attempt_count``, no model-only columns like ``user_id`` /
``context_package_id``).
"""

from __future__ import annotations

from app.models.job import Job

# Exact column set of the live Supabase public.jobs table.
LIVE_JOBS_COLUMNS = {
    "attempts",
    "completed_at",
    "created_at",
    "error",
    "id",
    "idempotency_key",
    "input",
    "max_attempts",
    "org_id",
    "output",
    "priority",
    "progress",
    "progress_metadata",
    "project_id",
    "started_at",
    "status",
    "talent_id",
    "type",
    "updated_at",
    "worker_id",
    "worker_name",
    "workflow_id",
    "workload_class",
}


def test_job_model_columns_match_live_schema() -> None:
    """The model's mapped columns exactly match the live table columns."""
    model_columns = set(Job.__table__.columns.keys())
    assert model_columns == LIVE_JOBS_COLUMNS


def test_job_model_uses_live_column_names() -> None:
    """Renamed columns use the live names; drifted columns are absent."""
    assert "type" in Job.__table__.columns
    assert "attempts" in Job.__table__.columns
    assert "progress" in Job.__table__.columns
    assert "error" in Job.__table__.columns
    assert "input" in Job.__table__.columns
    assert "output" in Job.__table__.columns

    # Old drifted / model-only columns must not be mapped.
    for absent in (
        "job_type",
        "attempt_count",
        "progress_percent",
        "progress_message",
        "error_message",
        "output_asset_ids",
        "cost_usd",
        "max_duration_seconds",
        "user_id",
        "context_package_id",
        "metadata",
    ):
        assert absent not in Job.__table__.columns, f"unexpected column: {absent}"

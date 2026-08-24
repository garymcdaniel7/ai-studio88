"""Job ORM model.

Represents an async processing job (generation, training, publishing, etc.).

The column set is reconciled to the LIVE Supabase ``public.jobs`` table, which
is the source of truth. Columns are mapped to the live schema:

    live column   ->  ORM attribute
    ------------      --------------
    type             ->  ``type``          (was ``job_type``)
    attempts         ->  ``attempts``      (was ``attempt_count``)
    progress         ->  ``progress_percent``
    error            ->  ``error_message``
    input            ->  ``parameters``
    output           ->  ``output_asset_ids``

Columns that exist only in the old model and not in the live table
(``user_id``, ``context_package_id``, ``cost_usd``, ``max_duration_seconds``,
``progress_message``, ``metadata``) are intentionally dropped.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDMixin


class Job(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """Job entity — an async processing job within a workspace.

    Always scoped to org_id. Cross-tenant access returns 404.
    Jobs are never soft-deleted — they have terminal status states.
    """

    __tablename__ = "jobs"

    # Workload type / routing
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    workload_class: Mapped[str | None] = mapped_column(String(50), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued")

    # Idempotency
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Input / output (map to live `input` / `output` columns)
    parameters: Mapped[dict | None] = mapped_column("input", JSONB, nullable=True)
    output_asset_ids: Mapped[list | None] = mapped_column(
        "output", JSONB, nullable=True
    )

    # Progress / error (map to live `progress` / `error` columns)
    progress_percent: Mapped[int | None] = mapped_column(
        "progress", Integer, nullable=True
    )
    progress_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column("error", Text, nullable=True)

    # Retry
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)

    # Scheduling / worker
    worker_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    worker_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Timestamps
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # References
    talent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

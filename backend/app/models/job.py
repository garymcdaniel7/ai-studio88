"""Job ORM model.

Represents an async processing job (generation, training, publishing, etc.).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDMixin


class Job(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """Job entity — an async processing job within a workspace.

    Always scoped to org_id. Cross-tenant access returns 404.
    Jobs are never soft-deleted — they have terminal status states.
    """

    __tablename__ = "jobs"

    job_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Idempotency
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Progress
    progress_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    progress_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Output
    output_asset_ids: Mapped[list | None] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=True)

    # Cost tracking
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Retry
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    max_duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=1800)

    # Scheduling
    workload_class: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Timestamps
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # References
    talent_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Context
    context_package_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    parameters: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

"""Provider Reputation ORM model.

Persists per-provider performance metrics to Supabase for dynamic
ranking and auto-quarantine decisions. Extends the existing in-memory
ProviderReputation engine with durable storage.

Metrics tracked:
    Positive signals:
        - startup_latency_seconds: time to boot/connect
        - queue_latency_seconds: time spent waiting in queue
        - generation_duration_seconds: average job execution time
        - failure_rate_24h: rolling 24-hour failure percentage
        - cost_variance: estimate vs actual cost deviation
        - availability_7d: uptime percentage over 7 days
        - model_cache_readiness: fraction of models pre-loaded (0.0-1.0)
        - quality_acceptance_rate: user acceptance rate of outputs

    Negative signals:
        - cleanup_failures: instances not terminated properly
        - cost_overruns: jobs exceeding budget estimate
        - timeout_rate: fraction of jobs timing out
        - connection_failures: SSH/API connection failures

    Quarantine:
        - is_quarantined: auto-excluded from dispatch
        - quarantined_at: when quarantine began
        - quarantine_reason: why provider was quarantined

Validates: Requirements R65.1, R65.2, R65.3, R65.4, R65.5, R65.6
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDMixin


class ProviderReputation(Base, UUIDMixin, TimestampMixin, TenantMixin):
    """Provider reputation record — persisted metrics for dynamic ranking.

    One record per (org_id, provider_name) pair. Updated after every job
    outcome to maintain rolling metrics. Cross-tenant access returns 404.

    Auto-quarantine: failure_rate_24h > 30% → is_quarantined=True until
    manually reviewed or metrics recover.
    """

    __tablename__ = "provider_reputation"

    # Provider identification
    provider_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Compute provider identifier (e.g., 'runpod', 'fluidstack', 'vast')",
    )
    provider_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="compute",
        server_default="compute",
        comment="Provider type: compute, llm, storage, voice",
    )

    # Positive signal metrics
    startup_latency_seconds: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        server_default="0.0",
        comment="Average time to boot/connect (seconds)",
    )
    queue_latency_seconds: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        server_default="0.0",
        comment="Average time spent waiting in queue (seconds)",
    )
    generation_duration_seconds: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        server_default="0.0",
        comment="Average job execution duration (seconds)",
    )
    failure_rate_24h: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        server_default="0.0",
        comment="Rolling 24-hour failure rate (0.0-1.0)",
    )
    cost_variance: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        server_default="0.0",
        comment="Average estimate vs actual cost variance (ratio)",
    )
    availability_7d: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=1.0,
        server_default="1.0",
        comment="7-day rolling availability percentage (0.0-1.0)",
    )
    model_cache_readiness: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        server_default="0.0",
        comment="Fraction of required models pre-loaded (0.0-1.0)",
    )
    quality_acceptance_rate: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=1.0,
        server_default="1.0",
        comment="User acceptance rate of generated outputs (0.0-1.0)",
    )

    # Negative signal metrics
    cleanup_failures: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Count of instances not terminated properly",
    )
    cost_overruns: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Count of jobs exceeding budget estimate",
    )
    timeout_rate: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        server_default="0.0",
        comment="Fraction of jobs that timed out (0.0-1.0)",
    )
    connection_failures: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Count of connection failures (SSH/API)",
    )

    # Aggregate counters for rolling calculations
    total_jobs: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Total jobs processed by this provider",
    )
    successful_jobs: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Total successful jobs",
    )
    failed_jobs: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Total failed jobs",
    )
    total_cost_usd: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        server_default="0.0",
        comment="Cumulative cost incurred on this provider (USD)",
    )

    # Quarantine
    is_quarantined: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="Whether provider is excluded from job dispatch",
    )
    quarantined_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When quarantine began",
    )
    quarantine_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Reason for quarantine",
    )

    # Dynamic ranking score (computed from all metrics)
    overall_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.5,
        server_default="0.5",
        comment="Computed overall reputation score (0.0-1.0)",
    )

    # Extended metadata (GPU type, region, capabilities)
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
        comment="Extended provider metadata (gpu_type, region, vram_gb, etc.)",
    )

    # Last job outcome timestamp (for staleness checks)
    last_job_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the last job outcome was recorded",
    )

    __table_args__ = (
        Index("ix_provider_reputation_org_id", "org_id"),
        Index(
            "ix_provider_reputation_org_provider",
            "org_id",
            "provider_name",
            unique=True,
        ),
        Index(
            "ix_provider_reputation_org_score",
            "org_id",
            "overall_score",
        ),
        Index(
            "ix_provider_reputation_quarantined",
            "org_id",
            "is_quarantined",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ProviderReputation(id={self.id}, org_id={self.org_id}, "
            f"provider={self.provider_name}, score={self.overall_score}, "
            f"quarantined={self.is_quarantined})>"
        )

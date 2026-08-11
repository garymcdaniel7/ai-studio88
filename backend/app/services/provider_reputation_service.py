"""Provider Reputation Service — dynamic ranking and auto-quarantine.

Persists per-provider metrics to Supabase and provides:
    - record_job_outcome(): update metrics after job completion
    - get_provider_ranking(): return dynamic ranking (learned, not hardcoded)
    - check_quarantine(): auto-quarantine if failure_rate > 30%
    - get_provider_metrics(): get current metrics for a provider

Extends the existing in-memory ProviderReputation engine in
backend/infrastructure/provider_reputation.py with durable storage.

Key invariant: Provider preference is a learned ranking based on
accumulated performance data, not a permanent hardcoded list.

Validates: Requirements R65.1, R65.2, R65.3, R65.4, R65.5, R65.6
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.logging import get_logger
from app.models.provider_reputation import ProviderReputation
from app.schemas.provider_reputation import (
    JobOutcomeStatus,
    ProviderRankingEntry,
    ProviderRankingResponse,
    ProviderType,
    QuarantineCheckResponse,
    RecordJobOutcomeRequest,
    RecordOutcomeResponse,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

# Quarantine threshold: failure rate > 30% over 24h triggers auto-quarantine
QUARANTINE_FAILURE_THRESHOLD = 0.30

# Minimum jobs before quarantine decisions apply (avoid noise from small samples)
MIN_JOBS_FOR_QUARANTINE = 5

# Scoring weights for overall reputation score
WEIGHT_RELIABILITY = 0.35
WEIGHT_LATENCY = 0.20
WEIGHT_COST_EFFICIENCY = 0.15
WEIGHT_AVAILABILITY = 0.15
WEIGHT_QUALITY = 0.15


class ProviderReputationService:
    """Service for managing provider reputation with Supabase persistence.

    All methods require org_id for tenant scoping. Provider reputation
    data is never shared across organizations.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def record_job_outcome(
        self,
        org_id: UUID,
        request: RecordJobOutcomeRequest,
    ) -> RecordOutcomeResponse:
        """Record a job outcome and update provider metrics.

        Creates the provider reputation record if it doesn't exist (upsert).
        Updates rolling metrics and recalculates overall score.
        Checks for auto-quarantine after update.

        Args:
            org_id: Organization this provider is associated with.
            request: Job outcome data to record.

        Returns:
            Updated provider score and quarantine status.

        Validates: R65.1, R65.2, R65.5
        """
        # Get or create reputation record
        record = await self._get_or_create_record(
            org_id=org_id,
            provider_name=request.provider_name,
            provider_type=request.provider_type.value,
        )

        # Update aggregate counters
        record.total_jobs += 1
        if request.status == JobOutcomeStatus.SUCCESS:
            record.successful_jobs += 1
        else:
            record.failed_jobs += 1

        # Update specific negative signal counters
        if request.status == JobOutcomeStatus.TIMEOUT:
            record.timeout_rate = self._compute_rolling_rate(
                current_rate=record.timeout_rate,
                total=record.total_jobs,
                is_event=True,
            )
        elif request.status == JobOutcomeStatus.CONNECTION_FAILURE:
            record.connection_failures += 1
        elif request.status == JobOutcomeStatus.CLEANUP_FAILURE:
            record.cleanup_failures += 1

        # Update latency metrics (exponential moving average)
        if request.startup_latency_seconds is not None:
            record.startup_latency_seconds = self._ema(
                record.startup_latency_seconds,
                request.startup_latency_seconds,
                record.total_jobs,
            )

        if request.queue_latency_seconds is not None:
            record.queue_latency_seconds = self._ema(
                record.queue_latency_seconds,
                request.queue_latency_seconds,
                record.total_jobs,
            )

        if request.generation_duration_seconds is not None:
            record.generation_duration_seconds = self._ema(
                record.generation_duration_seconds,
                request.generation_duration_seconds,
                record.total_jobs,
            )

        # Update cost variance
        if (
            request.estimated_cost_usd is not None
            and request.actual_cost_usd is not None
            and request.estimated_cost_usd > 0
        ):
            variance = abs(request.actual_cost_usd - request.estimated_cost_usd) / request.estimated_cost_usd
            record.cost_variance = self._ema(
                record.cost_variance,
                variance,
                record.total_jobs,
            )
            if request.actual_cost_usd > request.estimated_cost_usd:
                record.cost_overruns += 1

        # Update actual cost tracking
        if request.actual_cost_usd is not None:
            record.total_cost_usd += request.actual_cost_usd

        # Update quality acceptance rate
        if request.quality_accepted is not None:
            acceptance_value = 1.0 if request.quality_accepted else 0.0
            record.quality_acceptance_rate = self._ema(
                record.quality_acceptance_rate,
                acceptance_value,
                record.total_jobs,
            )

        # Update failure rate (rolling average)
        record.failure_rate_24h = (
            record.failed_jobs / record.total_jobs if record.total_jobs > 0 else 0.0
        )

        # Update availability (based on failures)
        record.availability_7d = (
            record.successful_jobs / record.total_jobs if record.total_jobs > 0 else 1.0
        )

        # Update metadata if provided
        if request.metadata is not None:
            record.metadata_ = request.metadata

        # Record timestamp
        record.last_job_at = datetime.now(UTC)

        # Recalculate overall score
        record.overall_score = self._compute_overall_score(record)

        # Check auto-quarantine
        quarantine_result = self._evaluate_quarantine(record)
        if quarantine_result == "quarantine":
            record.is_quarantined = True
            record.quarantined_at = datetime.now(UTC)
            record.quarantine_reason = (
                f"Auto-quarantined: failure rate {record.failure_rate_24h:.2%} "
                f"exceeds threshold {QUARANTINE_FAILURE_THRESHOLD:.0%} "
                f"({record.failed_jobs}/{record.total_jobs} jobs failed)"
            )
            logger.warning(
                "provider_auto_quarantined",
                provider_name=request.provider_name,
                org_id=str(org_id),
                failure_rate=record.failure_rate_24h,
            )

        await self.db.flush()

        logger.info(
            "provider_reputation_updated",
            provider_name=request.provider_name,
            org_id=str(org_id),
            status=request.status.value,
            overall_score=record.overall_score,
            total_jobs=record.total_jobs,
        )

        return RecordOutcomeResponse(
            provider_name=request.provider_name,
            updated_score=record.overall_score,
            is_quarantined=record.is_quarantined,
            total_jobs=record.total_jobs,
        )

    async def get_provider_ranking(
        self,
        org_id: UUID,
        include_quarantined: bool = False,
    ) -> ProviderRankingResponse:
        """Get dynamic provider ranking ordered by overall reputation score.

        Returns providers sorted by learned ranking score. Quarantined
        providers are excluded by default unless explicitly requested.

        Args:
            org_id: Organization to query rankings for.
            include_quarantined: Whether to include quarantined providers.

        Returns:
            Ranked list of providers with key metrics.

        Validates: R65.3, R65.6
        """
        stmt = (
            select(ProviderReputation)
            .where(ProviderReputation.org_id == org_id)
            .order_by(ProviderReputation.overall_score.desc())
        )

        if not include_quarantined:
            stmt = stmt.where(ProviderReputation.is_quarantined.is_(False))

        result = await self.db.execute(stmt)
        records = list(result.scalars().all())

        # Count quarantined separately
        quarantine_stmt = (
            select(ProviderReputation)
            .where(
                ProviderReputation.org_id == org_id,
                ProviderReputation.is_quarantined.is_(True),
            )
        )
        quarantine_result = await self.db.execute(quarantine_stmt)
        quarantined_count = len(list(quarantine_result.scalars().all()))

        rankings = [
            ProviderRankingEntry(
                provider_name=r.provider_name,
                provider_type=r.provider_type,
                overall_score=round(r.overall_score, 4),
                failure_rate_24h=round(r.failure_rate_24h, 4),
                availability_7d=round(r.availability_7d, 4),
                startup_latency_seconds=round(r.startup_latency_seconds, 2),
                total_jobs=r.total_jobs,
                is_quarantined=r.is_quarantined,
            )
            for r in records
        ]

        return ProviderRankingResponse(
            rankings=rankings,
            total_providers=len(rankings),
            quarantined_count=quarantined_count,
        )

    async def check_quarantine(
        self,
        org_id: UUID,
        provider_name: str,
    ) -> QuarantineCheckResponse:
        """Check whether a provider should be quarantined and apply if needed.

        Auto-quarantine logic: if failure_rate_24h > 30% over at least
        MIN_JOBS_FOR_QUARANTINE jobs, the provider is excluded from dispatch.

        If the failure rate has recovered below the threshold and the
        provider is currently quarantined, it will be released.

        Args:
            org_id: Organization context.
            provider_name: Provider to check.

        Returns:
            Current quarantine status and any action taken.

        Validates: R65.4
        """
        stmt = select(ProviderReputation).where(
            ProviderReputation.org_id == org_id,
            ProviderReputation.provider_name == provider_name,
        )
        result = await self.db.execute(stmt)
        record = result.scalar_one_or_none()

        if record is None:
            return QuarantineCheckResponse(
                provider_name=provider_name,
                is_quarantined=False,
                failure_rate_24h=0.0,
                threshold=QUARANTINE_FAILURE_THRESHOLD,
                action_taken=None,
                reason="No reputation data found for this provider",
            )

        action_taken: str | None = None
        reason: str | None = None

        quarantine_decision = self._evaluate_quarantine(record)

        if quarantine_decision == "quarantine" and not record.is_quarantined:
            record.is_quarantined = True
            record.quarantined_at = datetime.now(UTC)
            record.quarantine_reason = (
                f"Auto-quarantined: failure rate {record.failure_rate_24h:.2%} "
                f"exceeds {QUARANTINE_FAILURE_THRESHOLD:.0%}"
            )
            action_taken = "quarantined"
            reason = record.quarantine_reason
            await self.db.flush()
            logger.warning(
                "provider_quarantined",
                provider_name=provider_name,
                org_id=str(org_id),
                failure_rate=record.failure_rate_24h,
            )

        elif quarantine_decision == "release" and record.is_quarantined:
            record.is_quarantined = False
            record.quarantined_at = None
            record.quarantine_reason = None
            action_taken = "released"
            reason = (
                f"Released: failure rate {record.failure_rate_24h:.2%} "
                f"recovered below {QUARANTINE_FAILURE_THRESHOLD:.0%}"
            )
            await self.db.flush()
            logger.info(
                "provider_released_from_quarantine",
                provider_name=provider_name,
                org_id=str(org_id),
                failure_rate=record.failure_rate_24h,
            )

        return QuarantineCheckResponse(
            provider_name=provider_name,
            is_quarantined=record.is_quarantined,
            failure_rate_24h=round(record.failure_rate_24h, 4),
            threshold=QUARANTINE_FAILURE_THRESHOLD,
            action_taken=action_taken,
            reason=reason,
        )

    async def get_provider_metrics(
        self,
        org_id: UUID,
        provider_name: str,
    ) -> ProviderReputation | None:
        """Get full metrics for a specific provider.

        Args:
            org_id: Organization context.
            provider_name: Provider to query.

        Returns:
            Provider reputation record or None if not found.

        Validates: R65.1, R65.2, R65.6
        """
        stmt = select(ProviderReputation).where(
            ProviderReputation.org_id == org_id,
            ProviderReputation.provider_name == provider_name,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def quarantine_provider(
        self,
        org_id: UUID,
        provider_name: str,
        reason: str,
    ) -> bool:
        """Manually quarantine a provider.

        Args:
            org_id: Organization context.
            provider_name: Provider to quarantine.
            reason: Reason for quarantine.

        Returns:
            True if provider was quarantined, False if not found.
        """
        stmt = select(ProviderReputation).where(
            ProviderReputation.org_id == org_id,
            ProviderReputation.provider_name == provider_name,
        )
        result = await self.db.execute(stmt)
        record = result.scalar_one_or_none()

        if record is None:
            return False

        record.is_quarantined = True
        record.quarantined_at = datetime.now(UTC)
        record.quarantine_reason = reason
        await self.db.flush()

        logger.info(
            "provider_manually_quarantined",
            provider_name=provider_name,
            org_id=str(org_id),
            reason=reason,
        )
        return True

    async def release_provider(
        self,
        org_id: UUID,
        provider_name: str,
    ) -> bool:
        """Release a provider from quarantine.

        Args:
            org_id: Organization context.
            provider_name: Provider to release.

        Returns:
            True if provider was released, False if not found.
        """
        stmt = select(ProviderReputation).where(
            ProviderReputation.org_id == org_id,
            ProviderReputation.provider_name == provider_name,
        )
        result = await self.db.execute(stmt)
        record = result.scalar_one_or_none()

        if record is None:
            return False

        record.is_quarantined = False
        record.quarantined_at = None
        record.quarantine_reason = None
        await self.db.flush()

        logger.info(
            "provider_manually_released",
            provider_name=provider_name,
            org_id=str(org_id),
        )
        return True

    # ─── Private Helpers ──────────────────────────────────────────────────

    async def _get_or_create_record(
        self,
        org_id: UUID,
        provider_name: str,
        provider_type: str,
    ) -> ProviderReputation:
        """Get existing reputation record or create a new one.

        Uses SELECT first, then INSERT if not found — simple and compatible
        with all DB backends.
        """
        stmt = select(ProviderReputation).where(
            ProviderReputation.org_id == org_id,
            ProviderReputation.provider_name == provider_name,
        )
        result = await self.db.execute(stmt)
        record = result.scalar_one_or_none()

        if record is not None:
            return record

        # Create new record
        record = ProviderReputation(
            org_id=org_id,
            provider_name=provider_name,
            provider_type=provider_type,
        )
        self.db.add(record)
        await self.db.flush()
        return record

    @staticmethod
    def _ema(current: float, new_value: float, total: int, alpha: float = 0.1) -> float:
        """Compute exponential moving average.

        For the first observation, return the new value directly.
        For subsequent observations, blend with existing average.
        """
        if total <= 1:
            return new_value
        return current * (1 - alpha) + new_value * alpha

    @staticmethod
    def _compute_rolling_rate(
        current_rate: float,
        total: int,
        is_event: bool,
    ) -> float:
        """Compute a rolling rate incrementally.

        Uses a simple incremental formula:
            new_rate = ((current_rate * (total-1)) + event_value) / total
        """
        event_value = 1.0 if is_event else 0.0
        if total <= 1:
            return event_value
        return ((current_rate * (total - 1)) + event_value) / total

    @staticmethod
    def _compute_overall_score(record: ProviderReputation) -> float:
        """Compute weighted overall reputation score.

        Components:
            - Reliability (35%): success rate
            - Latency (20%): inverse of startup latency (normalized)
            - Cost efficiency (15%): inverse of cost variance
            - Availability (15%): 7-day rolling availability
            - Quality (15%): user acceptance rate

        Returns a score between 0.0 and 1.0.
        """
        # Reliability: success rate
        reliability = (
            record.successful_jobs / record.total_jobs
            if record.total_jobs > 0
            else 0.5
        )

        # Latency: normalize against 300s max (lower is better)
        max_latency = 300.0
        latency_score = max(0.0, 1.0 - (record.startup_latency_seconds / max_latency))

        # Cost efficiency: lower variance is better
        cost_score = max(0.0, 1.0 - record.cost_variance)

        # Availability
        availability_score = record.availability_7d

        # Quality
        quality_score = record.quality_acceptance_rate

        overall = (
            WEIGHT_RELIABILITY * reliability
            + WEIGHT_LATENCY * latency_score
            + WEIGHT_COST_EFFICIENCY * cost_score
            + WEIGHT_AVAILABILITY * availability_score
            + WEIGHT_QUALITY * quality_score
        )

        return round(max(0.0, min(1.0, overall)), 4)

    @staticmethod
    def _evaluate_quarantine(record: ProviderReputation) -> str:
        """Evaluate whether a provider should be quarantined or released.

        Returns:
            "quarantine" if should be quarantined
            "release" if should be released from quarantine
            "no_change" if current state is correct
        """
        if record.total_jobs < MIN_JOBS_FOR_QUARANTINE:
            return "no_change"

        if record.failure_rate_24h > QUARANTINE_FAILURE_THRESHOLD:
            return "quarantine"

        if record.is_quarantined and record.failure_rate_24h <= QUARANTINE_FAILURE_THRESHOLD:
            return "release"

        return "no_change"

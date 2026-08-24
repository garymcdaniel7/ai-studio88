"""Job repository — tenant-scoped database access for Jobs and Job Leases.

All queries are automatically filtered by org_id from TenantContext.
Cross-tenant access returns 404. The quarantined UUID is rejected with 422.

Includes atomic job claiming via FOR UPDATE SKIP LOCKED, lease management
(heartbeat, release), and stale lease expiration.

Requirements: R2.2, R2.6, R2.7, R2.8, R2.9, R2.10, R21.2, R21.3, R21.4,
              R21.5, R21.12, R64.2, R64.4
"""

from __future__ import annotations

import uuid as uuid_mod
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select, update

from app.core.logging import get_logger
from app.db.tenant_scope import TenantScopedRepository
from app.models.job import Job
from app.models.job_lease import JobLease

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

# Terminal statuses where jobs cannot be claimed or re-queued
TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})

# Default lease duration if not specified
DEFAULT_LEASE_DURATION = timedelta(minutes=30)


class JobRepository(TenantScopedRepository):
    """Tenant-scoped repository for Job entities and job leasing.

    All operations are automatically scoped to the authenticated org_id.
    The org_id is resolved from TenantContext (JWT → org_members lookup)
    and never accepted from client request parameters.

    Jobs are not soft-deleted — they have terminal status states
    (completed, failed, cancelled).

    Leasing operations use FOR UPDATE SKIP LOCKED for atomic claiming
    without blocking concurrent workers.
    """

    def __init__(self, db: "AsyncSession", org_id: UUID) -> None:
        """Initialize with DB session and authenticated org_id."""
        super().__init__(db, org_id)

    # =========================================================================
    # Basic CRUD
    # =========================================================================

    async def get_by_id(self, job_id: UUID) -> Job:
        """Fetch a single job by ID, scoped to authenticated org.

        Returns 404 if not found or belongs to different org (R2.6).
        """
        return await self._get_one(Job, job_id, "Job")

    async def list_all(
        self,
        limit: int = 20,
        offset: int = 0,
        status: str | None = None,
        job_type: str | None = None,
        talent_id: UUID | None = None,
    ) -> tuple[list[Job], int]:
        """List jobs for the authenticated org with optional filters.

        Args:
            limit: Maximum items per page (1-100).
            offset: Pagination offset.
            status: Filter by job status.
            job_type: Filter by job type.
            talent_id: Filter by associated talent.

        Returns:
            Tuple of (items, total_count) for this tenant only.
        """
        stmt = select(Job)

        if status is not None:
            stmt = stmt.where(Job.status == status)

        if job_type is not None:
            stmt = stmt.where(Job.type == job_type)

        if talent_id is not None:
            stmt = stmt.where(Job.talent_id == talent_id)

        return await self._list(Job, stmt, limit, offset)

    async def create(self, **kwargs: object) -> Job:
        """Create a new job record for the authenticated org.

        The org_id is automatically set from the repository context.
        """
        job = Job(org_id=self._org_id, **kwargs)
        self._db.add(job)
        await self._db.flush()
        return job

    async def find_by_idempotency_key(self, key: str) -> Job | None:
        """Find an existing non-terminal job by idempotency key within this org.

        Used for deduplication: same (org_id, key) for non-terminal job →
        return existing (R21.11).

        Args:
            key: The idempotency key to look up.

        Returns:
            Job if found and non-terminal (queued/running), None otherwise.
        """
        from app.db.tenant_scope import tenant_filter

        stmt = select(Job).where(Job.idempotency_key == key)
        stmt = tenant_filter(stmt, Job, self._org_id)
        stmt = stmt.where(Job.status.notin_(TERMINAL_STATUSES))

        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def update_status(
        self,
        job_id: UUID,
        status: str,
        error_message: str | None = None,
        progress_percent: int | None = None,
    ) -> Job:
        """Update job status with optional progress/error information.

        Verifies tenant ownership before updating.

        Args:
            job_id: The job UUID.
            status: New status value.
            error_message: Error message (for failed status).
            progress_percent: Progress percentage (0-100).

        Returns:
            Updated Job instance.

        Raises:
            HTTPException: 404 if not found or cross-tenant.
        """
        job = await self.get_by_id(job_id)
        job.status = status

        if error_message is not None:
            job.error_message = error_message

        if progress_percent is not None:
            job.progress_percent = progress_percent

        if status in ("running",) and job.started_at is None:
            job.started_at = datetime.now(UTC)

        if status in ("completed", "failed", "cancelled"):
            job.completed_at = datetime.now(UTC)

        await self._db.flush()
        return job

    async def exists(self, job_id: UUID) -> bool:
        """Check if job exists for the authenticated org."""
        return await self._exists(Job, job_id)

    # =========================================================================
    # Job Leasing Operations (R21.3, R21.4, R21.5, R21.12, R64.2)
    # =========================================================================

    async def claim_next_job(
        self,
        worker_identity: str,
        lease_duration: timedelta = DEFAULT_LEASE_DURATION,
        workload_class: str | None = None,
    ) -> tuple[Job, JobLease] | None:
        """Atomically claim the next queued job using FOR UPDATE SKIP LOCKED.

        Selects the highest-priority queued job (optionally filtered by
        workload_class), locks it to prevent concurrent claims, transitions
        it to "claimed" status, and creates a JobLease record.

        This is the core atomic claiming operation per R64.2. The
        FOR UPDATE SKIP LOCKED clause ensures that concurrent workers
        never block each other — they simply skip already-locked rows.

        Args:
            worker_identity: Identifier for the claiming worker
                (hostname, instance ID, pod name, etc.).
            lease_duration: How long the lease is valid before expiration.
                Defaults to 30 minutes.
            workload_class: Optional filter to claim only jobs of a specific
                workload class (e.g., "image_generation", "training").

        Returns:
            Tuple of (Job, JobLease) if a job was claimed, None if no
            queued jobs are available.

        Validates: R21.3, R64.2
        """
        now = datetime.now(UTC)
        lease_expiration = now + lease_duration
        lease_token = uuid_mod.uuid4()

        # Build the claim query: select next queued job, highest priority first
        # FOR UPDATE SKIP LOCKED ensures atomicity without blocking
        stmt = (
            select(Job)
            .where(
                Job.org_id == self._org_id,
                Job.status == "queued",
            )
            .order_by(Job.priority.desc(), Job.created_at.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )

        if workload_class is not None:
            stmt = stmt.where(Job.workload_class == workload_class)

        result = await self._db.execute(stmt)
        job = result.scalar_one_or_none()

        if job is None:
            return None

        # Transition job to "claimed" status
        job.status = "claimed"
        job.attempts += 1

        # Create the lease record
        lease = JobLease(
            org_id=self._org_id,
            job_id=job.id,
            worker_identity=worker_identity,
            lease_token=lease_token,
            lease_expiration=lease_expiration,
            heartbeat_at=now,
        )
        self._db.add(lease)
        await self._db.flush()

        logger.info(
            "job_claimed",
            job_id=str(job.id),
            org_id=str(self._org_id),
            worker_identity=worker_identity,
            lease_expiration=lease_expiration.isoformat(),
            attempt=job.attempts,
            workload_class=job.workload_class,
        )

        return job, lease

    async def release_lease(
        self,
        job_id: UUID,
        lease_token: UUID,
        final_status: str = "completed",
        error_message: str | None = None,
        output_asset_ids: list[UUID] | None = None,
    ) -> Job:
        """Release a lease on job completion or failure.

        The caller must present the correct lease_token. If the token
        does not match the active lease, the request is rejected (stale
        worker rejection per R21.12).

        Args:
            job_id: The job UUID.
            lease_token: The secret token issued when the lease was created.
            final_status: Terminal status to set ("completed", "failed",
                "cancelled").
            error_message: Error message if status is "failed".
            output_asset_ids: UUIDs of output assets (for completed jobs).

        Returns:
            The updated Job instance.

        Raises:
            ValueError: If lease_token does not match the active lease
                (stale worker rejection).
            ValueError: If no active lease exists for this job.

        Validates: R21.12
        """
        # Find the active lease for this job and verify token
        lease = await self._get_active_lease(job_id)

        if lease is None:
            raise ValueError(
                f"No active lease found for job {job_id}. "
                "The lease may have expired."
            )

        if lease.lease_token != lease_token:
            logger.warning(
                "stale_worker_rejected",
                job_id=str(job_id),
                org_id=str(self._org_id),
                worker_identity=lease.worker_identity,
                reason="lease_token_mismatch",
            )
            raise ValueError(
                f"Invalid lease token for job {job_id}. "
                "Only the current lease holder may update job state."
            )

        # Get the job and update to final status
        job = await self.get_by_id(job_id)
        job.status = final_status
        job.completed_at = datetime.now(UTC)

        if error_message is not None:
            job.error_message = error_message

        if output_asset_ids is not None:
            job.output_asset_ids = output_asset_ids

        # Expire the lease (set expiration to now so partial index excludes it)
        lease.lease_expiration = datetime.now(UTC)

        await self._db.flush()

        logger.info(
            "lease_released",
            job_id=str(job_id),
            org_id=str(self._org_id),
            final_status=final_status,
            worker_identity=lease.worker_identity,
        )

        return job

    async def heartbeat(
        self,
        job_id: UUID,
        lease_token: UUID,
        extend_duration: timedelta = DEFAULT_LEASE_DURATION,
        progress_percent: int | None = None,
        progress_metadata: dict | None = None,
    ) -> JobLease:
        """Extend a lease via heartbeat signal.

        Workers must call heartbeat at intervals <= lease_duration / 3
        to prevent lease expiration. Each heartbeat extends the lease
        expiration by extend_duration from the current time.

        Also supports optional progress reporting per R21.13.

        Args:
            job_id: The job UUID.
            lease_token: The secret token issued when the lease was created.
            extend_duration: How much to extend the lease from now.
            progress_percent: Optional progress update (0-100).
            progress_metadata: Optional structured progress data.

        Returns:
            The updated JobLease instance.

        Raises:
            ValueError: If lease_token does not match (stale worker rejection).
            ValueError: If no active lease exists.

        Validates: R21.4, R21.5, R21.13
        """
        lease = await self._get_active_lease(job_id)

        if lease is None:
            raise ValueError(
                f"No active lease found for job {job_id}. "
                "The lease may have expired."
            )

        if lease.lease_token != lease_token:
            logger.warning(
                "heartbeat_rejected_stale_worker",
                job_id=str(job_id),
                org_id=str(self._org_id),
            )
            raise ValueError(
                f"Invalid lease token for job {job_id}. "
                "Heartbeat rejected — stale worker."
            )

        now = datetime.now(UTC)
        lease.heartbeat_at = now
        lease.lease_expiration = now + extend_duration

        # Update job progress if provided (R21.13)
        if (
            progress_percent is not None
            or progress_metadata is not None
        ):
            job = await self.get_by_id(job_id)
            if progress_percent is not None:
                job.progress_percent = progress_percent
            if progress_metadata is not None:
                job.progress_metadata = progress_metadata

        await self._db.flush()
        return lease

    async def expire_stale_leases(self) -> list[UUID]:
        """Find and expire leases past their expiration time.

        For each expired lease:
        - If attempts < max_attempts: mark job as "queued" (re-queue)
        - If attempts >= max_attempts: mark job as "failed"

        This is called periodically by a background process to recover
        from worker crashes/disconnections.

        Returns:
            List of job_ids that were expired and re-queued or failed.

        Validates: R21.5, R21.8, R21.9
        """
        now = datetime.now(UTC)
        expired_job_ids: list[UUID] = []

        # Find all expired leases for jobs in non-terminal status
        # within this org
        stmt = (
            select(JobLease)
            .join(Job, JobLease.job_id == Job.id)
            .where(
                JobLease.org_id == self._org_id,
                JobLease.lease_expiration <= now,
                Job.status.in_(("claimed", "running")),
            )
            .with_for_update(skip_locked=True)
        )

        result = await self._db.execute(stmt)
        expired_leases = list(result.scalars().all())

        for lease in expired_leases:
            # Load the associated job
            job_stmt = (
                select(Job)
                .where(Job.id == lease.job_id, Job.org_id == self._org_id)
                .with_for_update()
            )
            job_result = await self._db.execute(job_stmt)
            job = job_result.scalar_one_or_none()

            if job is None:
                continue

            if job.attempts >= job.max_attempts:
                # Max attempts reached — mark as failed
                job.status = "failed"
                job.error_message = (
                    f"Job failed after {job.attempts} attempts. "
                    f"Last lease expired without heartbeat from worker "
                    f"'{lease.worker_identity}'."
                )
                job.completed_at = now
                logger.warning(
                    "job_failed_max_attempts",
                    job_id=str(job.id),
                    org_id=str(self._org_id),
                    attempts=job.attempts,
                    max_attempts=job.max_attempts,
                    last_worker=lease.worker_identity,
                )
            else:
                # Re-queue for another attempt
                job.status = "queued"
                job.started_at = None
                logger.info(
                    "job_requeued_lease_expired",
                    job_id=str(job.id),
                    org_id=str(self._org_id),
                    attempts=job.attempts,
                    max_attempts=job.max_attempts,
                    last_worker=lease.worker_identity,
                )

            expired_job_ids.append(job.id)

        if expired_leases:
            await self._db.flush()

        return expired_job_ids

    # =========================================================================
    # Private Helpers
    # =========================================================================

    async def _get_active_lease(self, job_id: UUID) -> JobLease | None:
        """Get the active (non-expired) lease for a job within this org.

        Args:
            job_id: The job UUID.

        Returns:
            The active JobLease if one exists, None otherwise.
        """
        now = datetime.now(UTC)
        stmt = select(JobLease).where(
            JobLease.job_id == job_id,
            JobLease.org_id == self._org_id,
            JobLease.lease_expiration > now,
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

"""Job Service — business logic for job submission, leasing, and lifecycle.

Orchestrates job creation, atomic claiming via leases, heartbeat-based lease
extension, completion/failure handling, cancellation, and stale lease expiration.

The service delegates all database access to JobRepository, which enforces
tenant isolation via TenantScopedRepository.

Requirements: R21.1, R21.3, R21.4, R21.5, R21.8, R64.1, R64.3
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.core.logging import get_logger
from app.models.job import Job
from app.models.job_lease import JobLease
from app.repositories.job_repository import JobRepository
from app.schemas.job import JobCreate
from app.services.job_type_config import (
    JOB_TYPE_CONFIGS,
    validate_job_duration,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

# Default lease duration: 30 minutes
DEFAULT_LEASE_DURATION_SECONDS: int = 1800


class JobServiceError(Exception):
    """Base exception for JobService operations."""

    def __init__(self, message: str, code: str = "JOB_ERROR") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class JobNotCancellableError(JobServiceError):
    """Raised when attempting to cancel a job in a terminal state."""

    def __init__(self, job_id: UUID, current_status: str) -> None:
        super().__init__(
            message=(
                f"Job {job_id} cannot be cancelled — "
                f"current status is '{current_status}'"
            ),
            code="JOB_NOT_CANCELLABLE",
        )


class StaleWorkerError(JobServiceError):
    """Raised when a stale worker attempts to update a job."""

    def __init__(self, job_id: UUID) -> None:
        super().__init__(
            message=(
                f"Stale worker rejected for job {job_id}. "
                "Lease token does not match the active lease."
            ),
            code="STALE_WORKER",
        )


class NoActiveLeaseError(JobServiceError):
    """Raised when no active lease exists for a job operation."""

    def __init__(self, job_id: UUID) -> None:
        super().__init__(
            message=(
                f"No active lease found for job {job_id}. "
                "The lease may have expired."
            ),
            code="NO_ACTIVE_LEASE",
        )


class JobService:
    """Job lifecycle management service.

    Encapsulates business logic for the full job lifecycle:
    submit → claim → heartbeat → complete/fail/cancel.

    All operations are tenant-scoped via the repository layer.
    org_id is resolved from TenantContext, never from client input.

    Requirements: R21.1, R21.3, R21.4, R21.5, R21.8, R64.1, R64.3
    """

    def __init__(self, db: "AsyncSession", org_id: UUID) -> None:
        """Initialize the JobService with a DB session and org_id.

        Args:
            db: SQLAlchemy async session.
            org_id: Authenticated org UUID from TenantContext.
        """
        self._db = db
        self._org_id = org_id
        self._repo = JobRepository(db=db, org_id=org_id)

    async def submit_job(
        self, create_schema: JobCreate, user_id: UUID
    ) -> Job:
        """Submit a new job for processing.

        Creates a job record with status "queued". If an idempotency_key
        is provided, checks for an existing non-terminal job first and
        returns it instead of creating a duplicate (R21.11).

        Race condition handling: If two concurrent requests with the same
        idempotency_key both pass the initial check, the DB partial unique
        index (ix_jobs_org_idempotency_key) catches the duplicate. The
        IntegrityError is caught here and we retry the lookup to return
        the winning row.

        Args:
            create_schema: Validated job creation parameters.
            user_id: The authenticated user submitting the job.

        Returns:
            The created (or existing) Job instance with status "queued".

        Validates: R21.1, R21.11, R64.1
        """
        # Check idempotency_key for deduplication
        if create_schema.idempotency_key:
            existing = await self._repo.find_by_idempotency_key(
                create_schema.idempotency_key
            )
            if existing is not None:
                logger.info(
                    "job_submit_idempotent_hit",
                    job_id=str(existing.id),
                    org_id=str(self._org_id),
                    idempotency_key=create_schema.idempotency_key,
                )
                return existing

        # Resolve job type configuration for defaults (R64.4)
        job_type_str = create_schema.job_type.value
        type_config = JOB_TYPE_CONFIGS.get(job_type_str)

        # Auto-set workload_class from config if not provided by client
        if create_schema.workload_class:
            workload_class = create_schema.workload_class.value
        elif type_config is not None:
            workload_class = type_config.workload_class
        else:
            workload_class = None

        # Validate/clamp max_duration_seconds to type's maximum
        if type_config is not None:
            max_duration_seconds = validate_job_duration(
                job_type_str, create_schema.max_duration_seconds
            )
            max_attempts = type_config.retry_policy.max_attempts
        else:
            max_duration_seconds = create_schema.max_duration_seconds
            max_attempts = 3

        # Create the job — handle race condition on idempotency_key
        try:
            job = await self._repo.create(
                job_type=job_type_str,
                status="queued",
                priority=create_schema.priority,
                idempotency_key=create_schema.idempotency_key,
                workload_class=workload_class,
                max_duration_seconds=max_duration_seconds,
                max_attempts=max_attempts,
                talent_id=create_schema.talent_id,
                user_id=user_id,
                parameters=create_schema.parameters,
            )
        except IntegrityError as exc:
            # Race condition: another request inserted with the same
            # idempotency_key between our check and our insert.
            # Roll back the failed flush and return the existing job.
            if create_schema.idempotency_key and "ix_jobs_org_idempotency_key" in str(exc):
                await self._db.rollback()
                existing = await self._repo.find_by_idempotency_key(
                    create_schema.idempotency_key
                )
                if existing is not None:
                    logger.info(
                        "job_submit_idempotent_race_resolved",
                        job_id=str(existing.id),
                        org_id=str(self._org_id),
                        idempotency_key=create_schema.idempotency_key,
                    )
                    return existing
            # Not an idempotency conflict — re-raise
            raise

        logger.info(
            "job_submitted",
            job_id=str(job.id),
            org_id=str(self._org_id),
            user_id=str(user_id),
            job_type=create_schema.job_type.value,
            priority=create_schema.priority,
        )

        return job

    async def claim_job(
        self,
        worker_identity: str,
        lease_duration_seconds: int | None = None,
        workload_class: str | None = None,
    ) -> tuple[Job, JobLease] | None:
        """Atomically claim the next queued job for a worker.

        Uses FOR UPDATE SKIP LOCKED to prevent concurrent claims.
        Transitions the job from "queued" to "claimed" and creates
        a JobLease record with a unique lease_token.

        If lease_duration_seconds is not provided, uses the type-specific
        configuration from JOB_TYPE_CONFIGS (R64.4). Falls back to the
        global default of 1800 seconds if no type config is found.

        Args:
            worker_identity: Identifier for the claiming worker.
            lease_duration_seconds: Override lease validity in seconds.
                If None, uses the claimed job's type-specific config.
            workload_class: Optional filter for specific workload types.

        Returns:
            Tuple of (Job, JobLease) if a job was claimed, None if no
            queued jobs are available.

        Validates: R21.3, R64.2, R64.4
        """
        # If caller specifies a duration, use it. Otherwise we'll use
        # type-specific config after claiming (repo needs a duration upfront,
        # so we pass the default and let the type-specific lookup happen
        # inside the repo layer, or we handle it here).
        # Strategy: use the workload_class to determine the lease duration
        # before claiming. If workload_class is specified, look up config.
        if lease_duration_seconds is not None:
            lease_duration = timedelta(seconds=lease_duration_seconds)
        elif workload_class is not None:
            # Find config by workload_class match
            matched_config = None
            for cfg in JOB_TYPE_CONFIGS.values():
                if cfg.workload_class == workload_class:
                    matched_config = cfg
                    break
            if matched_config is not None:
                lease_duration = matched_config.lease_duration
            else:
                lease_duration = timedelta(seconds=DEFAULT_LEASE_DURATION_SECONDS)
        else:
            lease_duration = timedelta(seconds=DEFAULT_LEASE_DURATION_SECONDS)

        result = await self._repo.claim_next_job(
            worker_identity=worker_identity,
            lease_duration=lease_duration,
            workload_class=workload_class,
        )

        return result

    async def heartbeat(
        self,
        job_id: UUID,
        lease_token: UUID,
        progress_percent: int | None = None,
        progress_message: str | None = None,
        progress_metadata: dict | None = None,
    ) -> JobLease:
        """Extend a lease via heartbeat signal.

        Workers must call heartbeat at intervals <= lease_duration / 3
        to prevent lease expiration. Each heartbeat extends the lease
        from the current time.

        Args:
            job_id: The job UUID.
            lease_token: The secret token issued when the lease was created.
            progress_percent: Optional progress update (0-100).
            progress_message: Optional human-readable progress message.
            progress_metadata: Optional structured progress data (R21.13).

        Returns:
            The updated JobLease with extended expiration.

        Raises:
            StaleWorkerError: If lease_token does not match active lease.
            NoActiveLeaseError: If no active lease exists.

        Validates: R21.4, R21.5, R21.13
        """
        try:
            lease = await self._repo.heartbeat(
                job_id=job_id,
                lease_token=lease_token,
                progress_percent=progress_percent,
                progress_message=progress_message,
                progress_metadata=progress_metadata,
            )
            return lease
        except ValueError as exc:
            msg = str(exc)
            if "Invalid lease token" in msg:
                raise StaleWorkerError(job_id) from exc
            raise NoActiveLeaseError(job_id) from exc

    async def complete_job(
        self,
        job_id: UUID,
        lease_token: UUID,
        cost_usd: float | None = None,
        output_asset_ids: list[UUID] | None = None,
    ) -> Job:
        """Mark a job as completed and release the lease.

        The caller must present the correct lease_token. Stale workers
        (with an expired lease) are rejected.

        Args:
            job_id: The job UUID.
            lease_token: The secret token from lease creation.
            cost_usd: Actual cost of job execution.
            output_asset_ids: UUIDs of generated output assets.

        Returns:
            The updated Job with status "completed".

        Raises:
            StaleWorkerError: If lease_token does not match.
            NoActiveLeaseError: If no active lease exists.

        Validates: R21.8
        """
        try:
            job = await self._repo.release_lease(
                job_id=job_id,
                lease_token=lease_token,
                final_status="completed",
                cost_usd=cost_usd,
                output_asset_ids=output_asset_ids,
            )

            logger.info(
                "job_completed",
                job_id=str(job_id),
                org_id=str(self._org_id),
                cost_usd=cost_usd,
            )

            return job
        except ValueError as exc:
            msg = str(exc)
            if "Invalid lease token" in msg:
                raise StaleWorkerError(job_id) from exc
            raise NoActiveLeaseError(job_id) from exc

    async def fail_job(
        self,
        job_id: UUID,
        lease_token: UUID,
        error_message: str,
    ) -> Job:
        """Mark a job as failed and release the lease.

        The caller must present the correct lease_token. Records the
        error message for debugging and audit.

        Args:
            job_id: The job UUID.
            lease_token: The secret token from lease creation.
            error_message: Human-readable failure description.

        Returns:
            The updated Job with status "failed".

        Raises:
            StaleWorkerError: If lease_token does not match.
            NoActiveLeaseError: If no active lease exists.
        """
        try:
            job = await self._repo.release_lease(
                job_id=job_id,
                lease_token=lease_token,
                final_status="failed",
                error_message=error_message,
            )

            logger.warning(
                "job_failed",
                job_id=str(job_id),
                org_id=str(self._org_id),
                error_message=error_message,
            )

            return job
        except ValueError as exc:
            msg = str(exc)
            if "Invalid lease token" in msg:
                raise StaleWorkerError(job_id) from exc
            raise NoActiveLeaseError(job_id) from exc

    async def cancel_job(self, job_id: UUID) -> Job:
        """Cancel a job, revoking any active lease.

        Only non-terminal jobs can be cancelled. If the job has an active
        lease, the lease is expired (set expiration to now) so the worker
        is rejected on next heartbeat/completion attempt.

        Cancellation signal mechanism (R21.6):
        Since the job leasing system uses a polling-based heartbeat model,
        "signal the worker to stop" is implemented by expiring the active
        lease. The worker discovers the cancellation on its next heartbeat
        attempt (which returns 409 Conflict / NoActiveLeaseError), at which
        point it must cease work. There is no push-based interrupt — the
        heartbeat interval (max lease_duration / 3) bounds worst-case
        notification latency.

        Args:
            job_id: The job UUID to cancel.

        Returns:
            The updated Job with status "cancelled".

        Raises:
            JobNotCancellableError: If the job is in a terminal state.

        Validates: R21.6
        """
        job = await self._repo.get_by_id(job_id)

        terminal_statuses = {"completed", "failed", "cancelled"}
        if job.status in terminal_statuses:
            raise JobNotCancellableError(
                job_id=job_id, current_status=job.status
            )

        # Expire any active lease so worker is rejected on next contact
        active_lease = await self._repo._get_active_lease(job_id)
        if active_lease is not None:
            from datetime import UTC, datetime

            active_lease.lease_expiration = datetime.now(UTC)

        # Update job status to cancelled
        job = await self._repo.update_status(
            job_id=job_id,
            status="cancelled",
        )

        logger.info(
            "job_cancelled",
            job_id=str(job_id),
            org_id=str(self._org_id),
            had_active_lease=active_lease is not None,
        )

        return job

    async def expire_stale_leases(self) -> list[UUID]:
        """Find and expire leases past their expiration time.

        For each expired lease:
        - If attempt_count < max_attempts: re-queue the job
        - If attempt_count >= max_attempts: mark as failed

        This should be called periodically by a background process.

        Returns:
            List of job_ids that were expired and re-queued or failed.

        Validates: R21.5, R21.8, R21.9
        """
        expired_ids = await self._repo.expire_stale_leases()

        if expired_ids:
            logger.info(
                "stale_leases_expired",
                org_id=str(self._org_id),
                count=len(expired_ids),
                job_ids=[str(jid) for jid in expired_ids],
            )

        return expired_ids

    async def get_job(self, job_id: UUID) -> Job:
        """Get a single job by ID, scoped to the authenticated org.

        Args:
            job_id: The job UUID.

        Returns:
            The Job instance.

        Raises:
            HTTPException: 404 if not found or cross-tenant.
        """
        return await self._repo.get_by_id(job_id)

    async def list_jobs(
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
            Tuple of (items, total_count).
        """
        return await self._repo.list_all(
            limit=limit,
            offset=offset,
            status=status,
            job_type=job_type,
            talent_id=talent_id,
        )

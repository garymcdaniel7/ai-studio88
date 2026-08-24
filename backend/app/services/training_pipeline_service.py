"""Training Pipeline Service — LoRA training job lifecycle management.

Orchestrates training job submission, cost estimation, completion handling
(model record creation + talent association), cancellation, and timeout enforcement.

The service integrates with:
    - DatasetManifestService: manifest integrity verification before training
    - JobService: job leasing and lifecycle management
    - CostService: cost reservation and reconciliation
    - ModelRegistryEntry: model record creation on completion
    - TalentLora: talent ↔ LoRA association on completion

Requirements: R35.1, R35.2, R35.3, R35.4, R35.5, R35.6, R35.7, R35.8, R35.10, R35.11
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select

from app.core.logging import get_logger
from app.models.dataset_manifest import DatasetManifest
from app.models.model_lifecycle import ModelRegistryEntry, ModelTransition
from app.models.talent import AiTalent
from app.models.talent_lora import TalentLora
from app.schemas.training import (
    TrainingEstimateResponse,
    TrainingJobCreate,
    TrainingJobStatus,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.dependencies import TenantContext

logger = get_logger(__name__)

# Training job timeout: 4 hours (R35.7)
TRAINING_TIMEOUT_SECONDS: int = 14400


# Default hourly GPU rate for cost estimation
DEFAULT_HOURLY_RATE_USD: float = 1.50


class TrainingPipelineError(Exception):
    """Base exception for training pipeline operations."""

    def __init__(self, message: str, code: str = "TRAINING_ERROR") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class ManifestInvalidError(TrainingPipelineError):
    """Raised when the dataset manifest fails verification."""

    def __init__(self, manifest_id: UUID, reason: str) -> None:
        super().__init__(
            message=f"Dataset manifest {manifest_id} is invalid: {reason}",
            code="MANIFEST_INVALID",
        )


class ImageCountError(TrainingPipelineError):
    """Raised when image count is outside 10-200 range (R35.10)."""

    def __init__(self, count: int) -> None:
        super().__init__(
            message=(
                f"Training requires 10-200 images, got {count}. "
                "Adjust your dataset manifest."
            ),
            code="INVALID_IMAGE_COUNT",
        )


class TrainingNotCancellableError(TrainingPipelineError):
    """Raised when a training job cannot be cancelled (R35.6)."""

    def __init__(self, job_id: UUID, current_status: str) -> None:
        super().__init__(
            message=(
                f"Training job {job_id} cannot be cancelled — "
                f"status is '{current_status}' (only queued/running jobs can be cancelled)"
            ),
            code="TRAINING_NOT_CANCELLABLE",
        )


class TrainingJob:
    """In-memory representation of a training job record.

    This wraps the jobs table row with training-specific semantics.
    Training jobs are stored in the same `jobs` table as other job types
    but with job_type='lora_training' and training-specific parameters.
    """

    def __init__(self, job_row: object) -> None:
        self._job = job_row

    @property
    def id(self) -> UUID:
        return self._job.id

    @property
    def org_id(self) -> UUID:
        return self._job.org_id

    @property
    def status(self) -> str:
        return self._job.status

    @property
    def talent_id(self) -> UUID | None:
        return self._job.talent_id

    @property
    def parameters(self) -> dict:
        return self._job.parameters or {}

    @property
    def manifest_id(self) -> UUID | None:
        params = self.parameters
        mid = params.get("manifest_id")
        if mid:
            return UUID(mid) if isinstance(mid, str) else mid
        return None

    @property
    def model_id(self) -> UUID | None:
        params = self.parameters
        mid = params.get("model_id")
        if mid:
            return UUID(mid) if isinstance(mid, str) else mid
        return None

    @property
    def base_model(self) -> str:
        return self.parameters.get("base_model", "flux-dev")

    @property
    def trigger_word(self) -> str:
        return self.parameters.get("trigger_word", "ohwx")

    @property
    def steps(self) -> int:
        return self.parameters.get("steps", 1000)

    @property
    def rank(self) -> int:
        return self.parameters.get("rank", 16)

    @property
    def learning_rate(self) -> float:
        return self.parameters.get("learning_rate", 1e-4)

    @property
    def resolution(self) -> int:
        return self.parameters.get("resolution", 1024)


class TrainingPipelineService:
    """Training pipeline lifecycle management.

    Handles:
        - Job submission with manifest verification (R35.1)
        - Cost estimation (R35.2)
        - Job completion: model record + talent_loras association (R35.4, R35.11)
        - Cancellation for queued/running jobs (R35.5, R35.6)
        - 4-hour timeout enforcement (R35.7)

    All operations are tenant-scoped via TenantContext.
    """

    def __init__(self, db: "AsyncSession", tenant: "TenantContext") -> None:
        """Initialize with database session and tenant context.

        Args:
            db: SQLAlchemy async session.
            tenant: Authenticated TenantContext (never client-supplied).
        """
        self._db = db
        self._tenant = tenant

    async def submit_training_job(
        self,
        data: TrainingJobCreate,
    ) -> object:
        """Submit a new LoRA training job.

        Steps:
            1. Validate talent exists and belongs to this org
            2. Validate manifest exists, belongs to this org, and is valid
            3. Validate image count is 10-200 (R35.10)
            4. Create a job record with status "queued"
            5. Return 202 Accepted

        Args:
            data: Validated training job creation request.

        Returns:
            The created Job ORM instance.

        Raises:
            HTTPException 404: If talent or manifest not found.
            HTTPException 422: If image count outside 10-200 range.
            HTTPException 409: If idempotent job already exists.

        Validates: R35.1, R35.10
        """
        # 1. Validate talent exists and belongs to this org
        await self._validate_talent(data.talent_id)

        # 2. Validate manifest exists and is valid
        manifest = await self._validate_manifest(data.manifest_id)

        # 3. Validate image count: 10-200 (R35.10)
        image_count = manifest.total_file_count
        if image_count < 10 or image_count > 200:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Training requires 10-200 images, got {image_count}. "
                    "Adjust your dataset manifest."
                ),
            )

        # 4. Check idempotency
        if data.idempotency_key:
            existing = await self._find_by_idempotency_key(data.idempotency_key)
            if existing is not None:
                logger.info(
                    "training_job_idempotent_hit",
                    job_id=str(existing.id),
                    org_id=str(self._tenant.org_id),
                    idempotency_key=data.idempotency_key,
                )
                return existing

        # 5. Create the job record via the jobs table
        from app.models.job import Job

        job = Job(
            org_id=self._tenant.org_id,
            type="lora_training",
            status="queued",
            priority=5,
            idempotency_key=data.idempotency_key,
            workload_class="training",
            max_attempts=2,
            talent_id=data.talent_id,
            parameters={
                "manifest_id": str(data.manifest_id),
                "base_model": data.base_model.value,
                "trigger_word": data.trigger_word,
                "steps": data.steps,
                "rank": data.rank,
                "learning_rate": data.learning_rate,
                "resolution": data.resolution,
            },
        )
        self._db.add(job)
        await self._db.flush()
        await self._db.refresh(job)

        logger.info(
            "training_job_submitted",
            job_id=str(job.id),
            org_id=str(self._tenant.org_id),
            talent_id=str(data.talent_id),
            manifest_id=str(data.manifest_id),
            base_model=data.base_model.value,
            steps=data.steps,
        )

        return job

    async def estimate_cost(
        self,
        base_model: str,
        steps: int,
        resolution: int,
        image_count: int,
    ) -> TrainingEstimateResponse:
        """Estimate training cost before submission.

        Uses heuristics based on model type, resolution, steps, and
        current GPU provider rates.

        Args:
            base_model: The base model identifier.
            steps: Number of training steps.
            resolution: Training resolution in pixels.
            image_count: Number of images in dataset.

        Returns:
            Cost estimation with time and dollar estimates.

        Validates: R35.2
        """
        hourly_rate = float(
            os.getenv("VAST_MAX_PRICE_PER_HOUR", str(DEFAULT_HOURLY_RATE_USD))
        )

        # Estimate steps per second based on model and resolution
        if "flux" in base_model:
            # Flux models are slower due to larger architecture
            if resolution >= 1024:
                steps_per_second = 0.3
            else:
                steps_per_second = 0.5
        else:
            # SDXL/SD1.5 are faster
            if resolution >= 1024:
                steps_per_second = 0.5
            else:
                steps_per_second = 1.0

        # Account for dataset size impact (more images = more repeats per step)
        dataset_factor = 1.0 + (image_count / 200) * 0.3

        estimated_seconds = int((steps / steps_per_second) * dataset_factor)
        # Add overhead: provisioning (~120s) + model download (~180s)
        estimated_seconds += 300

        estimated_cost = (estimated_seconds / 3600) * hourly_rate

        return TrainingEstimateResponse(
            base_model=base_model,
            steps=steps,
            resolution=resolution,
            image_count=image_count,
            estimated_time_seconds=estimated_seconds,
            estimated_cost_usd=round(estimated_cost, 2),
            hourly_rate_usd=hourly_rate,
            gpu_type="RTX 4090",
            note="Estimate based on current provider rates. Actual cost may vary.",
        )

    async def complete_training_job(
        self,
        job_id: UUID,
        model_name: str,
        storage_key: str,
        checksum_sha256: str,
        file_size_bytes: int,
        cost_usd: float | None = None,
    ) -> object:
        """Handle training job completion — create model record and talent association.

        On successful training:
            1. Create a ModelRegistryEntry with provenance (R35.4)
            2. Create a TalentLora association (type=identity, strength=0.7, always_on=True) (R35.11)
            3. Update job status to "completed"

        This method is called by the worker after training finishes successfully.
        Instance termination happens in the finally block of the worker (R35.8).

        Args:
            job_id: The training job UUID.
            model_name: Human-readable name for the trained model.
            storage_key: B2 storage key for the LoRA file.
            checksum_sha256: SHA-256 hash of the LoRA file.
            file_size_bytes: Size of the LoRA file in bytes.
            cost_usd: Actual GPU cost incurred.

        Returns:
            The updated Job instance.

        Raises:
            HTTPException 404: If job not found or cross-tenant.

        Validates: R35.4, R35.11
        """
        from app.models.job import Job

        # Get the job
        job = await self._get_job(job_id)

        # Extract training parameters
        params = job.parameters or {}
        talent_id = job.talent_id
        base_model = params.get("base_model", "flux-dev")
        trigger_word = params.get("trigger_word", "ohwx")
        manifest_id = params.get("manifest_id")

        # 1. Create model registry entry with provenance (R35.4)
        model_entry = ModelRegistryEntry(
            org_id=self._tenant.org_id,
            name=model_name,
            model_type="lora",
            lifecycle_state="trained",
            risk_class="standard",
            base_model_id=base_model,
            checksum_sha256=checksum_sha256,
            storage_key=storage_key,
            file_size_bytes=file_size_bytes,
            metadata_={
                "source": "user_trained",
                "base_model": base_model,
                "trigger_word": trigger_word,
                "training_job_id": str(job_id),
                "manifest_id": manifest_id,
                "training_parameters": {
                    "steps": params.get("steps", 1000),
                    "rank": params.get("rank", 16),
                    "learning_rate": params.get("learning_rate", 1e-4),
                    "resolution": params.get("resolution", 1024),
                },
            },
        )
        self._db.add(model_entry)
        await self._db.flush()
        await self._db.refresh(model_entry)

        # Record model transition
        transition = ModelTransition(
            org_id=self._tenant.org_id,
            model_id=model_entry.id,
            from_state="none",
            to_state="trained",
            actor=f"training_pipeline:job:{job_id}",
            actor_type="system",
            risk_class="standard",
            evidence={
                "training_job_id": str(job_id),
                "manifest_id": manifest_id,
                "checksum": checksum_sha256,
            },
            gate_checks_performed=["training_completion"],
            gate_checks_passed=["training_completion"],
            success=True,
        )
        self._db.add(transition)

        # 2. Create talent_loras association (R35.11)
        if talent_id:
            talent_lora = TalentLora(
                org_id=self._tenant.org_id,
                talent_id=talent_id,
                lora_model_id=model_entry.id,
                type="identity",
                strength=0.7,
                always_on=True,
            )
            self._db.add(talent_lora)

        # 3. Update job to completed
        job.status = "completed"
        job.completed_at = datetime.now(UTC)
        job.output_asset_ids = [model_entry.id]
        # Store model_id in parameters for retrieval
        params["model_id"] = str(model_entry.id)
        job.parameters = params

        await self._db.flush()

        logger.info(
            "training_job_completed",
            job_id=str(job_id),
            org_id=str(self._tenant.org_id),
            model_id=str(model_entry.id),
            talent_id=str(talent_id) if talent_id else None,
            cost_usd=cost_usd,
        )

        return job

    async def cancel_training_job(self, job_id: UUID) -> object:
        """Cancel a training job (R35.5, R35.6).

        Only queued or running jobs can be cancelled.
        Completed/failed/cancelled jobs return 409.

        Args:
            job_id: The training job UUID.

        Returns:
            The updated Job instance.

        Raises:
            HTTPException 404: If job not found or cross-tenant.
            HTTPException 409: If job is in a terminal state (R35.6).

        Validates: R35.5, R35.6
        """
        from app.models.job import Job

        job = await self._get_job(job_id)

        cancellable_statuses = {"queued", "provisioning", "running", "claimed"}
        if job.status not in cancellable_statuses:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Training job {job_id} cannot be cancelled — "
                    f"current status is '{job.status}'"
                ),
            )

        job.status = "cancelled"
        job.completed_at = datetime.now(UTC)
        # Store cancellation timestamp in parameters
        params = job.parameters or {}
        params["cancelled_at"] = datetime.now(UTC).isoformat()
        params["cancelled_by"] = str(self._tenant.user_id)
        job.parameters = params

        await self._db.flush()

        logger.info(
            "training_job_cancelled",
            job_id=str(job_id),
            org_id=str(self._tenant.org_id),
            previous_status=job.status,
        )

        return job

    async def fail_training_job(
        self,
        job_id: UUID,
        error_message: str,
        timed_out: bool = False,
    ) -> object:
        """Mark a training job as failed.

        Called by the worker when training fails or times out (R35.7).
        Instance termination happens in the worker's finally block (R35.8).

        Args:
            job_id: The training job UUID.
            error_message: Human-readable failure description.
            timed_out: If True, sets status to "timed_out" instead of "failed".

        Returns:
            The updated Job instance.

        Validates: R35.7, R35.8
        """
        from app.models.job import Job

        job = await self._get_job(job_id)

        job.status = "timed_out" if timed_out else "failed"
        job.error_message = error_message
        job.completed_at = datetime.now(UTC)

        await self._db.flush()

        log_fn = logger.warning if not timed_out else logger.error
        log_fn(
            "training_job_failed",
            job_id=str(job_id),
            org_id=str(self._tenant.org_id),
            timed_out=timed_out,
            error_message=error_message,
        )

        return job

    async def get_training_job(self, job_id: UUID) -> object:
        """Get a training job by ID, scoped to authenticated org.

        Args:
            job_id: The job UUID.

        Returns:
            The Job instance.

        Raises:
            HTTPException 404: If not found or cross-tenant.
        """
        return await self._get_job(job_id)

    async def list_training_jobs(
        self,
        limit: int = 20,
        offset: int = 0,
        talent_id: UUID | None = None,
        job_status: str | None = None,
    ) -> tuple[list, int]:
        """List training jobs for this org with optional filters.

        Args:
            limit: Maximum items per page (1-100).
            offset: Pagination offset.
            talent_id: Filter by associated talent.
            job_status: Filter by job status.

        Returns:
            Tuple of (items, total_count).
        """
        from app.models.job import Job

        base_filter = [
            Job.org_id == self._tenant.org_id,
            Job.type == "lora_training",
        ]
        if talent_id:
            base_filter.append(Job.talent_id == talent_id)
        if job_status:
            base_filter.append(Job.status == job_status)

        # Count
        count_stmt = (
            select(func.count()).select_from(Job).where(*base_filter)
        )
        total = await self._db.scalar(count_stmt) or 0

        # Items
        stmt = (
            select(Job)
            .where(*base_filter)
            .order_by(Job.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._db.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    # =========================================================================
    # Internal Validation Methods
    # =========================================================================

    async def _validate_talent(self, talent_id: UUID) -> AiTalent:
        """Verify talent exists and belongs to this org.

        Raises:
            HTTPException 404: If talent not found or cross-tenant.
        """
        stmt = select(AiTalent).where(
            AiTalent.id == talent_id,
            AiTalent.org_id == self._tenant.org_id,
        )
        result = await self._db.execute(stmt)
        talent = result.scalar_one_or_none()

        if talent is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Talent {talent_id} not found in this workspace",
            )

        if hasattr(talent, "deleted_at") and talent.deleted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Talent {talent_id} has been deleted",
            )

        return talent

    async def _validate_manifest(self, manifest_id: UUID) -> DatasetManifest:
        """Verify manifest exists, belongs to this org, and is valid.

        Raises:
            HTTPException 404: If manifest not found.
            HTTPException 422: If manifest is invalid (files deleted, consent revoked).
        """
        stmt = select(DatasetManifest).where(
            DatasetManifest.id == manifest_id,
            DatasetManifest.org_id == self._tenant.org_id,
        )
        result = await self._db.execute(stmt)
        manifest = result.scalar_one_or_none()

        if manifest is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dataset manifest {manifest_id} not found",
            )

        if not manifest.is_valid:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Dataset manifest {manifest_id} is invalid: "
                    f"{manifest.invalidation_reason or 'files deleted or consent revoked'}"
                ),
            )

        return manifest

    async def _get_job(self, job_id: UUID) -> object:
        """Get a training job by ID, scoped to this org.

        Raises:
            HTTPException 404: If not found or cross-tenant or wrong type.
        """
        from app.models.job import Job

        stmt = select(Job).where(
            Job.id == job_id,
            Job.org_id == self._tenant.org_id,
            Job.type == "lora_training",
        )
        result = await self._db.execute(stmt)
        job = result.scalar_one_or_none()

        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Training job not found",
            )

        return job

    async def _find_by_idempotency_key(self, key: str) -> object | None:
        """Find an existing non-terminal training job by idempotency key."""
        from app.models.job import Job

        terminal = {"completed", "failed", "cancelled", "timed_out"}
        stmt = select(Job).where(
            Job.org_id == self._tenant.org_id,
            Job.type == "lora_training",
            Job.idempotency_key == key,
            Job.status.notin_(terminal),
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

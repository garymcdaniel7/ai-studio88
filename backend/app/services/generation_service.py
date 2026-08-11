"""Generation Service — orchestrates image generation job submission.

Handles the full lifecycle of generation request intake:
    - Validates inputs (prompt length, dimensions, model, talent ownership)
    - Creates a job record with status "queued" via JobService
    - Optionally resolves a GenerationContextPackage
    - Returns 202 with job ID within 2 seconds

Retry configuration for dispatched jobs:
    - Workflow errors (bad JSON, missing model) → fail immediately, no retry
    - Transient infrastructure errors → retry 3x with backoff (10s, 20s, 40s)
    - Timeout (30 min default) → fail, terminate instance

Requirements: R12.1, R12.2, R12.3, R12.6, R12.7, R12.8, R12.9, R12.10
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import HTTPException, status

from app.core.logging import get_logger
from app.schemas.generation import GenerationModel, ImageGenerateRequest
from app.schemas.job import JobCreate
from app.schemas.validation import JobType, WorkloadClass

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.dependencies import TenantContext
    from app.models.job import Job

logger = get_logger(__name__)


# =============================================================================
# Retry Configuration (R12.8, R12.9)
# =============================================================================

# Transient error retry backoff sequence in seconds
TRANSIENT_RETRY_BACKOFF_SECONDS: list[int] = [10, 20, 40]

# Maximum number of retry attempts for transient errors
MAX_TRANSIENT_RETRIES: int = 3

# Default timeout before marking a generation job as failed (R12.6)
DEFAULT_GENERATION_TIMEOUT_SECONDS: int = 1800  # 30 minutes


# =============================================================================
# Exceptions
# =============================================================================


class GenerationServiceError(Exception):
    """Base exception for GenerationService operations."""

    def __init__(self, message: str, code: str = "GENERATION_ERROR") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class WorkflowError(GenerationServiceError):
    """Raised for workflow errors — do NOT retry (bad JSON, missing model).

    Validates: R12.8
    """

    def __init__(self, message: str) -> None:
        super().__init__(message=message, code="WORKFLOW_ERROR")


class TransientError(GenerationServiceError):
    """Raised for transient infrastructure errors — retry with backoff.

    Validates: R12.9
    """

    def __init__(self, message: str) -> None:
        super().__init__(message=message, code="TRANSIENT_ERROR")


# =============================================================================
# VRAM Requirements per Model
# =============================================================================

MODEL_VRAM_REQUIREMENTS: dict[GenerationModel, int] = {
    GenerationModel.FLUX_DEV: 12,
    GenerationModel.SDXL_TURBO: 8,
    GenerationModel.SD15: 8,
}


# =============================================================================
# Service
# =============================================================================


class GenerationService:
    """Service for orchestrating image generation job submission.

    Responsibilities:
        - Validate generation request inputs (R12.1)
        - Verify talent_id ownership if provided (R12.11)
        - Create a job with status "queued" (R12.1)
        - Return 202 with job_id within 2 seconds (R12.1)

    The actual dispatch to ComputeProvider and ComfyUI is handled by
    the worker layer (job claiming). This service handles intake only.

    Requirements: R12.1, R12.2, R12.3, R12.6, R12.7, R12.8, R12.9, R12.10
    """

    def __init__(self, db: "AsyncSession", tenant: "TenantContext") -> None:
        """Initialize the GenerationService.

        Args:
            db: SQLAlchemy async session.
            tenant: Authenticated TenantContext (never client-supplied).
        """
        self._db = db
        self._tenant = tenant

    async def submit_image_generation(
        self,
        request: ImageGenerateRequest,
    ) -> "Job":
        """Submit an image generation request.

        Creates a job record with status "queued" and returns it.
        The endpoint wraps this and returns HTTP 202.

        Flow:
            1. Validate talent_id ownership (if provided)
            2. Build job parameters
            3. Create job via JobService
            4. Return job (caller extracts job_id for response)

        Args:
            request: Validated ImageGenerateRequest schema.

        Returns:
            The created Job instance with status "queued".

        Raises:
            HTTPException 403: If talent_id belongs to another org.
            HTTPException 422: If inputs are invalid.

        Validates: R12.1, R12.2, R12.11
        """
        # Validate talent ownership if talent_id provided (R12.11)
        if request.talent_id is not None:
            await self._validate_talent_ownership(request.talent_id)

        # Build job parameters for dispatch
        parameters = self._build_job_parameters(request)

        # Create job via JobService (R12.1 — status "queued")
        from app.services.job_service import JobService

        job_service = JobService(db=self._db, org_id=self._tenant.org_id)

        job_create = JobCreate(
            job_type=JobType.IMAGE_GENERATION,
            talent_id=request.talent_id,
            parameters=parameters,
            priority=5,
            workload_class=WorkloadClass.IMAGE_GENERATION,
            max_duration_seconds=DEFAULT_GENERATION_TIMEOUT_SECONDS,
        )

        job = await job_service.submit_job(
            create_schema=job_create,
            user_id=self._tenant.user_id,
        )

        logger.info(
            "image_generation_submitted",
            job_id=str(job.id),
            org_id=str(self._tenant.org_id),
            user_id=str(self._tenant.user_id),
            model=request.model.value,
            width=request.width,
            height=request.height,
        )

        return job

    def get_retry_config(self) -> dict:
        """Return retry configuration for generation jobs.

        Returns a dict describing the retry strategy:
            - Workflow errors: no retry (fail immediately)
            - Transient errors: retry with backoff [10s, 20s, 40s]
            - Timeout: 30 minutes → fail and terminate

        Validates: R12.8, R12.9, R12.6
        """
        return {
            "max_retries": MAX_TRANSIENT_RETRIES,
            "backoff_seconds": TRANSIENT_RETRY_BACKOFF_SECONDS,
            "timeout_seconds": DEFAULT_GENERATION_TIMEOUT_SECONDS,
            "workflow_error_retry": False,
            "transient_error_retry": True,
        }

    def compute_retry_delay(self, attempt: int) -> int | None:
        """Compute the retry delay for a given attempt number.

        Args:
            attempt: The current attempt number (0-indexed).

        Returns:
            Delay in seconds, or None if no more retries allowed.

        Validates: R12.9
        """
        if attempt >= MAX_TRANSIENT_RETRIES:
            return None
        if attempt < len(TRANSIENT_RETRY_BACKOFF_SECONDS):
            return TRANSIENT_RETRY_BACKOFF_SECONDS[attempt]
        return None

    def get_vram_requirement(self, model: GenerationModel) -> int:
        """Get minimum VRAM requirement for a model.

        Args:
            model: The generation model enum.

        Returns:
            Minimum VRAM in GB required.

        Validates: R12.2
        """
        return MODEL_VRAM_REQUIREMENTS.get(model, 8)

    # =========================================================================
    # Internal Methods
    # =========================================================================

    async def _validate_talent_ownership(self, talent_id: UUID) -> None:
        """Verify the talent_id belongs to the authenticated org.

        Args:
            talent_id: The talent UUID to verify.

        Raises:
            HTTPException 403: If talent belongs to another org.

        Validates: R12.11
        """
        from sqlalchemy import select

        from app.models.talent import AiTalent

        stmt = select(AiTalent.id).where(
            AiTalent.id == talent_id,
            AiTalent.org_id == self._tenant.org_id,
        )
        result = await self._db.execute(stmt)
        talent = result.scalar_one_or_none()

        if talent is None:
            logger.warning(
                "generation_talent_ownership_denied",
                talent_id=str(talent_id),
                org_id=str(self._tenant.org_id),
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Talent does not belong to this organization",
                headers={"X-Error-Code": "FORBIDDEN"},
            )

    def _build_job_parameters(self, request: ImageGenerateRequest) -> dict:
        """Build the job parameters dict from the generation request.

        These parameters are stored on the job record and used by the
        worker to dispatch the actual generation to ComfyUI.

        Args:
            request: Validated ImageGenerateRequest.

        Returns:
            Dict of job parameters for worker dispatch.
        """
        params: dict = {
            "prompt": request.prompt,
            "model": request.model.value,
            "width": request.width,
            "height": request.height,
            "num_steps": request.num_steps,
            "guidance_scale": request.guidance_scale,
            "vram_required_gb": self.get_vram_requirement(request.model),
        }

        if request.negative_prompt:
            params["negative_prompt"] = request.negative_prompt

        if request.seed is not None:
            params["seed"] = request.seed

        if request.lora_model_id:
            params["lora_model_id"] = str(request.lora_model_id)
            params["lora_strength"] = request.lora_strength

        if request.talent_id:
            params["talent_id"] = str(request.talent_id)

        return params

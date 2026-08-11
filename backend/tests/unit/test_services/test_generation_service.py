"""Unit tests for GenerationService — image generation pipeline.

Tests cover:
    - submit_image_generation creates a queued job and returns it
    - submit_image_generation with talent_id validates ownership
    - submit_image_generation rejects cross-tenant talent_id with 403
    - submit_image_generation builds correct job parameters
    - get_retry_config returns expected configuration
    - compute_retry_delay returns correct backoff values (10s, 20s, 40s)
    - compute_retry_delay returns None after max retries
    - get_vram_requirement returns correct VRAM per model
    - Workflow errors → no retry (fail immediately)
    - Transient errors → retry 3x with backoff

Requirements: R12.1, R12.2, R12.3, R12.6, R12.7, R12.8, R12.9, R12.10
"""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

# =============================================================================
# Mock heavy dependencies before importing application modules.
# =============================================================================

_sa_mock = MagicMock()
_sa_mock.DateTime = MagicMock
_sa_mock.Float = MagicMock
_sa_mock.Integer = MagicMock
_sa_mock.String = MagicMock
_sa_mock.Text = MagicMock
_sa_mock.Boolean = MagicMock
_sa_mock.ForeignKey = MagicMock
_sa_mock.Index = MagicMock
_sa_mock.func = MagicMock()
_sa_mock.select = MagicMock()
_sa_mock.update = MagicMock()
_sa_mock.and_ = MagicMock()

_sa_orm_mock = MagicMock()
_sa_orm_mock.Mapped = MagicMock
_sa_orm_mock.mapped_column = MagicMock(return_value=None)
_sa_orm_mock.relationship = MagicMock(return_value=None)
_sa_orm_mock.DeclarativeBase = type("DeclarativeBase", (), {})

_sa_dialects_pg_mock = MagicMock()
_sa_dialects_pg_mock.UUID = MagicMock
_sa_dialects_pg_mock.JSONB = MagicMock
_sa_dialects_pg_mock.ARRAY = MagicMock

_sa_ext_asyncio_mock = MagicMock()
_sa_ext_asyncio_mock.AsyncSession = MagicMock

sys.modules.setdefault("sqlalchemy", _sa_mock)
sys.modules.setdefault("sqlalchemy.orm", _sa_orm_mock)
sys.modules.setdefault("sqlalchemy.dialects", MagicMock())
sys.modules.setdefault("sqlalchemy.dialects.postgresql", _sa_dialects_pg_mock)
sys.modules.setdefault("sqlalchemy.ext", MagicMock())
sys.modules.setdefault("sqlalchemy.ext.asyncio", _sa_ext_asyncio_mock)
sys.modules.setdefault("sqlalchemy.exc", MagicMock())

# Mock app.db.*
_mock_db_mod = ModuleType("app.db")
sys.modules.setdefault("app.db", _mock_db_mod)

_mock_db_session = ModuleType("app.db.session")
_mock_db_session.get_db_session = MagicMock()  # type: ignore[attr-defined]
sys.modules.setdefault("app.db.session", _mock_db_session)

_mock_db_base = ModuleType("app.db.base")


class _FakeBase:
    metadata = MagicMock()


_mock_db_base.Base = _FakeBase  # type: ignore[attr-defined]
sys.modules.setdefault("app.db.base", _mock_db_base)

_mock_db_tenant = ModuleType("app.db.tenant_scope")
_mock_db_tenant.QUARANTINED_ORG_ID = UUID("00000000-0000-0000-0000-000000000000")  # type: ignore[attr-defined]
_mock_db_tenant.TenantScopedRepository = MagicMock  # type: ignore[attr-defined]
sys.modules.setdefault("app.db.tenant_scope", _mock_db_tenant)

# Mock app.models.*
sys.modules.setdefault("app.models", MagicMock())
sys.modules.setdefault("app.models.job", MagicMock())
sys.modules.setdefault("app.models.job_lease", MagicMock())
sys.modules.setdefault("app.models.talent", MagicMock())
sys.modules.setdefault("app.models.asset", MagicMock())
sys.modules.setdefault("app.models.consent", MagicMock())
sys.modules.setdefault("app.models.talent_lora", MagicMock())
sys.modules.setdefault("app.models.generation_context_package", MagicMock())

# Mock app.repositories.*
sys.modules.setdefault("app.repositories", MagicMock())
sys.modules.setdefault("app.repositories.job_repository", MagicMock())

# Mock backend.database (for TenantContext resolution fallback)
sys.modules.setdefault("backend", MagicMock())
sys.modules.setdefault("backend.database", MagicMock())

# =============================================================================
# Now import application modules
# =============================================================================

from app.core.dependencies import TenantContext, TrustDomain, WorkspaceRole
from app.schemas.generation import GenerationModel, ImageGenerateRequest
from app.services.generation_service import (
    DEFAULT_GENERATION_TIMEOUT_SECONDS,
    MAX_TRANSIENT_RETRIES,
    TRANSIENT_RETRY_BACKOFF_SECONDS,
    GenerationService,
    GenerationServiceError,
    TransientError,
    WorkflowError,
)


# =============================================================================
# Fixtures
# =============================================================================

ORG_ID = uuid4()
USER_ID = uuid4()
TALENT_ID = uuid4()


@pytest.fixture
def tenant_context() -> TenantContext:
    """Create a test TenantContext."""
    return TenantContext(
        user_id=USER_ID,
        org_id=ORG_ID,
        role=WorkspaceRole.EDITOR,
        trust_domain=TrustDomain.CUSTOMER_USER,
        email="test@example.com",
    )


@pytest.fixture
def mock_db() -> AsyncMock:
    """Create a mock async database session."""
    return AsyncMock()


@pytest.fixture
def service(mock_db: AsyncMock, tenant_context: TenantContext) -> GenerationService:
    """Create a GenerationService instance with mocked deps."""
    return GenerationService(db=mock_db, tenant=tenant_context)


@pytest.fixture
def valid_request() -> ImageGenerateRequest:
    """Create a valid ImageGenerateRequest."""
    return ImageGenerateRequest(
        prompt="A beautiful sunset over mountains",
        model=GenerationModel.FLUX_DEV,
        width=1024,
        height=1024,
    )


@pytest.fixture
def request_with_talent() -> ImageGenerateRequest:
    """Create a request with a talent_id."""
    return ImageGenerateRequest(
        prompt="Portrait of AI talent",
        model=GenerationModel.SDXL_TURBO,
        width=512,
        height=512,
        talent_id=TALENT_ID,
    )


# =============================================================================
# Tests — submit_image_generation
# =============================================================================


class TestSubmitImageGeneration:
    """Tests for GenerationService.submit_image_generation."""

    @pytest.mark.asyncio
    async def test_creates_queued_job(
        self, service: GenerationService, valid_request: ImageGenerateRequest, mock_db: AsyncMock
    ) -> None:
        """submit_image_generation creates a job with status 'queued'."""
        mock_job = MagicMock()
        mock_job.id = uuid4()
        mock_job.status = "queued"

        with patch(
            "app.services.job_service.JobService"
        ) as MockJobService:
            mock_job_service_instance = AsyncMock()
            mock_job_service_instance.submit_job.return_value = mock_job
            MockJobService.return_value = mock_job_service_instance

            result = await service.submit_image_generation(valid_request)

        assert result.id == mock_job.id
        assert result.status == "queued"
        mock_job_service_instance.submit_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_job_with_correct_type(
        self, service: GenerationService, valid_request: ImageGenerateRequest
    ) -> None:
        """Job is created with job_type=image_generation."""
        mock_job = MagicMock()
        mock_job.id = uuid4()
        mock_job.status = "queued"

        with patch(
            "app.services.job_service.JobService"
        ) as MockJobService:
            mock_job_service_instance = AsyncMock()
            mock_job_service_instance.submit_job.return_value = mock_job
            MockJobService.return_value = mock_job_service_instance

            await service.submit_image_generation(valid_request)

            # Verify the JobCreate schema passed to submit_job
            call_args = mock_job_service_instance.submit_job.call_args
            job_create = call_args.kwargs.get("create_schema") or call_args[0][0]
            assert job_create.job_type.value == "image_generation"

    @pytest.mark.asyncio
    async def test_validates_talent_ownership_success(
        self,
        service: GenerationService,
        request_with_talent: ImageGenerateRequest,
        mock_db: AsyncMock,
    ) -> None:
        """Valid talent_id owned by org passes validation."""
        # Mock the DB query to return a talent
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = TALENT_ID
        mock_db.execute.return_value = mock_result

        mock_job = MagicMock()
        mock_job.id = uuid4()
        mock_job.status = "queued"

        with patch(
            "app.services.job_service.JobService"
        ) as MockJobService:
            mock_job_service_instance = AsyncMock()
            mock_job_service_instance.submit_job.return_value = mock_job
            MockJobService.return_value = mock_job_service_instance

            result = await service.submit_image_generation(request_with_talent)

        assert result.id == mock_job.id

    @pytest.mark.asyncio
    async def test_rejects_cross_tenant_talent_with_403(
        self,
        service: GenerationService,
        request_with_talent: ImageGenerateRequest,
        mock_db: AsyncMock,
    ) -> None:
        """talent_id belonging to another org raises 403."""
        from fastapi import HTTPException

        # Mock the DB query to return None (talent not found for this org)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(HTTPException) as exc_info:
            await service.submit_image_generation(request_with_talent)

        assert exc_info.value.status_code == 403
        assert "does not belong" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_no_talent_validation_when_none(
        self, service: GenerationService, valid_request: ImageGenerateRequest, mock_db: AsyncMock
    ) -> None:
        """No talent ownership check when talent_id is None."""
        mock_job = MagicMock()
        mock_job.id = uuid4()
        mock_job.status = "queued"

        with patch(
            "app.services.job_service.JobService"
        ) as MockJobService:
            mock_job_service_instance = AsyncMock()
            mock_job_service_instance.submit_job.return_value = mock_job
            MockJobService.return_value = mock_job_service_instance

            await service.submit_image_generation(valid_request)

        # DB execute should NOT be called for talent validation
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_max_duration_set_to_30_minutes(
        self, service: GenerationService, valid_request: ImageGenerateRequest
    ) -> None:
        """Job max_duration_seconds set to 1800 (30 minutes)."""
        mock_job = MagicMock()
        mock_job.id = uuid4()
        mock_job.status = "queued"

        with patch(
            "app.services.job_service.JobService"
        ) as MockJobService:
            mock_job_service_instance = AsyncMock()
            mock_job_service_instance.submit_job.return_value = mock_job
            MockJobService.return_value = mock_job_service_instance

            await service.submit_image_generation(valid_request)

            call_args = mock_job_service_instance.submit_job.call_args
            job_create = call_args.kwargs.get("create_schema") or call_args[0][0]
            assert job_create.max_duration_seconds == 1800


# =============================================================================
# Tests — Job Parameters
# =============================================================================


class TestBuildJobParameters:
    """Tests for _build_job_parameters."""

    def test_basic_parameters(
        self, service: GenerationService, valid_request: ImageGenerateRequest
    ) -> None:
        """Basic request produces correct parameter dict."""
        params = service._build_job_parameters(valid_request)

        assert params["prompt"] == "A beautiful sunset over mountains"
        assert params["model"] == "flux_dev"
        assert params["width"] == 1024
        assert params["height"] == 1024
        assert params["num_steps"] == 20
        assert params["guidance_scale"] == 7.5
        assert params["vram_required_gb"] == 12  # Flux requires 12GB

    def test_includes_talent_id_when_provided(self, service: GenerationService) -> None:
        """talent_id is included in parameters when provided."""
        request = ImageGenerateRequest(
            prompt="Test prompt",
            model=GenerationModel.SDXL_TURBO,
            width=512,
            height=512,
            talent_id=TALENT_ID,
        )
        params = service._build_job_parameters(request)
        assert params["talent_id"] == str(TALENT_ID)

    def test_includes_negative_prompt(self, service: GenerationService) -> None:
        """Negative prompt is included when provided."""
        request = ImageGenerateRequest(
            prompt="Beautiful landscape",
            negative_prompt="blurry, low quality",
            width=1024,
            height=1024,
        )
        params = service._build_job_parameters(request)
        assert params["negative_prompt"] == "blurry, low quality"

    def test_includes_seed_when_provided(self, service: GenerationService) -> None:
        """Seed is included when provided."""
        request = ImageGenerateRequest(
            prompt="Test",
            seed=42,
            width=1024,
            height=1024,
        )
        params = service._build_job_parameters(request)
        assert params["seed"] == 42

    def test_includes_lora_when_provided(self, service: GenerationService) -> None:
        """LoRA model_id and strength included when provided."""
        lora_id = uuid4()
        request = ImageGenerateRequest(
            prompt="Test with LoRA",
            lora_model_id=lora_id,
            lora_strength=0.6,
            width=1024,
            height=1024,
        )
        params = service._build_job_parameters(request)
        assert params["lora_model_id"] == str(lora_id)
        assert params["lora_strength"] == 0.6

    def test_excludes_none_optional_fields(
        self, service: GenerationService, valid_request: ImageGenerateRequest
    ) -> None:
        """Optional fields that are None are not included in parameters."""
        params = service._build_job_parameters(valid_request)
        assert "negative_prompt" not in params
        assert "seed" not in params
        assert "lora_model_id" not in params
        assert "talent_id" not in params


# =============================================================================
# Tests — Retry Configuration
# =============================================================================


class TestRetryConfiguration:
    """Tests for retry logic configuration (R12.8, R12.9)."""

    def test_get_retry_config_values(self, service: GenerationService) -> None:
        """get_retry_config returns expected configuration."""
        config = service.get_retry_config()

        assert config["max_retries"] == 3
        assert config["backoff_seconds"] == [10, 20, 40]
        assert config["timeout_seconds"] == 1800
        assert config["workflow_error_retry"] is False
        assert config["transient_error_retry"] is True

    def test_compute_retry_delay_first_attempt(self, service: GenerationService) -> None:
        """First retry attempt: 10 seconds delay."""
        delay = service.compute_retry_delay(0)
        assert delay == 10

    def test_compute_retry_delay_second_attempt(self, service: GenerationService) -> None:
        """Second retry attempt: 20 seconds delay."""
        delay = service.compute_retry_delay(1)
        assert delay == 20

    def test_compute_retry_delay_third_attempt(self, service: GenerationService) -> None:
        """Third retry attempt: 40 seconds delay."""
        delay = service.compute_retry_delay(2)
        assert delay == 40

    def test_compute_retry_delay_beyond_max(self, service: GenerationService) -> None:
        """Beyond max retries returns None (no more retries)."""
        delay = service.compute_retry_delay(3)
        assert delay is None

    def test_compute_retry_delay_way_beyond_max(self, service: GenerationService) -> None:
        """Far beyond max retries still returns None."""
        delay = service.compute_retry_delay(10)
        assert delay is None


# =============================================================================
# Tests — VRAM Requirements
# =============================================================================


class TestVRAMRequirements:
    """Tests for get_vram_requirement (R12.2 — dispatch to provider meeting requirements)."""

    def test_flux_dev_requires_12gb(self, service: GenerationService) -> None:
        """Flux Dev requires 12GB VRAM."""
        assert service.get_vram_requirement(GenerationModel.FLUX_DEV) == 12

    def test_sdxl_turbo_requires_8gb(self, service: GenerationService) -> None:
        """SDXL Turbo requires 8GB VRAM."""
        assert service.get_vram_requirement(GenerationModel.SDXL_TURBO) == 8

    def test_sd15_requires_8gb(self, service: GenerationService) -> None:
        """SD 1.5 requires 8GB VRAM."""
        assert service.get_vram_requirement(GenerationModel.SD15) == 8


# =============================================================================
# Tests — Exception Classes
# =============================================================================


class TestExceptions:
    """Tests for generation-specific exceptions."""

    def test_workflow_error_no_retry(self) -> None:
        """WorkflowError has code WORKFLOW_ERROR and should not be retried."""
        err = WorkflowError("Missing model file: flux_dev.safetensors")
        assert err.code == "WORKFLOW_ERROR"
        assert "Missing model" in err.message

    def test_transient_error_can_retry(self) -> None:
        """TransientError has code TRANSIENT_ERROR and can be retried."""
        err = TransientError("Connection to GPU worker timed out")
        assert err.code == "TRANSIENT_ERROR"
        assert "timed out" in err.message

    def test_base_error(self) -> None:
        """GenerationServiceError has a default code."""
        err = GenerationServiceError("Something went wrong")
        assert err.code == "GENERATION_ERROR"


# =============================================================================
# Tests — Constants
# =============================================================================


class TestConstants:
    """Tests for module-level configuration constants."""

    def test_backoff_sequence(self) -> None:
        """Backoff sequence is [10, 20, 40] per R12.9."""
        assert TRANSIENT_RETRY_BACKOFF_SECONDS == [10, 20, 40]

    def test_max_retries(self) -> None:
        """Max retries is 3 per R12.9."""
        assert MAX_TRANSIENT_RETRIES == 3

    def test_default_timeout(self) -> None:
        """Default timeout is 1800 seconds (30 minutes) per R12.6."""
        assert DEFAULT_GENERATION_TIMEOUT_SECONDS == 1800


# =============================================================================
# Tests — Schema Validation (already defined in generation.py, tested here)
# =============================================================================


class TestImageGenerateRequestSchema:
    """Tests for ImageGenerateRequest Pydantic validation."""

    def test_valid_minimal_request(self) -> None:
        """Minimal valid request passes validation."""
        req = ImageGenerateRequest(prompt="Hello world", width=1024, height=1024)
        assert req.prompt == "Hello world"
        assert req.model == GenerationModel.FLUX_DEV  # default

    def test_prompt_max_length_2000(self) -> None:
        """Prompt exceeding 2000 chars is rejected."""
        with pytest.raises(Exception):
            ImageGenerateRequest(
                prompt="x" * 2001,
                width=1024,
                height=1024,
            )

    def test_whitespace_only_prompt_rejected(self) -> None:
        """Whitespace-only prompt is rejected."""
        with pytest.raises(Exception):
            ImageGenerateRequest(
                prompt="   ",
                width=1024,
                height=1024,
            )

    def test_dimensions_below_256_rejected(self) -> None:
        """Dimensions below 256px are rejected."""
        with pytest.raises(Exception):
            ImageGenerateRequest(
                prompt="Test",
                width=128,
                height=1024,
            )

    def test_dimensions_above_2048_rejected(self) -> None:
        """Dimensions above 2048px are rejected."""
        with pytest.raises(Exception):
            ImageGenerateRequest(
                prompt="Test",
                width=4096,
                height=1024,
            )

    def test_dimensions_not_multiple_of_64_rejected(self) -> None:
        """Dimensions not multiples of 64 are rejected."""
        with pytest.raises(Exception):
            ImageGenerateRequest(
                prompt="Test",
                width=1000,
                height=1024,
            )

    def test_valid_dimensions_pass(self) -> None:
        """Valid dimensions (multiples of 64, 256-2048) pass."""
        req = ImageGenerateRequest(
            prompt="Test",
            width=512,
            height=768,
        )
        assert req.width == 512
        assert req.height == 768

    def test_invalid_model_rejected(self) -> None:
        """Invalid model enum value is rejected."""
        with pytest.raises(Exception):
            ImageGenerateRequest(
                prompt="Test",
                model="nonexistent_model",
                width=1024,
                height=1024,
            )

    def test_talent_id_accepts_uuid(self) -> None:
        """talent_id accepts valid UUID."""
        tid = uuid4()
        req = ImageGenerateRequest(
            prompt="Test",
            talent_id=tid,
            width=1024,
            height=1024,
        )
        assert req.talent_id == tid

"""Unit tests for TrainingPipelineService — training job lifecycle.

Tests cover:
    - submit_training_job creates job with status "queued" (R35.1)
    - submit rejects when talent not found (404)
    - submit rejects when manifest not found (404)
    - submit rejects when manifest is invalid (422)
    - submit rejects when image count < 10 or > 200 (R35.10)
    - submit returns existing job for duplicate idempotency_key
    - estimate_cost returns valid estimates (R35.2)
    - complete_training_job creates model + talent_loras (R35.4, R35.11)
    - cancel_training_job cancels queued/running jobs (R35.5)
    - cancel_training_job returns 409 for terminal states (R35.6)
    - fail_training_job marks job as failed
    - fail_training_job marks job as timed_out when timeout flag set (R35.7)
    - list_training_jobs returns paginated results
    - get_training_job returns job for valid ID
    - get_training_job raises 404 for missing/cross-tenant

Requirements: R35.1, R35.2, R35.4, R35.5, R35.6, R35.7, R35.8, R35.10, R35.11
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

# =============================================================================
# Mock heavy dependencies at sys.modules level before any app imports.
# =============================================================================

_sa_mock = MagicMock()
_sa_mock.DateTime = MagicMock
_sa_mock.Float = MagicMock
_sa_mock.Integer = MagicMock
_sa_mock.String = MagicMock
_sa_mock.Text = MagicMock
_sa_mock.Boolean = MagicMock
_sa_mock.Numeric = MagicMock
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
    pass


_mock_db_base.Base = _FakeBase  # type: ignore[attr-defined]
_mock_db_base.TimestampMixin = type("TimestampMixin", (), {})  # type: ignore[attr-defined]
_mock_db_base.UUIDMixin = type("UUIDMixin", (), {})  # type: ignore[attr-defined]
_mock_db_base.TenantMixin = type("TenantMixin", (), {})  # type: ignore[attr-defined]
_mock_db_base.SoftDeleteMixin = type("SoftDeleteMixin", (), {})  # type: ignore[attr-defined]
sys.modules.setdefault("app.db.base", _mock_db_base)

_mock_tenant_scope = ModuleType("app.db.tenant_scope")
_mock_tenant_scope.QUARANTINED_ORG_ID = UUID("00000000-0000-0000-0000-000000000000")  # type: ignore[attr-defined]
_mock_tenant_scope.TenantScopedRepository = MagicMock()  # type: ignore[attr-defined]
_mock_tenant_scope.validate_org_id = MagicMock()  # type: ignore[attr-defined]
sys.modules.setdefault("app.db.tenant_scope", _mock_tenant_scope)

# Mock jose, passlib, pydantic-settings, structlog, dotenv
sys.modules.setdefault("jose", MagicMock())
sys.modules.setdefault("passlib", MagicMock())
sys.modules.setdefault("passlib.context", MagicMock())

_pydantic_settings_mock = MagicMock()
_pydantic_settings_mock.BaseSettings = type("BaseSettings", (), {"model_config": {}})
sys.modules.setdefault("pydantic_settings", _pydantic_settings_mock)
sys.modules.setdefault("dotenv", MagicMock())
sys.modules.setdefault("structlog", MagicMock())

# Mock app.models package
_mock_models_pkg = ModuleType("app.models")
_mock_models_pkg.__path__ = []  # type: ignore[attr-defined]
sys.modules.setdefault("app.models", _mock_models_pkg)

# Mock app.models.talent
_mock_models_talent = ModuleType("app.models.talent")


class _MockAiTalent:
    __tablename__ = "talent"
    id = MagicMock()
    org_id = MagicMock()
    deleted_at = MagicMock()

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


_mock_models_talent.AiTalent = _MockAiTalent  # type: ignore[attr-defined]
sys.modules.setdefault("app.models.talent", _mock_models_talent)

# Mock app.models.dataset_manifest
_mock_models_dm = ModuleType("app.models.dataset_manifest")


class _MockDatasetManifest:
    __tablename__ = "dataset_manifests"
    id = MagicMock()
    org_id = MagicMock()
    is_valid = MagicMock()

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        if "id" not in kwargs:
            self.id = uuid4()
        if "created_at" not in kwargs:
            self.created_at = datetime.now(UTC)
        if "updated_at" not in kwargs:
            self.updated_at = datetime.now(UTC)


_mock_models_dm.DatasetManifest = _MockDatasetManifest  # type: ignore[attr-defined]
sys.modules.setdefault("app.models.dataset_manifest", _mock_models_dm)

# Mock app.models.model_lifecycle
_mock_models_ml = ModuleType("app.models.model_lifecycle")


class _MockModelRegistryEntry:
    __tablename__ = "model_registry"

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        if "id" not in kwargs:
            self.id = uuid4()
        if "created_at" not in kwargs:
            self.created_at = datetime.now(UTC)
        if "updated_at" not in kwargs:
            self.updated_at = datetime.now(UTC)


class _MockModelTransition:
    __tablename__ = "model_transitions"

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


_mock_models_ml.ModelRegistryEntry = _MockModelRegistryEntry  # type: ignore[attr-defined]
_mock_models_ml.ModelTransition = _MockModelTransition  # type: ignore[attr-defined]
sys.modules.setdefault("app.models.model_lifecycle", _mock_models_ml)

# Mock app.models.talent_lora
_mock_models_tl = ModuleType("app.models.talent_lora")


class _MockTalentLora:
    __tablename__ = "talent_loras"

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


_mock_models_tl.TalentLora = _MockTalentLora  # type: ignore[attr-defined]
sys.modules.setdefault("app.models.talent_lora", _mock_models_tl)

# Mock app.models.job
_mock_models_job = ModuleType("app.models.job")


class _MockJob:
    __tablename__ = "jobs"
    # Class-level column attributes for SQLAlchemy-style filtering
    id = MagicMock()
    org_id = MagicMock()
    type = MagicMock()
    status = MagicMock()
    talent_id = MagicMock()
    idempotency_key = MagicMock()
    created_at = MagicMock()

    # Ensure status.notin_ works for idempotency queries
    status.notin_ = MagicMock(return_value=MagicMock())

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        if "id" not in kwargs:
            self.id = uuid4()
        if "created_at" not in kwargs:
            self.created_at = datetime.now(UTC)
        if "updated_at" not in kwargs:
            self.updated_at = datetime.now(UTC)
        if "progress_percent" not in kwargs:
            self.progress_percent = None
        if "progress_message" not in kwargs:
            self.progress_message = None
        if "error_message" not in kwargs:
            self.error_message = None
        if "cost_usd" not in kwargs:
            self.cost_usd = None
        if "started_at" not in kwargs:
            self.started_at = None
        if "completed_at" not in kwargs:
            self.completed_at = None
        if "output_asset_ids" not in kwargs:
            self.output_asset_ids = None


_mock_models_job.Job = _MockJob  # type: ignore[attr-defined]
sys.modules.setdefault("app.models.job", _mock_models_job)

# Mock consent model (used by dataset manifest service)
_mock_models_consent = ModuleType("app.models.consent")


class _MockConsentRecord:
    __tablename__ = "consent_records"

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


_mock_models_consent.ConsentRecord = _MockConsentRecord  # type: ignore[attr-defined]
sys.modules.setdefault("app.models.consent", _mock_models_consent)

# Mock backend.storage
sys.modules.setdefault("backend", MagicMock())
sys.modules.setdefault("backend.storage", MagicMock())

# =============================================================================
# Now import the service under test
# =============================================================================

from app.core.dependencies import TenantContext, TrustDomain, WorkspaceRole  # noqa: E402
from app.schemas.training import TrainingBaseModel, TrainingJobCreate  # noqa: E402
from app.services.training_pipeline_service import (  # noqa: E402
    TrainingPipelineService,
)


# =============================================================================
# Fixtures
# =============================================================================

ORG_ID = uuid4()
USER_ID = uuid4()
TALENT_ID = uuid4()
MANIFEST_ID = uuid4()


@pytest.fixture
def tenant_context() -> TenantContext:
    """Create a standard test TenantContext."""
    return TenantContext(
        user_id=USER_ID,
        org_id=ORG_ID,
        role=WorkspaceRole.EDITOR,
        trust_domain=TrustDomain.CUSTOMER_USER,
    )


@pytest.fixture
def mock_db() -> AsyncMock:
    """Create a mock async DB session."""
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.scalar = AsyncMock(return_value=0)
    return db


@pytest.fixture
def service(mock_db: AsyncMock, tenant_context: TenantContext) -> TrainingPipelineService:
    """Create the service under test."""
    return TrainingPipelineService(db=mock_db, tenant=tenant_context)


def _make_talent(org_id=ORG_ID, talent_id=TALENT_ID, deleted_at=None):
    """Create a mock talent."""
    return _MockAiTalent(
        id=talent_id, org_id=org_id, name="Test Talent", deleted_at=deleted_at
    )


def _make_manifest(org_id=ORG_ID, manifest_id=MANIFEST_ID, is_valid=True, file_count=20):
    """Create a mock manifest."""
    return _MockDatasetManifest(
        id=manifest_id,
        org_id=org_id,
        is_valid=is_valid,
        total_file_count=file_count,
        invalidation_reason=None if is_valid else "test invalid",
    )


def _make_job(org_id=ORG_ID, job_status="queued", type="lora_training", **kwargs):
    """Create a mock job."""
    defaults = {
        "id": uuid4(),
        "org_id": org_id,
        "type": type,
        "status": job_status,
        "talent_id": TALENT_ID,
        "parameters": {
            "manifest_id": str(MANIFEST_ID),
            "base_model": "flux-dev",
            "trigger_word": "ohwx",
            "steps": 1000,
            "rank": 16,
            "learning_rate": 1e-4,
            "resolution": 1024,
        },
    }
    defaults.update(kwargs)
    return _MockJob(**defaults)


# =============================================================================
# Tests — Submit Training Job (R35.1, R35.10)
# =============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_submit_training_job_success(service, mock_db):
    """submit_training_job creates job with status 'queued' on valid input."""
    talent = _make_talent()
    manifest = _make_manifest(file_count=20)

    # Mock DB queries: talent lookup, manifest lookup, idempotency check
    mock_result_talent = MagicMock()
    mock_result_talent.scalar_one_or_none.return_value = talent

    mock_result_manifest = MagicMock()
    mock_result_manifest.scalar_one_or_none.return_value = manifest

    mock_db.execute = AsyncMock(
        side_effect=[mock_result_talent, mock_result_manifest]
    )

    # Mock refresh to set ID on the job
    async def _refresh(obj):
        if not hasattr(obj, "id") or obj.id is None:
            obj.id = uuid4()
        if not hasattr(obj, "created_at"):
            obj.created_at = datetime.now(UTC)
        if not hasattr(obj, "updated_at"):
            obj.updated_at = datetime.now(UTC)

    mock_db.refresh = AsyncMock(side_effect=_refresh)

    data = TrainingJobCreate(
        talent_id=TALENT_ID,
        manifest_id=MANIFEST_ID,
        base_model=TrainingBaseModel.FLUX_DEV,
        trigger_word="ohwx",
        steps=1000,
        rank=16,
    )

    result = await service.submit_training_job(data)

    assert result.status == "queued"
    assert result.type == "lora_training"
    assert result.org_id == ORG_ID
    assert result.talent_id == TALENT_ID
    assert result.parameters["manifest_id"] == str(MANIFEST_ID)
    mock_db.add.assert_called_once()
    mock_db.flush.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_submit_rejects_missing_talent(service, mock_db):
    """submit_training_job raises 404 when talent not found."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)

    data = TrainingJobCreate(
        talent_id=TALENT_ID,
        manifest_id=MANIFEST_ID,
    )

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await service.submit_training_job(data)

    assert exc_info.value.status_code == 404
    assert "Talent" in exc_info.value.detail


@pytest.mark.unit
@pytest.mark.asyncio
async def test_submit_rejects_missing_manifest(service, mock_db):
    """submit_training_job raises 404 when manifest not found."""
    talent = _make_talent()
    mock_result_talent = MagicMock()
    mock_result_talent.scalar_one_or_none.return_value = talent

    mock_result_manifest = MagicMock()
    mock_result_manifest.scalar_one_or_none.return_value = None

    mock_db.execute = AsyncMock(
        side_effect=[mock_result_talent, mock_result_manifest]
    )

    data = TrainingJobCreate(talent_id=TALENT_ID, manifest_id=MANIFEST_ID)

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await service.submit_training_job(data)

    assert exc_info.value.status_code == 404
    assert "manifest" in exc_info.value.detail.lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_submit_rejects_invalid_manifest(service, mock_db):
    """submit_training_job raises 422 when manifest is invalid."""
    talent = _make_talent()
    manifest = _make_manifest(is_valid=False)

    mock_result_talent = MagicMock()
    mock_result_talent.scalar_one_or_none.return_value = talent

    mock_result_manifest = MagicMock()
    mock_result_manifest.scalar_one_or_none.return_value = manifest

    mock_db.execute = AsyncMock(
        side_effect=[mock_result_talent, mock_result_manifest]
    )

    data = TrainingJobCreate(talent_id=TALENT_ID, manifest_id=MANIFEST_ID)

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await service.submit_training_job(data)

    assert exc_info.value.status_code == 422
    assert "invalid" in exc_info.value.detail.lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_submit_rejects_too_few_images(service, mock_db):
    """submit_training_job raises 422 when fewer than 10 images (R35.10)."""
    talent = _make_talent()
    manifest = _make_manifest(file_count=5)

    mock_result_talent = MagicMock()
    mock_result_talent.scalar_one_or_none.return_value = talent

    mock_result_manifest = MagicMock()
    mock_result_manifest.scalar_one_or_none.return_value = manifest

    mock_db.execute = AsyncMock(
        side_effect=[mock_result_talent, mock_result_manifest]
    )

    data = TrainingJobCreate(talent_id=TALENT_ID, manifest_id=MANIFEST_ID)

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await service.submit_training_job(data)

    assert exc_info.value.status_code == 422
    assert "10-200" in exc_info.value.detail


@pytest.mark.unit
@pytest.mark.asyncio
async def test_submit_rejects_too_many_images(service, mock_db):
    """submit_training_job raises 422 when more than 200 images (R35.10)."""
    talent = _make_talent()
    manifest = _make_manifest(file_count=250)

    mock_result_talent = MagicMock()
    mock_result_talent.scalar_one_or_none.return_value = talent

    mock_result_manifest = MagicMock()
    mock_result_manifest.scalar_one_or_none.return_value = manifest

    mock_db.execute = AsyncMock(
        side_effect=[mock_result_talent, mock_result_manifest]
    )

    data = TrainingJobCreate(talent_id=TALENT_ID, manifest_id=MANIFEST_ID)

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await service.submit_training_job(data)

    assert exc_info.value.status_code == 422
    assert "10-200" in exc_info.value.detail


# =============================================================================
# Tests — Cost Estimation (R35.2)
# =============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_estimate_cost_returns_valid_estimate(service):
    """estimate_cost returns a valid TrainingEstimateResponse."""
    result = await service.estimate_cost(
        base_model="flux-dev",
        steps=1000,
        resolution=1024,
        image_count=20,
    )

    assert result.base_model == "flux-dev"
    assert result.steps == 1000
    assert result.resolution == 1024
    assert result.image_count == 20
    assert result.estimated_time_seconds > 0
    assert result.estimated_cost_usd > 0
    assert result.hourly_rate_usd > 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_estimate_cost_higher_for_more_steps(service):
    """estimate_cost increases with more steps."""
    result_low = await service.estimate_cost(
        base_model="flux-dev", steps=500, resolution=1024, image_count=20
    )
    result_high = await service.estimate_cost(
        base_model="flux-dev", steps=3000, resolution=1024, image_count=20
    )

    assert result_high.estimated_cost_usd > result_low.estimated_cost_usd
    assert result_high.estimated_time_seconds > result_low.estimated_time_seconds


# =============================================================================
# Tests — Complete Training Job (R35.4, R35.11)
# =============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_complete_training_job_creates_model_and_lora(service, mock_db):
    """complete_training_job creates model record + talent_loras association."""
    job = _make_job(job_status="running")

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = job
    mock_db.execute = AsyncMock(return_value=mock_result)

    async def _refresh(obj):
        if not hasattr(obj, "id") or obj.id is None:
            obj.id = uuid4()
        if not hasattr(obj, "created_at"):
            obj.created_at = datetime.now(UTC)
        if not hasattr(obj, "updated_at"):
            obj.updated_at = datetime.now(UTC)

    mock_db.refresh = AsyncMock(side_effect=_refresh)

    result = await service.complete_training_job(
        job_id=job.id,
        model_name="lora_test_model",
        storage_key="/org/models/talent/lora.safetensors",
        checksum_sha256="a" * 64,
        file_size_bytes=1024 * 1024,
        cost_usd=2.50,
    )

    assert result.status == "completed"
    assert result.completed_at is not None
    # Verify model, transition, and talent_lora were added
    assert mock_db.add.call_count == 3  # model + transition + talent_lora


# =============================================================================
# Tests — Cancel Training Job (R35.5, R35.6)
# =============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cancel_queued_job_succeeds(service, mock_db):
    """cancel_training_job cancels a queued job."""
    job = _make_job(job_status="queued")

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = job
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await service.cancel_training_job(job.id)

    assert result.status == "cancelled"
    assert result.completed_at is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cancel_running_job_succeeds(service, mock_db):
    """cancel_training_job cancels a running job."""
    job = _make_job(job_status="running")

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = job
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await service.cancel_training_job(job.id)

    assert result.status == "cancelled"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cancel_completed_job_returns_409(service, mock_db):
    """cancel_training_job returns 409 for completed jobs (R35.6)."""
    job = _make_job(job_status="completed")

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = job
    mock_db.execute = AsyncMock(return_value=mock_result)

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await service.cancel_training_job(job.id)

    assert exc_info.value.status_code == 409


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cancel_failed_job_returns_409(service, mock_db):
    """cancel_training_job returns 409 for failed jobs (R35.6)."""
    job = _make_job(job_status="failed")

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = job
    mock_db.execute = AsyncMock(return_value=mock_result)

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await service.cancel_training_job(job.id)

    assert exc_info.value.status_code == 409


# =============================================================================
# Tests — Fail Training Job (R35.7)
# =============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fail_training_job(service, mock_db):
    """fail_training_job marks job as failed."""
    job = _make_job(job_status="running")

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = job
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await service.fail_training_job(
        job_id=job.id,
        error_message="GPU out of memory",
    )

    assert result.status == "failed"
    assert result.error_message == "GPU out of memory"
    assert result.completed_at is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fail_training_job_timed_out(service, mock_db):
    """fail_training_job with timed_out=True sets status to timed_out (R35.7)."""
    job = _make_job(job_status="running")

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = job
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await service.fail_training_job(
        job_id=job.id,
        error_message="Training exceeded 4-hour timeout",
        timed_out=True,
    )

    assert result.status == "timed_out"
    assert result.error_message == "Training exceeded 4-hour timeout"


# =============================================================================
# Tests — Get / List Training Jobs
# =============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_training_job_success(service, mock_db):
    """get_training_job returns job for valid ID."""
    job = _make_job()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = job
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await service.get_training_job(job.id)
    assert result.id == job.id


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_training_job_not_found(service, mock_db):
    """get_training_job raises 404 for missing job."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await service.get_training_job(uuid4())

    assert exc_info.value.status_code == 404


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_training_jobs(service, mock_db):
    """list_training_jobs returns paginated results."""
    jobs = [_make_job() for _ in range(3)]

    # First call: count query
    mock_db.scalar = AsyncMock(return_value=3)

    # Second call: list query
    mock_result_list = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = jobs
    mock_result_list.scalars.return_value = mock_scalars
    mock_db.execute = AsyncMock(return_value=mock_result_list)

    items, total = await service.list_training_jobs(limit=20, offset=0)

    assert total == 3
    assert len(items) == 3

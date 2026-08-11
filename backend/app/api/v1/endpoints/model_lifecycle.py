"""Model/LoRA Lifecycle API endpoints.

Provides promotion gate management:
    - GET    /api/v1/models/lifecycle          — list models with lifecycle state
    - POST   /api/v1/models/lifecycle          — register a model in the system
    - GET    /api/v1/models/lifecycle/{id}     — get model lifecycle details
    - POST   /api/v1/models/lifecycle/{id}/promote    — promote to next state
    - POST   /api/v1/models/lifecycle/{id}/quarantine — quarantine from any state
    - POST   /api/v1/models/lifecycle/{id}/deprecate  — deprecate active model
    - GET    /api/v1/models/lifecycle/{id}/transitions — transition audit log
    - GET    /api/v1/models/lifecycle/transitions      — all transitions (workspace)

Requirements: R67.1, R67.2, R67.3, R67.4, R67.5, R67.6, R67.7, R67.8, R34.8
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, status

from app.core.dependencies import DBSessionDep, TenantContextDep
from app.core.rbac import AdminDep, EditorDep, ViewerDep
from app.schemas.model_lifecycle import (
    ModelDeprecateRequest,
    ModelLifecycleState,
    ModelPromoteRequest,
    ModelQuarantineRequest,
    ModelRegisterRequest,
    ModelRegistryListResponse,
    ModelRegistryResponse,
    ModelRiskClass,
    ModelTransitionListResponse,
    ModelTransitionResponse,
    ModelType,
)
from app.services.model_lifecycle_service import ModelLifecycleService

router = APIRouter(prefix="/models/lifecycle", tags=["model-lifecycle"])


# =============================================================================
# Helper to build response from ORM model
# =============================================================================


def _model_to_response(model: object) -> ModelRegistryResponse:
    """Convert a ModelRegistryEntry ORM instance to a response schema."""
    return ModelRegistryResponse(
        id=model.id,
        org_id=model.org_id,
        name=model.name,
        model_type=model.model_type,
        lifecycle_state=model.lifecycle_state,
        risk_class=model.risk_class,
        base_model_id=model.base_model_id,
        checksum_sha256=model.checksum_sha256,
        storage_key=model.storage_key,
        file_size_bytes=model.file_size_bytes,
        metadata=model.metadata_,
        quarantine_reason=model.quarantine_reason,
        quarantined_at=model.quarantined_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _transition_to_response(transition: object) -> ModelTransitionResponse:
    """Convert a ModelTransition ORM instance to a response schema."""
    return ModelTransitionResponse(
        id=transition.id,
        org_id=transition.org_id,
        model_id=transition.model_id,
        from_state=transition.from_state,
        to_state=transition.to_state,
        actor=transition.actor,
        actor_type=transition.actor_type,
        risk_class=transition.risk_class,
        evidence=transition.evidence,
        gate_checks_performed=transition.gate_checks_performed,
        gate_checks_passed=transition.gate_checks_passed,
        success=transition.success,
        error_message=transition.error_message,
        created_at=transition.created_at,
    )


# =============================================================================
# Endpoints
# =============================================================================


@router.get("", response_model=ModelRegistryListResponse)
async def list_models(
    tenant: ViewerDep,
    db: DBSessionDep,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    lifecycle_state: ModelLifecycleState | None = Query(
        None, description="Filter by lifecycle state"
    ),
    risk_class: ModelRiskClass | None = Query(
        None, description="Filter by risk class"
    ),
    model_type: ModelType | None = Query(
        None, description="Filter by model type"
    ),
) -> ModelRegistryListResponse:
    """List model registry entries with lifecycle state.

    Returns paginated list of models registered in the promotion
    gate system for the authenticated workspace.
    """
    service = ModelLifecycleService(db=db, tenant=tenant)
    items, total = await service.list_models(
        limit=limit,
        offset=offset,
        lifecycle_state=lifecycle_state.value if lifecycle_state else None,
        risk_class=risk_class.value if risk_class else None,
        model_type=model_type.value if model_type else None,
    )
    return ModelRegistryListResponse(
        items=[_model_to_response(m) for m in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "",
    response_model=ModelRegistryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_model(
    tenant: EditorDep,
    db: DBSessionDep,
    body: ModelRegisterRequest,
) -> ModelRegistryResponse:
    """Register a new model in the promotion gate lifecycle system.

    Models enter at IMPORTED or TRAINED state and must progress
    through promotion gates before becoming ACTIVE for production use.
    """
    service = ModelLifecycleService(db=db, tenant=tenant)
    model = await service.register_model(
        name=body.name,
        model_type=body.model_type.value,
        risk_class=body.risk_class.value,
        initial_state=body.initial_state.value,
        base_model_id=body.base_model_id,
        checksum_sha256=body.checksum_sha256,
        storage_key=body.storage_key,
        file_size_bytes=body.file_size_bytes,
        metadata=body.metadata,
    )
    return _model_to_response(model)


@router.get("/{model_id}", response_model=ModelRegistryResponse)
async def get_model(
    model_id: UUID,
    tenant: ViewerDep,
    db: DBSessionDep,
) -> ModelRegistryResponse:
    """Get a model's current lifecycle state and details."""
    service = ModelLifecycleService(db=db, tenant=tenant)
    model = await service.get_model(model_id)
    return _model_to_response(model)


@router.post(
    "/{model_id}/promote",
    response_model=ModelRegistryResponse,
)
async def promote_model(
    model_id: UUID,
    tenant: EditorDep,
    db: DBSessionDep,
    body: ModelPromoteRequest,
) -> ModelRegistryResponse:
    """Promote a model to the next valid lifecycle state.

    Enforces forward-only transitions and human approval gates
    for HIGH_RISK models at APPROVED/ACTIVE states.
    """
    service = ModelLifecycleService(db=db, tenant=tenant)
    model = await service.promote(
        model_id=model_id,
        target_state=body.target_state.value,
        actor=body.actor,
        actor_type=body.actor_type,
        evidence=body.evidence,
    )
    return _model_to_response(model)


@router.post(
    "/{model_id}/quarantine",
    response_model=ModelRegistryResponse,
)
async def quarantine_model(
    model_id: UUID,
    tenant: AdminDep,
    db: DBSessionDep,
    body: ModelQuarantineRequest,
) -> ModelRegistryResponse:
    """Quarantine a model from any lifecycle state.

    Quarantined models are immediately unavailable for all operations
    (generation, training, publishing) regardless of prior state.
    Requires ADMIN role.
    """
    service = ModelLifecycleService(db=db, tenant=tenant)
    model = await service.quarantine(
        model_id=model_id,
        reason=body.reason,
        actor=body.actor,
        evidence=body.evidence,
    )
    return _model_to_response(model)


@router.post(
    "/{model_id}/deprecate",
    response_model=ModelRegistryResponse,
)
async def deprecate_model(
    model_id: UUID,
    tenant: AdminDep,
    db: DBSessionDep,
    body: ModelDeprecateRequest,
) -> ModelRegistryResponse:
    """Deprecate an ACTIVE model.

    Removes from future job dispatch while preserving for
    reproducibility of historical jobs. Requires ADMIN role.
    """
    service = ModelLifecycleService(db=db, tenant=tenant)
    model = await service.deprecate(
        model_id=model_id,
        reason=body.reason,
        actor=body.actor,
    )
    return _model_to_response(model)


@router.get(
    "/{model_id}/transitions",
    response_model=ModelTransitionListResponse,
)
async def get_model_transitions(
    model_id: UUID,
    tenant: ViewerDep,
    db: DBSessionDep,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> ModelTransitionListResponse:
    """Get transition audit log for a specific model.

    Returns the full history of lifecycle state changes including
    failed attempts and gate check results.
    """
    service = ModelLifecycleService(db=db, tenant=tenant)
    items, total = await service.get_transitions(
        model_id=model_id,
        limit=limit,
        offset=offset,
    )
    return ModelTransitionListResponse(
        items=[_transition_to_response(t) for t in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/transitions/all", response_model=ModelTransitionListResponse)
async def list_all_transitions(
    tenant: ViewerDep,
    db: DBSessionDep,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> ModelTransitionListResponse:
    """Get all transition audit records for the workspace.

    Returns a paginated list of all model lifecycle transitions
    across all models in the authenticated workspace.
    """
    service = ModelLifecycleService(db=db, tenant=tenant)
    items, total = await service.get_transitions(
        model_id=None,
        limit=limit,
        offset=offset,
    )
    return ModelTransitionListResponse(
        items=[_transition_to_response(t) for t in items],
        total=total,
        limit=limit,
        offset=offset,
    )

"""Capability Registry API Endpoint.

Routes:
    GET /api/v1/capabilities  → 200 (all capabilities with classification, providers, health)

Returns the full Capability_Registry with current classification state for
each feature. Used by the frontend to determine which UI features to show,
disable, or badge with simulation indicators.

Also used by GET /ready to derive service readiness (R19.3) and by
Hermes/Brain to answer questions about platform capabilities (R19.7).

Validates: Requirements R19.1, R19.2, R19.3, R19.7
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.schemas.capability_registry import (
    CapabilityClassificationSchema,
    CapabilityListResponse,
    CapabilityResponse,
    CapabilityTransitionResponse,
    HealthStatusSchema,
)
from app.services.capability_registry import (
    CapabilityNotFoundError,
    CapabilityRegistryService,
)

router = APIRouter(tags=["capabilities"])

# Module-level registry instance. In production this would be injected via
# dependency injection (FastAPI Depends). For now, a module-level singleton
# provides the canonical state.
_registry = CapabilityRegistryService()


def get_registry() -> CapabilityRegistryService:
    """Get the capability registry service instance.

    This function serves as the access point for the registry singleton.
    It can be overridden in tests via dependency injection.
    """
    return _registry


@router.get(
    "/capabilities",
    response_model=CapabilityListResponse,
    status_code=status.HTTP_200_OK,
    summary="List all platform capabilities",
    description=(
        "Returns all registered capabilities with their current classification, "
        "required providers, and health status. Used by frontend for feature "
        "gating, by /ready for service readiness, and by Brain/Hermes for "
        "platform awareness."
    ),
)
async def list_capabilities(
    classification: CapabilityClassificationSchema | None = Query(
        default=None,
        description="Filter capabilities by classification state",
    ),
) -> CapabilityListResponse:
    """List all capabilities with optional classification filter.

    Requirements: R19.1, R19.2, R19.3, R19.7
    """
    registry = get_registry()
    capabilities = registry.get_all_capabilities()

    # Optional classification filter
    if classification is not None:
        capabilities = [
            c for c in capabilities
            if c.classification.value == classification.value
        ]

    items = [
        CapabilityResponse(
            name=cap.name,
            classification=CapabilityClassificationSchema(cap.classification.value),
            required_providers=cap.required_providers,
            health_status=HealthStatusSchema(cap.health_status.value),
            description=cap.description,
        )
        for cap in capabilities
    ]

    return CapabilityListResponse(
        items=items,
        total=len(items),
    )


@router.get(
    "/capabilities/{name}",
    response_model=CapabilityResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a single capability",
    description="Returns a single capability by name with current state.",
)
async def get_capability(name: str) -> CapabilityResponse:
    """Get a single capability by name.

    Returns 404 if the capability is not registered.
    """
    registry = get_registry()
    try:
        cap = registry.get_capability(name)
    except CapabilityNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Capability '{name}' not found",
        )

    return CapabilityResponse(
        name=cap.name,
        classification=CapabilityClassificationSchema(cap.classification.value),
        required_providers=cap.required_providers,
        health_status=HealthStatusSchema(cap.health_status.value),
        description=cap.description,
    )


@router.get(
    "/capabilities/{name}/transitions",
    response_model=list[CapabilityTransitionResponse],
    status_code=status.HTTP_200_OK,
    summary="Get classification transition history",
    description=(
        "Returns the audit log of classification transitions for a capability. "
        "Includes timestamp, actor, and reason for each transition (R19.6)."
    ),
)
async def get_capability_transitions(
    name: str,
) -> list[CapabilityTransitionResponse]:
    """Get the transition audit log for a capability.

    Requirements: R19.6
    """
    registry = get_registry()

    # Verify capability exists
    try:
        registry.get_capability(name)
    except CapabilityNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Capability '{name}' not found",
        )

    transitions = registry.get_transitions(name)
    return [
        CapabilityTransitionResponse(
            capability_name=t.capability_name,
            previous_classification=CapabilityClassificationSchema(
                t.previous_classification.value
            ),
            new_classification=CapabilityClassificationSchema(
                t.new_classification.value
            ),
            actor=t.actor,
            reason=t.reason,
            timestamp=t.timestamp,
        )
        for t in transitions
    ]

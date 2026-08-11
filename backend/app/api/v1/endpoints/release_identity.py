"""Release Identity API endpoints.

Provides endpoints for creating and querying Release Identity records.
These are platform-level endpoints (not tenant-scoped) used by the
deployment pipeline to register new releases and by operators/services
to query the current active release.

Endpoints:
    GET  /release/current      → Get the currently active Release Identity
    GET  /release/{id}         → Get a specific Release Identity by ID
    GET  /release              → List all Release Identity records
    POST /release              → Create a new Release Identity (deployment)
    GET  /release/compare      → Compare two releases (R72.6)

Validates: Requirements R72.1, R72.2, R72.3, R72.4, R72.5, R72.6
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.core.dependencies import (
    CurrentUserIDDep,
    DBSessionDep,
    PaginationDep,
)
from app.schemas.release_identity import (
    ReleaseIdentityCompareResponse,
    ReleaseIdentityCreate,
    ReleaseIdentityListResponse,
    ReleaseIdentityResponse,
)
from app.services.release_identity_service import (
    IncompleteReleaseError,
    ReleaseIdentityService,
    ReleaseNotFoundError,
)

router = APIRouter(prefix="/release", tags=["release"])


@router.get(
    "/current",
    response_model=ReleaseIdentityResponse,
    summary="Get current active Release Identity",
    responses={
        404: {"description": "No active release identity found"},
    },
)
async def get_current_release(
    db: DBSessionDep,
) -> ReleaseIdentityResponse:
    """Get the currently active Release Identity.

    Returns the release identity record that represents the currently
    deployed version of the platform. Returns 404 if no release has
    been registered yet (e.g., in local development).

    This endpoint does not require authentication since it is used
    for operational visibility alongside /ready.
    """
    service = ReleaseIdentityService(db)
    release = await service.get_current()

    if release is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active release identity found",
        )

    return ReleaseIdentityResponse.model_validate(release)


@router.get(
    "",
    response_model=ReleaseIdentityListResponse,
    summary="List Release Identity records",
)
async def list_releases(
    db: DBSessionDep,
    current_user_id: CurrentUserIDDep,
    pagination: PaginationDep,
) -> ReleaseIdentityListResponse:
    """List all Release Identity records with pagination.

    Ordered by creation time descending (most recent first).
    Requires authentication (platform operator context).
    """
    service = ReleaseIdentityService(db)
    items, total = await service.list_releases(
        limit=pagination.limit,
        offset=pagination.offset,
    )

    return ReleaseIdentityListResponse(
        items=[ReleaseIdentityResponse.model_validate(r) for r in items],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get(
    "/compare",
    response_model=ReleaseIdentityCompareResponse,
    summary="Compare two releases (R72.6)",
    responses={
        404: {"description": "One or both release identities not found"},
    },
)
async def compare_releases(
    db: DBSessionDep,
    current_user_id: CurrentUserIDDep,
    from_id: UUID,
    to_id: UUID,
) -> ReleaseIdentityCompareResponse:
    """Compare two Release Identity records and show what changed.

    Per R72.6: given two releases, show what changed (commits,
    migrations, config, models).
    """
    service = ReleaseIdentityService(db)

    try:
        comparison = await service.compare_releases(from_id, to_id)
    except ReleaseNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.message,
        )

    # Fetch both releases for the response
    from_release = await service.get_by_id(from_id)
    to_release = await service.get_by_id(to_id)

    return ReleaseIdentityCompareResponse(
        from_release=ReleaseIdentityResponse.model_validate(from_release),
        to_release=ReleaseIdentityResponse.model_validate(to_release),
        changes=comparison["changes"],
    )


@router.get(
    "/{release_id}",
    response_model=ReleaseIdentityResponse,
    summary="Get a specific Release Identity",
    responses={
        404: {"description": "Release identity not found"},
    },
)
async def get_release_by_id(
    db: DBSessionDep,
    current_user_id: CurrentUserIDDep,
    release_id: UUID,
) -> ReleaseIdentityResponse:
    """Get a specific Release Identity by its UUID.

    Used for investigating historical releases or correlating
    a release with a specific incident timestamp (R72.4).
    """
    service = ReleaseIdentityService(db)
    release = await service.get_by_id(release_id)

    if release is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Release identity not found: {release_id}",
        )

    return ReleaseIdentityResponse.model_validate(release)


@router.post(
    "",
    response_model=ReleaseIdentityResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new Release Identity",
    responses={
        422: {"description": "Incomplete release identity — deployment blocked (R72.5)"},
    },
)
async def create_release(
    db: DBSessionDep,
    current_user_id: CurrentUserIDDep,
    data: ReleaseIdentityCreate,
) -> ReleaseIdentityResponse:
    """Create a new immutable Release Identity during deployment.

    This endpoint is called by the deployment pipeline to register
    a new release. It validates completeness (R72.5) and rejects
    deployments that cannot produce a complete Release_Identity.

    Required fields: git_commit_sha, frontend_artifact, backend_artifact,
    migration_set. Missing any of these blocks deployment.

    The new release becomes the active (is_current=True) release,
    deactivating any previous one.
    """
    service = ReleaseIdentityService(db)

    try:
        release = await service.create_release(data)
    except IncompleteReleaseError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.message,
        )

    await db.commit()

    return ReleaseIdentityResponse.model_validate(release)

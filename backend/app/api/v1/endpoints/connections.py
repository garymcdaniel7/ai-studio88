"""Connections Hub API endpoints.

Manages connection lifecycle: OAuth initiation, API key connections,
listing, updates, and deletion. Enforces RBAC per ownership type.

API Surface:
    POST   /api/v1/connections/initiate  → OAuth flow initiation (returns redirect_url)
    POST   /api/v1/connections/callback  → OAuth callback (token exchange)
    POST   /api/v1/connections           → API key connection creation (201)
    GET    /api/v1/connections           → List connections (paginated)
    GET    /api/v1/connections/{id}      → Get single connection
    PATCH  /api/v1/connections/{id}      → Update connection
    DELETE /api/v1/connections/{id}      → Delete connection (204)

Requirements: R85.1, R85.2, R85.4, R85.6, R27.4, R27.6, R92.4, R92.6
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, Field

from app.core.dependencies import DBSessionDep, WorkspaceRole
from app.core.rbac import AdminDep, EditorDep, ViewerDep
from app.schemas.connection import (
    ConnectionCategoryEnum,
    ConnectionLifecycleEnum,
    ConnectionListResponse,
    ConnectionOwnershipEnum,
    ConnectionResponse,
    ConnectionUpdate,
)
from app.services.connection_service import ConnectionService

router = APIRouter(prefix="/connections", tags=["connections"])


# =============================================================================
# Request Schemas (endpoint-specific)
# =============================================================================


class OAuthInitiateRequest(BaseModel):
    """Request schema for initiating an OAuth connection flow."""

    provider_name: str = Field(
        ..., min_length=1, max_length=100, description="Provider to connect"
    )
    category: ConnectionCategoryEnum = Field(
        ..., description="Connection category"
    )
    ownership: ConnectionOwnershipEnum = Field(
        ..., description="Connection ownership type"
    )
    display_name: str = Field(
        ..., min_length=1, max_length=200, description="Display name"
    )

    model_config = {"extra": "forbid"}


class OAuthInitiateResponse(BaseModel):
    """Response for OAuth initiation — contains redirect_url."""

    redirect_url: str = Field(..., description="URL to redirect user for OAuth consent")
    connection_id: str = Field(..., description="Connection ID for callback")
    state: str = Field(..., description="CSRF state token")


class OAuthCallbackRequest(BaseModel):
    """Request schema for completing OAuth callback."""

    connection_id: UUID = Field(..., description="Connection ID from initiation")
    code: str = Field(..., min_length=1, description="OAuth authorization code")
    state: str = Field(..., min_length=1, description="CSRF state token for verification")

    model_config = {"extra": "forbid"}


class ApiKeyConnectionRequest(BaseModel):
    """Request schema for creating an API key connection.

    The api_key is accepted ONCE and never redisplayed (R27.6).
    """

    provider_name: str = Field(
        ..., min_length=1, max_length=100, description="Provider identifier"
    )
    category: ConnectionCategoryEnum = Field(
        ..., description="Connection category"
    )
    ownership: ConnectionOwnershipEnum = Field(
        ..., description="Connection ownership type"
    )
    display_name: str = Field(
        ..., min_length=1, max_length=200, description="Display name"
    )
    api_key: str = Field(
        ..., min_length=8, max_length=500, description="API key (accepted once, never redisplayed)"
    )
    allowed_roles: list[str] = Field(
        default_factory=lambda: ["owner", "admin", "editor"],
        description="Roles permitted to use this connection",
    )
    tool_policy: dict = Field(
        default_factory=dict,
        description="Per-tool allow/deny policy",
    )

    model_config = {"extra": "forbid"}


# =============================================================================
# Endpoints
# =============================================================================


@router.post(
    "/initiate",
    response_model=OAuthInitiateResponse,
    status_code=status.HTTP_200_OK,
    summary="Initiate OAuth connection flow",
)
async def initiate_oauth_connection(
    body: OAuthInitiateRequest,
    tenant: EditorDep,
    db: DBSessionDep,
) -> OAuthInitiateResponse:
    """Initiate an OAuth connection flow.

    Returns a redirect_url for the user to complete OAuth consent.
    Workspace connections require admin/owner role (R85.6, R92.4).
    User connections require at least editor role.

    Requirements: R85.2, R27.4
    """
    # Workspace connections require admin or owner (R85.6, R92.4)
    if body.ownership == ConnectionOwnershipEnum.WORKSPACE:
        tenant.require_role(WorkspaceRole.ADMIN)

    service = ConnectionService(db=db, org_id=tenant.org_id)
    result = await service.initiate_oauth(
        provider_name=body.provider_name,
        category=body.category.value,
        ownership=body.ownership.value,
        display_name=body.display_name,
        user_id=tenant.user_id,
    )

    return OAuthInitiateResponse(
        redirect_url=result["redirect_url"],
        connection_id=result["connection_id"],
        state=result["state"],
    )


@router.post(
    "/callback",
    response_model=ConnectionResponse,
    status_code=status.HTTP_200_OK,
    summary="Complete OAuth callback",
)
async def complete_oauth_callback(
    body: OAuthCallbackRequest,
    tenant: EditorDep,
    db: DBSessionDep,
) -> ConnectionResponse:
    """Complete the OAuth callback and establish the connection.

    Exchanges the authorization code for tokens, stores them encrypted,
    discovers capabilities, and transitions connection to CONNECTED.

    Requirements: R85.2, R27.4
    """
    service = ConnectionService(db=db, org_id=tenant.org_id)
    connection = await service.complete_oauth_callback(
        connection_id=body.connection_id,
        auth_code=body.code,
    )
    return ConnectionResponse.model_validate(connection)


@router.post(
    "",
    response_model=ConnectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create API key connection",
)
async def create_api_key_connection(
    body: ApiKeyConnectionRequest,
    tenant: EditorDep,
    db: DBSessionDep,
) -> ConnectionResponse:
    """Create a connection using an API key.

    The API key is accepted once, validated, stored encrypted, and never
    redisplayed. Workspace connections require admin/owner role (R85.6).

    Requirements: R27.6, R85.6, R92.4
    """
    # Workspace connections require admin or owner (R85.6, R92.4)
    if body.ownership == ConnectionOwnershipEnum.WORKSPACE:
        tenant.require_role(WorkspaceRole.ADMIN)

    service = ConnectionService(db=db, org_id=tenant.org_id)
    connection = await service.create_api_key_connection(
        provider_name=body.provider_name,
        category=body.category.value,
        ownership=body.ownership.value,
        display_name=body.display_name,
        api_key=body.api_key,
        user_id=tenant.user_id,
        allowed_roles=body.allowed_roles,
        tool_policy=body.tool_policy,
    )
    return ConnectionResponse.model_validate(connection)


@router.get(
    "",
    response_model=ConnectionListResponse,
    summary="List connections",
)
async def list_connections(
    tenant: ViewerDep,
    db: DBSessionDep,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    category: ConnectionCategoryEnum | None = Query(None),
    ownership: ConnectionOwnershipEnum | None = Query(None),
    lifecycle_state: ConnectionLifecycleEnum | None = Query(None),
) -> ConnectionListResponse:
    """List connections for the authenticated workspace.

    Supports filtering by category, ownership, and lifecycle state.
    Requires VIEWER role (any authenticated member).
    """
    service = ConnectionService(db=db, org_id=tenant.org_id)
    items, total = await service.list_connections(
        limit=limit,
        offset=offset,
        category=category.value if category else None,
        ownership=ownership.value if ownership else None,
        lifecycle_state=lifecycle_state.value if lifecycle_state else None,
    )
    return ConnectionListResponse(
        items=[ConnectionResponse.model_validate(c) for c in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{connection_id}",
    response_model=ConnectionResponse,
    summary="Get connection details",
)
async def get_connection(
    connection_id: UUID,
    tenant: ViewerDep,
    db: DBSessionDep,
) -> ConnectionResponse:
    """Get a single connection by ID.

    Returns 404 if not found or belongs to different org.
    Requires VIEWER role.
    """
    service = ConnectionService(db=db, org_id=tenant.org_id)
    connection = await service.get_connection(connection_id)
    return ConnectionResponse.model_validate(connection)


@router.patch(
    "/{connection_id}",
    response_model=ConnectionResponse,
    summary="Update connection",
)
async def update_connection(
    connection_id: UUID,
    body: ConnectionUpdate,
    tenant: EditorDep,
    db: DBSessionDep,
) -> ConnectionResponse:
    """Update a connection's mutable fields.

    Lifecycle state transitions are validated via the state machine.
    Requires EDITOR role.
    """
    service = ConnectionService(db=db, org_id=tenant.org_id)
    connection = await service.update_connection(connection_id, body)
    return ConnectionResponse.model_validate(connection)


@router.delete(
    "/{connection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete connection",
)
async def delete_connection(
    connection_id: UUID,
    tenant: AdminDep,
    db: DBSessionDep,
) -> None:
    """Delete a connection.

    Transitions to DISCONNECTED before deletion. Requires ADMIN role
    for workspace connections. Users can delete their own USER connections.

    Requirements: R85.6, R92.4
    """
    service = ConnectionService(db=db, org_id=tenant.org_id)
    await service.delete_connection(connection_id)

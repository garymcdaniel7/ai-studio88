"""Authenticated NCII takedown API."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, Field, field_validator

from backend.auth import AuthUser, require_auth
from backend.compliance.takedown import get_takedown_service

router = APIRouter(prefix="/api/v1/compliance", tags=["compliance"])


class TakedownRequest(BaseModel):
    """Validated request for removal of a non-consensual intimate image."""

    asset_id: UUID
    claimant_email: str = Field(min_length=3, max_length=320)
    reason: str = Field(min_length=1, max_length=2_000)
    attests_authority: bool

    @field_validator("claimant_email")
    @classmethod
    def validate_email_shape(cls, value: str) -> str:
        """Require a minimally valid contact address without external I/O."""
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("claimant_email must be a valid email address")
        return value

    @field_validator("attests_authority")
    @classmethod
    def require_attestation(cls, value: bool) -> bool:
        """Require the claimant's authority attestation."""
        if not value:
            raise ValueError("attests_authority must be true")
        return value


async def _process_case(case_id: str) -> None:
    """Background task that executes removal and the identical-copy sweep."""
    get_takedown_service().process(case_id)


@router.post("/takedown", status_code=202)
async def submit_takedown(
    payload: TakedownRequest,
    background_tasks: BackgroundTasks,
    user: AuthUser = Depends(require_auth),
) -> dict[str, object]:
    """Accept a validated takedown request and queue its removal sweep."""
    case = get_takedown_service().submit(
        asset_id=str(payload.asset_id),
        claimant_email=payload.claimant_email,
        reason=payload.reason,
        org_id=user.org_id or "",
        actor_user_id=user.user_id,
        now=datetime.now(UTC),
    )
    background_tasks.add_task(_process_case, case.id)
    return case.to_dict()
